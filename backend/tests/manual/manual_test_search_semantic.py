# -*- coding: utf-8 -*-
"""Tests semantiques avances : cas difficiles + focus Echantillons.

Ces tests evaluent la capacite du moteur a comprendre le SENS des documents
plutot que de simplement matcher des mots-cles. Les requetes sont formulees
de maniere indirecte, par concept ou par synonyme.
"""

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
assert resp.status_code == 200, f"Login echoue: {resp.status_code}"
token = resp.json()["token"]
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
print("Connecte avec succes.\n")


# ═══════════════════════════════════════════════════════════════════════════
#  PARTIE A — Tests sémantiques Echantillons (8 tests)
#  On cherche les 8 fichiers Echantillons avec des formulations indirectes.
# ═══════════════════════════════════════════════════════════════════════════
echantillon_tests = [
    {
        "query": "appel d'offres international intelligence artificielle",
        "expected_file_contains": ["RC AO"],
        "desc": "RC AO 12.2024 — reglement consultation strategie DATA & IA"
    },
    {
        "query": "serveurs centre regional Tanger oceauanographie peche",
        "expected_file_contains": ["Armoire"],
        "desc": "NP Armoire — mise en place serveurs centre Tanger"
    },
    {
        "query": "horloge pointage empreinte digitale controle acces",
        "expected_file_contains": ["Evolution", "USB", "Bio"],
        "desc": "Evolution USB Bio — horloge biometrique time clock"
    },
    {
        "query": "contrat maintenance infrastructure reseau hotline support",
        "expected_file_contains": ["CPS", "contrat"],
        "desc": "CPS — contrat assistance maintenance parc informatique"
    },
    {
        "query": "ordinateurs portables impressions specifications techniques",
        "expected_file_contains": ["caracteristiques"],
        "desc": "caracteristiques AO 2025 — PC, imprimantes, onduleurs"
    },
    {
        "query": "reorganisation activite cellule teledetection spatiale",
        "expected_file_contains": ["Note de service"],
        "desc": "Note de service — reorganisation Centre Regional Tanger"
    },
    {
        "query": "protection antiviruelle pare-feu securite reseau",
        "expected_file_contains": ["CPS", "Sophos", "Fortinet"],
        "desc": "CPS ou caracteristiques — securite informatique"
    },
    {
        "query": "imprimante laser copie numerisation A3",
        "expected_file_contains": ["caracteristiques", "Konica"],
        "desc": "caracteristiques AO 2025 — photocopieur Konica Minolta"
    },
]


# ═══════════════════════════════════════════════════════════════════════════
#  PARTIE B — Recherches sémantiques pures (concepts ≠ mots du document)
# ═══════════════════════════════════════════════════════════════════════════
concept_tests = [
    {
        "query": "comment proteger les donnees informatiques de l'entreprise",
        "expected_file_contains": ["Sophos", "CPS", "licence"],
        "desc": "Securite reseau → CPS ou caracteristiques (licence Sophos)"
    },
    {
        "query": "arreter de travailler pour raison de sante",
        "expected_file_contains": ["certificat", "medical"],
        "desc": "Arret maladie → certificat medical"
    },
    {
        "query": "quitter volontairement son emploi",
        "expected_file_contains": ["demission"],
        "desc": "Demission → lettre de demission"
    },
    {
        "query": "blessure accident voiture assurance",
        "expected_file_contains": ["constat", "amiable"],
        "desc": "Accident auto → constat amiable"
    },
    {
        "query": "preuve de domicile pour administration",
        "expected_file_contains": ["attestation", "domicile"],
        "desc": "Justificatif domicile → attestation domicile"
    },
    {
        "query": "combien gagne un employe par mois",
        "expected_file_contains": ["bulletin", "salaire", "paie"],
        "desc": "Remuneration → bulletin de salaire"
    },
]


# ═══════════════════════════════════════════════════════════════════════════
#  PARTIE C — Requetes ambiguës / multi-corpus
# ═══════════════════════════════════════════════════════════════════════════
ambiguous_tests = [
    {
        "query": "INRH institut recherche halieutique",
        "min_results": 3,
        "desc": "Requete generique INRH → au moins 3 resultats dans differents corpus"
    },
    {
        "query": "Casablanca Maroc adresse",
        "min_results": 3,
        "desc": "Localisation → documents contenant des adresses marocaines"
    },
]


all_tests = []
for t in echantillon_tests:
    all_tests.append({**t, "group": "Echantillons"})
for t in concept_tests:
    all_tests.append({**t, "group": "Concepts"})
for t in ambiguous_tests:
    all_tests.append({**t, "group": "Ambigues", "expected_file_contains": []})


def check_file_match(result, expected_parts):
    """Verifie si un fichier correspond aux fragments attendus."""
    fname = result.get("file_name", "").lower()
    rel = result.get("relative_path", "").replace("\\", "/").lower()
    for part in expected_parts:
        if part.lower() in fname or part.lower() in rel:
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
#  EXECUTION
# ═══════════════════════════════════════════════════════════════════════════
print("=" * 100)
print("  TESTS SEMANTIQUES AVANCES — Focus Echantillons + Cas Difficiles")
print("=" * 100)

