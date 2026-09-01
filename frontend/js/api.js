// Port fidèle de src/api.js — vanilla JS (ES module)
export const API_BASE_URL = "http://127.0.0.1:8000";
export const TOKEN_KEY = "ged_auth_token";
export const HISTORY_KEY = "ged_search_history";

const REQUEST_TIMEOUT_MS = 15000;

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export function fileUrl(relativePath) {
  return `${API_BASE_URL}/files/${encodeURI(relativePath.replace(/\\/g, "/"))}`;
}

// Double mécanisme d'authentification :
//  - cookie httpOnly posé par le backend (fonctionne quand front et back sont
//    sur le même site, ex 127.0.0.1) ;
//  - header Authorization: Bearer en secours, indispensable quand la page est
//    servie depuis localhost:5500 (site différent de 127.0.0.1:8000 pour les
//    cookies SameSite -> le cookie n'y est pas envoyé).
export async function apiRequest(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };

  const token = getToken();

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      credentials: "include",
      signal: controller.signal,
    });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("Le serveur met trop de temps à répondre. Réessayez.");
    }
    throw new Error("Impossible de contacter le serveur. Vérifiez que le backend est lancé.");
  } finally {
    clearTimeout(timeoutId);
  }

  const contentType = response.headers.get("content-type") || "";

  if (contentType.includes("application/json")) {
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.detail || "Erreur serveur");
      error.status = response.status;
      throw error;
    }
    return data;
  }

  if (!response.ok) {
    const error = new Error("Erreur serveur");
    error.status = response.status;
    throw error;
  }

  return response;
}

// Ouvre un document dans un nouvel onglet en passant par le backend
// authentifie (cookie de session via credentials + Bearer en secours).
export async function openDocument(relativePath) {
  const headers = {};
  const token = getToken();

  if (token) headers["Authorization"] = `Bearer ${token}`;

  const response = await fetch(fileUrl(relativePath), {
    credentials: "include",
    headers,
  });

  if (!response.ok) {
    throw new Error("Impossible d'ouvrir le document.");
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank");
  // Liberation tardive pour ne pas casser l'affichage d'un PDF long.
  setTimeout(() => URL.revokeObjectURL(url), 10 * 60 * 1000);
}

// ---- Historique local de recherche ----
export function readHistory() {
  try {
    return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]");
  } catch {
    return [];
  }
}

export function addHistoryItem(item) {
  try {
    const current = readHistory();
    // Deduplication : une meme requete (avec meme top_k) remonte en haut.
    const next = [
      item,
      ...current.filter(
        (existing) =>
          !(existing.query === item.query && existing.top_k === item.top_k)
      ),
    ].slice(0, 20);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
  } catch {
    // ignore storage errors
  }
}

export function removeHistoryItem(timestamp, query) {
  try {
    const next = readHistory().filter(
      (item) => !(item.timestamp === timestamp && item.query === query)
    );
    localStorage.setItem(HISTORY_KEY, JSON.stringify(next));
  } catch {
    // ignore storage errors
  }
}

export function clearHistory() {
  try {
    localStorage.removeItem(HISTORY_KEY);
  } catch {
    // ignore storage errors
  }
}

export function categoryOf(relativePath) {
  const segment = relativePath.replace(/\\/g, "/").split("/")[0];
  return segment || "Documents";
}
