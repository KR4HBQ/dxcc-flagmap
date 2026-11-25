import json
from pathlib import Path

from wavelog_flagmap import cli, config, data, stats, wavelog
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

    def fake_post(url, json, timeout):
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
    monkeypatch.setattr(wavelog.requests, "post", lambda url, json, timeout: _Resp(body))
    assert list(wavelog.fetch_v1("https://wl.example", "k", 1)) == []


def test_fetch_v1_error_reason_is_reported(monkeypatch):
    import pytest
    body = {"status": "failed", "reason": "Station ID not accessible for this API key"}
    monkeypatch.setattr(wavelog.requests, "post", lambda url, json, timeout: _Resp(body, 401))
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

    def fake_post(url, json, timeout):
        sent.append(json["station_id"])
        return _Resp(body)

    monkeypatch.setattr(wavelog.requests, "post", fake_post)
    list(wavelog.fetch_v1("https://wl.example", "k", ["1", "2"]))
    list(wavelog.fetch_v1("https://wl.example", "k", ["5"]))
    assert sent == [[1, 2], "5"]


def test_station_all_lists_locations_then_fetches_them(monkeypatch):
    got = {}

    def fake_get(url, timeout):
        got["url"] = url
        return _Resp([{"station_id": "1", "station_callsign": "N0CALL"}, {"station_id": "7"}])

    def fake_post(url, json, timeout):
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
