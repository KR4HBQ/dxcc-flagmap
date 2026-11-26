# CLAUDE.md - wavelog-flagmap

Open-source (MIT) Python tool: reads QSOs from Wavelog (API) or an ADIF file and renders a
Flag Counter-style flag grid + world map as static PNGs for embedding in a QRZ.com bio.
Owner: Neal (KR4HBQ). Intended audience: any Wavelog user, so nothing may be hardcoded to Neal.

## Decisions already made
- MIT license. Python >= 3.10 (3.9 is EOL and gone from GitHub runners), Pillow for rendering, no heavy deps.
- Sources: Wavelog API (default, no DB access), LoTW (`--source lotw`, LOTW_USERNAME/LOTW_PASSWORD env), ADIF file
  or URL (`--adif`, any logger). LoTW VERIFIED live 2026-11-25: 125 worked like Wavelog, 96 LoTW-confirmed vs
  Wavelog's 95 (one confirmation Wavelog had not synced yet); the report takes ~3 min for 5k QSOs. Auto order: adif, wavelog, lotw. Every request sends net.USER_AGENT.
  Credentials that sit in a URL (LoTW password, Wavelog station_info key) must never reach error messages;
  ADIF URLs are shown without query/userinfo (`net.redact`). Wavelog refuses plain http:// (key in clear) unless
  localhost or `--allow-http`, and never follows redirects (v1 key is in the POST body, station_info key in the path).
  Security audit 2026-11-26: publish.yml has per-job permissions, actions pinned to SHAs (Dependabot updates),
  hash-pinned requirements-publish.txt (regenerate with pip-compile --generate-hashes when deps change), tool run
  from src/ with no build step; WAVELOG_URL/LOTW_USERNAME/ADIF_URL may be secrets (public logs show vars).
- Club Log (clublog.py: REST `POST /api/v1/logs/{call}/adif-export`, Bearer `cl_` token from Settings > API, 500
  requests/day) VERIFIED live 2026-11-25: 125 worked / 96 confirmed, every entity identical to Wavelog. Export has
  DXCC and only QSL_RCVD (LoTW + cards merged; no LOTW_QSL_RCVD), so confirmed_by lotw alone gives 0 there.
- QRZ Logbook (qrz.py: `ACTION=FETCH`, `OPTION=MAX:250,AFTERLOGID:n`, subscription needed,
  APP_QRZLOG_STATUS=C -> confirmed_by qrz) VERIFIED live 2026-11-25: 5,178 QSOs in 18 s, every entity identical
  to Wavelog, lotw,qsl = 96 confirmed (lotw alone 95). ADIF comes HTML-escaped (&lt;...&gt;); past the last page
  QRZ answers "COUNT=0&RESULT=FAIL" with no REASON. The export carries the logger's LOTW/QSL/eQSL fields.
  QRZ's own "confirmed" (status C) is far looser: 125/125 entities.
- World Radio League (wrl.py: JSON `GET /v1/contacts`, Bearer `wrl_live_` key, 100/page, `meta.nextCursor`
  paging, 120 reads/min) VERIFIED live 2026-11-25: 5,043 contacts in 38 s, all with dxcc, no duplicates; every
  entity matches Wavelog except one QSO not yet uploaded to WRL. Contacts carry NO confirmation
  status, so the WRL footer omits "confirmed" and --metric confirmed is refused. isDuplicate contacts skipped.
- Not supported: Cloudlog (no export API), Ham2K PoLo (on-device only, manual ADIF export), HamRS (sync is
  private to its apps; users can upload to QRZ and use --source qrz).
- QRZ bios allow basic HTML + external images, not JS/iframes -> output is static PNG with stable filenames,
  regenerated on a schedule and hosted somewhere public.
- Offline rendering: flags (flag-icons, MIT), land polygons (Natural Earth), DXCC list (k0swe/dxcc-json) and entity coordinates (from AD1C cty.dat) are bundled.
- Secrets only via env vars (`${VAR}` expansion in config); never commit keys or callsign-specific config.

## Layout
- `src/wavelog_flagmap/` adif.py (parser), wavelog.py (API v1/v2 client), lotw.py (LoTW lotwreport.adi), net.py
  (User-Agent, ADIF-from-URL), stats.py, render.py (grid + map), config.py, cli.py
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
   Re-run when cty.dat adds entities. Also copies the primary prefix and writes
   data/prefixes.json (prefix + exact-call table; WAE records mapped via WAE_PARENT) for `data.entity_by_call`,
   used when a QSO has no DXCC field (order: DXCC field, callsign, country name; DXCC 0 = no entity).
   Matches Wavelog on 99.87% of a real 5k-QSO log; misses are moved KL7/KH6/KP4 hams (Big CTY has more
   exact calls if that ever matters). Cloudlog has no ADIF export API (checked 2026-11-25). cty.dat is MIT (country-files.com/copyright), notice in LICENSES/cty-dat-MIT.txt.
4. Special flags: UN HQ and ITU HQ use flag-icons `un` (the ITU emblem is a protected IGO emblem, not bundled),
   SMOM uses `scripts/flags/smom.svg` (own drawing; build_data.py falls back to scripts/flags/), Market Reef uses `ax`.
   Only Spratly Islands is still `zz` (grey placeholder; disputed, no neutral flag).
5. Hosting: `.github/workflows/publish.yml` (nightly, GitHub Pages, config only via repo vars/secret, skipped unless
   WAVELOG_URL, LOTW_USERNAME, ADIF_URL or FLAGMAP_SOURCE is a variable; keepalive (own job) re-enables itself against the 60-day schedule shutoff; the API call succeeds, whether it
   actually resets the 60-day timer is unconfirmed). LIVE since 2026-11-25 for the owner's setup (repo secrets + vars, not files). Hardened workflow
   VERIFIED 2026-11-26 (run #5): hash-pinned install, Wavelog URL as a secret, Pages deploy failed once and the
   retry after 90 s succeeded.
   Optional: publish to PyPI, WordPress/SFTP upload plugin,
   per-band or per-mode filters, "worked vs confirmed" overlay.
6. Confirm the dxcc-json (Apache-2.0) attribution in THIRD_PARTY_NOTICES.md is sufficient before a 1.0 release.

## Dev
`pip install -e ".[dev]" && pytest`. Keep tests offline (the API client is tested with monkeypatched requests).
