# CLAUDE.md - wavelog-flagmap

Open-source (MIT) Python tool: reads QSOs from Wavelog (API) or an ADIF file and renders a
Flag Counter-style flag grid + world map as static PNGs for embedding in a QRZ.com bio.
Owner: Neal (KR4HBQ). Intended audience: any Wavelog user, so nothing may be hardcoded to Neal.

## Decisions already made
- MIT license. Python >= 3.9, Pillow for rendering, no heavy deps.
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
   errors `{status: failed, reason}` with 4xx; 20000 QSOs/call default). v2 rewritten from the docs
   (`data.{exported,lastfetchedid,adif}`, `meta.has_more`, page via `since_id`), still EXPERIMENTAL: not run live yet.
2. Test with a real log (Neal's Wavelog, ~hundreds of entities) and tune the look (spacing, crowded Europe).
3. Entity coordinates now come from AD1C cty.dat (`scripts/apply_cty.py <cty.dat>` after build_data.py; matches by
   name, ALIASES prefix table, then prefix; KEEP = Canada/Antarctica stay on Natural Earth points). cty.dat is not bundled.
   Re-run when cty.dat adds entities.
4. Some entities have no flag (`zz`): grey placeholder. Consider special icons (UN, SMOM, ITU).
5. Optional: publish to PyPI, add GitHub Actions workflow for scheduled runs, WordPress/SFTP upload plugin,
   per-band or per-mode filters, "worked vs confirmed" overlay.
6. Confirm the dxcc-json (Apache-2.0) attribution in THIRD_PARTY_NOTICES.md is sufficient before a 1.0 release.

## Dev
`pip install -e ".[dev]" && pytest`. Keep tests offline (the API client is tested with monkeypatched requests).
