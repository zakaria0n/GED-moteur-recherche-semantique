// Port de ForgotPassword.jsx
import { apiRequest } from "../api.js";
import { el, hide, setLoadingButton, show } from "./helpers.js";

const form = document.getElementById("forgot-form");
const emailInput = document.getElementById("email");
const errorBox = document.getElementById("form-error");
const successBox = document.getElementById("form-success");
const submitBtn = document.getElementById("submit-btn");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  hide(errorBox);
  hide(successBox);
  setLoadingButton(submitBtn, true, "Envoi…", "Recevoir le lien");

  try {
    const data = await apiRequest("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email: emailInput.value.trim() }),
    });
    if (data.reset_token) {
      show(successBox, "Jeton de réinitialisation généré, redirection…");
      const linkWrap = el("p");
      linkWrap.style.marginTop = "8px";
      const link = el("a", null, "réinitialisation");
      link.href = `reset-password.html?token=${encodeURIComponent(data.reset_token)}`;
      linkWrap.append("Rendez-vous sur la page de ", link, ".");
      successBox.appendChild(linkWrap);
      setTimeout(() => {
        window.location.href = `reset-password.html?token=${encodeURIComponent(data.reset_token)}`;
      }, 600);
    } else {
      show(successBox, "Si le compte existe, un email de réinitialisation a été envoyé.");
    }
  } catch (err) {
    show(errorBox, err.message);
  } finally {
    setLoadingButton(submitBtn, false, "", "Recevoir le lien");
  }
});
