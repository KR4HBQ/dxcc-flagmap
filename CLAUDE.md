# CLAUDE.md - wavelog-flagmap

Open-source (MIT) Python tool: reads QSOs from Wavelog (API) or an ADIF file and renders a
Flag Counter-style flag grid + world map as static PNGs for embedding in a QRZ.com bio.
Owner: Neal (KR4HBQ). Intended audience: any Wavelog user, so nothing may be hardcoded to Neal.

## Decisions already made
- MIT license. Python >= 3.10 (3.9 is EOL and gone from GitHub runners), Pillow for rendering, no heavy deps.
- Wavelog API is the default source (portable, no DB access). ADIF file is the alternative.
- QRZ bios allow basic HTML + external images, not JS/iframes -> output is static PNG with stable filenames,
  regenerated on a schedule and hosted somewhere public.
- Offline rendering: flags (flag-icons, MIT), land polygons (Natural Earth), DXCC list (k0swe/dxcc-json) and entity coordinates (from AD1C cty.dat) are bundled.
- Secrets only via env vars (`${VAR}` expansion in config); never commit keys or callsign-specific config.

## Layout
- `src/wavelog_flagmap/` adif.py (parser), wavelog.py (API v1/v2 client), stats.py, render.py (grid + map), config.py, cli.py
- `src/wavelog_flagmap/data/` generated data; rebuild with `scripts/build_data.py` (needs cairosvg, flag-icons npm package, Natural Earth GeoJSON)
- `examples/` config + synthetic sample ADIF (`make_sample.py`); `docs/` README images

## Open items / next steps
1. **Wavelog API clients.** v1 checked against Wavelog's `Api::get_contacts_adif` source (JSON body `key`,
   `station_id`, `fetchfromid`; response `status`, `lastfetchedid`, `exported_qsos`, `adif` (null when empty);
   errors `{status: failed, reason}` with 4xx; 20000 QSOs/call default; `lastfetchedid` comes back as a string).
   VERIFIED live 2026-11-25. `station_id: all` (default) lists ids via `GET /api/station_info/{key}`. v2 rewritten from the docs
   (`data.{exported,lastfetchedid,adif}`, `meta.has_more`, page via `since_id`), VERIFIED live 2026-11-25: identical QSOs to v1.
2. Real-log tuning done (2026-11-25, ~5k QSOs / 124 entities): prefix labels under grid counts, box-based map
   spreading, `confirmed_by` (default lotw,qsl = Wavelog DXCC page default; 124 worked / 96 confirmed matched Wavelog exactly). QRZ embed checked: grid fonts/flags enlarged, map
   `view: cropped` (78N..56S, default) or `full`, flags 36x27, kept in bounds, footer in its own strip under the map.
3. Entity coordinates now come from AD1C cty.dat (`scripts/apply_cty.py <cty.dat>` after build_data.py; matches by
   name, ALIASES prefix table, then prefix; KEEP = Canada/Antarctica stay on Natural Earth points). cty.dat is not bundled.
   Re-run when cty.dat adds entities. Also copies the primary prefix. cty.dat is MIT (country-files.com/copyright), notice in LICENSES/cty-dat-MIT.txt.
4. Some entities have no flag (`zz`): grey placeholder. Consider special icons (UN, SMOM, ITU).
5. Hosting: `.github/workflows/publish.yml` (nightly, GitHub Pages, config only via repo vars/secret, skipped when
   `vars.WAVELOG_URL` is unset; keepalive re-enables itself against the 60-day schedule shutoff; the API call succeeds, whether it
   actually resets the 60-day timer is unconfirmed). LIVE since 2026-11-25 for the owner's setup (repo vars, not files).
   Optional: publish to PyPI, WordPress/SFTP upload plugin,
   per-band or per-mode filters, "worked vs confirmed" overlay.
6. Confirm the dxcc-json (Apache-2.0) attribution in THIRD_PARTY_NOTICES.md is sufficient before a 1.0 release.

## Dev
`pip install -e ".[dev]" && pytest`. Keep tests offline (the API client is tested with monkeypatched requests).
