#!/usr/bin/env python3
"""Generate comparison charts for AUSTRIA_PHS_THEORETICAL_POTENTIAL.md."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "hydro_data" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

# Palette — cool alpine slate / teal (not purple)
C_BUILT = "#1a5f7a"
C_PIPELINE = "#57c5b6"
C_REALISABLE = "#159895"
C_THEORY = "#002b5b"
C_SEASONAL = "#7a869a"
C_NEED = "#c1121f"
C_ELEC = "#e09f3e"  # amber — annual electricity use
C_BG = "#f7f9fb"
C_GRID = "#dce3ea"
C_TEXT = "#1c2333"

# Statistik Austria / EIA-consistent round figure for 2024:
# Net electricity consumption ≈ 61.6 TWh (use 62 TWh).
AT_ELEC_TWH = 62.0
AT_ELEC_MEAN_GW = AT_ELEC_TWH / 8.76  # ≈ 7.1 GW average load


def style():
    plt.rcParams.update(
        {
            "figure.facecolor": C_BG,
            "axes.facecolor": C_BG,
            "axes.edgecolor": C_GRID,
            "axes.labelcolor": C_TEXT,
            "text.color": C_TEXT,
            "xtick.color": C_TEXT,
            "ytick.color": C_TEXT,
            "grid.color": C_GRID,
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "figure.dpi": 140,
            "savefig.dpi": 160,
            "savefig.bbox": "tight",
            "savefig.facecolor": C_BG,
        }
    )


def save(fig, name: str) -> Path:
    path = OUT / name
    fig.savefig(path)
    plt.close(fig)
    print(f"Wrote {path}")
    return path


def plot_energy_ladder():
    """Built vs theoretical storage vs Austria annual electricity use (TWh)."""
    labels = [
        "Existing\nreversible PHS",
        "Pipeline\nto ~2040\n(+ energy)",
        "JRC T1\ntheoretical\n(20 km)",
        "JRC T2\nrealisable\n(20 km)",
        "JRC T2\ntheoretical\n(20 km)",
        "Seasonal\nSpeicherkraft\nvolume",
        "100% RE\nstorage need\n(TU Graz)",
        "Austria\nelectricity use\n(2024)",
    ]
    values = np.array([0.175, 0.1, 0.443, 1.747, 2.915, 3.5, 20.0, AT_ELEC_TWH])
    colors = [
        C_BUILT,
        C_PIPELINE,
        C_THEORY,
        C_REALISABLE,
        C_THEORY,
        C_SEASONAL,
        C_NEED,
        C_ELEC,
    ]

    fig, ax = plt.subplots(figsize=(12, 5.8))
    x = np.arange(len(labels))
    bars = ax.bar(x, values, color=colors, width=0.72, edgecolor="white", linewidth=0.8)

    for bar, v in zip(bars, values):
        txt = f"{v:.0f}" if v >= 10 else f"{v:.2f}"
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() * 1.02,
            f"{txt} TWh",
            ha="center",
            va="bottom",
            fontsize=8.5,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylabel("Energy [TWh]")
    ax.set_title("Austria PHS storage estimates vs annual electricity use")
    ax.set_ylim(0, max(values) * 1.14)
    ax.yaxis.grid(True, linestyle="--", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    legend = [
        Patch(facecolor=C_BUILT, label="Built / near-term storage"),
        Patch(facecolor=C_THEORY, label="GIS theoretical (JRC)"),
        Patch(facecolor=C_REALISABLE, label="GIS realisable (JRC)"),
        Patch(facecolor=C_SEASONAL, label="Seasonal hydro volume"),
        Patch(facecolor=C_NEED, label="Modelled storage need"),
        Patch(facecolor=C_ELEC, label="Annual electricity use (≈62 TWh, 2024)"),
    ]
    ax.legend(handles=legend, loc="upper left", frameon=False, fontsize=8.5, ncol=2)
    ax.annotate(
        "Electricity use = annual throughput  ·  PHS bars = stored energy capacity  ·  "
        f"≈{AT_ELEC_TWH:.0f} TWh net electricity consumption (2024)",
        xy=(0.5, -0.24),
        xycoords="axes fraction",
        ha="center",
        fontsize=8,
        color="#5c6778",
    )
    fig.tight_layout()
    return save(fig, "phs_energy_built_vs_theory.png")


def plot_energy_zoom():
    """Zoom on storage; annotate that national use is far off-scale."""
    labels = [
        "Existing\nreversible PHS",
        "+ Pipeline\nenergy\n(~2040)",
        "Existing +\npipeline\n(illustrative)",
        "JRC T1\ntheory",
        "JRC T1\nrealisable",
        "JRC T2\nrealisable",
        "JRC T2\ntheory",
    ]
    existing = 0.175
    pipeline = 0.1
    values = np.array([existing, pipeline, existing + pipeline, 0.443, 0.283, 1.747, 2.915])
    colors = [C_BUILT, C_PIPELINE, "#2c7a7b", C_THEORY, "#3d5a80", C_REALISABLE, C_THEORY]

    fig, ax = plt.subplots(figsize=(11, 5.4))
    x = np.arange(len(labels))
    bars = ax.bar(x, values, color=colors, width=0.7, edgecolor="white")

    for bar, v in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.04,
            f"{v:.2f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.axhline(existing, color=C_BUILT, linestyle=":", linewidth=1.2, alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Energy storage [TWh]")
    ax.set_title("Zoom: built fleet vs JRC limits (national use off-scale)")
    ax.set_ylim(0, 3.55)
    ax.yaxis.grid(True, linestyle="--", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    ax.text(
        0.98,
        0.97,
        f"Austria electricity use (2024) ≈ {AT_ELEC_TWH:.0f} TWh/a\n"
        f"(far above this axis)",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        color=C_ELEC,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor=C_ELEC, alpha=0.95),
    )
    mult = 2.915 / existing
    ax.annotate(
        f"JRC T2 theory ≈ {mult:.0f}× existing reversible energy",
        xy=(6, 2.915),
        xytext=(2.8, 3.25),
        fontsize=9,
        arrowprops=dict(arrowstyle="->", color=C_TEXT, lw=1),
        color=C_TEXT,
    )
    fig.tight_layout()
    return save(fig, "phs_energy_zoom_jrc.png")


def plot_power_capacity():
    """Power (GW): built, pipeline, modelled need + mean electricity load."""
    labels = [
        "Existing PHS\n(large plants)",
        "Existing +\nunder construction\n(+0.4 GW)",
        "Existing +\npipeline to ~2040\n(+~5.5 GW)",
        "TU Graz potential\n(pump power, 2012)",
        "100% RE need\n(min scenarios)",
        "100% RE need\n(higher scenarios)",
        "Austria mean\nelectricity load\n(2024)",
    ]
    values = np.array([3.7, 4.1, 9.2, 4.8, 11.7, 21.4, AT_ELEC_MEAN_GW])
    colors = [C_BUILT, C_PIPELINE, "#2c7a7b", C_THEORY, C_NEED, "#9b2226", C_ELEC]

    fig, ax = plt.subplots(figsize=(12, 5.4))
    x = np.arange(len(labels))
    bars = ax.bar(x, values, color=colors, width=0.7, edgecolor="white")
    for bar, v in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.25,
            f"{v:.1f} GW",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.set_ylabel("Power capacity [GW]")
    ax.set_title("Austria PHS power vs modelled need and mean national electricity load")
    ax.set_ylim(0, 25)
    ax.yaxis.grid(True, linestyle="--", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    legend = [
        Patch(facecolor=C_BUILT, label="Built / near-term"),
        Patch(facecolor=C_THEORY, label="Cited hydraulic potential (2012)"),
        Patch(facecolor=C_NEED, label="100% RE model need (TU Graz)"),
        Patch(
            facecolor=C_ELEC,
            label=f"Mean load from {AT_ELEC_TWH:.0f} TWh/a electricity (≈{AT_ELEC_MEAN_GW:.1f} GW)",
        ),
    ]
    ax.legend(handles=legend, loc="upper left", frameon=False, fontsize=9)
    fig.tight_layout()
    return save(fig, "phs_power_built_vs_need.png")


def plot_jrc_distance():
    """JRC Austria T1/T2 energy vs max distance — theoretical vs realisable."""
    distances = np.array([1, 5, 10, 20])
    t1_th = np.array([0, 105, 199, 443]) / 1000  # TWh
    t1_re = np.array([0, 4, 102, 283]) / 1000
    t2_th = np.array([1, 335, 1143, 2915]) / 1000
    t2_re = np.array([1, 120, 439, 1747]) / 1000
    existing = 0.175

    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    ax.plot(distances, t2_th, "o-", color=C_THEORY, lw=2.2, ms=7, label="T2 theoretical")
    ax.plot(distances, t2_re, "s--", color=C_REALISABLE, lw=2, ms=7, label="T2 realisable")
    ax.plot(distances, t1_th, "^-", color="#3d5a80", lw=1.8, ms=7, label="T1 theoretical")
    ax.plot(distances, t1_re, "v--", color="#89a7c2", lw=1.8, ms=7, label="T1 realisable")
    ax.axhline(existing, color=C_BUILT, linestyle=":", lw=1.8, label="Existing reversible PHS")

    ax.fill_between(distances, t2_re, t2_th, color=C_THEORY, alpha=0.08)
    ax.set_xlabel("Maximum distance between reservoirs [km]")
    ax.set_ylabel("Energy storage [TWh]")
    ax.set_title("JRC Austria GIS potential vs distance (built fleet as reference)")
    ax.set_xticks(distances)
    ax.set_ylim(0, 3.35)
    ax.yaxis.grid(True, linestyle="--", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    ax.annotate(
        "T2 @ 20 km ≈ 2.9 TWh theory / 1.7 TWh realisable",
        xy=(20, 2.915),
        xytext=(8, 2.7),
        fontsize=8.5,
        arrowprops=dict(arrowstyle="->", color=C_TEXT, lw=0.9),
    )
    ax.text(
        0.98,
        0.02,
        f"For scale: Austria uses ≈{AT_ELEC_TWH:.0f} TWh electricity per year (2024)",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color="#5c6778",
    )
    fig.tight_layout()
    return save(fig, "phs_jrc_distance_curves.png")


def plot_multiplier():
    """Horizontal bars: how many × existing reversible energy."""
    existing = 0.175
    items = [
        ("Existing reversible PHS", existing, C_BUILT),
        ("+ Pipeline energy (~2040)", existing + 0.1, C_PIPELINE),
        ("JRC T1 theoretical (20 km)", 0.443, C_THEORY),
        ("JRC T2 realisable (20 km)", 1.747, C_REALISABLE),
        ("JRC T2 theoretical (20 km)", 2.915, C_THEORY),
        ("Seasonal Speicherkraft volume", 3.5, C_SEASONAL),
        ("100% RE storage need (mid)", 20.0, C_NEED),
        ("Austria electricity use (2024)", AT_ELEC_TWH, C_ELEC),
    ]
    labels = [i[0] for i in items]
    values = np.array([i[1] for i in items])
    colors = [i[2] for i in items]
    mult = values / existing

    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    y = np.arange(len(labels))
    bars = ax.barh(y, mult, color=colors, height=0.65, edgecolor="white")
    ax.set_yticks(y)
    ax.set_yticklabels(labels)
    ax.set_xlabel("Multiple of today’s reversible PHS energy (≈ 0.175 TWh)")
    ax.set_title("Estimates and electricity use relative to built PHS energy")
    ax.axvline(1, color=C_BUILT, lw=1.4)
    ax.xaxis.grid(True, linestyle="--", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    for bar, m, v in zip(bars, mult, values):
        if m < 50:
            txt = f"{m:.0f}×  ({v:.2f} TWh)"
        else:
            txt = f"{m:.0f}×  (~{v:.0f} TWh)"
        ax.text(
            bar.get_width() + max(mult) * 0.012,
            bar.get_y() + bar.get_height() / 2,
            txt,
            va="center",
            fontsize=9,
        )
    ax.set_xlim(0, max(mult) * 1.28)
    ax.invert_yaxis()
    fig.tight_layout()
    return save(fig, "phs_multiples_of_built.png")


def main():
    style()
    plot_energy_ladder()
    plot_energy_zoom()
    plot_power_capacity()
    plot_jrc_distance()
    plot_multiplier()
    print(f"Figures in {OUT}")


if __name__ == "__main__":
    main()
