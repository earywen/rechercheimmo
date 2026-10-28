/* Recherche Immo IA — Frontend Application Logic (Impeccable & Context7 Compliant) */

let ALL_LISTINGS = [];
let CURRENT_ID = null;
let SETTINGS = {};
let LEAFLET_MAP = null;
let LEAFLET_TILE_LAYER = null;

function isDarkModeActive() {
  const meta = document.querySelector('meta[name="color-scheme"]');
  const content = meta ? meta.content : "light dark";
  if (content === "dark") return true;
  if (content === "light") return false;
  return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function getTileLayerUrl() {
  return isDarkModeActive()
    ? "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
    : "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
}

function updateThemeButtonLabel() {
  const btn = document.getElementById("btnThemeToggle");
  if (!btn) return;
  btn.textContent = isDarkModeActive() ? "Mode clair" : "Mode sombre";
}

function toggleColorScheme() {
  const meta = document.querySelector('meta[name="color-scheme"]');
  if (!meta) return;
  const sysDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  const sysScheme = sysDark ? "dark" : "light";
  const currentRendered = isDarkModeActive() ? "dark" : "light";
  const targetScheme = currentRendered === "dark" ? "light" : "dark";

  try {
    if (targetScheme !== sysScheme) {
      localStorage.setItem("color-scheme", targetScheme);
      meta.content = targetScheme;
    } else {
      localStorage.removeItem("color-scheme");
      meta.content = "light dark";
    }
  } catch (e) {
    meta.content = targetScheme;
  }

  updateThemeButtonLabel();
  if (LEAFLET_TILE_LAYER) {
    LEAFLET_TILE_LAYER.setUrl(getTileLayerUrl());
  }
}

function fmtEur(n) {
  if (n === null || n === undefined || isNaN(n)) return "—";
  return new Intl.NumberFormat("fr-FR").format(Math.round(Number(n))) + " €";
}

function scoreClass(score) {
  if (score >= 72) return "score-high";
  if (score >= 52) return "score-mid";
  return "score-low";
}

function barColor(score) {
  if (score >= 72) return "#166534";
  if (score >= 52) return "#b45309";
  return "#991b1b";
}

/* Native <dialog> light-dismiss fallback for browsers without closedBy */
function setupDialogs() {
  document.querySelectorAll("dialog").forEach((dialog) => {
    if (!("closedBy" in HTMLDialogElement.prototype)) {
      dialog.addEventListener("click", (event) => {
        if (event.target !== dialog) return;
        const rect = dialog.getBoundingClientRect();
        const isDialogContent =
          rect.top <= event.clientY &&
          event.clientY <= rect.top + rect.height &&
          rect.left <= event.clientX &&
          event.clientX <= rect.left + rect.width;
        if (isDialogContent) return;
        dialog.close();
      });
    }
  });

  document.querySelectorAll("[data-close-dialog]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-close-dialog");
      const dlg = document.getElementById(id);
      if (dlg) dlg.close();
    });
  });
}

async function loadInitialData() {
  const [resSettings, resListings] = await Promise.all([
    fetch("/api/settings"),
    fetch("/api/listings"),
  ]);
  SETTINGS = await resSettings.json();
  ALL_LISTINGS = await resListings.json();

  document.getElementById("pillBudget").textContent = fmtEur(SETTINGS.target_budget);
  document.getElementById("pillApport").textContent = fmtEur(SETTINGS.apport);

  renderSidebar();
  if (ALL_LISTINGS.length > 0) {
    selectListing(ALL_LISTINGS[0].id);
  } else {
    document.getElementById("detailContainer").innerHTML = `
      <div class="dossier-sheet" style="text-align:center; padding: 3rem;">
        <h2>Aucune annonce enregistrée</h2>
        <p style="color: var(--ink-muted); margin: 0.75rem 0 1.25rem;">Cliquez sur « + Analyser un bien » ou utilisez l'extension Chrome sur LeBonCoin / SeLoger / Bien'ici.</p>
        <div><button class="btn btn-primary" onclick="document.getElementById('addListingDialog').showModal()">+ Analyser ma première maison</button></div>
      </div>
    `;
  }
}

function renderSidebar() {
  const filterVal = document.getElementById("filterStatus").value;
  const filtered = ALL_LISTINGS.filter(
    (item) => filterVal === "ALL" || item.status === filterVal
  );
  document.getElementById("listingsCount").textContent = filtered.length;

  const container = document.getElementById("listingsList");
  container.innerHTML = filtered
    .map((item) => {
      const isAct = item.id === CURRENT_ID ? "active" : "";
      const sClass = scoreClass(item.score_total);
      const dbCount = item.dealbreakers_count || 0;
      const mMin = item.madame_transit_min || "?";
      const dpe = (item.dpe_letter || "?").toUpperCase();

      return `
        <div class="listing-item ${isAct}" onclick="selectListing(${item.id})">
          <div class="listing-item-top">
            <div class="listing-title">${item.title}</div>
            <div class="score-badge ${sClass}">${item.score_total}/100</div>
          </div>
          <div style="font-weight: 750; color: var(--accent); font-size: 0.96rem;">
            ${fmtEur(item.price)}
            <span style="font-weight: 450; color: var(--ink-muted); font-size: 0.8rem;">
              (${fmtEur(item.true_monthly_cost)}/mois tout compris)
            </span>
          </div>
          <div class="listing-meta">
            <span class="tag">${item.surface_m2 || "?"} m²</span>
            ${item.land_m2 ? `<span class="tag">Terrain ${Math.round(item.land_m2)} m²</span>` : ""}
            <span class="tag">${item.bedrooms || "?"} ch</span>
            <span class="tag">DPE ${dpe}</span>
            <span class="tag ${mMin <= 45 ? "tag-ok" : "tag-alert"}">Mme: ${mMin} min</span>
            ${dbCount > 0 ? `<span class="tag tag-alert">${dbCount} alerte(s)</span>` : ""}
          </div>
        </div>
      `;
    })
    .join("");
}

