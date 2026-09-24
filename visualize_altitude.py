#!/usr/bin/env python3
"""Interactive visualization of the BEV 50 m Austria elevation model (DGM)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent / "DGM_Rasterweite_50m"
CACHE_PATH = DATA_DIR / "_mosaic_50m.npz"


def _parse_asc_header(path: Path) -> dict[str, float]:
    header: dict[str, float] = {}
    with path.open() as f:
        for _ in range(6):
            key, value = f.readline().split()
            header[key] = float(value)
    return header


def _load_asc(path: Path) -> tuple[dict[str, float], np.ndarray]:
    header = _parse_asc_header(path)
    nrows = int(header["nrows"])
    ncols = int(header["ncols"])
    data = np.loadtxt(path, skiprows=6, dtype=np.float32)
    if data.shape != (nrows, ncols):
        raise ValueError(f"{path.name}: expected shape {(nrows, ncols)}, got {data.shape}")
    return header, data


def build_mosaic(data_dir: Path, force: bool = False) -> tuple[np.ndarray, dict[str, float]]:
    """Assemble ASC tiles into one elevation grid. Cache as .npz for faster reruns."""
    if CACHE_PATH.exists() and not force:
        print(f"Loading cached mosaic: {CACHE_PATH.name}")
        cached = np.load(CACHE_PATH)
        meta = {k: float(cached[k]) for k in ("xllcorner", "yllcorner", "cellsize", "ncols", "nrows")}
        return cached["elevation"], meta

    tiles = sorted(data_dir.glob("*_R50.asc"))
    if not tiles:
        raise FileNotFoundError(f"No *_R50.asc tiles found in {data_dir}")

    print(f"Building mosaic from {len(tiles)} tiles (first run caches to disk)...")
    headers = []
    arrays = []
    t0 = time.perf_counter()
    for i, path in enumerate(tiles, 1):
        header, arr = _load_asc(path)
        headers.append(header)
        arrays.append(arr)
        if i % 10 == 0 or i == len(tiles):
            print(f"  loaded {i}/{len(tiles)}")

    cellsize = headers[0]["cellsize"]
    xlls = np.array([h["xllcorner"] for h in headers])
    ylls = np.array([h["yllcorner"] for h in headers])
    ncols_t = int(headers[0]["ncols"])
    nrows_t = int(headers[0]["nrows"])

    xll = float(xlls.min())
    yll = float(ylls.min())
    xmax = float((xlls + (ncols_t - 1) * cellsize).max())
    ymax = float((ylls + (nrows_t - 1) * cellsize).max())

    ncols = int(round((xmax - xll) / cellsize)) + 1
    nrows = int(round((ymax - yll) / cellsize)) + 1

    mosaic = np.full((nrows, ncols), np.nan, dtype=np.float32)
    for header, arr in zip(headers, arrays):
        col0 = int(round((header["xllcorner"] - xll) / cellsize))
        row0 = int(round((ymax - (header["yllcorner"] + (nrows_t - 1) * cellsize)) / cellsize))
        nodata = header["NODATA_value"]
        tile = arr.copy()
        tile[(tile == nodata) | (tile <= -9000)] = np.nan
        # Some BEV tiles use 0 as NODATA; Austria's true elevations are well above that.
        if nodata == 0:
            tile[arr == 0] = np.nan
        mosaic[row0 : row0 + nrows_t, col0 : col0 + ncols_t] = tile

    meta = {
        "xllcorner": xll,
        "yllcorner": yll,
        "cellsize": float(cellsize),
        "ncols": float(ncols),
        "nrows": float(nrows),
        "ymax": ymax,
    }
    np.savez_compressed(
        CACHE_PATH,
        elevation=mosaic,
        xllcorner=np.float64(xll),
        yllcorner=np.float64(yll),
        cellsize=np.float64(cellsize),
        ncols=np.float64(ncols),
        nrows=np.float64(nrows),
    )
    print(f"Mosaic {ncols}×{nrows} built in {time.perf_counter() - t0:.1f}s → {CACHE_PATH.name}")
    return mosaic, meta


def downsample(elevation: np.ndarray, factor: int) -> np.ndarray:
    if factor <= 1:
        return elevation
    rows = (elevation.shape[0] // factor) * factor
    cols = (elevation.shape[1] // factor) * factor
    trimmed = elevation[:rows, :cols]
    reshaped = trimmed.reshape(rows // factor, factor, cols // factor, factor)
    # nanmean over each block so nodata edges do not dominate
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        with np.errstate(all="ignore"):
            block_mean = np.nanmean(reshaped, axis=(1, 3))
    return np.asarray(block_mean, dtype=np.float32)



def altitude_cmap():
    """Green (low) → yellow/brown → white (high). Blue channel stays low throughout."""
    from matplotlib.colors import LinearSegmentedColormap

    # Explicit RGB triples keep B ≤ G so nothing reads as blue.
    return LinearSegmentedColormap.from_list(
        "altitude_green_white",
        [
            (0.00, (0.16, 0.45, 0.14)),  # low valleys — green
            (0.22, (0.40, 0.62, 0.22)),  # mid green
            (0.42, (0.72, 0.72, 0.28)),  # yellow-green foothills
            (0.62, (0.72, 0.52, 0.28)),  # warm brown slopes
            (0.80, (0.88, 0.82, 0.70)),  # warm pale rock
            (1.00, (1.00, 1.00, 1.00)),  # high peaks — white
        ],
    )


OVERLAY_DIR = Path(__file__).resolve().parent / "overlays"
WATER_FACE = "#3a7fc1"
WATER_EDGE = "#2a5f94"
RIVER_COLOR = "#4a90c8"
CITY_COLOR = "#1a1a1a"


def load_overlays(overlay_dir: Path) -> tuple:
    """Load lakes, rivers, and top-100 city markers (EPSG:31287)."""
    import geopandas as gpd

    lakes_path = overlay_dir / "lakes.gpkg"
    rivers_path = overlay_dir / "rivers.gpkg"
    cities_path = overlay_dir / "cities_top100.gpkg"
    missing = [p.name for p in (lakes_path, rivers_path, cities_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            f"Missing overlay files: {', '.join(missing)}. "
            "Run: python prepare_overlays.py"
        )
    lakes = gpd.read_file(lakes_path)
    rivers = gpd.read_file(rivers_path)
    cities = gpd.read_file(cities_path)
    return lakes, rivers, cities


def draw_overlays(ax, lakes, rivers, cities, label_top: int = 25) -> dict[str, list]:
    """Plot water + cities; return artist lists keyed for layer toggles."""
    artists: dict[str, list] = {"Lakes": [], "Rivers": [], "Cities": []}

    if len(rivers):
        major = rivers["length_m"] >= 8000
        if (~major).any():
            n0 = len(ax.collections)
            rivers.loc[~major].plot(ax=ax, color=RIVER_COLOR, linewidth=0.35, alpha=0.5, zorder=3)
            artists["Rivers"].extend(ax.collections[n0:])
        if major.any():
            n0 = len(ax.collections)
            rivers.loc[major].plot(ax=ax, color=RIVER_COLOR, linewidth=0.9, alpha=0.5, zorder=4)
            artists["Rivers"].extend(ax.collections[n0:])

    if len(lakes):
        n0 = len(ax.collections)
        lakes.plot(
            ax=ax,
            facecolor=WATER_FACE,
            edgecolor=WATER_EDGE,
            linewidth=0.4,
            alpha=0.5,
            zorder=5,
        )
        artists["Lakes"].extend(ax.collections[n0:])

    if not len(cities):
        return artists

    sizes = 18 + 70 * (cities["population"] / cities["population"].max()) ** 0.5
    scatter = ax.scatter(
        cities.geometry.x,
        cities.geometry.y,
        s=sizes,
        c=CITY_COLOR,
        marker="o",
        linewidths=0.6,
        edgecolors="white",
        zorder=6,
        label="Cities (top 100)",
    )
    artists["Cities"].append(scatter)

    from matplotlib import patheffects as pe

    label_fx = [pe.withStroke(linewidth=2.2, foreground="white")]
    for _, row in cities.nsmallest(label_top, "rank").iterrows():
        ann = ax.annotate(
            row["name"],
            xy=(row.geometry.x, row.geometry.y),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=7 if row["rank"] > 10 else 8.5,
            fontweight="bold" if row["rank"] <= 10 else "normal",
            color="#111111",
            zorder=7,
            path_effects=label_fx,
        )
        artists["Cities"].append(ann)

    return artists


def visualize(
    elevation: np.ndarray,
    meta: dict[str, float],
    downsample_factor: int,
    overlay_dir: Path | None = None,
    show_overlays: bool = True,
) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource, Normalize
    from matplotlib.widgets import CheckButtons

    display = downsample(elevation, downsample_factor)
    cell = meta["cellsize"] * downsample_factor
    xll = meta["xllcorner"]
    yll = meta["yllcorner"]
    xmax = xll + (display.shape[1] - 1) * cell
    ymax = yll + (elevation.shape[0] - 1) * meta["cellsize"]
    # After row-downsample, geographic ymax still matches full mosaic top.
    ymin = ymax - (display.shape[0] - 1) * cell

    valid = display[np.isfinite(display)]
    if valid.size == 0:
        raise RuntimeError("No valid elevation values to plot.")

    vmin = float(np.nanpercentile(valid, 1))
    vmax = float(np.nanpercentile(valid, 99.5))
    cmap = altitude_cmap()
    norm = Normalize(vmin=vmin, vmax=vmax)

    # Color from the ramp only, then darken with hillshade (no cool/blue blend).
    filled = np.nan_to_num(display, nan=vmin)
    rgb = cmap(norm(filled))[:, :, :3]
    intensity = LightSource(azdeg=315, altdeg=45).hillshade(
        filled, vert_exag=1.5, dx=cell, dy=cell
    )
    rgb = rgb * (0.35 + 0.65 * intensity[..., None])

    mask = ~np.isfinite(display)
    rgb = rgb.copy()
    rgb[mask] = 0.92  # light gray background outside Austria

    fig, ax = plt.subplots(figsize=(15, 8))
    # Leave room on the right for colorbar + layer checklist
    fig.subplots_adjust(left=0.07, right=0.72, top=0.94, bottom=0.08)

    elev_im = ax.imshow(
        rgb, extent=(xll, xmax, ymin, ymax), origin="upper", interpolation="nearest", zorder=1
    )
    cax = fig.add_axes([0.735, 0.15, 0.015, 0.7])
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, cax=cax)
    cbar.set_label("Elevation (m)")

    layer_artists: dict[str, list] = {
        "Elevation": [elev_im, cax],
        "Lakes": [],
        "Rivers": [],
        "Cities": [],
    }

    if show_overlays:
        overlay_dir = overlay_dir or OVERLAY_DIR
        lakes, rivers, cities = load_overlays(overlay_dir)
        drawn = draw_overlays(ax, lakes, rivers, cities)
        layer_artists["Lakes"] = drawn["Lakes"]
        layer_artists["Rivers"] = drawn["Rivers"]
        layer_artists["Cities"] = drawn["Cities"]

    ax.set_title("Austria — elevation, water & largest cities")
    ax.set_xlabel("Easting (m, MGI / Austria Lambert)")
    ax.set_ylabel("Northing (m, MGI / Austria Lambert)")
    ax.set_aspect("equal")
    ax.set_xlim(xll, xmax)
    ax.set_ylim(ymin, ymax)

    # Side checklist to toggle layers
    labels = ["Elevation", "Lakes", "Rivers", "Cities"]
    active = [True, show_overlays, show_overlays, show_overlays]
    rax = fig.add_axes([0.78, 0.55, 0.18, 0.28])
    rax.set_facecolor("#f7f7f7")
    for spine in rax.spines.values():
        spine.set_color("#cccccc")
    rax.set_title("Layers", fontsize=10, pad=8)
    check = CheckButtons(rax, labels, active)

    def on_toggle(label: str) -> None:
        status = check.get_status()
        visible = status[labels.index(label)]
        for artist in layer_artists.get(label, []):
            artist.set_visible(visible)
        fig.canvas.draw_idle()

    check.on_clicked(on_toggle)
    # Keep widget alive (matplotlib can GC it otherwise)
    fig._layer_check = check  # type: ignore[attr-defined]
    fig._layer_artists = layer_artists  # type: ignore[attr-defined]

    # Cursor readout of altitude under the mouse
    def format_coord(x: float, y: float) -> str:
        col = int(round((x - xll) / cell))
        row = int(round((ymax - y) / cell))
        if 0 <= row < display.shape[0] and 0 <= col < display.shape[1]:
            z = display[row, col]
            if np.isfinite(z):
                return f"x={x:.0f}  y={y:.0f}  elev={z:.1f} m"
        return f"x={x:.0f}  y={y:.0f}"

    ax.format_coord = format_coord

    print("Interactive window open — use the side checklist to toggle layers, toolbar to pan/zoom.")
    print(f"Elevation range (display): {vmin:.0f} … {vmax:.0f} m")
    plt.show()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DATA_DIR,
        help="Folder with *_R50.asc tiles (default: DGM_Rasterweite_50m)",
    )
    parser.add_argument(
        "--downsample",
        type=int,
        default=4,
        help="Display every Nth cell for snappier zoom (1 = full 50 m). Default: 4",
    )
    parser.add_argument(
        "--rebuild-cache",
        action="store_true",
        help="Force rebuild of the mosaic cache",
    )
    parser.add_argument(
        "--no-overlays",
        action="store_true",
        help="Show elevation only (skip water and cities)",
    )
    parser.add_argument(
        "--overlay-dir",
        type=Path,
        default=OVERLAY_DIR,
        help="Directory with lakes.gpkg, rivers.gpkg, cities_top100.gpkg",
    )
    args = parser.parse_args()

    if args.downsample < 1:
        parser.error("--downsample must be >= 1")

    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("matplotlib is required. Install with:\n  pip install -r requirements.txt", file=sys.stderr)
        return 1

    global CACHE_PATH
    CACHE_PATH = args.data_dir / "_mosaic_50m.npz"

    elevation, meta = build_mosaic(args.data_dir, force=args.rebuild_cache)
    # ymax needed for display math
    meta["ymax"] = meta["yllcorner"] + (elevation.shape[0] - 1) * meta["cellsize"]
    visualize(
        elevation,
        meta,
        args.downsample,
        overlay_dir=args.overlay_dir,
        show_overlays=not args.no_overlays,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
