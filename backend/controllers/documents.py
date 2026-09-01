"""Routes de recherche, consultation des documents et sante du backend."""

import csv
import io
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse

from shared import logger
from shared.metrics import record_search, record_search_error, snapshot as metrics_snapshot
from config import FAISS_INDEX_PATH, PDFS_DIR
from repositories.documents import count_documents, list_documents
from middleware.auth import get_current_user
from shared.serialization import serialize_user
from models.auth import SearchRequest
from services.search.embedder import load_embedding_model
from services.search.search_engine import _search_cache, _generate_suggestions, search_documents
from services.state import search_state
from services.sync_service import run_sync, start_background_startup_sync

router = APIRouter(tags=["documents"])


def _engine_documents_count():
    engine = search_state["engine"]
    if engine is None:
        return 0
    return sum(len(shard["documents"]) for shard in engine["shards"].values())


def _engine_categories():
    engine = search_state["engine"]
    if engine is None:
        return []
    return sorted(engine["shards"].keys())


@router.get("/")
def read_root():
    return {
        "message": "Backend FastAPI du moteur de recherche semantique",
        "documents_folder": str(PDFS_DIR),
        "index_path": str(FAISS_INDEX_PATH),
        "documents_in_memory": _engine_documents_count(),
        "categories": _engine_categories(),
        "database_error": search_state["database_error"],
    }


@router.get("/health")
def health():
    return {
        "api": "ok",
        "database_error": search_state["database_error"],
        "index_loaded": search_state["engine"] is not None,
        "sync_running": search_state["sync_running"],
        "last_sync_message": search_state["last_sync_message"],
        "documents_indexed": _engine_documents_count(),
        "categories_count": len(_engine_categories()),
    }


@router.get("/metrics")
def metrics(current_user=Depends(get_current_user)):
    """Metriques de performance du moteur (latence, erreurs, documents)."""
    return metrics_snapshot()


@router.post("/sync")
def sync(current_user=Depends(get_current_user)):
    """Force la synchronisation (detecte et applique les changements).

    Mise a jour incrementale si l'index est deja charge (seuls les fichiers
    ajoutes/modifies sont re-indexes). Reconstruction complete sinon.
    """

    if search_state["sync_running"]:
        raise HTTPException(status_code=409, detail="Synchronisation deja en cours")

    search_state["sync_running"] = True
    search_state["last_sync_message"] = "Synchronisation manuelle demandee"

    try:
        model = load_embedding_model()
        _search_cache.clear()  # Invalider le cache apres re-indexation.
        result = run_sync(model=model)
    except Exception as exc:
        search_state["last_sync_message"] = f"Erreur de synchronisation: {exc}"
        logger.error("sync", f"Echec de la synchronisation manuelle: {exc}", user=current_user)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        search_state["sync_running"] = False

    return result


@router.get("/dashboard/summary")
def dashboard_summary(current_user=Depends(get_current_user)):

    return {
        "user": serialize_user(current_user),
        "documents_count": count_documents(),
        "index_loaded": search_state["engine"] is not None,
        "documents_in_memory": _engine_documents_count(),
        "categories": _engine_categories(),
    }


@router.post("/search")
def search(request: SearchRequest, current_user=Depends(get_current_user)):

    if request.top_k < 1 or request.top_k > 50:
        raise HTTPException(status_code=400, detail="top_k doit etre compris entre 1 et 50")

    engine = search_state["engine"]

    if engine is None:
        if not search_state["sync_running"]:
            logger.warning("recherche", "Index pas encore pret. Relance de l'indexation initiale...", user=current_user)
            start_background_startup_sync()

        raise HTTPException(
            status_code=503,
            detail="Indexation initiale en cours. Reessayez dans quelques instants.",
        )

    start = time.perf_counter()

    try:
        results = search_documents(
            request.query,
            engine,
            top_k=request.top_k,
            category=request.category,
            file_type=request.file_type,
        )
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        record_search_error(latency_ms)
        logger.error("recherche", f'Erreur pendant la recherche de "{request.query}": {exc}', user=current_user)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    latency_ms = (time.perf_counter() - start) * 1000
    record_search(latency_ms, len(results))

    logger.info(
        "recherche",
        f'Recherche de "{request.query}" - {len(results)} resultat(s) - {latency_ms:.1f}ms',
        user=current_user,
    )

    # Si 0 resultat, generer des suggestions par termes individuels.
    suggestions = []
    if not results:
        try:
            suggestions = _generate_suggestions(request.query, engine)
        except Exception:
            pass

    return {
        "query": request.query,
        "results_count": len(results),
        "results": results,
        "suggestions": suggestions,
    }


@router.get("/search/cache-stats")
def search_cache_stats(current_user=Depends(get_current_user)):
    """Statistiques du cache LRU des recherches."""
    return _search_cache.stats()


@router.post("/search/export")
def export_search_csv(request: SearchRequest, current_user=Depends(get_current_user)):
    """Exporte les resultats de recherche en CSV telechargeable."""
    engine = search_state["engine"]

    if engine is None:
        raise HTTPException(status_code=503, detail="Index pas encore pret")

    try:
        results = search_documents(
            request.query,
            engine,
            top_k=request.top_k,
            category=request.category,
            file_type=request.file_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["file_name", "category", "file_type", "score", "aggregated", "relevance_pct", "text_preview"])

    for r in results:
        category = r["relative_path"].replace("\\", "/").split("/")[0] if "/" in r["relative_path"].replace("\\", "/") else "_root"
        writer.writerow([
            r["file_name"],
            category,
            r["file_type"],
            round(r["score"], 4),
            round(r["aggregated"], 6),
            r.get("relevance"),
            r["text_preview"],
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="recherche_{request.query[:30]}.csv"'},
    )


@router.get("/documents")
def get_documents(
    current_user=Depends(get_current_user),
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    try:
        documents = list_documents(limit=limit, offset=offset)
        total = count_documents()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "count": len(documents),
        "total_count": total,
        "documents": documents,
    }


@router.get("/files/{file_path:path}")
def get_document_file(file_path: str, current_user=Depends(get_current_user)):
    full_path = (PDFS_DIR / file_path).resolve()
    pdfs_root = PDFS_DIR.resolve()

    # Protection path traversal : le chemin resolu doit rester sous PDFS_DIR.
    if pdfs_root not in full_path.parents and full_path != pdfs_root:
        logger.warning("fichiers", f"Chemin de fichier refuse: {file_path}", user=current_user)
        raise HTTPException(status_code=400, detail="Chemin de fichier invalide")

    if not full_path.is_file():
        logger.warning("fichiers", f"Fichier introuvable: {file_path}", user=current_user)
        raise HTTPException(status_code=404, detail="Fichier introuvable")

    logger.info("fichiers", f"Ouverture du document {file_path}", user=current_user)

    return FileResponse(full_path)
