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


def classify_document_type(filename: str, text: str, user_given: str = "") -> str:
    """Automatically determine the type of document from filename and extracted content."""
    if user_given and user_given not in ("Auto", "Autre", "Autre justificatif", ""):
        return user_given

    fn = filename.lower()
    txt = (text or "").lower()

    # 1. Avis de Taxe Foncière
    if any(k in fn for k in ("taxe_fonciere", "taxes_foncieres", "avis_tf", "imposition_tf", "taxe fonciere")) or \
       "montant de vos taxes foncières" in txt or \
       "avis_tf_rg" in txt or \
       ("avis" in txt and "taxes foncières" in txt):
        return "Taxe Foncière"

    # 2. ERP / Géorisques
    if "erp" in fn or "etat des risques" in txt or "risques et pollutions" in txt or "fiche radon" in txt or "sols argileux" in txt:
        return "État des Risques (ERP)"

    # 3. DDT / Diagnostics Techniques
    if "ddt" in fn or "dossier technique immobilier" in txt or "repérage amiante" in txt or "constat amiante" in txt or "exposition au plomb" in txt:
        return "Diagnostics Techniques (DDT)"

    # 4. DPE
    if "dpe" in fn or "diagnostic de performance énergétique" in txt or ("kwh/m²" in txt and "consommation" in txt):
        return "DPE complet"

    # 5. Factures Énergie
    if any(k in fn for k in ("facture", "edf", "engie", "totalenergies")) or ("facture d'électricité" in txt or "fournisseur d'énergie" in txt):
        return "Facture Énergie"

    # 6. Devis travaux
    if "devis" in fn or "devis" in txt[:500] or "facture artisan" in txt:
        return "Devis / Travaux"

    # 7. PV Assemblée générale / Copropriété
    if "pv" in fn or "assemblée générale" in txt or "procès-verbal d'assemblée" in txt or "syndic" in txt:
        return "PV Copropriété / AG"

    return "Document Justificatif"


def parse_document_hints(text: str, filename: str = "") -> dict[str, Any]:
    """Extract known numerical figures (Taxe Foncière, DPE, Facture Énergie, Cadastre ERP) from official document text."""
    hints: dict[str, Any] = {}
    if not text:
        return hints

    low = text.lower()

    # Detection of tax notice year (e.g. 2025, 2026)
    year_m = re.search(r"202[4-9]", filename + " " + text[:600])
    if year_m:
        hints["annee"] = int(year_m.group(0))

    # 1. Taxe Foncière detection (Strict patterns excluding city aggregate budgets)
    # DGFiP wording: "Montant de vos taxes foncières                    1101,00 €" or "1093,00 €"
    tf_strict_patterns = [
        r"montant\s+de\s+vos\s+taxes\s+foncières[\s\:\=]+([0-9\s]{3,5})(?:,[0-9]{2})?\s*€",
        r"total\s+de\s+votre\s+imposition[\s\:\=]+([0-9\s]{3,5})(?:,[0-9]{2})?\s*€",
        r"cotisation\s+totale[\s\:\=]+([0-9\s]{3,5})(?:,[0-9]{2})?\s*€",
    ]
    for pat in tf_strict_patterns:
        m = re.search(pat, low)
        if m:
            val_str = m.group(1).replace(" ", "").strip()
            try:
                val = int(val_str)
                if 200 <= val <= 8000:
                    hints["taxe_fonciere"] = val
                    break
            except Exception:
                pass

    # 2. DPE letter & kWh/m²/an
    kwh_m = re.search(r"([0-9]{2,3})\s*kwh(?:ep)?\s*\/\s*m²(?:\.|\s*\/)?\s*an", low)
    if kwh_m:
        try:
            hints["dpe_kwh"] = int(kwh_m.group(1))
        except Exception:
            pass

    if "dpe" in low or "performance énergétique" in low:
        dpe_letter_m = re.search(r"(?:classe(?:\s+énergétique|\s+dpe)?|étiquette(?:\s+dpe)?|dpe\s*[\:\=])[\s\:\-]+([a-g])\b", low)
        if dpe_letter_m:
            hints["dpe_letter"] = dpe_letter_m.group(1).upper()

        ges_letter_m = re.search(r"(?:émissions|ges|climat)\s*[\:\=][\s\-]*([a-g])\b", low)
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

    # 4. ERP Cadastre & Diagnostics
    # Pattern like "76540 000 EH 76"
    parcel_m = re.search(r"([0-9]{5})\s+[0-9]{3}\s+([a-z]{1,2})\s+([0-9]{1,4})", low)
    if parcel_m:
        hints["parcelle"] = f"Section {parcel_m.group(2).upper()} n° {parcel_m.group(3)}"

    # 5. DDT Diagnostics findings
    if "il n'a pas été repéré de matériaux ou produits contenant de l'amiante" in low:
        hints["amiante"] = "Aucun amiante détecté"
    if "l'installation intérieure d'électricité comporte une ou des anomalies" in low:
        hints["electricite"] = "Anomalie(s) électrique(s) à contrôler"
    elif "l'installation intérieure d'électricité ne comporte aucune anomalie" in low:
        hints["electricite"] = "Aucune anomalie électrique"

    return hints


