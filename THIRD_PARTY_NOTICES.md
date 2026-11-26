# Third-party data bundled with dxcc-flagmap

| Data | Source | License |
|---|---|---|
| Flag images (`data/flags/*.png`, rendered from SVG) | [flag-icons](https://github.com/lipis/flag-icons) | MIT |
| SMOM flag (`data/flags/smom.png`, from `scripts/flags/smom.svg`) | drawn for this project | MIT |
| DXCC entity list, ISO country codes (`data/dxcc_entities.json`) | [k0swe/dxcc-json](https://github.com/k0swe/dxcc-json) | Apache-2.0 (derived from the ARRL DXCC Current/Deleted list, edition 2026-01) |
| Map base (`data/land.json`); fallback coordinates for Canada and Antarctica | [Natural Earth](https://www.naturalearthdata.com/) | Public domain |
| Entity latitude/longitude and primary prefixes (`data/dxcc_entities.json`); prefix and callsign table (`data/prefixes.json`) | Jim Reisert AD1C, [cty.dat country file](https://www.country-files.com/) | MIT ([terms](https://www.country-files.com/copyright/)); derived values only, cty.dat itself is not bundled |

`scripts/build_data.py` regenerates these files. Full license texts for the bundled data are in [`LICENSES/`](LICENSES/) (Apache-2.0 requires shipping a copy; MIT requires keeping the notice). `data/dxcc_entities.json` is a modified subset of the upstream dxcc.json with added map coordinates (from cty.dat via `scripts/apply_cty.py`).
