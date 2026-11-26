import json
from pathlib import Path

import pytest

from wavelog_flagmap import cli, clublog, config, data, lotw, net, qrz, stats, wavelog, wrl
from wavelog_flagmap.adif import parse_adif
from wavelog_flagmap.render import GridOptions, MapOptions, render_grid, render_map

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample.adi"

ADIF = """header text
<adif_ver:5>3.1.4<eoh>
<call:4>W1AW<dxcc:3>291<country:24>United States of America<lotw_qsl_rcvd:1>Y<eor>
<call:5>DL1AB<country:7>Germany<eor>
<call:4>Q1ZZ<country:11>Nowhereland<eor>
"""


def test_parse_adif_skips_header_and_reads_fields():
    recs = list(parse_adif(ADIF))
    assert [r["call"] for r in recs] == ["W1AW", "DL1AB", "Q1ZZ"]
    assert recs[0]["dxcc"] == "291"


def test_parse_adif_without_eor_at_end_and_typed_fields():
    recs = list(parse_adif("<call:4:S>W1AW<qso_date:8:D>20260101"))
    assert recs == [{"call": "W1AW", "qso_date": "20260101"}]


def test_entities_loaded_and_flags_present():
    ents = data.entities()
    assert len(ents) > 300
    us = ents[291]
    assert us.iso == "us" and data.flag_path("us") is not None
    assert data.flag_path("gb-sct") is not None
    # special entities: UN and ITU fly the UN flag, SMOM and Market Reef have their own
    assert {ents[d].iso for d in (289, 117)} == {"un"}
    assert ents[246].iso == "smom" and data.flag_path("smom") is not None
    assert ents[167].iso == "ax" and data.flag_path("ax") is not None
    # every entity with a flag code ships its image (zz = deliberately flagless)
    assert not [e.dxcc for e in ents.values() if e.iso not in ("", "zz") and data.flag_path(e.iso) is None]


def test_count_entities_dxcc_number_then_callsign_fallback():
    counts, skipped = stats.count_entities(parse_adif(ADIF))
    assert counts[291].qsos == 1 and counts[291].confirmed == 1
    assert counts[230].qsos == 1 and counts[230].confirmed == 0   # no DXCC field: callsign DL -> Germany
    assert skipped == 1


def test_ranked_metric_filters_and_sorts():
    counts, _ = stats.count_entities(parse_adif(ADIF))
    assert [r.entity.dxcc for r in stats.ranked(counts, "confirmed")] == [291]
    assert len(stats.ranked(counts, "qsos")) == 2


def test_render_smoke():
    counts, _ = stats.count_entities(parse_adif(SAMPLE.read_text()))
    rows = stats.ranked(counts)
    g = render_grid(rows, GridOptions(title="T"))
    m = render_map(rows, MapOptions(width=800, footer=False))
    assert g.width > 200 and g.height > 100
    assert m.size == (800, int(800 * (78 + 56) / 360))


def test_cli_end_to_end(tmp_path):
    rc = cli.main(["--adif", str(SAMPLE), "-o", str(tmp_path), "--callsign", "N0CALL"])
    assert rc == 0
    assert (tmp_path / "dxcc-grid.png").stat().st_size > 1000
    assert (tmp_path / "dxcc-map.png").stat().st_size > 1000
    st = json.loads((tmp_path / "dxcc-stats.json").read_text())
    assert st["callsign"] == "N0CALL" and st["entities"]


def test_config_env_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_KEY", "sekret")
    p = tmp_path / "c.yaml"
    p.write_text("wavelog:\n  url: https://x.example\n  key: ${MY_KEY}\n  station_id: 3\n")
    cfg = config.load(p)
    assert cfg.wavelog_key == "sekret" and cfg.station_ids == ["3"]


def test_fetch_v1_pages_until_no_new_ids(monkeypatch):
    calls = []

    class R:
        status_code = 200

        def __init__(self, body):
            self._b = body

        def json(self):
            return self._b

    pages = [{"adif": "<call:1>A<eor>", "lastfetchedid": 10}, {"adif": "<call:1>B<eor>", "lastfetchedid": 20},
             {"adif": "", "lastfetchedid": 20}]

    def fake_post(url, json, timeout, headers=None, **_):
        calls.append((url, json["fetchfromid"]))
        return R(pages[len(calls) - 1])

    monkeypatch.setattr(wavelog.requests, "post", fake_post)
    chunks = list(wavelog.fetch_v1("https://wl.example/", "k", 1))
    assert len(chunks) == 2
    assert [c[1] for c in calls] == [0, 10, 20]
    assert calls[0][0] == "https://wl.example/index.php/api/get_contacts_adif"


