// Port de Dashboard.jsx
import { apiRequest, categoryOf, openDocument } from "../api.js";
import { getUser } from "../auth.js";
import { el, fileTypeLabel } from "./helpers.js";
import { icon as layoutIcon } from "../layout.js";

function kpiIcon(name) {
  if (name === "documents") return layoutIcon("folder");
  if (name === "account") return layoutIcon("user");
  return null;
}

function buildKpi(iconName, tone, value, label) {
  const card = el("div", "kpi-card");
  const top = el("div", "kpi-top");
  const iconWrap = el("div", `kpi-icon ${tone}`);
  const svg = kpiIcon(iconName);
  if (iconName === "memory") {
    // Éclair (port de l'icône memory du JSX)
    iconWrap.innerHTML =
      '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></svg>';
  } else if (svg) {
    iconWrap.appendChild(svg);
  } else if (iconName === "index") {
    iconWrap.innerHTML =
      '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" /><path d="M12 16v-4" /><path d="M12 8h.01" /></svg>';
  }
  top.appendChild(iconWrap);
  card.append(top, el("div", "kpi-value", value), el("div", "kpi-label", label));
  return card;
}

function buildRecentRow(doc) {
  const typeLabel = fileTypeLabel(doc.file_type);
  const row = el("div", "recent-row");
  const fileIco = el("div", `file-ico ${typeLabel.length > 3 ? "wide" : ""}`, typeLabel);
  const body = el("div", "r-body");
  body.append(el("strong", null, doc.file_name), el("span", null, categoryOf(doc.relative_path)));
  const openBtn = el("button", "btn btn-ghost recent-open", "Ouvrir →");
  openBtn.type = "button";
  openBtn.addEventListener("click", () => {
    openDocument(doc.relative_path).catch(() => {});
  });
  row.append(fileIco, body, openBtn);
  return row;
}

function renderSummary(main, summary) {
  const user = getUser();

  // Les 4 indicateurs côte à côte (grille responsive définie dans pages.css).
  const kpiGrid = el("div", "kpi-grid");
  kpiGrid.appendChild(buildKpi("documents", "blue", summary.documents_count ?? "—", "Documents indexés"));
  kpiGrid.appendChild(buildKpi("memory", "blue", summary.documents_in_memory ?? "—", "Documents en mémoire"));
  kpiGrid.appendChild(buildKpi("index", "cyan", summary.index_loaded ? "Oui" : "Non", "Index chargé"));
  kpiGrid.appendChild(
    buildKpi("account", "cyan", user?.is_email_verified ? "Vérifié" : "En attente", "Statut du compte")
  );
  main.appendChild(kpiGrid);

  const layout = el("div", "dash-layout");
  const dashMain = el("div", "dash-main");

  // Recherche rapide
  const quickSection = el("section", "panel-section");
  const quickTitle = el("div", "panel-title");
  quickTitle.appendChild(el("h2", null, "Recherche rapide"));
  const quickBody = el("div", "panel-body");
  const quickForm = el("form", "quick-search");
  const quickInput = document.createElement("input");
  quickInput.placeholder = "Rechercher un document… (ex : bulletin de salaire)";
  quickForm.appendChild(quickInput);
  const quickBtn = el("button", "btn btn-primary", "Rechercher");
  quickBtn.type = "submit";
  quickForm.appendChild(quickBtn);
  quickForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = quickInput.value.trim();
    if (value) window.location.href = `search.html?q=${encodeURIComponent(value)}`;
  });
  quickBody.appendChild(quickForm);
  quickSection.append(quickTitle, quickBody);

  // Derniers documents
  const recentDocs = main._recent || [];
  const recentSection = el("section", "panel-section");
  const recentTitle = el("div", "panel-title");
  recentTitle.appendChild(el("h2", null, "Derniers documents"));
  const seeAll = el("a", null, "Voir tout →");
  seeAll.href = "documents.html";
  recentTitle.appendChild(seeAll);
  recentSection.appendChild(recentTitle);
  if (recentDocs.length === 0) {
    const b = el("div", "panel-body");
    b.appendChild(el("p", "muted", "Aucun document disponible."));
    recentSection.appendChild(b);
  } else {
    const list = el("div", "recent-list");
    for (const doc of recentDocs) list.appendChild(buildRecentRow(doc));
    recentSection.appendChild(list);
  }

  dashMain.append(quickSection, recentSection);

  // État du système
  const side = el("div", "dash-side");
  const statusSection = el("section", "panel-section");
  const statusTitle = el("div", "panel-title");
  statusTitle.appendChild(el("h2", null, "État du système"));
  const dl = el("dl", "status-list");

  function makeRow(label, ddBuilder) {
    const r = el("div", "status-row");
    r.appendChild(el("dt", null, label));
    const dd = document.createElement("dd");
    ddBuilder(dd);
    r.appendChild(dd);
    dl.appendChild(r);
  }

  makeRow("Index vectoriel", (dd) => {
    const badge = el("span", summary.index_loaded ? "badge badge-success" : "badge badge-warning");
    badge.textContent = summary.index_loaded ? "Chargé" : "Non chargé";
    dd.appendChild(badge);
  });
  makeRow("Base de documents", (dd) => {
    dd.textContent = `${summary.documents_count ?? 0} fichiers`;
  });
  makeRow("Compte", (dd) => {
    const badge = el("span", user?.is_email_verified ? "badge badge-success" : "badge badge-warning");
    badge.textContent = user?.is_email_verified ? "Vérifié" : "En attente";
    dd.appendChild(badge);
  });
  makeRow("Membre depuis", (dd) => {
    dd.textContent = user?.created_at
      ? new Date(user.created_at).toLocaleDateString("fr-FR")
      : "—";
  });

  statusSection.append(statusTitle, dl);
  side.appendChild(statusSection);

  layout.append(dashMain, side);
  main.appendChild(layout);
}

