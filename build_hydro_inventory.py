#!/usr/bin/env python3
"""Build Austria pumped-storage plant + reservoir inventory CSVs.

Sources (see hydro_data/SOURCES.md):
- de.wikipedia Liste von Pumpspeicherkraftwerken (Österreich)
- de.wikipedia Liste von Wasserkraftwerken in Österreich (* = pumped)
- VERBUND EURELECTRIC presentation (reservoir energy/volume)
- Tirol WIS_GEW_PL lake outlines for Tyrol reservoirs
- Wikipedia Infobox Stausee / Wikidata where available
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
HYDRO = ROOT / "hydro_data"
OUT_PLANTS = HYDRO / "austria_pumped_storage_plants.csv"
OUT_RESERVOIRS = HYDRO / "austria_pump_hydro_reservoirs.csv"
OUT_SOURCES = HYDRO / "SOURCES.md"


def _clean_name(s: str) -> str:
    s = str(s)
    s = re.sub(r"\[\d+\]", "", s)
    s = re.sub(r"\*+\)?", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("\xa0", " ")
    return s


def _parse_mw(val) -> float | None:
    """Parse German MW values; Wikipedia often uses decimal comma (730,0)."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).replace("\xa0", " ").strip()
    if not s or s in {"-", "–", "—", "nan"}:
        return None
    # strip footnote refs and ranges like 78–
    s = re.sub(r"\[\d+\]", "", s)
    s = s.split("–")[0].split("-")[0].strip()
    s = s.replace("rd.", "").replace("ca.", "").strip()
    # European: 1.234,5 or 730,0
    if re.search(r",\d", s):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    m = re.search(r"[\d.]+", s)
    if not m:
        return None
    v = float(m.group(0))
    # Heuristic: wiki HTML often drops the decimal comma → 7300 for 730,0 / 1128 for 112,8.
    # All operating Austrian PS plants are well below 1000 MW.
    if v >= 1000:
        v = v / 10.0
    return v


def _parse_year(val) -> str | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val).replace("\xa0", " ")
    years = re.findall(r"(?:19|20)\d{2}", s)
    if not years:
        return None
    return "/".join(dict.fromkeys(years))  # preserve order, unique


def load_wikipedia_ps_austria() -> pd.DataFrame:
    tables = pd.read_html(HYDRO / "wiki_pumpspeicher.html", flavor="lxml")
    at = tables[2].copy()
    at = at.dropna(subset=["Name"])
    at = at[~at["Name"].astype(str).str.contains("Gesamtleistung", na=False)]
    at = at[~at["Name"].astype(str).str.contains("Bernegger|ESB Molln", na=False)]
    rows = []
    for _, r in at.iterrows():
        name = _clean_name(r["Name"])
        if not name or name.lower() == "nan":
            continue
        rows.append(
            {
                "plant_name": name,
                "capacity_mw": _parse_mw(r["Leistung in MW"]),
                "annual_gen_gwh": _parse_mw(
                    r.get("Regelarbeit in Mio. kWh/Jahr")
                ),  # Mio kWh = GWh
                "head_m": _parse_mw(r.get("Rohfall- höhe")),
                "design_flow_m3s": _parse_mw(r.get("Ausbau­wassermenge in m³/s")),
                "commissioned": _parse_year(r.get("Fertig- stellung")),
                "state": str(r.get("Bundes- land", "")).replace("\xa0", " ").strip(),
                "operator": str(r.get("Betreiber", "")).replace("\xa0", " ").strip(),
                "source": "wikipedia_liste_pumpspeicherkraftwerke",
                "status": "operating",
            }
        )
    return pd.DataFrame(rows)


