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
        try:
            with sqlite3.connect(str(ASTUCE_DB_PATH)) as conn:
                conn.execute("SELECT transfer_min FROM astuce_stops LIMIT 1")
                return
        except Exception:
            pass

    if not GTFS_ZIP_PATH.exists():
        return

    with zipfile.ZipFile(GTFS_ZIP_PATH, "r") as z:
        # 1. Routes
        routes: dict[str, dict[str, str]] = {}
        with z.open("routes.txt") as f:
            for r in csv.DictReader(io.TextIOWrapper(f, "utf-8-sig")):
                routes[r["route_id"]] = {
                    "short_name": r.get("route_short_name", "") or r["route_id"],
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
        dest_stops: dict[str, tuple[str, float]] = {}  # stop_id -> (stop_name, walk_minutes_to_target)

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
                # 34 rue Cauchoise is within 700m of Cauchoise, Vieux Marché, Square Verdrel, Palais de Justice, Théâtre des Arts, Belges, Gare-Rue Verte
                if dist_target <= 700:
                    walk_min = (dist_target * 1.25) / 78.0  # ~4.7 km/h with urban street factor 1.25
                    dest_stops[sid] = (sname, round(walk_min, 1))

        # 4. Scan stop_times for morning peak window (07:00 to 09:30 -> 25200 to 34200 sec)
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
                if sec is None or not (25200 <= sec <= 34200):
                    continue
                seq = int(r.get("stop_sequence") or 0)
                trip_stops[tid].append((seq, sid, sec))

        # 5. Direct from any stop to any dest_stop
        best_direct: dict[str, tuple[float, str, str]] = {}  # sid -> (total_transit_plus_dest_walk_min, line_name, dest_name)
        for tid, slist in trip_stops.items():
            slist.sort(key=lambda x: x[0])
            rid = trip_route.get(tid, "")
            rshort = routes.get(rid, {}).get("short_name", rid)
            dest_indices = [(idx, sid, sec) for idx, (_, sid, sec) in enumerate(slist) if sid in dest_stops]
            if not dest_indices:
                continue
            for d_idx, dsid, d_sec in dest_indices:
                dname, dwalk = dest_stops[dsid]
                for i in range(d_idx):
                    orig_sid = slist[i][1]
                    orig_sec = slist[i][2]
                    ride_m = (d_sec - orig_sec) / 60.0
                    tot = ride_m + dwalk
                    if orig_sid not in best_direct or tot < best_direct[orig_sid][0]:
                        best_direct[orig_sid] = (round(tot, 1), rshort, dname)

        # 6. Real 1-transfer connections
        # Leg 2 from transfer station X to dest_stop D
        leg2_by_stop = defaultdict(list)
        for tid, slist in trip_stops.items():
            slist.sort(key=lambda x: x[0])
            rid = trip_route.get(tid, "")
            rshort = routes.get(rid, {}).get("short_name", rid)
            dest_indices = [(idx, sid, sec) for idx, (_, sid, sec) in enumerate(slist) if sid in dest_stops]
            if not dest_indices:
                continue
            for d_idx, dsid, d_sec in dest_indices:
                dname, dwalk = dest_stops[dsid]
                for i in range(d_idx):
                    xsid = slist[i][1]
                    x_sec = slist[i][2]
                    leg2_by_stop[xsid].append((x_sec, d_sec, rshort, dname, dwalk))

        best_transfer: dict[str, tuple[float, str, str, str, str]] = {}  # sid -> (total_transit_min, line1, xname, line2, dest_name)
        for tid, slist in trip_stops.items():
            slist.sort(key=lambda x: x[0])
            rid = trip_route.get(tid, "")
            r1 = routes.get(rid, {}).get("short_name", rid)
            for i, (_, sid, orig_sec) in enumerate(slist):
                for j in range(i + 1, len(slist)):
                    xsid = slist[j][1]
                    x_arr_sec = slist[j][2]
                    if xsid in leg2_by_stop:
                        xname = stops.get(xsid, {}).get("stop_name", "")
                        for (t_dep, t_arr, r2, dname, dwalk) in leg2_by_stop[xsid]:
                            wait_s = t_dep - x_arr_sec
                            if 180 <= wait_s <= 720:  # 3 to 12 min connection buffer
                                transit_m = (t_arr - orig_sec) / 60.0 + dwalk
                                if sid not in best_transfer or transit_m < best_transfer[sid][0]:
                                    best_transfer[sid] = (round(transit_m, 1), r1, xname, r2, dname)

        conn = sqlite3.connect(str(ASTUCE_DB_PATH))
        conn.execute("DROP TABLE IF EXISTS astuce_stops")
        conn.execute(
            """
            CREATE TABLE astuce_stops (
                stop_id TEXT PRIMARY KEY,
                stop_name TEXT,
                lat REAL,
                lon REAL,
                lines_json TEXT,
                direct_min REAL,
                direct_line TEXT,
                direct_arrival_stop TEXT,
                transfer_min REAL,
                transfer_line1 TEXT,
                transfer_station TEXT,
                transfer_line2 TEXT,
                transfer_arrival_stop TEXT
            )
            """
        )

        rows_out = []
        for sid, sinfo in stops.items():
            lines_sorted = sorted(stop_routes_set.get(sid, set()))
            if not lines_sorted:
                continue
            d_info = best_direct.get(sid, (None, "", ""))
            t_info = best_transfer.get(sid, (None, "", "", "", ""))
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
                    t_info[0],
                    t_info[1],
                    t_info[2],
                    t_info[3],
                    t_info[4],
                )
            )

        conn.executemany(
            "INSERT INTO astuce_stops VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                "origin_stop": "Départ du bien",
                "line": "À pied",
                "transfers": 0,
                "details": f"Marche directe jusqu'au 34 rue Cauchoise ({round(direct_walk_dist_m)} m, ~{direct_walk_min} min)",
            }
        )

    if ASTUCE_DB_PATH.exists():
        conn = sqlite3.connect(str(ASTUCE_DB_PATH))
        conn.row_factory = sqlite3.Row
        # Scan stops up to 1800m to catch high-speed TEOR terminus (e.g. Bernard Palissy T2) or Fast lines
        dlat = 1800 / 111000.0
        dlon = 1800 / 72000.0
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
            if dist_m > 1600:
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
                tot = round(walk_min + 3.0 + float(r["direct_min"]))  # +3 min average departure wait
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
                        "details": f"{round(walk_min)} min à pied jusqu'à « {r['stop_name']} » ({round(dist_m)} m) → Ligne {r['direct_line']} direct jusqu'à « {r['direct_arrival_stop']} » ({round(r['direct_min'])} min trajet+marche)",
                    }
                )
            # 1-transfer option via real connection station
            if r["transfer_min"] is not None:
                tot = round(walk_min + 3.0 + float(r["transfer_min"]))
                best_options.append(
                    {
                        "mode": "Astuce (1 correspondance)",
                        "total_minutes": tot,
                        "walk_to_stop_min": round(walk_min),
                        "distance_stop_m": round(dist_m),
                        "origin_stop": r["stop_name"],
                        "transfer_station": r["transfer_station"],
                        "arrival_stop": r["transfer_arrival_stop"],
                        "line": f"{r['transfer_line1']} + {r['transfer_line2']}",
                        "transfers": 1,
                        "details": f"{round(walk_min)} min à pied jusqu'à « {r['stop_name']} » ({round(dist_m)} m) → Ligne {r['transfer_line1']} jusqu'à « {r['transfer_station']} » puis Ligne {r['transfer_line2']} vers « {r['transfer_arrival_stop']} » ({round(r['transfer_min'])} min trajet+corresp)",
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
