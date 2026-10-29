"""DVF (Demandes de Valeurs Foncières) Engine for Seine-Maritime (76) & National Fallback."""

from __future__ import annotations

import csv
import gzip
import math
import sqlite3
import statistics
from pathlib import Path
from typing import Any

from src.db import DATA_DIR

DVF_DB_PATH = DATA_DIR / "dvf_76_cache.db"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def ensure_dvf_index() -> None:
    """Build a fast SQLite spatial index from data/dvf_76_*.csv.gz if not already built."""
    if DVF_DB_PATH.exists() and DVF_DB_PATH.stat().st_size > 500_000:
        return

    gz_files = sorted(DATA_DIR.glob("dvf_76_*.csv.gz"))
    if not gz_files:
        return

    conn = sqlite3.connect(str(DVF_DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mutations (
            id_mutation TEXT,
            date_mutation TEXT,
            valeur_fonciere REAL,
            adresse_numero TEXT,
            adresse_nom_voie TEXT,
            code_postal TEXT,
            nom_commune TEXT,
            type_local TEXT,
            surface_bati REAL,
            pieces INTEGER,
            surface_terrain REAL,
            lat REAL,
            lon REAL,
            prix_m2 REAL
        )
        """
    )
    conn.execute("DELETE FROM mutations")

    # Group by id_mutation so multi-lot rows (e.g. house + dependency + land parcel) are aggregated cleanly
    mutations_agg: dict[str, dict[str, Any]] = {}

    for gz in gz_files:
        try:
            with gzip.open(gz, "rt", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("nature_mutation") != "Vente":
                        continue
                    type_local = row.get("type_local", "")
                    if type_local not in ("Maison", "Appartement"):
                        continue
                    try:
                        val = float(row.get("valeur_fonciere") or 0)
                        surf = float(row.get("surface_reelle_bati") or 0)
                        lat = float(row.get("latitude") or 0)
                        lon = float(row.get("longitude") or 0)
                    except ValueError:
                        continue
                    if val < 25000 or surf < 15 or lat == 0 or lon == 0:
                        continue

                    mid = row.get("id_mutation") or f"{row.get('date_mutation')}_{lat}_{lon}_{val}"
                    terrain = 0.0
                    try:
                        terrain = float(row.get("surface_terrain") or 0)
                    except ValueError:
                        pass
                    pieces = 0
                    try:
                        pieces = int(float(row.get("nombre_pieces_principales") or 0))
                    except ValueError:
                        pass

                    existing = mutations_agg.get(mid)
                    if not existing or surf > existing["surface_bati"]:
                        mutations_agg[mid] = {
                            "id_mutation": mid,
                            "date_mutation": row.get("date_mutation", ""),
                            "valeur_fonciere": val,
                            "adresse_numero": row.get("adresse_numero", ""),
                            "adresse_nom_voie": row.get("adresse_nom_voie", ""),
                            "code_postal": row.get("code_postal", ""),
                            "nom_commune": row.get("nom_commune", ""),
                            "type_local": type_local,
                            "surface_bati": surf,
                            "pieces": pieces,
                            "surface_terrain": max(terrain, existing["surface_terrain"] if existing else 0.0),
                            "lat": lat,
                            "lon": lon,
                        }
        except Exception:
            continue

    rows_to_insert = []
    for m in mutations_agg.values():
        prix_m2 = m["valeur_fonciere"] / m["surface_bati"]
        if 500 <= prix_m2 <= 12000:
            rows_to_insert.append(
                (
                    m["id_mutation"],
                    m["date_mutation"],
                    m["valeur_fonciere"],
                    m["adresse_numero"],
                    m["adresse_nom_voie"],
                    m["code_postal"],
                    m["nom_commune"],
                    m["type_local"],
                    m["surface_bati"],
                    m["pieces"],
                    m["surface_terrain"],
                    m["lat"],
                    m["lon"],
                    round(prix_m2, 0),
                )
            )

    conn.executemany(
        """
        INSERT INTO mutations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows_to_insert,
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lat_lon ON mutations (lat, lon)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cp ON mutations (code_postal)")
    conn.commit()
    conn.close()


def analyze_dvf_around(
    lat: float,
    lon: float,
    property_type: str = "Maison",
    price: float = 0,
    surface_m2: float = 0,
    radius_m: int = 800,
) -> dict[str, Any]:
    """Return local notarized sales statistics & comparable transactions around (lat, lon)."""
    ensure_dvf_index()
    if not DVF_DB_PATH.exists() or lat == 0 or lon == 0:
        return {"available": False, "sales": []}

    # Bounding box for initial query (~2km max)
    search_radius = max(radius_m, 1500)
    dlat = search_radius / 111000.0
    dlon = search_radius / (111000.0 * math.cos(math.radians(lat)))

    conn = sqlite3.connect(str(DVF_DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT * FROM mutations
        WHERE lat BETWEEN ? AND ?
          AND lon BETWEEN ? AND ?
        ORDER BY date_mutation DESC
        """,
        (lat - dlat, lat + dlat, lon - dlon, lon + dlon),
    ).fetchall()
    conn.close()

    all_nearby = []
    for r in rows:
        dist = haversine_m(lat, lon, r["lat"], r["lon"])
        if dist <= search_radius:
            d = dict(r)
            d["distance_m"] = round(dist)
            all_nearby.append(d)

    # Filter for same property type within 800m, or expand to 1500m if < 8 sales
    target_type = "Maison" if "maison" in property_type.lower() else "Appartement"
    same_type_800 = [x for x in all_nearby if x["type_local"] == target_type and x["distance_m"] <= radius_m]
    same_type_1500 = [x for x in all_nearby if x["type_local"] == target_type]

    sample = same_type_800 if len(same_type_800) >= 6 else same_type_1500
    used_radius = radius_m if len(same_type_800) >= 6 else 1500

    if not sample:
        sample = all_nearby
        used_radius = 1500

    if not sample:
        return {"available": False, "sales": [], "count": 0}

    prices_m2 = sorted([x["prix_m2"] for x in sample])
    median_m2 = round(statistics.median(prices_m2))
    mean_m2 = round(statistics.mean(prices_m2))
    q25_m2 = round(prices_m2[max(0, int(len(prices_m2) * 0.25))])
    q75_m2 = round(prices_m2[min(len(prices_m2) - 1, int(len(prices_m2) * 0.75))])

    # Street-level sales (< 220m)
    street_sales = [x for x in sample if x["distance_m"] <= 220]
    street_median_m2 = round(statistics.median([x["prix_m2"] for x in street_sales])) if len(street_sales) >= 2 else None

    listing_price_m2 = round(price / surface_m2) if (price > 0 and surface_m2 > 0) else 0
    diff_pct = round(((listing_price_m2 - median_m2) / median_m2) * 100, 1) if (listing_price_m2 and median_m2) else 0
    street_diff_pct = round(((listing_price_m2 - street_median_m2) / street_median_m2) * 100, 1) if (listing_price_m2 and street_median_m2) else None

    # Commune-wide benchmark (e.g. all of Rouen or Maromme, like MoteurImmo / MeilleursAgents)
    commune_name = sample[0].get("nom_commune") if sample else None
    commune_median_m2 = None
    commune_diff_pct = None
    if commune_name:
        try:
            conn = sqlite3.connect(str(DVF_DB_PATH))
            c_rows = conn.execute(
                "SELECT prix_m2 FROM mutations WHERE UPPER(nom_commune) = ? AND type_local = ? AND prix_m2 BETWEEN 500 AND 12000",
                (commune_name.upper(), target_type),
            ).fetchall()
            if not c_rows:
                c_rows = conn.execute(
                    "SELECT prix_m2 FROM mutations WHERE UPPER(nom_commune) = ? AND prix_m2 BETWEEN 500 AND 12000",
                    (commune_name.upper(),),
                ).fetchall()
            conn.close()
            c_prices = [r[0] for r in c_rows if r[0] > 0]
            if c_prices:
                commune_median_m2 = round(statistics.median(c_prices))
                if listing_price_m2 and commune_median_m2:
                    commune_diff_pct = round(((listing_price_m2 - commune_median_m2) / commune_median_m2) * 100, 1)
        except Exception:
            pass

    estimated_fair_price = round(median_m2 * surface_m2, -2) if surface_m2 > 0 else 0
    estimated_low_price = round(q25_m2 * surface_m2, -2) if surface_m2 > 0 else 0
    estimated_high_price = round(q75_m2 * surface_m2, -2) if surface_m2 > 0 else 0

    if diff_pct <= -10:
        verdict = "Excellente affaire (Sous le marché)"
    elif diff_pct <= 3:
        verdict = "Au prix du marché"
    elif diff_pct <= 12:
        verdict = "Légèrement surcoté (À négocier)"
    else:
        verdict = "Fortement surcoté vs ventes notariées"

    # Sort closest & most comparable first
    sample_sorted = sorted(sample, key=lambda x: (x["distance_m"], -int(x["date_mutation"].replace("-", "") or 0)))

    return {
        "available": True,
        "target_type": target_type,
        "radius_used_m": used_radius,
        "count": len(sample),
        "street_count": len(street_sales),
        "median_price_m2": median_m2,
        "mean_price_m2": mean_m2,
        "q25_price_m2": q25_m2,
        "q75_price_m2": q75_m2,
        "street_median_m2": street_median_m2,
        "street_diff_pct": street_diff_pct,
        "commune_name": commune_name,
        "commune_median_m2": commune_median_m2,
        "commune_diff_pct": commune_diff_pct,
        "listing_price_m2": listing_price_m2,
        "diff_vs_median_pct": diff_pct,
        "verdict": verdict,
        "estimated_fair_price": int(estimated_fair_price),
        "estimated_low_price": int(estimated_low_price),
        "estimated_high_price": int(estimated_high_price),
        "sales": sample_sorted[:25],
    }