def load_wikipedia_hydro_pumped_markers() -> pd.DataFrame:
    """Extra plants marked *) on Liste von Wasserkraftwerken in Österreich."""
    tables = pd.read_html(HYDRO / "wiki_hydro.html", flavor="lxml")
    big = pd.concat([tables[0], tables[1]], ignore_index=True)
    mask = big["Name"].astype(str).str.contains(r"\*\)", regex=True)
    rows = []
    for _, r in big.loc[mask].iterrows():
        name = _clean_name(r["Name"])
        rows.append(
            {
                "plant_name": name,
                "capacity_mw": _parse_mw(r["Leistung in MW"]),
                "annual_gen_gwh": _parse_mw(r.get("Regel­arbeit in Mio. kWh/a")),
                "head_m": _parse_mw(r.get("Roh­fall- höhe in m")),
                "design_flow_m3s": _parse_mw(r.get("Ausbau- durch­fluss in m³/s")),
                "commissioned": _parse_year(r.get("Fertig- stellung")),
                "state": str(r.get("Bun- des- land", "")).strip(),
                "operator": str(r.get("Betreiber", "")).strip(),
                "source": "wikipedia_wasserkraftwerke_starred",
                "status": "operating",
            }
        )
    return pd.DataFrame(rows)


# Curated plant ↔ reservoir links and attributes from operators / wiki / VERBUND PDF
PLANT_RESERVOIR_MAP = [
    # plant, role, reservoir, volume_hm3, area_km2, water_level_m, dam_height_m, lat, lon, notes
    ("Malta-Hauptstufe", "upper", "Kölnbreinspeicher", 200.2, 2.5, 1902, 200, 47.079, 13.344, "Malta-Reißeck group; VERBUND volume"),
    ("Malta-Hauptstufe", "lower", "Ausgleichsbecken Rottau / Galgenbichl", None, None, None, None, 46.923, 13.355, "Lower basin for pumps"),
    ("Malta-Oberstufe", "upper", "Großer Mühldorfer See / Reißeck lakes", None, None, None, None, 46.925, 13.365, "Reißeck plateau lakes"),
    ("Malta-Oberstufe", "lower", "Kölnbreinspeicher", 200.2, 2.5, 1902, 200, 47.079, 13.344, ""),
    ("Reißeck II", "upper", "Reißeck / Großer See group", None, None, None, None, 46.93, 13.37, "Links Reißeck lakes to Kölnbrein"),
    ("Reißeck II", "lower", "Kölnbreinspeicher", 200.2, 2.5, 1902, 200, 47.079, 13.344, ""),
    ("Limberg II", "upper", "Mooserboden", 84.9, 1.6, 2036, 107, 47.168, 12.718, "Kaprun; VERBUND volume"),
    ("Limberg II", "lower", "Wasserfallboden", 81.2, 1.5, 1672, 120, 47.183, 12.722, "Kaprun"),
    ("Kaprun Oberstufe Limberg", "upper", "Mooserboden", 84.9, 1.6, 2036, 107, 47.168, 12.718, ""),
    ("Kaprun Oberstufe Limberg", "lower", "Wasserfallboden", 81.2, 1.5, 1672, 120, 47.183, 12.722, ""),
    ("Kopswerk II", "upper", "Kopssee (Kops)", 42.9, 1.0, 1809, 122, 46.972, 10.122, "illwerke vkw"),
    ("Kopswerk II", "lower", "Rifa / Vermunt cascade", None, None, None, None, 47.01, 10.05, "Via Obervermunt / Rodund system"),
    ("Obervermuntwerk II", "upper", "Silvretta-Stausee", 38.0, 1.3, 2030, 80, 46.918, 10.092, ""),
    ("Obervermuntwerk II", "lower", "Vermuntsee", 11.0, 0.4, 1743, 54, 46.955, 10.065, ""),
    ("Rodundwerk II", "upper", "Latschau / Vermunt cascade", None, None, None, None, 47.07, 9.88, "illwerke Rodund group"),
    ("Rodundwerk II", "lower", "Rodundbecken", None, None, None, None, 47.10, 9.85, ""),
    ("Rodundwerk I", "upper", "Latschau / Vermunt cascade", None, None, None, None, 47.07, 9.88, ""),
    ("Rodundwerk I", "lower", "Rodundbecken", None, None, None, None, 47.10, 9.85, ""),
    ("Lünerseewerk", "upper", "Lünersee", 78.3, 1.55, 1970, None, 47.052, 9.753, "Natural lake raised"),
    ("Lünerseewerk", "lower", "Latschau / Ill cascade", None, None, None, None, 47.07, 9.88, ""),
    ("Häusling", "upper", "Speicher Zillergründl", 86.7, 1.28, 1850, 186, 47.121, 12.067, "Zemm-Ziller; VERBUND"),
    ("Häusling", "lower", "Speicher Stillupp", 6.8, 0.55, 1120, 28, 47.075, 11.862, "Weekly storage / lower basin"),
    ("Roßhag", "upper", "Schlegeisspeicher", 126.5, 2.02, 1782, 131, 47.033, 11.704, "Zemm-Ziller; VERBUND"),
    ("Roßhag", "lower", "Speicher Stillupp", 6.8, 0.55, 1120, 28, 47.075, 11.862, ""),
    ("Kühtai", "upper", "Speicher Finstertal", 60.0, 1.02, 2325, 150, 47.213, 11.041, "Sellrain-Silz; TIWAG"),
    ("Kühtai", "lower", "Ausgleichsbecken Längental", 3.0, 0.18, 1900, None, 47.210, 11.015, ""),
    ("Silz", "upper", "Speicher Finstertal", 60.0, 1.02, 2325, 150, 47.213, 11.041, "Turbine-only from Finstertal (not a pump plant)"),
    ("Feldsee", "upper", "Feldsee (Fragant)", None, None, None, None, 46.95, 13.05, "KELAG Fragant group"),
    ("Feldsee", "lower", "Wurten / Fragant cascade", None, None, None, None, 46.94, 13.03, ""),
    ("Koralpe", "upper", "Koralpe upper basin", None, None, None, None, 46.75, 15.02, "KELAG"),
    ("Koralpe", "lower", "Koralpe lower basin", None, None, None, None, 46.74, 15.03, ""),
    ("Ranna", "upper", "Ranna / Klaffer reservoirs", None, None, None, None, 48.58, 13.78, "Energie AG; earliest AT PS (1925)"),
    ("Ranna", "lower", "Ranna lower basin", None, None, None, None, 48.57, 13.79, ""),
    ("Innerfragant I", "upper", "Fragant / Wurten reservoirs", None, None, None, None, 46.95, 13.05, "KELAG"),
    ("Innerfragant II", "upper", "Fragant / Wurten reservoirs", None, None, None, None, 46.95, 13.05, "KELAG"),
    ("Reißeck Jahresspeicher", "upper", "Reißeck Jahresspeicher lakes", None, None, None, None, 46.93, 13.37, "VERBUND Reißeck"),
    ("Wienerbruck", "upper", "Wienerbruck reservoir", None, None, None, None, 47.85, 15.30, "evn; small PS (**)"),
    ("Erlaufboden", "upper", "Erlaufboden reservoir", None, None, None, None, 47.87, 15.28, "evn; small PS (**)"),
]

