# reservoir_grid

Austria elevation + pumped-storage hydro inventory.

## Elevation
- BEV DGM 50 m mosaic viewer: `visualize_altitude.py`
- Optional ALS 1 m tiles: `download_als_1m.py`

## Pumped storage inventory

Formatted overview: **[`AUSTRIA_PUMPED_STORAGE.md`](AUSTRIA_PUMPED_STORAGE.md)**

```bash
.venv/bin/python build_hydro_inventory.py   # refresh CSVs
```

CSVs in `hydro_data/`: plants, plant↔reservoir links, unique reservoirs, `SOURCES.md`.

## Example reservoir map (Schlegeisspeicher)
```bash
.venv/bin/python map_reservoir_example.py           # opens plot + saves PNG
.venv/bin/python map_reservoir_example.py --no-show # PNG only
```
ALS/DGM only sees the **water surface**; depth is a geometric estimate, not a survey.
