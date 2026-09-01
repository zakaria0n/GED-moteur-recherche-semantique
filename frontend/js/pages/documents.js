// Port de Documents.jsx + DocumentCard.jsx
import { apiRequest, categoryOf, openDocument } from "../api.js";
import { el, formatDate } from "./helpers.js";

const PAGE_SIZE = 30;

let documents = null;
let filter = "Tous";
let visibleCount = PAGE_SIZE;

function buildDocCard(doc) {
  const { file_name, relative_path, file_type, modified_at } = doc;
  const typeLabel = (file_type || "PDF").split("/").pop().toUpperCase();

  const card = el("article", "doc-card");
  card.appendChild(el("div", "doc-icon", typeLabel));

  const body = el("div", "doc-body");
  body.appendChild(el("h3", null, file_name));

  const metaText = categoryOf(relative_path) + (modified_at ? ` · ${formatDate(modified_at)}` : "");
  body.appendChild(el("div", "doc-meta", metaText));

  const errorLine = el("div", "form-error");
  errorLine.hidden = true;

  const openBtn = el("button", "btn btn-primary doc-open", "Ouvrir le document →");
  openBtn.type = "button";
  openBtn.addEventListener("click", async () => {
    openBtn.disabled = true;
    openBtn.textContent = "Ouverture…";
    errorLine.hidden = true;
    try {
      await openDocument(relative_path);
      openBtn.textContent = "Ouvrir le document →";
    } catch (err) {
      errorLine.textContent = err.message;
      errorLine.hidden = false;
      openBtn.textContent = "Ouvrir le document →";
    } finally {
      openBtn.disabled = false;
    }
  });

  body.append(errorLine, openBtn);
  card.appendChild(body);
  return card;
}

export function initDocuments(main) {
  function categoriesOf() {
    if (!documents) return [];
    const counts = new Map();
    for (const doc of documents) {
      const name = categoryOf(doc.relative_path);
      counts.set(name, (counts.get(name) || 0) + 1);
    }
    return Array.from(counts.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }

  function groupedOf() {
    if (!documents) return [];
    const map = new Map();
    for (const doc of documents) {
      const name = categoryOf(doc.relative_path);
      if (filter !== "Tous" && name !== filter) continue;
      if (!map.has(name)) map.set(name, []);
      map.get(name).push(doc);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }

  // Affiche seulement `visibleCount` documents au total, répartis par
  // catégorie, pour rester fluide quand la bibliothèque grossit.
  function visibleGroupsOf(grouped) {
    let remaining = visibleCount;
    const out = [];
    for (const [name, items] of grouped) {
      if (remaining <= 0) break;
      out.push([name, items.length > remaining ? items.slice(0, remaining) : items]);
      remaining -= items.length;
    }
    return out;
  }

  function renderList(contentBox, header) {
    contentBox.textContent = "";
    const grouped = groupedOf();
    const filteredTotal = grouped.reduce((acc, [, items]) => acc + items.length, 0);

    if (grouped.length === 0) {
      contentBox.appendChild(el("div", "empty-state", "Aucun document dans cette catégorie."));
      return;
    }

    for (const [category, items] of visibleGroupsOf(grouped)) {
      const section = el("section", "category-section");
      const head = el("div", "category-head");
      head.append(el("h2", null, category), el("span", "count", `${items.length} document(s)`));
      section.appendChild(head);

      const grid = el("div", "doc-grid");
      for (const doc of items) grid.appendChild(buildDocCard(doc));
      section.appendChild(grid);
      contentBox.appendChild(section);
    }

    if (visibleCount < filteredTotal) {
      const wrap = el("div", "load-more-wrap");
      const btn = el(
        "button",
        "btn btn-ghost",
        `Afficher plus (${filteredTotal - visibleCount} restants)`
      );
      btn.type = "button";
      btn.addEventListener("click", () => {
        visibleCount += PAGE_SIZE;
        renderList(contentBox, header);
      });
      wrap.appendChild(btn);
      contentBox.appendChild(wrap);
    }
  }

  function renderFilters(filterBar, listBox, header) {
    filterBar.textContent = "";
    const total = documents ? documents.length : 0;

    function chip(name, count) {
      const b = el("button", `chip ${filter === name ? "active" : ""}`);
      b.type = "button";
      b.appendChild(document.createTextNode(`${name} `));
      const countSpan = el("span", `chip-count ${filter === name ? "active" : ""}`, `(${count})`);
      b.appendChild(countSpan);
      b.addEventListener("click", () => {
        filter = name;
        visibleCount = PAGE_SIZE;
        renderFilters(filterBar, listBox, header);
        renderList(listBox, header);
      });
      return b;
    }

    filterBar.appendChild(chip("Tous", total));
    for (const [name, count] of categoriesOf()) filterBar.appendChild(chip(name, count));
  }

  function buildHeader(total) {
    const header = el("div", "page-header");
    const hLeft = el("div");
    hLeft.append(el("h1", "page-title", "Documents"));
    hLeft.appendChild(
      el(
        "p",
        "page-subtitle",
        total > 0
          ? `${total} document(s) indexé(s), classés par catégorie.`
          : "Bibliothèque documentaire classée par catégorie."
      )
    );
    header.appendChild(hLeft);
    return header;
  }

  // Chargement initial
  main.appendChild(buildHeader(0));
  const loadingState = el("div", "empty-state");
  const spinner = el("span", "spinner");
  spinner.style.display = "block";
  spinner.style.margin = "0 auto";
  loadingState.appendChild(spinner);
  main.appendChild(loadingState);

  apiRequest("/documents", { method: "GET" })
    .then((data) => {
      documents = data.documents || [];
    })
    .catch((err) => {
      const errorBox = el("div", "form-error", err.message);
      errorBox.style.marginBottom = "16px";
      main.insertBefore(errorBox, main.querySelector(".empty-state"));
      documents = documents || [];
    })
    .finally(() => {
      main.textContent = "";
      const header = buildHeader(documents ? documents.length : 0);
      main.appendChild(header);

      const filterBar = el("div", "doc-filters");
      main.appendChild(filterBar);
      const listBox = el("div");
      main.appendChild(listBox);

      renderFilters(filterBar, listBox, header);
      renderList(listBox, header);
    });
}