class _Resp:
    def __init__(self, body, status_code=200):
        self._b, self.status_code = body, status_code

    def json(self):
        if isinstance(self._b, Exception):
            raise self._b
        return self._b


def test_fetch_v1_null_adif_when_nothing_new(monkeypatch):
    # Shape returned by Wavelog's Api::get_contacts_adif when no rows match
    body = {"status": "successful", "message": "No new QSOs available.", "lastfetchedid": 0,
            "exported_qsos": 0, "adif": None}
    monkeypatch.setattr(wavelog.requests, "post", lambda url, json, timeout, headers=None, **_: _Resp(body))
    assert list(wavelog.fetch_v1("https://wl.example", "k", 1)) == []


def test_fetch_v1_error_reason_is_reported(monkeypatch):
    import pytest
    body = {"status": "failed", "reason": "Station ID not accessible for this API key"}
    monkeypatch.setattr(wavelog.requests, "post", lambda url, json, timeout, headers=None, **_: _Resp(body, 401))
    with pytest.raises(wavelog.WavelogError, match="401.*Station ID not accessible"):
        list(wavelog.fetch_v1("https://wl.example", "k", 99))


def test_fetch_v2_pages_with_since_id_and_has_more(monkeypatch):
    calls = []
    pages = [
        {"data": {"exported": 2, "lastfetchedid": 10, "adif": "<call:1>A<eor><call:1>B<eor>"},
         "meta": {"page": 1, "has_more": True}},
        {"data": {"exported": 1, "lastfetchedid": 15, "adif": "<call:1>C<eor>"},
         "meta": {"page": 1, "has_more": False}},
    ]

    def fake_get(url, params, headers, timeout):
        calls.append((url, dict(params), headers))
        return _Resp(pages[len(calls) - 1])

    monkeypatch.setattr(wavelog.requests, "get", fake_get)
    chunks = list(wavelog.fetch_v2("https://wl.example/", "wl2_x", 3))
    assert len(chunks) == 2
    assert [c[1]["since_id"] for c in calls] == [0, 10]
    assert calls[0][1]["format"] == "adif" and calls[0][1]["station_id"] == 3
    assert calls[0][2]["Authorization"] == "Bearer wl2_x"
    assert calls[0][0] == "https://wl.example/index.php/api/v2/qso"


def test_fetch_v2_error_envelope(monkeypatch):
    import pytest
    body = {"error": {"code": "invalid_token", "message": "Token is invalid", "details": None}}
    monkeypatch.setattr(wavelog.requests, "get", lambda *a, **k: _Resp(body, 401))
    with pytest.raises(wavelog.WavelogError, match="invalid_token"):
        list(wavelog.fetch_v2("https://wl.example", "bad"))


def test_parse_station_ids_forms():
    assert config.parse_station_ids(None) == []
    assert config.parse_station_ids(1) == ["1"]
    assert config.parse_station_ids("1-3, 7") == ["1", "2", "3", "7"]
    assert config.parse_station_ids([2, "4-5", 2]) == ["2", "4", "5"]


def test_fetch_v1_sends_station_list_as_array(monkeypatch):
    sent = []
    body = {"status": "successful", "lastfetchedid": 0, "exported_qsos": 0, "adif": None}

    def fake_post(url, json, timeout, headers=None, **_):
        sent.append(json["station_id"])
        return _Resp(body)

    monkeypatch.setattr(wavelog.requests, "post", fake_post)
    list(wavelog.fetch_v1("https://wl.example", "k", ["1", "2"]))
    list(wavelog.fetch_v1("https://wl.example", "k", ["5"]))
    assert sent == [[1, 2], "5"]


