// Port de Register.jsx
import { apiRequest } from "../api.js";
import { bindPwdToggle, hide, setLoadingButton, show } from "./helpers.js";

const form = document.getElementById("register-form");
const errorBox = document.getElementById("form-error");
const submitBtn = document.getElementById("submit-btn");

bindPwdToggle("password", "pwd-toggle", "eye-icon", "eye-off-icon");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const fullName = document.getElementById("full_name").value.trim();
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;

  // Validation minimale côté client (équivalent required/minLength).
  if (!fullName || !email || password.length < 8) {
    if (password.length > 0 && password.length < 8) {
      show(errorBox, "Le mot de passe doit contenir au moins 8 caractères.");
      return;
    }
  }

  hide(errorBox);
  setLoadingButton(submitBtn, true, "Création…", "Créer le compte");

  try {
    const data = await apiRequest("/auth/register", {
      method: "POST",
      body: JSON.stringify({ full_name: fullName, email, password }),
    });
    // Jeton present seulement si l'email n'a pas pu etre envoye (dev sans SMTP).
    const tokenParam = data.verification_token
      ? `&verification_token=${encodeURIComponent(data.verification_token)}`
      : "";
    window.location.href = `verify.html?email=${encodeURIComponent(email)}${tokenParam}`;
  } catch (err) {
    show(errorBox, err.message);
    setLoadingButton(submitBtn, false, "", "Créer le compte");
  }
});
