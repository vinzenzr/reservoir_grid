#!/usr/bin/env python3
"""Example reservoir map: Schlegeisspeicher (Zemm–Ziller / Roßhag).

Shows:
  - surrounding BEV DGM 50 m elevation + hillshade
  - Tirol WIS reservoir outline
  - geometric bathymetry estimate calibrated to published volume (126.5 hm³)
    (ALS DEM only sees the water surface — true bathymetry is rarely public)

Run:
  .venv/bin/python map_reservoir_example.py              # interactive window + PNG
  .venv/bin/python map_reservoir_example.py --no-show    # PNG only
"""

from __future__ import annotations

import argparse
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colors
from matplotlib.colors import LightSource
from rasterio.features import geometry_mask
from scipy import ndimage
from shapely.geometry import mapping

ROOT = Path(__file__).resolve().parent
DEM_CACHE = ROOT / "DGM_Rasterweite_50m" / "_mosaic_50m.npz"
WIS_PATH = ROOT / "hydro_data" / "tirol_seen" / "WIS_GEW_PL_1.shp"
OUT_DIR = ROOT / "hydro_data"
DEM_CRS = "EPSG:31287"

RESERVOIR_NAME = "Schlegeisspeicher"
WIS_MATCH = "Schlegeis"
VOLUME_M3 = 126.5e6
FULL_SUPPLY_LEVEL_M = 1782.0
DAM_HEIGHT_M = 131.0
GLOBATHY_HYLAK_ID = 169131
GLOBATHY_DMAX_M = 28.81
PAD_M = 2500.0


def load_dem_window(bounds_31287: tuple[float, float, float, float]):
    """Return (elev, transform-like dict, window slice) from cached 50 m mosaic."""
    z = np.load(DEM_CACHE)
    elev_full = z["elevation"]
    xll = float(z["xllcorner"])
    yll = float(z["yllcorner"])
    cell = float(z["cellsize"])
    nrows = int(z["nrows"])
    ymax = yll + (nrows - 1) * cell

    xmin, ymin, xmax, ymax_b = bounds_31287
    col0 = max(0, int((xmin - xll) / cell))
    col1 = min(int(z["ncols"]), int((xmax - xll) / cell) + 1)
    row0 = max(0, int((ymax - ymax_b) / cell))
    row1 = min(nrows, int((ymax - ymin) / cell) + 1)

    elev = elev_full[row0:row1, col0:col1].astype(np.float32)
    win_xmin = xll + col0 * cell
    win_ymax = ymax - row0 * cell
    meta = {
        "xll": win_xmin,
        "ymax": win_ymax,
        "cell": cell,
        "nrows": elev.shape[0],
        "ncols": elev.shape[1],
    }
    return elev, meta


def affine_params(meta: dict):
    """Return rasterio-like Affine coefficients a, b, c, d, e, f."""
    a = meta["cell"]
    e = -meta["cell"]
    c = meta["xll"]
    f = meta["ymax"]
    return a, 0.0, c, 0.0, e, f


