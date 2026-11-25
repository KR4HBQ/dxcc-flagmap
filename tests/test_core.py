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
<call:5>XX9ZZ<country:11>Nowhereland<eor>
"""


def test_parse_adif_skips_header_and_reads_fields():
    recs = list(parse_adif(ADIF))
    assert [r["call"] for r in recs] == ["W1AW", "DL1AB", "XX9ZZ"]
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


def test_count_entities_dxcc_number_then_country_name_fallback():
    counts, skipped = stats.count_entities(parse_adif(ADIF))
    assert counts[291].qsos == 1 and counts[291].confirmed == 1
    assert counts[230].qsos == 1 and counts[230].confirmed == 0   # matched by name: Germany
    assert skipped == 1


def test_ranked_metric_filters_and_sorts():
    counts, _ = stats.count_entities(parse_adif(ADIF))
    assert [r.entity.dxcc for r in stats.ranked(counts, "confirmed")] == [291]
    assert len(stats.ranked(counts, "qsos")) == 2


def test_render_smoke():
    counts, _ = stats.count_entities(parse_adif(SAMPLE.read_text()))
    rows = stats.ranked(counts)
    g = render_grid(rows, GridOptions(title="T"))
    m = render_map(rows, MapOptions(width=800))
    assert g.width > 200 and g.height > 100
    assert m.size == (800, 315)


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
    assert cfg.wavelog_key == "sekret" and cfg.station_id == "3"


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
