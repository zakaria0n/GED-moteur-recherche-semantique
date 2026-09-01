// Port de Profile.jsx (+ AccountCard, PersonalInformation, SecuritySection,
// DangerZone, format.js).
import { apiRequest } from "../api.js";
import { getUser, setUser, logoutLocal } from "../auth.js";
import { el } from "./helpers.js";
import { initials } from "../layout.js";

const EYE_SVG =
  '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" /></svg>';
const EYE_OFF_SVG =
  '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c6.5 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" /><path d="M6.61 6.61A13.53 13.53 0 0 0 2 12s3.5 7 10 7a9.74 9.74 0 0 0 5.39-1.61" /><path d="M14.12 14.12A3 3 0 1 1 9.88 9.88" /><path d="m2 2 20 20" /></svg>';

function formatDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

function buildPanel(titleText, subText) {
  const section = el("section", "panel-section");
  const title = el("div", "panel-title");
  const wrap = el("div", "pt-wrap");
  wrap.append(el("h2", null, titleText), el("span", "pt-sub", subText));
  title.appendChild(wrap);
  return { section, title };
}

// ---- AccountCard ----
function buildAccountCard() {
  const user = getUser();
  const { section, title } = buildPanel("Mon compte", "Coordonnées du compte");

  const avatar = el("span", "account-avatar", initials(user?.full_name));
  title.appendChild(avatar);

  const body = el("div", "panel-body");
  const dl = el("dl", "account-defs");
  const rows = [
    { k: "Identifiant", v: `#${user?.id ?? "—"}` },
    { k: "Créé le", v: formatDate(user?.created_at) },
    { k: "Mis à jour", v: formatDate(user?.updated_at) },
  ];
  for (const row of rows) {
    const def = el("div", "account-def");
    def.appendChild(el("dt", null, row.k));
    const dd = document.createElement("dd");
    dd.title = row.v;
    dd.textContent = row.v;
    def.appendChild(dd);
    dl.appendChild(def);
  }
  body.appendChild(dl);

  section.append(title, body);
  return section;
}

// ---- PersonalInformation ----
function buildPersonalInformation() {
  const user = getUser();
  const { section, title } = buildPanel(
    "Informations personnelles",
    "Coordonnées associées à votre compte."
  );
  const body = el("div", "panel-body");
  const form = el("form");
  form.noValidate = true;

  const grid = el("div", "settings-grid");

  function field(id, labelText, type, autoComplete, value) {
    const group = el("div", "form-group");
    group.appendChild(el("label", null, labelText));
    const input = document.createElement("input");
    input.id = id;
    if (type) input.type = type;
    input.autocomplete = autoComplete || "off";
    input.required = true;
    input.value = value;
    group.appendChild(input);
    grid.appendChild(group);
    return input;
  }

  const nameInput = field("pf-name", "Nom complet", null, "name", user?.full_name || "");
  const emailInput = field("pf-email", "Adresse e-mail", "email", "email", user?.email || "");
  form.appendChild(grid);

  const actionsRow = el("div", "settings-form-actions");
  const feedback = el("p");
  feedback.hidden = true;

  const submitBtn = el("button", "btn btn-primary", "Enregistrer");
  submitBtn.type = "submit";

  actionsRow.append(feedback, submitBtn);
  form.appendChild(actionsRow);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    feedback.hidden = true;
    submitBtn.disabled = true;
    submitBtn.textContent = "Enregistrement…";
    try {
      const data = await apiRequest(
        "/auth/profile",
        {
          method: "PUT",
          body: JSON.stringify({
            full_name: nameInput.value,
            email: emailInput.value,
          }),
        },
      );
      feedback.textContent = data.message || "Informations enregistrées.";
      feedback.className = "settings-feedback ok";
      feedback.setAttribute("role", "status");
      feedback.hidden = false;
      if (data.user) setUser(data.user);
    } catch (error) {
      feedback.textContent = error.message;
      feedback.className = "settings-feedback err";
      feedback.setAttribute("role", "alert");
      feedback.hidden = false;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Enregistrer";
    }
  });

  body.appendChild(form);
  section.append(title, body);
  return section;
}