export function initDashboard(main) {
  let summary = null;
  let errorBox = null;

  async function load() {
    // Reset du contenu
    main.textContent = "";
    if (errorBox && errorBox.isConnected) errorBox.remove();

    const header = el("div", "page-header");
    const hLeft = el("div");
    hLeft.append(el("h1", "page-title", "Tableau de bord"));
    const today = new Date().toLocaleDateString("fr-FR", {
      weekday: "long",
      day: "numeric",
      month: "long",
      year: "numeric",
    });
    hLeft.appendChild(
      el("p", "page-subtitle", `${today} · ${getUser()?.full_name}`)
    );
    const actions = el("div", "page-actions");
    const refreshBtn = el("button", "btn btn-ghost", "Actualiser");
    refreshBtn.type = "button";
    refreshBtn.addEventListener("click", load);
    actions.appendChild(refreshBtn);
    header.append(hLeft, actions);
    main.appendChild(header);

    if (errorBox) main.appendChild(errorBox);

    if (!summary) {
      const loadingState = el("div", "empty-state");
      const spinner = el("span", "spinner");
      spinner.style.display = "block";
      spinner.style.margin = "0 auto";
      loadingState.appendChild(spinner);
      main.appendChild(loadingState);
    }

    try {
      const [sum, docs] = await Promise.all([
        apiRequest("/dashboard/summary", { method: "GET" }),
        apiRequest("/documents?limit=5", { method: "GET" }),
      ]);
      summary = sum;
      const recent = docs.documents || [];
      main._recent = recent;

      main.textContent = "";
      main.appendChild(header);
      if (errorBox) main.appendChild(errorBox);
      renderSummary(main, summary);
    } catch (err) {
      if (!errorBox) {
        errorBox = el("div", "form-error");
        errorBox.style.marginBottom = "16px";
      }
      errorBox.textContent = err.message;
      main.textContent = "";
      main.appendChild(header);
      main.appendChild(errorBox);
      if (!summary) {
        const empty = el("div", "empty-state", "Aucune donnée à afficher.");
        main.appendChild(empty);
      } else {
        renderSummary(main, summary);
      }
    }
  }

  load();
}
