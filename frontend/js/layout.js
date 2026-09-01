// Port de AppLayout.jsx + Sidebar.jsx : injecte le layout commun aux pages protégées.
import { apiRequest } from "./api.js";
import { getUser, logoutLocal } from "./auth.js";

const NAV_GROUPS = [
  {
    label: "Espace",
    items: [{ href: "dashboard.html", label: "Tableau de bord", icon: "dashboard", key: "dashboard" }],
  },
  {
    label: "GED",
    items: [
      { href: "documents.html", label: "Documents", icon: "folder", key: "documents" },
      { href: "history.html", label: "Historique", icon: "history", key: "history" },
    ],
  },
  {
    label: "Compte",
    items: [{ href: "profile.html", label: "Profil", icon: "user", key: "profile" }],
  },
];

const PAGE_LABELS = {
  dashboard: "Tableau de bord",
  search: "Recherche",
  documents: "Documents",
  history: "Historique",
  profile: "Profil",
};

const MOBILE_NAV_ITEMS = [
  { href: "dashboard.html", label: "Dashboard", icon: "dashboard", key: "dashboard" },
  { href: "documents.html", label: "Documents", icon: "folder", key: "documents" },
  { href: "search.html", label: "Recherche", icon: "search", key: "search" },
  { href: "profile.html", label: "Profil", icon: "user", key: "profile" },
];

export function initials(fullName) {
  if (!fullName) return "?";
  return fullName
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function svg(paths, size = 18) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("width", size);
  s.setAttribute("height", size);
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("fill", "none");
  s.setAttribute("stroke", "currentColor");
  s.setAttribute("stroke-width", "2");
  s.setAttribute("stroke-linecap", "round");
  s.setAttribute("stroke-linejoin", "round");
  for (const [tag, attrs] of paths) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    s.appendChild(el);
  }
  return s;
}

export function icon(name) {
  switch (name) {
    case "dashboard":
      return svg([
        ["rect", { x: "3", y: "3", width: "7", height: "9", rx: "1.5" }],
        ["rect", { x: "14", y: "3", width: "7", height: "5", rx: "1.5" }],
        ["rect", { x: "14", y: "12", width: "7", height: "9", rx: "1.5" }],
        ["rect", { x: "3", y: "16", width: "7", height: "5", rx: "1.5" }],
      ]);
    case "folder":
      return svg([
        ["path", { d: "M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.7-.9L9.2 3.9A2 2 0 0 0 7.5 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" }],
      ]);
    case "history":
      return svg([
        ["path", { d: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" }],
        ["path", { d: "M3 3v5h5" }],
        ["path", { d: "M12 7v5l4 2" }],
      ]);
    case "user":
      return svg([
        ["path", { d: "M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" }],
        ["circle", { cx: "12", cy: "7", r: "4" }],
      ]);
    case "logout":
      return svg([
        ["path", { d: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" }],
        ["path", { d: "m16 17 5-5-5-5" }],
        ["path", { d: "M21 12H9" }],
      ]);
    case "search":
      return svg([
        ["circle", { cx: "11", cy: "11", r: "7" }],
        ["path", { d: "m21 21-4.3-4.3" }],
      ]);
    default:
      return null;
  }
}

function buildSidebar(activeKey, onOpenClose) {
  const aside = document.createElement("aside");
  aside.className = "sidebar";

  const brand = document.createElement("div");
  brand.className = "sidebar-brand";
  const img = document.createElement("img");
  img.src = "logo.png";
  img.alt = "GED INRH";
  img.className = "brand-logo";
  const text = document.createElement("div");
  text.className = "brand-text";
  const strong = document.createElement("strong");
  strong.textContent = "GED INRH";
  const span = document.createElement("span");
  span.textContent = "Documentation";
  text.append(strong, span);
  const closeBtn = document.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "sidebar-close";
  closeBtn.setAttribute("aria-label", "Fermer le menu");
  closeBtn.textContent = "✕";
  closeBtn.addEventListener("click", onOpenClose);
  brand.append(img, text, closeBtn);

  const nav = document.createElement("nav");
  nav.className = "sidebar-nav";
  for (const group of NAV_GROUPS) {
    const g = document.createElement("div");
    g.className = "nav-group";
    const gl = document.createElement("div");
    gl.className = "nav-group-label";
    gl.textContent = group.label;
    g.appendChild(gl);
    for (const item of group.items) {
      const a = document.createElement("a");
      a.href = item.href;
      a.className = item.key === activeKey ? "nav-link active" : "nav-link";
      a.appendChild(icon(item.icon));
      a.appendChild(document.createTextNode(item.label));
      a.addEventListener("click", onOpenClose);
      g.appendChild(a);
    }
    nav.appendChild(g);
  }

  const footer = document.createElement("div");
  footer.className = "sidebar-footer";
  const logoutBtn = document.createElement("button");
  logoutBtn.type = "button";
  logoutBtn.className = "sidebar-logout";
  logoutBtn.appendChild(icon("logout"));
  logoutBtn.appendChild(document.createTextNode("Se déconnecter"));
  logoutBtn.addEventListener("click", async () => {
    try {
      await apiRequest("/auth/logout", { method: "POST" });
    } catch {
      // failure to reach backend shouldn't block local logout
    }
    logoutLocal();
    window.location.href = "index.html";
  });
  footer.appendChild(logoutBtn);

  aside.append(brand, nav, footer);
  return aside;
}

function buildTopbar(activeKey, onOpenMenu) {
  const header = document.createElement("header");
  header.className = "topbar";

  const menuBtn = document.createElement("button");
  menuBtn.type = "button";
  menuBtn.className = "topbar-menu";
  menuBtn.setAttribute("aria-label", "Ouvrir le menu");
  menuBtn.appendChild(svg([["path", { d: "M4 7h16" }], ["path", { d: "M4 12h16" }], ["path", { d: "M4 17h16" }]]));
  menuBtn.addEventListener("click", onOpenMenu);

  const crumb = document.createElement("div");
  crumb.className = "topbar-crumb";
  crumb.append(
    document.createTextNode("GED INRH / "),
    Object.assign(document.createElement("strong"), { textContent: PAGE_LABELS[activeKey] || "Espace GED" })
  );

  const form = document.createElement("form");
  form.className = "topbar-search";
  form.appendChild(svg([["circle", { cx: "11", cy: "11", r: "7" }], ["path", { d: "m21 21-4.3-4.3" }]]));
  const input = document.createElement("input");
  input.placeholder = "Recherche rapide…";
  input.setAttribute("aria-label", "Recherche rapide");
  form.appendChild(input);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = input.value.trim();
    if (!value) return;
    window.location.href = `search.html?q=${encodeURIComponent(value)}`;
  });

  // Bouton dark mode.
  const darkBtn = document.createElement("button");
  darkBtn.type = "button";
  darkBtn.className = "topbar-menu";
  darkBtn.setAttribute("aria-label", "Basculer le mode sombre");
  darkBtn.title = "Mode sombre";
  darkBtn.appendChild(svg([["path", { d: "M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" }]]));
  darkBtn.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("ged_theme", next);
  });

  const user = getUser();
  const userWrap = document.createElement("div");
  userWrap.className = "topbar-user";
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = initials(user?.full_name);
  const meta = document.createElement("div");
  meta.className = "meta";
  const mStrong = document.createElement("strong");
  mStrong.textContent = user?.full_name || "Utilisateur";
  const mSpan = document.createElement("span");
  mSpan.textContent = user?.email || "";
  meta.append(mStrong, mSpan);
  userWrap.append(avatar, meta);

  header.append(menuBtn, crumb, form, darkBtn, userWrap);
  return header;
}

