// Port de Search.jsx
import { addHistoryItem, apiRequest, categoryOf, getToken, openDocument } from "../api.js";
import { el, fileTypeLabel } from "./helpers.js";

export function initSearch(main) {
  const params = new URLSearchParams(window.location.search);

  let query = params.get("q") || "";
  let topK = Number(params.get("k")) || 5;
  let category = params.get("category") || "";
  let fileType = params.get("file_type") || "";
  let results = null;
  let indexing = false;

  // Score affiché : le backend renvoie `relevance`, un pourcentage REEL
  // calcule par le moteur (cosinus SBERT + BM25 normalise, 0-100,
  // independant des autres resultats). Fallback : normalisation relative
  // sur l'ancien champ `aggregated` si le backend ne le fournit pas.
  function normalizeResults(list) {
    if (!list || !list.length) return list;

    if (typeof list[0].relevance === "number") {
      return list.map((r) => ({ ...r, _normalizedScore: r.relevance }));
    }

    const maxAgg = Math.max(...list.map((r) => r.aggregated || 0));
    if (maxAgg <= 0) return list;
    return list.map((r) => ({
      ...r,
      _normalizedScore: Math.round(((r.aggregated || 0) / maxAgg) * 1000) / 10,
    }));
  }

  // Format français : virgule décimale + signe % (ex : "87,5 %").
  function formatPercent(value) {
    return `${String(value).replace(".", ",")} %`;
  }

  function highlightInto(container, text, queryValue) {
    if (!text) return;
    const terms = queryValue
      .trim()
      .split(/\s+/)
      .filter(Boolean)
      .map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));

    if (!terms.length) {
      container.appendChild(document.createTextNode(text));
      return;
    }

    const regex = new RegExp(`(${terms.join("|")})`, "i");
    for (const part of text.split(regex)) {
      if (!part) continue;
      if (regex.test(part)) container.appendChild(el("mark", null, part));
      else container.appendChild(el("span", null, part));
    }
  }

  async function handleOpen(result) {
    try {
      await openDocument(result.relative_path);
      openErrorBox.hidden = true;
    } catch (err) {
      openErrorBox.textContent = err.message;
      openErrorBox.hidden = false;
    }
  }

  function buildResultCard(result) {
    const typeLabel = fileTypeLabel(result.file_type);
    const card = el("article", "result-card");

    const head = el("div", "result-head");
    const h3 = el("h3");
    h3.title = result.file_name;
    highlightInto(h3, result.file_name, query);
    head.appendChild(h3);
    const normScore = result._normalizedScore ?? 0;
    const normLabel = formatPercent(normScore);
    const pill = el("span", "score-pill", normLabel);
    pill.title = `Cosinus: ${(result.score || 0).toFixed(3)} | Agrégé: ${(result.aggregated || 0).toFixed(6)}`;
    head.appendChild(pill);
    card.appendChild(head);

    const meta = el("div", "result-meta");
    meta.append(
      el("span", `file-ico ${typeLabel.length > 3 ? "wide" : ""}`, typeLabel),
      el("span", null, categoryOf(result.relative_path)),
      el("span", null, "·"),
      el("span", null, result.file_type)
    );
    card.appendChild(meta);

    card.appendChild(el("div", "result-path", result.relative_path));

    if (result.text_preview) {
      const preview = el("div", "result-preview");
      highlightInto(preview, result.text_preview, query);
      card.appendChild(preview);
    }

    const foot = el("div", "result-foot");
    const relevance = el("span", "muted", `Score de pertinence ${normLabel}`);
    relevance.style.fontSize = "12px";
    const openBtn = el("button", "btn btn-ghost result-open", "Ouvrir le document →");
    openBtn.type = "button";
    openBtn.addEventListener("click", () => handleOpen(result));
    foot.append(relevance, openBtn);
    card.appendChild(foot);

    return card;
  }

  function renderResults() {
    resultsBox.textContent = "";

    if (results == null) {
      const empty = el("div", "empty-state");
      empty.innerHTML =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg>';
      const text = el("div");
      text.textContent = indexing
        ? "Indexation en cours…"
        : "Lancez une recherche pour afficher les documents pertinents.";
      empty.appendChild(text);
      resultsBox.appendChild(empty);
      exportBtn.style.display = "none";
      return;
    }

    if (results.length === 0) {
      resultsBox.appendChild(
        el("div", "empty-state", "Aucun document ne correspond à votre recherche.")
      );
      exportBtn.style.display = "none";
      return;
    }

    const grid = el("div", "results-grid");
    const normalized = normalizeResults(results);
    for (const result of normalized) grid.appendChild(buildResultCard(result));
    resultsBox.appendChild(grid);
    exportBtn.style.display = "";
  }

  async function runSearch(searchQuery, searchTopK, searchCategory, searchFileType) {
    indexing = false;
    rebuildSearchPanel();
    statusBox.hidden = true;
    openErrorBox.hidden = true;
    errorBox.hidden = true;
    suggestionsBox.hidden = true;
    suggestionsBox.textContent = "";
    submitBtn.disabled = true;
    submitBtn.textContent = "Recherche…";

    // Mettre a jour l'URL pour les liens partageables.
    const urlParams = new URLSearchParams();
    if (searchQuery) urlParams.set("q", searchQuery);
    if (searchTopK && searchTopK !== 5) urlParams.set("k", String(searchTopK));
    if (searchCategory) urlParams.set("category", searchCategory);
    if (searchFileType) urlParams.set("file_type", searchFileType);
    const newUrl = `${window.location.pathname}${urlParams.toString() ? "?" + urlParams : ""}`;
    history.replaceState(null, "", newUrl);

    try {
      const body = { query: searchQuery, top_k: Number(searchTopK) };
      if (searchCategory) body.category = searchCategory;
      if (searchFileType) body.file_type = searchFileType;

      const data = await apiRequest(
        "/search",
        { method: "POST", body: JSON.stringify(body) },
      );
      results = data.results || [];
      statusBox.textContent = `${data.results_count} résultat(s) trouvé(s) pour « ${searchQuery} ».`;
      statusBox.hidden = false;
      addHistoryItem({
        query: searchQuery,
        top_k: Number(searchTopK),
        category: searchCategory || undefined,
        file_type: searchFileType || undefined,
        timestamp: new Date().toISOString(),
        results_count: data.results_count,
      });

      // Afficher les suggestions si 0 resultat.
      if (results.length === 0 && data.suggestions && data.suggestions.length) {
        suggestionsBox.hidden = false;
        const label = el("strong", null, "Suggestions : ");
        suggestionsBox.appendChild(label);
        for (const sug of data.suggestions) {
          const chip = el("button", "chip", sug.term);
          chip.type = "button";
          chip.addEventListener("click", () => {
            queryInput.value = sug.term;
            query = sug.term;
            runSearch(sug.term, topKSelect.value, categorySelect.value, fileTypeSelect.value);
          });
          suggestionsBox.appendChild(chip);
        }
      }
    } catch (err) {
      results = null;
      indexing = err.status === 503;
      if (!indexing) {
        errorBox.textContent = err.message;
        errorBox.hidden = false;
      }
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Rechercher";
    }

    renderResults();
  }

  // Bandeau d'indexation (503) avec bouton réessayer.
  function rebuildSearchPanel() {
    const old = form.querySelector(".notice");
    if (old) old.remove();
    if (indexing) {
      const notice = el("div", "search-status notice");
      notice.append(
        document.createTextNode(
          "Le serveur est en train d'indexer les documents pour la première fois. La recherche sémantique sera disponible dans quelques instants."
        )
      );
      const retryBtn = el("button", "btn btn-ghost", "Réessayer");
      retryBtn.type = "button";
      retryBtn.style.marginTop = "8px";
      retryBtn.addEventListener("click", () => {
        retryBtn.disabled = true;
        retryBtn.textContent = "Vérification…";
        runSearch(queryInput.value, topKSelect.value);
      });
      notice.appendChild(retryBtn);
      form.appendChild(notice);
    }
  }

  // ---- Construction de la page ----
  const header = el("div", "page-header");
  const hLeft = el("div");
  hLeft.append(
    el("h1", "page-title", "Recherche documentaire"),
    el("p", "page-subtitle", "Recherche sémantique dans l'ensemble des documents indexés.")
  );
  header.appendChild(hLeft);
  main.appendChild(header);

  const form = el("form", "search-panel");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    runSearch(queryInput.value, topKSelect.value, categorySelect.value, fileTypeSelect.value);
  });

  const searchBar = el("div", "search-bar");
  const inputWrap = el("div", "search-input");
  inputWrap.innerHTML =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></svg>';
  const queryInput = document.createElement("input");
  queryInput.placeholder = "Rechercher un document (ex : bulletin de salaire)…";
  queryInput.value = query;
  queryInput.addEventListener("input", () => {
    query = queryInput.value;
  });
  inputWrap.appendChild(queryInput);

  const topKSelect = document.createElement("select");
  topKSelect.title = "Nombre de résultats";
  topKSelect.setAttribute("aria-label", "Nombre de résultats");
  for (const n of [3, 5, 8, 10, 15]) {
    const option = el("option", null, `${n} résultats`);
    option.value = String(n);
    if (n === topK) option.selected = true;
    topKSelect.appendChild(option);
  }
  topKSelect.addEventListener("change", () => {
    topK = Number(topKSelect.value);
  });

  // Filtre par categorie.
  const categorySelect = document.createElement("select");
  categorySelect.title = "Catégorie";
  categorySelect.setAttribute("aria-label", "Catégorie");
  categorySelect.innerHTML = '<option value="">Toutes les catégories</option>';
  categorySelect.addEventListener("change", () => {
    category = categorySelect.value;
  });

  // Filtre par type de fichier.
  const fileTypeSelect = document.createElement("select");
  fileTypeSelect.title = "Type de fichier";
  fileTypeSelect.setAttribute("aria-label", "Type de fichier");
  fileTypeSelect.innerHTML = '<option value="">Tous les types</option>';
  for (const [label, value] of [["PDF", ".pdf"], ["Word", ".docx"], ["PowerPoint", ".pptx"], ["Excel", ".xlsx"], ["Image", ".png"]]) {
    const opt = el("option", null, label);
    opt.value = value;
    fileTypeSelect.appendChild(opt);
  }
  fileTypeSelect.addEventListener("change", () => {
    fileType = fileTypeSelect.value;
  });

  const submitBtn = el("button", "btn btn-primary", "Rechercher");
  submitBtn.type = "submit";

  // Bouton export CSV.
  const exportBtn = el("button", "btn btn-ghost", "Exporter CSV");
  exportBtn.type = "button";
  exportBtn.style.display = "none";
  exportBtn.addEventListener("click", async () => {
    try {
      const body = { query, top_k: Number(topKSelect.value) };
      if (categorySelect.value) body.category = categorySelect.value;
      if (fileTypeSelect.value) body.file_type = fileTypeSelect.value;
      const response = await fetch(`${window.location.protocol}//${window.location.hostname}:8000/search/export`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
        },
        credentials: "include",
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error("Erreur d'export");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `recherche_${query.slice(0, 30)}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      errorBox.textContent = "Erreur lors de l'export CSV : " + err.message;
      errorBox.hidden = false;
    }
  });

  searchBar.append(inputWrap, categorySelect, fileTypeSelect, topKSelect, submitBtn, exportBtn);
  form.appendChild(searchBar);

  const statusBox = el("div", "search-status");
  statusBox.hidden = true;
  const openErrorBox = el("div", "form-error");
  openErrorBox.hidden = true;
  const errorBox = el("div", "form-error");
  errorBox.hidden = true;
  const suggestionsBox = el("div", "search-suggestions");
  suggestionsBox.hidden = true;

  form.append(statusBox, openErrorBox, errorBox, suggestionsBox);
  main.appendChild(form);

  const resultsBox = el("div");
  main.appendChild(resultsBox);

  renderResults();

  // Charger les categories depuis l'engine pour le filtre.
  (async () => {
    try {
      const data = await apiRequest("/health");
      if (data.categories_count > 0) {
        const rootData = await apiRequest("/");
        if (rootData.categories) {
          for (const cat of rootData.categories) {
            const opt = el("option", null, cat);
            opt.value = cat;
            if (cat === category) opt.selected = true;
            categorySelect.appendChild(opt);
          }
        }
      }
    } catch {
      // ignore — filtres restent vides
    }
  })();

  // Relance la recherche si ?q= est présent dans l'URL (recherche globale,
  // historique ou navigation).
  if (params.get("q") != null) {
    const initCat = params.get("category") || "";
    const initFileType = params.get("file_type") || "";
    runSearch(params.get("q"), Number(params.get("k")) || topK, initCat, initFileType);
  }
}
