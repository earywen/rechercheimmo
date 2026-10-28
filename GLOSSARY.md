# Glossaire du Domaine — Recherche Immo (Métropole Rouen Normandie)

Ce glossaire définit le vocabulaire métier utilisé dans le code, la base de données et l'interface de l'analyseur immobilier.

| Terme | Définition dans le projet |
| :--- | :--- |
| **Listing (Annonce)** | Offre immobilière soumise à l'analyse (maison ou appartement), identifiée par son adresse postale (ou ses coordonnées GPS estimées via le Mode Détective), son prix affiché, ses caractéristiques (surface, pièces, chambres, terrain, DPE) et ses photos. |
| **Enrichment (Enrichissement Open Data)** | Collecte automatisée et déterministe de données publiques autour de la parcelle du bien : BAN, Cadastre IGN, DVF 76, ADEME DPE, Géorisques (Marnières/Cavités, RGA, PPRI, Radon, ICPE/Seveso), Éducation Nationale (Écoles & IPS), PVGIS Solaire, Overpass OSM (Commerces & Bruit), et Mobilité. |
| **Astuce Transit (Trajet Madame)** | Calcul du temps de trajet porte-à-porte en transports en commun sur le réseau **Astuce** (Métropole Rouen Normandie : Métro, TEOR T1-T4, lignes Fast, Bus) entre le bien et le **34 rue Cauchoise, 76000 Rouen**, basé sur les données officielles GTFS Astuce. Dealbreaker au-delà de **40–45 minutes**. |
| **Madrillet Drive (Trajet Monsieur)** | Calcul du temps de trajet routier en voiture entre le bien et **GINGER BURGEAP (`Rue du Pré de la Roquette, 76800 Saint-Étienne-du-Rouvray`)** via l'API de routage IGN Valhalla, avec détection du franchissement des ponts de la Seine. |
| **Marnière / Cavité 76** | Risque spécifique haut-normand lié aux cavités souterraines (marnières, karst crayeux). Tout indice de cavité dans un rayon de 100 m à 500 m est signalé avec sa distance exacte. |
| **True Monthly Cost (Vrai Coût Mensuel)** | Somme mensuelle réelle supportée par le couple : mensualité de crédit (Prix + Frais de notaire + Travaux estimés - Apport de 80 000 €) + 1/12e de la Taxe Foncière + 1/12e de la facture énergétique annuelle DPE + charges/entretien. |
| **Dealbreaker (Drapeau Rouge)** | Critère rédhibitoire déclenchant une alerte immédiate en haut de la fiche (ex: trajet Madame > 45 min, moins de 2 chambres, marnière à moins de 100 m, zone inondable PPRI, site Seveso proche, DPE F/G sans budget travaux). |
| **Radar Score (Score 360°)** | Note globale sur 100 calculée à partir de 6 axes pondérés : (1) Prix & Marché DVF, (2) Mobilité Couple (priorité Madame), (3) Bâti, Terrain & Énergie, (4) Risques & Sous-sol 76, (5) Quartier, Écoles & Commodités, (6) Potentiel & Confort. |
| **AI Audit (Expertise IA `agy`)** | Analyse approfondie exécutée via le compte `agy` (Gemini Pro OAuth) comprenant : le décryptage du texte de l'annonce, l'inspection visuelle des photos (toiture, menuiseries, électricité, humidité, cuisine/SDB), le chiffrage des travaux, les arguments de négociation et la checklist de visite. |