def save_uploaded_document(
    listing_id: int,
    filename: str,
    content: bytes,
    doc_type: str = "Auto",
) -> dict[str, Any]:
    """Save document to disk, extract its text, auto-classify its type and append it to listing['documents']."""
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
    auto_type = classify_document_type(filename, extracted_text, user_given=doc_type)
    hints = parse_document_hints(extracted_text, filename=filename)

    doc_meta = {
        "id": doc_id,
        "filename": filename,
        "safe_filename": safe_name,
        "doc_type": auto_type,
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

    # Determine best official figures from all available documents
    best_tf = _find_best_taxe_fonciere(current_docs)
    if best_tf is not None:
        updates["taxe_fonciere"] = best_tf

    if hints.get("dpe_letter") and auto_type in ("DPE", "DPE complet"):
        updates["dpe_letter"] = hints["dpe_letter"]
    if hints.get("ges_letter") and auto_type in ("DPE", "DPE complet"):
        updates["ges_letter"] = hints["ges_letter"]

    save_listing(updates, listing_id=listing_id)
    return doc_meta


def _find_best_taxe_fonciere(docs: list[dict[str, Any]]) -> int | None:
    """Find the most relevant and recent Taxe Foncière amount across documents."""
    candidates: list[tuple[int, int]] = []  # (year, amount)
    for d in docs:
        hints = d.get("detected_hints") or {}
        tf = hints.get("taxe_fonciere")
        if tf and 200 <= tf <= 8000:
            year = hints.get("annee") or 2024
            candidates.append((year, tf))
    if not candidates:
        return None
    # Sort by year descending (newest first)
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def reprocess_listing_documents(listing_id: int) -> dict[str, Any] | None:
    """Re-analyze all already uploaded documents for a listing with updated classification and parser."""
    listing = get_listing(listing_id)
    if not listing:
        return None

    dest_dir = UPLOADS_DIR / str(listing_id)
    current_docs = list(listing.get("documents") or [])
    updated_docs = []

    for d in current_docs:
        doc_id = d.get("id")
        safe_name = d.get("safe_filename") or sanitize_filename(d.get("filename", ""))
        file_path = dest_dir / f"{doc_id}_{safe_name}"

        extracted_text = d.get("extracted_text_full") or ""
        if file_path.exists():
            extracted_text = extract_text_from_file(file_path)

        auto_type = classify_document_type(d.get("filename", ""), extracted_text, user_given="")
        hints = parse_document_hints(extracted_text, filename=d.get("filename", ""))

        d["doc_type"] = auto_type
        d["detected_hints"] = hints
        d["extracted_chars"] = len(extracted_text)
        d["extracted_snippet"] = extracted_text[:1200] if extracted_text else ""
        d["extracted_text_full"] = extracted_text[:25000] if extracted_text else ""
        updated_docs.append(d)

    updates: dict[str, Any] = {"documents": updated_docs}
    best_tf = _find_best_taxe_fonciere(updated_docs)
    if best_tf is not None:
        updates["taxe_fonciere"] = best_tf

    save_listing(updates, listing_id=listing_id)
    return get_listing(listing_id)


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
