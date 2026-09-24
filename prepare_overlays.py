#!/usr/bin/env python3
"""Download/process Austria water + city overlays for the altitude map.

Sources (CC BY 4.0):
  - Lakes/reservoirs: Umweltbundesamt GGN StandingWater (INSPIRE)
  - Rivers: Umweltbundesamt GGN WatercourseLink (INSPIRE)
  - Cities: Statistik Austria municipality population + GEM polygons
"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path
from urllib.request import urlretrieve

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "overlays" / "raw"
OUT = ROOT / "overlays"
TARGET_CRS = "EPSG:31287"  # MGI / Austria Lambert (matches BEV 50 m DGM)

URLS = {
    "standing_water.zip": "https://inspire.lfrz.gv.at/000801/ds/AT_STANDINGWATER_GML.zip",
    "watercourse_link.zip": "https://inspire.lfrz.gv.at/000801/ds/AT_WATERCOURSELINK_GML.zip",
    "gem_2026.zip": (
        "https://www.statistik.gv.at/gs-open/GEODATA/ows"
        "?service=WFS&version=1.0.0&request=GetFeature"
        "&typeName=GEODATA:STATISTIK_AUSTRIA_GEM_20260101"
        "&outputFormat=SHAPE-ZIP&format_options=CHARSET:UTF-8"
    ),
    "pop_gem.csv": "https://data.statistik.gv.at/data/OGDEXT_AEST_GEMTAB_1.csv",
}


def _swap_xy(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """INSPIRE GML for EPSG:3035 is stored northing/easting; shapely expects easting/northing."""
    from shapely.ops import transform as shapely_transform

    out = gdf.copy()
    out["geometry"] = out.geometry.map(lambda g: shapely_transform(lambda x, y: (y, x), g))
    return out


def download_raw(force: bool = False) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in URLS.items():
        dest = RAW / name
        if dest.exists() and not force:
            print(f"exists: {dest.name}")
            continue
        print(f"downloading {dest.name} ...")
        urlretrieve(url, dest)

    for zname, sub in [
        ("standing_water.zip", "standing"),
        ("watercourse_link.zip", "watercourse_link"),
        ("gem_2026.zip", "gem"),
    ]:
        target = RAW / sub
        if target.exists() and any(target.iterdir()) and not force:
            continue
        target.mkdir(exist_ok=True)
        with zipfile.ZipFile(RAW / zname) as zf:
            zf.extractall(target)


def build_lakes(min_area_m2: float = 50_000) -> Path:
    print("Building lakes...")
    gml = RAW / "standing" / "AT_STANDINGWATER_GML.gml"
    lakes = gpd.read_file(gml, engine="pyogrio")
    lakes = _swap_xy(lakes)
    lakes = lakes.rename(columns={"text": "name", "surfaceArea": "area_m2"})
    lakes = lakes[lakes["area_m2"] >= min_area_m2].copy()
    lakes = lakes.drop_duplicates(subset="geometry")
    lakes = lakes.set_crs("EPSG:3035", allow_override=True).to_crs(TARGET_CRS)
    lakes = lakes[["name", "area_m2", "geometry"]]
    # Light simplify for snappier plotting
    lakes["geometry"] = lakes.geometry.simplify(25, preserve_topology=True)
    out = OUT / "lakes.gpkg"
    lakes.to_file(out, driver="GPKG")
    print(f"  {len(lakes)} lakes → {out.name}")
    return out


def build_rivers(min_length_m: float = 2000) -> Path:
    print("Building rivers...")
    gml = RAW / "watercourse_link" / "AT_WATERCOURSELINK_GML.gml"
    rivers = gpd.read_file(gml, engine="pyogrio")
    rivers = _swap_xy(rivers)
    rivers = rivers.rename(columns={"text": "name", "length": "length_m"})
    rivers = rivers[rivers["length_m"] >= min_length_m].copy()
    rivers = rivers.set_crs("EPSG:3035", allow_override=True).to_crs(TARGET_CRS)
    rivers = rivers[["name", "length_m", "geometry"]]
    rivers["geometry"] = rivers.geometry.simplify(40, preserve_topology=True)
    out = OUT / "rivers.gpkg"
    rivers.to_file(out, driver="GPKG")
    print(f"  {len(rivers)} river segments → {out.name}")
    return out


def build_cities(top_n: int = 100) -> Path:
    print("Building cities...")
    pop = pd.read_csv(RAW / "pop_gem.csv", sep=";")
    pop = pop[pop["JAHR"] == pop["JAHR"].max()].copy()
    pop["BEV_ABSOLUT"] = pd.to_numeric(pop["BEV_ABSOLUT"], errors="coerce")
    pop["GCD"] = pop["GCD"].astype(int)

    # Vienna is published as 23 districts — aggregate to one city for rankings.
    is_wien = (pop["GCD"] >= 90101) & (pop["GCD"] <= 92301)
    wien_pop = int(pop.loc[is_wien, "BEV_ABSOLUT"].sum())
    rest = pop.loc[~is_wien, ["GCD", "GEM_NAME", "BEV_ABSOLUT"]]
    ranked = pd.concat(
        [pd.DataFrame([{"GCD": 90001, "GEM_NAME": "Wien", "BEV_ABSOLUT": wien_pop}]), rest],
        ignore_index=True,
    )
    ranked = ranked.nlargest(top_n, "BEV_ABSOLUT").reset_index(drop=True)
    ranked["rank"] = ranked.index + 1

    gem = gpd.read_file(RAW / "gem" / "STATISTIK_AUSTRIA_GEM_20260101.shp")
    gem["g_id"] = gem["g_id"].astype(int)
    wien_geom = gem.loc[(gem["g_id"] >= 90101) & (gem["g_id"] <= 92301)].dissolve().geometry.iloc[0]

    rows = []
    for _, r in ranked.iterrows():
        if int(r["GCD"]) == 90001:
            geom = wien_geom.centroid
            name = "Wien"
        else:
            match = gem.loc[gem["g_id"] == int(r["GCD"])]
            if match.empty:
                print(f"  missing geometry: {r['GEM_NAME']} ({r['GCD']})")
                continue
            geom = match.geometry.iloc[0].centroid
            name = str(r["GEM_NAME"])
        rows.append(
            {
                "rank": int(r["rank"]),
                "name": name,
                "population": int(r["BEV_ABSOLUT"]),
                "geometry": geom,
            }
        )

    cities = gpd.GeoDataFrame(rows, crs=gem.crs).to_crs(TARGET_CRS)
    out = OUT / "cities_top100.gpkg"
    cities.to_file(out, driver="GPKG")
    print(f"  {len(cities)} cities → {out.name}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force-download", action="store_true")
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    if not args.skip_download:
        download_raw(force=args.force_download)
    build_lakes()
    build_rivers()
    build_cities()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
