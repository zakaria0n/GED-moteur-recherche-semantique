// Port de Login.jsx
import { apiRequest, setToken } from "../api.js";
import { bindPwdToggle, hide, setLoadingButton, show } from "./helpers.js";

const form = document.getElementById("login-form");
const errorBox = document.getElementById("form-error");
const submitBtn = document.getElementById("submit-btn");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const rememberInput = document.getElementById("remember_me");

bindPwdToggle("password", "pwd-toggle", "eye-icon", "eye-off-icon");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!emailInput.value || !passwordInput.value) return;
  hide(errorBox);
  setLoadingButton(submitBtn, true, "Connexion…", "Se connecter");

  try {
    const data = await apiRequest("/auth/login", {
      method: "POST",
      body: JSON.stringify({
        email: emailInput.value,
        password: passwordInput.value,
        remember_me: rememberInput.checked,
      }),
    });
    // Cookie httpOnly pose par le backend + token garde en secours pour les
    // requêtes cross-site (ex : front sur localhost:5500, API sur 127.0.0.1:8000,
    // où le cookie SameSite n'est pas envoyé).
    if (data.token) setToken(data.token);
    window.location.href = "dashboard.html";
  } catch (err) {
    show(errorBox, err.message);
    setLoadingButton(submitBtn, false, "", "Se connecter");
  }
});