def geometric_bathymetry(meta: dict, geom_mask: np.ndarray, volume_m3: float, dmax_cap: float):
    dist = ndimage.distance_transform_edt(geom_mask)
    if dist.max() <= 0:
        raise SystemExit("Empty reservoir mask")
    rel = dist / dist.max()
    pix_area = meta["cell"] ** 2
    k = volume_m3 / (rel[geom_mask].sum() * pix_area)
    depth = np.zeros(geom_mask.shape, dtype=np.float32)
    depth[geom_mask] = (k * rel[geom_mask]).astype(np.float32)
    dmax = float(depth.max())
    if dmax > dmax_cap:
        depth *= dmax_cap / dmax
        dmax = dmax_cap
    return depth, dmax


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--save",
        type=Path,
        default=OUT_DIR / "schlegeis_example_map.png",
        help="PNG output path (default: hydro_data/schlegeis_example_map.png)",
    )
    ap.add_argument(
        "--no-show",
        action="store_true",
        help="Save PNG only; do not open an interactive window",
    )
    args = ap.parse_args()

    g = gpd.read_file(WIS_PATH)
    hits = g[g["GEW_NAME"].astype(str).str.contains(WIS_MATCH, case=False, na=False)]
    if hits.empty:
        raise SystemExit(f"No WIS lake matching {WIS_MATCH!r}")
    res = hits.sort_values("SHAPE_AREA", ascending=False).iloc[[0]].to_crs(DEM_CRS)
    print("GEW_NAME:", res.iloc[0]["GEW_NAME"])
    print("Area km²:", float(res.iloc[0].geometry.area) / 1e6)

    minx, miny, maxx, maxy = res.total_bounds
    elev, meta = load_dem_window((minx - PAD_M, miny - PAD_M, maxx + PAD_M, maxy + PAD_M))
    a, b, c, d, e, f = affine_params(meta)

    class T:
        pass

    transform = T()
    transform.a, transform.b, transform.c = a, b, c
    transform.d, transform.e, transform.f = d, e, f

    from affine import Affine

    aff = Affine(a, b, c, d, e, f)
    inside = ~geometry_mask(
        [mapping(res.iloc[0].geometry)],
        out_shape=elev.shape,
        transform=aff,
        invert=False,
    )
    # Cap near dam height (water column cannot exceed the structure)
    depth, dmax = geometric_bathymetry(meta, inside, VOLUME_M3, DAM_HEIGHT_M)

    water_surface = FULL_SUPPLY_LEVEL_M
    elev_hs = elev.copy()
    elev_hs[inside] = water_surface
    ls = LightSource(azdeg=315, altdeg=45)
    fill = float(np.nanmedian(elev))
    hs = ls.hillshade(np.nan_to_num(elev_hs, nan=fill), vert_exag=2.0)

    left = meta["xll"]
    top = meta["ymax"]
    right = left + meta["ncols"] * meta["cell"]
    bottom = top - meta["nrows"] * meta["cell"]
    extent = (left, right, bottom, top)

    fig, axes = plt.subplots(1, 2, figsize=(14, 7), constrained_layout=True)

    ax = axes[0]
    vmin, vmax = np.nanpercentile(elev, [2, 98])
    dem_cmap = colors.LinearSegmentedColormap.from_list(
        "elev_gw", ["#2d6a4f", "#95d5b2", "#f8f9fa", "#ffffff"]
    )
    rgb = ls.shade(
        np.nan_to_num(elev, nan=vmin),
        cmap=dem_cmap,
        blend_mode="overlay",
        vert_exag=2.0,
        vmin=vmin,
        vmax=vmax,
    )
    ax.imshow(rgb, extent=extent, origin="upper")
    res.boundary.plot(ax=ax, color="#0077b6", linewidth=1.8)
    elev_norm = colors.Normalize(vmin=vmin, vmax=vmax)
    elev_sm = plt.cm.ScalarMappable(norm=elev_norm, cmap=dem_cmap)
    elev_sm.set_array([])
    cb_elev = fig.colorbar(elev_sm, ax=ax, fraction=0.046, pad=0.04)
    cb_elev.set_label("Elevation [m a.s.l.]")
    ax.set_title(f"{RESERVOIR_NAME} — terrain (BEV DGM 50 m)")
    ax.set_xlabel("EPSG:31287 Easting [m]")
    ax.set_ylabel("Northing [m]")
    ax.set_aspect("equal")

    ax = axes[1]
    ax.imshow(hs, extent=extent, origin="upper", cmap="gray", alpha=0.55)
    depth_plot = np.ma.masked_where(~inside, depth)
    im = ax.imshow(depth_plot, extent=extent, origin="upper", cmap="Blues", vmin=0, vmax=dmax, alpha=0.9)
    res.boundary.plot(ax=ax, color="#023e8a", linewidth=1.5)
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("Estimated depth [m]")
    ax.set_title("Geometric bathymetry (volume-calibrated)")
    ax.set_xlabel("EPSG:31287 Easting [m]")
    ax.set_aspect("equal")

    vol_check = float(depth[inside].sum() * meta["cell"] ** 2)
    fig.suptitle(
        f"{RESERVOIR_NAME}  |  published V={VOLUME_M3/1e6:.1f} hm³, "
        f"FSL={FULL_SUPPLY_LEVEL_M:.0f} m, dam={DAM_HEIGHT_M:.0f} m\n"
        f"map V≈{vol_check/1e6:.1f} hm³, Dmax≈{dmax:.0f} m  |  "
        f"GLOBathy Hylak {GLOBATHY_HYLAK_ID} Dmax_use≈{GLOBATHY_DMAX_M:.0f} m (modelled)\n"
        "Depth is NOT surveyed bathymetry — ALS DEM is water surface only.",
        fontsize=11,
    )

    args.save.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.save, dpi=160)
    print(f"Saved {args.save}")

    # Save depth as NPZ (no GeoTIFF dependency on full DEM)
    npz_path = OUT_DIR / "schlegeis_depth_estimate.npz"
    np.savez_compressed(
        npz_path,
        depth=depth,
        inside=inside,
        elev=elev,
        xll=meta["xll"],
        ymax=meta["ymax"],
        cell=meta["cell"],
        dmax=dmax,
        volume_m3=vol_check,
    )
    print(f"Saved {npz_path}")

    meta_path = OUT_DIR / "schlegeis_example_meta.txt"
    meta_path.write_text(
        f"""reservoir: {RESERVOIR_NAME}
wis_id: {res.iloc[0]['GEW_ID']}
wis_name: {res.iloc[0]['GEW_NAME']}
published_volume_hm3: {VOLUME_M3/1e6}
full_supply_level_m: {FULL_SUPPLY_LEVEL_M}
dam_height_m: {DAM_HEIGHT_M}
map_volume_hm3: {vol_check/1e6:.3f}
map_dmax_m: {dmax:.2f}
globathy_hylak_id: {GLOBATHY_HYLAK_ID}
globathy_dmax_use_m: {GLOBATHY_DMAX_M}
linked_plant: Roßhag (pumped storage, 231 MW) → lower basin Stillupp
note: geometric depth from distance-to-shore, scaled to published volume; not a survey
""",
        encoding="utf-8",
    )
    print(f"Saved {meta_path}")

    if args.no_show:
        plt.close(fig)
    else:
        print("Close the plot window to exit.")
        plt.show()


if __name__ == "__main__":
    main()