def test_station_all_lists_locations_then_fetches_them(monkeypatch):
    got = {}

    def fake_get(url, timeout, headers=None, **_):
        got["url"] = url
        return _Resp([{"station_id": "1", "station_callsign": "N0CALL"}, {"station_id": "7"}])

    def fake_post(url, json, timeout, headers=None, **_):
        got["station"] = json["station_id"]
        return _Resp({"status": "successful", "lastfetchedid": 0, "adif": None})

    monkeypatch.setattr(wavelog.requests, "get", fake_get)
    monkeypatch.setattr(wavelog.requests, "post", fake_post)
    assert config.parse_station_ids("all") == []
    cfg = config.Config(wavelog_url="https://wl.example", wavelog_key="k")
    assert cli._load_qsos(cfg) == []
    assert got == {"url": "https://wl.example/index.php/api/station_info/k", "station": [1, 7]}


def test_confirmed_by_sources_and_summary():
    import pytest
    adif = ("<call:2>A1<dxcc:3>291<lotw_qsl_rcvd:1>Y<eor>"
            "<call:2>B1<dxcc:3>230<eqsl_qsl_rcvd:1>Y<eor>"
            "<call:2>C1<dxcc:3>227<qrzcom_qso_download_status:1>Y<eor>")
    counts, _ = stats.count_entities(parse_adif(adif))  # default: lotw + qsl
    assert {d for d, c in counts.items() if c.confirmed} == {291}
    counts, _ = stats.count_entities(parse_adif(adif), ["lotw", "eqsl", "qrz"])
    assert {d for d, c in counts.items() if c.confirmed} == {291, 230, 227}
    assert stats.summary(counts) == "3 worked / 3 confirmed / 3 QSOs"
    with pytest.raises(ValueError):
        stats.count_entities(parse_adif(adif), ["bogus"])


def test_map_views_and_edge_entities_stay_inside():
    counts, _ = stats.count_entities(parse_adif(
        "<dxcc:2>61<eor><dxcc:2>13<eor><dxcc:3>237<eor><dxcc:3>259<eor>"))  # FJL, Antarctica, OX, JW
    rows = stats.ranked(counts)
    assert render_map(rows, MapOptions(width=800, view="full", footer=False)).size == (800, int(800 * 142 / 360))
    assert render_map(rows, MapOptions(width=800, footer=False)).size == (800, int(800 * 134 / 360))


def test_credit_line_is_optional():
    counts, _ = stats.count_entities(parse_adif("<dxcc:3>291<eor>"))
    rows = stats.ranked(counts)
    with_credit, without = render_grid(rows), render_grid(rows, GridOptions(credit=False))
    assert with_credit.height > without.height and with_credit.width >= without.width
    assert render_map(rows, MapOptions(width=800, credit=False)).size == render_map(rows, MapOptions(width=800)).size


def test_cli_map_view_and_grid_labels(tmp_path):
    rc = cli.main(["--adif", str(SAMPLE), "-o", str(tmp_path), "--map-view", "full", "--grid-labels", "none"])
    assert rc == 0


def test_entity_by_call_prefixes_portables_and_overrides():
    def call(c):
        e = data.entity_by_call(c)
        return e.dxcc if e else None
    assert call("W1AW") == 291
    assert call("KH6/W1AW") == 110 and call("W1AW/KH6") == 110       # Hawaii either way round
    assert call("EA8/DL1ABC") == 29 and call("DL1ABC/P") == 230
    assert call("VE3XYZ/4") == 1 and call("KL7XX") == 6
    assert call("KG4AA") == 105 and call("KG4ABC") == 291            # Guantanamo is KG4 + 2 letters only
    assert call("W1AW/MM") is None and call("Q1ZZ") is None


def test_count_entities_respects_explicit_dxcc_zero_and_country_last():
    adif = ("<call:6>W1AW/M<dxcc:1>0<eor>"                       # logger says: no entity
            "<call:4>Q1ZZ<country:7>Germany<eor>")                # unknown call, country name wins
    counts, skipped = stats.count_entities(parse_adif(adif))
    assert skipped == 1 and list(counts) == [230]


class _Raw:
    def __init__(self, text, status_code=200):
        self.content, self.status_code = text.encode("utf-8"), status_code


LOTW_REPORT = ("ARRL Logbook of the World Status Report\n<PROGRAMID:4>LoTW\n<eoh>\n"
               "<CALL:5>DL1AA<BAND:3>20M<QSL_RCVD:1>Y<QSLRDATE:10>2026-01-02<DXCC:3>230<COUNTRY:7>GERMANY<eor>\n"
               "<CALL:4>JA1A<BAND:3>20M<QSL_RCVD:1>N<eor>\n")


