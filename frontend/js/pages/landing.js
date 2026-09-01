// Port de Landing.jsx : année du footer + CTA selon l'état de connexion.
// Le cookie de session est httpOnly : on ne peut pas le lire en JS, on interroge
// donc /auth/me (le cookie est envoyé automatiquement via credentials:"include").
import { apiRequest } from "../api.js";

document.getElementById("footer-year").textContent = new Date().getFullYear();

const cta = document.getElementById("cta-connect");
apiRequest("/auth/me", { method: "GET" })
  .then(() => {
    cta.textContent = "Accéder à mon espace";
    cta.href = "dashboard.html";
  })
  .catch(() => {
    // non connecté : on garde le CTA par défaut (connexion / inscription)
  });