// ---- SecuritySection ----
function strengthScore(pwd) {
  let score = 0;
  if (pwd.length >= 8) score += 1;
  if (pwd.length >= 12) score += 1;
  if (/[a-z]/.test(pwd) && /[A-Z]/.test(pwd)) score += 1;
  if (/\d/.test(pwd) && /[^A-Za-z0-9]/.test(pwd)) score += 1;
  return score;
}

const STRENGTH_LABELS = ["", "Faible", "Moyen", "Bon", "Fort"];

function pwdField(id, labelText, autoComplete) {
  const group = el("div", "form-group");
  group.appendChild(el("label", null, labelText));
  const wrap = el("div", "pwd-field");
  const input = document.createElement("input");
  input.id = id;
  input.type = "password";
  input.autocomplete = autoComplete;
  input.required = true;
  const toggle = el("button", "pwd-toggle");
  toggle.type = "button";
  toggle.innerHTML = EYE_SVG;
  let shown = false;
  toggle.addEventListener("click", () => {
    shown = !shown;
    input.type = shown ? "text" : "password";
    toggle.innerHTML = shown ? EYE_OFF_SVG : EYE_SVG;
    const label = shown ? "Masquer le mot de passe" : "Afficher le mot de passe";
    toggle.setAttribute("aria-label", label);
    toggle.setAttribute("aria-pressed", String(shown));
  });
  toggle.setAttribute("aria-label", "Afficher le mot de passe");
  toggle.setAttribute("aria-pressed", "false");
  wrap.append(input, toggle);
  group.appendChild(wrap);
  return { group, input };
}

function buildSecuritySection() {
  const { section, title } = buildPanel(
    "Sécurité",
    "Mettez à jour votre mot de passe. Une reconnexion sera nécessaire."
  );
  const body = el("div", "panel-body");
  const form = el("form");
  form.noValidate = true;

  const grid = el("div", "settings-grid");
  const current = pwdField("pwd-current", "Mot de passe actuel", "current-password");
  const next = pwdField("pwd-new", "Nouveau mot de passe", "new-password");

  // Jauge de force du mot de passe
  const strength = el("div", "strength");
  strength.setAttribute("aria-hidden", "true");
  strength.hidden = true;
  const track = el("div", "strength-track");
  const fill = el("div", "strength-fill");
  track.appendChild(fill);
  const label = el("span", "strength-label");
  strength.append(track, label);
  next.group.appendChild(strength);
  next.input.addEventListener("input", () => {
    const score = strengthScore(next.input.value);
    if (next.input.value.length > 0) {
      strength.hidden = false;
      fill.style.width = `${(score / 4) * 100}%`;
      label.textContent = STRENGTH_LABELS[score];
    } else {
      strength.hidden = true;
    }
  });

  grid.append(current.group, next.group);
  form.appendChild(grid);

  form.appendChild(
    el(
      "p",
      "settings-hint",
      "Au moins 8 caractères — privilégiez un mélange de lettres, chiffres et symboles."
    )
  );

  const actionsRow = el("div", "settings-form-actions");
  const feedback = el("p");
  feedback.hidden = true;
  const submitBtn = el("button", "btn btn-primary", "Mettre à jour");
  submitBtn.type = "submit";
  actionsRow.append(feedback, submitBtn);
  form.appendChild(actionsRow);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    feedback.hidden = true;
    submitBtn.disabled = true;
    submitBtn.textContent = "Mise à jour…";
    try {
      const data = await apiRequest(
        "/auth/change-password",
        {
          method: "PUT",
          body: JSON.stringify({
            current_password: current.input.value,
            new_password: next.input.value,
          }),
        },
      );
      feedback.textContent = data.message || "Mot de passe mis à jour. Reconnexion nécessaire…";
      feedback.className = "settings-feedback ok";
      feedback.setAttribute("role", "status");
      feedback.hidden = false;
      current.input.value = "";
      next.input.value = "";
      strength.hidden = true;
      setTimeout(() => {
        logoutLocal();
        window.location.href = "login.html";
      }, 1400);
    } catch (error) {
      feedback.textContent = error.message;
      feedback.className = "settings-feedback err";
      feedback.setAttribute("role", "alert");
      feedback.hidden = false;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Mettre à jour";
    }
  });

  body.appendChild(form);
  section.append(title, body);
  return section;
}

