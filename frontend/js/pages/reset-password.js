// Port de ResetPassword.jsx — token depuis ?token=...
import { apiRequest } from "../api.js";
import { hide, setLoadingButton, show } from "./helpers.js";

const params = new URLSearchParams(window.location.search);
const tokenInput = document.getElementById("reset-token");
const passwordInput = document.getElementById("new-password");
const errorBox = document.getElementById("form-error");
const submitBtn = document.getElementById("submit-btn");

tokenInput.value = params.get("token") || "";

document.getElementById("reset-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  hide(errorBox);
  setLoadingButton(submitBtn, true, "Réinitialisation…", "Réinitialiser");

  try {
    await apiRequest("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({
        token: tokenInput.value,
        new_password: passwordInput.value,
      }),
    });
    window.location.href = "login.html";
  } catch (err) {
    show(errorBox, err.message);
    setLoadingButton(submitBtn, false, "", "Réinitialiser");
  }
});
