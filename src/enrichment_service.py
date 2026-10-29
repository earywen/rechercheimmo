"""Open Data Enrichment Pipeline (BAN, Cadastre IGN, Géorisques 76, ADEME DPE, Écoles & IPS, PVGIS, Overpass OSM)."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from src.dvf_service import analyze_dvf_around, haversine_m
from src.mobility_service import compute_mobility
from src.neighborhood_service import (
    compute_15min_city_walkability,
    evaluate_property_appreciation_potential,
    fetch_complete_education_trajectory,
    get_commune_socio_profile,
)


async def geocode_address(address: str, postcode: str = "", city: str = "") -> dict[str, Any]:
    """Resolve an address via the French Base Adresse Nationale (BAN)."""
    q = address.strip()
    if postcode and postcode not in q:
        q = f"{q} {postcode}"
    if city and city.lower() not in q.lower():
        q = f"{q} {city}"

    if not q:
        return {"found": False}

    params: dict[str, Any] = {"q": q, "limit": 5}
    if postcode and len(postcode.strip()) == 5:
        params["postcode"] = postcode.strip()

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get("https://api-adresse.data.gouv.fr/search/", params=params)
            if resp.status_code != 200 and "postcode" in params:
                del params["postcode"]
                resp = await client.get("https://api-adresse.data.gouv.fr/search/", params=params)
            if resp.status_code == 200:
                features = resp.json().get("features", [])
                if not features and "postcode" in params:
                    del params["postcode"]
                    resp2 = await client.get("https://api-adresse.data.gouv.fr/search/", params=params)
                    features = resp2.json().get("features", [])
                if features:
                    top = features[0]
                    lon, lat = top["geometry"]["coordinates"]
                    props = top.get("properties", {})
                    return {
                        "found": True,
                        "label": props.get("label", q),
                        "score": round(float(props.get("score", 0)), 2),
                        "type": props.get("type", "housenumber"),
                        "postcode": props.get("postcode", postcode),
                        "city": props.get("city", city),
                        "citycode": props.get("citycode", ""),
                        "street": props.get("street") or props.get("name", ""),
                        "housenumber": props.get("housenumber", ""),
                        "lat": float(lat),
                        "lon": float(lon),
                        "candidates": [
                            {
                                "label": f["properties"].get("label"),
                                "lat": f["geometry"]["coordinates"][1],
                                "lon": f["geometry"]["coordinates"][0],
                                "type": f["properties"].get("type"),
                            }
                            for f in features[:4]
                        ],
                    }
    except Exception:
        pass
    return {"found": False}


async def detective_dpe_lookup(
    postcode: str,
    surface_m2: float = 0,
    dpe_letter: str = "",
    ges_letter: str = "",
    construction_year: int = 0,
    property_type: str = "Maison",
) -> list[dict[str, Any]]:
    """Reverse-engineer exact property address from ADEME DPE Open Data when only postal code + DPE/surface are known."""
    if not postcode:
        return []

    qs_parts = [f"code_postal_ban:{postcode.strip()}"]
    if dpe_letter and dpe_letter.upper() in "ABCDEFG":
        qs_parts.append(f"etiquette_dpe:{dpe_letter.upper()}")
    if ges_letter and ges_letter.upper() in "ABCDEFG":
        qs_parts.append(f"etiquette_ges:{ges_letter.upper()}")
    if property_type:
        btype = "maison" if "maison" in property_type.lower() else "appartement"
        qs_parts.append(f"type_batiment:{btype}")
    if surface_m2 > 15:
        low_s = max(10, int(surface_m2 - 12))
        high_s = int(surface_m2 + 12)
        qs_parts.append(f"surface_habitable_logement:[{low_s} TO {high_s}]")

    qs = " AND ".join(qs_parts)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines",
                params={"size": 15, "qs": qs},
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                candidates = []
                for r in results:
                    addr = r.get("adresse_ban") or f"{r.get('numero_voie_ban', '')} {r.get('nom_rue_ban', '')} {r.get('code_postal_ban', '')} {r.get('nom_commune_ban', '')}".strip()
                    surf = float(r.get("surface_habitable_logement") or 0)
                    yr = r.get("annee_construction") or r.get("periode_construction") or ""
                    diff_s = abs(surf - surface_m2) if surface_m2 else 0
                    candidates.append(
                        {
                            "numero_dpe": r.get("numero_dpe"),
                            "date_etablissement_dpe": r.get("date_etablissement_dpe"),
                            "address": addr,
                            "postcode": r.get("code_postal_ban", postcode),
                            "city": r.get("nom_commune_ban", ""),
                            "surface_m2": surf,
                            "surface_diff": round(diff_s, 1),
                            "dpe": r.get("etiquette_dpe"),
                            "ges": r.get("etiquette_ges"),
                            "conso_kwh_m2_an": r.get("conso_5_usages_par_m2_ep"),
                            "cout_total_5_usages": r.get("cout_total_5_usages"),
                            "construction_year": yr,
                            "type_energie_chauffage": r.get("type_energie_principale_chauffage"),
                            "type_generateur_chauffage": r.get("type_generateur_n1_installation_n1"),
                            "qualite_isolation_enveloppe": r.get("qualite_isolation_enveloppe"),
                            "qualite_isolation_murs": r.get("qualite_isolation_murs"),
                            "qualite_isolation_menuiseries": r.get("qualite_isolation_menuiseries"),
                        }
                    )
                candidates.sort(key=lambda x: x["surface_diff"])
                return candidates[:8]
    except Exception:
        pass
    return []


async def fetch_cadastre_and_plu(lat: float, lon: float) -> dict[str, Any]:
    """Fetch exact cadastral parcel & urbanism zone from IGN APICarto."""
    geom_str = json.dumps({"type": "Point", "coordinates": [lon, lat]})
    out: dict[str, Any] = {
        "parcel_found": False,
        "parcel_id": "",
        "section": "",
        "numero": "",
        "contenance_m2": 0,
        "commune": "",
        "parcel_geometry": None,
        "plu_zone": "",
        "plu_libelle": "",
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r_cad = await client.get("https://apicarto.ign.fr/api/cadastre/parcelle", params={"geom": geom_str})
            if r_cad.status_code == 200:
                feats = r_cad.json().get("features", [])
                if feats:
                    f0 = feats[0]
                    props = f0.get("properties", {})
                    out.update(
                        {
                            "parcel_found": True,
                            "parcel_id": props.get("idu", ""),
                            "section": props.get("section", ""),
                            "numero": props.get("numero", ""),
                            "contenance_m2": int(props.get("contenance") or 0),
                            "commune": props.get("nom_com", ""),
                            "parcel_geometry": f0.get("geometry"),
                        }
                    )
            r_gpu = await client.get("https://apicarto.ign.fr/api/gpu/zone-urba", params={"geom": geom_str})
            if r_gpu.status_code == 200:
                gfeats = r_gpu.json().get("features", [])
                if gfeats:
                    gprops = gfeats[0].get("properties", {})
                    out["plu_zone"] = gprops.get("libelle", "")
                    out["plu_libelle"] = gprops.get("libelong", "") or gprops.get("typezone", "")
    except Exception:
        pass
    return out


async def fetch_georisques(lat: float, lon: float, citycode: str = "") -> dict[str, Any]:
    """Fetch comprehensive risk profile from Géorisques API, with special focus on 76 Marnières/Cavités & Seveso."""
    latlon = f"{lon},{lat}"
    out: dict[str, Any] = {
        "argiles_exposition": "Non renseigné",
        "argiles_code": 0,
        "radon_classe": 1,
        "cavites_500m_count": 0,
        "cavites_100m_count": 0,
        "nearest_cavite_m": None,
        "cavites_list": [],
        "icpe_1km_count": 0,
        "seveso_count": 0,
        "icpe_list": [],
        "inondation_risque": False,
        "risques_commune": [],
        "catnat_count": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            tasks = [
                client.get("https://georisques.gouv.fr/api/v1/rga", params={"latlon": latlon}),
                client.get("https://georisques.gouv.fr/api/v1/cavites", params={"latlon": latlon, "rayon": 1000}),
                client.get("https://georisques.gouv.fr/api/v1/installations_classees", params={"latlon": latlon, "rayon": 1500}),
                client.get("https://georisques.gouv.fr/api/v1/gaspar/risques", params={"latlon": latlon, "rayon": 1000}),
            ]
            if citycode:
                tasks.append(client.get("https://georisques.gouv.fr/api/v1/radon", params={"code_insee": citycode}))
                tasks.append(client.get("https://georisques.gouv.fr/api/v1/gaspar/catnat", params={"code_insee": citycode, "page_size": 20}))

            resps = await asyncio.gather(*tasks, return_exceptions=True)

            # 1. RGA (Retrait-Gonflement des Argiles)
            if not isinstance(resps[0], Exception) and resps[0].status_code == 200:
                d_rga = resps[0].json()
                out["argiles_exposition"] = d_rga.get("exposition", "Faible")
                try:
                    out["argiles_code"] = int(d_rga.get("codeExposition") or 0)
                except ValueError:
                    pass

            # 2. Cavités souterraines & Marnières (crucial in 76)
            if not isinstance(resps[1], Exception) and resps[1].status_code == 200:
                d_cav = resps[1].json().get("data", [])
                cav_items = []
                for c in d_cav:
                    clat = c.get("latitude")
                    clon = c.get("longitude")
                    if clat and clon:
                        dist = round(haversine_m(lat, lon, float(clat), float(clon)))
                        cav_items.append(
                            {
                                "id": c.get("identifiant"),
                                "type": c.get("type", "Cavité / Marnière"),
                                "nom": c.get("nom", ""),
                                "distance_m": dist,
                                "lat": float(clat),
                                "lon": float(clon),
                            }
                        )
                cav_items.sort(key=lambda x: x["distance_m"])
                out["cavites_list"] = cav_items[:12]
                out["cavites_500m_count"] = sum(1 for x in cav_items if x["distance_m"] <= 500)
                out["cavites_100m_count"] = sum(1 for x in cav_items if x["distance_m"] <= 120)
                if cav_items:
                    out["nearest_cavite_m"] = cav_items[0]["distance_m"]

            # 3. ICPE & Seveso
            if not isinstance(resps[2], Exception) and resps[2].status_code == 200:
                d_icpe = resps[2].json().get("data", [])
                icpe_items = []
                for ic in d_icpe:
                    ilat = ic.get("latitude")
                    ilon = ic.get("longitude")
                    dist = round(haversine_m(lat, lon, float(ilat), float(ilon))) if (ilat and ilon) else 9999
                    statut_seveso = str(ic.get("statutSeveso") or "")
                    is_seveso = "seveso" in statut_seveso.lower() and "non" not in statut_seveso.lower()
                    icpe_items.append(
                        {
                            "nom": ic.get("raisonSociale", "Installation classée"),
                            "regime": ic.get("regime", ""),
                            "seveso": statut_seveso or "Non Seveso",
                            "is_seveso": is_seveso,
                            "distance_m": dist,
                        }
                    )
                icpe_items.sort(key=lambda x: x["distance_m"])
                out["icpe_list"] = icpe_items[:10]
                out["icpe_1km_count"] = sum(1 for x in icpe_items if x["distance_m"] <= 1000)
                out["seveso_count"] = sum(1 for x in icpe_items if x["is_seveso"] and x["distance_m"] <= 2000)

            # 4. GASPAR Risques (Inondation, PPRI, etc.)
            if not isinstance(resps[3], Exception) and resps[3].status_code == 200:
                d_gas = resps[3].json().get("data", [])
                r_labels: list[str] = []
                for item in d_gas:
                    for rd in item.get("risques_detail", []):
                        lbl = rd.get("libelle_risque_long", "")
                        if lbl and lbl not in r_labels:
                            r_labels.append(lbl)
                out["risques_commune"] = r_labels
                out["inondation_risque"] = any("inondation" in l.lower() for l in r_labels)

            # 5. Radon & CatNat
            if len(resps) > 4 and not isinstance(resps[4], Exception) and resps[4].status_code == 200:
                d_rad = resps[4].json().get("data", [])
                if d_rad:
                    out["radon_classe"] = int(d_rad[0].get("classe_potentiel") or 1)
            if len(resps) > 5 and not isinstance(resps[5], Exception) and resps[5].status_code == 200:
                out["catnat_count"] = int(resps[5].json().get("results") or 0)
    except Exception:
        pass
    return out


async def fetch_ademe_dpe_for_address(
    address_label: str,
    postcode: str,
    surface_m2: float = 0,
    dpe_letter: str = "",
) -> dict[str, Any]:
    """Find matching DPE record(s) at or near the given address."""
    if not postcode:
        return {"found": False, "records": []}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            # Query by address text first
            resp = await client.get(
                "https://data.ademe.fr/data-fair/api/v1/datasets/dpe03existant/lines",
                params={"size": 10, "q": address_label, "qs": f"code_postal_ban:{postcode}"},
            )
            records = []
            if resp.status_code == 200:
                records = resp.json().get("results", [])

            if not records:
                # Fallback to detective match on postcode + surface + dpe
                det = await detective_dpe_lookup(postcode=postcode, surface_m2=surface_m2, dpe_letter=dpe_letter)
                return {"found": bool(det), "exact_address_match": False, "records": det[:5]}

            formatted = []
            for r in records[:5]:
                formatted.append(
                    {
                        "numero_dpe": r.get("numero_dpe"),
                        "date_etablissement_dpe": r.get("date_etablissement_dpe"),
                        "address": r.get("adresse_ban"),
                        "surface_m2": r.get("surface_habitable_logement"),
                        "dpe": r.get("etiquette_dpe"),
                        "ges": r.get("etiquette_ges"),
                        "conso_kwh_m2_an": r.get("conso_5_usages_par_m2_ep"),
                        "cout_total_5_usages": r.get("cout_total_5_usages"),
                        "cout_chauffage": r.get("cout_chauffage"),
                        "construction_year": r.get("annee_construction") or r.get("periode_construction"),
                        "type_energie_chauffage": r.get("type_energie_principale_chauffage"),
                        "type_generateur_chauffage": r.get("type_generateur_n1_installation_n1"),
                        "qualite_isolation_enveloppe": r.get("qualite_isolation_enveloppe"),
                        "qualite_isolation_murs": r.get("qualite_isolation_murs"),
                        "qualite_isolation_menuiseries": r.get("qualite_isolation_menuiseries"),
                        "qualite_isolation_plancher_haut": r.get("qualite_isolation_plancher_haut_comble_amena") or r.get("qualite_isolation_plancher_haut_comble_perdu"),
                    }
                )
            return {"found": True, "exact_address_match": True, "records": formatted}
    except Exception:
        return {"found": False, "records": []}


async def fetch_schools_and_ips(lat: float, lon: float, city: str = "") -> dict[str, Any]:
    """Fetch nearby schools (maternelle, élémentaire, collège, lycée) & Social Position Index (IPS)."""
    out: dict[str, Any] = {"count": 0, "schools": [], "average_ips": None}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            where_clause = f"within_distance(position, geom'POINT({lon} {lat})', 2000m)"
            r_sch = await client.get(
                "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-annuaire-education/records",
                params={"where": where_clause, "limit": 25},
            )
            schools_list = []
            uai_list = []
            if r_sch.status_code == 200:
                for s in r_sch.json().get("results", []):
                    pos = s.get("position") or {}
                    slat = pos.get("lat")
                    slon = pos.get("lon")
                    dist = round(haversine_m(lat, lon, float(slat), float(slon))) if (slat and slon) else 9999
                    uai = s.get("identifiant_de_l_etablissement", "")
                    if uai:
                        uai_list.append(f"'{uai}'")
                    schools_list.append(
                        {
                            "uai": uai,
                            "nom": s.get("nom_etablissement", ""),
                            "type": s.get("type_etablissement", ""),
                            "statut": s.get("statut_public_prive", ""),
                            "adresse": s.get("adresse_1", ""),
                            "commune": s.get("nom_commune", ""),
                            "distance_m": dist,
                            "ips": None,
                        }
                    )
            schools_list.sort(key=lambda x: x["distance_m"])

            # Enrich with IPS if UAI codes found
            if uai_list:
                uai_filter = f"uai IN ({','.join(uai_list[:15])})"
                r_ips = await client.get(
                    "https://data.education.gouv.fr/api/explore/v2.1/catalog/datasets/fr-en-ips-ecoles-ap2022/records",
                    params={"where": uai_filter, "limit": 30},
                )
                ips_map: dict[str, float] = {}
                if r_ips.status_code == 200:
                    for ir in r_ips.json().get("results", []):
                        u = ir.get("uai")
                        val = ir.get("ips")
                        if u and val:
                            try:
                                ips_map[u] = round(float(val), 1)
                            except ValueError:
                                pass
                for s in schools_list:
                    if s["uai"] in ips_map:
                        s["ips"] = ips_map[s["uai"]]

            ips_vals = [s["ips"] for s in schools_list if s["ips"] is not None]
            out["count"] = len(schools_list)
            out["schools"] = schools_list[:12]
            if ips_vals:
                out["average_ips"] = round(sum(ips_vals) / len(ips_vals), 1)
    except Exception:
        pass
    return out


async def fetch_solar_pvgis(lat: float, lon: float) -> dict[str, Any]:
    """Fetch solar irradiation & sunshine profile from European Commission PVGIS API."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://re.jrc.ec.europa.eu/api/v5_2/PVcalc",
                params={
                    "lat": round(lat, 4),
                    "lon": round(lon, 4),
                    "peakpower": 3,  # 3 kWp typical residential solar installation
                    "loss": 14,
                    "angle": 35,
                    "aspect": 0,
                    "outputformat": "json",
                },
            )
            if resp.status_code == 200:
                totals = resp.json().get("outputs", {}).get("totals", {}).get("fixed", {})
                e_y = float(totals.get("E_y") or 0)  # kWh/year for 3 kWc
                h_y = float(totals.get("H(i)_y") or 0)  # kWh/m2/year irradiation
                loss_aoi = float(totals.get("l_tg") or 0)
                return {
                    "available": True,
                    "yearly_irradiation_kwh_m2": round(h_y),
                    "pv_3kwc_production_kwh_year": round(e_y),
                    "estimated_solar_savings_eur_year": round(e_y * 0.22),
                    "sunshine_quality": "Très bon ensoleillement local" if h_y >= 1180 else ("Ensoleillement standard Normandie" if h_y >= 1080 else "Fond de vallée / Masque d'ombrage modéré"),
                }
    except Exception:
        pass
    return {"available": False}


