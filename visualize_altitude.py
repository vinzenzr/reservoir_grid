#!/usr/bin/env python3
"""Interactive visualization of the BEV 50 m Austria elevation model (DGM)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent / "DGM_Rasterweite_50m"
ALS_1M_DIR = Path(__file__).resolve().parent / "ALS_DTM_1m"
CACHE_PATH = DATA_DIR / "_mosaic_50m.npz"
OVERLAY_DIR = Path(__file__).resolve().parent / "overlays"


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


# Named windows in EPSG:31287 (MGI / Austria Lambert) — matches the 50 m DGM.
# Format: (xmin, ymin, xmax, ymax)
REGIONS_31287: dict[str, tuple[float, float, float, float]] = {
    # Single 50 m tile that contains Innsbruck (2535_R50.asc)
    "innsbruck": (249975.0, 349975.0, 299975.0, 399975.0),
    # Broader Tyrol / North Tyrol alpine window (still light at 50 m)
    "tyrol": (180000.0, 320000.0, 320000.0, 430000.0),
}


def crop_elevation(
    elevation: np.ndarray,
    meta: dict[str, float],
    bbox: tuple[float, float, float, float],
) -> tuple[np.ndarray, dict[str, float]]:
    """Crop a mosaic to bbox (xmin, ymin, xmax, ymax) in the mosaic CRS."""
    xmin, ymin, xmax, ymax = bbox
    cell = meta["cellsize"]
    xll = meta["xllcorner"]
    yll = meta["yllcorner"]
    full_ymax = meta.get("ymax", yll + (elevation.shape[0] - 1) * cell)

    col0 = max(0, int(np.floor((xmin - xll) / cell)))
    col1 = min(elevation.shape[1], int(np.ceil((xmax - xll) / cell)) + 1)
    row0 = max(0, int(np.floor((full_ymax - ymax) / cell)))
    row1 = min(elevation.shape[0], int(np.ceil((full_ymax - ymin) / cell)) + 1)
    if col1 <= col0 or row1 <= row0:
        raise ValueError(f"bbox {bbox} does not intersect the elevation grid")

    cropped = elevation[row0:row1, col0:col1].copy()
    new_meta = {
        **meta,
        "xllcorner": xll + col0 * cell,
        "yllcorner": full_ymax - (row1 - 1) * cell,
        "ymax": full_ymax - row0 * cell,
        "ncols": float(cropped.shape[1]),
        "nrows": float(cropped.shape[0]),
        "cellsize": cell,
    }
    return cropped, new_meta


def clip_overlays(lakes, rivers, cities, bbox: tuple[float, float, float, float], crs: str):
    """Clip overlay layers to bbox in the given CRS."""
    import geopandas as gpd
    from shapely.geometry import box

    frame = gpd.GeoDataFrame(geometry=[box(*bbox)], crs=crs)
    lakes_c = gpd.clip(lakes.to_crs(crs) if lakes.crs != crs else lakes, frame)
    rivers_c = gpd.clip(rivers.to_crs(crs) if rivers.crs != crs else rivers, frame)
    cities_c = cities.to_crs(crs) if cities.crs != crs else cities
    cities_c = cities_c[cities_c.intersects(frame.geometry.iloc[0])].copy()
    return lakes_c, rivers_c, cities_c



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


WATER_FACE = "#3a7fc1"
WATER_EDGE = "#2a5f94"
RIVER_COLOR = "#4a90c8"
CITY_COLOR = "#1a1a1a"


def load_1m_elevation(
    als_dir: Path,
    downsample_factor: int = 25,
) -> tuple[np.ndarray, dict[str, float]]:
    """Load downloaded ALS 1 m GeoTIFF tiles (EPSG:3035), downsampled for display."""
    try:
        import rasterio
        from rasterio.enums import Resampling
    except ImportError as exc:
        raise ImportError("rasterio is required for 1 m ALS tiles. pip install rasterio") from exc

    tifs = sorted(als_dir.glob("ALS_DTM_*.tif"))
    if not tifs:
        raise FileNotFoundError(
            f"No ALS_DTM_*.tif files in {als_dir}. "
            "Download tiles with: python download_als_1m.py --city innsbruck"
        )

    factor = max(1, int(downsample_factor))
    print(f"Loading {len(tifs)} ALS 1 m tile(s), display downsample ×{factor} ...")

    srcs = [rasterio.open(p) for p in tifs]
    try:
        bounds = None
        for src in srcs:
            b = src.bounds
            if bounds is None:
                bounds = [b.left, b.bottom, b.right, b.top]
            else:
                bounds = [
                    min(bounds[0], b.left),
                    min(bounds[1], b.bottom),
                    max(bounds[2], b.right),
                    max(bounds[3], b.top),
                ]
        assert bounds is not None
        cell = float(srcs[0].res[0]) * factor
        width = int(np.ceil((bounds[2] - bounds[0]) / cell))
        height = int(np.ceil((bounds[3] - bounds[1]) / cell))
        mosaic = np.full((height, width), np.nan, dtype=np.float32)

        for src in srcs:
            out_h = max(1, src.height // factor)
            out_w = max(1, src.width // factor)
            data = src.read(
                1,
                out_shape=(out_h, out_w),
                resampling=Resampling.average,
            ).astype(np.float32)
            if src.nodata is not None:
                data[data == src.nodata] = np.nan
            data[(data < -500) | (data > 6000)] = np.nan

            left, top = src.bounds.left, src.bounds.top
            col0 = int(round((left - bounds[0]) / cell))
            row0 = int(round((bounds[3] - top) / cell))
            mosaic[row0 : row0 + out_h, col0 : col0 + out_w] = data

        meta = {
            "xllcorner": float(bounds[0]),
            "yllcorner": float(bounds[1]),
            "cellsize": float(cell),
            "ncols": float(width),
            "nrows": float(height),
            "ymax": float(bounds[3]),
            "crs": "EPSG:3035",
        }
        return mosaic, meta
    finally:
        for src in srcs:
            src.close()


def _elevation_rgb(display: np.ndarray, cell: float):
    from matplotlib.colors import LightSource, Normalize

    valid = display[np.isfinite(display)]
    if valid.size == 0:
        raise RuntimeError("No valid elevation values to plot.")
    vmin = float(np.nanpercentile(valid, 1))
    vmax = float(np.nanpercentile(valid, 99.5))
    cmap = altitude_cmap()
    norm = Normalize(vmin=vmin, vmax=vmax)
    filled = np.nan_to_num(display, nan=vmin)
    rgb = cmap(norm(filled))[:, :, :3]
    intensity = LightSource(azdeg=315, altdeg=45).hillshade(
        filled, vert_exag=1.5, dx=cell, dy=cell
    )
    rgb = rgb * (0.35 + 0.65 * intensity[..., None])
    mask = ~np.isfinite(display)
    rgb = rgb.copy()
    rgb[mask] = 0.92
    return rgb, vmin, vmax, cmap, norm



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
    elevation_50m: np.ndarray,
    meta_50m: dict[str, float],
    downsample_factor: int,
    overlay_dir: Path | None = None,
    show_overlays: bool = True,
    als_dir: Path | None = None,
    initial_resolution: str = "50m",
    downsample_1m: int = 25,
    bbox_31287: tuple[float, float, float, float] | None = None,
    region_name: str | None = None,
) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.widgets import CheckButtons, RadioButtons
    from pyproj import Transformer

    overlay_dir = overlay_dir or OVERLAY_DIR
    als_dir = als_dir or ALS_1M_DIR
    has_1m = bool(list(als_dir.glob("ALS_DTM_*.tif"))) if als_dir.exists() else False

    elev_50 = elevation_50m
    meta_50 = {**meta_50m, "crs": "EPSG:31287"}
    if bbox_31287 is not None:
        elev_50, meta_50 = crop_elevation(elev_50, meta_50, bbox_31287)
        label = region_name or "custom bbox"
        print(
            f"Cropped 50 m to {label}: {elev_50.shape[1]}×{elev_50.shape[0]} cells "
            f"({meta_50['cellsize']:.0f} m)"
        )

    # Preload overlays; clip to region when requested
    lakes_31287 = rivers_31287 = cities_31287 = None
    lakes_3035 = rivers_3035 = cities_3035 = None
    if show_overlays:
        lakes_31287, rivers_31287, cities_31287 = load_overlays(overlay_dir)
        if bbox_31287 is not None:
            lakes_31287, rivers_31287, cities_31287 = clip_overlays(
                lakes_31287, rivers_31287, cities_31287, bbox_31287, "EPSG:31287"
            )
        lakes_3035 = lakes_31287.to_crs("EPSG:3035")
        rivers_3035 = rivers_31287.to_crs("EPSG:3035")
        cities_3035 = cities_31287.to_crs("EPSG:3035")

    datasets: dict[str, tuple[np.ndarray, dict[str, float]]] = {
        "50m": (elev_50, meta_50),
    }
    if has_1m:
        try:
            elev_1m, meta_1m = load_1m_elevation(als_dir, downsample_factor=downsample_1m)
            if bbox_31287 is not None:
                # Convert region bbox 31287 → 3035 and crop 1 m mosaic too
                to_3035 = Transformer.from_crs("EPSG:31287", "EPSG:3035", always_xy=True)
                xs = [bbox_31287[0], bbox_31287[2], bbox_31287[0], bbox_31287[2]]
                ys = [bbox_31287[1], bbox_31287[1], bbox_31287[3], bbox_31287[3]]
                xe, yn = to_3035.transform(xs, ys)
                bbox_3035 = (min(xe), min(yn), max(xe), max(yn))
                try:
                    elev_1m, meta_1m = crop_elevation(elev_1m, meta_1m, bbox_3035)
                except ValueError:
                    print(
                        "Downloaded 1 m tiles do not cover this region — "
                        "50 m only for now. (Tip: python download_als_1m.py --city innsbruck)"
                    )
                    has_1m = False
                    elev_1m = None
            if has_1m and elev_1m is not None:
                datasets["1m"] = (elev_1m, meta_1m)
        except Exception as exc:
            print(f"Could not load 1 m ALS tiles: {exc}")
            has_1m = False

    if initial_resolution == "1m" and "1m" not in datasets:
        print("No 1 m tiles available — starting with 50 m.")
        initial_resolution = "50m"
        has_1m = False
    else:
        has_1m = "1m" in datasets

    state = {"res": initial_resolution}
    title_region = f" — {region_name}" if region_name else ""

    def _prep(res: str):
        elev, meta = datasets[res]
        # 50 m path still applies interactive downsample; 1 m already downsampled on load
        if res == "50m":
            display = downsample(elev, downsample_factor)
            cell = meta["cellsize"] * downsample_factor
            ymax = meta["yllcorner"] + (elev.shape[0] - 1) * meta["cellsize"]
        else:
            display = elev
            cell = meta["cellsize"]
            ymax = meta["ymax"]
        xll = meta["xllcorner"]
        xmax = xll + (display.shape[1] - 1) * cell
        ymin = ymax - (display.shape[0] - 1) * cell
        rgb, vmin, vmax, cmap, norm = _elevation_rgb(display, cell)
        return display, meta, rgb, vmin, vmax, cmap, norm, xll, xmax, ymin, ymax, cell

    display, meta, rgb, vmin, vmax, cmap, norm, xll, xmax, ymin, ymax, cell = _prep(state["res"])

    fig, ax = plt.subplots(figsize=(15, 8))
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

    def _clear_overlay_artists() -> None:
        for key in ("Lakes", "Rivers", "Cities"):
            for artist in layer_artists[key]:
                artist.remove()
            layer_artists[key] = []

    def _draw_current_overlays() -> None:
        if not show_overlays:
            return
        _clear_overlay_artists()
        if state["res"] == "1m":
            lakes, rivers, cities = lakes_3035, rivers_3035, cities_3035
        else:
            lakes, rivers, cities = lakes_31287, rivers_31287, cities_31287
        drawn = draw_overlays(ax, lakes, rivers, cities)
        layer_artists["Lakes"] = drawn["Lakes"]
        layer_artists["Rivers"] = drawn["Rivers"]
        layer_artists["Cities"] = drawn["Cities"]
        # Respect current checklist visibility
        status = check.get_status()
        for i, label in enumerate(["Elevation", "Lakes", "Rivers", "Cities"]):
            vis = status[i]
            for artist in layer_artists.get(label, []):
                artist.set_visible(vis)

    crs_label = "ETRS89 / LAEA Europe" if state["res"] == "1m" else "MGI / Austria Lambert"
    ax.set_title(f"Austria{title_region} — elevation ({state['res']}), water & cities")
    ax.set_xlabel(f"Easting (m, {crs_label})")
    ax.set_ylabel(f"Northing (m, {crs_label})")
    ax.set_aspect("equal")
    ax.set_xlim(xll, xmax)
    ax.set_ylim(ymin, ymax)

    # Side checklist to toggle layers
    labels = ["Elevation", "Lakes", "Rivers", "Cities"]
    active = [True, show_overlays, show_overlays, show_overlays]
    rax = fig.add_axes([0.78, 0.58, 0.18, 0.28])
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

    # Resolution selector
    rrax = fig.add_axes([0.78, 0.32, 0.18, 0.18])
    rrax.set_facecolor("#f7f7f7")
    for spine in rrax.spines.values():
        spine.set_color("#cccccc")
    rrax.set_title("Elevation data", fontsize=10, pad=8)
    radio_labels = ["50 m DGM"]
    if has_1m:
        radio_labels.append("1 m ALS")
    else:
        rrax.text(
            0.05,
            0.15,
            "1 m: download tiles\nwith download_als_1m.py",
            transform=rrax.transAxes,
            fontsize=7,
            color="#666666",
            va="bottom",
        )
    radio = RadioButtons(rrax, radio_labels, active=0 if state["res"] == "50m" else 1)

    view = {
        "display": display,
        "xll": xll,
        "ymax": ymax,
        "cell": cell,
    }

    def on_resolution(label: str) -> None:
        res = "1m" if "1 m" in label else "50m"
        if res == state["res"]:
            return
        if res == "1m" and not has_1m:
            return
        state["res"] = res
        display_n, meta_n, rgb_n, vmin_n, vmax_n, cmap_n, norm_n, xll_n, xmax_n, ymin_n, ymax_n, cell_n = _prep(res)
        elev_im.set_data(rgb_n)
        elev_im.set_extent((xll_n, xmax_n, ymin_n, ymax_n))
        sm.set_cmap(cmap_n)
        sm.set_norm(norm_n)
        cbar.update_normal(sm)
        ax.set_xlim(xll_n, xmax_n)
        ax.set_ylim(ymin_n, ymax_n)
        crs_l = "ETRS89 / LAEA Europe" if res == "1m" else "MGI / Austria Lambert"
        ax.set_title(f"Austria{title_region} — elevation ({res}), water & cities")
        ax.set_xlabel(f"Easting (m, {crs_l})")
        ax.set_ylabel(f"Northing (m, {crs_l})")
        view.update(display=display_n, xll=xll_n, ymax=ymax_n, cell=cell_n)
        _draw_current_overlays()
        fig.canvas.draw_idle()
        print(f"Switched to {res}  elev {vmin_n:.0f}…{vmax_n:.0f} m")

    radio.on_clicked(on_resolution)
    fig._layer_check = check  # type: ignore[attr-defined]
    fig._layer_radio = radio  # type: ignore[attr-defined]
    fig._layer_artists = layer_artists  # type: ignore[attr-defined]

    _draw_current_overlays()

    def format_coord(x: float, y: float) -> str:
        col = int(round((x - view["xll"]) / view["cell"]))
        row = int(round((view["ymax"] - y) / view["cell"]))
        disp = view["display"]
        if 0 <= row < disp.shape[0] and 0 <= col < disp.shape[1]:
            z = disp[row, col]
            if np.isfinite(z):
                return f"x={x:.0f}  y={y:.0f}  elev={z:.1f} m"
        return f"x={x:.0f}  y={y:.0f}"

    ax.format_coord = format_coord

    print("Interactive window open — toggle Layers / Elevation data on the right; toolbar to pan/zoom.")
    if not has_1m:
        print("Tip: download a 1 m tile first, e.g.  python download_als_1m.py --city innsbruck")
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
        "--als-dir",
        type=Path,
        default=ALS_1M_DIR,
        help="Folder with downloaded ALS_DTM_*.tif 1 m tiles",
    )
    parser.add_argument(
        "--resolution",
        choices=("50m", "1m"),
        default="50m",
        help="Initial elevation product",
    )
    parser.add_argument(
        "--downsample",
        type=int,
        default=4,
        help="Display every Nth cell for 50 m (1 = full). Default: 4",
    )
    parser.add_argument(
        "--downsample-1m",
        type=int,
        default=25,
        help="Display downsample for 1 m ALS tiles (native is huge). Default: 25",
    )
    parser.add_argument(
        "--region",
        choices=sorted(REGIONS_31287),
        help="Crop to a named alpine window (EPSG:31287). Recommended with --downsample 1.",
    )
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        metavar=("XMIN", "YMIN", "XMAX", "YMAX"),
        help="Crop to custom bbox in EPSG:31287 (MGI Austria Lambert metres)",
    )
    parser.add_argument(
        "--rebuild-cache",
        action="store_true",
        help="Force rebuild of the 50 m mosaic cache",
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

    if args.downsample < 1 or args.downsample_1m < 1:
        parser.error("downsample factors must be >= 1")
    if args.region and args.bbox:
        parser.error("use either --region or --bbox, not both")

    try:
        import matplotlib  # noqa: F401
    except ImportError:
        print("matplotlib is required. Install with:\n  pip install -r requirements.txt", file=sys.stderr)
        return 1

    global CACHE_PATH
    CACHE_PATH = args.data_dir / "_mosaic_50m.npz"

    elevation, meta = build_mosaic(args.data_dir, force=args.rebuild_cache)
    meta["ymax"] = meta["yllcorner"] + (elevation.shape[0] - 1) * meta["cellsize"]

    bbox = None
    region_name = None
    if args.region:
        bbox = REGIONS_31287[args.region]
        region_name = args.region
    elif args.bbox:
        bbox = tuple(args.bbox)  # type: ignore[assignment]
        region_name = "bbox"

    visualize(
        elevation,
        meta,
        args.downsample,
        overlay_dir=args.overlay_dir,
        show_overlays=not args.no_overlays,
        als_dir=args.als_dir,
        initial_resolution=args.resolution,
        downsample_1m=args.downsample_1m,
        bbox_31287=bbox,
        region_name=region_name,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
