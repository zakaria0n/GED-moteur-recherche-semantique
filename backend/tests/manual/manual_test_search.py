"""Script de test automatisé : 20 recherches sémantiques via l'API."""

import requests
import json
import time

BASE = "http://127.0.0.1:8000"

# ── Connexion ──────────────────────────────────────────────────────────────
resp = requests.post(f"{BASE}/auth/login", json={
    "email": "stage.demo.week4@example.com",
    "password": "Demo1234!",
    "remember_me": False,
})
assert resp.status_code == 200, f"Login echoue: {resp.status_code} {resp.text}"
token = resp.json()["token"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
print("Connecte avec succes.\n")

# ── 20 tests ───────────────────────────────────────────────────────────────
tests = [
    {"query": "bulletin de salaire",       "expected_cat": "Salaires",     "desc": "Recherche document salaire"},
    {"query": "attestation de travail",    "expected_cat": "Administratif","desc": "Attestation travail"},
    {"query": "assurance habitation",      "expected_cat": "Assurance",    "desc": "Assurance habitation"},
    {"query": "contrat de bail",           "expected_cat": "Contrats",     "desc": "Contrat bail"},
    {"query": "facture fournisseur",       "expected_cat": "Factures",     "desc": "Facture fournisseur"},
    {"query": "releve bancaire",           "expected_cat": "Banque",       "desc": "Releve bancaire"},
    {"query": "certificat medical",        "expected_cat": "Administratif","desc": "Certificat medical"},
    {"query": "demande de conge",          "expected_cat": "Administratif","desc": "Demande conge"},
    {"query": "acte de naissance",         "expected_cat": "Administratif","desc": "Acte naissance"},
    {"query": "pret immobilier",           "expected_cat": "Banque",       "desc": "Pret immobilier"},
    {"query": "declaration sinistre",      "expected_cat": "Assurance",    "desc": "Declaration sinistre"},
    {"query": "lettre de demission",       "expected_cat": "Administratif","desc": "Lettre demission"},
    {"query": "scan procedure interne",    "expected_cat": "Scan",         "desc": "Scan procedure"},
    {"query": "entreprise rapport activite","expected_cat": "Entreprise",   "desc": "Rapport activite"},
    {"query": "echantillon analyse poisson","expected_cat": "Echantillons", "desc": "Echantillon poisson"},
    {"query": "virement bancaire",         "expected_cat": "Banque",       "desc": "Virement bancaire"},
    {"query": "constat amiable accident",  "expected_cat": "Assurance",    "desc": "Constat amiable"},
    {"query": "bulletin de paie",          "expected_cat": "Salaires",     "desc": "Bulletin paie"},
    {"query": "attestation domicile",      "expected_cat": "Administratif","desc": "Attestation domicile"},
    {"query": "rib releve identite bancaire","expected_cat": "Banque",     "desc": "RIB bancaire"},
]

passed = 0
failed = 0
partial = 0
all_results = []

print(f"{'#':>3} | {'Statut':>8} | {'Res':>3} | {'Latence':>8} | {'Categorie':>15} | {'Fichier'}")
print("-" * 110)

for i, test in enumerate(tests, 1):
    start = time.time()
    resp = requests.post(
        f"{BASE}/search",
        headers=headers,
        json={"query": test["query"], "top_k": 5},
    )
    latency_ms = (time.time() - start) * 1000

    if resp.status_code != 200:
        status = "ERROR"
        results_count = 0
        best_cat = "N/A"
        best_file = f"HTTP {resp.status_code}"
        has_results = False
    else:
        data = resp.json()
        results_count = data.get("results_count", 0)
        results = data.get("results", [])
        suggestions = data.get("suggestions", [])
        has_results = results_count > 0

        best_cat = ""
        best_file = ""
        cat_ok = False
        if results:
            best = results[0]
            best_file = best.get("file_name", "")
            rel_path = best.get("relative_path", "")
            best_cat = rel_path.replace("\\", "/").split("/")[0] if "/" in rel_path else "_root"
            cat_ok = (
                test["expected_cat"].lower() in best_cat.lower()
                or test["expected_cat"].lower() in best_file.lower()
            )

        if has_results and cat_ok:
            status = "PASS"
            passed += 1
        elif has_results:
            status = "PARTIAL"
            partial += 1
        else:
            status = "FAIL"
            failed += 1

    print(
        f"{i:3d} | {status:>8} | {results_count:3d} | {latency_ms:7.1f}ms | {best_cat:>15} | {best_file[:50]}"
    )

    all_results.append({
        "num": i,
        "query": test["query"],
        "desc": test["desc"],
        "expected_cat": test["expected_cat"],
        "status": status,
        "results_count": results_count,
        "best_file": best_file,
        "best_cat": best_cat,
        "latency_ms": round(latency_ms, 1),
    })

# ── Résumé ─────────────────────────────────────────────────────────────────
total = len(tests)
print()
print("=" * 80)
print("  RÉSUMÉ DES 20 TESTS DE RECHERCHE")
print("=" * 80)
print(f"  PASS   : {passed}/{total} ({passed/total*100:.0f}%)")
print(f"  PARTIAL: {partial}/{total} ({partial/total*100:.0f}%) - résultat trouvé mais catégorie inexacte")
print(f"  FAIL   : {failed}/{total} ({failed/total*100:.0f}%)")
print(f"  TOTAL  : {total}")
print("=" * 80)

# Détails des PARTIAL et FAIL
issues = [r for r in all_results if r["status"] != "PASS"]
if issues:
    print()
    print("DÉTAILS DES PROBLÈMES:")
    print("-" * 80)
    for r in issues:
        print(f"  Test {r['num']:2d} [{r['status']:8s}] «{r['query']}»")
        print(f"       Attendu: {r['expected_cat']}, Obtenu: {r['best_cat']}")
        print(f"       Meilleur fichier: {r['best_file']}")
        print()
else:
    print("\nTous les tests sont passés avec succès !")

# Latence moyenne
latencies = [r["latency_ms"] for r in all_results if r["latency_ms"] > 0]
if latencies:
    avg = sum(latencies) / len(latencies)
    mx = max(latencies)
    mn = min(latencies)
    print(f"\nLatence moyenne: {avg:.1f}ms | min: {mn:.1f}ms | max: {mx:.1f}ms")
