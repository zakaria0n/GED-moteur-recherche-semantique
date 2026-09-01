"""Script de benchmark pour le moteur de recherche semantique.

Mesure :
  - Temps d'indexation (OCR active/inactive)
  - Temps de recherche (latence moyenne, P95, P99)
  - Memoire utilisee

Usage :
    python tests/benchmark_search.py
    python tests/benchmark_search.py --queries "contrat" "salaire" "facture"
    python tests/benchmark_search.py --csv results.csv
"""

import argparse
import csv
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import PDFS_DIR
from services.search.embedder import load_embedding_model
from services.search.search_engine import build_search_engine, search_documents

# Requetes predefinies pour le benchmark (mix semantique + lexical).
DEFAULT_QUERIES = [
    "contrat de travail",
    "bulletin de salaire",
    "facture client",
    "compte rendu reunion",
    "decision administrative",
    "rapport annuel",
    "procedure interne",
    "organigramme entreprise",
    "note de service",
    "budget previsionnel",
]


def _get_memory_mb():
    """Memoire RSS du processus actuel en MB."""
    try:
        import psutil
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except ImportError:
        return 0.0


def benchmark_indexation(queries):
    """Mesure le temps d'indexation du moteur."""
    print("\n=== BENCHMARK INDEXATION ===")
    print(f"Documents: {PDFS_DIR}")

    mem_before = _get_memory_mb()
    t0 = time.perf_counter()

    engine = build_search_engine()

    t_index = time.perf_counter() - t0
    mem_after = _get_memory_mb()

    n_docs = sum(len(shard["documents"]) for shard in engine["shards"].values())
    n_chunks = len(engine["all_chunks"])
    n_cats = len(engine["shards"])

    print(f"  Documents indexes : {n_docs}")
    print(f"  Categories        : {n_cats}")
    print(f"  Passages (chunks) : {n_chunks}")
    print(f"  Temps indexation   : {t_index:.2f}s")
    print(f"  Memoire           : {mem_after:.0f} MB (+{mem_after - mem_before:.0f} MB)")

    return engine


def benchmark_recherche(engine, queries):
    """Mesure la latence de recherche sur un ensemble de requetes."""
    print("\n=== BENCHMARK RECHERCHE ===")
    print(f"  Requetes : {len(queries)}")

    # Phase de warm-up (premiere requete = plus lente a cause du cache).
    search_documents(queries[0], engine, top_k=5)

    latencies = []
    results_table = []

    for query in queries:
        t0 = time.perf_counter()
        results = search_documents(query, engine, top_k=5)
        latency = (time.perf_counter() - t0) * 1000  # ms

        latencies.append(latency)
        results_table.append({
            "query": query,
            "results": len(results),
            "latency_ms": round(latency, 2),
            "best_score": round(results[0]["score"], 4) if results else 0,
        })

        print(f"  [{latency:7.1f}ms] {query} -> {len(results)} resultat(s)")

    # Statistiques
    avg = statistics.mean(latencies)
    med = statistics.median(latencies)
    p95 = sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 2 else max(latencies)
    p99 = sorted(latencies)[int(len(latencies) * 0.99)] if len(latencies) >= 2 else max(latencies)
    total = sum(latencies)

    print(f"\n  Latence moyenne : {avg:.1f}ms")
    print(f"  Latence mediane : {med:.1f}ms")
    print(f"  P95             : {p95:.1f}ms")
    print(f"  P99             : {p99:.1f}ms")
    print(f"  Total           : {total:.1f}ms")

    return {
        "avg_ms": round(avg, 2),
        "median_ms": round(med, 2),
        "p95_ms": round(p95, 2),
        "p99_ms": round(p99, 2),
        "total_ms": round(total, 2),
        "queries": results_table,
    }


def benchmark_cache(engine, queries):
    """Mesure le hit rate du cache LRU (2eme appel = cache hit)."""
    print("\n=== BENCHMARK CACHE ===")

    from services.search.search_engine import _search_cache

    # Premiers appels (miss).
    for q in queries[:5]:
        search_documents(q, engine, top_k=5)

    stats_before = _search_cache.stats()
    print(f"  Avant 2e tour : {stats_before}")

    # Deuxieme tour (hits).
    for q in queries[:5]:
        search_documents(q, engine, top_k=5)

    stats_after = _search_cache.stats()
    print(f"  Apres 2e tour : {stats_after}")
    print(f"  Hit rate      : {stats_after['hit_rate_pct']}%")

    return {"before": stats_before, "after": stats_after}


def export_csv(benchmark_data, csv_path):
    """Exporte les resultats en CSV."""
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["metric", "value"])
        writer.writerow(["avg_latency_ms", benchmark_data["recherche"]["avg_ms"]])
        writer.writerow(["median_latency_ms", benchmark_data["recherche"]["median_ms"]])
        writer.writerow(["p95_latency_ms", benchmark_data["recherche"]["p95_ms"]])
        writer.writerow(["p99_latency_ms", benchmark_data["recherche"]["p99_ms"]])
        writer.writerow(["total_latency_ms", benchmark_data["recherche"]["total_ms"]])
        writer.writerow([])
        writer.writerow(["query", "results_count", "latency_ms", "best_score"])
        for q in benchmark_data["recherche"]["queries"]:
            writer.writerow([q["query"], q["results"], q["latency_ms"], q["best_score"]])

    print(f"\n  CSV exporte : {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Benchmark du moteur de recherche semantique")
    parser.add_argument("--queries", nargs="*", help="Requetes custom (defaut: 10 predefinies)")
    parser.add_argument("--csv", help="Chemin du fichier CSV de sortie")
    args = parser.parse_args()

    queries = args.queries or DEFAULT_QUERIES

    print("=" * 60)
    print("  BENCHMARK MOTEUR DE RECHERCHE SEMANTIQUE")
    print("=" * 60)

    engine = benchmark_indexation(queries)
    recherche = benchmark_recherche(engine, queries)
    cache = benchmark_cache(engine, queries)

    mem_final = _get_memory_mb()

    benchmark_data = {
        "recherche": recherche,
        "cache": cache,
        "memory_mb": round(mem_final, 1),
    }

    if args.csv:
        export_csv(benchmark_data, args.csv)

    print("\n" + "=" * 60)
    print("  RESUME")
    print("=" * 60)
    print(f"  Documents indexes : {sum(len(s['documents']) for s in engine['shards'].values())}")
    print(f"  Latence moyenne   : {recherche['avg_ms']}ms")
    print(f"  P95               : {recherche['p95_ms']}ms")
    print(f"  Cache hit rate    : {cache['after']['hit_rate_pct']}%")
    print(f"  Memoire finale    : {mem_final:.0f} MB")
    print("=" * 60)


if __name__ == "__main__":
    main()