async function selectListing(id) {
  CURRENT_ID = id;
  renderSidebar();
  const res = await fetch(`/api/listings/${id}`);
  if (!res.ok) return;
  const item = await res.json();
  renderDetail(item);
}

function renderDetail(item) {
  const enr = item.enrichment || {};
  const dvf = enr.dvf || {};
  const mob = enr.mobility || {};
  const mme = mob.madame || {};
  const mr = mob.monsieur || {};
  const cad = enr.cadastre || {};
  const geo = enr.georisques || {};
  const dpeData = enr.ademe_dpe || {};
  const sch = enr.schools || {};
  const sol = enr.solar || {};
  const osm = enr.osm || {};
  const fin = item.finance || {};
  const sco = item.scoring || {};
  const ai = item.ai_audit || {};

  const dpeLetter = (item.dpe_letter || "?").toUpperCase();
  const axesHtml = Object.values(sco.axes || {})
    .map(
      (ax) => `
      <div class="axis-row">
        <div class="axis-head">
          <span>${ax.label} <small style="color:var(--ink-muted)">(poids ${ax.weight}%)</small></span>
          <strong>${ax.score}/100</strong>
        </div>
        <div class="progress-track">
          <div class="progress-fill" style="width:${ax.score}%; background:${barColor(ax.score)};"></div>
        </div>
      </div>
    `
    )
    .join("");

  const dealbreakersHtml = (sco.dealbreakers || [])
    .map(
      (db) => `
      <div class="notice-bar notice-red">
        <div><strong>DRAPEAU ROUGE — ${db.title} :</strong> ${db.detail}</div>
      </div>
    `
    )
    .join("");

  const warningsHtml = (sco.warnings || [])
    .map(
      (w) => `
      <div class="notice-bar notice-warn">
        <div><strong>Point de vigilance :</strong> ${w}</div>
      </div>
    `
    )
    .join("");

  const strengthsHtml = (sco.strengths || [])
    .map(
      (st) => `
      <div class="notice-bar notice-green">
        <div><strong>Atout :</strong> ${st}</div>
      </div>
    `
    )
    .join("");

  const dvfRows = (dvf.sales || [])
    .slice(0, 10)
    .map(
      (s) => `
      <tr>
        <td>${s.date_mutation}</td>
        <td>${s.adresse_numero || ""} ${s.adresse_nom_voie || s.nom_commune}</td>
        <td><strong>${fmtEur(s.valeur_fonciere)}</strong></td>
        <td>${s.surface_bati} m²</td>
        <td>${s.surface_terrain ? Math.round(s.surface_terrain) + " m²" : "—"}</td>
        <td><strong>${fmtEur(s.prix_m2)}/m²</strong></td>
        <td>${s.distance_m} m</td>
      </tr>
    `
    )
    .join("");

  const worksRows = (ai.works_breakdown || [])
    .map(
      (w) => `
      <tr>
        <td><strong>${w.poste}</strong><br/><small style="color:var(--ink-muted)">${w.commentaire || ""}</small></td>
        <td><span class="tag">${w.urgence || "Moyenne"}</span></td>
        <td>${fmtEur(w.budget_min)} – ${fmtEur(w.budget_max)}</td>
      </tr>
    `
    )
    .join("");

  const checklistItems = (item.visit_checklist && item.visit_checklist.length
    ? item.visit_checklist
    : ai.visit_questions || []
  )
    .map(
      (q, idx) => `
      <label class="checklist-row">
        <input type="checkbox" ${q.checked ? "checked" : ""} onchange="toggleChecklistItem(${item.id}, ${idx}, this.checked)" />
        <div>
          <strong style="color: var(--accent);">[${q.category || "Visite"}]</strong> ${q.question}
        </div>
      </label>
    `
    )
    .join("");

  const streetViewUrl = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${item.lat},${item.lon}`;
  const geoportailUrl = `https://www.geoportail.gouv.fr/carte?c=${item.lon},${item.lat}&z=19&l0=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2::GEOPORTAIL:OGC:WMTS(1)&l1=CADASTRALPARCELS.PARCELLAIRE_EXPRESS::GEOPORTAIL:OGC:WMTS(1)&permalink=yes`;

  const container = document.getElementById("detailContainer");
  container.innerHTML = `
    <article class="dossier-sheet">
      <!-- HERO HEADER -->
      <header class="hero-header">
        <div>
          <div style="display:flex; align-items:center; gap:0.65rem; flex-wrap:wrap; margin-bottom:0.5rem;">
            <span class="score-badge ${scoreClass(item.score_total)}" style="font-size:1.05rem; height:34px; padding:0 0.75rem;">
              Score ${item.score_total}/100
            </span>
            <span class="tag" style="font-size:0.84rem; font-weight:650;">${sco.verdict_badge || ""}</span>
            <select aria-label="Statut de suivi du bien" onchange="updateListingStatus(${item.id}, this.value)" style="background:var(--bg); color:var(--ink); border:1px solid var(--border-strong); padding:0.25rem 0.6rem; border-radius:6px; font-size:0.84rem; font-weight:600;">
              ${["À étudier", "À visiter", "Visité", "Offre", "Écarté"]
                .map((st) => `<option value="${st}" ${item.status === st ? "selected" : ""}>Statut : ${st}</option>`)
                .join("")}
            </select>
          </div>
          <h2>${item.title}</h2>
          <div class="hero-address">
            ${item.address_resolved || item.address_input}
            — <a href="${streetViewUrl}" target="_blank">Street View</a>
            · <a href="${geoportailUrl}" target="_blank">Cadastre IGN</a>
            ${item.source_url ? `· <a href="${item.source_url}" target="_blank">Annonce d'origine</a>` : ""}
          </div>
        </div>

        <div style="display:flex; flex-direction:column; gap:0.5rem;">
          <button class="btn btn-primary" id="btnRunDeepAi" onclick="triggerDeepAiAudit(${item.id})">
            Relancer l'Audit IA Approfondi (agy)
          </button>
          <button class="btn btn-danger btn-sm" onclick="removeListing(${item.id})">
            Supprimer cette fiche
          </button>
        </div>
      </header>

      <!-- ARCHITECTURAL LEDGER STRIP (Zero Nested Cards) -->
      <div class="metrics-strip">
        <div class="metric-cell">
          <span class="metric-label">Prix Affiché</span>
          <span class="metric-val">${fmtEur(item.price)}</span>
        </div>
        <div class="metric-cell">
          <span class="metric-label">Prix / m² (vs DVF 76)</span>
          <span class="metric-val">${fmtEur(dvf.listing_price_m2)}/m² <small style="font-size:0.8rem; color:var(--ink-muted); font-weight:500;">(DVF: ${fmtEur(dvf.median_price_m2)})</small></span>
        </div>
        <div class="metric-cell">
          <span class="metric-label">Vrai Coût Mensuel</span>
          <span class="metric-val" style="color:var(--accent);">${fmtEur(fin.true_monthly_cost)}/mois</span>
        </div>
        <div class="metric-cell">
          <span class="metric-label">Surface &amp; Terrain</span>
          <span class="metric-val">${item.surface_m2 || "?"} m² · ${Math.round(item.land_m2 || cad.contenance_m2 || 0)} m²</span>
        </div>
        <div class="metric-cell">
          <span class="metric-label">Chambres &amp; DPE</span>
          <span class="metric-val">${item.bedrooms || "?"} ch (${item.rooms || "?"} p) · <span class="dpe-badge dpe-${dpeLetter}">${dpeLetter}</span></span>
        </div>
      </div>

      <!-- ALERTS & DEALBREAKERS -->
      <div class="alerts-list">
        ${dealbreakersHtml}
        ${warningsHtml}
        ${strengthsHtml}
      </div>

      <!-- SECTION 1: MOBILITÉ COUPLE & SCORING 360 -->
      <div class="editorial-grid">
        <div class="editorial-section">
          <div class="section-header">
            <h3>Mobilité du Couple (Astuce Rouen &amp; Madrillet)</h3>
            <span class="tag ${mme.is_dealbreaker ? "tag-alert" : "tag-ok"}">${mme.status_label || ""}</span>
          </div>

          <div class="commute-row">
            <div style="display:flex; justify-content:space-between; align-items:baseline;">
              <strong>Trajet Madame (Transport Astuce → 34 rue Cauchoise, Rouen)</strong>
              <span style="font-size:1.25rem; font-weight:800; color:${mme.is_dealbreaker ? "var(--danger-ink)" : "var(--ok-ink)"};">${mme.duration_min || "?"} min</span>
            </div>
            <p style="font-size:0.88rem; color:var(--ink);">
              <strong>Itinéraire matin (8h30) :</strong> ${mme.best_itinerary ? mme.best_itinerary.details : "Calcul en cours"}
            </p>
            ${
              (mme.nearby_astuce_stops || []).length
                ? `<div style="font-size:0.8rem; color:var(--ink-muted);">
                    <strong>Arrêts Astuce accessibles à pied :</strong>
                    ${mme.nearby_astuce_stops
                      .slice(0, 4)
                      .map((s) => `${s.stop_name} (${s.distance_m} m, lignes ${(s.lines || []).join(", ")})`)
                      .join(" · ")}
                  </div>`
                : ""
            }
          </div>

          <div class="commute-row">
            <div style="display:flex; justify-content:space-between; align-items:baseline;">
              <strong>Trajet Monsieur (Voiture → GINGER BURGEAP, Saint-Étienne-du-Rouvray)</strong>
              <span style="font-size:1.15rem; font-weight:800; color:var(--accent);">${mr.duration_min || "?"} min (${mr.distance_km || "?"} km)</span>
            </div>
            <p style="font-size:0.84rem; color:var(--ink-muted);">${mr.bridge_note || ""}</p>
          </div>
        </div>

        <div class="editorial-section">
          <div class="section-header">
            <h3>Décomposition du Score 360°</h3>
            <strong>${item.score_total}/100</strong>
          </div>
          <div style="display:flex; flex-direction:column; gap:0.75rem;">
            ${axesHtml}
          </div>
        </div>
      </div>

      <!-- SECTION 2: CARTE INTERACTIVE MULTI-COUCHES & AUDIT IA AGY -->
      <div class="editorial-grid">
        <div class="editorial-section">
          <div class="section-header">
            <h3>Plan Cadastral, Marnières 76, Ventes DVF &amp; Arrêts Astuce</h3>
            <small style="color:var(--ink-muted);">Marqueur déplaçable pour affiner l'adresse</small>
          </div>
          <div id="propertyMap"></div>
          <div style="display:flex; gap:0.8rem; flex-wrap:wrap; font-size:0.8rem; color:var(--ink-muted);">
            <span><strong>Bleu :</strong> Parcelle &amp; Bien</span>
            <span><strong>Vert :</strong> Ventes DVF récentes</span>
            <span><strong>Violet :</strong> Arrêts Astuce</span>
            <span><strong>Rouge :</strong> Cavités / Marnières 76</span>
          </div>
        </div>

        <div class="editorial-section">
          <div class="section-header">
            <h3>Expertise IA &amp; Stratégie de Négociation</h3>
            <span class="tag">${ai.engine || "Analyse IA"}</span>
          </div>
          <p style="font-size:0.92rem; color:var(--ink);">
            <strong>Avis global :</strong> ${ai.executive_summary || "Analyse disponible."}
          </p>

          <div>
            <strong style="font-size:0.88rem; color:var(--accent);">Décryptage de l'annonce vs Open Data :</strong>
            <ul style="padding-left:1.25rem; font-size:0.86rem; margin-top:0.35rem; color:var(--ink-muted);">
              ${(ai.ad_decryption || []).map((pt) => `<li>${pt}</li>`).join("")}
            </ul>
          </div>

          <div class="notice-bar notice-green" style="flex-direction:column; gap:0.4rem;">
            <div style="display:flex; justify-content:space-between; width:100%; align-items:center;">
              <strong>Prix d'offre recommandé : ${fmtEur(ai.negotiation_strategy?.target_offer_eur || fin.recommended_offer_price)}</strong>
              <span class="tag tag-ok">Marge : -${fmtEur(fin.potential_discount_eur)} (-${fin.potential_discount_pct}%)</span>
            </div>
            <ul style="padding-left:1.2rem; font-size:0.85rem; color:var(--ink);">
              ${(ai.negotiation_strategy?.arguments || []).map((arg) => `<li>${arg}</li>`).join("")}
            </ul>
          </div>
        </div>
      </div>

      <!-- SECTION 3: SIMULATEUR FINANCIER COMPLET & CHIFFRAGE TRAVAUX -->
      <div class="editorial-grid">
        <div class="editorial-section">
          <div class="section-header">
            <h3>Simulateur du « Vrai Coût Mensuel Tout Compris »</h3>
            <span class="tag">Apport ${fmtEur(fin.apport)} · ${fin.loan_years} ans à ${fin.interest_rate_pct}%</span>
          </div>
          <table class="data-table">
            <tbody>
              <tr><td>Prix d'achat affiché</td><td><strong>${fmtEur(fin.price)}</strong></td></tr>
              <tr><td>Frais de notaire (~7,8% ancien)</td><td>${fmtEur(fin.notary_fees)}</td></tr>
              <tr>
                <td>Budget travaux retenu (modifiable)</td>
                <td>
                  <input type="number" aria-label="Budget travaux retenu" value="${fin.travaux_estimes}" onchange="updateFinancialField(${item.id}, 'travaux_estimes', this.value)" style="width:110px; background:var(--bg); color:var(--ink); border:1px solid var(--border-strong); padding:0.2rem 0.45rem; border-radius:4px;" /> €
                </td>
              </tr>
              <tr><td><strong>Coût total de l'opération</strong></td><td><strong>${fmtEur(fin.total_project_cost)}</strong> (Emprunt : ${fmtEur(fin.loan_amount)})</td></tr>
              <tr><td>Mensualité Crédit + Assurance</td><td><strong>${fmtEur(fin.monthly_mortgage)} / mois</strong></td></tr>
              <tr>
                <td>Taxe foncière mensualisée (${fin.taxe_fonciere_estimated ? "estimée" : "réelle"} : ${fmtEur(fin.taxe_fonciere_an)}/an)</td>
                <td>+ ${fmtEur(fin.monthly_tax)} / mois</td>
              </tr>
              <tr><td>Énergie chauffage &amp; élec DPE (${fmtEur(fin.energy_an)}/an)</td><td>+ ${fmtEur(fin.monthly_energy)} / mois</td></tr>
              <tr><td>Provision entretien / charges (${fmtEur(fin.charges_an)}/an)</td><td>+ ${fmtEur(fin.monthly_charges)} / mois</td></tr>
              <tr style="background:var(--accent-soft); font-size:0.95rem;">
                <td><strong>VRAI COÛT MENSUEL TOUT COMPRIS</strong></td>
                <td><strong style="color:var(--accent); font-size:1.1rem;">${fmtEur(fin.true_monthly_cost)} / mois</strong></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="editorial-section">
          <div class="section-header">
            <h3>Postes de Travaux &amp; Diagnostic DPE ADEME</h3>
            <span class="tag">Fourchette : ${fmtEur(ai.works_total_min)} – ${fmtEur(ai.works_total_max)}</span>
          </div>
          ${
            worksRows
              ? `<table class="data-table">
                  <thead><tr><th>Poste de travaux</th><th>Priorité</th><th>Estimation</th></tr></thead>
                  <tbody>${worksRows}</tbody>
                </table>`
              : `<p style="font-size:0.88rem; color:var(--ink-muted);">Aucun gros poste de travaux détecté automatiquement.</p>`
          }

          ${
            (dpeData.records || []).length
              ? `<div style="padding-top:0.75rem; border-top:1px solid var(--border); font-size:0.84rem;">
                  <strong>DPE ADEME trouvé à proximité (${dpeData.records[0].numero_dpe || "Base Nationale"}) :</strong><br/>
                  Chauffage : ${dpeData.records[0].type_energie_chauffage || "—"} (${dpeData.records[0].type_generateur_chauffage || "—"})<br/>
                  Isolation murs : <strong>${dpeData.records[0].qualite_isolation_murs || "—"}</strong> · Menuiseries : <strong>${dpeData.records[0].qualite_isolation_menuiseries || "—"}</strong> · Conso : ${dpeData.records[0].conso_kwh_m2_an || "?"} kWh/m²/an
                </div>`
              : ""
          }
        </div>
      </div>

      <!-- SECTION 4: RISQUES 76 (MARNIÈRES / ARGILES / SEVESO) & VENTES NOTARIÉES DVF -->
      <div class="editorial-grid">
        <div class="editorial-section">
          <div class="section-header">
            <h3>Risques Naturels &amp; Marnières 76</h3>
            <span class="tag">Parcelle ${cad.section || ""}${cad.numero || ""} (${cad.contenance_m2 || "?"} m²)</span>
          </div>
          <table class="data-table">
            <tbody>
              <tr>
                <td><strong>Marnières &amp; Cavités souterraines (76)</strong></td>
                <td>
                  <strong style="color:${geo.cavites_100m_count > 0 ? "var(--danger-ink)" : geo.cavites_500m_count > 0 ? "var(--warn-ink)" : "var(--ok-ink)"};">
                    ${geo.cavites_100m_count || 0} à moins de 100 m · ${geo.cavites_500m_count || 0} dans les 500 m
                  </strong>
                  ${geo.nearest_cavite_m ? `(Plus proche à ${geo.nearest_cavite_m} m)` : "(Aucune à proximité)"}
                </td>
              </tr>
              <tr>
                <td><strong>Retrait-Gonflement des Argiles (Fissures)</strong></td>
                <td>Aléa <strong>${geo.argiles_exposition || "Faible"}</strong> (Code ${geo.argiles_code || 1}/3)</td>
              </tr>
              <tr>
                <td><strong>Inondation / PPRI &amp; Arrêtés CatNat</strong></td>
                <td>${geo.inondation_risque ? "Présence de zonage inondation communal" : "Hors zone inondable majeure"} (${geo.catnat_count || 0} arrêtés CatNat sur la commune)</td>
              </tr>
              <tr>
                <td><strong>Sites Industriels ICPE &amp; Seveso</strong></td>
                <td>${geo.seveso_count || 0} site Seveso (&lt;2 km) · ${geo.icpe_1km_count || 0} installation(s) ICPE (&lt;1 km)</td>
              </tr>
              <tr>
                <td><strong>Zonage PLU &amp; Ensoleillement PVGIS</strong></td>
                <td>Zone PLU : <strong>${cad.plu_zone || "Urbaine"}</strong> (${cad.plu_libelle || ""}) · Solaire : ${sol.yearly_irradiation_kwh_m2 || "1150"} kWh/m²/an (${sol.sunshine_quality || ""})</td>
              </tr>
              <tr>
                <td><strong>Nuisances Sonores (OSM)</strong></td>
                <td>
                  ${
                    (osm.noise_sources || []).length
                      ? osm.noise_sources.map((n) => `${n.type} (${n.name}) à ${n.distance_m} m`).join(" · ")
                      : "Aucune voie ferrée, autoroute ou ligne HT à moins de 300 m"
                  }
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="editorial-section">
          <div class="section-header">
            <h3>Ventes Notariées Réelles (DVF 76) autour du bien</h3>
            <span class="tag">${dvf.count || 0} ventes (${dvf.verdict || ""})</span>
          </div>
          <div style="display:flex; justify-content:space-between; padding:0.5rem 0; border-bottom:1px solid var(--border); font-size:0.85rem;">
            <span>Bas (Q25) : <strong>${fmtEur(dvf.q25_price_m2)}/m²</strong></span>
            <span>Médiane DVF : <strong style="color:var(--accent);">${fmtEur(dvf.median_price_m2)}/m²</strong></span>
            <span>Haut (Q75) : <strong>${fmtEur(dvf.q75_price_m2)}/m²</strong></span>
          </div>
          <div style="max-height:240px; overflow-y:auto;">
            <table class="data-table">
              <thead>
                <tr><th>Date</th><th>Voie</th><th>Prix net</th><th>Bâti</th><th>Terrain</th><th>€/m²</th><th>Dist.</th></tr>
              </thead>
              <tbody>${dvfRows || "<tr><td colspan='7'>Aucune vente trouvée dans ce rayon</td></tr>"}</tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- SECTION 5: ÉCOLES / COMMODITÉS & CHECKLIST DE VISITE INTERACTIVE -->
      <div class="editorial-grid">
        <div class="editorial-section">
          <div class="section-header">
            <h3>Écoles (IPS) &amp; Commerces de Proximité</h3>
            <span class="tag">${osm.walkability_label || ""}</span>
          </div>
          <div style="font-size:0.86rem;">
            <strong>Commerces &amp; Santé (&lt; 1 km) :</strong>
            <p style="color:var(--ink-muted); margin:0.25rem 0 0.65rem;">
              Supermarchés : ${(osm.supermarkets || []).slice(0, 3).map((s) => `${s.name} (${s.distance_m} m)`).join(", ") || "Aucun &lt; 1 km"}<br/>
              Boulangeries / Frais : ${(osm.bakeries || []).slice(0, 3).map((s) => `${s.name} (${s.distance_m} m)`).join(", ") || "Aucune &lt; 1 km"}<br/>
              Santé / Pharmacies : ${(osm.health || []).slice(0, 3).map((s) => `${s.name} (${s.distance_m} m)`).join(", ") || "Aucune &lt; 1 km"}
            </p>
          </div>
          <div style="max-height:190px; overflow-y:auto;">
            <table class="data-table">
              <thead><tr><th>Établissement scolaire</th><th>Type</th><th>IPS (Niveau social)</th><th>Distance</th></tr></thead>
              <tbody>
                ${(sch.schools || [])
                  .slice(0, 6)
                  .map(
                    (s) => `
                    <tr>
                      <td>${s.nom}</td>
                      <td>${s.type} (${s.statut})</td>
                      <td><strong>${s.ips ? s.ips : "—"}</strong></td>
                      <td>${s.distance_m} m</td>
                    </tr>
                  `
                  )
                  .join("")}
              </tbody>
            </table>
          </div>
        </div>

        <div class="editorial-section">
          <div class="section-header">
            <h3>Fiche de Visite Interactive &amp; Notes du Couple</h3>
            <span class="tag">Cochez pendant l'appel ou la visite</span>
          </div>
          <div style="display:flex; flex-direction:column; max-height:220px; overflow-y:auto;">
            ${checklistItems}
          </div>
          <div class="form-group" style="margin-top:0.5rem;">
            <label for="visitNotesField">Vos notes personnelles (ressenti, défauts vus sur place, retour de Madame...)</label>
            <textarea id="visitNotesField" rows="3" onchange="updateFinancialField(${item.id}, 'user_notes', this.value)" placeholder="Notez ici vos observations de visite...">${item.user_notes || ""}</textarea>
          </div>
        </div>
      </div>
    </article>
  `;

  initPropertyMap(item);
}

function initPropertyMap(item) {
  const mapEl = document.getElementById("propertyMap");
  if (!mapEl || !item.lat || !item.lon) return;

  if (LEAFLET_MAP) {
    LEAFLET_MAP.remove();
    LEAFLET_MAP = null;
  }

  LEAFLET_MAP = L.map("propertyMap").setView([item.lat, item.lon], 15);
  LEAFLET_TILE_LAYER = L.tileLayer(getTileLayerUrl(), {
    attribution: "© OpenStreetMap · CARTO · IGN · DVF · Géorisques",
    maxZoom: 19,
  }).addTo(LEAFLET_MAP);

  const enr = item.enrichment || {};

  // 1. Cadastral parcel polygon via Leaflet GeoJSON with style() and onEachFeature() per Context7 Leaflet docs
  const parcelGeom = enr.cadastre?.parcel_geometry;
  if (parcelGeom) {
    L.geoJSON(parcelGeom, {
      style() {
        return { color: "#0f4c3a", weight: 3, fillColor: "#0f4c3a", fillOpacity: 0.2 };
      },
      onEachFeature(_feature, layer) {
        layer.bindPopup(
          `Parcelle cadastrale ${enr.cadastre.section}${enr.cadastre.numero} (${enr.cadastre.contenance_m2} m²)`
        );
      },
    }).addTo(LEAFLET_MAP);
  }

  // 2. Main draggable property marker
  const mainMarker = L.marker([item.lat, item.lon], { draggable: true })
    .addTo(LEAFLET_MAP)
    .bindPopup(`<strong>${item.title}</strong><br/>${fmtEur(item.price)} — Déplacez-moi pour recalculer à une adresse exacte`);

  mainMarker.on("dragend", async (ev) => {
    const pos = ev.target.getLatLng();
    if (confirm(`Recalculer toute l'analyse (Cadastre, Risques, Trajet Astuce, DVF) sur ce nouveau point GPS (${pos.lat.toFixed(5)}, ${pos.lng.toFixed(5)}) ?`)) {
      await fetch(`/api/listings/${item.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lat: pos.lat, lon: pos.lng, reanalyze: true }),
      });
      await loadInitialData();
      selectListing(item.id);
    }
  });

  // 3. DVF recent sales (Green circles)
  (enr.dvf?.sales || []).slice(0, 18).forEach((s) => {
    if (s.lat && s.lon) {
      L.circleMarker([s.lat, s.lon], {
        radius: 6,
        color: "#14532d",
        fillColor: "#16a34a",
        fillOpacity: 0.85,
      })
        .bindPopup(
          `<strong>Vente DVF (${s.date_mutation})</strong><br/>${s.type_local} ${s.surface_bati} m² (Terrain ${Math.round(s.surface_terrain || 0)} m²)<br/><strong>${fmtEur(s.valeur_fonciere)} (${fmtEur(s.prix_m2)}/m²)</strong>`
        )
        .addTo(LEAFLET_MAP);
    }
  });

  // 4. Nearby Astuce stops (Purple circles)
  (enr.mobility?.madame?.nearby_astuce_stops || []).forEach((st) => {
    if (st.lat && st.lon) {
      L.circleMarker([st.lat, st.lon], {
        radius: 7,
        color: "#581c87",
        fillColor: "#7e22ce",
        fillOpacity: 0.9,
      })
        .bindPopup(`<strong>Arrêt Astuce : ${st.stop_name}</strong><br/>À ${st.distance_m} m (${st.walk_min} min à pied)<br/>Lignes : ${(st.lines || []).join(", ")}`)
        .addTo(LEAFLET_MAP);
    }
  });

  // 5. Cavités / Marnières 76 (Red warning circles + 65m safety perimeter)
  (enr.georisques?.cavites_list || []).forEach((cav) => {
    if (cav.lat && cav.lon) {
      L.circle([cav.lat, cav.lon], {
        radius: 65,
        color: "#991b1b",
        fillColor: "#dc2626",
        fillOpacity: 0.25,
      })
        .bindPopup(`<strong>Cavité / Marnière 76 (${cav.type})</strong><br/>ID: ${cav.id} — Distance: ${cav.distance_m} m`)
        .addTo(LEAFLET_MAP);
    }
  });
}

async function updateListingStatus(id, status) {
  await fetch(`/api/listings/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  await loadInitialData();
  selectListing(id);
}

async function updateFinancialField(id, field, value) {
  const payload = {};
  payload[field] = field === "user_notes" ? value : Number(value);
  const res = await fetch(`/api/listings/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.ok) {
    const updated = await res.json();
    ALL_LISTINGS = ALL_LISTINGS.map((x) => (x.id === id ? updated : x));
    renderSidebar();
    renderDetail(updated);
  }
}

async function toggleChecklistItem(id, idx, checked) {
  const item = ALL_LISTINGS.find((x) => x.id === id);
  if (!item) return;
  const list =
    item.visit_checklist && item.visit_checklist.length
      ? [...item.visit_checklist]
      : [...(item.ai_audit?.visit_questions || [])];
  if (list[idx]) {
    list[idx].checked = checked;
    await fetch(`/api/listings/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ visit_checklist: list }),
    });
  }
}

