# Recherche Immo — Instructions Agents

## Règles Impératives du Projet (Quality & Design Gates)

### 1. Documentation & Code Review/Production via Context7 MCP
- **Obligatoire** : Pour toute production, revue ou mise à jour de code utilisant une librairie, un framework, un SDK ou une API (ex: `FastAPI`, `Pydantic`, `httpx`, `Leaflet`, `SQLite`, `Chrome Extensions Manifest V3`), **utiliser impérativement le serveur MCP `context7`** (`resolve-library-id` puis `query-docs`) afin de vérifier les bonnes pratiques actuelles et éviter les patterns dépréciés.

### 2. Design & Audit UI via Impeccable
- **Obligatoire** : Pour toute conception, modification ou revue d'interface (`templates/`, `static/`, `chrome-extension/`), **utiliser impérativement `impeccable`** (les skills `.gemini/skills/impeccable/`, les fichiers de vérité `PRODUCT.md` et `DESIGN.md`, ainsi que le détecteur déterministe `npx impeccable detect <cible>` et `npx impeccable detect http://localhost:8765`).
- Aucun changement UI ne doit être livré avec des anti-patterns détectés par `impeccable detect` (zéro `ai-color-palette`, `low-contrast`, `side-tab`, `nested-cards`, `flat-type-hierarchy`, `skipped-heading`).

---

## Agent skills

### Issue tracker

Issues and specs are tracked in GitHub Issues (`earywen/rechercheimmo`) via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Uses the five default canonical triage labels (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout (`GLOSSARY.md` and `docs/adr/` at the repo root). See `docs/agents/domain.md`.