// ---- DangerZone ----
function buildDangerZone() {
  const { section, title } = buildPanel(
    "Supprimer le compte",
    "Supprime définitivement votre compte ainsi que toutes les données associées."
  );

  // Classe supplémentaire danger-card
  section.classList.add("danger-card");
  const body = el("div", "panel-body");

  let open = false;

  function render() {
    body.textContent = "";
    if (!open) {
      const openBtn = el("button", "btn btn-danger-outline", "Supprimer le compte");
      openBtn.type = "button";
      openBtn.addEventListener("click", () => {
        open = true;
        render();
      });
      body.appendChild(openBtn);
      return;
    }

    const form = el("form");
    form.noValidate = true;

    const warning = el("p", "danger-warning");
    warning.append(
      document.createTextNode("La suppression est "),
      Object.assign(el("strong"), { textContent: "définitive et irréversible" }),
      document.createTextNode(" : votre compte, vos documents et votre historique seront effacés.")
    );
    form.appendChild(warning);

    const errLine = el("p", "form-error");
    errLine.setAttribute("role", "alert");
    errLine.hidden = true;
    form.appendChild(errLine);

    const checkboxLine = el("label", "checkbox-line");
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkboxLine.append(checkbox, el("span", null, "Je comprends que cette action est irréversible."));
    form.appendChild(checkboxLine);

    const confirmRow = el("div", "danger-confirm-row");
    const group = el("div", "form-group");
    group.appendChild(el("label", null, "Mot de passe actuel"));
    const passwordInput = document.createElement("input");
    passwordInput.id = "del-password";
    passwordInput.type = "password";
    passwordInput.autocomplete = "current-password";
    passwordInput.placeholder = "••••••••";
    passwordInput.required = true;
    group.appendChild(passwordInput);
    confirmRow.appendChild(group);

    const actionsRow = el("div", "danger-actions");
    const cancelBtn = el("button", "btn btn-ghost", "Annuler");
    cancelBtn.type = "button";
    cancelBtn.addEventListener("click", () => {
      open = false;
      render();
    });
    const deleteBtn = el("button", "btn btn-danger", "Supprimer définitivement");
    deleteBtn.type = "submit";
    deleteBtn.disabled = true;
    checkbox.addEventListener("change", () => {
      deleteBtn.disabled = !(checkbox.checked && passwordInput.value.length > 0);
    });
    passwordInput.addEventListener("input", () => {
      deleteBtn.disabled = !(checkbox.checked && passwordInput.value.length > 0);
    });
    actionsRow.append(cancelBtn, deleteBtn);
    confirmRow.appendChild(actionsRow);
    form.appendChild(confirmRow);

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      errLine.hidden = true;
      deleteBtn.disabled = true;
      deleteBtn.textContent = "Suppression…";
      try {
        await apiRequest(
          "/auth/delete-account",
          { method: "DELETE", body: JSON.stringify({ password: passwordInput.value }) },
          token
        );
        logoutLocal();
        window.location.href = "index.html";
      } catch (error) {
        errLine.textContent = error.message;
        errLine.hidden = false;
        deleteBtn.disabled = false;
        deleteBtn.textContent = "Supprimer définitivement";
      }
    });

    body.appendChild(form);
  }

  render();
  section.append(title, body);
  return section;
}

export function initProfile(main) {
  const page = el("div", "settings-page");

  const header = el("header", "page-header");
  const hLeft = el("div");
  hLeft.append(
    el("h1", "page-title", "Profil"),
    el(
      "p",
      "page-subtitle",
      "Gérez vos informations personnelles, la sécurité et les paramètres de votre compte."
    )
  );
  header.appendChild(hLeft);
  page.appendChild(header);

  const layout = el("div", "settings-layout");
  layout.appendChild(buildAccountCard());
  const col = el("div", "settings-col");
  col.append(buildPersonalInformation(), buildSecuritySection(), buildDangerZone());
  layout.appendChild(col);

  page.appendChild(layout);
  main.appendChild(page);
}