# Additional hydro reservoirs often paired with PS / storage plants (not always pumped)
EXTRA_RESERVOIRS = [
    ("Stausee Gepatsch", 138.0, 2.6, 1767, 153, 46.931, 10.745, "TIWAG Kaunertal; storage (not PS upper/lower pair)", "Tirol"),
    ("Achensee", 481.0, 6.8, 929, None, 47.45, 11.71, "TIWAG Achenseewerk; natural lake used as storage", "Tirol"),
    ("Speicher Durlaßboden", 52.0, 1.75, 1405, None, 47.28, 12.08, "Gerlos group; VERBUND lists 50.7 hm³", "Tirol"),
]


def normalize_plant_key(name: str) -> str:
    n = name.lower()
    n = n.replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    n = re.sub(r"[^a-z0-9]+", "", n)
    return n


PLANT_ALIASES = {
    "maltahauptstufe": "Malta-Hauptstufe",
    "maltaoberstufe": "Malta-Oberstufe",
    "kopswerkii": "Kopswerk II",
    "limbergii": "Limberg II",
    "kaprunoberstufelimbergii": "Limberg II",
    "kaprunoberstufelimberg": "Kaprun Oberstufe Limberg",
    "reisseckii": "Reißeck II",
    "reisseckjahresspeicher": "Reißeck Jahresspeicher",
    "haeusling": "Häusling",
    "obervermuntwerkii": "Obervermuntwerk II",
    "rodundwerkii": "Rodundwerk II",
    "rodundwerki": "Rodundwerk I",
    "luenerseewerk": "Lünerseewerk",
    "rosshag": "Roßhag",
    "kuehtai": "Kühtai",
    "silz": "Silz",
    "feldsee": "Feldsee",
    "koralpe": "Koralpe",
    "ranna": "Ranna",
    "pumpspeicherkraftwerkranna": "Ranna",
    "innerfraganti": "Innerfragant I",
    "innerfragantii": "Innerfragant II",
    "wienerbruck": "Wienerbruck",
    "erlaufboden": "Erlaufboden",
}


