"""Astuce Transit (Métropole Rouen Normandie GTFS) & IGN Valhalla Car Routing Engine."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

from src.db import DATA_DIR
from src.dvf_service import haversine_m

GTFS_ZIP_PATH = DATA_DIR / "astuce_gtfs.zip"
ASTUCE_DB_PATH = DATA_DIR / "astuce_transit_cache.db"


def _parse_gtfs_sec(t_str: str) -> int | None:
    parts = t_str.strip().split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return None


def ensure_astuce_index(target_lat: float = 49.44412, target_lon: float = 1.087764) -> None:
    """Build a fast SQLite summary of Astuce GTFS stops, routes, and morning peak travel times to Madame's work."""
    if ASTUCE_DB_PATH.exists() and ASTUCE_DB_PATH.stat().st_size > 50_000:
        return
    if not GTFS_ZIP_PATH.exists():
        return

    with zipfile.ZipFile(GTFS_ZIP_PATH, "r") as z:
        # 1. Routes
        routes: dict[str, dict[str, str]] = {}
        with z.open("routes.txt") as f:
            for r in csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")):
                routes[r["route_id"]] = {
                    "short_name": r.get("route_short_name", ""),
                    "long_name": r.get("route_long_name", ""),
                    "type": r.get("route_type", "3"),
                    "color": r.get("route_color", "0055A4"),
                }

        # 2. Trips
        trip_route: dict[str, str] = {}
        with z.open("trips.txt") as f:
            for r in csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")):
                trip_route[r["trip_id"]] = r["route_id"]

        # 3. Stops
        stops: dict[str, dict[str, Any]] = {}
        dest_stops: dict[str, float] = {}  # stop_id -> walk_minutes_to_target
        hub_stops: dict[str, str] = {}  # stop_id -> hub_name (Gare Rue Verte, Théâtre des Arts, Vieux Marché, Palais de Justice)

        with z.open("stops.txt") as f:
            for r in csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")):
                try:
                    slat = float(r["stop_lat"])
                    slon = float(r["stop_lon"])
                except (ValueError, KeyError):
                    continue
                sid = r["stop_id"]
                sname = r.get("stop_name", "")
                dist_target = haversine_m(slat, slon, target_lat, target_lon)
                stops[sid] = {
                    "stop_id": sid,
                    "stop_name": sname,
                    "lat": slat,
                    "lon": slon,
                    "dist_target_m": round(dist_target),
                }
                # 34 rue Cauchoise is within 650m of Vieux Marché, Gare Rue Verte, Palais de Justice, Théâtre des Arts, Cauchoise
                if dist_target <= 700:
                    walk_min = (dist_target * 1.25) / 78.0  # ~4.7 km/h with urban street factor 1.25
                    dest_stops[sid] = walk_min
                if any(h in sname.lower() for h in ("théâtre des arts", "theatre des arts", "gare-rue verte", "gare rue verte", "palais de justice", "vieux marché", "cauchoise", "boulingrin", "hôtel de ville", "hotel de ville")):
                    hub_stops[sid] = sname

        # 4. Scan stop_times for morning window (07:15 to 09:15 -> 26100 to 33300 sec)
        # Group stop sequences per trip
        trip_stops: dict[str, list[tuple[int, str, int]]] = defaultdict(list)
        stop_routes_set: dict[str, set[str]] = defaultdict(set)

        with z.open("stop_times.txt") as f:
            for r in csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")):
                tid = r["trip_id"]
                sid = r["stop_id"]
                rid = trip_route.get(tid)
                if rid and sid in stops:
                    rshort = routes.get(rid, {}).get("short_name") or rid
                    stop_routes_set[sid].add(rshort)
                sec = _parse_gtfs_sec(r.get("departure_time") or r.get("arrival_time") or "")
                if sec is None or not (25200 <= sec <= 34200):  # 07:00 - 09:30
                    continue
                seq = int(r.get("stop_sequence") or 0)
                trip_stops[tid].append((seq, sid, sec))

        # Compute best direct ride time from any stop to dest_stops, and to hub_stops
        best_direct_to_dest: dict[str, tuple[float, str, str]] = {}  # sid -> (total_ride_plus_dest_walk_min, line_name, dest_stop_name)
        best_to_hub: dict[str, tuple[float, str, str]] = {}  # sid -> (ride_min_to_hub, line_name, hub_stop_name)

        for tid, seq_list in trip_stops.items():
            if len(seq_list) < 2:
                continue
            seq_list.sort(key=lambda x: x[0])
            rid = trip_route.get(tid, "")
            rshort = routes.get(rid, {}).get("short_name", rid)

            # Find if this trip hits any dest_stop or hub_stop
            dest_hits = [(idx, sid, sec) for idx, (_, sid, sec) in enumerate(seq_list) if sid in dest_stops]
            hub_hits = [(idx, sid, sec) for idx, (_, sid, sec) in enumerate(seq_list) if sid in hub_stops]

            if dest_hits:
                for i, (_, orig_sid, orig_sec) in enumerate(seq_list):
                    for d_idx, d_sid, d_sec in dest_hits:
                        if d_idx > i and d_sec > orig_sec:
                            ride_min = (d_sec - orig_sec) / 60.0
                            total_min = ride_min + dest_stops[d_sid]
                            prev = best_direct_to_dest.get(orig_sid)
                            if prev is None or total_min < prev[0]:
                                best_direct_to_dest[orig_sid] = (
                                    round(total_min, 1),
                                    rshort,
                                    stops[d_sid]["stop_name"],
                                )

            if hub_hits:
                for i, (_, orig_sid, orig_sec) in enumerate(seq_list):
                    for h_idx, h_sid, h_sec in hub_hits:
                        if h_idx > i and h_sec > orig_sec:
                            ride_min = (h_sec - orig_sec) / 60.0
                            prev = best_to_hub.get(orig_sid)
                            if prev is None or ride_min < prev[0]:
                                best_to_hub[orig_sid] = (
                                    round(ride_min, 1),
                                    rshort,
                                    stops[h_sid]["stop_name"],
                                )

        conn = sqlite3.connect(str(ASTUCE_DB_PATH))
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS astuce_stops (
                stop_id TEXT PRIMARY KEY,
                stop_name TEXT,
                lat REAL,
                lon REAL,
                lines_json TEXT,
                direct_min REAL,
                direct_line TEXT,
                direct_arrival_stop TEXT,
                hub_min REAL,
                hub_line TEXT,
                hub_stop_name TEXT
            )
            """
        )
        conn.execute("DELETE FROM astuce_stops")

        rows_out = []
        for sid, sinfo in stops.items():
            lines_sorted = sorted(stop_routes_set.get(sid, set()))
            if not lines_sorted:
                continue
            d_info = best_direct_to_dest.get(sid, (None, "", ""))
            h_info = best_to_hub.get(sid, (None, "", ""))
            rows_out.append(
                (
                    sid,
                    sinfo["stop_name"],
                    sinfo["lat"],
                    sinfo["lon"],
                    json.dumps(lines_sorted, ensure_ascii=False),
                    d_info[0],
                    d_info[1],
                    d_info[2],
                    h_info[0],
                    h_info[1],
                    h_info[2],
                )
            )

        conn.executemany(
            "INSERT INTO astuce_stops VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows_out,
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_astuce_lat_lon ON astuce_stops (lat, lon)")
        conn.commit()
        conn.close()


async def compute_mobility(
    lat: float,
    lon: float,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Compute both Madame's Astuce public transit commute and Monsieur's car commute."""
    madame_lat = float(settings.get("madame_work_lat", 49.44412))
    madame_lon = float(settings.get("madame_work_lon", 1.087764))
    madame_max = int(settings.get("madame_max_transit_min", 45))

    monsieur_lat = float(settings.get("monsieur_work_lat", 49.372555))
    monsieur_lon = float(settings.get("monsieur_work_lon", 1.095197))

    ensure_astuce_index(madame_lat, madame_lon)

    # 1. Madame's Transit via Astuce GTFS
    direct_walk_dist_m = haversine_m(lat, lon, madame_lat, madame_lon)
    direct_walk_min = round((direct_walk_dist_m * 1.25) / 78.0)

    best_options: list[dict[str, Any]] = []
    nearby_stops_out: list[dict[str, Any]] = []

    if direct_walk_dist_m <= 1600:
        best_options.append(
            {
                "mode": "Marche directe",
                "total_minutes": direct_walk_min,
                "walk_to_stop_min": direct_walk_min,
                "OriginStop": "Départ du bien",
                "line": "À pied",
                "transfers": 0,
                "details": f"Marche directe jusqu'au 34 rue Cauchoise ({round(direct_walk_dist_m)} m)",
            }
        )

    if ASTUCE_DB_PATH.exists():
        conn = sqlite3.connect(str(ASTUCE_DB_PATH))
        conn.row_factory = sqlite3.Row
        dlat = 1500 / 111000.0
        dlon = 1500 / 72000.0
        rows = conn.execute(
            """
            SELECT * FROM astuce_stops
            WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?
            """,
            (lat - dlat, lat + dlat, lon - dlon, lon + dlon),
        ).fetchall()
        conn.close()

        seen_names: set[str] = set()
        for r in rows:
            dist_m = haversine_m(lat, lon, r["lat"], r["lon"])
            if dist_m > 1200:
                continue
            walk_min = round((dist_m * 1.25) / 78.0, 1)
            lines = json.loads(r["lines_json"] or "[]")

            if r["stop_name"] not in seen_names and dist_m <= 900:
                seen_names.add(r["stop_name"])
                nearby_stops_out.append(
                    {
                        "stop_name": r["stop_name"],
                        "distance_m": round(dist_m),
                        "walk_min": round(walk_min),
                        "lines": lines[:8],
                        "lat": r["lat"],
                        "lon": r["lon"],
                    }
                )

            # Direct line to 34 rue Cauchoise area
            if r["direct_min"] is not None:
                tot = round(walk_min + 3.0 + float(r["direct_min"]))  # +3 min average wait time at peak
                best_options.append(
                    {
                        "mode": "Astuce Direct",
                        "total_minutes": tot,
                        "walk_to_stop_min": round(walk_min),
                        "distance_stop_m": round(dist_m),
                        "origin_stop": r["stop_name"],
                        "arrival_stop": r["direct_arrival_stop"],
                        "line": r["direct_line"],
                        "transfers": 0,
                        "details": f"{round(walk_min)} min à pied jusqu'à « {r['stop_name']} » → Ligne {r['direct_line']} direct jusqu'à « {r['direct_arrival_stop']} » puis marche jusqu'au 34 rue Cauchoise",
                    }
                )
            # 1-transfer option via Rouen center hub (Théâtre des Arts / Gare Rue Verte / Boulingrin)
            elif r["hub_min"] is not None:
                # Hub to 34 rue Cauchoise takes ~8 min (transfer TEOR/Métro + short walk)
                tot = round(walk_min + 4.0 + float(r["hub_min"]) + 8.0)
                best_options.append(
                    {
                        "mode": "Astuce (1 correspondance)",
                        "total_minutes": tot,
                        "walk_to_stop_min": round(walk_min),
                        "distance_stop_m": round(dist_m),
                        "origin_stop": r["stop_name"],
                        "arrival_stop": r["hub_stop_name"],
                        "line": f"{r['hub_line']} + TEOR/Métro",
                        "transfers": 1,
                        "details": f"{round(walk_min)} min à pied jusqu'à « {r['stop_name']} » → Ligne {r['hub_line']} jusqu'au pôle « {r['hub_stop_name']} » + correspondance TEOR/Métro/Marche vers 34 rue Cauchoise",
                    }
                )

    nearby_stops_out.sort(key=lambda x: x["distance_m"])

    # Deduplicate options by line & sort by fastest total time
    unique_opts: dict[str, dict[str, Any]] = {}
    for opt in sorted(best_options, key=lambda x: x["total_minutes"]):
        key = f"{opt.get('line')}_{opt.get('transfers')}"
        if key not in unique_opts:
            unique_opts[key] = opt
    sorted_opts = list(unique_opts.values())[:5]

    if sorted_opts:
        best_madame = sorted_opts[0]
        madame_min = int(best_madame["total_minutes"])
    else:
        # Fallback estimation if outside Astuce GTFS perimeter (e.g. distant village + TER/Car)
        est_min = round(15 + (direct_walk_dist_m / 1000.0) * 3.2)
        madame_min = est_min
        best_madame = {
            "mode": "Estimation hors périmètre Astuce direct",
            "total_minutes": est_min,
            "transfers": 1,
            "line": "Car / TER + Astuce",
            "details": f"Aucun arrêt Astuce à moins de 1,2 km ({round(direct_walk_dist_m/1000, 1)} km de Rouen Rive Droite). Rabattement gare/parking relais requis.",
        }

    # 2. Monsieur's Car Commute via IGN Géoplateforme Valhalla
    monsieur_min = 0
    monsieur_km = 0.0
    crosses_seine_bridge = False
    route_geojson = None

    # Check if property is North of the Seine (Rive Droite / Plateaux Nord) while Madrillet is South (Rive Gauche)
    # In Rouen agglomeration, the Seine loops, roughly lat > 49.438 near Rouen center is Rive Droite
    if lat > 49.435:
        crosses_seine_bridge = True

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://data.geopf.fr/navigation/itineraire",
                params={
                    "resource": "bdtopo-valhalla",
                    "start": f"{lon},{lat}",
                    "end": f"{monsieur_lon},{monsieur_lat}",
                    "profile": "car",
                    "optimization": "fastest",
                },
            )
            if resp.status_code == 200:
                rdata = resp.json()
                duration_sec = float(rdata.get("duration") or 0)
                distance_m = float(rdata.get("distance") or 0)
                # Valhalla duration is free-flow; add realistic morning peak factor (+25% if crossing Seine bridge, +12% otherwise)
                peak_factor = 1.25 if crosses_seine_bridge else 1.12
                monsieur_min = max(1, round((duration_sec / 60.0) * peak_factor))
                monsieur_km = round(distance_m / 1000.0, 1)
                route_geojson = rdata.get("geometry")
    except Exception:
        pass

    if monsieur_min == 0:
        dist_m_mr = haversine_m(lat, lon, monsieur_lat, monsieur_lon)
        monsieur_km = round((dist_m_mr * 1.35) / 1000.0, 1)
        monsieur_min = max(5, round(monsieur_km * 1.6 + (7 if crosses_seine_bridge else 0)))

    return {
        "madame": {
            "destination": settings.get("madame_work_label"),
            "mode": "Transports en commun (Réseau Astuce)",
            "duration_min": madame_min,
            "max_allowed_min": madame_max,
            "is_dealbreaker": madame_min > madame_max,
            "status_label": (
                "Excellent (≤ 30 min)"
                if madame_min <= 30
                else ("Conforme (≤ 45 min)" if madame_min <= madame_max else f"TROP LONG (> {madame_max} min)")
            ),
            "best_itinerary": best_madame,
            "alternatives": sorted_opts[1:4],
            "nearby_astuce_stops": nearby_stops_out[:8],
        },
        "monsieur": {
            "destination": settings.get("monsieur_work_label"),
            "mode": "Voiture (Technopôle du Madrillet)",
            "duration_min": monsieur_min,
            "distance_km": monsieur_km,
            "crosses_seine_bridge": crosses_seine_bridge,
            "bridge_note": (
                "Franchissement de la Seine requis (prévoir +5 à +10 min aux heures de pointe sur les ponts de Rouen)"
                if crosses_seine_bridge
                else "Accès Rive Gauche / Sud sans traversée des ponts centraux de Rouen"
            ),
            "route_geometry": route_geojson,
        },
    }
