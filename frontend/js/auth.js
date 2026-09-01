// Équivalent AuthContext.jsx — garde d'authentification pour pages statiques.
import { apiRequest, getToken, setToken, clearToken } from "./api.js";

// --- Theme : appliquer le choix sauvegarde au chargement ---
// Theme clair par defaut (identique a la page d'accueil). Le mode sombre ne
// s'active que si l'utilisateur l'a choisie lui-meme via le bouton de la
// topbar (jamais automatiquement via la preference systeme).
(function initTheme() {
  const saved = localStorage.getItem("ged_theme");
  if (saved === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  }
})();

let _user = null;
let _ready = false; // authReady
const listeners = [];

export function getUser() {
  return _user;
}

export function setUser(user) {
  _user = user;
}

// Le token de session est désormais transporté par un cookie httpOnly posé par le
// backend : on ne le stocke plus côté JS (réduit le risque de vol par XSS). Cette
// fonction reste une coquille sans effet pour préserver l'API existante.
export function login(_newToken) {
  // volontairement vide : l'authentification passe par le cookie de session
}

export function logoutLocal() {
  clearToken();
  _user = null;
}

function onAuthReady(fn) {
  if (_ready) fn();
  else listeners.push(fn);
}

/**
 * Garde des pages protégées : valide la session via GET /auth/me (le cookie de
 * session httpOnly est envoyé automatiquement avec credentials:"include"), affiche
 * un spinner pendant la validation, puis appelle onReady(user). Redirige vers
 * login.html si la session est absente ou invalide.
 */
export function requireAuth(onReady) {
  // Spinner plein écran pendant la validation (évite le flash de contenu).
  const loader = document.createElement("div");
  loader.className = "auth-loading";
  const spinner = document.createElement("span");
  spinner.className = "spinner";
  loader.appendChild(spinner);
  document.body.appendChild(loader);
  document.body.classList.add("auth-loading");

  apiRequest("/auth/me", { method: "GET" })
    .then((data) => {
      _user = data.user;
      _ready = true;
      document.body.classList.remove("auth-loading");
      loader.remove();
      if (onReady) onReady(_user);
      listeners.forEach((fn) => fn(_user));
    })
    .catch(() => {
      clearToken();
      _user = null;
      _ready = true;
      window.location.replace("login.html");
    });
}

export { getToken, setToken, clearToken };
