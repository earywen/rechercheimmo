# Référentiel des Sources Open Data, API & Critères d'Analyse Immobilière (France)

Ce document recense l'ensemble des API publiques gratuites, jeux de données Open Data et critères d'analyse exploitables pour évaluer un bien immobilier à 360° en France.

---

## 1. Pivot Géographique & Foncier (Retrouver et localiser le bien)

| Source / API | Endpoint / Accès | Clé requise | Données récupérées & Usage |
| :--- | :--- | :--- | :--- |
| **API Adresse (BAN)** | `https://api-adresse.data.gouv.fr/search/` | Non | Géocodage normalisé, coordonnées GPS (`lat`, `lon`), identifiant unique `ban_id`, code INSEE commune. |
| **API Carto / Cadastre (IGN)** | `https://apicarto.ign.fr/api/cadastre/` | Non | Parcelle cadastrale exacte (numéro, section, contenance/surface terrain en m²), géométrie GeoJSON de la parcelle et emprise au sol des bâtiments. |
| **API Découpage Administratif** | `https://geo.api.gouv.fr/communes` | Non | Informations communales, code EPCI, population, département. |

---

## 2. Prix au m² Réel & Historique du Marché

| Source / API | Endpoint / Accès | Clé requise | Données récupérées & Usage |
| :--- | :--- | :--- | :--- |
| **DVF (Demandes de Valeurs Foncières) / Cerema DVF+** | `https://apidf-preprod.cerema.fr/` ou `https://api.cquest.org/dvf` ou fichiers CSV/Parquet `data.gouv.fr` | Non | Toutes les ventes notariées sur 5 à 10 ans : date de mutation, prix net vendeur, surface bâtie, nombre de pièces, surface du terrain, nature du bien. Permet de calculer le vrai prix médian au m² de la rue et du quartier. |
| **Castorus / Pappers Immobilier** | Consultation web / scraping | — | Historique de l'annonce (durée de mise en vente, baisses de prix successives) et propriétaire personne morale (SCI) via Pappers. |

---

## 3. Performance Énergétique & Caractéristiques Techniques du Bâtiment

| Source / API | Endpoint / Accès | Clé requise | Données récupérées & Usage |
| :--- | :--- | :--- | :--- |
| **API DPE ADEME (Logements existants & neufs)** | `https://data.ademe.fr/data-fair/api/v1/datasets/dpe-v2-logements-existants/lines` | Non | **Pépite pour démasquer l'adresse d'une annonce** (en filtrant par code postal + surface + classe DPE/GES + année). Donne : numéro DPE, étiquette DPE/GES, consommation en $\text{kWh/m}^2/\text{an}$, coût annuel estimé de chauffage, type d'isolation (murs, fenêtres, toiture), type de chauffage/ECS, présence de climatisation, altitude, étage. |
| **BDNB (Base de Données Nationale des Bâtiments - CSTB)** | `https://api.bdnb.io/` (Open Data / Freemium) | Non (Open) | Croisement DPE + Cadastre + Fichiers fonciers : année de construction, matériaux des murs/toiture, hauteur du bâtiment, potentiel solaire en toiture. |
| **Registre National des Copropriétés (RNC)** | `data.gouv.fr` | Non | Nombre de lots, époque de construction, syndic professionnel ou bénévole, procédures d'alerte ou dettes de la copropriété. |

---

## 4. Risques Naturels, Miniers, Technologiques & Pollutions

