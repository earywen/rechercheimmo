# DESIGN.md — Architectural & Editorial Cartography (Mode: Operate)

## 1. Visual Direction & Palette
- **Concept**: *Carnet d'Architecte & Cadastre Normand* — une interface claire, haute lisibilité en extérieur sur mobile (lors des visites) comme sur grand écran, inspirée des plans d'architecte, des revues foncières et de la pierre/ardoise rouennaise.
- **No AI Slop**: Zéro gradient violet/néon, zéro carte imbriquée dans une carte (`nested-cards`), zéro bordure latérale épaisse (`side-tab`), contrastes strictement conformes WCAG AA ($\ge 4.5:1$ pour le texte et les boutons).
- **Palette Tokens**:
  - Fond principal (`--bg`): `#f1f5f9` (Gris ardoise clair de Seine)
  - Surface / Panneaux (`--surface`): `#ffffff` (Blanc pur)
  - Surface secondaire (`--surface-subtle`): `#e2e8f0` (Ardoise douce)
  - Bordures (`--border`): `#cbd5e1` (Trait fin architectural)
  - Texte principal (`--ink`): `#0f172a` (Encre ardoise profonde, contraste > 15:1)
  - Texte secondaire (`--ink-muted`): `#475569` (Gris ardoise soutenu, contraste > 7:1)
  - Accent primaire (`--accent`): `#0f4c3a` (Vert forêt normand profond — texte `#ffffff` avec contraste > 9.5:1)
  - Statuts sémantiques (contraste AA garanti):
    - Succès / Conforme (`--ok-bg` `#e6f4ea`, `--ok-ink` `#13532c`)
    - Vigilance (`--warn-bg` `#fef3c7`, `--warn-ink` `#78350f`)
    - Alerte Rouge / Dealbreaker (`--danger-bg` `#fee2e2`, `--danger-ink` `#7f1d1d`)

## 2. Typography & Hierarchy
- **Échelle typographique franche** (ratio > 1.25× entre niveaux adjacents):
  - `h1` (Titre application): `1.35rem` (21.6px), `font-weight: 700`, `letter-spacing: -0.02em`
  - `h2` (Titre du bien / En-têtes de sections et modales): `1.65rem` (26.4px) pour le titre principal du bien, `1.2rem` (19.2px) pour les sections
  - `h3` (Sous-groupes): `1.0rem` (16px), `font-weight: 600`
  - `body`: `0.9375rem` (15px), `font-variant-numeric: tabular-nums` sur toutes les données chiffrées (prix, $\text{m}^2$, distances, temps de trajet).

## 3. Structural Principles
- **Flat Hierarchy (Zéro `nested-cards`)**: Les sections de la fiche de bien sont structurées par des filets horizontaux (`border-top: 1px solid var(--border)`), de l'espace blanc généreux et des grilles tabulaires propres, sans empiler de boîtes dans des boîtes.