async function triggerDeepAiAudit(id) {
  const btn = document.getElementById("btnRunDeepAi");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Audit IA agy (Gemini Pro) en cours...";
  }
  try {
    const res = await fetch(`/api/listings/${id}/reanalyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ deep_ai: true }),
    });
    if (res.ok) {
      const updated = await res.json();
      ALL_LISTINGS = ALL_LISTINGS.map((x) => (x.id === id ? updated : x));
      renderSidebar();
      renderDetail(updated);
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Relancer l'Audit IA Approfondi (agy)";
    }
  }
}

async function removeListing(id) {
  if (!confirm("Supprimer définitivement cette annonce ?")) return;
  await fetch(`/api/listings/${id}`, { method: "DELETE" });
  CURRENT_ID = null;
  await loadInitialData();
}

/* Event Listeners */
document.addEventListener("DOMContentLoaded", () => {
  setupDialogs();
  updateThemeButtonLabel();
  loadInitialData();

  const themeBtn = document.getElementById("btnThemeToggle");
  if (themeBtn) {
    themeBtn.addEventListener("click", toggleColorScheme);
  }
  window.addEventListener("storage", (e) => {
    if (e.key === "color-scheme") {
      const meta = document.querySelector('meta[name="color-scheme"]');
      if (meta) meta.content = e.newValue ?? "light dark";
      updateThemeButtonLabel();
      if (LEAFLET_TILE_LAYER) LEAFLET_TILE_LAYER.setUrl(getTileLayerUrl());
    }
  });

  document.getElementById("filterStatus").addEventListener("change", renderSidebar);

  document.getElementById("btnOpenAddModal").addEventListener("click", () => {
    document.getElementById("addListingDialog").showModal();
  });

  document.getElementById("btnOpenDetectiveModal").addEventListener("click", () => {
    document.getElementById("detectiveDialog").showModal();
  });

  document.getElementById("btnOpenCompareModal").addEventListener("click", () => {
    renderComparisonTable();
    document.getElementById("compareDialog").showModal();
  });

  document.getElementById("btnOpenSettingsModal").addEventListener("click", () => {
    document.getElementById("s_target_budget").value = SETTINGS.target_budget || 250000;
    document.getElementById("s_max_budget").value = SETTINGS.max_budget || 275000;
    document.getElementById("s_apport").value = SETTINGS.apport || 80000;
    document.getElementById("s_loan_years").value = SETTINGS.loan_years || 25;
    document.getElementById("s_interest_rate").value = SETTINGS.interest_rate || 3.35;
    document.getElementById("s_insurance_rate").value = SETTINGS.insurance_rate || 0.34;
    document.getElementById("s_min_bedrooms").value = SETTINGS.min_bedrooms || 2;
    document.getElementById("s_madame_max").value = SETTINGS.madame_max_transit_min || 45;
    document.getElementById("settingsDialog").showModal();
  });

  document.getElementById("addListingForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("btnSubmitListing");
    btn.disabled = true;
    btn.textContent = "Interrogation des API Open Data (DVF, Astuce, Géorisques, IGN)...";

    const fd = new FormData(e.target);
    const payload = {};
    fd.forEach((v, k) => {
      if (v !== "") payload[k] = v;
    });
    ["price", "surface_m2", "land_m2", "rooms", "bedrooms", "taxe_fonciere", "travaux_estimes"].forEach((k) => {
      if (payload[k]) payload[k] = Number(payload[k]);
    });

    try {
      const res = await fetch("/api/listings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        const created = await res.json();
        document.getElementById("addListingDialog").close();
        e.target.reset();
        await loadInitialData();
        selectListing(created.id);
      }
    } finally {
      btn.disabled = false;
      btn.textContent = "Lancer l'analyse 360° Open Data + IA";
    }
  });

  document.getElementById("detectiveForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const box = document.getElementById("detectiveResults");
    box.innerHTML = "<p style='color:var(--ink-muted);'>Recherche dans les diagnostics ADEME DPE en cours...</p>";
    const res = await fetch("/api/detective-dpe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        postcode: document.getElementById("det_cp").value,
        surface_m2: Number(document.getElementById("det_surf").value || 0),
        dpe_letter: document.getElementById("det_dpe").value,
        ges_letter: document.getElementById("det_ges").value,
      }),
    });
    const data = await res.json();
    const cands = data.candidates || [];
    if (!cands.length) {
      box.innerHTML = "<p style='color:var(--warn-ink);'>Aucun DPE correspondant trouvé avec ces critères exacts.</p>";
      return;
    }
    box.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Adresse exacte trouvée (BAN)</th><th>Surface</th><th>DPE / GES</th><th>Année</th><th>Chauffage</th><th>Action</th></tr></thead>
        <tbody>
          ${cands
            .map(
              (c) => `
              <tr>
                <td><strong>${c.address}</strong></td>
                <td>${c.surface_m2} m²</td>
                <td>DPE ${c.dpe} / GES ${c.ges}</td>
                <td>${c.construction_year || "—"}</td>
                <td>${c.type_energie_chauffage || "—"}</td>
                <td>
                  <button class="btn btn-sm btn-primary" onclick="useDetectiveAddress('${(c.address || "").replace(/'/g, "\\'")}', ${c.surface_m2 || 0}, '${c.dpe || ""}', '${c.ges || ""}')">
                    Utiliser cette adresse
                  </button>
                </td>
              </tr>
            `
            )
            .join("")}
        </tbody>
      </table>
    `;
  });

  document.getElementById("settingsForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      target_budget: Number(document.getElementById("s_target_budget").value),
      max_budget: Number(document.getElementById("s_max_budget").value),
      apport: Number(document.getElementById("s_apport").value),
      loan_years: Number(document.getElementById("s_loan_years").value),
      interest_rate: Number(document.getElementById("s_interest_rate").value),
      insurance_rate: Number(document.getElementById("s_insurance_rate").value),
      min_bedrooms: Number(document.getElementById("s_min_bedrooms").value),
      madame_max_transit_min: Number(document.getElementById("s_madame_max").value),
    };
    await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    document.getElementById("settingsDialog").close();
    await loadInitialData();
    if (CURRENT_ID) selectListing(CURRENT_ID);
  });
});

