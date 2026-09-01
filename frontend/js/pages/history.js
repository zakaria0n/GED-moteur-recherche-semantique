// Port de History.jsx
import { clearHistory, readHistory, removeHistoryItem } from "../api.js";
import { el } from "./helpers.js";

export function initHistory(main) {
  let items = readHistory();
  let confirmOpen = false;
  let backdrop = null;

  function render() {
    main.textContent = "";

    const header = el("div", "page-header");
    const hLeft = el("div");
    hLeft.append(
      el("h1", "page-title", "Historique"),
      el("p", "page-subtitle", "Vos dernières recherches sur la plateforme.")
    );
    header.appendChild(hLeft);
    if (items.length > 0) {
      const actions = el("div", "page-actions");
      const clearBtn = el("button", "btn btn-ghost", "Tout effacer");
      clearBtn.type = "button";
      clearBtn.addEventListener("click", () => {
        confirmOpen = true;
        render();
      });
      actions.appendChild(clearBtn);
      header.appendChild(actions);
    }
    main.appendChild(header);

    if (items.length === 0) {
      main.appendChild(
        el("div", "empty-state", "Aucune recherche enregistrée pour le moment.")
      );
    } else {
      const list = el("div", "history-list");
      for (const item of items) list.appendChild(buildRow(item));
      main.appendChild(list);
    }

    // Modale de confirmation
    if (backdrop) {
      backdrop.remove();
      backdrop = null;
    }
    if (confirmOpen) {
      backdrop = el("div", "modal-backdrop");
      backdrop.addEventListener("click", () => {
        confirmOpen = false;
        render();
      });

      const card = el("div", "modal-card");
      card.setAttribute("role", "dialog");
      card.setAttribute("aria-modal", "true");
      card.setAttribute("aria-labelledby", "history-confirm-title");
      card.addEventListener("click", (event) => event.stopPropagation());

      const title = el("h2", null, "Confirmer la suppression");
      title.id = "history-confirm-title";
      card.appendChild(title);
      card.appendChild(el("p", null, "Voulez-vous vraiment effacer tout l'historique de recherche ?"));

      const modalActions = el("div", "modal-actions");
      const cancelBtn = el("button", "btn btn-ghost", "Annuler");
      cancelBtn.type = "button";
      cancelBtn.addEventListener("click", () => {
        confirmOpen = false;
        render();
      });
      const confirmBtn = el("button", "btn btn-danger", "Effacer tout");
      confirmBtn.type = "button";
      confirmBtn.addEventListener("click", () => {
        clearHistory();
        items = readHistory();
        confirmOpen = false;
        render();
      });
      modalActions.append(cancelBtn, confirmBtn);
      card.appendChild(modalActions);

      backdrop.appendChild(card);
      document.body.appendChild(backdrop);
    }
  }

  function buildRow(item) {
    const row = el("div", "history-row");

    const itemBtn = el("button", "history-item");
    itemBtn.type = "button";
    itemBtn.addEventListener("click", () => {
      window.location.href = `search.html?q=${encodeURIComponent(item.query)}&k=${item.top_k}`;
    });
    const hMain = el("div", "h-main");
    hMain.appendChild(el("strong", null, item.query));
    const hMeta = el("div", "h-meta");
    hMeta.append(
      el("span", null, `Résultats : ${item.results_count}`),
      el("span", null, `Top K : ${item.top_k}`),
      el("span", null, new Date(item.timestamp).toLocaleString("fr-FR"))
    );
    hMain.appendChild(hMeta);
    itemBtn.appendChild(hMain);
    itemBtn.appendChild(el("span", "badge badge-info", "Relancer →"));

    const deleteBtn = el("button", "history-delete");
    deleteBtn.type = "button";
    deleteBtn.title = "Supprimer cette recherche";
    deleteBtn.setAttribute("aria-label", "Supprimer cette recherche");
    deleteBtn.innerHTML =
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18" /><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" /><path d="M10 11v6" /><path d="M14 11v6" /></svg>';
    deleteBtn.addEventListener("click", () => {
      removeHistoryItem(item.timestamp, item.query);
      items = readHistory();
      render();
    });

    row.append(itemBtn, deleteBtn);
    return row;
  }

  render();
}
