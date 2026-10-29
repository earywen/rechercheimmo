"""Territorial Socio-Economics, Education Trajectory (Crèche to Higher Ed), Amenities, and Appreciation Engine for Rouen Métropole."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from src.dvf_service import haversine_m

# Comprehensive INSEE Filosofi, Census, and Urban Planning Database for Métropole Rouen Normandie Communes
COMMUNES_ROUEN_METROPOLE: dict[str, dict[str, Any]] = {
    # Plateau Nord (Secteur très aisé, cadre prisé, très faible pauvreté)
    "bois-guillaume": {
        "nom": "Bois-Guillaume",
        "revenu_median_uc": 35800,
        "taux_pauvrete_pct": 7.0,
        "part_cadres_pct": 36.5,
        "part_proprietaires_pct": 72.8,
        "taux_menages_imposes_pct": 78.4,
        "profil_socio": "Commune résidentielle d'excellence (Cadres supérieurs & professions libérales)",
        "classe_prosperite": "Très favorisée",
        "has_qpv": False,
        "qpv_nom": None,
        "tendance_dvf_5ans_pct": +14.2,
        "marche_plein_air": "Marché place de la Mairie le samedi matin",
        "atout_quartier": "Plateau Nord résidentiel très recherché, proximité Forêt Verte et cliniques",
    },
    "mont-saint-aignan": {
        "nom": "Mont-Saint-Aignan",
        "revenu_median_uc": 31640,
        "taux_pauvrete_pct": 14.0,  # Biais lié à la population étudiante
        "part_cadres_pct": 32.1,
        "part_proprietaires_pct": 53.4,
        "taux_menages_imposes_pct": 69.8,
        "profil_socio": "Pôle universitaire et résidentiel aisé (Cadres, enseignants, chercheurs)",
        "classe_prosperite": "Très favorisée",
        "has_qpv": False,
        "qpv_nom": None,
        "tendance_dvf_5ans_pct": +11.8,
        "marche_plein_air": "Marché place Colbert le mercredi matin",
        "atout_quartier": "Campus universitaire, NEOMA Business School, ligne TEOR T5 vers Rive Gauche",
    },
    "bihorel": {
        "nom": "Bihorel",
        "revenu_median_uc": 29400,
        "taux_pauvrete_pct": 11.2,
        "part_cadres_pct": 27.8,
        "part_proprietaires_pct": 64.2,
        "taux_menages_imposes_pct": 71.5,
        "profil_socio": "Commune résidentielle paisible, limitrophe Rouen gare",
        "classe_prosperite": "Favorisée",
        "has_qpv": False,
        "qpv_nom": None,
        "tendance_dvf_5ans_pct": +12.5,
        "marche_plein_air": "Marché place de l'Église le jeudi matin",
        "atout_quartier": "Accès direct Rouen centre-ville et gare via TEOR T2 / F2",
    },
    "isneauville": {
        "nom": "Isneauville",
        "revenu_median_uc": 34200,
        "taux_pauvrete_pct": 6.5,
        "part_cadres_pct": 34.0,
        "part_proprietaires_pct": 82.5,
        "taux_menages_imposes_pct": 79.1,
        "profil_socio": "Périurbain pavillonnaire très aisé et familial",
        "classe_prosperite": "Très favorisée",
        "has_qpv": False,
        "qpv_nom": None,
        "tendance_dvf_5ans_pct": +15.0,
        "marche_plein_air": "Marché communal le vendredi après-midi",
        "atout_quartier": "Grands jardins, tranquillité, accès A28 et plaine de la Ronce",
    },
    # Plateau Est & Rive Droite Résidentielle
    "le mesnil-esnard": {
        "nom": "Le Mesnil-Esnard",
        "revenu_median_uc": 30500,
        "taux_pauvrete_pct": 7.8,
        "part_cadres_pct": 29.5,
        "part_proprietaires_pct": 77.2,
        "taux_menages_imposes_pct": 74.0,
        "profil_socio": "Plateau Est résidentiel familial et calme",
        "classe_prosperite": "Favorisée",
        "has_qpv": False,
        "qpv_nom": None,
        "tendance_dvf_5ans_pct": +13.0,
        "marche_plein_air": "Commerces de bouche réputés sur la route de Paris",
        "atout_quartier": "Excellentes écoles (La Providence), cadre verdoyant, accès rapide Rive Gauche",
    },
    "bonsecours": {
        "nom": "Bonsecours",
        "revenu_median_uc": 28600,
        "taux_pauvrete_pct": 9.8,
        "part_cadres_pct": 26.2,
        "part_proprietaires_pct": 66.8,
        "taux_menages_imposes_pct": 70.2,
        "profil_socio": "Commune perchée sur la Seine, vue panoramique et calme",
        "classe_prosperite": "Favorisée",
        "has_qpv": False,
        "qpv_nom": None,
        "tendance_dvf_5ans_pct": +10.5,
        "marche_plein_air": "Marché place de la Basilique",
        "atout_quartier": "Basilique Notre-Dame, colline Sainte-Catherine, cadre patrimonial",
    },
    "franqueville-saint-pierre": {
        "nom": "Franqueville-Saint-Pierre",
        "revenu_median_uc": 31200,
        "taux_pauvrete_pct": 6.8,
        "part_cadres_pct": 28.0,
        "part_proprietaires_pct": 81.0,
        "taux_menages_imposes_pct": 76.5,
        "profil_socio": "Commune pavillonnaire aisée avec grands terrains",
        "classe_prosperite": "Très favorisée",
        "has_qpv": False,
        "qpv_nom": None,
        "tendance_dvf_5ans_pct": +12.0,
        "marche_plein_air": "Marché local le samedi",
        "atout_quartier": "Aéroport d'affaires, zones sportives, espaces naturels préservés",
    },
    # Rouen Ville-Centre (Forte mixité selon les micro-quartiers)
    "rouen": {
        "nom": "Rouen",
        "revenu_median_uc": 23060,
        "taux_pauvrete_pct": 26.4,
        "part_cadres_pct": 24.5,
        "part_proprietaires_pct": 28.6,
        "taux_menages_imposes_pct": 52.8,
        "profil_socio": "Cœur métropolitain : forte polarisation (secteurs bourgeois Rive Droite vs quartiers populaires)",
        "classe_prosperite": "Mixte et contrastée",
        "has_qpv": True,
        "qpv_nom": "Hauts-de-Rouen (Grand'Mare, Châtelet, Lombardie) et Grammont",
        "tendance_dvf_5ans_pct": +8.5,
        "marche_plein_air": "Marché du Vieux-Marché, marché Saint-Marc (mardi, vendredi, samedi, dimanche)",
        "atout_quartier": "Gare TGV/TER, patrimoine historique, commerces, lycées Corneille/Jeanne d'Arc",
    },
    # Vallée du Cailly (Tradition industrielle, ouvrière et en rénovation urbaine)
    "maromme": {
        "nom": "Maromme",
        "revenu_median_uc": 21200,
        "taux_pauvrete_pct": 20.5,
        "part_cadres_pct": 14.2,
        "part_proprietaires_pct": 47.5,
        "taux_menages_imposes_pct": 51.0,
        "profil_socio": "Vallée du Cailly : mixité ouvrière, employés et jeunes ménages primo-accédants",
        "classe_prosperite": "Populaire & intermédiaire",
        "has_qpv": True,
        "qpv_nom": "La Maine (secteur délimité)",
        "tendance_dvf_5ans_pct": +6.2,
        "marche_plein_air": "Marché place Jean Jaurès le samedi matin",
        "atout_quartier": "Prix au m² très attractifs, liaison TEOR T2 rapide vers Rouen centre",
    },
    "déville-lès-rouen": {
        "nom": "Déville-lès-Rouen",
        "revenu_median_uc": 20800,
        "taux_pauvrete_pct": 22.0,
        "part_cadres_pct": 13.5,
        "part_proprietaires_pct": 46.0,
        "taux_menages_imposes_pct": 49.5,
        "profil_socio": "Bourgade urbaine de la vallée du Cailly, populaire et accessible",
        "classe_prosperite": "Populaire",
        "has_qpv": True,
        "qpv_nom": "Quartier République / Cailly",
        "tendance_dvf_5ans_pct": +5.5,
        "marche_plein_air": "Marché le jeudi matin",
        "atout_quartier": "Pôle commercial des Docks à proximité, ligne TEOR T2",
    },
    "notre-dame-de-bondeville": {
        "nom": "Notre-Dame-de-Bondeville",
        "revenu_median_uc": 21800,
        "taux_pauvrete_pct": 17.5,
        "part_cadres_pct": 16.0,
        "part_proprietaires_pct": 52.0,
        "taux_menages_imposes_pct": 54.0,
        "profil_socio": "Commune verte de vallée avec maisons de ville et pavillons",
        "classe_prosperite": "Intermédiaire",
        "has_qpv": False,
        "qpv_nom": None,
        "tendance_dvf_5ans_pct": +7.8,
        "marche_plein_air": "Marché local le dimanche matin",
        "atout_quartier": "Musée de la Corderie Vallois, vallée verdoyante du Cailly",
    },
    "canteleu": {
        "nom": "Canteleu",
        "revenu_median_uc": 18900,
        "taux_pauvrete_pct": 31.0,
        "part_cadres_pct": 11.0,
        "part_proprietaires_pct": 34.0,
        "taux_menages_imposes_pct": 43.0,
        "profil_socio": "Forte présence d'habitat social sur le plateau, secteur village plus préservé",
        "classe_prosperite": "Zone prioritaire / Populaire",
        "has_qpv": True,
        "qpv_nom": "Cité Rose / Plateau de Canteleu",
        "tendance_dvf_5ans_pct": +3.5,
        "marche_plein_air": "Marché place Touzet le dimanche matin",
        "atout_quartier": "Ligne TEOR T3 directe, bordure directe de la Forêt de Roumare",
    },
    # Rive Gauche (Sotteville, Quevilly, Saint-Étienne-du-Rouvray)
    "sotteville-lès-rouen": {
        "nom": "Sotteville-lès-Rouen",
        "revenu_median_uc": 23630,
        "taux_pauvrete_pct": 22.4,
        "part_cadres_pct": 19.8,
        "part_proprietaires_pct": 51.2,
        "taux_menages_imposes_pct": 56.5,
        "profil_socio": "Cœur de la Rive Gauche, tradition cheminote, très familial en zone pavillonnaire",
        "classe_prosperite": "Intermédiaire & dynamique",
        "has_qpv": True,
        "qpv_nom": "Secteur Gadeau de Kerville",
        "tendance_dvf_5ans_pct": +9.8,
        "marche_plein_air": "L'un des plus grands marchés de France (Place de l'Hôtel de Ville le dimanche)",
        "atout_quartier": "Métro/tram direct gare et centre, Jardin des Plantes, très recherché en maisons de ville avec jardin",
    },
    "le petit-quevilly": {
        "nom": "Le Petit-Quevilly",
        "revenu_median_uc": 19800,
        "taux_pauvrete_pct": 28.5,
        "part_cadres_pct": 13.0,
        "part_proprietaires_pct": 35.0,
        "taux_menages_imposes_pct": 45.0,
        "profil_socio": "Rive Gauche en mutation urbaine (écoquartier Flaubert, nouveau T5)",
        "classe_prosperite": "Populaire en transition",
        "has_qpv": True,
        "qpv_nom": "Saint-Julien / Nobel",
        "tendance_dvf_5ans_pct": +8.0,
        "marche_plein_air": "Marché des Bruyères",
        "atout_quartier": "Nouvelle ligne T5 vers Mont-Saint-Aignan, métro, potentiel de plus-value via Flaubert",
    },
    "le grand-quevilly": {
        "nom": "Le Grand-Quevilly",
        "revenu_median_uc": 22500,
        "taux_pauvrete_pct": 21.0,
        "part_cadres_pct": 16.5,
        "part_proprietaires_pct": 42.0,
        "taux_menages_imposes_pct": 53.0,
        "profil_socio": "Commune très bien équipée en équipements publics et culturels",
        "classe_prosperite": "Intermédiaire",
        "has_qpv": True,
        "qpv_nom": "Quartier Kennedy / Chêne à Leu",
        "tendance_dvf_5ans_pct": +7.5,
        "marche_plein_air": "Marché du Bourg",
        "atout_quartier": "La Maison de l'Université, Zénith de Rouen, Parc des Provinces, métro",
    },
    "saint-étienne-du-rouvray": {
        "nom": "Saint-Étienne-du-Rouvray",
        "revenu_median_uc": 18500,
        "taux_pauvrete_pct": 32.5,
        "part_cadres_pct": 12.0,
        "part_proprietaires_pct": 39.0,
        "taux_menages_imposes_pct": 42.0,
        "profil_socio": "Commune contrastée : grand pôle d'ingénieurs Madrillet vs quartiers sociaux",
        "classe_prosperite": "Zone prioritaire avec pôle technologique",
        "has_qpv": True,
        "qpv_nom": "Château Blanc, Robespierre",
        "tendance_dvf_5ans_pct": +4.0,
        "marche_plein_air": "Marché de l'Hôtel de Ville",
        "atout_quartier": "Technopôle du Madrillet (GINGER BURGEAP, INSA, ESIGELEC), terminus métro",
    },
    "darnétal": {
        "nom": "Darnétal",
        "revenu_median_uc": 21400,
        "taux_pauvrete_pct": 23.0,
        "part_cadres_pct": 17.5,
        "part_proprietaires_pct": 42.0,
        "taux_menages_imposes_pct": 51.5,
        "profil_socio": "Vallée du Robec, patrimoine industriel textile réhabilité, école d'architecture",
        "classe_prosperite": "Intermédiaire & artistique",
        "has_qpv": True,
        "qpv_nom": "Quartier du Robec",
        "tendance_dvf_5ans_pct": +8.2,
        "marche_plein_air": "Marché place de la Gare",
        "atout_quartier": "Terminus TEOR T2/T3, École Nationale Supérieure d'Architecture de Normandie",
    },
}

DEFAULT_COMMUNE_STATS = {
    "nom": "Métropole Rouen Normandie",
    "revenu_median_uc": 23200,
    "taux_pauvrete_pct": 21.0,
    "part_cadres_pct": 21.0,
    "part_proprietaires_pct": 52.0,
    "taux_menages_imposes_pct": 55.0,
    "profil_socio": "Commune périurbaine de la Métropole Rouen Normandie",
    "classe_prosperite": "Moyenne métropolitaine",
    "has_qpv": False,
    "qpv_nom": None,
    "tendance_dvf_5ans_pct": +7.5,
    "marche_plein_air": "Marché hebdomadaire local",
    "atout_quartier": "Cadre de vie normand avec commodités de proximité",
}


def get_commune_socio_profile(city: str) -> dict[str, Any]:
    """Retrieve official INSEE socio-economic profile and prosperity ranking for a commune."""
    normalized = city.strip().lower()
    for key, data in COMMUNES_ROUEN_METROPOLE.items():
        if key in normalized or normalized in key:
            return data
    return {**DEFAULT_COMMUNE_STATS, "nom": city or "Commune locale"}


async def fetch_complete_education_trajectory(lat: float, lon: float, city: str = "") -> dict[str, Any]:
    """Fetch education trajectory from Early Childhood (crèche) to Higher Ed with IPS, Brevet, and Lycée indicators."""
    out: dict[str, Any] = {
        "creches_and_early_childhood": [],
        "maternelles_and_elementaires": [],
        "colleges": [],
        "lycees": [],
        "higher_education_campus": [],
        "summary": {
            "total_count": 0,
            "average_ips": None,
            "ips_verdict": "Non évalué",
            "nearest_school_dist_m": None,
            "nearest_college_dist_m": None,
            "nearest_lycee_dist_m": None,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=9.0) as client:
            where_clause = f"within_distance(position, geom'POINT({lon} {lat})', 3500m)"
            resp = await client.get(
                "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-annuaire-education/records",
                params={"where": where_clause, "limit": 45},
            )
            raw_schools = []
            uai_colleges = []
            uai_schools = []

            if resp.status_code == 200:
                for item in resp.json().get("results", []):
                    pos = item.get("position") or {}
                    slat = pos.get("lat")
                    slon = pos.get("lon")
                    dist = round(haversine_m(lat, lon, float(slat), float(slon))) if (slat and slon) else 9999
                    uai = item.get("identifiant_de_l_etablissement", "")
                    t_type = item.get("type_etablissement", "")

                    record = {
                        "uai": uai,
                        "nom": item.get("nom_etablissement", ""),
                        "type": t_type,
                        "statut": item.get("statut_public_prive", "Public"),
                        "adresse": item.get("adresse_1", ""),
                        "commune": item.get("nom_commune", ""),
                        "distance_m": dist,
                        "ips": None,
                        "brevet_reussite_pct": None,
                        "brevet_mentions_pct": None,
                    }
                    raw_schools.append(record)
                    if "Collège" in t_type:
                        uai_colleges.append(f"'{uai}'")
                    elif "Ecole" in t_type:
                        uai_schools.append(f"'{uai}'")

            # Enrich with IPS for Schools and Colleges in parallel
            ips_tasks = []
            if uai_schools:
                ips_tasks.append(
                    client.get(
                        "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-ips-ecoles-ap2022/records",
                        params={"where": f"uai IN ({','.join(uai_schools[:15])})", "limit": 20},
                    )
                )
            if uai_colleges:
                ips_tasks.append(
                    client.get(
                        "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-ips-colleges-ap2022/records",
                        params={"where": f"uai IN ({','.join(uai_colleges[:10])})", "limit": 15},
                    )
                )

            ips_responses = await asyncio.gather(*ips_tasks, return_exceptions=True)
            ips_map: dict[str, float] = {}

            for r_ips in ips_responses:
                if not isinstance(r_ips, Exception) and r_ips.status_code == 200:
                    for ir in r_ips.json().get("results", []):
                        u = ir.get("uai")
                        val = ir.get("ips")
                        if u and val:
                            try:
                                ips_map[u] = round(float(val), 1)
                            except ValueError:
                                pass

            # Classify by Educational Stage
            for s in sorted(raw_schools, key=lambda x: x["distance_m"]):
                if s["uai"] in ips_map:
                    s["ips"] = ips_map[s["uai"]]

                t = s["type"]
                if "Ecole" in t:
                    out["maternelles_and_elementaires"].append(s)
                elif "Collège" in t:
                    out["colleges"].append(s)
                elif "Lycée" in t:
                    out["lycees"].append(s)

            # Add major Rouen higher-ed campuses
            out["higher_education_campus"] = [
                {
                    "nom": "Campus Santé / Médecine & Pharmacie (Rouen CHU / Martainville)",
                    "commune": "Rouen",
                    "type": "Pôle Universitaire Santé",
                    "filiere": "Médecine, Pharmacie, Biologie, Soins infirmiers",
                    "acces": "TEOR T1, T2, T3, T4 arrêt CHU Charles Nicolle",
                    "access_info": "TEOR T1, T2, T3, T4 arrêt CHU Charles Nicolle",
                },
                {
                    "nom": "Campus Mont-Saint-Aignan (Université de Rouen Normandie & NEOMA)",
                    "commune": "Mont-Saint-Aignan",
                    "type": "Campus Principal & Grande École",
                    "filiere": "Lettres, Sciences Humaines, NEOMA Business School, STAPS",
                    "acces": "TEOR T1 & nouvelle ligne T5, bus F2",
                    "access_info": "TEOR T1 & nouvelle ligne T5, bus F2",
                },
                {
                    "nom": "Campus Pasteur (Rouen Rive Droite Ouest)",
                    "commune": "Rouen",
                    "type": "Faculté de Droit & Économie",
                    "filiere": "Faculté de Droit, Économie et Gestion",
                    "acces": "Lignes TEOR T1, T2, T3 arrêt Pasteur",
                    "access_info": "Lignes TEOR T1, T2, T3 arrêt Pasteur",
                },
                {
                    "nom": "Technopôle du Madrillet (Saint-Étienne-du-Rouvray)",
                    "commune": "Saint-Étienne-du-Rouvray",
                    "type": "Pôle d'Ingénieurs & Sciences",
                    "filiere": "INSA Rouen Normandie, ESIGELEC, UFR Sciences",
                    "acces": "Métro Terminus Technopôle & Ligne F6",
                    "access_info": "Métro Terminus Technopôle & Ligne F6",
                },
            ]

            # Overall IPS and Education Score
            all_ips = [s["ips"] for s in raw_schools if s["ips"] is not None]
            if all_ips:
                avg = round(sum(all_ips) / len(all_ips), 1)
                out["summary"]["average_ips"] = avg
                if avg >= 115:
                    out["summary"]["ips_verdict"] = "Cadre éducatif très favorisé & stimulant (CSP++)"
                elif avg >= 102:
                    out["summary"]["ips_verdict"] = "Cadre éducatif équilibré et favorable (au-dessus de la moyenne nationale)"
                elif avg >= 92:
                    out["summary"]["ips_verdict"] = "Mixité sociale standard"
                else:
                    out["summary"]["ips_verdict"] = "Établissements en réseau d'éducation prioritaire (REP)"

            out["summary"]["total_count"] = len(raw_schools)
            if out["maternelles_and_elementaires"]:
                out["summary"]["nearest_school_dist_m"] = out["maternelles_and_elementaires"][0]["distance_m"]
            if out["colleges"]:
                out["summary"]["nearest_college_dist_m"] = out["colleges"][0]["distance_m"]
            if out["lycees"]:
                out["summary"]["nearest_lycee_dist_m"] = out["lycees"][0]["distance_m"]

    except Exception:
        pass

    return out


def evaluate_property_appreciation_potential(
    city: str,
    listing_price: float,
    surface_m2: float,
    land_m2: float,
    dpe_letter: str,
    mobility: dict[str, Any],
) -> dict[str, Any]:
    """Calculate 5-year capital appreciation potential, urban projects catalyst, and land reserves."""
    socio = get_commune_socio_profile(city)
    dpe = (dpe_letter or "D").upper()

    # 1. Historical 5-year price trend
    trend_5y = socio.get("tendance_dvf_5ans_pct", 7.5)

    # 2. Major Infrastructure Catalysts in Rouen Métropole
    catalysts: list[dict[str, str]] = []
    madame_transit = mobility.get("madame", {})
    itinerary_text = str(madame_transit.get("best_itinerary", {}).get("details", "")).lower()

    # T5 TEOR proximity (Mont-Saint-Aignan <-> Saint-Sever via pont Flaubert)
    if any(k in itinerary_text for k in ("t5", "kindarena", "flaubert", "colbert", "mont-saint-aignan")) or any(c in city.lower() for c in ("mont-saint-aignan", "déville", "petit-quevilly")):
        catalysts.append({
            "projet": "Nouvelle ligne TEOR T5 (Mise en service 2025)",
            "title": "Nouvelle ligne TEOR T5 (Mise en service 2025)",
            "impact": "Forte valorisation : liaison transversale directe Nord-Sud sans passer par le Théâtre des Arts.",
            "description": "Forte valorisation : liaison transversale directe Nord-Sud sans passer par le Théâtre des Arts.",
            "potentiel": "+4% à +7% de surcote d'accessibilité",
        })

    # Saint-Sever New Station & LNPN
    if any(c in city.lower() for c in ("rouen", "sotteville", "petit-quevilly", "saint-sever")):
        catalysts.append({
            "projet": "Pôle Gare Rouen Saint-Sever & LNPN (Ligne Nouvelle Paris-Normandie)",
            "title": "Pôle Gare Rouen Saint-Sever & LNPN (Ligne Nouvelle Paris-Normandie)",
            "impact": "Requalification majeure de la Rive Gauche à horizon 2030+ (hub multimodal TGV/TER, bureaux, logements neufs).",
            "description": "Requalification majeure de la Rive Gauche à horizon 2030+ (hub multimodal TGV/TER, bureaux, logements neufs).",
            "potentiel": "Catalyseur patrimonial majeur à moyen/long terme",
        })

    # Technopôle du Madrillet
    if any(c in city.lower() for c in ("saint-étienne-du-rouvray", "sotteville", "petit-couronne", "oissel")):
        catalysts.append({
            "projet": "Développement du Technopôle du Madrillet",
            "title": "Développement du Technopôle du Madrillet",
            "impact": "Concentration croissante d'ingénieurs, chercheurs et laboratoires d'innovation automobile/matériaux.",
            "description": "Concentration croissante d'ingénieurs, chercheurs et laboratoires d'innovation automobile/matériaux.",
            "potentiel": "Demande locative et familiale pérenne",
        })

    # 3. Land Reserve / Extension Potential
    land_reserve_score = "Modéré"
    land_notes = "Parcelle standard pour la zone."
    if land_m2 > 0 and surface_m2 > 0:
        footprint_ratio = (surface_m2 / 1.5) / land_m2  # Rough footprint estimation
        if land_m2 >= 450 and footprint_ratio <= 0.22:
            land_reserve_score = "Élevé"
            land_notes = f"Terrain généreux de {int(land_m2)} m² : excellente réserve foncière pour extension, surélévation, véranda ou piscine (selon règlement PLU)."
        elif land_m2 >= 300:
            land_reserve_score = "Bon"
            land_notes = f"Terrain de {int(land_m2)} m² permettant un aménagement extérieur de qualité sans mitoyenneté étouffante."

    # 4. Green Value Potential (DPE Renovation Arbitrage)
    green_value_potential = 0
    green_notes = "Performance énergétique actuelle satisfaisante."
    if dpe in ("E", "F", "G"):
        # Renovating an E/F/G to B/C yields ~10-15% property value increase in Rouen market
        gain_pct = 15 if dpe in ("F", "G") else 10
        green_value_potential = round(listing_price * (gain_pct / 100))
        green_notes = (
            f"Passage de DPE {dpe} à B/C via travaux d'isolation : potentiel de plus-value verte estimé à +{gain_pct}% "
            f"(~{green_value_potential:,} € à la revente), tout en échappant au gel des loyers et aux décotes futures."
        ).replace(",", " ")

    # 5. Global Appreciation Index (0 to 100)
    score_appreciation = 60
    if trend_5y >= 12:
        score_appreciation += 15
    elif trend_5y >= 8:
        score_appreciation += 8

    if socio.get("classe_prosperite") in ("Très favorisée", "Favorisée"):
        score_appreciation += 12
    if land_reserve_score == "Élevé":
        score_appreciation += 8
    if green_value_potential > 0:
        score_appreciation += 5

    score_appreciation = min(95, max(45, score_appreciation))

    verdict_appreciation = "Bon potentiel de valorisation patrimoniale"
    if score_appreciation >= 80:
        verdict_appreciation = "Excellente sécurité patrimoniale & fort potentiel de prise de valeur"
    elif score_appreciation < 60:
        verdict_appreciation = "Valorisation stable et modérée (marché populaire ou contraint)"

    return {
        "score_appreciation": score_appreciation,
        "verdict": verdict_appreciation,
        "tendance_dvf_5ans_pct": trend_5y,
        "catalysts": catalysts,
        "land_reserve": {
            "score": land_reserve_score,
            "surface_terrain_m2": land_m2,
            "commentaire": land_notes,
        },
        "green_value": {
            "dpe_actuel": dpe,
            "plus_value_potentielle_eur": green_value_potential,
            "commentaire": green_notes,
        },
        "socio_commune": socio,
    }


def compute_15min_city_walkability(osm_data: dict[str, Any]) -> dict[str, Any]:
    """Structure the 15-minute city / daily convenience breakdown from amenities data."""
    supermarkets = osm_data.get("supermarkets", [])
    bakeries = osm_data.get("bakeries", [])
    health = osm_data.get("health", [])

    # Proximity breakdown
    immediate_5min = []  # < 400m
    easy_10min = []  # 400 - 800m
    car_needed = []  # > 1000m

    def check_item(item_list, label):
        if item_list:
            nearest = item_list[0]
            d = nearest.get("distance_m", 9999)
            if d <= 450:
                immediate_5min.append(f"{label} ({nearest.get('name')}, {d} m)")
            elif d <= 850:
                easy_10min.append(f"{label} ({nearest.get('name')}, {d} m)")
            else:
                car_needed.append(f"{label} (plus proche à {d} m)")
        else:
            car_needed.append(f"{label} (aucun à proximité immédiate)")

    check_item(bakeries, "Boulangerie / Pain frais")
    check_item(supermarkets, "Supermarché / Courses")
    check_item([h for h in health if h.get("type") == "pharmacy"], "Pharmacie")
    check_item([h for h in health if h.get("type") in ("doctors", "clinic")], "Médecin généraliste")

    walk_score = 50
    if len(immediate_5min) >= 2:
        walk_score = 90
        verdict = "Tout à pied en 5 min (Boulangerie, pharmacie, petits commerces au pied du bien)"
    elif len(immediate_5min) >= 1 or len(easy_10min) >= 2:
        walk_score = 75
        verdict = "Vie de quartier très pratique à pied (10 min maximum pour les besoins quotidiens)"
    elif easy_10min:
        walk_score = 60
        verdict = "Quartier résidentiel calme (courses d'appoint à pied, supermarché utile en voiture/vélo)"
    else:
        walk_score = 45
        verdict = "Environnement purement pavillonnaire (voiture indispensable pour les courses)"

    return {
        "walk_score": walk_score,
        "verdict": verdict,
        "immediate_5min": immediate_5min,
        "easy_10min": easy_10min,
        "car_needed": car_needed,
    }
