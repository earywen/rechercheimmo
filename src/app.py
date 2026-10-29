"""FastAPI Application for Recherche Immo (Métropole Rouen Normandie)."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import re
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.ai_service import build_heuristic_audit, run_agy_deep_audit
from src.db import (
    BASE_DIR,
    delete_listing,
    get_listing,
    get_settings,
    init_db,
    list_listings,
    save_listing,
    update_settings,
)
from src.document_service import (
    get_document_file,
    remove_document,
    reprocess_listing_documents,
    save_uploaded_document,
)
from src.dvf_service import ensure_dvf_index
from src.enrichment_service import (
    detective_dpe_lookup,
    geocode_address,
    run_full_enrichment,
)
from src.finance_and_scoring import compute_financials, compute_scoring_and_dealbreakers
from src.mobility_service import ensure_astuce_index

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, ensure_dvf_index)
    await loop.run_in_executor(None, ensure_astuce_index)
    await seed_demo_listing_if_empty()
    yield


app = FastAPI(
    title="Recherche Immo — Métropole Rouen Normandie",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


def parse_raw_ad_text(text: str) -> dict[str, Any]:
    """Extract price, surface, rooms, bedrooms, land, DPE, GES, and postal code from raw pasted listing text."""
    out: dict[str, Any] = {}
    if not text:
        return out

    # 1. Price (e.g. 245 000 € or 245000€)
    m_price = re.search(r"(\d[\d\s\u00a0\u202f]{4,8})\s*€", text)
    if m_price:
        p_str = re.sub(r"\D", "", m_price.group(1))
        if p_str and 30000 <= int(p_str) <= 2500000:
            out["price"] = int(p_str)

    # 2. Terrain / Jardin (detect first so we don't confuse land size with living surface)
    m_land = re.search(
        r"(?:surface\s+totale\s+du\s+terrain|surface\s+terrain|terrain\s*:\s*|terrain\s+de\s+|parcelle\s+de\s+|jardin\s+de\s+)[^\d]{0,15}(\d{2,5})\s*m(?:²|2)",
        text,
        re.IGNORECASE,
    )
    if m_land:
        out["land_m2"] = float(m_land.group(1))
    else:
        m_land_fb = re.search(r"(?:terrain|parcelle|jardin)[^\d]{0,25}(\d{2,5})\s*m(?:²|2)", text, re.IGNORECASE)
        if m_land_fb:
            out["land_m2"] = float(m_land_fb.group(1))

    land_val = out.get("land_m2")

    # 3. Surface habitable with strict priorities:
    # Priority A: Explicit "Surface habitable", "Loi Carrez", or "habitable"
    m_hab = re.search(r"(?:surface\s+habitable|loi\s+carrez|habitable)[^\d]{0,25}(\d{2,3}(?:[.,]\d)?)\s*m(?:²|2)?\b", text, re.IGNORECASE)
    if m_hab:
        out["surface_m2"] = float(m_hab.group(1).replace(",", "."))

    # Priority B: "Maison 3 pièces 93 m²" or "3 pièces 93m²"
    if not out.get("surface_m2"):
        m_pieces_surf = re.search(r"\d{1,2}\s*pi[èe]ces?[^\d]{1,20}(\d{2,3}(?:[.,]\d)?)\s*m(?:²|2)?\b", text, re.IGNORECASE)
        if m_pieces_surf:
            cand = float(m_pieces_surf.group(1).replace(",", "."))
            if cand != land_val:
                out["surface_m2"] = cand

    # Priority C: Total price / price per m² (e.g. 249 000 € and 2 677 €/m² -> 93 m²)
    if not out.get("surface_m2") and out.get("price"):
        m_ppm2 = re.search(r"(\d[\d\s\u00a0\u202f]{3,5})\s*€\s*(?:par|\/)\s*m[²2]", text, re.IGNORECASE)
        if m_ppm2:
            ppm2 = float(re.sub(r"\D", "", m_ppm2.group(1)))
            if ppm2 > 500:
                calc_surf = round(out["price"] / ppm2, 1)
                if 20 <= calc_surf <= 400:
                    out["surface_m2"] = calc_surf

    # Priority D: First occurrence that is not equal to land_val
    if not out.get("surface_m2"):
        all_surfs = [
            float(x.replace(",", "."))
            for x in re.findall(r"(\d{2,3}(?:[.,]\d)?)\s*m(?:²|2)\b", text, re.IGNORECASE)
        ]
        valid_surfs = [s for s in all_surfs if land_val is None or s != land_val]
        if valid_surfs:
            out["surface_m2"] = valid_surfs[0]
        elif all_surfs:
            out["surface_m2"] = all_surfs[0]

    # Rooms & Bedrooms
    m_rooms = re.search(r"(\d{1,2})\s*pi[èe]ces?", text, re.IGNORECASE)
    if m_rooms:
        out["rooms"] = int(m_rooms.group(1))
    m_bed = re.search(r"(\d{1,2})\s*chambres?", text, re.IGNORECASE)
    if m_bed:
        out["bedrooms"] = int(m_bed.group(1))

    # DPE & GES
    m_dpe = re.search(r"\bDPE\s*[:\-]?\s*([A-G])\b", text, re.IGNORECASE)
    if m_dpe:
        out["dpe_letter"] = m_dpe.group(1).upper()
    m_ges = re.search(r"\bGES\s*[:\-]?\s*([A-G])\b", text, re.IGNORECASE)
    if m_ges:
        out["ges_letter"] = m_ges.group(1).upper()

    # Postal code (76xxx or 27xxx)
    m_cp = re.search(r"\b((?:76|27)\d{3})\b", text)
    if m_cp:
        out["postcode"] = m_cp.group(1)

    # Taxe foncière
    m_tf = re.search(r"taxe\s+fonci[èe]re[^\d]{0,20}(\d[\d\s]{2,5})\s*€", text, re.IGNORECASE)
    if m_tf:
        tf_s = re.sub(r"\D", "", m_tf.group(1))
        if tf_s:
            out["taxe_fonciere"] = int(tf_s)

    return out


async def _analyze_listing_pipeline(listing_id: int, run_deep_ai: bool = False) -> dict[str, Any]:
    listing = get_listing(listing_id)
    if not listing:
        raise ValueError(f"Listing {listing_id} not found")

    settings = get_settings()
    enrichment = await run_full_enrichment(listing, settings)
    geo = enrichment.get("geocoding", {})

    updates: dict[str, Any] = {}
    if geo.get("found"):
        updates["lat"] = geo.get("lat")
        updates["lon"] = geo.get("lon")
        updates["address_resolved"] = geo.get("label") or listing.get("address_input")
        updates["postcode"] = geo.get("postcode") or listing.get("postcode")
        updates["city"] = geo.get("city") or listing.get("city")
        updates["citycode"] = geo.get("citycode") or listing.get("citycode")

    cad_area = enrichment.get("cadastre", {}).get("contenance_m2") or 0
    if not listing.get("land_m2") and cad_area > 0 and "maison" in (listing.get("property_type") or "Maison").lower():
        updates["land_m2"] = cad_area

    ademe_recs = enrichment.get("ademe_dpe", {}).get("records", [])
    if ademe_recs and enrichment.get("ademe_dpe", {}).get("exact_address_match"):
        top_dpe = ademe_recs[0]
        if not listing.get("dpe_letter") and top_dpe.get("dpe"):
            updates["dpe_letter"] = top_dpe["dpe"]
        if not listing.get("ges_letter") and top_dpe.get("ges"):
            updates["ges_letter"] = top_dpe["ges"]

    merged_listing = dict(listing)
    merged_listing.update(updates)

    # Heuristic or deep AI audit
    temp_finance = compute_financials(merged_listing, enrichment, settings)
    temp_scoring = compute_scoring_and_dealbreakers(merged_listing, enrichment, temp_finance, settings)

    if run_deep_ai:
        ai_audit = await run_agy_deep_audit(merged_listing, enrichment, temp_finance, temp_scoring)
    else:
        ai_audit = build_heuristic_audit(merged_listing, enrichment, temp_finance, temp_scoring)

    # Align travaux_estimes with AI audit realistic works breakdown (e.g. decoration/customization vs major renovation)
    if ai_audit.get("works_total_min") is not None:
        est_w = round((int(ai_audit.get("works_total_min", 0)) + int(ai_audit.get("works_total_max", 0))) / 2, -2)
        updates["travaux_estimes"] = int(est_w)
        merged_listing["travaux_estimes"] = int(est_w)

    finance = compute_financials(merged_listing, enrichment, settings)
    scoring = compute_scoring_and_dealbreakers(merged_listing, enrichment, finance, settings)

    if not listing.get("visit_checklist"):
        updates["visit_checklist"] = ai_audit.get("visit_questions", [])

    updates.update(
        {
            "enrichment": enrichment,
            "finance": finance,
            "scoring": scoring,
            "ai_audit": ai_audit,
            "score_total": int(scoring.get("total_score") or 0),
            "dealbreakers_count": len(scoring.get("dealbreakers") or []),
            "madame_transit_min": int(enrichment.get("mobility", {}).get("madame", {}).get("duration_min") or 0),
            "monsieur_drive_min": int(enrichment.get("mobility", {}).get("monsieur", {}).get("duration_min") or 0),
            "true_monthly_cost": int(finance.get("true_monthly_cost") or 0),
        }
    )
    return save_listing(updates, listing_id=listing_id)


async def seed_demo_listing_if_empty() -> None:
    existing = list_listings()
    if existing:
        return
    # Create one realistic house in Bois-Guillaume / Bihorel (very sought-after in Rouen Métropole, direct TEOR/Fast bus to Cauchoise)
    sample = {
        "title": "Maison familiale 4 ch avec jardin — Bois-Guillaume (Limite Rouen)",
        "source_url": "https://www.leboncoin.fr/ad/ventes_immobilieres/exemple-bois-guillaume",
        "portal": "LeBonCoin (Exemple Démo)",
        "property_type": "Maison",
        "status": "À visiter",
        "price": 248000,
        "surface_m2": 96,
        "land_m2": 340,
        "rooms": 5,
        "bedrooms": 3,
        "dpe_letter": "D",
        "ges_letter": "D",
        "construction_year": 1978,
        "address_input": "120 Rue de la République 76230 Bois-Guillaume",
        "postcode": "76230",
        "city": "Bois-Guillaume",
        "taxe_fonciere": 1650,
        "description": (
            "À vendre sur le plateau de Bois-Guillaume, proche des commerces et des lignes de bus Fast F1 / F2 vers Rouen Centre (Cauchoise / Théâtre des Arts). "
            "Maison lumineuse de 96 m² comprenant entrée, séjour-salon traversant donnant sur jardin clos de 340 m² exposé Sud-Ouest, cuisine aménagée, "
            "3 chambres à l'étage (possibilité 4e), salle de bains, garage complet. Double vitrage PVC, chauffage gaz condensation récent. DPE D."
        ),
    }
    saved = save_listing(sample)
    try:
        await _analyze_listing_pipeline(saved["id"], run_deep_ai=False)
    except Exception:
        pass


@app.get("/", response_class=HTMLResponse)
async def index_page() -> HTMLResponse:
    index_file = TEMPLATES_DIR / "index.html"
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


@app.get("/api/settings")
async def api_get_settings() -> JSONResponse:
    return JSONResponse(get_settings())


@app.put("/api/settings")
async def api_update_settings(payload: dict[str, Any]) -> JSONResponse:
    updated = update_settings(payload)
    return JSONResponse(updated)


@app.get("/api/listings")
async def api_list_listings() -> JSONResponse:
    return JSONResponse(list_listings())


@app.get("/api/listings/{listing_id}")
async def api_get_listing(listing_id: int) -> JSONResponse:
    item = get_listing(listing_id)
    if not item:
        raise HTTPException(status_code=404, detail="Annonce introuvable")
    return JSONResponse(item)


@app.post("/api/listings")
async def api_create_listing(payload: dict[str, Any], background_tasks: BackgroundTasks) -> JSONResponse:
    # Auto-parse raw text if fields are missing
    desc = payload.get("description", "")
    extracted = parse_raw_ad_text(desc)
    for k, v in extracted.items():
        if not payload.get(k):
            payload[k] = v

    if not payload.get("title"):
        ptype = payload.get("property_type", "Maison")
        surf = payload.get("surface_m2") or "?"
        city = payload.get("city") or payload.get("address_input") or "Rouen Métropole"
        payload["title"] = f"{ptype} {surf} m² — {city}"

    payload["price"] = int(payload.get("price") or 250000)
    saved = save_listing(payload)
    analyzed = await _analyze_listing_pipeline(saved["id"], run_deep_ai=bool(payload.get("run_deep_ai", False)))
    if payload.get("run_deep_ai_async", True) and not payload.get("run_deep_ai", False):
        background_tasks.add_task(_analyze_listing_pipeline, saved["id"], True)
    return JSONResponse(analyzed)


@app.put("/api/listings/{listing_id}")
async def api_update_listing(listing_id: int, payload: dict[str, Any]) -> JSONResponse:
    existing = get_listing(listing_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Annonce introuvable")

    reanalyze = bool(payload.pop("reanalyze", False))
    saved = save_listing(payload, listing_id=listing_id)
    if reanalyze:
        saved = await _analyze_listing_pipeline(listing_id, run_deep_ai=False)
    else:
        # Recompute financials & scoring if financial fields changed
        settings = get_settings()
        fin = compute_financials(saved, saved.get("enrichment", {}), settings)
        sco = compute_scoring_and_dealbreakers(saved, saved.get("enrichment", {}), fin, settings)
        saved = save_listing(
            {
                "finance": fin,
                "scoring": sco,
                "score_total": sco["total_score"],
                "dealbreakers_count": len(sco["dealbreakers"]),
                "true_monthly_cost": fin["true_monthly_cost"],
            },
            listing_id=listing_id,
        )
    return JSONResponse(saved)


@app.post("/api/listings/{listing_id}/reanalyze")
async def api_reanalyze_listing(listing_id: int, payload: dict[str, Any] | None = None) -> JSONResponse:
    deep = True if not payload else bool(payload.get("deep_ai", True))
    analyzed = await _analyze_listing_pipeline(listing_id, run_deep_ai=deep)
    return JSONResponse(analyzed)


@app.delete("/api/listings/{listing_id}")
async def api_delete_listing(listing_id: int) -> JSONResponse:
    ok = delete_listing(listing_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Annonce introuvable")
    return JSONResponse({"deleted": True, "id": listing_id})


@app.get("/api/geocode")
async def api_geocode(q: str, postcode: str = "") -> JSONResponse:
    res = await geocode_address(q, postcode=postcode)
    return JSONResponse(res)


@app.post("/api/detective-dpe")
async def api_detective_dpe(payload: dict[str, Any]) -> JSONResponse:
    candidates = await detective_dpe_lookup(
        postcode=str(payload.get("postcode") or ""),
        surface_m2=float(payload.get("surface_m2") or 0),
        dpe_letter=str(payload.get("dpe_letter") or ""),
        ges_letter=str(payload.get("ges_letter") or ""),
        construction_year=int(payload.get("construction_year") or 0),
        property_type=str(payload.get("property_type") or "Maison"),
    )
    return JSONResponse({"candidates": candidates})


@app.post("/api/listings/{listing_id}/documents")
async def api_upload_document(
    listing_id: int,
    file: UploadFile = File(...),
    doc_type: str = Form("Auto"),
) -> JSONResponse:
    existing = get_listing(listing_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Annonce introuvable")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Fichier vide")

    doc_meta = save_uploaded_document(
        listing_id=listing_id,
        filename=file.filename or "document.bin",
        content=content,
        doc_type=doc_type,
    )

    # Recalculate financials and scoring if taxe fonciere or energy hints were detected
    updated_listing = get_listing(listing_id) or {}
    settings = get_settings()
    fin = compute_financials(updated_listing, updated_listing.get("enrichment", {}), settings)
    sco = compute_scoring_and_dealbreakers(updated_listing, updated_listing.get("enrichment", {}), fin, settings)
    save_listing(
        {
            "finance": fin,
            "scoring": sco,
            "score_total": sco["total_score"],
            "dealbreakers_count": len(sco["dealbreakers"]),
            "true_monthly_cost": fin["true_monthly_cost"],
        },
        listing_id=listing_id,
    )
    final_listing = get_listing(listing_id)
    return JSONResponse({"success": True, "document": doc_meta, "listing": final_listing})


@app.post("/api/listings/{listing_id}/documents/reprocess")
async def api_reprocess_documents(listing_id: int) -> JSONResponse:
    updated = reprocess_listing_documents(listing_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Annonce introuvable")
    settings = get_settings()
    fin = compute_financials(updated, updated.get("enrichment", {}), settings)
    sco = compute_scoring_and_dealbreakers(updated, updated.get("enrichment", {}), fin, settings)
    save_listing(
        {
            "finance": fin,
            "scoring": sco,
            "score_total": sco["total_score"],
            "dealbreakers_count": len(sco["dealbreakers"]),
            "true_monthly_cost": fin["true_monthly_cost"],
        },
        listing_id=listing_id,
    )
    final_listing = get_listing(listing_id)
    return JSONResponse({"success": True, "listing": final_listing})


@app.get("/api/listings/{listing_id}/documents/{doc_id}/download")
async def api_download_document(listing_id: int, doc_id: str):
    res = get_document_file(listing_id, doc_id)
    if not res:
        raise HTTPException(status_code=404, detail="Document introuvable sur le disque")
    file_path, original_filename = res
    return FileResponse(
        path=str(file_path),
        filename=original_filename,
        media_type="application/octet-stream",
    )


@app.delete("/api/listings/{listing_id}/documents/{doc_id}")
async def api_delete_document(listing_id: int, doc_id: str) -> JSONResponse:
    ok = remove_document(listing_id, doc_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Document introuvable")
    updated = get_listing(listing_id)
    return JSONResponse({"deleted": True, "listing": updated})

