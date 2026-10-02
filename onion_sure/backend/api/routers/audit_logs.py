"""
Audit Logging Router
Smart India Hackathon 2026 - Problem Statement PS26031

Endpoints:
- GET /audit-logs: Retrieve tamper-evident administrative audit trail with filtering and pagination (Admin only)
"""

from typing import Optional, List, Union
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ...database import get_db
from ...models.entities import AuditLog, User
from ...schemas.api_schemas import AuditLogResponse, PaginatedResponse
from ...security import RequireRoles

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


@router.get("", response_model=Union[PaginatedResponse[AuditLogResponse], List[AuditLogResponse]])
def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    page: Optional[int] = Query(None, ge=1),
    page_size: Optional[int] = Query(None, ge=1, le=100),
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    actor_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRoles("SUPER_ADMIN", "ADMIN", "CENTRE_ADMIN")),
):
    """
    Retrieves system audit trail with filtering and pagination (Admin only).
    Logs all critical events: user logins, registrations, inspection creation,
    grading evaluation, manual overrides, and report finalizations.
    """
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action.upper())
    if entity_type:
        query = query.filter(AuditLog.entity_type.ilike(entity_type))
    if actor_id:
        query = query.filter(AuditLog.actor_id == actor_id)

    total = query.count()

    if page is not None:
        p_size = page_size or 20
        offset = (page - 1) * p_size
        items = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(p_size).all()
        total_pages = (total + p_size - 1) // p_size if total > 0 else 1
        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=p_size,
            total_pages=total_pages,
        )

    return query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