async def fetch_osm_amenities_and_noise(lat: float, lon: float) -> dict[str, Any]:
    """Query OpenStreetMap Overpass API for shops, healthcare, parks, and noise sources (railways, motorways, high-voltage)."""
    query = f"""
    [out:json][timeout:8];
    (
      node["shop"~"supermarket|convenience|bakery|butcher|greengrocer"](around:1000,{lat},{lon});
      way["shop"~"supermarket|convenience|bakery"](around:1000,{lat},{lon});
      node["amenity"~"pharmacy|doctors|clinic|hospital|childcare|kindergarten|marketplace|post_office"](around:1000,{lat},{lon});
      way["leisure"~"park|garden|sports_centre"](around:800,{lat},{lon});
      way["railway"~"rail|tram|subway"](around:350,{lat},{lon});
      way["highway"~"motorway|trunk|primary"](around:300,{lat},{lon});
      way["power"="line"](around:250,{lat},{lon});
    );
    out center 60;
    """
    out: dict[str, Any] = {
        "supermarkets": [],
        "bakeries": [],
        "health": [],
        "parks_count": 0,
        "noise_sources": [],
        "walkability_label": "Modérée",
    }
    try:
        async with httpx.AsyncClient(timeout=9.0) as client:
            resp = await client.post("https://overpass-api.de/api/interpreter", data={"data": query})
            if resp.status_code == 200:
                elements = resp.json().get("elements", [])
                for el in elements:
                    tags = el.get("tags", {})
                    elat = el.get("lat") or (el.get("center") or {}).get("lat")
                    elon = el.get("lon") or (el.get("center") or {}).get("lon")
                    dist = round(haversine_m(lat, lon, float(elat), float(elon))) if (elat and elon) else 500
                    name = tags.get("name", "")

                    shop = tags.get("shop", "")
                    amenity = tags.get("amenity", "")
                    if shop in ("supermarket", "convenience"):
                        out["supermarkets"].append({"name": name or "Supermarché / Supérette", "distance_m": dist})
                    elif shop in ("bakery", "butcher", "greengrocer"):
                        out["bakeries"].append({"name": name or f"Commerce ({shop})", "distance_m": dist})
                    elif amenity in ("pharmacy", "doctors", "clinic", "hospital", "childcare"):
                        out["health"].append({"name": name or amenity.capitalize(), "type": amenity, "distance_m": dist})
                    elif tags.get("leisure") in ("park", "garden"):
                        out["parks_count"] += 1
                    elif tags.get("railway") == "rail":
                        out["noise_sources"].append({"type": "Voie ferrée SNCF", "name": name or "Ligne ferroviaire", "distance_m": dist})
                    elif tags.get("highway") in ("motorway", "trunk", "primary"):
                        out["noise_sources"].append({"type": "Axe routier majeur", "name": name or tags.get("ref", "Grand axe"), "distance_m": dist})
                    elif tags.get("power") == "line":
                        out["noise_sources"].append({"type": "Ligne Haute Tension", "name": "Ligne électrique HT", "distance_m": dist})

                out["supermarkets"].sort(key=lambda x: x["distance_m"])
                out["bakeries"].sort(key=lambda x: x["distance_m"])
                out["health"].sort(key=lambda x: x["distance_m"])
                # Deduplicate noise sources by type
                dedup_noise = {}
                for ns in sorted(out["noise_sources"], key=lambda x: x["distance_m"]):
                    if ns["type"] not in dedup_noise:
                        dedup_noise[ns["type"]] = ns
                out["noise_sources"] = list(dedup_noise.values())

                poi_total = len(out["supermarkets"]) + len(out["bakeries"]) + len(out["health"])
                if poi_total >= 8:
                    out["walkability_label"] = "Excellente (Tout à pied < 10 min)"
                elif poi_total >= 3:
                    out["walkability_label"] = "Bonne (Commerces de proximité accessibles)"
                else:
                    out["walkability_label"] = "Secteur résidentiel calme (Voiture/Vélo utile pour les courses)"
    except Exception:
        pass
    return out


