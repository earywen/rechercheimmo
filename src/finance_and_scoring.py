"""Financial Simulator (True Monthly Cost) & 360° Scoring Engine."""

from __future__ import annotations

from typing import Any


DPE_ANNUAL_EUR_PER_M2: dict[str, float] = {
    "A": 5.5,
    "B": 8.5,
    "C": 13.0,
    "D": 19.0,
    "E": 26.5,
    "F": 35.0,
    "G": 46.0,
}


def compute_financials(
    listing: dict[str, Any],
    enrichment: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    price = int(listing.get("price") or 0)
    surface = float(listing.get("surface_m2") or 80)
    travaux = int(listing.get("travaux_estimes") or 0)
    apport = int(settings.get("apport") or 80000)
    notary_rate = float(settings.get("notary_rate_old") or 7.8) / 100.0
    loan_years = int(settings.get("loan_years") or 25)
    interest_rate = float(settings.get("interest_rate") or 3.35) / 100.0
    insurance_rate = float(settings.get("insurance_rate") or 0.34) / 100.0

    notary_fees = round(price * notary_rate)
    total_project_cost = price + notary_fees + travaux
    loan_amount = max(0, total_project_cost - apport)

    months = loan_years * 12
    monthly_rate = interest_rate / 12.0
    if loan_amount > 0 and monthly_rate > 0:
        monthly_principal_interest = loan_amount * (monthly_rate / (1.0 - (1.0 + monthly_rate) ** (-months)))
    elif loan_amount > 0:
        monthly_principal_interest = loan_amount / months
    else:
        monthly_principal_interest = 0.0

    monthly_insurance = (loan_amount * insurance_rate) / 12.0
    monthly_mortgage = round(monthly_principal_interest + monthly_insurance)
    total_interest_and_insurance = max(0, round((monthly_mortgage * months) - loan_amount))

    # Taxe foncière (known or estimated ~16 €/m2/year in Rouen agglomeration)
    taxe_fonciere_an = int(listing.get("taxe_fonciere") or 0)
    taxe_fonciere_estimated = False
    if taxe_fonciere_an <= 0:
        taxe_fonciere_an = round(surface * 16.5)
        taxe_fonciere_estimated = True

    # Annual energy cost (from ADEME DPE record if matched, else DPE letter * surface)
    dpe_letter = (listing.get("dpe_letter") or "").upper()
    ademe_records = enrichment.get("ademe_dpe", {}).get("records", [])
    energy_an = 0
    if ademe_records and ademe_records[0].get("cout_total_5_usages"):
        try:
            energy_an = round(float(ademe_records[0]["cout_total_5_usages"]))
        except (ValueError, TypeError):
            pass
    if energy_an <= 0:
        rate_m2 = DPE_ANNUAL_EUR_PER_M2.get(dpe_letter, 19.5)
        energy_an = round(surface * rate_m2)

    # Maintenance / Copro charges
    charges_an = int(listing.get("charges_annuelles") or 0)
    if charges_an <= 0:
        # Standard house maintenance provision (~60 €/month) vs apartment copro (~140 €/month)
        charges_an = 720 if "maison" in (listing.get("property_type") or "Maison").lower() else 1680

    monthly_tax = round(taxe_fonciere_an / 12.0)
    monthly_energy = round(energy_an / 12.0)
    monthly_charges = round(charges_an / 12.0)
    true_monthly_cost = monthly_mortgage + monthly_tax + monthly_energy + monthly_charges

    # Target negotiation price
    dvf = enrichment.get("dvf", {})
    dvf_fair = int(dvf.get("estimated_fair_price") or 0)
    if dvf_fair > 0 and dvf_fair < price:
        recommended_offer = max(round(price * 0.86, -2), round((dvf_fair + price) / 2 - (travaux * 0.5), -2))
    else:
        recommended_offer = round(price * 0.94 - (travaux * 0.35), -2)
    recommended_offer = int(min(price, max(price * 0.80, recommended_offer)))

    return {
        "price": price,
        "notary_fees": notary_fees,
        "travaux_estimes": travaux,
        "total_project_cost": total_project_cost,
        "apport": apport,
        "loan_amount": loan_amount,
        "loan_years": loan_years,
        "interest_rate_pct": round(interest_rate * 100, 2),
        "insurance_rate_pct": round(insurance_rate * 100, 2),
        "monthly_mortgage": monthly_mortgage,
        "total_credit_cost": total_interest_and_insurance,
        "taxe_fonciere_an": taxe_fonciere_an,
        "taxe_fonciere_estimated": taxe_fonciere_estimated,
        "energy_an": energy_an,
        "charges_an": charges_an,
        "monthly_tax": monthly_tax,
        "monthly_energy": monthly_energy,
        "monthly_charges": monthly_charges,
        "true_monthly_cost": true_monthly_cost,
        "recommended_offer_price": recommended_offer,
        "potential_discount_eur": max(0, price - recommended_offer),
        "potential_discount_pct": round(((price - recommended_offer) / price) * 100, 1) if price > 0 else 0,
    }


def compute_scoring_and_dealbreakers(
    listing: dict[str, Any],
    enrichment: dict[str, Any],
    finance: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    dealbreakers: list[dict[str, str]] = []
    warnings: list[str] = []
    strengths: list[str] = []

    price = int(listing.get("price") or 0)
    bedrooms = int(listing.get("bedrooms") or 0)
    surface = float(listing.get("surface_m2") or 0)
    land = float(listing.get("land_m2") or 0) or float(enrichment.get("cadastre", {}).get("contenance_m2") or 0)
    dpe = (listing.get("dpe_letter") or "").upper()
    prop_type = listing.get("property_type") or "Maison"

    dvf = enrichment.get("dvf", {})
    mob = enrichment.get("mobility", {})
    madame_mob = mob.get("madame", {})
    monsieur_mob = mob.get("monsieur", {})
    geo = enrichment.get("georisques", {})
    osm = enrichment.get("osm", {})
    schools = enrichment.get("schools", {})
    solar = enrichment.get("solar", {})

    # --- 1. Prix & Marché (0-100) ---
    diff_pct = float(dvf.get("diff_vs_median_pct") or 0)
    if dvf.get("available"):
        if diff_pct <= -12:
            s_price = 95
            strengths.append(f"Prix au m² très attractif ({diff_pct}% sous la médiane notariale DVF locale)")
        elif diff_pct <= 0:
            s_price = 84
            strengths.append(f"Prix cohérent avec les actes notariés DVF ({dvf.get('median_price_m2')} €/m²)")
        elif diff_pct <= 10:
            s_price = 68
            warnings.append(f"Prix affiché +{diff_pct}% au-dessus de la médiane DVF ({dvf.get('median_price_m2')} €/m²) — marge de négociation à activer")
        elif diff_pct <= 22:
            s_price = 48
            warnings.append(f"Bien surcoté (+{diff_pct}% vs DVF)")
        else:
            s_price = 28
            warnings.append(f"Forte surcote (+{diff_pct}% vs ventes réelles DVF du secteur)")
    else:
        s_price = 65

    max_budget = int(settings.get("max_budget") or 275000)
    target_budget = int(settings.get("target_budget") or 250000)
    if price > max_budget:
        dealbreakers.append(
            {
                "code": "BUDGET_MAX",
                "title": f"Budget dépassé ({price:,} € > {max_budget:,} €)".replace(",", " "),
                "detail": "Le prix affiché dépasse votre plafond défini (sauf forte négociation possible).",
            }
        )
        s_price = max(15, s_price - 20)
    elif price <= target_budget:
        strengths.append(f"Dans la cible budgétaire ({price:,} € ≤ {target_budget:,} €)".replace(",", " "))

    # --- 2. Mobilité Couple (Priorité Trajet Madame ≤ 40-45 min Astuce) (0-100) ---
    m_min = int(madame_mob.get("duration_min") or 0)
    m_max = int(settings.get("madame_max_transit_min") or 45)
    if m_min == 0:
        s_mob = 60
    elif m_min <= 22:
        s_mob = 96
        strengths.append(f"Trajet Madame top : {m_min} min en transport Astuce vers le 34 rue Cauchoise")
    elif m_min <= 32:
        s_mob = 88
        strengths.append(f"Trajet Madame très confortable : {m_min} min vers le 34 rue Cauchoise")
    elif m_min <= 40:
        s_mob = 76
    elif m_min <= m_max:
        s_mob = 62
        warnings.append(f"Trajet Madame proche de la limite : {m_min} min (max {m_max} min)")
    else:
        s_mob = max(10, 50 - (m_min - m_max) * 2)
        dealbreakers.append(
            {
                "code": "MADAME_TRANSIT",
                "title": f"Trajet Madame trop long ({m_min} min > {m_max} min)",
                "detail": madame_mob.get("best_itinerary", {}).get("details", "Dépasse le seuil de 40-45 min en transports Astuce."),
            }
        )

    # --- 3. Bâti, Terrain & Énergie (0-100) ---
    dpe_scores = {"A": 98, "B": 92, "C": 84, "D": 72, "E": 54, "F": 32, "G": 18}
    s_bati = dpe_scores.get(dpe, 65)
    if dpe in ("A", "B", "C"):
        strengths.append(f"Bonne performance énergétique (DPE {dpe})")
    elif dpe in ("F", "G"):
        warnings.append(f"Passoire thermique (DPE {dpe}) : prévoir enveloppe d'isolation / chauffage")

    min_bed = int(settings.get("min_bedrooms") or 2)
    if 0 < bedrooms < min_bed:
        dealbreakers.append(
            {
                "code": "MIN_BEDROOMS",
                "title": f"Nombre de chambres insuffisant ({bedrooms} < {min_bed})",
                "detail": f"Vous recherchez au minimum {min_bed} chambres.",
            }
        )
        s_bati = max(15, s_bati - 25)
    elif bedrooms >= 3:
        s_bati = min(100, s_bati + 6)
        strengths.append(f"{bedrooms} chambres (évolutif)")

    if "maison" in prop_type.lower():
        if land >= 300:
            s_bati = min(100, s_bati + 6)
            strengths.append(f"Beau terrain / jardin de {int(land)} m²")
        elif 0 < land < 80:
            warnings.append(f"Extérieur / parcelle très modeste ({int(land)} m²)")

    # --- 4. Risques & Sous-sol 76 (Marnières, Argiles, Inondation, Seveso) (0-100) ---
    s_risks = 90
    cav_100 = int(geo.get("cavites_100m_count") or 0)
    cav_500 = int(geo.get("cavites_500m_count") or 0)
    nearest_cav = geo.get("nearest_cavite_m")

    if cav_100 > 0:
        s_risks -= 45
        dealbreakers.append(
            {
                "code": "MARNIERE_100M",
                "title": f"Indice de cavité / marnière à {nearest_cav} m !",
                "detail": "Périmètre de sécurité marnière (Seine-Maritime) : vérifier impérativement le rapport géotechnique et le PLU en mairie.",
            }
        )
    elif cav_500 > 0:
        s_risks -= 15
        warnings.append(f"{cav_500} cavité(s)/marnière(s) recensée(s) dans un rayon de 500 m (plus proche à {nearest_cav} m)")
    else:
        strengths.append("Aucune marnière ou cavité souterraine recensée à proximité immédiate")

    rga_code = int(geo.get("argiles_code") or 0)
    if rga_code >= 3:
        s_risks -= 20
        warnings.append("Aléa FORT Retrait-Gonflement des Argiles (inspecter minutieusement les façades et fissures)")
    elif rga_code == 2:
        s_risks -= 8
        warnings.append("Aléa MOYEN Retrait-Gonflement des Argiles")

    if int(geo.get("seveso_count") or 0) > 0:
        s_risks -= 20
        warnings.append(f"{geo.get('seveso_count')} site(s) industriel(s) Seveso dans un rayon de 2 km")

    noise_list = osm.get("noise_sources", [])
    for ns in noise_list:
        if ns["distance_m"] <= 120:
            s_risks -= 15
            warnings.append(f"Nuisance sonore potentielle : {ns['type']} ({ns['name']}) à {ns['distance_m']} m")

    s_risks = max(10, min(100, s_risks))

    # --- 5. Quartier, Écoles & Commodités (0-100) ---
    s_neigh = 70
    poi_count = len(osm.get("supermarkets", [])) + len(osm.get("bakeries", [])) + len(osm.get("health", []))
    if poi_count >= 8:
        s_neigh += 15
        strengths.append("Quartier très commerçant (boulangeries, supermarchés et santé accessibles à pied)")
    elif poi_count >= 3:
        s_neigh += 8
    else:
        s_neigh -= 8

    avg_ips = schools.get("average_ips")
    if avg_ips:
        if avg_ips >= 115:
            s_neigh += 12
            strengths.append(f"Écoles du secteur très bien cotées (IPS moyen : {avg_ips})")
        elif avg_ips < 90:
            s_neigh -= 8
            warnings.append(f"Indice de Position Sociale (IPS) des écoles du secteur inférieur à la moyenne ({avg_ips})")

    s_neigh = max(20, min(100, s_neigh))

    # --- 6. Potentiel & Confort (Ensoleillement, PLU, Jardin) (0-100) ---
    s_comfort = 75
    if solar.get("available") and int(solar.get("yearly_irradiation_kwh_m2") or 0) >= 1150:
        s_comfort += 10
    if osm.get("parks_count", 0) >= 2:
        s_comfort += 8
    if int(finance.get("true_monthly_cost") or 0) <= 1150:
        s_comfort += 7
        strengths.append(f"Coût mensuel global maîtrisé ({finance.get('true_monthly_cost')} €/mois tout compris)")
    s_comfort = max(20, min(100, s_comfort))

    weights = settings.get("weights", {})
    w_price = float(weights.get("price_market", 25))
    w_mob = float(weights.get("mobility_madame", 25))
    w_bati = float(weights.get("building_energy", 18))
    w_risks = float(weights.get("risks_subsoil", 15))
    w_neigh = float(weights.get("neighborhood_schools", 10))
    w_comf = float(weights.get("comfort_potential", 7))
    w_sum = max(1.0, w_price + w_mob + w_bati + w_risks + w_neigh + w_comf)

    total_score = round(
        (
            s_price * w_price
            + s_mob * w_mob
            + s_bati * w_bati
            + s_risks * w_risks
            + s_neigh * w_neigh
            + s_comfort * w_comf
        )
        / w_sum
    )

    # Apply penalty if hard dealbreakers exist
    if dealbreakers:
        total_score = max(12, total_score - 12 * len(dealbreakers))

    return {
        "total_score": total_score,
        "verdict_badge": (
            "Pépite / Coup de cœur"
            if total_score >= 82 and not dealbreakers
            else (
                "Très bon candidat (À visiter)"
                if total_score >= 68 and not dealbreakers
                else ("À creuser / Négocier" if total_score >= 52 else "Vigilance / Alerte Rouge")
            )
        ),
        "axes": {
            "price_market": {"label": "Prix & Marché DVF", "score": s_price, "weight": w_price},
            "mobility_madame": {"label": "Trajet Madame (Astuce)", "score": s_mob, "weight": w_mob},
            "building_energy": {"label": "Bâti, Terrain & DPE", "score": s_bati, "weight": w_bati},
            "risks_subsoil": {"label": "Risques & Sous-sol 76", "score": s_risks, "weight": w_risks},
            "neighborhood_schools": {"label": "Quartier, Écoles & Commerces", "score": s_neigh, "weight": w_neigh},
            "comfort_potential": {"label": "Confort & Coût Mensuel", "score": s_comfort, "weight": w_comf},
        },
        "dealbreakers": dealbreakers,
        "warnings": warnings,
        "strengths": strengths,
    }
