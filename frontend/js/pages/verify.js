// Port de VerifyEmail.jsx — token depuis ?token=... (URL) ou ?verification_token=...
import { apiRequest } from "../api.js";
import { hide, show } from "./helpers.js";

const params = new URLSearchParams(window.location.search);
const tokenInput = document.getElementById("verify-token");
const errorBox = document.getElementById("form-error");
const successBox = document.getElementById("form-success");
const submitBtn = document.getElementById("submit-btn");

tokenInput.value = params.get("token") || params.get("verification_token") || "";

document.getElementById("verify-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  hide(errorBox);
  hide(successBox);
  submitBtn.disabled = true;
  submitBtn.textContent = "Vérification…";

  try {
    const data = await apiRequest(
      `/auth/verify-email?token=${encodeURIComponent(tokenInput.value)}`,
      { method: "GET" }
    );
    show(successBox, data.message);
  } catch (err) {
    show(errorBox, err.message);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Vérifier mon email";
  }
});
