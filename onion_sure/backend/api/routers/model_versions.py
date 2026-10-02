"""
Model Versioning Router
Smart India Hackathon 2026 - Problem Statement PS26031

Endpoints:
- GET  /model-versions: List tracked AI models and metrics
- POST /model-versions: Register new model version
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...models.entities import ModelVersion, User
from ...schemas.api_schemas import ModelVersionCreate, ModelVersionResponse
from ...security import RequireRoles
from ...services.audit_service import AuditService

router = APIRouter(prefix="/model-versions", tags=["Model Versions"])


@router.get("", response_model=List[ModelVersionResponse])
def list_model_versions(db: Session = Depends(get_db)):
    """Lists registered AI model versions and their evaluation metrics."""
    return db.query(ModelVersion).order_by(ModelVersion.created_at.desc()).all()


@router.post("", response_model=ModelVersionResponse, status_code=status.HTTP_201_CREATED)
def register_model_version(
    model_in: ModelVersionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRoles("SUPER_ADMIN", "ADMIN", "CENTRE_ADMIN")),
):
    """Registers a new trained AI model version for inference traceability (Admin only)."""
    existing = db.query(ModelVersion).filter(ModelVersion.version == model_in.version).first()
    if existing:
        raise HTTPException(status_code=400, detail="Model version identifier already exists.")

    m_ver = ModelVersion(
        model_name=model_in.model_name,
        version=model_in.version,
        model_type=model_in.model_type,
        artifact_reference=model_in.artifact_reference,
        dataset_version=model_in.dataset_version,
        metrics_summary=model_in.metrics_summary,
        status=model_in.status,
    )
    db.add(m_ver)
    db.flush()

    AuditService.log_event(
        db=db,
        actor_id=current_user.id,
        action="MODEL_VERSION_REGISTERED",
        entity_type="ModelVersion",
        entity_id=m_ver.id,
        new_values={"model_name": m_ver.model_name, "version": m_ver.version},
    )

    db.commit()
    db.refresh(m_ver)
    return m_ver
