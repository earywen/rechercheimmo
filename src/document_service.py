"""Document management & analysis service for Recherche Immo.

Handles uploading, storage, text extraction (via pdftotext / layout),
and parsing of real documents (DPE, Taxe Foncière, Factures, Diagnostics)
to feed into AI audits and financial simulations.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.db import BASE_DIR, get_listing, save_listing

UPLOADS_DIR = BASE_DIR / "data" / "uploads"
PDFTOTEXT_BIN = shutil.which("pdftotext") or "/usr/bin/pdftotext"


def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r"[^\w\.\-\s]", "_", filename).strip()
    return re.sub(r"\s+", "_", cleaned) or "document.bin"


def extract_text_from_file(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        if Path(PDFTOTEXT_BIN).exists():
            try:
                res = subprocess.run(
                    [PDFTOTEXT_BIN, "-layout", str(file_path), "-"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip()
            except Exception:
                pass
        return ""
    elif ext in (".txt", ".md", ".json", ".csv", ".log"):
        try:
            return file_path.read_text(encoding="utf-8", errors="ignore").strip()
        except Exception:
            return ""
    return ""


def parse_document_hints(text: str, doc_type: str) -> dict[str, Any]:
    """Extract known numerical figures (Taxe Foncière, DPE, Facture Énergie) from official document text."""
    hints: dict[str, Any] = {}
    if not text:
        return hints

    low = text.lower()

    # 1. Taxe Foncière detection
    # Patterns like: "Total de votre imposition : 1 450 €", "Montant net à payer : 1450 €", "Taxe foncière : 1 450 €"
    tf_patterns = [
        r"(?:total\s+de\s+votre\s+imposition|total\s+à\s+payer|montant\s+(?:net\s+)?à\s+payer|cotisation\s+totale|taxe\s+foncière)[\s\:\=]+([0-9\s]{3,6})\s*(?:€|euros)",
        r"(?:taxe\s+foncière.*?)([0-9]{3,4})\s*(?:€|euros)",
    ]
    for pat in tf_patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            val_str = m.group(1).replace(" ", "").strip()
            try:
                val = int(val_str)
                if 200 <= val <= 10000:
                    hints["taxe_fonciere"] = val
                    break
            except Exception:
                pass

    # 2. DPE letter & kWh/m²/an
    # Patterns like "Consommation (énergie primaire) : 185 kWh/m²/an" or "Classe D"
    kwh_m = re.search(r"([0-9]{2,3})\s*kwh(?:ep)?\s*\/\s*m²(?:\.|\s*\/)?\s*an", low)
    if kwh_m:
        try:
            hints["dpe_kwh"] = int(kwh_m.group(1))
        except Exception:
            pass

    dpe_letter_m = re.search(r"(?:classe|dpe|consommation\s+énergétique)[\s\:\-]+([a-g])\b", low)
    if dpe_letter_m:
        hints["dpe_letter"] = dpe_letter_m.group(1).upper()

    ges_letter_m = re.search(r"(?:émissions|ges|climat)[\s\:\-]+([a-g])\b", low)
    if ges_letter_m:
        hints["ges_letter"] = ges_letter_m.group(1).upper()

    # 3. Energy bills (factures annuelles EDF / Engie / TotalEnergies)
    energy_bill_m = re.search(r"(?:montant\s+annuel|facture\s+annuelle|total\s+ttc\s+annuel|consommation\s+estimée)[\s\:\=]+([0-9\s]{3,5})\s*(?:€|euros)", low)
    if energy_bill_m:
        try:
            val = int(energy_bill_m.group(1).replace(" ", ""))
            if 300 <= val <= 8000:
                hints["facture_energie_an"] = val
        except Exception:
            pass

    return hints


def save_uploaded_document(
    listing_id: int,
    filename: str,
    content: bytes,
    doc_type: str = "Autre",
) -> dict[str, Any]:
    """Save document to disk, extract its text, and append it to listing['documents']."""
    listing = get_listing(listing_id)
    if not listing:
        raise ValueError(f"Listing {listing_id} introuvable")

    doc_id = uuid.uuid4().hex[:8]
    safe_name = sanitize_filename(filename)
    dest_dir = UPLOADS_DIR / str(listing_id)
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest_file = dest_dir / f"{doc_id}_{safe_name}"
    dest_file.write_bytes(content)

    extracted_text = extract_text_from_file(dest_file)
    hints = parse_document_hints(extracted_text, doc_type)

    doc_meta = {
        "id": doc_id,
        "filename": filename,
        "safe_filename": safe_name,
        "doc_type": doc_type,
        "size_bytes": len(content),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "extracted_chars": len(extracted_text),
        "extracted_snippet": extracted_text[:1200] if extracted_text else "",
        "extracted_text_full": extracted_text[:25000] if extracted_text else "",
        "detected_hints": hints,
    }

    current_docs = list(listing.get("documents") or [])
    current_docs.append(doc_meta)

    updates: dict[str, Any] = {"documents": current_docs}

    # If document provides official figures, automatically update the listing fields!
    if hints.get("taxe_fonciere") and (not listing.get("taxe_fonciere") or doc_type in ("Taxe Foncière", "Avis d'imposition")):
        updates["taxe_fonciere"] = hints["taxe_fonciere"]
    if hints.get("dpe_letter") and doc_type in ("DPE", "Diagnostic de Performance Énergétique"):
        updates["dpe_letter"] = hints["dpe_letter"]
    if hints.get("ges_letter") and doc_type in ("DPE", "Diagnostic de Performance Énergétique"):
        updates["ges_letter"] = hints["ges_letter"]

    save_listing(updates, listing_id=listing_id)
    return doc_meta


def remove_document(listing_id: int, doc_id: str) -> bool:
    listing = get_listing(listing_id)
    if not listing:
        return False

    current_docs = list(listing.get("documents") or [])
    new_docs = []
    removed = False

    for doc in current_docs:
        if doc.get("id") == doc_id:
            removed = True
            safe_name = doc.get("safe_filename") or sanitize_filename(doc.get("filename", ""))
            file_on_disk = UPLOADS_DIR / str(listing_id) / f"{doc_id}_{safe_name}"
            if file_on_disk.exists():
                try:
                    file_on_disk.unlink()
                except Exception:
                    pass
        else:
            new_docs.append(doc)

    if removed:
        save_listing({"documents": new_docs}, listing_id=listing_id)
        return True
    return False


def get_document_file(listing_id: int, doc_id: str) -> tuple[Path, str] | None:
    listing = get_listing(listing_id)
    if not listing:
        return None
    for doc in listing.get("documents") or []:
        if doc.get("id") == doc_id:
            safe_name = doc.get("safe_filename") or sanitize_filename(doc.get("filename", ""))
            target = UPLOADS_DIR / str(listing_id) / f"{doc_id}_{safe_name}"
            if target.exists():
                return target, doc.get("filename", safe_name)
    return None


def format_documents_for_audit_prompt(documents: list[dict[str, Any]]) -> str:
    if not documents:
        return ""
    lines = ["=== PIÈCES & DOCUMENTS OFFICIELS TRANSMIS PAR LE PROPRIÉTAIRE / VENDEUR ==="]
    for d in documents:
        lines.append(f"\n[DOCUMENT: {d.get('filename')} | Type: {d.get('doc_type')} | Ajouté le {d.get('uploaded_at', '')[:10]}]")
        hints = d.get("detected_hints", {})
        if hints:
            lines.append(f"Chiffres détectés : {hints}")
        text = d.get("extracted_text_full") or d.get("extracted_snippet") or ""
        if text:
            # Crop to 6000 chars per doc to maintain reasonable prompt length
            cropped = text[:6000].replace("\r\n", "\n")
            lines.append("EXTRAIT DU CONTENU DU DOCUMENT :")
            lines.append(cropped)
        else:
            lines.append("(Aucun texte extrait - fichier binaire ou image)")
    lines.append("\n===========================================================================")
    return "\n".join(lines)