def test_lotw_fetch_all_uploads_and_normalize(monkeypatch):
    seen = {}

    def fake_get(url, params, headers, timeout):
        seen.update(params=params, headers=headers)
        return _Raw(LOTW_REPORT)

    monkeypatch.setattr(lotw.requests, "get", fake_get)
    recs = [lotw.normalize(r) for r in parse_adif(lotw.fetch("n0call", "pw", owncall="N0CALL"))]
    assert seen["params"]["qso_qsl"] == "no" and seen["params"]["qso_query"] == "1"
    assert seen["params"]["qso_owncall"] == "N0CALL"
    assert seen["headers"]["User-Agent"].startswith("wavelog-flagmap/")
    assert recs[0]["lotw_qsl_rcvd"] == "Y" and "qsl_rcvd" not in recs[0]  # LoTW, not a paper card
    counts, skipped = stats.count_entities(recs)                    # JA1A: no DXCC field -> callsign
    assert skipped == 0 and counts[230].confirmed == 1 and counts[339].confirmed == 0
    counts, _ = stats.count_entities(recs, ["qsl"])
    assert counts[230].confirmed == 0


def test_lotw_login_failure_never_shows_the_password(monkeypatch):
    monkeypatch.setattr(lotw.requests, "get", lambda *a, **k: _Raw("<html>Username/password incorrect</html>"))
    with pytest.raises(lotw.LotwError) as e:
        lotw.fetch("n0call", "hunter2")
    assert "password" in str(e.value) and "hunter2" not in str(e.value)

    def boom(*a, **k):
        raise lotw.requests.ConnectionError("https://lotw.arrl.org/...?password=hunter2")
    monkeypatch.setattr(lotw.requests, "get", boom)
    with pytest.raises(lotw.LotwError) as e:
        lotw.fetch("n0call", "hunter2")
    assert "hunter2" not in str(e.value)


def test_station_info_error_never_shows_the_key(monkeypatch):
    def boom(*a, **k):
        raise wavelog.requests.ConnectionError("https://wl.example/index.php/api/station_info/sekret")
    monkeypatch.setattr(wavelog.requests, "get", boom)
    with pytest.raises(wavelog.WavelogError) as e:
        wavelog.station_ids_v1("https://wl.example", "sekret")
    assert "sekret" not in str(e.value)


def test_cli_adif_from_url_and_source_selection(tmp_path, monkeypatch):
    seen = []

    def fake_get(url, headers, timeout):
        seen.append(url)
        return _Raw(SAMPLE.read_text(encoding="utf-8"))

    monkeypatch.setattr(net.requests, "get", fake_get)
    assert cli.main(["--adif", "https://example.org/log.adi", "-o", str(tmp_path)]) == 0
    assert seen == ["https://example.org/log.adi"]
    c = config.Config(adif="x.adi", wavelog_url="https://wl", lotw_username="u")
    assert cli._source(c) == "adif"
    c.adif = None
    assert cli._source(c) == "wavelog"
    c.wavelog_url = None
    assert cli._source(c) == "lotw"
    c.source = "wavelog"
    with pytest.raises(SystemExit):
        cli._load_qsos(c)


def test_config_unset_env_var_is_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("LOTW_PASSWORD", raising=False)
    monkeypatch.delenv("LOTW_USERNAME", raising=False)
    p = tmp_path / "c.yaml"
    p.write_text("lotw:\n  username: ${LOTW_USERNAME}\n  password: ${LOTW_PASSWORD}\n")
    cfg = config.load(p)
    assert not cfg.lotw_username and not cfg.lotw_password and cli._source(cfg) is None


class _Http:
    def __init__(self, body, status_code=200):
        self.content = body.encode("utf-8") if isinstance(body, str) else body
        self.status_code = status_code

    def json(self):
        return json.loads(self.content)