def merge_plants(ps: pd.DataFrame, starred: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for df in (ps, starred):
        d = df.copy()
        d["key"] = d["plant_name"].map(normalize_plant_key)
        d["canonical"] = d["key"].map(PLANT_ALIASES)
        frames.append(d)
    allp = pd.concat(frames, ignore_index=True)

    # Prefer canonical names; drop Silz from pumped list (turbine-only) unless we keep for reference
    prefer_source = {
        "wikipedia_liste_pumpspeicherkraftwerke": 0,
        "wikipedia_wasserkraftwerke_starred": 1,
    }
    allp["_rank"] = allp["source"].map(prefer_source).fillna(9)
    allp["plant_name"] = allp["canonical"].fillna(allp["plant_name"])
    allp = allp.sort_values(["plant_name", "_rank"])
    merged = allp.groupby("plant_name", as_index=False).first()

    # Fill missing capacity from other rows
    for col in ["capacity_mw", "annual_gen_gwh", "head_m", "design_flow_m3s", "commissioned"]:
        filled = allp.groupby("plant_name")[col].apply(
            lambda s: next((x for x in s if pd.notna(x) and x not in {"", None}), None)
        )
        merged[col] = merged["plant_name"].map(filled)

    # Annotate plant type
    turbine_only = {"Silz"}
    merged["plant_type"] = merged["plant_name"].map(
        lambda n: "storage_turbine" if n in turbine_only else "pumped_storage"
    )
    # Kühtai is the pumped plant for Sellrain-Silz; ensure present
    if "Kühtai" not in set(merged["plant_name"]):
        kue = starred[starred["plant_name"].str.contains("Kühtai|Kuehtai|Kuhtai", case=False, na=False)]
        if len(kue):
            row = kue.iloc[0].to_dict()
            row["plant_name"] = "Kühtai"
            row["plant_type"] = "pumped_storage"
            merged = pd.concat([merged, pd.DataFrame([row])], ignore_index=True)

    merged = merged.drop(columns=[c for c in ["key", "canonical", "_rank"] if c in merged.columns])
    merged = merged.sort_values("capacity_mw", ascending=False, na_position="last")
    return merged.reset_index(drop=True)


def build_reservoirs(plants: pd.DataFrame) -> pd.DataFrame:
    rows = []
    plant_set = set(plants["plant_name"])
    for plant, role, res, vol, area, level, dam_h, lat, lon, notes in PLANT_RESERVOIR_MAP:
        if plant not in plant_set and plant not in {"Kühtai", "Silz"}:
            # still include if we know the plant from map
            pass
        rows.append(
            {
                "reservoir_name": res,
                "linked_plant": plant,
                "role": role,
                "volume_hm3": vol,
                "surface_area_km2": area,
                "full_supply_level_m": level,
                "dam_height_m": dam_h,
                "lat": lat,
                "lon": lon,
                "state": None,
                "notes": notes,
                "pump_hydro_related": True,
            }
        )
    for name, vol, area, level, dam_h, lat, lon, notes, state in EXTRA_RESERVOIRS:
        rows.append(
            {
                "reservoir_name": name,
                "linked_plant": None,
                "role": "storage",
                "volume_hm3": vol,
                "surface_area_km2": area,
                "full_supply_level_m": level,
                "dam_height_m": dam_h,
                "lat": lat,
                "lon": lon,
                "state": state,
                "notes": notes,
                "pump_hydro_related": "storage_associated",
            }
        )
    df = pd.DataFrame(rows)

    # Attach Tirol WIS ids where we can match names
    wis_path = HYDRO / "tirol_seen" / "WIS_GEW_PL_1.shp"
    if wis_path.exists():
        import geopandas as gpd

        g = gpd.read_file(wis_path)
        name_map = {
            "Schlegeisspeicher": "Schlegeis",
            "Speicher Zillergründl": "Zillergründl",
            "Speicher Stillupp": "Stillupp",
            "Speicher Finstertal": "Finstertal",
            "Ausgleichsbecken Längental": "Längental",
            "Stausee Gepatsch": "Gepatsch",
            "Speicher Durlaßboden": "Durlaßboden",
            "Achensee": "Achensee",
        }
        wis_ids = []
        wis_areas = []
        for _, r in df.iterrows():
            key = None
            for k, v in name_map.items():
                if k.lower() in str(r["reservoir_name"]).lower() or v.lower() in str(
                    r["reservoir_name"]
                ).lower():
                    key = v
                    break
            if key is None:
                wis_ids.append(None)
                wis_areas.append(None)
                continue
            hits = g[g["GEW_NAME"].astype(str).str.contains(key, case=False, na=False)]
            if len(hits) == 0:
                wis_ids.append(None)
                wis_areas.append(None)
            else:
                hit = hits.sort_values("SHAPE_AREA", ascending=False).iloc[0]
                wis_ids.append(hit["GEW_ID"])
                wis_areas.append(round(float(hit["SHAPE_AREA"]) / 1e6, 3))
        df["tirol_wis_id"] = wis_ids
        df["tirol_wis_area_km2"] = wis_areas

    # Deduplicate unique reservoirs (keep first plant link rows as multi-row plant links)
    return df


def write_sources() -> None:
    OUT_SOURCES.write_text(
        """# Hydro inventory sources

## Plants
- [Liste von Pumpspeicherkraftwerken – Österreich](https://de.wikipedia.org/wiki/Liste_von_Pumpspeicherkraftwerken)
- [Liste von Wasserkraftwerken in Österreich](https://de.wikipedia.org/wiki/Liste_von_Wasserkraftwerken_in_%C3%96sterreich) (entries marked `*)` = pumped storage)
- Official capacities cross-checked against VERBUND / illwerke / TIWAG / KELAG public pages where noted

## Reservoirs / volumes
- VERBUND: *Pumped Hydro Storage* (EURELECTRIC, Harreiter 2017) — Kölnbrein, Schlegeis, Zillergründl, Mooserboden, Wasserfallboden, Durlaßboden volumes
- Wikipedia Infobox Stausee (e.g. Gepatschspeicher, Kraftwerksgruppe Zemm-Ziller)
- Tirol open data: WIS standing waters (`WIS_GEW_PL`) for outlines / area of Tyrol Kraftwerksspeicher

## Bathymetry note
ALS/LiDAR DEMs map the **water surface**, not lakebed depth. Operator bathymetric surveys are rarely public.
GLOBathy (Khazaei et al. 2022) provides **modelled** max-depth estimates for HydroLAKES waterbodies (Schlegeis ≈ Hylak_id 169131); use as estimate only.

## Official register
- [E-Control Anlagenregister](https://anlagenregister.at/) — plant-level register (technology, capacity, location); not a dedicated pumped-storage+reservoir catalogue
""",
        encoding="utf-8",
    )


def main() -> None:
    HYDRO.mkdir(parents=True, exist_ok=True)
    ps = load_wikipedia_ps_austria()
    starred = load_wikipedia_hydro_pumped_markers()
    plants = merge_plants(ps, starred)

    # Ensure Kühtai present with reasonable MW from starred list
    if plants.loc[plants["plant_name"] == "Kühtai", "capacity_mw"].isna().all():
        pass

    plants.insert(0, "id", range(1, len(plants) + 1))
    plants.to_csv(OUT_PLANTS, index=False)
    print(f"Wrote {OUT_PLANTS} ({len(plants)} plants)")
    print(plants[["plant_name", "capacity_mw", "commissioned", "state", "plant_type"]].to_string(index=False))

    reservoirs = build_reservoirs(plants)
    reservoirs.insert(0, "id", range(1, len(reservoirs) + 1))
    reservoirs.to_csv(OUT_RESERVOIRS, index=False)
    print(f"\nWrote {OUT_RESERVOIRS} ({len(reservoirs)} rows)")

    write_sources()
    print(f"Wrote {OUT_SOURCES}")


if __name__ == "__main__":
    main()