async def run_full_enrichment(listing_data: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    """Run all Open Data enrichments in parallel for a property."""
    lat = float(listing_data.get("lat") or 0)
    lon = float(listing_data.get("lon") or 0)
    address_input = listing_data.get("address_input", "")
    postcode = listing_data.get("postcode", "")
    city = listing_data.get("city", "")
    citycode = listing_data.get("citycode", "")
    surface_m2 = float(listing_data.get("surface_m2") or 0)
    price = float(listing_data.get("price") or 0)
    property_type = listing_data.get("property_type", "Maison")
    dpe_letter = listing_data.get("dpe_letter", "")

    geo_info: dict[str, Any] = {}
    if (lat == 0 or lon == 0) and (address_input or city or postcode):
        geo_info = await geocode_address(address_input or city, postcode, city)
        if geo_info.get("found"):
            lat = geo_info["lat"]
            lon = geo_info["lon"]
            postcode = geo_info.get("postcode") or postcode
            city = geo_info.get("city") or city
            citycode = geo_info.get("citycode") or citycode

    if lat == 0 or lon == 0:
        return {"error": "Impossible de géolocaliser l'adresse"}

    cadastre_task = fetch_cadastre_and_plu(lat, lon)
    georisques_task = fetch_georisques(lat, lon, citycode)
    dpe_task = fetch_ademe_dpe_for_address(address_input or geo_info.get("label", ""), postcode, surface_m2, dpe_letter)
    schools_task = fetch_schools_and_ips(lat, lon, city)
    education_task = fetch_complete_education_trajectory(lat, lon, city)
    solar_task = fetch_solar_pvgis(lat, lon)
    osm_task = fetch_osm_amenities_and_noise(lat, lon)
    mobility_task = compute_mobility(lat, lon, settings)

    cadastre, georisques, ademe_dpe, schools, education_data, solar, osm, mobility = await asyncio.gather(
        cadastre_task,
        georisques_task,
        dpe_task,
        schools_task,
        education_task,
        solar_task,
        osm_task,
        mobility_task,
    )

    dvf = analyze_dvf_around(
        lat=lat,
        lon=lon,
        property_type=property_type,
        price=price,
        surface_m2=surface_m2,
    )

    land_m2 = float(listing_data.get("land_m2") or cadastre.get("contenance_m2") or 0)
    appreciation_data = evaluate_property_appreciation_potential(
        city=city or geo_info.get("city", "Rouen"),
        listing_price=price,
        surface_m2=surface_m2,
        land_m2=land_m2,
        dpe_letter=dpe_letter,
        mobility=mobility,
    )
    walkability_data = compute_15min_city_walkability(osm)
    socio_data = get_commune_socio_profile(city or geo_info.get("city", "Rouen"))

    neighborhood = {
        "socio": socio_data,
        "education": education_data,
        "appreciation": appreciation_data,
        "walkability_15min": walkability_data,
    }

    return {
        "geocoding": geo_info
        or {
            "found": True,
            "label": listing_data.get("address_resolved") or address_input,
            "lat": lat,
            "lon": lon,
            "postcode": postcode,
            "city": city,
            "citycode": citycode,
        },
        "dvf": dvf,
        "mobility": mobility,
        "cadastre": cadastre,
        "georisques": georisques,
        "ademe_dpe": ademe_dpe,
        "schools": schools,
        "solar": solar,
        "osm": osm,
        "neighborhood": neighborhood,
    }