function useDetectiveAddress(address, surf, dpe, ges) {
  document.getElementById("detectiveDialog").close();
  document.getElementById("f_address").value = address;
  if (surf) document.getElementById("f_surface").value = surf;
  if (dpe) document.getElementById("f_dpe").value = dpe;
  if (ges) document.getElementById("f_ges").value = ges;
  document.getElementById("addListingDialog").showModal();
}

function renderComparisonTable() {
  const box = document.getElementById("compareTableContainer");
  if (!ALL_LISTINGS.length) {
    box.innerHTML = "<p>Aucun bien à comparer.</p>";
    return;
  }
  box.innerHTML = `
    <table class="data-table">
      <thead>
        <tr>
          <th>Bien</th>
          <th>Score 360°</th>
          <th>Prix affiché</th>
          <th>Vrai Coût / mois</th>
          <th>Prix/m² vs DVF</th>
          <th>Surface / Terrain</th>
          <th>Chambres / DPE</th>
          <th>Trajet Madame</th>
          <th>Trajet Monsieur</th>
          <th>Marnières 500m</th>
          <th>Offre conseillée</th>
        </tr>
      </thead>
      <tbody>
        ${ALL_LISTINGS.map((it) => {
          const dvf = it.enrichment?.dvf || {};
          const geo = it.enrichment?.georisques || {};
          const fin = it.finance || {};
          return `
            <tr onclick="document.getElementById('compareDialog').close(); selectListing(${it.id});" style="cursor:pointer;">
              <td><strong>${it.title}</strong><br/><small style="color:var(--ink-muted)">${it.city || ""}</small></td>
              <td><span class="score-badge ${scoreClass(it.score_total)}">${it.score_total}/100</span></td>
              <td><strong>${fmtEur(it.price)}</strong></td>
              <td><strong style="color:var(--accent)">${fmtEur(it.true_monthly_cost)}/mois</strong></td>
              <td>${fmtEur(dvf.listing_price_m2)}/m² <small>(${dvf.diff_vs_median_pct > 0 ? "+" : ""}${dvf.diff_vs_median_pct || 0}%)</small></td>
              <td>${it.surface_m2} m² / ${Math.round(it.land_m2 || 0)} m²</td>
              <td>${it.bedrooms} ch · DPE ${it.dpe_letter || "?"}</td>
              <td><span class="tag ${it.madame_transit_min <= 45 ? "tag-ok" : "tag-alert"}">${it.madame_transit_min} min</span></td>
              <td>${it.monsieur_drive_min} min</td>
              <td>${geo.cavites_500m_count || 0} (${geo.nearest_cavite_m ? geo.nearest_cavite_m + " m" : "ras"})</td>
              <td><strong style="color:var(--ok-ink)">${fmtEur(fin.recommended_offer_price)}</strong></td>
            </tr>
          `;
        }).join("")}
      </tbody>
    </table>
  `;
}
