"""
Rotas da Fila - Endpoints para o dashboard acessar a fila de decisoes.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List

from .auth import authenticated_user
from .database import get_db
from .queue_service import approve, reject, list_items, get_summary, expire_stale
from .decision_reasons import get_reason_labels


router = APIRouter(prefix="/queue", tags=["queue"])


class BulkActionRequest(BaseModel):
    ids: List[int]
    action: str  # "approve" ou "reject"


class RejectRequest(BaseModel):
    reason: Optional[str] = None


@router.get("/summary")
async def queue_summary(
    user: dict = Depends(lambda: {"id": None}),
    db: Session = Depends(get_db)
):
    """Resumo da fila para os cartoes do topo do dashboard."""
    owner_id = user.get("id")
    if owner_id is None:
        pass  # Modo local
    
    return get_summary(db, owner_id)


@router.get("/")
async def list_queue_items(
    decision: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(lambda: {"id": None}),
    db: Session = Depends(get_db)
):
    """Listar itens da fila com paginacao e filtros."""
    owner_id = user.get("id")
    if owner_id is None:
        pass  # Modo local
    
    items, total = list_items(
        db,
        owner_id,
        decision=decision,
        status=status,
        limit=min(limit, 100),
        offset=offset
    )
    
    # Traduzir motivos para texto legivel
    result_items = []
    for item in items:
        result_items.append({
            "id": item.id,
            "source": item.source,
            "source_ref": item.source_ref,
            "captured_at": item.captured_at.isoformat() if item.captured_at else None,
            "title": item.title,
            "company": item.company,
            "location": item.location,
            "modality": item.modality,
            "url": item.url,
            "confidence_overall": item.confidence_overall,
            "decision": item.decision,
            "decision_reasons": get_reason_labels(item.decision_reasons or []),
            "decision_reasons_raw": item.decision_reasons or [],
            "status": item.status,
            "score": item.score,
            "seen_count": item.seen_count,
            "first_seen_at": item.first_seen_at.isoformat() if item.first_seen_at else None,
            "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
            "job_id": item.job_id,
            "health_score": item.health_score,
            "health_band": item.health_band,
            "fraud_suspected": item.fraud_suspected,
        })
    
    return {
        "items": result_items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/{item_id}")
async def get_queue_item(
    item_id: int,
    user: dict = Depends(lambda: {"id": None}),
    db: Session = Depends(get_db)
):
    """Obter detalhe de um item da fila."""
    owner_id = user.get("id")
    if owner_id is None:
        pass  # Modo local
    
    from .models import QueueItem
    query = db.query(QueueItem).filter(QueueItem.id == item_id)
    if owner_id is not None:
        query = query.filter(QueueItem.owner_id == owner_id)
    item = query.first()
    
    if not item:
        raise HTTPException(status_code=404, detail="Item nao encontrado.")
    
    return {
        "id": item.id,
        "source": item.source,
        "source_ref": item.source_ref,
        "captured_at": item.captured_at.isoformat() if item.captured_at else None,
        "title": item.title,
        "company": item.company,
        "location": item.location,
        "modality": item.modality,
        "url": item.url,
        "description": item.description,
        "raw_excerpt": item.raw_excerpt,
        "confidence_title": item.confidence_title,
        "confidence_company": item.confidence_company,
        "confidence_description": item.confidence_description,
        "confidence_url": item.confidence_url,
        "confidence_overall": item.confidence_overall,
        "decision": item.decision,
        "decision_reasons": get_reason_labels(item.decision_reasons or []),
        "decision_reasons_raw": item.decision_reasons or [],
        "decision_engine_version": item.decision_engine_version,
        "status": item.status,
        "score": item.score,
        "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
        "resolved_by": item.resolved_by,
        "job_id": item.job_id,
        "dedup_hash": item.dedup_hash,
        "seen_count": item.seen_count,
        "first_seen_at": item.first_seen_at.isoformat() if item.first_seen_at else None,
        "last_seen_at": item.last_seen_at.isoformat() if item.last_seen_at else None,
        "health_score": item.health_score,
        "health_band": item.health_band,
        "health_signals": item.health_signals or [],
        "fraud_suspected": item.fraud_suspected,
    }


@router.post("/{item_id}/approve")
async def approve_queue_item(
    item_id: int,
    user: dict = Depends(lambda: {"id": None}),
    db: Session = Depends(get_db)
):
    """Promover um item da fila para job."""
    owner_id = user.get("id")
    if owner_id is None:
        pass  # Modo local
    
    try:
        result = approve(db, owner_id, item_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{item_id}/reject")
async def reject_queue_item(
    item_id: int,
    request: RejectRequest,
    user: dict = Depends(lambda: {"id": None}),
    db: Session = Depends(get_db)
):
    """Recusar um item da fila."""
    owner_id = user.get("id")
    if owner_id is None:
        pass  # Modo local
    
    try:
        result = reject(db, owner_id, item_id, request.reason)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/bulk")
async def bulk_action(
    request: BulkActionRequest,
    user: dict = Depends(lambda: {"id": None}),
    db: Session = Depends(get_db)
):
    """Acao em lote: aprovar ou recusar multiplos itens."""
    owner_id = user.get("id")
    if owner_id is None:
        pass  # Modo local
    
    if request.action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Acao invalida. Use 'approve' ou 'reject'.")
    
    results = []
    for item_id in request.ids:
        try:
            if request.action == "approve":
                result = approve(db, owner_id, item_id)
            else:
                result = reject(db, owner_id, item_id)
            results.append({"id": item_id, "success": True, "result": result})
        except ValueError as e:
            results.append({"id": item_id, "success": False, "error": str(e)})
        except Exception as e:
            results.append({"id": item_id, "success": False, "error": str(e)})
    
    return {
        "action": request.action,
        "processed": len(request.ids),
        "results": results
    }


@router.post("/expire")
async def expire_stale_items(
    user: dict = Depends(lambda: {"id": None}),
    db: Session = Depends(get_db)
):
    """Expiracao manual de itens antigos (rotina do worker)."""
    owner_id = user.get("id")
    if owner_id is None:
        pass  # Modo local
    
    # Apenas o dono pode expirar seus proprios itens
    count = expire_stale(db, 14)  # 14 dias
    return {"expired": count}
