"""AI Audit & Vision Service powered by the user's authenticated `agy` CLI (Gemini Pro OAuth)."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from pathlib import Path
from typing import Any

AGY_BIN = shutil.which("agy") or "/home/beelink/.local/bin/agy"


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    # Strip markdown code fences if present
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # Find outermost braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except Exception:
            pass
    return None


def build_heuristic_audit(
    listing: dict[str, Any],
    enrichment: dict[str, Any],
    finance: dict[str, Any],
    scoring: dict[str, Any],
) -> dict[str, Any]:
    """Provide an immediate structured expert analysis before/while the deep `agy` AI audit runs."""
    dvf = enrichment.get("dvf", {})
    mob = enrichment.get("mobility", {})
    geo = enrichment.get("georisques", {})
    cad = enrichment.get("cadastre", {})
    dpe_letter = (listing.get("dpe_letter") or "Non renseigné").upper()
    surface = float(listing.get("surface_m2") or 85)

    # Estimate works by DPE and description keywords
    desc_low = (listing.get("description") or "").lower()
    works_items: list[dict[str, Any]] = []
    if dpe_letter in ("E", "F", "G"):
        cost_iso = round(surface * (280 if dpe_letter in ("F", "G") else 140), -2)
        works_items.append(
            {
                "poste": f"Isolation thermique & chauffage (DPE {dpe_letter})",
                "urgence": "Haute" if dpe_letter in ("F", "G") else "Moyenne",
                "budget_min": int(cost_iso * 0.8),
                "budget_max": int(cost_iso * 1.25),
                "commentaire": "Isolation combles/murs ou remplacement du système de chauffage pour réduire la facture annuelle.",
            }
        )
    if any(w in desc_low for w in ("rafraîchir", "rafraichir", "travaux", "potentiel", "rénover", "renover", "à moderniser")):
        works_items.append(
            {
                "poste": "Rafraîchissement intérieur (peintures, sols, cuisine/SDB)",
                "urgence": "Moyenne",
                "budget_min": int(surface * 180),
                "budget_max": int(surface * 350),
                "commentaire": "Mots-clés de rénovation détectés dans le descriptif de l'annonce.",
            }
        )
    if "simple vitrage" in desc_low or "fenêtres" in desc_low:
        works_items.append(
            {
                "poste": "Menuiseries (passage en double vitrage PVC/Alu)",
                "urgence": "Haute",
                "budget_min": 6000,
                "budget_max": 12000,
                "commentaire": "Vérifier l'état de toutes les huisseries et volets lors de la visite.",
            }
        )

    total_min = sum(w["budget_min"] for w in works_items)
    total_max = sum(w["budget_max"] for w in works_items)

    # Negotiation arguments
    neg_args: list[str] = []
    if dvf.get("available") and float(dvf.get("diff_vs_median_pct") or 0) > 2:
        neg_args.append(
            f"Écart de +{dvf['diff_vs_median_pct']}% par rapport aux ventes notariées DVF réelles autour du bien ({dvf['median_price_m2']} €/m² sur {dvf['count']} ventes comparables, soit une valeur théorique de {dvf['estimated_fair_price']:,} €).".replace(",", " ")
        )
    if dpe_letter in ("E", "F", "G"):
        neg_args.append(
            f"Performance énergétique DPE {dpe_letter} impliquant une facture d'énergie estimée à {finance.get('energy_an')} €/an et des travaux d'amélioration thermique."
        )
    if int(geo.get("argiles_code") or 0) >= 2:
        neg_args.append(
            f"Exposition au retrait-gonflement des argiles ({geo.get('argiles_exposition')}) nécessitant une vigilance structurelle."
        )
    if not neg_args:
        neg_args.append(
            f"Positionnement d'une offre initiale autour de {finance.get('recommended_offer_price', 0):,} € en s'appuyant sur votre dossier financier solide (80 000 € d'apport immédiat).".replace(",", " ")
        )

    checklist = [
        {"category": "Toiture & Bâti", "question": "De quelle année date la toiture (ardoises/tuiles, liteaux, zinguerie) et y a-t-il une décennale ou facture d'entretien ?", "checked": False},
        {"category": "Sous-sol & Marnières (76)", "question": f"Existe-t-il un diagnostic cavités/marnières sur la parcelle {cad.get('section', '')}{cad.get('numero', '')} ? ({geo.get('cavites_500m_count', 0)} cavité(s) dans les 500 m)", "checked": False},
        {"category": "Assainissement", "question": "Le bien est-il raccordé au tout-à-l'égout avec contrôle de conformité de la Métropole Rouen Normandie à jour ?", "checked": False},
        {"category": "Énergie & Chauffage", "question": "Quel est l'âge exact de la chaudière / PAC / ballon d'eau chaude et le montant réel des dernières factures EDF/Gaz ?", "checked": False},
        {"category": "Électricité & Amiante", "question": "Quelles sont les anomalies listées dans le diagnostic électrique et le diagnostic amiante/plomb ?", "checked": False},
        {"category": "Fiscalité & Motifs", "question": "Quel est le montant exact de la dernière taxe foncière et depuis combien de temps le bien est-il en vente ?", "checked": False},
    ]

    madame_min = mob.get("madame", {}).get("duration_min", "?")
    monsieur_min = mob.get("monsieur", {}).get("duration_min", "?")

    return {
        "engine": "Synthèse Open Data + Règles Métier (Prêt pour Audit IA Approfondi `agy`)",
        "executive_summary": (
            f"{listing.get('property_type', 'Bien')} de {int(surface)} m² à {listing.get('city', 'Rouen Métropole')} affiché à {int(listing.get('price', 0)):,} € "
            f"({dvf.get('listing_price_m2', 0)} €/m² vs {dvf.get('median_price_m2', '?')} €/m² DVF). "
            f"Trajet Madame (Astuce vers 34 rue Cauchoise) : {madame_min} min. Trajet Monsieur (voiture vers Madrillet) : {monsieur_min} min. "
            f"Vrai coût mensuel tout compris estimé à {finance.get('true_monthly_cost', 0)} €/mois."
        ).replace(",", " "),
        "ad_decryption": [
            "Vérifiez la concordance entre la surface annoncée et la surface habitable réelle du DPE ADEME.",
            f"Parcelle cadastrale identifiée : Section {cad.get('section', '?')} n°{cad.get('numero', '?')} ({cad.get('contenance_m2', '?')} m²), zone PLU {cad.get('plu_zone', 'U')}.",
        ],
        "photo_observations": [],
        "works_breakdown": works_items,
        "works_total_min": total_min,
        "works_total_max": total_max,
        "negotiation_strategy": {
            "target_offer_eur": finance.get("recommended_offer_price"),
            "max_walkaway_eur": min(int(listing.get("price") or 0), int(dvf.get("estimated_high_price") or listing.get("price") or 0)),
            "arguments": neg_args,
        },
        "visit_questions": checklist,
    }


async def run_agy_deep_audit(
    listing: dict[str, Any],
    enrichment: dict[str, Any],
    finance: dict[str, Any],
    scoring: dict[str, Any],
) -> dict[str, Any]:
    """Invoke `agy --print` with the user's Gemini Pro OAuth account to perform a deep text + photo + open-data audit."""
    base_audit = build_heuristic_audit(listing, enrichment, finance, scoring)
    if not Path(AGY_BIN).exists():
        return base_audit

    # Prepare compact context for agy prompt
    dvf_summary = {
        k: enrichment.get("dvf", {}).get(k)
        for k in ("median_price_m2", "q25_price_m2", "q75_price_m2", "listing_price_m2", "diff_vs_median_pct", "verdict", "estimated_fair_price", "count")
    }
    context_payload = {
        "bien": {
            "titre": listing.get("title"),
            "type": listing.get("property_type"),
            "prix": listing.get("price"),
            "surface_m2": listing.get("surface_m2"),
            "terrain_m2": listing.get("land_m2") or enrichment.get("cadastre", {}).get("contenance_m2"),
            "pieces": listing.get("rooms"),
            "chambres": listing.get("bedrooms"),
            "dpe": listing.get("dpe_letter"),
            "ges": listing.get("ges_letter"),
            "annee_construction": listing.get("construction_year"),
            "adresse": listing.get("address_resolved") or listing.get("address_input"),
            "description": listing.get("description"),
            "photos": (listing.get("photos") or [])[:6],
        },
        "profil_couple": {
            "budget_cible": 250000,
            "apport": 80000,
            "chambres_min": 2,
            "trajet_madame_cible": "34 rue Cauchoise 76000 Rouen en transport Astuce (max 40-45 min)",
            "trajet_monsieur_cible": "GINGER BURGEAP Saint-Étienne-du-Rouvray en voiture",
        },
        "open_data": {
            "dvf": dvf_summary,
            "mobilite": enrichment.get("mobility"),
            "cadastre_plu": {
                k: enrichment.get("cadastre", {}).get(k)
                for k in ("parcel_id", "section", "numero", "contenance_m2", "plu_zone", "plu_libelle")
            },
            "georisques_76": {
                k: enrichment.get("georisques", {}).get(k)
                for k in ("argiles_exposition", "cavites_100m_count", "cavites_500m_count", "nearest_cavite_m", "seveso_count", "inondation_risque", "risques_commune")
            },
            "ademe_dpe": enrichment.get("ademe_dpe", {}).get("records", [])[:2],
            "ecoles": enrichment.get("schools", {}).get("schools", [])[:4],
            "solaire": enrichment.get("solar"),
            "commerces_et_bruit_osm": enrichment.get("osm"),
        },
        "simulation_financiere": finance,
        "scoring": scoring,
    }

    prompt = (
        "Tu es un chasseur immobilier expert de la Métropole Rouen Normandie et ingénieur bâtiment. "
        "Analyse ce bien immobilier pour un couple (budget ~250 000 €, apport 80 000 €, min 2 chambres, "
        "Madame travaille au 34 rue Cauchoise à Rouen en transport en commun Astuce max 45 min, "
        "Monsieur travaille chez GINGER BURGEAP au Madrillet à Saint-Étienne-du-Rouvray en voiture). "
        "N'utilise AUCUN outil externe : toutes les données Open Data ont déjà été collectées ci-dessous.\n\n"
        f"DONNÉES DU BIEN ET OPEN DATA :\n{json.dumps(context_payload, ensure_ascii=False)}\n\n"
        "Réponds UNIQUEMENT avec un objet JSON valide respectant exactement cette structure :\n"
        "{\n"
        '  "executive_summary": "Synthèse franche et directe en 3-4 phrases sur l\'intérêt du bien pour le couple",\n'
        '  "ad_decryption": ["Décryptage des sous-entendus de l\'annonce vs réalité Open Data (3 à 5 points)"],\n'
        '  "photo_observations": ["Observations sur l\'état apparent / points visuels à contrôler (2 à 4 points)"],\n'
        '  "works_breakdown": [\n'
        '    {"poste": "Nom du poste de travaux", "urgence": "Haute|Moyenne|Basse", "budget_min": 2000, "budget_max": 5000, "commentaire": "Explication"}\n'
        "  ],\n"
        '  "works_total_min": 5000,\n'
        '  "works_total_max": 15000,\n'
        '  "negotiation_strategy": {\n'
        '    "target_offer_eur": 235000,\n'
        '    "max_walkaway_eur": 245000,\n'
        '    "arguments": ["Argument chiffré 1 (DVF, DPE, travaux, risques...)", "Argument chiffré 2", "Argument chiffré 3"]\n'
        "  },\n"
        '  "visit_questions": [\n'
        '    {"category": "Toiture / Sous-sol 76 / Énergie / Copro...", "question": "Question précise à poser à l\'agent immobilier", "checked": false}\n'
        "  ]\n"
        "}"
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            AGY_BIN,
            "--disable-slash-commands",
            "--output-format",
            "json",
            f"--print={prompt}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=75.0)
        raw_out = stdout.decode("utf-8", errors="ignore").strip()
        outer = json.loads(raw_out)
        resp_text = outer.get("response", "") if isinstance(outer, dict) else raw_out
        parsed = _extract_json(resp_text)
        if parsed and isinstance(parsed, dict) and "executive_summary" in parsed:
            parsed["engine"] = "Audit IA Approfondi (`agy` / Gemini Pro OAuth)"
            return parsed
    except Exception:
        pass

    return base_audit