def test_clublog_fetch_and_errors(monkeypatch):
    seen = {}

    def fake_post(url, json, headers, timeout):
        seen.update(url=url, json=json, headers=headers)
        return _Http("<eoh> <CALL:5>DL1AA<DXCC:3>230<eor>")

    monkeypatch.setattr(clublog.requests, "post", fake_post)
    assert "DL1AA" in clublog.fetch("n0call/p", "cl_tok")
    assert seen["url"] == "https://clublog.org/api/v1/logs/N0CALL/P/adif-export" and seen["json"] == {}
    assert seen["headers"]["Authorization"] == "Bearer cl_tok" and "User-Agent" in seen["headers"]
    err = '{"error":{"code":"unauthorized","message":"Send Authorization: Bearer <token>.","details":null}}'
    monkeypatch.setattr(clublog.requests, "post", lambda *a, **k: _Http(err, 401))
    with pytest.raises(clublog.ClublogError, match="401.*CLUBLOG_TOKEN"):
        clublog.fetch("N0CALL", "bad")


def test_qrz_fetch_pages_by_logid_and_normalizes(monkeypatch):
    from urllib.parse import quote
    recs = [f"<call:5>DL1A{i}<dxcc:3>230<app_qrzlog_logid:3>{100 + i}<app_qrzlog_status:1>{'C' if i == 0 else 'N'}<eor>"
            for i in range(5)]
    calls = []

    def fake_post(url, data, headers, timeout):
        calls.append(data["OPTION"])
        opts = dict(o.split(":") for o in data["OPTION"].split(","))
        after, size = int(opts["AFTERLOGID"]), int(opts["MAX"])
        page = [r for i, r in enumerate(recs) if 100 + i >= after][:size]
        if not page:
            return _Http("COUNT=0&RESULT=FAIL")  # what QRZ really sends past the end
        return _Http(f"RESULT=OK&COUNT=5&ADIF={quote(''.join(page))}")

    monkeypatch.setattr(qrz.requests, "post", fake_post)
    out = [qrz.normalize(r) for chunk in qrz.fetch("KEY", page=2) for r in parse_adif(chunk)]
    assert calls == ["MAX:2,AFTERLOGID:0", "MAX:2,AFTERLOGID:102", "MAX:2,AFTERLOGID:104"]
    assert len(out) == 5 and out[0]["qrzcom_qso_download_status"] == "Y"
    assert "qrzcom_qso_download_status" not in out[1]
    counts, _ = stats.count_entities(out, ["qrz"])
    assert counts[230].confirmed == 1
    calls.clear()  # a log that ends exactly on a page boundary: the next fetch is past the end
    assert len([r for chunk in qrz.fetch("KEY", page=5) for r in parse_adif(chunk)]) == 5
    assert calls == ["MAX:5,AFTERLOGID:0", "MAX:5,AFTERLOGID:105"]


def test_qrz_response_parsing_and_auth_error(monkeypatch):
    raw = qrz._parse("RESULT=OK&COUNT=1&ADIF=&lt;call:4&gt;K1AB&lt;eor&gt;")   # HTML-escaped (what QRZ sends)
    assert raw["RESULT"] == "OK" and raw["ADIF"] == "<call:4>K1AB<eor>"
    raw = qrz._parse("RESULT=OK&ADIF=<call:4>K1AB<comment:3>a&b<eor>&COUNT=1")  # raw '&' inside the ADIF
    assert "a&b" in raw["ADIF"]
    monkeypatch.setattr(qrz.requests, "post",
                        lambda *a, **k: _Http("RESULT=AUTH&REASON=invalid api key"))
    with pytest.raises(qrz.QrzError, match="subscription"):
        list(qrz.fetch("KEY"))


def test_wrl_pages_by_cursor_and_maps_contacts(monkeypatch):
    pages = {
        None: {"data": [{"call": "DL1AA", "timestamp": "2026-11-20T14:05:00Z", "band": 20, "mode": "FT8",
                         "dxcc": 230, "isDuplicate": False},
                        {"call": "DL1AA", "timestamp": "2026-11-20T14:05:00Z", "band": 20, "dxcc": 230,
                         "isDuplicate": True}],
               "meta": {"count": 2, "nextCursor": "abc"}, "error": None},
        "abc": {"data": [{"call": "JA1XYZ", "timestamp": "2026-11-19T01:00:00Z", "band": 0.7, "dxcc": None}],
                "meta": {"count": 1, "nextCursor": None}, "error": None},
    }
    seen = []

    def fake_get(url, params, headers, timeout):
        seen.append((params.get("cursor"), params["limit"], headers["Authorization"]))
        return _Http(json.dumps(pages[params.get("cursor")]))

    monkeypatch.setattr(wrl.requests, "get", fake_get)
    recs = list(wrl.fetch("wrl_live_x"))
    assert [s[0] for s in seen] == [None, "abc"] and seen[0][1] == 100 and seen[0][2] == "Bearer wrl_live_x"
    assert recs[0] == {"call": "DL1AA", "qso_date": "20261120", "time_on": "1405", "band": "20m",
                       "mode": "FT8", "dxcc": "230"}
    assert len(recs) == 2 and recs[1]["band"] == "70cm" and "dxcc" not in recs[1]   # duplicate skipped
    counts, skipped = stats.count_entities(recs)
    assert set(counts) == {230, 339} and skipped == 0                   # JA from the callsign
    assert stats.summary(counts, confirmations=False) == "2 worked / 2 QSOs"


