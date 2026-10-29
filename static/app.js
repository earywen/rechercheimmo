/* Recherche Immo IA — Frontend Application Logic (Impeccable UX & Context7 Compliant) */

let ALL_LISTINGS = [];
let CURRENT_ID = null;
let CURRENT_TAB = "tab-synthese";
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
  return "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
}

function updateThemeButtonLabel() {
  const dark = isDarkModeActive();
  document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
  const btn = document.getElementById("btnThemeToggle");
  if (!btn) return;
  btn.textContent = dark ? "Mode clair" : "Mode sombre";
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
  if (score >= 72) return "var(--ok-bar)";
  if (score >= 52) return "var(--warn-bar)";
  return "var(--danger-bar)";
}

function switchDossierTab(tabId) {
  CURRENT_TAB = tabId;
  document.querySelectorAll(".dossier-tabs .tab-btn").forEach((btn) => {
    const isTarget = btn.getAttribute("data-tab") === tabId;
    btn.setAttribute("aria-selected", isTarget ? "true" : "false");
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === tabId);
  });
  if (tabId === "tab-synthese" && LEAFLET_MAP) {
    setTimeout(() => LEAFLET_MAP.invalidateSize(), 60);
  }
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
    selectListing(CURRENT_ID || ALL_LISTINGS[0].id);
  } else {
    document.getElementById("detailContainer").innerHTML = `
      <div class="dossier-sheet" style="text-align:center; padding: 3rem;">
        <h2>Aucune annonce enregistrée</h2>
        <p style="color: var(--ink-muted); margin: 0.75rem auto 1.25rem;">Ajoutez une annonce ou utilisez l'extension Chrome sur LeBonCoin, SeLoger ou Bien'ici.</p>
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
            <div class="score-badge ${sClass}">${item.score_total}</div>
          </div>
          <div class="listing-price-row">
            <span class="listing-price">${fmtEur(item.price)}</span>
            <span class="listing-monthly">${fmtEur(item.true_monthly_cost)}/mois</span>
          </div>
          <div class="listing-meta">
            <span class="tag">${item.surface_m2 || "?"} m² · ${item.bedrooms || "?"} ch · DPE ${dpe}</span>
            <span class="tag ${mMin <= 45 ? "tag-ok" : "tag-alert"}">Mme ${mMin} min</span>
            ${dbCount > 0 ? `<span class="tag tag-alert">${dbCount} alerte${dbCount > 1 ? "s" : ""}</span>` : ""}
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
  const neigh = enr.neighborhood || {};
  const socio = neigh.socio || {};
  const edu = neigh.education || {};
  const apprec = neigh.appreciation || {};
  const walk15 = neigh.walkability_15min || {};

  const dpeLetter = (item.dpe_letter || "?").toUpperCase();
  const axesHtml = Object.values(sco.axes || {})
    .map(
      (ax) => `
      <div class="axis-row">
        <div class="axis-head">
          <span>${ax.label} <small style="color:var(--ink-muted)">(${ax.weight}%)</small></span>
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
        <div><strong>Point bloquant — ${db.title} :</strong> ${db.detail}</div>
      </div>
    `
    )
    .join("");

  const warningsHtml = (sco.warnings || [])
    .map(
      (w) => `
      <span class="highlight-pill notice-warn">
        <strong>Vigilance :</strong> ${w}
      </span>
    `
    )
    .join("");

  const strengthsHtml = (sco.strengths || [])
    .map(
      (st) => `
      <span class="highlight-pill notice-green">
        <strong>Atout :</strong> ${st}
      </span>
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

  const rawChecklist =
    item.visit_checklist && item.visit_checklist.length
      ? item.visit_checklist
      : ai.visit_questions || [];

  const checklistItems = rawChecklist
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

  const documents = item.documents || [];
  const documentsHtml =
    documents.length === 0
      ? `<div style="font-size:0.86rem; color:var(--ink-muted); font-style:italic; padding:0.75rem 0;">
          Aucun document déposé pour ce bien. Déposez un DPE officiel, un avis de taxe foncière ou une facture pour confronter l'annonce.
         </div>`
      : `<div class="documents-list">
          ${documents
            .map((doc) => {
              const sizeKb = Math.round((doc.size_bytes || 0) / 1024);
              const sizeLabel = sizeKb > 1024 ? `${(sizeKb / 1024).toFixed(1)} Mo` : `${sizeKb} Ko`;
              const hints = doc.detected_hints || {};
              let hintsBadges = "";
              if (hints.taxe_fonciere) {
                hintsBadges += `<span class="tag tag-ok">Taxe Foncière : ${hints.taxe_fonciere} €/an</span>`;
              }
              if (hints.dpe_letter) {
                hintsBadges += `<span class="tag tag-ok">DPE extrait : ${hints.dpe_letter}${hints.dpe_kwh ? ` (${hints.dpe_kwh} kWh/m²/an)` : ""}</span>`;
              }
              if (hints.facture_energie_an) {
                hintsBadges += `<span class="tag tag-ok">Facture annuelle : ${hints.facture_energie_an} €</span>`;
              }

              const hasText = (doc.extracted_chars || 0) > 0;
              const snippet = doc.extracted_snippet || "";

              return `
                <div class="document-row">
                  <div class="document-main">
                    <div class="document-header-line">
                      <span class="document-badge">${doc.doc_type || "Autre"}</span>
                      <span class="document-name">${doc.filename}</span>
                      <span class="document-meta">${sizeLabel} · ${doc.uploaded_at ? doc.uploaded_at.slice(0, 10) : ""}</span>
                      ${hasText ? `<span class="tag" style="font-size:0.7rem; padding:0.1rem 0.35rem;">Texte extrait (${doc.extracted_chars} car.)</span>` : ""}
                    </div>
                    ${hintsBadges ? `<div class="document-hints">${hintsBadges}</div>` : ""}
                    ${
                      snippet
                        ? `
                      <details style="margin-top:0.35rem; font-size:0.8rem; color:var(--ink-muted);">
                        <summary style="cursor:pointer; color:var(--accent);">Aperçu du texte extrait</summary>
                        <pre style="white-space:pre-wrap; font-family:monospace; font-size:0.75rem; background:var(--surface-subtle); padding:0.4rem; border-radius:4px; margin-top:0.25rem; max-height:150px; overflow-y:auto;">${snippet.replace(/</g, "&lt;").replace(/>/g, "&gt;")}</pre>
                      </details>
                    `
                        : ""
                    }
                  </div>
                  <div class="document-actions">
                    <a class="btn btn-sm" href="/api/listings/${item.id}/documents/${doc.id}/download" download title="Télécharger le fichier">
                      📥 Télécharger
                    </a>
                    <button type="button" class="btn btn-sm btn-danger" onclick="deleteListingDocument(${item.id}, '${doc.id}')" title="Supprimer ce document">
                      🗑️
                    </button>
                  </div>
                </div>
              `;
            })
            .join("")}
        </div>`;

  const eduSummary = edu.summary || {};
  const collegesRows = (edu.colleges || []).slice(0, 4).map((c) => {
    const brevetTxt = c.brevet_reussite_pct
      ? `${c.brevet_reussite_pct}% réussite (${c.brevet_mentions_pct || 0}% mentions)`
      : (c.brevet?.taux_reussite ? `${c.brevet.taux_reussite}% réussite` : "DNB n.c.");
    return `
      <tr>
        <td><strong>${c.nom}</strong><br/><small style="color:var(--ink-muted)">${c.statut || "Public"} · ${c.commune || ""}</small></td>
        <td><strong>${c.ips ? c.ips : "—"}</strong></td>
        <td><span class="tag tag-ok">${brevetTxt}</span></td>
        <td>${c.distance_m || "?"} m</td>
      </tr>
    `;
  }).join("");

  const schoolsRows = (edu.maternelles_and_elementaires || []).slice(0, 5).map((s) => `
    <tr>
      <td><strong>${s.nom}</strong><br/><small style="color:var(--ink-muted)">${s.statut || "Public"} · ${s.type || "École"}</small></td>
      <td><strong>${s.ips ? s.ips : "—"}</strong> ${s.ips_label ? `<small style="color:var(--ink-muted)">(${s.ips_label})</small>` : ""}</td>
      <td>${s.distance_m || "?"} m</td>
    </tr>
  `).join("");

  const lyceesRows = (edu.lycees || []).slice(0, 3).map((l) => `
    <tr>
      <td><strong>${l.nom}</strong><br/><small style="color:var(--ink-muted)">${l.statut || "Public"} · ${l.commune || ""}</small></td>
      <td><strong>${l.ips ? l.ips : "—"}</strong></td>
      <td>${l.distance_m || "?"} m</td>
    </tr>
  `).join("");

  const campusList = (edu.higher_education_campus || []).map((cp) => `
    <li style="padding: 0.4rem 0; border-bottom: 1px solid var(--border); font-size: 0.84rem;">
      <strong>${cp.nom}</strong> ${cp.commune ? `<small style="color:var(--ink-muted)">(${cp.commune})</small>` : ""}<br/>
      <span style="color:var(--ink-muted);">${cp.filiere || cp.type || "Enseignement supérieur"} · <em>Accès : ${cp.acces || cp.access_info || "Réseau Astuce"}</em></span>
    </li>
  `).join("");

  const catalystsHtml = (apprec.catalysts || []).map((cat) => `
    <li style="padding: 0.5rem 0; border-bottom: 1px solid var(--border); font-size: 0.86rem; line-height: 1.45;">
      <strong>${cat.projet || cat.title || "Projet urbain"} :</strong>
      ${cat.impact || cat.description || ""}
      ${cat.potentiel ? `<span class="tag tag-ok" style="margin-left:0.4rem; display:inline-block; font-size:0.75rem;">${cat.potentiel}</span>` : ""}
    </li>
  `).join("");

  const streetViewUrl = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${item.lat},${item.lon}`;
  const geoportailUrl = `https://www.geoportail.gouv.fr/carte?c=${item.lon},${item.lat}&z=19&l0=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2::GEOPORTAIL:OGC:WMTS(1)&l1=CADASTRALPARCELS.PARCELLAIRE_EXPRESS::GEOPORTAIL:OGC:WMTS(1)&permalink=yes`;
  const offerTarget = ai.negotiation_strategy?.target_offer_eur || fin.recommended_offer_price;

  const container = document.getElementById("detailContainer");
  container.innerHTML = `
    <article class="dossier-sheet">
      <!-- 1. EN-TÊTE DE DÉCISION FIXE & ÉPURÉ -->
      <header class="hero-header">
        <div>
          <div style="display:flex; align-items:center; gap:0.6rem; flex-wrap:wrap; margin-bottom:0.45rem;">
            <span class="score-badge ${scoreClass(item.score_total)}" style="font-size:0.95rem; height:30px; padding:0 0.65rem;">
              Score ${item.score_total}/100
            </span>
            <span class="tag" style="font-size:0.82rem; font-weight:650;">${sco.verdict_badge || ""}</span>
            <select aria-label="Statut de suivi du bien" class="control-select" onchange="updateListingStatus(${item.id}, this.value)">
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
            ${item.source_url ? `· <a href="${item.source_url}" target="_blank">Annonce originale</a>` : ""}
          </div>
        </div>

        <div style="display:flex; gap:0.5rem; align-items:center; flex-wrap:wrap;">
          <button class="btn btn-primary btn-sm" id="btnRunDeepAi" onclick="triggerDeepAiAudit(${item.id})">
            Relancer l'Audit IA (agy)
          </button>
          <button class="btn btn-danger btn-sm" onclick="removeListing(${item.id})">
            Supprimer
          </button>
        </div>
      </header>

      <!-- 2. BANDEAU DES 4 INDICATEURS CLÉS DE DÉCISION -->
      <div class="metrics-strip">
        <div class="metric-cell">
          <span class="metric-label">Vrai Coût Mensuel</span>
          <span class="metric-val" style="color:var(--accent);">${fmtEur(fin.true_monthly_cost)}/mois</span>
          <span class="metric-sub">Crédit + TF + énergie + entretien</span>
        </div>
        <div class="metric-cell">
          <span class="metric-label">Prix &amp; Offre Conseillée</span>
          <span class="metric-val">${fmtEur(item.price)}</span>
          <span class="metric-sub">Offre cible : <strong style="color:var(--ok-ink);">${fmtEur(offerTarget)}</strong> (${fmtEur(dvf.listing_price_m2)}/m²)</span>
        </div>
        <div class="metric-cell">
          <span class="metric-label">Trajet Madame (Astuce)</span>
          <span class="metric-val" style="color:${mme.is_dealbreaker ? "var(--danger-ink)" : (mme.duration_min > 40 ? "var(--warn-ink)" : "var(--ok-ink)")};">${mme.duration_min || "?"} min</span>
          <span class="metric-sub">34 rue Cauchoise · Monsieur : ${mr.duration_min || "?"} min</span>
        </div>
        <div class="metric-cell">
          <span class="metric-label">Surface &amp; DPE</span>
          <span class="metric-val">${item.surface_m2 || "?"} m² · <span class="dpe-badge dpe-${dpeLetter}">${dpeLetter}</span></span>
          <span class="metric-sub">Terrain ${Math.round(item.land_m2 || cad.contenance_m2 || 0)} m² · ${item.bedrooms || "?"} chambres</span>
        </div>
      </div>

      <!-- 3. BARRE D'ONGLETS THÉMATIQUES (PROGRESSIVE DISCLOSURE) -->
      <nav class="dossier-tabs" role="tablist" aria-label="Sections du dossier immobilier">
        <button type="button" role="tab" class="tab-btn" data-tab="tab-synthese" aria-selected="true" onclick="switchDossierTab('tab-synthese')">
          1. Synthèse &amp; Carte
        </button>
        <button type="button" role="tab" class="tab-btn" data-tab="tab-budget" aria-selected="false" onclick="switchDossierTab('tab-budget')">
          2. Budget, DVF &amp; Travaux
          <span class="tab-count">${dvf.count || 0} ventes</span>
        </button>
        <button type="button" role="tab" class="tab-btn" data-tab="tab-quartier" aria-selected="false" onclick="switchDossierTab('tab-quartier')">
          3. Quartier, Écoles &amp; Cadre de Vie
          <span class="tab-count">${eduSummary.total_count || 0} étab.</span>
        </button>
        <button type="button" role="tab" class="tab-btn" data-tab="tab-visite" aria-selected="false" onclick="switchDossierTab('tab-visite')">
          4. Visite &amp; Documents
          <span class="tab-count">${documents.length} doc${documents.length > 1 ? "s" : ""} · ${rawChecklist.length} pts</span>
        </button>
      </nav>

      <!-- ONGLET 1 : SYNTHÈSE, VERDICT IA & CARTE -->
      <section id="tab-synthese" role="tabpanel" class="tab-panel active">
        ${dealbreakersHtml ? `<div class="alerts-list">${dealbreakersHtml}</div>` : ""}
        ${warningsHtml || strengthsHtml ? `<div class="highlights-strip">${warningsHtml}${strengthsHtml}</div>` : ""}

        <div class="editorial-grid synthese-grid">
          <div class="editorial-section">
            <div class="section-header">
              <h3>Score 360° &amp; Synthèse IA</h3>
              <span class="tag">${(ai.engine || "").includes("agy") ? "Gemini Pro (agy)" : "Analyse IA"}</span>
            </div>
            <p style="font-size:0.9rem; color:var(--ink);">
              ${ai.executive_summary || "Analyse disponible."}
            </p>
            <div style="display:flex; flex-direction:column; gap:0.55rem; margin-top:0.25rem;">
              ${
                ai.neighborhood_verdict
                  ? `<div class="verdict-callout">
                      <strong>Quartier &amp; Sociologie (INSEE)</strong>
                      <div>${ai.neighborhood_verdict}</div>
                    </div>`
                  : ""
              }
              ${
                ai.education_verdict
                  ? `<div class="verdict-callout">
                      <strong>Écoles &amp; Réussite des Enfants</strong>
                      <div>${ai.education_verdict}</div>
                    </div>`
                  : ""
              }
              ${
                ai.appreciation_verdict
                  ? `<div class="verdict-callout">
                      <strong>Valorisation Patrimoniale &amp; Avenir</strong>
                      <div>${ai.appreciation_verdict}</div>
                    </div>`
                  : ""
              }
              <div style="margin-top:0.35rem; display:flex; flex-direction:column; gap:0.55rem;">
                ${axesHtml}
              </div>
            </div>
          </div>

          <div class="editorial-section">
            <div class="section-header">
              <h3>Carte Cadastrale &amp; Environnement</h3>
              <span class="tag">Marqueur déplaçable</span>
            </div>
            <div id="propertyMap"></div>
            <div style="display:flex; gap:0.85rem; flex-wrap:wrap; font-size:0.8rem; color:var(--ink-muted);">
              <span><strong>Bleu :</strong> Parcelle ${cad.section ? `(${cad.section}${cad.numero})` : "&amp; Bien"}</span>
              <span><strong>Vert :</strong> Ventes DVF</span>
              <span><strong>Violet :</strong> Arrêts Astuce</span>
              <span><strong>Rouge :</strong> Marnières 76</span>
            </div>
          </div>

          <div class="editorial-section span-2-laptop">
            <div class="section-header">
              <h3>Décryptage de l'Annonce vs Open Data</h3>
              <span class="tag">Vérification auto</span>
            </div>
            <ul style="display:flex; flex-direction:column; gap:0.65rem; padding-left:1.2rem; font-size:0.88rem; color:var(--ink);">
              ${(ai.ad_decryption || []).map((pt) => `<li>${pt}</li>`).join("")}
            </ul>
          </div>
        </div>
      </section>

      <!-- ONGLET 2 : BUDGET, DVF & TRAVAUX -->
      <section id="tab-budget" role="tabpanel" class="tab-panel">
        <div class="editorial-grid three-col">
          <div class="editorial-section">
            <div class="section-header">
              <h3>Coût Mensuel Tout Compris</h3>
              <span class="tag">${fin.loan_years} ans à ${fin.interest_rate_pct}%</span>
            </div>
            <table class="data-table">
              <tbody>
                <tr><td>Prix d'achat affiché</td><td><strong>${fmtEur(fin.price)}</strong></td></tr>
                <tr><td>Frais de notaire (~7,8% ancien)</td><td>${fmtEur(fin.notary_fees)}</td></tr>
                <tr>
                  <td>Budget travaux retenu (modifiable)</td>
                  <td>
                    <input type="number" aria-label="Budget travaux retenu" value="${fin.travaux_estimes}" onchange="updateFinancialField(${item.id}, 'travaux_estimes', this.value)" style="width:115px; background:var(--bg); color:var(--ink); border:1px solid var(--border-strong); padding:0.2rem 0.45rem; border-radius:4px;" /> €
                  </td>
                </tr>
                <tr><td><strong>Coût total de l'opération</strong></td><td><strong>${fmtEur(fin.total_project_cost)}</strong> (Emprunt : ${fmtEur(fin.loan_amount)})</td></tr>
                <tr><td>Mensualité Crédit + Assurance</td><td><strong>${fmtEur(fin.monthly_mortgage)} / mois</strong></td></tr>
                <tr>
                  <td>Taxe foncière (${fin.taxe_fonciere_estimated ? "estimée" : "réelle"} : ${fmtEur(fin.taxe_fonciere_an)}/an)</td>
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

            <div class="section-header" style="margin-top:0.5rem;">
              <h3>Postes de Travaux Estimés</h3>
              <span class="tag">${fmtEur(ai.works_total_min)} – ${fmtEur(ai.works_total_max)}</span>
            </div>
            ${
              worksRows
                ? `<table class="data-table">
                    <thead><tr><th>Poste</th><th>Priorité</th><th>Estimation</th></tr></thead>
                    <tbody>${worksRows}</tbody>
                  </table>`
                : `<p style="font-size:0.88rem; color:var(--ink-muted);">Aucun gros poste de travaux détecté automatiquement.</p>`
            }
          </div>

          <div class="editorial-section">
            <div class="section-header">
              <h3>Stratégie de Négociation &amp; Offre</h3>
              <span class="tag tag-ok">Marge : -${fmtEur(fin.potential_discount_eur)} (-${fin.potential_discount_pct}%)</span>
            </div>
            <div class="notice-bar notice-green" style="flex-direction:column; gap:0.4rem;">
              <strong>Prix d'offre recommandé : ${fmtEur(offerTarget)}</strong>
              <ul style="padding-left:1.2rem; font-size:0.85rem; color:var(--ink);">
                ${(ai.negotiation_strategy?.arguments || []).map((arg) => `<li>${arg}</li>`).join("")}
              </ul>
            </div>

            <div class="section-header" style="margin-top:0.5rem;">
              <h3>Ventes Notariées DVF (Secteur)</h3>
              <span class="tag">${dvf.count || 0} actes (${dvf.verdict || ""})</span>
            </div>
            <div style="display:flex; justify-content:space-between; padding:0.4rem 0; border-bottom:1px solid var(--border); font-size:0.85rem;">
              <span>Bas (Q25) : <strong>${fmtEur(dvf.q25_price_m2)}/m²</strong></span>
              <span>Médiane DVF : <strong style="color:var(--accent);">${fmtEur(dvf.median_price_m2)}/m²</strong></span>
              <span>Haut (Q75) : <strong>${fmtEur(dvf.q75_price_m2)}/m²</strong></span>
            </div>
            <div style="max-height:280px; overflow-y:auto;">
              <table class="data-table">
                <thead>
                  <tr><th>Date</th><th>Voie</th><th>Prix net</th><th>Bâti</th><th>Terrain</th><th>€/m²</th><th>Dist.</th></tr>
                </thead>
                <tbody>${dvfRows || "<tr><td colspan='7'>Aucune vente trouvée dans ce rayon</td></tr>"}</tbody>
              </table>
            </div>
          </div>

          <div class="editorial-section span-2-laptop">
            <div class="section-header">
              <h3>Potentiel de Valorisation Patrimoniale</h3>
              <span class="tag tag-ok">${apprec.score_appreciation || 65}/100</span>
            </div>
            <div class="notice-bar notice-green">
              <div><strong>Verdict Avenir :</strong> ${apprec.verdict || "Bon potentiel de valorisation patrimoniale sur le secteur."}</div>
            </div>

            <table class="data-table">
              <tbody>
                <tr>
                  <td><strong>Tendance DVF 5 ans (Commune)</strong></td>
                  <td>
                    <strong style="color:var(--ok-ink); font-size:1.05rem;">
                      ${apprec.tendance_dvf_5ans_pct ? (apprec.tendance_dvf_5ans_pct > 0 ? "+" : "") + apprec.tendance_dvf_5ans_pct + "%" : "+8.5%"}
                    </strong>
                    <span style="font-size:0.8rem; color:var(--ink-muted);">sur 5 ans (${socio.nom || item.city})</span>
                  </td>
                </tr>
                <tr>
                  <td><strong>Réserve foncière cadastrale</strong></td>
                  <td>
                    <strong>Terrain de ${Math.round(item.land_m2 || cad.contenance_m2 || 0)} m²</strong> (Zone PLU ${cad.plu_zone || "Urbaine"})<br/>
                    <small style="color:var(--ink-muted);">${apprec.land_reserve?.commentaire || "Parcelle adéquate pour extension ou piscine sous réserve du PLU."}</small>
                  </td>
                </tr>
                <tr>
                  <td><strong>Plus-value verte (Rénovation DPE)</strong></td>
                  <td>
                    <strong>DPE actuel ${dpeLetter}</strong><br/>
                    <small style="color:var(--ink-muted);">${apprec.green_value?.commentaire || "Amélioration énergétique valorisante pour la revente."}</small>
                  </td>
                </tr>
              </tbody>
            </table>

            <div class="section-header" style="margin-top:0.4rem;">
              <h3>Catalyseurs &amp; Projets Métropole Rouen</h3>
              <span class="tag">Horizon 2025-2035</span>
            </div>
            <ul style="display:flex; flex-direction:column; gap:0.45rem; list-style:none;">
              ${catalystsHtml || "<li style='font-size:0.86rem; color:var(--ink-muted);'>Aucun grand chantier structurant identifié directement sur la commune.</li>"}
            </ul>
          </div>
        </div>
      </section>

      <!-- ONGLET 3 : QUARTIER, ÉCOLES & CADRE DE VIE -->
      <section id="tab-quartier" role="tabpanel" class="tab-panel">
        <div class="editorial-grid three-col">
          <!-- COLONNE 1 : SOCIOLOGIE INSEE & VILLE DU 1/4 D'HEURE -->
          <div class="editorial-section">
            <div class="section-header">
              <h3>Niveau de Vie &amp; Sociologie INSEE</h3>
              <span class="tag tag-ok">${socio.classe_prosperite || "Intermédiaire"}</span>
            </div>
            <div class="kpi-grid-4">
              <div class="kpi-stat">
                <span class="kpi-stat-label">Revenu médian UC</span>
                <span class="kpi-stat-value">${fmtEur(socio.revenu_median_uc || 22000)}/an</span>
                <span class="kpi-stat-sub">Rouen : 23 100 € · Fr : 23 800 €</span>
              </div>
              <div class="kpi-stat">
                <span class="kpi-stat-label">Taux de pauvreté</span>
                <span class="kpi-stat-value" style="color:${(socio.taux_pauvrete_pct || 15) > 20 ? "var(--danger-ink)" : "var(--ok-ink)"};">${socio.taux_pauvrete_pct || 15}%</span>
                <span class="kpi-stat-sub">France : 14.5%</span>
              </div>
              <div class="kpi-stat">
                <span class="kpi-stat-label">Cadres &amp; CSP+</span>
                <span class="kpi-stat-value">${socio.part_cadres_pct || 20}%</span>
                <span class="kpi-stat-sub">${socio.part_proprietaires_pct || 55}% de propriétaires</span>
              </div>
              <div class="kpi-stat">
                <span class="kpi-stat-label">Statut QPV</span>
                <span class="kpi-stat-value" style="font-size:0.92rem; color:${socio.has_qpv ? "var(--warn-ink)" : "var(--ok-ink)"};">${socio.has_qpv ? (socio.qpv_nom || "Zone QPV") : "Hors QPV"}</span>
                <span class="kpi-stat-sub">${socio.has_qpv ? "Quartier prioritaire proche" : "Quartier favorisé / sans QPV"}</span>
              </div>
            </div>

            <p style="font-size:0.88rem; color:var(--ink); line-height:1.5;">
              <strong>Diagnostic sociologique :</strong> ${socio.profil_socio || "Profil résidentiel standard de l'agglomération rouennaise."}
            </p>
            <p style="font-size:0.84rem; color:var(--ink-muted);">
              <strong>Marché de plein air :</strong> ${socio.marche_plein_air || "Marché hebdomadaire en centre-ville"}<br/>
              <strong>Atout cadre de vie :</strong> ${socio.atout_quartier || "Quartier résidentiel calme"}
            </p>

            <div class="section-header" style="margin-top:0.6rem;">
              <h3>Vie Quotidienne &amp; 15 min à Pied</h3>
              <span class="tag">${walk15.walk_score || 60}/100</span>
            </div>
            <div class="notice-bar notice-green">
              <div><strong>Diagnostic piéton :</strong> ${walk15.verdict || "Commerces de proximité accessibles."}</div>
            </div>
            <div style="font-size:0.85rem; color:var(--ink); line-height:1.65;">
              <p><strong>À 5 min à pied (&lt; 450 m) :</strong><br/>
              ${(walk15.immediate_5min || []).join(" · ") || "<span style='color:var(--ink-muted);'>Aucun commerce de première nécessité sous 450 m</span>"}</p>
              <p style="margin-top:0.35rem;"><strong>À 10 min à pied (&lt; 850 m) :</strong><br/>
              ${(walk15.easy_10min || []).join(" · ") || "<span style='color:var(--ink-muted);'>Courses d'appoint uniquement</span>"}</p>
              <p style="margin-top:0.35rem;"><strong>Nécessite voiture / vélo :</strong><br/>
              <span style="color:var(--ink-muted);">${(walk15.car_needed || []).join(" · ") || "Tous commerces à proximité"}</span></p>
            </div>
          </div>

          <!-- COLONNE 2 : PARCOURS ÉDUCATIF DE LA CRÈCHE AU SUPÉRIEUR -->
          <div class="editorial-section">
            <div class="section-header">
              <h3>Parcours Scolaire (Crèche au Supérieur)</h3>
              <span class="tag tag-ok">IPS moyen : ${eduSummary.average_ips || 100}</span>
            </div>
            <div class="notice-bar notice-green">
              <div><strong>Cadre éducatif :</strong> ${eduSummary.ips_verdict || "Mixité sociale standard favorable aux apprentissages."}</div>
            </div>

            <div class="section-header" style="margin-top:0.4rem;">
              <h4>Collèges de Rattachement (Brevet &amp; Mentions)</h4>
              <span class="tag">${(edu.colleges || []).length} collèges</span>
            </div>
            <table class="data-table">
              <thead><tr><th>Collège</th><th>IPS</th><th>Résultats DNB</th><th>Dist.</th></tr></thead>
              <tbody>${collegesRows || "<tr><td colspan='4'>Aucun collège sous 3 km</td></tr>"}</tbody>
            </table>

            <div class="section-header" style="margin-top:0.4rem;">
              <h4>Maternelles &amp; Élémentaires (&lt; 1,5 km)</h4>
              <span class="tag">${(edu.maternelles_and_elementaires || []).length} écoles</span>
            </div>
            <table class="data-table">
              <thead><tr><th>École</th><th>IPS</th><th>Distance</th></tr></thead>
              <tbody>${schoolsRows || "<tr><td colspan='3'>Aucune école sous 1,5 km</td></tr>"}</tbody>
            </table>

            <div class="section-header" style="margin-top:0.4rem;">
              <h4>Lycées de Secteur</h4>
              <span class="tag">${(edu.lycees || []).length} lycées</span>
            </div>
            <table class="data-table">
              <thead><tr><th>Lycée</th><th>IPS</th><th>Distance</th></tr></thead>
              <tbody>${lyceesRows || "<tr><td colspan='3'>Aucun lycée sous 4 km</td></tr>"}</tbody>
            </table>

            <div class="section-header" style="margin-top:0.4rem;">
              <h4>Pôles Universitaires &amp; Grandes Écoles</h4>
              <span class="tag">Métropole</span>
            </div>
            <ul style="display:flex; flex-direction:column; gap:0.25rem; list-style:none;">
              ${campusList}
            </ul>
          </div>

          <!-- COLONNE 3 : MOBILITÉ DU COUPLE & RISQUES 76 -->
          <div class="editorial-section span-2-laptop">
            <div class="section-header">
              <h3>Mobilité du Couple (Astuce &amp; Voiture)</h3>
              <span class="tag ${mme.is_dealbreaker ? "tag-alert" : "tag-ok"}">${mme.status_label || ""}</span>
            </div>
            <div class="commute-row">
              <div style="display:flex; justify-content:space-between; align-items:baseline;">
                <strong>Madame (Transport Astuce → 34 rue Cauchoise, Rouen)</strong>
                <span style="font-size:1.2rem; font-weight:800; color:${mme.is_dealbreaker ? "var(--danger-ink)" : (mme.duration_min > 40 ? "var(--warn-ink)" : "var(--ok-ink)")};">${mme.duration_min || "?"} min</span>
              </div>
              <p style="font-size:0.88rem; color:var(--ink);">
                <strong>Itinéraire optimisé (pointe matin) :</strong> ${mme.best_itinerary ? mme.best_itinerary.details : "Calcul en cours"}<br/>
                <small style="color:var(--ink-muted);"><em>Heures creuses / journée : compter 45 à 48 min selon les fréquences et la marche (source MyAstuce).</em></small>
              </p>
              ${
                (mme.alternatives || []).length
                  ? `<div style="font-size:0.82rem; color:var(--ink-muted); margin-top:0.35rem;">
                      <strong>Autres options réseau Astuce :</strong>
                      <ul style="padding-left:1.1rem; margin-top:0.2rem;">
                        ${mme.alternatives.map((alt) => `<li>${alt.total_minutes} min : ${alt.details}</li>`).join("")}
                      </ul>
                    </div>`
                  : ""
              }
              ${
                (mme.nearby_astuce_stops || []).length
                  ? `<div style="font-size:0.8rem; color:var(--ink-muted); margin-top:0.35rem;">
                      <strong>Arrêts à pied :</strong>
                      ${mme.nearby_astuce_stops
                        .slice(0, 4)
                        .map((s) => `${s.stop_name} (${s.distance_m} m, lignes ${(s.lines || []).join(", ")})`)
                        .join(" · ")}
                    </div>`
                  : ""
              }
            </div>
            <div class="commute-row">
              <div style="display:flex; justify-content:space-between; align-items:baseline; gap:0.75rem;">
                <strong>Monsieur (Voiture → GINGER BURGEAP, Saint-Étienne-du-Rouvray)</strong>
                <span style="font-size:1.1rem; font-weight:800; color:var(--accent); white-space:nowrap; flex-shrink:0;">${mr.duration_min || "?"} min (${mr.distance_km || "?"} km)</span>
              </div>
              <p style="font-size:0.84rem; color:var(--ink-muted);">${mr.bridge_note || ""}</p>
            </div>

            <div class="section-header" style="margin-top:0.6rem;">
              <h3>Risques Naturels &amp; Marnières 76</h3>
              <span class="tag">Terrain ${Math.round(cad.contenance_m2 || item.land_m2 || 0)} m²</span>
            </div>
            <table class="data-table">
              <tbody>
                <tr>
                  <td><strong>Marnières &amp; Cavités souterraines (76)</strong></td>
                  <td>
                    <strong style="color:${geo.cavites_100m_count > 0 ? "var(--danger-ink)" : geo.cavites_500m_count > 0 ? "var(--warn-ink)" : "var(--ok-ink)"};">
                      ${geo.cavites_100m_count || 0} à &lt;100 m · ${geo.cavites_500m_count || 0} à &lt;500 m
                    </strong>
                    ${geo.nearest_cavite_m ? `(Plus proche à ${geo.nearest_cavite_m} m)` : "(Aucune à proximité)"}
                  </td>
                </tr>
                <tr>
                  <td><strong>Retrait-Gonflement des Argiles</strong></td>
                  <td>Aléa <strong>${geo.argiles_exposition || "Faible"}</strong> (Code ${geo.argiles_code || 1}/3)</td>
                </tr>
                <tr>
                  <td><strong>Inondation / PPRI &amp; CatNat</strong></td>
                  <td>${geo.inondation_risque ? "Zonage inondation communal" : "Hors zone inondable majeure"} (${geo.catnat_count || 0} arrêtés CatNat)</td>
                </tr>
                <tr>
                  <td><strong>Sites Industriels ICPE &amp; Seveso</strong></td>
                  <td>${geo.seveso_count || 0} site Seveso (&lt;2 km) · ${geo.icpe_1km_count || 0} ICPE (&lt;1 km)</td>
                </tr>
                <tr>
                  <td><strong>Zonage PLU &amp; Ensoleillement PVGIS</strong></td>
                  <td>Zone PLU : <strong>${cad.plu_zone || "Urbaine"}</strong> · Solaire : ${sol.yearly_irradiation_kwh_m2 || "1150"} kWh/m²/an (${sol.sunshine_quality || ""})</td>
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

            ${
              (dpeData.records || []).length
                ? `<div class="section-header" style="margin-top:0.5rem;">
                    <h3>Diagnostic DPE ADEME à proximité</h3>
                    <span class="tag">${dpeData.records[0].numero_dpe || "ADEME"}</span>
                  </div>
                  <div style="font-size:0.86rem;">
                    Chauffage : <strong>${dpeData.records[0].type_energie_chauffage || "—"}</strong> (${dpeData.records[0].type_generateur_chauffage || "—"})<br/>
                    Isolation murs : <strong>${dpeData.records[0].qualite_isolation_murs || "—"}</strong> · Menuiseries : <strong>${dpeData.records[0].qualite_isolation_menuiseries || "—"}</strong> · Conso : ${dpeData.records[0].conso_kwh_m2_an || "?"} kWh/m²/an
                  </div>`
                : ""
            }
          </div>
        </div>
      </section>

      <!-- ONGLET 4 : CHECKLIST DE VISITE, NOTES & COFFRE-FORT DOCUMENTS -->
      <section id="tab-visite" role="tabpanel" class="tab-panel">
        <div class="editorial-grid">
          <!-- Colonne Gauche : Questions agence & Notes -->
          <div class="editorial-section">
            <div class="section-header">
              <h3>Questions à poser à l'agence &amp; Points de vigilance</h3>
              <span class="tag">Interactif</span>
            </div>
            <div style="display:flex; flex-direction:column; margin-bottom:1.25rem;">
              ${checklistItems}
            </div>

            <div class="section-header">
              <h3>Notes Personnelles du Couple</h3>
              <span class="tag">Sauvegarde auto</span>
            </div>
            <div class="form-group">
              <label for="visitNotesField">Ressenti général, luminosité, bruit perçu sur place, retour de Madame et Monsieur :</label>
              <textarea id="visitNotesField" rows="5" onchange="updateFinancialField(${item.id}, 'user_notes', this.value)" placeholder="Notez ici vos observations pendant l'appel ou la visite...">${item.user_notes || ""}</textarea>
            </div>
          </div>

          <!-- Colonne Droite : Coffre-fort Documents Vendeur & Ingestion IA -->
          <div class="editorial-section">
            <div class="section-header">
              <h3>Pièces &amp; Documents Officiels</h3>
              <span class="tag tag-ok">Ingéré par l'IA</span>
            </div>
            <p style="font-size:0.86rem; color:var(--ink-muted); margin-bottom:0.75rem;">
              Déposez les pièces fournies par le propriétaire ou l'agence (DPE officiel, taxe foncière, factures d'énergie, diagnostics amiante/élec, devis). Le texte est automatiquement extrait et injecté dans l'audit IA (Gemini Pro) pour confronter l'annonce et recalculer vos mensualités réelles.
            </p>

            <div class="dropzone-container">
              <div style="display:flex; gap:0.5rem; align-items:center;">
                <label for="docTypeSelect" style="font-size:0.82rem; font-weight:600; white-space:nowrap; color:var(--ink);">Type de pièce :</label>
                <select id="docTypeSelect" style="flex:1; padding:0.4rem 0.5rem; font-size:0.84rem; background:var(--bg); border:1px solid var(--border-strong); border-radius:6px; color:var(--ink);">
                  <option value="DPE">DPE complet (Diagnostic Performance Énergétique)</option>
                  <option value="Taxe Foncière">Avis de Taxe Foncière (Imposition)</option>
                  <option value="Facture Énergie">Facture d'Énergie annuelle (EDF / Engie)</option>
                  <option value="Diagnostics">Diagnostics Techniques (Amiante / Élec / Plomb)</option>
                  <option value="Devis / Travaux">Devis d'Artisans ou Travaux réalisés</option>
                  <option value="PV AG / Copro">PV d'Assemblée Générale / Copropriété</option>
                  <option value="Autre" selected>Autre justificatif</option>
                </select>
              </div>

              <div class="dropzone-box" id="documentDropzone" onclick="document.getElementById('docFileInput').click()">
                <span class="dropzone-icon">📄</span>
                <div class="dropzone-prompt">Glissez-déposez une pièce ici ou cliquez pour parcourir</div>
                <div class="dropzone-hint">PDF, TXT, images (jusqu'à 25 Mo) · Extraction automatique de texte</div>
                <input type="file" id="docFileInput" style="display:none;" onchange="onDocumentFileSelected(${item.id}, this.files)" />
              </div>
            </div>

            <div class="section-header" style="margin-top:1rem; border-top:1px solid var(--border); padding-top:0.75rem;">
              <h3>Documents Enregistrés (${documents.length})</h3>
              ${documents.length > 0 ? `<button type="button" class="btn btn-primary btn-sm" onclick="triggerDeepAiAudit(${item.id})" title="Relance l'audit agy en confrontant ces pièces">⚡ Relancer l'Audit IA avec ces pièces</button>` : ""}
            </div>
            ${documentsHtml}
          </div>
        </div>
      </section>
    </article>
  `;

  initPropertyMap(item);
  setupDropzoneDragAndDrop(item.id);
  if (CURRENT_TAB && CURRENT_TAB !== "tab-synthese") {
    switchDossierTab(CURRENT_TAB);
  }
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
    const parcelColor = isDarkModeActive() ? "#60a5fa" : "#1d4ed8";
    L.geoJSON(parcelGeom, {
      style() {
        return { color: parcelColor, weight: 3, fillColor: parcelColor, fillOpacity: 0.22 };
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
    btn.textContent = "Audit IA agy en cours...";
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
      btn.textContent = "Relancer l'Audit IA (agy)";
    }
  }
}

async function removeListing(id) {
  if (!confirm("Supprimer définitivement cette annonce ?")) return;
  await fetch(`/api/listings/${id}`, { method: "DELETE" });
  CURRENT_ID = null;
  await loadInitialData();
}

/* Documents & Vault Management */
async function onDocumentFileSelected(listingId, files) {
  if (!files || files.length === 0) return;
  const file = files[0];
  const typeSelect = document.getElementById("docTypeSelect");
  const docType = typeSelect ? typeSelect.value : "Autre";
  await uploadDocumentFile(listingId, file, docType);
}

async function uploadDocumentFile(listingId, file, docType) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("doc_type", docType);

  const dropzonePrompt = document.querySelector("#documentDropzone .dropzone-prompt");
  if (dropzonePrompt) dropzonePrompt.textContent = "Téléversement et extraction de texte en cours...";

  try {
    const res = await fetch(`/api/listings/${listingId}/documents`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      alert("Erreur lors de l'enregistrement du document.");
      return;
    }
    const data = await res.json();
    if (data.listing) {
      ALL_LISTINGS = ALL_LISTINGS.map((x) => (x.id === listingId ? data.listing : x));
      renderSidebar();
      renderDetail(data.listing);
    }
  } catch (err) {
    console.error(err);
    alert("Erreur de connexion lors du téléversement.");
  }
}

async function deleteListingDocument(listingId, docId) {
  if (!confirm("Supprimer définitivement ce document ?")) return;
  try {
    const res = await fetch(`/api/listings/${listingId}/documents/${docId}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      alert("Erreur lors de la suppression.");
      return;
    }
    const data = await res.json();
    if (data.listing) {
      ALL_LISTINGS = ALL_LISTINGS.map((x) => (x.id === listingId ? data.listing : x));
      renderSidebar();
      renderDetail(data.listing);
    }
  } catch (err) {
    console.error(err);
    alert("Erreur lors de la suppression.");
  }
}

function setupDropzoneDragAndDrop(listingId) {
  const dz = document.getElementById("documentDropzone");
  if (!dz) return;

  ["dragenter", "dragover"].forEach((eventName) => {
    dz.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dz.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dz.addEventListener(eventName, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dz.classList.remove("dragover");
    });
  });

  dz.addEventListener("drop", (e) => {
    const dt = e.dataTransfer;
    if (dt && dt.files && dt.files.length > 0) {
      onDocumentFileSelected(listingId, dt.files);
    }
  });
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
    btn.textContent = "Analyse Open Data + IA en cours...";

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
        CURRENT_ID = created.id;
        CURRENT_TAB = "tab-synthese";
        await loadInitialData();
      }
    } finally {
      btn.disabled = false;
      btn.textContent = "Lancer l'analyse 360°";
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
