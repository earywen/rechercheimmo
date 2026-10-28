# DESIGN.md — Architectural & Editorial Cartography (Mode: Operate)

## 1. Visual Direction & Palette
- **Concept**: *Swiss Precision & Cartographie Éditoriale (Bleu Outremer & Graphite)* — une interface analytique nette, haute lisibilité en extérieur sur mobile (lors des visites) comme sur grand écran en mode sombre, inspirée de la précision suisse (style Linear) et de la cartographie cadastrale.
- **No AI Slop**: Zéro gradient violet/néon, zéro carte imbriquée dans une carte (`nested-cards`), zéro bordure latérale épaisse (`side-tab`), contrastes strictement conformes WCAG AA ($\ge 4.5:1$ pour le texte et les boutons).
- **Palette Tokens (`color-scheme: light dark` & `light-dark()`)**:
  - Fond principal (`--bg`): `light-dark(#f3f4f6, #0b0f19)` (Zinc clair / Obsidienne ardoise sans dominante verte)
  - Surface / Panneaux (`--surface`): `light-dark(#ffffff, #111827)`
  - Surface secondaire (`--surface-subtle`): `light-dark(#e5e7eb, #1e293b)`
  - Bordures (`--border`): `light-dark(#d1d5db, #263248)`
  - Texte principal (`--ink`): `light-dark(#0f172a, #f8fafc)` (Contraste > 16:1 dans les deux modes)
  - Texte secondaire (`--ink-muted`): `light-dark(#475569, #94a3b8)` (Contraste > 6.4:1 dans les deux modes)
  - Accent primaire (`--accent`): `light-dark(#1d4ed8, #60a5fa)` (Bleu Outremer / Bleu Ciel Cobalt) avec texte `--accent-contrast: light-dark(#ffffff, #090d16)` (Contraste > 6.7:1 dans les deux modes)
  - Statuts sémantiques (séparés de l'accent de marque, contraste AA garanti):
    - Succès / Conforme (`--ok-bg` `light-dark(#ecfdf5, #062e22)`, `--ok-ink` `light-dark(#065f46, #6ee7b7)`)
    - Vigilance (`--warn-bg` `light-dark(#fffbeb, #331f06)`, `--warn-ink` `light-dark(#92400e, #fcd34d)`)
    - Alerte Rouge / Dealbreaker (`--danger-bg` `light-dark(#fef2f2, #381111)`, `--danger-ink` `light-dark(#991b1b, #fca5a5)`)

## 2. Typography & Hierarchy
- **Échelle typographique franche** (ratio > 1.25× entre niveaux adjacents):
  - `h1` (Titre application): `1.35rem` (21.6px), `font-weight: 700`, `letter-spacing: -0.02em`
  - `h2` (Titre du bien / En-têtes de sections et modales): `1.65rem` (26.4px) pour le titre principal du bien, `1.2rem` (19.2px) pour les sections
  - `h3` (Sous-groupes): `1.0rem` (16px), `font-weight: 600`
  - `body`: `0.9375rem` (15px), `font-variant-numeric: tabular-nums` sur toutes les données chiffrées (prix, $\text{m}^2$, distances, temps de trajet).

## 3. Structural Principles & Information Architecture
- **Flat Hierarchy (Zéro `nested-cards`)**: Les sections de la fiche de bien sont structurées par des filets horizontaux (`border-top: 1px solid var(--border)`), de l'espace blanc généreux et des grilles tabulaires propres, sans empiler de boîtes dans des boîtes.
- **Progressive Disclosure par 4 Onglets Thématiques (`role="tablist"`)**:
  - Au-dessus des onglets, un **En-tête de Décision fixe** présente les 4 indicateurs vitaux du couple : *Vrai Coût Mensuel*, *Prix & Offre Conseillée*, *Trajet Madame (Astuce)* et *Surface & DPE*.
  - Les analyses détaillées sont réparties dans 4 onglets thématiques cohérents :
    1. **Synthèse & Carte** (Alertes/Atouts, Verdict IA & Décryptage, Score 360°, Carte interactive multi-couches)
    2. **Budget, DVF & Travaux** (Simulateur du Vrai Coût Mensuel, Postes de travaux, Stratégie de négociation, Ventes notariées DVF 76)
    3. **Trajets, Quartier & Risques 76** (Mobilité Astuce/Voiture, Écoles IPS & Commerces, Marnières/Argiles/PLU/Solaire, Diagnostic DPE ADEME)
    4. **Checklist Visite & Notes** (Questions agence à cocher + bloc-notes du couple)
- **Formulaire d'ajout simplifié**: Seuls l'adresse, le prix, le lien et le texte de l'annonce sont affichés par défaut ; les 10 champs secondaires sont repliés dans un bloc `<details class="progressive-details">`.
