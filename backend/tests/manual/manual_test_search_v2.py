# -*- coding: utf-8 -*-
"""Script de test automatisé v2 : 20 recherches sémantiques via l'API."""

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
    {"query": "bulletin de salaire",        "expected_cat": "Salaires",      "expected_in_name": ["salaire", "bulletin", "paie"]},
    {"query": "attestation de travail",     "expected_cat": "Administratif", "expected_in_name": ["attestation", "travail"]},
    {"query": "assurance habitation",       "expected_cat": "Assurance",     "expected_in_name": ["assurance", "habitation"]},
    {"query": "contrat de bail",            "expected_cat": "Contrats",      "expected_in_name": ["contrat", "bail", "location"]},
    {"query": "facture fournisseur",        "expected_cat": "Factures",      "expected_in_name": ["facture", "fournisseur"]},
    {"query": "releve bancaire",            "expected_cat": "Banque",        "expected_in_name": ["releve", "banque", "bancaire"]},
    {"query": "certificat medical",         "expected_cat": "Administratif", "expected_in_name": ["certificat", "medical", "sante"]},
    {"query": "demande de conge",           "expected_cat": "Administratif", "expected_in_name": ["demande", "conge", "absence"]},
    {"query": "acte de naissance",          "expected_cat": "Administratif", "expected_in_name": ["acte", "naissance", "etat civil"]},
    {"query": "pret immobilier",            "expected_cat": "Banque",        "expected_in_name": ["pret", "immobilier", "credit"]},
    {"query": "declaration sinistre",       "expected_cat": "Assurance",     "expected_in_name": ["declaration", "sinistre", "accident"]},
    {"query": "lettre de demission",        "expected_cat": "Administratif", "expected_in_name": ["demission", "lettre", "resiliation"]},
    {"query": "scan procedure interne",     "expected_cat": "Scan",          "expected_in_name": ["scan", "procedure", "interne"]},
    {"query": "entreprise rapport activite", "expected_cat": "Entreprise",   "expected_in_name": ["rapport", "activite", "entreprise"]},
    {"query": "echantillon analyse poisson","expected_cat": "Echantillons",  "expected_in_name": ["echantillon", "poisson", "analyse"]},
    {"query": "virement bancaire",          "expected_cat": "Banque",        "expected_in_name": ["virement", "banque", "bancaire"]},
    {"query": "constat amiable accident",   "expected_cat": "Assurance",     "expected_in_name": ["constat", "amiable", "accident"]},
    {"query": "bulletin de paie",           "expected_cat": "Salaires",      "expected_in_name": ["bulletin", "paie", "salaire"]},
    {"query": "attestation domicile",       "expected_cat": "Administratif", "expected_in_name": ["attestation", "domicile", "adresse"]},
    {"query": "rib releve identite bancaire","expected_cat": "Banque",       "expected_in_name": ["rib", "releve", "identite", "bancaire"]},
]

def extract_category(relative_path):
    """Extrait la catégorie du chemin du fichier."""
    norm = relative_path.replace("\\", "/")
    parts = norm.split("/")
    return parts[0] if len(parts) > 1 else "_root"


def check_match(test, result):
    """Vérifie si un résultat correspond au test attendu."""
    rel_path = result.get("relative_path", "")
    file_name = result.get("file_name", "").lower()
    cat = extract_category(rel_path)

    # Vérification catégorie (fuzzy)
    cat_match = test["expected_cat"].lower() in cat.lower()

    # Vérification nom de fichier (un des mots attendus)
    name_match = any(m.lower() in file_name for m in test["expected_in_name"])

    return cat_match, name_match


passed = 0
failed = 0
partial = 0
all_results = []

print(f"{'#':>3} | {'Statut':>8} | {'Res':>3} | {'Latence':>8} | {'Categorie':>15} | {'Fichier'}")
print("-" * 115)

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
    else:
        data = resp.json()
        results_count = data.get("results_count", 0)
        results = data.get("results", [])

        best_cat = ""
        best_file = ""
        if results:
            best = results[0]
            best_file = best.get("file_name", "")
            best_cat = extract_category(best.get("relative_path", ""))
            cat_ok, name_ok = check_match(test, best)

            if cat_ok or name_ok:
                status = "PASS"
            elif results_count > 0:
                # Vérifier si au moins un des top 5 est bon
                any_ok = False
                for r in results[:5]:
                    c, n = check_match(test, r)
                    if c or n:
                        any_ok = True
                        break
                if any_ok:
                    status = "PARTIAL"
                else:
                    status = "FAIL"
            else:
                status = "FAIL"
        else:
            status = "FAIL"

    if status == "PASS":
        passed += 1
    elif status == "PARTIAL":
        partial += 1
    else:
        failed += 1

    marker = "[OK]" if status == "PASS" else ("[~~]" if status == "PARTIAL" else "[--]")
    print(
        f"{i:3d} | {marker} {status:>7s} | {results_count:3d} | {latency_ms:7.1f}ms | {best_cat:>15} | {best_file[:50]}"
    )

    all_results.append({
        "num": i,
        "query": test["query"],
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
print("  RÉSUMÉ DES 20 TESTS DE RECHERCHE SÉMANTIQUE")
print("=" * 80)
print(f"  [OK]  PASS   : {passed}/{total} ({passed/total*100:.0f}%) - resultat pertinent en 1ere position")
print(f"  [~~]  PARTIAL: {partial}/{total} ({partial/total*100:.0f}%) - resultat trouve dans le top 5 mais pas en 1er")
print(f"  [--]  FAIL   : {failed}/{total} ({failed/total*100:.0f}%) - aucun resultat pertinent")
print(f"  -----------")
print(f"  TOTAL        : {total}")
print("=" * 80)

# Détails des PARTIAL et FAIL
issues = [r for r in all_results if r["status"] != "PASS"]
if issues:
    print()
    print("DETAILS DES PROBLEMES:")
    print("-" * 80)
    for r in issues:
        print(f"  Test {r['num']:2d} [{r['status']:8s}] \"{r['query']}\"")
        print(f"       Categorie obtenue: {r['best_cat']}")
        print(f"       Meilleur fichier : {r['best_file']}")
        print()

# Latences
latencies = [r["latency_ms"] for r in all_results if r["latency_ms"] > 0]
if latencies:
    avg = sum(latencies) / len(latencies)
    mx = max(latencies)
    mn = min(latencies)
    print(f"Performance:")
    print(f"  Latence moyenne : {avg:.1f}ms")
    print(f"  Latence min     : {mn:.1f}ms")
    print(f"  Latence max     : {mx:.1f}ms")
    print(f"  Toutes sous 500ms : {'OUI' if mx < 500 else 'NON'}")
