"""Simulation d'echelle pour l'audit : comportement du moteur actuel a 10k/50k/100k docs.

Mesure, sur un corpus synthetique realiste (passages ~900 chars, vocabulaire francais) :
  1. BM25.get_scores()            -> O(N) par token de requete (pas d'index inverse)
  2. Boucle "fused" + injection    -> scans complets avec .lower() sur tout le corpus
  3. Tri complet des scores BM25   -> O(N log N)
  4. Memoire RSS du BM25 (tf/docs en dicts/listes Python)

Usage : python tests/audit_scale_sim.py
"""

import sys
import time
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psutil

from services.search.bm25 import BM25, tokenize

random.seed(42)

# Vocabulaire synthetique style documents GED (mots de 3-12 chars).
WORDS = [
    "contrat", "travail", "salaire", "facture", "client", "entreprise", "assurance",
    "banque", "virement", "attestation", "domicile", "conge", "demission", "medical",
    "document", "administration", "prefecture", "dossier", "demande", "copie",
    "inscription", "universite", "etudiant", "diplome", "releve", "notes", "examen",
    "assurance", "habitation", "sinistre", "declaration", "constat", "amiable",
    "immobilier", "pret", "interet", "mensualite", "emprunt", "caution", "garantie",
    "fournisseur", "commande", "livraison", "paiement", "facturation", "comptabilite",
    "bilan", "exercice", "fiscal", "tva", "impot", "declaration", "revenus",
]
NUM_WORDS = len(WORDS)


def make_text(rng, length=900):
    parts = []
    total = 0
    while total < length:
        w = rng.choice(WORDS)
        parts.append(w)
        total += len(w) + 1
    return " ".join(parts)


CHUNKS_PER_DOC = 3  # ordre de grandeur du vrai corpus (~900 chars/chunk)

for n_docs in (10_000, 50_000):
    n_chunks = n_docs * CHUNKS_PER_DOC
    rng = random.Random(1234)
    print(f"\n{'='*64}\nCorpus synthetique : {n_docs:,} documents -> {n_chunks:,} passages\n{'='*64}")

    mem0 = psutil.Process().memory_info().rss / 1024**2

    t0 = time.perf_counter()
    corpus_tokens = [tokenize(make_text(rng)) for _ in range(n_chunks)]
    t_tokenize = time.perf_counter() - t0

    t0 = time.perf_counter()
    bm25 = BM25(corpus_tokens)
    t_build = time.perf_counter() - t0

    mem1 = psutil.Process().memory_info().rss / 1024**2
    print(f"  Construction BM25          : {t_build:6.1f} s   (tokenization: {t_tokenize:.1f} s)")
    print(f"  Memoire BM25 (tf+docs+idf) : {mem1 - mem0:6.0f} Mo")

    query_tokens = tokenize("demande attestation domicile")

    # --- 1. get_scores (mesure sur 1 token et sur la requete complete) ---
    times = []
    for _ in range(3):
        t0 = time.perf_counter()
        scores = bm25.get_scores(query_tokens)
        times.append((time.perf_counter() - t0) * 1000)
    print(f"  BM25.get_scores (3 tokens) : {min(times):6.0f} ms / requete")

    # --- 2. Tri complet O(N log N) comme dans search_documents ---
    t0 = time.perf_counter()
    order = sorted(range(n_chunks), key=lambda i: scores[i], reverse=True)[:200]
    print(f"  sorted(range(N)) complet   : {(time.perf_counter()-t0)*1000:6.0f} ms")

    # --- 3. Boucles 'fused' + 'injection' + 'document_has_exact' (3 scans, .lower() inclus) ---
    texts = [make_text(rng, 900) for _ in range(n_chunks)]
    query_lower = "demande attestation domicile"
    query_terms = ["demande", "attestation", "domicile"]

    t0 = time.perf_counter()
    fused = {}
    for i in range(n_chunks):
        chunk_lower = texts[i].lower()  # c'est exactement ce que fait search_documents
        if query_lower in chunk_lower or all(t in chunk_lower for t in query_terms):
            fused[i] = 0.001
    t_scan1 = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    for i in range(n_chunks):
        if i in fused:
            continue
        chunk_lower = texts[i].lower()
        if query_lower in chunk_lower or all(t in chunk_lower for t in query_terms):
            fused[i] = 0.001
    t_scan2 = (time.perf_counter() - t0) * 1000

    print(f"  Scan fused  (1 passe)      : {t_scan1:6.0f} ms")
    print(f"  Scan injection (2e passe)  : {t_scan2:6.0f} ms")
    print(f"  >>> Cout CPU des scans seuls par requete : {t_scan1 + t_scan2:.0f} ms")

    del bm25, corpus_tokens, texts, scores, order, fused
