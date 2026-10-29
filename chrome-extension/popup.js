/* Popup script for Recherche Immo IA 1-Click Capture */

function extractPageData() {
  const text = document.body ? document.body.innerText : "";
  const title = document.title || "";

  let price = "";
  const mPrice = text.match(/(\d[\d\s\u00a0\u202f]{4,8})\s*€/);
  if (mPrice) {
    const p = mPrice[1].replace(/\D/g, "");
    if (p && Number(p) >= 30000 && Number(p) <= 2500000) price = p;
  }

  let surface = "";
  const mSurf = text.match(/(\d{2,3}(?:[.,]\d)?)\s*m(?:²|2)\b/i);
  if (mSurf) surface = mSurf[1].replace(",", ".");

  let land = "";
  const mLand = text.match(/(?:terrain|parcelle|jardin)[^\d]{0,25}(\d{2,5})\s*m(?:²|2)/i);
  if (mLand) land = mLand[1];

  let bedrooms = "";
  const mBed = text.match(/(\d{1,2})\s*chambres?/i);
  if (mBed) bedrooms = mBed[1];

  let dpe = "";
  const mDpe = text.match(/\bDPE\s*[:\-]?\s*([A-G])\b/i);
  if (mDpe) dpe = mDpe[1].toUpperCase();

  let postcode = "";
  const mCp = text.match(/\b((?:76|27)\d{3})\b/);
  if (mCp) postcode = mCp[1];

  // Extraction automatique des photos de l'annonce (Leboncoin, SeLoger, Bien'ici, PAP, Agences)
  const photos = [];
  const addPhoto = (u) => {
    if (!u || typeof u !== "string") return;
    const clean = u.trim();
    if (
      clean.startsWith("http") &&
      !photos.includes(clean) &&
      !clean.includes("avatar") &&
      !clean.includes("logo") &&
      !clean.includes("icon") &&
      !clean.includes("badge")
    ) {
      photos.push(clean);
    }
  };

  // 1. Next.js payload (__NEXT_DATA__) : Présent sur LeBonCoin, SeLoger, PAP
  try {
    const nextDataEl = document.getElementById("__NEXT_DATA__");
    if (nextDataEl && nextDataEl.textContent) {
      const parsed = JSON.parse(nextDataEl.textContent);
      // Leboncoin
      const lbcImgs = parsed.props?.pageProps?.ad?.images;
      if (lbcImgs) {
        const list = lbcImgs.urls_large || lbcImgs.urls || [];
        list.forEach(addPhoto);
      }
      // SeLoger / Logic-Immo
      const slPhotos =
        parsed.props?.pageProps?.classified?.photos ||
        parsed.props?.pageProps?.initialState?.photos ||
        parsed.props?.pageProps?.listing?.photos;
      if (Array.isArray(slPhotos)) {
        slPhotos.forEach((p) => addPhoto(typeof p === "string" ? p : p.url || p.largeUrl || p.highResolutionUrl));
      }
    }
  } catch (e) {}

  // 2. Scripts JSON intégrés (Bien'ici, Figaro, agences)
  try {
    const scripts = document.querySelectorAll("script");
    for (const sc of scripts) {
      const content = sc.textContent || "";
      if (
        content.includes("urls_large") ||
        content.includes("photos.bienici.com") ||
        content.includes("img.leboncoin.fr") ||
        content.includes("lbcpb/images")
      ) {
        const matches = content.match(/https?:\/\/[^"'\s]+\.(?:jpg|jpeg|webp|png)(?:\?[^"'\s]*)?/gi);
        if (matches) {
          matches.slice(0, 30).forEach(addPhoto);
        }
      }
    }
  } catch (e) {}

  // 3. Fallback balises <img> du carrousel et des galeries
  try {
    const imgEls = document.querySelectorAll(
      '[data-qa-id*="image"] img, [data-qa-id="slideshow"] img, [class*="gallery"] img, [class*="carousel"] img, [class*="slider"] img, [class*="photo"] img, img[src*="leboncoin.fr/api/v1/lbcpb/images"], img[src*="img.leboncoin.fr"], img[src*="photos.bienici.com"], img[src*="sl.sl-c.net"], img[src*="seloger.com"]'
    );
    imgEls.forEach((img) => {
      const src = img.currentSrc || img.src || img.getAttribute("data-src") || img.getAttribute("data-lazy");
      addPhoto(src);
    });
  } catch (e) {}

  return {
    title: title.slice(0, 120),
    price,
    surface,
    land,
    bedrooms,
    dpe,
    postcode,
    description: text.slice(0, 6000),
    photos: photos.slice(0, 30),
  };
}

document.addEventListener("DOMContentLoaded", async () => {
  const { serverUrl } = await chrome.storage.local.get("serverUrl");
  if (serverUrl) {
    document.getElementById("serverUrl").value = serverUrl;
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  let pageData = {};
  if (tab && tab.id && tab.url && tab.url.startsWith("http")) {
    try {
      const results = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: extractPageData,
      });
      if (results && results[0] && results[0].result) {
        pageData = results[0].result;
        document.getElementById("titleInput").value = pageData.title || "";
        document.getElementById("priceInput").value = pageData.price || "";
        document.getElementById("surfaceInput").value = pageData.surface || "";
        document.getElementById("landInput").value = pageData.land || "";
        document.getElementById("bedroomsInput").value = pageData.bedrooms || "";
        document.getElementById("dpeInput").value = pageData.dpe || "";
        if (pageData.postcode) {
          document.getElementById("addressInput").value = pageData.postcode + " ";
        }
        const photoEl = document.getElementById("photoStatus");
        if (photoEl) {
          const nb = (pageData.photos || []).length;
          if (nb > 0) {
            photoEl.innerHTML = `📷 <strong style="color:var(--accent);">${nb} photo${nb > 1 ? "s" : ""} détectée${nb > 1 ? "s" : ""}</strong>`;
          } else {
            photoEl.textContent = "📷 Aucune photo détectée sur cette page";
          }
        }
      }
    } catch (err) {
      console.warn("Extraction directe impossible sur cet onglet:", err);
    }
  }

  document.getElementById("btnSend").addEventListener("click", async () => {
    const statusEl = document.getElementById("statusMsg");
    const srv = document.getElementById("serverUrl").value.replace(/\/$/, "");
    await chrome.storage.local.set({ serverUrl: srv });

    const addr = document.getElementById("addressInput").value.trim();
    if (!addr) {
      statusEl.style.color = "#f87171";
      statusEl.textContent = "Veuillez indiquer l'adresse ou la commune.";
      return;
    }

    statusEl.style.color = "#38bdf8";
    statusEl.textContent = "⏳ Analyse Open Data & IA en cours...";

    try {
      const resp = await fetch(`${srv}/api/listings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: document.getElementById("titleInput").value,
          source_url: tab ? tab.url : "",
          property_type: document.getElementById("typeInput").value,
          address_input: addr,
          price: Number(document.getElementById("priceInput").value || 250000),
          surface_m2: Number(document.getElementById("surfaceInput").value || 0),
          land_m2: Number(document.getElementById("landInput").value || 0),
          bedrooms: Number(document.getElementById("bedroomsInput").value || 0),
          dpe_letter: document.getElementById("dpeInput").value.toUpperCase(),
          description: pageData.description || "",
          photos: pageData.photos || [],
        }),
      });
      if (resp.ok) {
        statusEl.style.color = "#4ade80";
        statusEl.textContent = "✅ Annonce analysée ! Ouverture du Dashboard...";
        await chrome.tabs.create({ url: srv });
      } else {
        statusEl.style.color = "#f87171";
        statusEl.textContent = "Erreur lors de l'envoi au serveur.";
      }
    } catch (e) {
      statusEl.style.color = "#f87171";
      statusEl.textContent = "Serveur inaccessible sur " + srv;
    }
  });
});