def test_wrl_error_and_confirmed_metric(monkeypatch):
    body = {"data": None, "meta": None, "error": {"code": "MEMBERSHIP_REQUIRED", "message": "Upgrade"}}
    monkeypatch.setattr(wrl.requests, "get", lambda *a, **k: _Http(json.dumps(body), 403))
    with pytest.raises(wrl.WrlError, match="MEMBERSHIP_REQUIRED"):
        list(wrl.fetch("k"))
    monkeypatch.setenv("WRL_API_KEY", "k")
    with pytest.raises(SystemExit, match="no confirmation"):
        cli.main(["--source", "wrl", "--metric", "confirmed"])


def test_wavelog_refuses_plain_http_except_localhost_or_when_allowed():
    with pytest.raises(wavelog.WavelogError, match="unencrypted"):
        wavelog.check_url("http://log.example.com")
    wavelog.check_url("https://log.example.com")
    wavelog.check_url("http://localhost:8086")
    wavelog.check_url("http://192.168.1.5", allow_http=True)
    with pytest.raises(wavelog.WavelogError, match="https://"):
        wavelog.check_url("log.example.com")


def test_cli_stops_before_sending_a_key_over_http(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise AssertionError("no request may be sent")
    monkeypatch.setattr(wavelog.requests, "get", boom)
    monkeypatch.setattr(wavelog.requests, "post", boom)
    monkeypatch.setenv("WAVELOG_API_KEY", "secret")
    with pytest.raises(SystemExit, match="unencrypted"):
        cli.main(["--url", "http://log.example.com", "-o", str(tmp_path)])


class _Redirect:
    status_code = 301
    headers = {"Location": "https://user:pw@new.example.com/index.php/api/station_info/SECRETKEY?x=1"}

    def json(self):
        raise ValueError


def test_wavelog_does_not_follow_redirects_and_hides_the_target_path(monkeypatch):
    seen = {}

    def fake_get(url, headers, timeout, allow_redirects=True):
        seen["redirects"] = allow_redirects
        return _Redirect()

    def fake_post(url, json, headers, timeout, allow_redirects=True):
        seen["post_redirects"] = allow_redirects
        return _Redirect()
    monkeypatch.setattr(wavelog.requests, "get", fake_get)
    monkeypatch.setattr(wavelog.requests, "post", fake_post)
    with pytest.raises(wavelog.WavelogError, match="redirected") as e:
        wavelog.station_ids_v1("https://log.example.com", "SECRETKEY")
    assert "https://new.example.com" in str(e.value)
    assert "SECRETKEY" not in str(e.value) and "pw" not in str(e.value)
    with pytest.raises(wavelog.WavelogError, match="redirected"):
        list(wavelog.fetch_v1("https://log.example.com", "SECRETKEY", 1))
    assert seen == {"redirects": False, "post_redirects": False}


def test_adif_url_errors_hide_query_and_credentials(monkeypatch):
    monkeypatch.setattr(net.requests, "get", lambda *a, **k: _Raw("nope", 403))
    with pytest.raises(net.FetchError) as e:
        net.fetch_text("https://me:pw@files.example.com/log.adi?token=SIGNED&dl=1")
    msg = str(e.value)
    assert "files.example.com/log.adi" in msg and "SIGNED" not in msg and "pw" not in msg


def test_wrl_retry_after_accepts_seconds_and_http_dates():
    assert wrl._retry_after("12") == 12
    assert wrl._retry_after(None) == 60
    assert wrl._retry_after("soon") == 60
    assert wrl._retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0  # in the past
