#!/usr/bin/env python3
"""Charts for EUROPE_PHS_ANNUAL_POTENTIAL.md — annual electrical TWh only."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "hydro_data" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

C_BUILT = "#1a5f7a"
C_ILLUST = "#002b5b"
C_REAL = "#159895"
C_ELEC = "#e09f3e"
C_SCENARIO = "#c1121f"
C_BG = "#f7f9fb"
C_GRID = "#dce3ea"
C_TEXT = "#1c2333"

# --- Annual electrical energy (TWh/a) ---
# PHS generation (EU27): JRC CETO average ~31.3; vgbe 2022 = 31 TWh
PHS_GEN_EU = 31.0
# Broader Europe (EU27+CH+IS+NO+TR+UK): vgbe 2022
PHS_GEN_EUROPE_PLUS = 36.0
# Final electricity consumption by sector, EU27 2023 (Eurostat): 815+691+703+70+46
ELEC_CONS_EU = 2325.0
# Gross electricity production EU27 2023 (Eurostat)
ELEC_PROD_EU = 2749.0

# Storage capacity (TWh stock) used only to convert → illustrative annual TWh/a
# Usable EU PSH storage ~0.5–0.8 TWh (Quaranta); use 0.7 → cycles ≈ 31/0.7 ≈ 44
USABLE_STORAGE_EU = 0.7
CYCLES = PHS_GEN_EU / USABLE_STORAGE_EU  # ≈ 44.3

# JRC 2013 storage potential (TWh stock) @ 20 km
JRC_T2_REAL_EU = 33.0  # EU T2 realisable
JRC_T2_TH_EU = 59.0  # ~59.4 from table EU T2 theoretical 20 km
JRC_T2_REAL_EUR = 80.0  # Europe T2 realisable
JRC_T2_TH_EUR = 123.0  # Europe T2 theoretical
ESTORAGE_FEASIBLE = 2.291  # TWh stock, EU-15+NO+CH existing-reservoir pairs

# Illustrative annual = storage × today's cycle intensity
def annual_from_storage(s_twh: float) -> float:
    return s_twh * CYCLES


# POTEnCIA scenario (JRC CETO): +67 TWh PSH use by 2050 vs 2025
POTENCIA_EXTRA_2050 = 67.0


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


def plot_phs_vs_consumption():
    """Annual PHS generation vs EU electricity consumption / production."""
    labels = [
        "PHS generation\nEU27\n(~31 TWh/a)",
        "PHS generation\nEurope+\n(~36 TWh/a)",
        "EU27 electricity\nconsumption\n(2023)",
        "EU27 gross\nelectricity\nproduction (2023)",
    ]
    values = np.array([PHS_GEN_EU, PHS_GEN_EUROPE_PLUS, ELEC_CONS_EU, ELEC_PROD_EU])
    colors = [C_BUILT, "#2c7a7b", C_ELEC, "#f4a261"]

    fig, ax = plt.subplots(figsize=(10.5, 5.6))
    x = np.arange(len(labels))
    bars = ax.bar(x, values, color=colors, width=0.7, edgecolor="white")
    for bar, v in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() * 1.02,
            f"{v:.0f} TWh/a",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Annual electrical energy [TWh/a]")
    ax.set_title("Europe — annual PHS generation vs electricity use / production")
    ax.set_ylim(0, max(values) * 1.14)
    ax.yaxis.grid(True, linestyle="--", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    share = 100 * PHS_GEN_EU / ELEC_CONS_EU
    ax.annotate(
        f"PHS ≈ {share:.1f}% of EU27 electricity consumption  ·  all bars are annual TWh/a",
        xy=(0.5, -0.20),
        xycoords="axes fraction",
        ha="center",
        fontsize=8.5,
        color="#5c6778",
    )
    fig.tight_layout()
    return save(fig, "europe_phs_vs_consumption.png")


def plot_annual_potential_illustrative():
    """Current annual PHS vs illustrative annual from storage×cycles."""
    labels = [
        "PHS gen\ntoday\n(EU27)",
        "eStorage\nfeasible\n(illustrative a)",
        "JRC T2\nrealisable EU\n(illustrative a)",
        "JRC T2\ntheory EU\n(illustrative a)",
        "JRC T2\nrealisable Europe\n(illustrative a)",
        "POTEnCIA\n+67 TWh/a\nby 2050",
        "EU27 electricity\nconsumption\n(2023)",
    ]
    values = np.array(
        [
            PHS_GEN_EU,
            annual_from_storage(ESTORAGE_FEASIBLE),
            annual_from_storage(JRC_T2_REAL_EU),
            annual_from_storage(JRC_T2_TH_EU),
            annual_from_storage(JRC_T2_REAL_EUR),
            POTENCIA_EXTRA_2050,
            ELEC_CONS_EU,
        ]
    )
    colors = [C_BUILT, C_REAL, C_ILLUST, "#3d5a80", "#001d3d", C_SCENARIO, C_ELEC]

    fig, ax = plt.subplots(figsize=(12.5, 5.8))
    x = np.arange(len(labels))
    bars = ax.bar(x, values, color=colors, width=0.72, edgecolor="white")
    for bar, v in zip(bars, values):
        txt = f"{v:.0f}" if v >= 10 else f"{v:.1f}"
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() * 1.015,
            f"{txt}",
            ha="center",
            va="bottom",
            fontsize=8.5,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("Annual electrical energy [TWh/a]")
    ax.set_title(
        f"Illustrative annual PHS throughput if new storage cycled like today (~{CYCLES:.0f}×/year)"
    )
    ax.set_ylim(0, max(values) * 1.12)
    ax.yaxis.grid(True, linestyle="--", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    legend = [
        Patch(facecolor=C_BUILT, label="Observed annual PHS generation"),
        Patch(facecolor=C_ILLUST, label="Illustrative: GIS storage × today’s cycle rate"),
        Patch(facecolor=C_SCENARIO, label="Model scenario (POTEnCIA, not GIS)"),
        Patch(facecolor=C_ELEC, label="EU27 annual electricity consumption"),
    ]
    ax.legend(handles=legend, loc="upper left", frameon=False, fontsize=8.5, ncol=2)
    ax.annotate(
        f"(a) Illustrative only: annual TWh/a ≈ (JRC/eStorage storage TWh) × {CYCLES:.0f} cycles/a, "
        f"matching today’s EU fleet (~{PHS_GEN_EU:.0f} TWh/a from ~{USABLE_STORAGE_EU:.1f} TWh usable storage). "
        "Not a published annual potential.",
        xy=(0.5, -0.26),
        xycoords="axes fraction",
        ha="center",
        fontsize=7.5,
        color="#5c6778",
    )
    fig.tight_layout()
    return save(fig, "europe_phs_annual_potential_illustrative.png")


def plot_zoom_without_consumption():
    """Zoom: annual PHS today vs illustrative potentials (no consumption bar)."""
    labels = [
        "PHS gen\ntoday\n(EU27)",
        "eStorage\nfeasible\n(illustrative)",
        "JRC T2\nrealisable EU\n(illustrative)",
        "JRC T2\ntheory EU\n(illustrative)",
        "POTEnCIA\n+67 TWh/a\nby 2050",
    ]
    values = np.array(
        [
            PHS_GEN_EU,
            annual_from_storage(ESTORAGE_FEASIBLE),
            annual_from_storage(JRC_T2_REAL_EU),
            annual_from_storage(JRC_T2_TH_EU),
            POTENCIA_EXTRA_2050,
        ]
    )
    colors = [C_BUILT, C_REAL, C_ILLUST, "#3d5a80", C_SCENARIO]

    fig, ax = plt.subplots(figsize=(10.5, 5.4))
    x = np.arange(len(labels))
    bars = ax.bar(x, values, color=colors, width=0.7, edgecolor="white")
    for bar, v in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() * 1.02,
            f"{v:.0f} TWh/a",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel("Annual electrical energy [TWh/a]")
    ax.set_title("Zoom: annual PHS today vs illustrative / scenario potentials")
    ax.set_ylim(0, max(values) * 1.18)
    ax.yaxis.grid(True, linestyle="--", linewidth=0.7)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.text(
        0.98,
        0.97,
        f"EU27 electricity consumption ≈ {ELEC_CONS_EU:.0f} TWh/a\n(off-scale on this chart)",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9,
        color=C_ELEC,
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", edgecolor=C_ELEC, alpha=0.95),
    )
    fig.tight_layout()
    return save(fig, "europe_phs_annual_zoom.png")


def plot_share_pie_style():
    """Simple bar: PHS share of consumption."""
    other = ELEC_CONS_EU - PHS_GEN_EU
    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.barh([0], [PHS_GEN_EU], color=C_BUILT, height=0.45, label="PHS generation")
    ax.barh(
        [0],
        [other],
        left=[PHS_GEN_EU],
        color="#dee2e6",
        height=0.45,
        label="Rest of electricity consumption",
    )
    ax.set_yticks([0])
    ax.set_yticklabels(["EU27 electricity\n(2023)"])
    ax.set_xlabel("Annual electrical energy [TWh/a]")
    ax.set_title(
        f"PHS generation is ≈ {100 * PHS_GEN_EU / ELEC_CONS_EU:.1f}% of EU27 electricity consumption"
    )
    ax.set_xlim(0, ELEC_CONS_EU * 1.02)
    ax.legend(frameon=False, loc="upper right")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.text(
        PHS_GEN_EU / 2,
        0,
        f"{PHS_GEN_EU:.0f}",
        ha="center",
        va="center",
        color="white",
        fontsize=10,
        fontweight="bold",
    )
    ax.text(
        PHS_GEN_EU + other / 2,
        0,
        f"{other:.0f} TWh/a",
        ha="center",
        va="center",
        fontsize=10,
        color=C_TEXT,
    )
    fig.tight_layout()
    return save(fig, "europe_phs_share_of_consumption.png")


def main():
    style()
    print(f"Implied cycles/year from today’s fleet: {CYCLES:.1f}")
    print(f"eStorage illustrative annual: {annual_from_storage(ESTORAGE_FEASIBLE):.0f} TWh/a")
    print(f"JRC T2 real EU illustrative annual: {annual_from_storage(JRC_T2_REAL_EU):.0f} TWh/a")
    plot_phs_vs_consumption()
    plot_annual_potential_illustrative()
    plot_zoom_without_consumption()
    plot_share_pie_style()
    print(f"Figures in {OUT}")


if __name__ == "__main__":
    main()
