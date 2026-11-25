# Third-party data bundled with wavelog-flagmap

| Data | Source | License |
|---|---|---|
| Flag images (`data/flags/*.png`, rendered from SVG) | [flag-icons](https://github.com/lipis/flag-icons) | MIT |
| DXCC entity list, ISO country codes (`data/dxcc_entities.json`) | [k0swe/dxcc-json](https://github.com/k0swe/dxcc-json) | Apache-2.0 (derived from the ARRL DXCC Current/Deleted list, edition 2026-01) |
| Map base and entity label points (`data/land.json`, coordinates) | [Natural Earth](https://www.naturalearthdata.com/) | Public domain |

`scripts/build_data.py` regenerates these files. Apache-2.0 requires keeping the upstream license notice; see https://github.com/k0swe/dxcc-json/blob/main/LICENSE.