passed = 0
partial = 0
failed = 0
all_results = []

for i, test in enumerate(all_tests, 1):
    start = time.time()
    resp = requests.post(
        f"{BASE}/search",
        headers=headers,
        json={"query": test["query"], "top_k": 10},
    )
    latency_ms = (time.time() - start) * 1000

    if resp.status_code != 200:
        print(f"\n  Test {i:2d} | ERROR HTTP {resp.status_code}")
        failed += 1
        continue

    data = resp.json()
    results = data.get("results", [])
    results_count = data.get("results_count", 0)

    # ── Verification ──
    group = test["group"]

    if group == "Ambigues":
        # Pour les requetes ambiguës, on verifie juste qu'on a assez de resultats
        ok = results_count >= test.get("min_results", 3)
        best_file = results[0]["file_name"] if results else "aucun"
        status = "PASS" if ok else "FAIL"
        match_detail = f"{results_count} resultats (min: {test.get('min_results', 3)})"
    else:
        expected_parts = test.get("expected_file_contains", [])
        # Chercher dans les 5 meilleurs resultats
        found_in_top = False
        found_rank = -1
        for rank, r in enumerate(results[:5]):
            if check_file_match(r, expected_parts):
                found_in_top = True
                found_rank = rank + 1
                break

        # Aussi chercher dans les 10 meilleurs
        found_in_10 = False
        for rank, r in enumerate(results[:10]):
            if check_file_match(r, expected_parts):
                found_in_10 = True
                if not found_in_top:
                    found_rank = rank + 1
                break

        best_file = results[0]["file_name"] if results else "aucun"
        if found_in_top:
            status = "PASS"
            match_detail = f"Trouve en position {found_rank}/10"
        elif found_in_10:
            status = "PARTIAL"
            match_detail = f"Trouve en position {found_rank}/10 (pas dans top 5)"
        else:
            status = "FAIL"
            match_detail = f"Absent des 10 premiers. Meilleur: {best_file[:45]}"

    marker = "[OK]" if status == "PASS" else ("[~~]" if status == "PARTIAL" else "[--]")

    if status == "PASS":
        passed += 1
    elif status == "PARTIAL":
        partial += 1
    else:
        failed += 1

    # Affichage compact
    print(
        f"\n  Test {i:2d} {marker} [{test['group']:12s}] {latency_ms:6.1f}ms"
    )
    print(f"         Requete: \"{test['query']}\"")
    print(f"         {match_detail}")
    print(f"         Description: {test['desc']}")
    if expected_parts and status != "PASS":
        print(f"         Attendu: {expected_parts}")

    all_results.append({
        "num": i,
        "group": group,
        "query": test["query"],
        "status": status,
        "results_count": results_count,
        "best_file": best_file,
        "latency_ms": round(latency_ms, 1),
    })

    # Afficher top 3 des résultats pour debug
    if results:
        print(f"         Top 3:")
        for j, r in enumerate(results[:3]):
            cat = r.get("relative_path", "").replace("\\", "/").split("/")[0]
            print(f"           {j+1}. {r['file_name'][:55]:55s} [{cat}] score={r.get('score', 0):.4f}")


# ═══════════════════════════════════════════════════════════════════════════
#  RÉSUMÉ
# ═══════════════════════════════════════════════════════════════════════════
total = len(all_tests)
print("\n")
print("=" * 100)
print("  RESUME — TESTS SEMANTIQUES AVANCES")
print("=" * 100)

# Par groupe
for group_name in ["Echantillons", "Concepts", "Ambigues"]:
    group_results = [r for r in all_results if r["group"] == group_name]
    g_pass = sum(1 for r in group_results if r["status"] == "PASS")
    g_total = len(group_results)
    g_pct = (g_pass / g_total * 100) if g_total > 0 else 0
    print(f"\n  {group_name:15s}: {g_pass}/{g_total} PASS ({g_pct:.0f}%)")
    for r in group_results:
        m = "[OK]" if r["status"] == "PASS" else ("[~~]" if r["status"] == "PARTIAL" else "[--]")
        print(f"    {m} {r['query'][:60]}")

print(f"\n  {'─' * 50}")
print(f"  TOTAL: {passed} PASS / {partial} PARTIAL / {failed} FAIL / {total} TESTS")
print(f"  Taux de reussite: {passed}/{total} ({passed/total*100:.0f}%)")
print("=" * 100)

# Latences
latencies = [r["latency_ms"] for r in all_results if r["latency_ms"] > 0]
if latencies:
    avg = sum(latencies) / len(latencies)
    mx = max(latencies)
    mn = min(latencies)
    print(f"\n  Performance:")
    print(f"    Moyenne: {avg:.1f}ms | Min: {mn:.1f}ms | Max: {mx:.1f}ms")
    print(f"    Toutes < 500ms: {'OUI' if mx < 500 else 'NON'}")