| Source / API | Endpoint / Accès | Clé requise | Données récupérées & Usage |
| :--- | :--- | :--- | :--- |
| **API Géorisques (BRGM / Ministère)** | `https://georisques.gouv.fr/api/v1/` | Non (ou Token gratuit) | Interrogation directe par `lat,lon` dans un rayon donné :<br>- **Retrait-gonflement des argiles (RGA)** : aléa faible/moyen/fort (critique pour les maisons).<br>- **Inondations** (PPRi, débordement de cours d'eau, remontée de nappes).<br>- **Radon** (potentiel 1 à 3) & **Zonage sismique**.<br>- **Cavités souterraines** & **Mouvements de terrain**.<br>- **Sols pollués** (BASOL / SIS / CASIAS - anciens sites industriels/stations-service).<br>- **Installations Classées (ICPE / Seveso)**. |

---

## 5. Qualité du Quartier, Démographie, Écoles & Sécurité

| Source / API | Endpoint / Accès | Clé requise | Données récupérées & Usage |
| :--- | :--- | :--- | :--- |
| **INSEE Filosofi (Données carroyées 200m × 200m)** | `data.gouv.fr` / `insee.fr` | Non | Niveau de vie médian des ménages dans le carré de 200m autour du bien, taux de pauvreté, part des propriétaires vs locataires, part des logements sociaux, part des ménages avec enfants, âge moyen. |
| **API Éducation Nationale** | `https://data.education.gouv.fr/api/explore/v2.1/` | Non | Annuaire des écoles maternelles, élémentaires, collèges, lycées + **IPS (Indice de Position Sociale)** de chaque établissement + **IVAL** (taux de réussite et de mentions au Brevet et au Bac). |
| **Sécurité / Délinquance (SSMSI)** | Jeux de données `data.gouv.fr` (Ministère de l'Intérieur) | Non | Taux pour 1000 habitants par commune : cambriolages de logements, vols de véhicules, dégradations volontaires, violences. |
| **Impôts locaux (DGFiP - REI)** | `data.gouv.fr` (Recensement des Éléments d'Imposition) | Non | Taux communal et intercommunal de la **Taxe Foncière** (TFPB) et de la TEOM (ordures ménagères). |

---

## 6. Infrastructures, Commerces, Transports & Qualité de Vie

| Source / API | Endpoint / Accès | Clé requise | Données récupérées & Usage |
| :--- | :--- | :--- | :--- |
| **OpenStreetMap (API Overpass)** | `https://overpass-api.de/api/interpreter` | Non | Extraction exhaustive dans un rayon de 500m / 1km / 2km : boulangeries, supermarchés, marchés, médecins, pharmacies, hôpitaux, crèches, parcs et espaces verts, salles de sport, restaurants, mais aussi sources de nuisances (voies ferrées, lignes haute tension, boîtes de nuit, axes routiers majeurs). |
| **API Isochrones / Itinéraires (IGN Géoplateforme / OSRM)** | `https://data.geopf.fr/navigation/isochrone` | Non | Calcul de la zone accessible en **5, 10 ou 15 minutes à pied, à vélo ou en voiture** (ville du quart d'heure) et temps de trajet vers les lieux de travail du couple. |
| **Transports en commun (PAN)** | `https://transport.data.gouv.fr/api/` | Non | Arrêts de bus, tram, métro, gares SNCF/TER/TGV et fréquences de passage (GTFS). |
| **Ensoleillement & Solaire (PVGIS - Commission Européenne)** | `https://re.jrc.ec.europa.eu/api/v5_2/` | Non | Irradiation solaire mensuelle, masque d'ombrage lié au relief (horizon), heures d'ensoleillement par an. |
| **Fibre & Télécoms (ARCEP)** | *Ma Connexion Internet* (`data.gouv.fr`) | Non | Éligibilité Fibre FttH à l'adresse et couverture 4G/5G des opérateurs. |
| **Cartes de Bruit (PPBE / Géoportail IGN)** | Flux WMS/WFS IGN / Cerema | Non | Exposition sonore en décibels ($L_{\text{den}}$ jour/soir/nuit et $L_{\text{night}}$) liée aux routes, trains et couloirs aériens. |
| **Qualité de l'Air (ATMO France)** | `atmo-france.org` / AASQA régionales | Sur inscription | Indice ATMO et concentrations annuelles en particules fines ($\text{PM}_{2.5}$, $\text{PM}_{10}$) et $\text{NO}_2$. |
