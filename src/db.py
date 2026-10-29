"""Database & Settings Management for Recherche Immo (Métropole Rouen Normandie)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "recherche_immo.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_SETTINGS: dict[str, Any] = {
    "target_budget": 250000,
    "max_budget": 275000,
    "apport": 80000,
    "loan_years": 25,
    "interest_rate": 3.65,
    "insurance_rate": 0.34,
    "notary_rate_old": 7.8,
    "min_bedrooms": 2,
    "min_surface_m2": 75,
    "min_land_m2": 150,
    "preferred_type": "Maison",
    "current_rent": 715.0,
    "current_energy": 127.45,
    "current_insurance": 10.0,
    "current_internet": 25.99,
    "madame_work_label": "34 Rue Cauchoise, 76000 Rouen",
    "madame_work_lat": 49.44412,
    "madame_work_lon": 1.087764,
    "madame_max_transit_min": 45,
    "madame_ideal_transit_min": 30,
    "monsieur_work_label": "GINGER BURGEAP — Rue du Pré de la Roquette, 76800 Saint-Étienne-du-Rouvray",
    "monsieur_work_lat": 49.372555,
    "monsieur_work_lon": 1.095197,
    "weights": {
        "price_market": 25,
        "mobility_madame": 25,
        "building_energy": 18,
        "risks_subsoil": 15,
        "neighborhood_schools": 10,
        "comfort_potential": 7,
    },
}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                source_url TEXT DEFAULT '',
                portal TEXT DEFAULT '',
                property_type TEXT DEFAULT 'Maison',
                status TEXT DEFAULT 'À étudier',
                price INTEGER NOT NULL,
                surface_m2 REAL DEFAULT 0,
                land_m2 REAL DEFAULT 0,
                rooms INTEGER DEFAULT 0,
                bedrooms INTEGER DEFAULT 0,
                dpe_letter TEXT DEFAULT '',
                ges_letter TEXT DEFAULT '',
                construction_year INTEGER DEFAULT 0,
                address_input TEXT DEFAULT '',
                address_resolved TEXT DEFAULT '',
                postcode TEXT DEFAULT '',
                city TEXT DEFAULT '',
                citycode TEXT DEFAULT '',
                lat REAL DEFAULT 0,
                lon REAL DEFAULT 0,
                address_confidence TEXT DEFAULT 'exact',
                description TEXT DEFAULT '',
                photos_json TEXT DEFAULT '[]',
                taxe_fonciere INTEGER DEFAULT 0,
                charges_annuelles INTEGER DEFAULT 0,
                travaux_estimes INTEGER DEFAULT 0,
                user_rating INTEGER DEFAULT 0,
                user_notes TEXT DEFAULT '',
                visit_checklist_json TEXT DEFAULT '[]',
                enrichment_json TEXT DEFAULT '{}',
                finance_json TEXT DEFAULT '{}',
                scoring_json TEXT DEFAULT '{}',
                ai_audit_json TEXT DEFAULT '{}',
                documents_json TEXT DEFAULT '[]',
                score_total INTEGER DEFAULT 0,
                dealbreakers_count INTEGER DEFAULT 0,
                madame_transit_min INTEGER DEFAULT 0,
                monsieur_drive_min INTEGER DEFAULT 0,
                true_monthly_cost INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        # Migration checks
        cur_cols = [c[1] for c in conn.execute("PRAGMA table_info(listings)").fetchall()]
        if "documents_json" not in cur_cols:
            conn.execute("ALTER TABLE listings ADD COLUMN documents_json TEXT DEFAULT '[]'")

        # Seed default settings if not present
        cur = conn.execute("SELECT COUNT(*) as c FROM settings")
        if cur.fetchone()["c"] == 0:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ("profile", json.dumps(DEFAULT_SETTINGS, ensure_ascii=False)),
            )
        conn.commit()


def get_settings() -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'profile'").fetchone()
        if not row:
            return dict(DEFAULT_SETTINGS)
        stored = json.loads(row["value"])
        merged = dict(DEFAULT_SETTINGS)
        merged.update(stored)
        return merged


def update_settings(new_settings: dict[str, Any]) -> dict[str, Any]:
    current = get_settings()
    current.update(new_settings)
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES ('profile', ?)",
            (json.dumps(current, ensure_ascii=False),),
        )
        conn.commit()
    return current


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    for k in ("photos_json", "visit_checklist_json", "enrichment_json", "finance_json", "scoring_json", "ai_audit_json", "documents_json"):
        short_key = k.replace("_json", "")
        try:
            d[short_key] = json.loads(d.get(k) or ("[]" if "list" in k or "photos" in k or "documents" in k else "{}"))
        except Exception:
            d[short_key] = [] if ("list" in k or "photos" in k or "documents" in k) else {}
    return d


def list_listings() -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM listings ORDER BY score_total DESC, created_at DESC"
        ).fetchall()
        return [_row_to_dict(r) for r in rows]


def get_listing(listing_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        return _row_to_dict(row) if row else None


def save_listing(data: dict[str, Any], listing_id: int | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    fields = [
        "title", "source_url", "portal", "property_type", "status",
        "price", "surface_m2", "land_m2", "rooms", "bedrooms",
        "dpe_letter", "ges_letter", "construction_year",
        "address_input", "address_resolved", "postcode", "city", "citycode",
        "lat", "lon", "address_confidence", "description",
        "photos_json", "taxe_fonciere", "charges_annuelles", "travaux_estimes",
        "user_rating", "user_notes", "visit_checklist_json",
        "enrichment_json", "finance_json", "scoring_json", "ai_audit_json", "documents_json",
        "score_total", "dealbreakers_count", "madame_transit_min",
        "monsieur_drive_min", "true_monthly_cost",
    ]
    json_map = {
        "photos": "photos_json",
        "visit_checklist": "visit_checklist_json",
        "enrichment": "enrichment_json",
        "finance": "finance_json",
        "scoring": "scoring_json",
        "ai_audit": "ai_audit_json",
        "documents": "documents_json",
    }
    for obj_key, col_key in json_map.items():
        if obj_key in data and col_key not in data:
            data[col_key] = json.dumps(data[obj_key], ensure_ascii=False)
    for col in ("enrichment_json", "finance_json", "scoring_json", "ai_audit_json", "documents_json"):
        if col in data and isinstance(data[col], (dict, list)):
            data[col] = json.dumps(data[col], ensure_ascii=False)

    with get_conn() as conn:
        if listing_id is None:
            cols = [f for f in fields if f in data]
            cols += ["created_at", "updated_at"]
            vals = [data[f] for f in fields if f in data] + [now, now]
            placeholders = ", ".join(["?"] * len(cols))
            cur = conn.execute(
                f"INSERT INTO listings ({', '.join(cols)}) VALUES ({placeholders})",
                vals,
            )
            listing_id = cur.lastrowid
        else:
            cols = [f for f in fields if f in data]
            vals = [data[f] for f in cols] + [now, listing_id]
            set_clause = ", ".join([f"{c} = ?" for c in cols] + ["updated_at = ?"])
            conn.execute(
                f"UPDATE listings SET {set_clause} WHERE id = ?",
                vals,
            )
        conn.commit()
    return get_listing(int(listing_id))  # type: ignore


def delete_listing(listing_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM listings WHERE id = ?", (listing_id,))
        conn.commit()
        return cur.rowcount > 0
