"""Collecte de metriques minimales, sans dependance externe.

Compteurs et echantillons en memoire (perdus au redemarrage). Thread-safe
car alimente depuis les requetes HTTP et le thread de synchronisation.

But : donner une visibilite immediate sur la sante du moteur (latence de
recherche, taux d'erreur, derniere sync) sans deploiement d'infra externe.
Pour une prod a grande echelle, exposer snapshot() a Prometheus/StatsD.
"""

import threading
import time
from collections import deque


_lock = threading.Lock()
_start_time = time.time()

# Echantillons recents bornea pour limiter la memoire.
_SEARCH_LATENCY_SAMPLES = deque(maxlen=200)
_SYNC_LATENCY_SAMPLES = deque(maxlen=50)

_state = {
    "search_total": 0,
    "search_errors": 0,
    "search_no_result": 0,
    "sync_total": 0,
    "sync_errors": 0,
    "last_sync": None,
    "documents_indexed": 0,
    "index_loaded_at": None,
}


def record_search(latency_ms, result_count):
    with _lock:
        _state["search_total"] += 1
        _SEARCH_LATENCY_SAMPLES.append(latency_ms)
        if result_count == 0:
            _state["search_no_result"] += 1


def record_search_error(latency_ms=0.0):
    with _lock:
        _state["search_total"] += 1
        _state["search_errors"] += 1
        _SEARCH_LATENCY_SAMPLES.append(latency_ms)


def record_sync(mode, documents_indexed, duration_ms, error=None):
    with _lock:
        _state["sync_total"] += 1

        if error:
            _state["sync_errors"] += 1

        _SYNC_LATENCY_SAMPLES.append(duration_ms)
        _state["last_sync"] = {
            "mode": mode,
            "documents_indexed": documents_indexed,
            "duration_ms": duration_ms,
            "error": error,
            "at": time.time(),
        }

        if not error:
            _state["documents_indexed"] = documents_indexed

        if _state["index_loaded_at"] is None:
            _state["index_loaded_at"] = time.time()


def set_documents_indexed(count):
    with _lock:
        _state["documents_indexed"] = count


def _percentile(sorted_samples, percentile):
    if not sorted_samples:
        return 0.0

    index = max(0, min(len(sorted_samples) - 1, int(round((percentile / 100) * (len(sorted_samples) - 1)))))
    return sorted_samples[index]


def snapshot():
    """Renvoie un dict de metriques lisible par un endpoint /metrics."""

    with _lock:
        samples = sorted(_SEARCH_LATENCY_SAMPLES)
        count = len(samples)
        average = sum(samples) / count if count else 0.0

        sync_samples = list(_SYNC_LATENCY_SAMPLES)
        sync_average = sum(sync_samples) / len(sync_samples) if sync_samples else 0.0

        return {
            "uptime_seconds": int(time.time() - _start_time),
            "search": {
                "total": _state["search_total"],
                "errors": _state["search_errors"],
                "no_result": _state["search_no_result"],
                "error_rate": (_state["search_errors"] / _state["search_total"]) if _state["search_total"] else 0.0,
                "avg_latency_ms": round(average, 2),
                "p95_latency_ms": round(_percentile(samples, 95), 2),
                "p99_latency_ms": round(_percentile(samples, 99), 2),
                "samples": count,
            },
            "sync": {
                "total": _state["sync_total"],
                "errors": _state["sync_errors"],
                "avg_duration_ms": round(sync_average, 2),
                "last": _state["last_sync"],
            },
            "index": {
                "documents_indexed": _state["documents_indexed"],
                "loaded": _state["index_loaded_at"] is not None,
            },
        }
