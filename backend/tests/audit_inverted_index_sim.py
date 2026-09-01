"""Prototype index inverse BM25 (postings numpy) vs implementation actuelle.

Compare a 100 000 documents (300 000 passages) :
  - memoire
  - temps de get_scores par requete
"""

import sys
import time
import random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import psutil

from services.search.bm25 import BM25, tokenize

random.seed(42)

WORDS = [
    "contrat", "travail", "salaire", "facture", "client", "entreprise", "assurance",
    "banque", "virement", "attestation", "domicile", "conge", "demission", "medical",
    "document", "administration", "prefecture", "dossier", "demande", "copie",
    "inscription", "universite", "etudiant", "diplome", "releve", "notes", "examen",
    "habitation", "sinistre", "declaration", "constat", "amiable", "immobilier",
    "pret", "interet", "mensualite", "emprunt", "caution", "garantie", "fournisseur",
]
# Vocabulaire plus large et plus realiste (Zipf) : 5000 mots, frequence ~1/rang.
rng_vocab = random.Random(7)
VOCAB = WORDS + [f"mot{i:04d}" for i in range(5000)]

N_DOCS = 100_000
CHUNKS_PER_DOC = 3
N = N_DOCS * CHUNKS_PER_DOC

print(f"Corpus : {N_DOCS:,} docs -> {N:,} passages")


def make_tokens(rng):
    n = rng.randint(120, 170)
    # Zipf approx : les mots courants dominent.
    return [rng.choice(VOCAB[:200]) if rng.random() < 0.7 else rng.choice(VOCAB) for _ in range(n)]


rng = random.Random(1234)
mem0 = psutil.Process().memory_info().rss / 1024**2

t0 = time.perf_counter()
corpus_tokens = [make_tokens(rng) for _ in range(N)]
t_tok = time.perf_counter() - t0
print(f"Tokenization : {t_tok:.1f} s")

# --- Implementation actuelle ---
t0 = time.perf_counter()
old = BM25(corpus_tokens)
t_old = time.perf_counter() - t0
mem1 = psutil.Process().memory_info().rss / 1024**2
print(f"[ACTUEL ] build: {t_old:6.1f}s   memoire: {mem1-mem0:7.0f} Mo")

q = tokenize("demande attestation dossier")
times = []
for _ in range(3):
    t0 = time.perf_counter()
    old.get_scores(q)
    times.append((time.perf_counter() - t0) * 1000)
print(f"[ACTUEL ] get_scores: {min(times):6.0f} ms/requete")

del old

# --- Index inverse propose ---
t0 = time.perf_counter()
vocab_index = {}
lengths = np.array([len(toks) for toks in corpus_tokens], dtype=np.float32)
avgdl = float(lengths.mean())
doc_count = N
# df + postings
postings_tf = {}  # term -> (list doc_idx, list tf)
for i, toks in enumerate(corpus_tokens):
    freqs = {}
    for tok in toks:
        freqs[tok] = freqs.get(tok, 0) + 1
    for tok, tf in freqs.items():
        entry = postings_tf.setdefault(tok, ([], []))
        entry[0].append(i)
        entry[1].append(tf)

vocab = sorted(postings_tf.keys())
term_to_id = {t: j for j, t in enumerate(vocab)}
df = np.array([len(postings_tf[t][0]) for t in vocab], dtype=np.float32)
idf = np.log(1 + (doc_count - df + 0.5) / (df + 0.5))
inv_doc_ids = [np.array(postings_tf[t][0], dtype=np.int32) for t in vocab]
inv_tfs = [np.array(postings_tf[t][1], dtype=np.float32) for t in vocab]
t_new = time.perf_counter() - t0
mem2 = psutil.Process().memory_info().rss / 1024**2
print(f"[INVERSE] build: {t_new:6.1f}s   memoire: {mem2-mem1:7.0f} Mo")


def get_scores_inverted(query_tokens, k1=1.5, b=0.75):
    scores = np.zeros(doc_count, dtype=np.float32)
    for tok in set(query_tokens):
        j = term_to_id.get(tok)
        if j is None:
            continue
        doc_ids = inv_doc_ids[j]
        tfs = inv_tfs[j]
        dls = lengths[doc_ids]
        denom = tfs + k1 * (1 - b + b * dls / avgdl)
        np.add.at(scores, doc_ids, idf[j] * (tfs * (k1 + 1)) / denom)
    return scores


times = []
for _ in range(5):
    t0 = time.perf_counter()
    s = get_scores_inverted(q)
    times.append((time.perf_counter() - t0) * 1000)
print(f"[INVERSE] get_scores: {min(times):6.2f} ms/requete")

# Top-k sans tri complet
t0 = time.perf_counter()
top = np.argpartition(s, -40)[-40:]
print(f"[INVERSE] top-40 sans tri complet: {(time.perf_counter()-t0)*1000:.2f} ms")