function buildMobileNav(activeKey) {
  const nav = document.createElement("nav");
  nav.className = "mobile-bottom-nav";
  nav.setAttribute("aria-label", "Navigation mobile");
  for (const item of MOBILE_NAV_ITEMS) {
    const a = document.createElement("a");
    a.href = item.href;
    a.className = item.key === activeKey ? "mobile-tab active" : "mobile-tab";
    const ic = document.createElement("span");
    ic.className = "mobile-tab-icon";
    ic.appendChild(icon(item.icon));
    const lb = document.createElement("span");
    lb.className = "mobile-tab-label";
    lb.textContent = item.label;
    a.append(ic, lb);
    nav.appendChild(a);
  }
  return nav;
}

/**
 * Injecte le layout dans #app-shell et retourne l'élément <main> où la page
 * écrit son contenu.
 */
export function renderLayout(activeKey) {
  const shell = document.getElementById("app-shell");
  shell.classList.add("app-shell");
  let mobileOpen = false;
  let backdrop = null;

  function setOpen(open) {
    mobileOpen = open;
    sidebar.classList.toggle("mobile-open", open);
    if (open && !backdrop) {
      backdrop = document.createElement("button");
      backdrop.type = "button";
      backdrop.className = "sidebar-backdrop";
      backdrop.setAttribute("aria-label", "Fermer le menu");
      backdrop.addEventListener("click", () => setOpen(false));
      shell.appendChild(backdrop);
    } else if (!open && backdrop) {
      backdrop.remove();
      backdrop = null;
    }
  }

  const sidebar = buildSidebar(activeKey, () => setOpen(false));

  const body = document.createElement("div");
  body.className = "app-body";

  const main = document.createElement("main");
  main.className = "app-main";

  const topbar = buildTopbar(activeKey, () => setOpen(true));

  body.append(topbar, main, buildMobileNav(activeKey));
  shell.append(sidebar, body);

  return main;
}
