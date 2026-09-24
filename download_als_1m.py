#!/usr/bin/env python3
"""Download BEV ALS DTM 1 m elevation tiles (GeoTIFF / COG).

Catalog (correct series):
  https://data.bev.gv.at/geonetwork/srv/ger/catalog.search#/metadata/ec12896e-1ecd-47ad-8d48-44d236e383cc
  Serie ALS DTM Höhenraster 1m — Stichtag 15.09.2025 (CC BY 4.0)

Important:
  The PDFs / tile-overview shapefile are ONLY indexes & survey-currency metadata.
  The actual altitude data are 55 GeoTIFF tiles under:
    https://data.bev.gv.at/download/ALS/DTM/20250915/ALS_DTM_<TILE_ID>.tif
  Tile sizes typically range from ~0.1 GB (border) to several GB each.
  All 55 tiles together are on the order of hundreds of GB — download selectively.
"""

from __future__ import annotations

import argparse
import csv
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TILE_CSV = ROOT / "overlays" / "als_1m_tiles.csv"
OUT_DIR = ROOT / "ALS_DTM_1m"
BASE_URL = "https://data.bev.gv.at/download/ALS/DTM/20250915/"


def load_tiles() -> list[dict[str, str]]:
    if not TILE_CSV.exists():
        raise FileNotFoundError(
            f"Missing {TILE_CSV}. Unzip ALS_Kacheluebersicht.zip and regenerate, "
            "or re-run after the tile overview shapefile is present."
        )
    with TILE_CSV.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def remote_size(url: str) -> int | None:
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            length = resp.headers.get("Content-Length")
            return int(length) if length else None
    except Exception:
        return None


def list_tiles(show_sizes: bool = False) -> None:
    tiles = load_tiles()
    print(f"{len(tiles)} tiles  |  series folder: {BASE_URL}\n")
    total = 0
    known = 0
    for t in tiles:
        line = t["tile_id"]
        if show_sizes:
            size = remote_size(t["url"])
            if size is not None:
                total += size
                known += 1
                line += f"  {size / 1e9:.2f} GB"
            else:
                line += "  (size unknown)"
        print(line)
    if show_sizes and known:
        print(f"\nSum of {known} reported sizes: {total / 1e9:.1f} GB")
    print(f"\nDownload example:\n  python download_als_1m.py --tile {tiles[0]['tile_id']}")


def download_one(tile_id: str, out_dir: Path, force: bool = False) -> Path:
    tiles = {t["tile_id"]: t for t in load_tiles()}
    # allow short form without ALS_DTM_ prefix / with .tif
    key = tile_id.replace("ALS_DTM_", "").replace(".tif", "")
    if key not in tiles:
        raise KeyError(f"Unknown tile id: {tile_id}")

    url = tiles[key]["url"]
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"ALS_DTM_{key}.tif"
    expected = remote_size(url)

    if dest.exists() and not force:
        local = dest.stat().st_size
        if expected is not None and local < expected:
            print(
                f"incomplete file: {dest.name} "
                f"({local / 1e9:.2f} GB local vs {expected / 1e9:.2f} GB remote) — re-downloading"
            )
            dest.unlink()
        elif expected is not None and local == expected:
            print(f"already exists: {dest} ({local / 1e9:.2f} GB)")
            return dest
        elif expected is None:
            print(f"already exists: {dest} ({local / 1e9:.2f} GB) — could not verify remote size")
            return dest
        else:
            # local larger than expected is unusual; keep unless --force
            print(f"already exists: {dest} ({local / 1e9:.2f} GB)")
            return dest

    size_txt = f"{expected / 1e9:.2f} GB" if expected else "unknown size"
    print(f"Downloading {dest.name} ({size_txt})")
    print(f"  {url}")

    tmp = dest.with_suffix(dest.suffix + ".part")
    if tmp.exists():
        tmp.unlink()

    def _progress(block_num: int, block_size: int, total_size: int) -> None:
        if total_size <= 0:
            return
        done = min(block_num * block_size, total_size)
        pct = 100.0 * done / total_size
        if block_num % 50 == 0 or done >= total_size:
            print(f"\r  {pct:5.1f}%  {done / 1e9:.2f}/{total_size / 1e9:.2f} GB", end="", flush=True)

    try:
        urllib.request.urlretrieve(url, tmp, reporthook=_progress)
        print()
        got = tmp.stat().st_size
        if expected is not None and got != expected:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(
                f"download size mismatch for {dest.name}: got {got} bytes, expected {expected}"
            )
        tmp.replace(dest)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    print(f"  saved {dest} ({dest.stat().st_size / 1e9:.2f} GB)")
    return dest


def find_tiles_for_point(easting_3035: float, northing_3035: float) -> list[str]:
    hits = []
    for t in load_tiles():
        if float(t["minx"]) <= easting_3035 <= float(t["maxx"]) and float(t["miny"]) <= northing_3035 <= float(
            t["maxy"]
        ):
            hits.append(t["tile_id"])
    return hits


# Approximate city centers in EPSG:3035 (ETRS89 / LAEA Europe)
CITY_3035 = {
    "wien": (4793000, 2805000),
    "vienna": (4793000, 2805000),
    "graz": (4654000, 2680000),
    "linz": (4578000, 2795000),
    "salzburg": (4475000, 2748000),
    # Verified via EPSG:31287 city centroid → EPSG:3035
    "innsbruck": (4425504.0, 2687116.0),
    "klagenfurt": (4555000, 2618000),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true", help="List all 55 tile IDs")
    parser.add_argument("--sizes", action="store_true", help="With --list, HEAD-request each tile size")
    parser.add_argument("--tile", action="append", default=[], help="Download tile id (repeatable)")
    parser.add_argument(
        "--city",
        type=str,
        help=f"Download tile(s) covering a city center. Known: {', '.join(sorted(CITY_3035))}",
    )
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--force", action="store_true", help="Re-download even if file exists")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Download ALL 55 tiles (hundreds of GB — confirmation required)",
    )
    args = parser.parse_args()

    if args.list or (not args.tile and not args.city and not args.all):
        list_tiles(show_sizes=args.sizes)
        if not args.tile and not args.city and not args.all:
            return 0

    to_get: list[str] = list(args.tile)
    if args.city:
        key = args.city.strip().lower()
        if key not in CITY_3035:
            print(f"Unknown city '{args.city}'. Known: {', '.join(sorted(CITY_3035))}", file=sys.stderr)
            return 1
        e, n = CITY_3035[key]
        hits = find_tiles_for_point(e, n)
        if not hits:
            print("No tile found for that point.", file=sys.stderr)
            return 1
        print(f"City {args.city}: tiles {hits}")
        to_get.extend(hits)

    if args.all:
        tiles = load_tiles()
        print(f"About to download {len(tiles)} tiles into {args.out_dir}")
        print("This can be on the order of HUNDREDS of GB.")
        confirm = input("Type YES to continue: ").strip()
        if confirm != "YES":
            print("Aborted.")
            return 1
        to_get = [t["tile_id"] for t in tiles]

    if not to_get:
        return 0

    for tid in dict.fromkeys(to_get):  # unique, keep order
        download_one(tid, args.out_dir, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
