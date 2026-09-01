// Petits utilitaires partagés entre les pages (création DOM sûre, pas d'innerHTML
// avec des données externes => pas de XSS).

export function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

export function show(elNode, message) {
  elNode.textContent = message;
  elNode.hidden = false;
}

export function hide(elNode) {
  elNode.hidden = true;
  elNode.textContent = "";
}

export function setLoadingButton(btn, loading, loadingLabel, normalLabel) {
  btn.disabled = loading;
  btn.textContent = "";
  if (loading) {
    const spinner = document.createElement("span");
    spinner.className = "spinner";
    btn.appendChild(spinner);
    btn.appendChild(document.createTextNode(loadingLabel));
  } else {
    btn.textContent = normalLabel;
  }
}

// Port de DocumentCard.formatDate : le backend fournit modified_at sous forme
// de timestamp Unix en secondes.
export function formatDate(value) {
  if (!value) return "";
  const numeric = Number(value);
  let date;
  if (Number.isFinite(numeric) && String(value).trim() === String(numeric)) {
    const ms = numeric < 1e12 ? numeric * 1000 : numeric;
    date = new Date(ms);
  } else {
    date = new Date(value);
  }
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("fr-FR");
}

// Port de Dashboard.fileTypeLabel / Search.fileTypeLabel
export function fileTypeLabel(fileType) {
  const label = (fileType || ".pdf").replace(/^\./, "").toUpperCase();
  return label || "PDF";
}

// Toggle afficher/masquer mot de passe pour les pages auth.
export function bindPwdToggle(inputId, toggleId, eyeId, eyeOffId) {
  const input = document.getElementById(inputId);
  const toggle = document.getElementById(toggleId);
  const eyeOn = document.getElementById(eyeId);
  const eyeOff = document.getElementById(eyeOffId);

  toggle.addEventListener("click", () => {
    const showPwd = input.type === "password";
    input.type = showPwd ? "text" : "password";
    eyeOn.hidden = showPwd;
    eyeOff.hidden = !showPwd;
    const label = showPwd ? "Masquer le mot de passe" : "Afficher le mot de passe";
    toggle.setAttribute("title", label);
    toggle.setAttribute("aria-label", label);
  });
}
