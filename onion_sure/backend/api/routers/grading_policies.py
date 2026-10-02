"""
Grading Policy and Policy Versioning Router
Smart India Hackathon 2026 - Problem Statement PS26031

Endpoints:
- GET  /grading-policies                : List policies
- POST /grading-policies                : Register new policy
- GET  /grading-policies/{code}/versions: List versions for policy
- POST /grading-policies/{code}/versions: Register versioned rules
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from ...database import get_db
from ...models.entities import GradingPolicy, GradingPolicyVersion, User
from ...schemas.api_schemas import (
    GradingPolicyCreate,
    GradingPolicyResponse,
    GradingPolicyVersionCreate,
    GradingPolicyVersionResponse,
)
from ...security import get_current_user, RequireRoles
from ...services.audit_service import AuditService

router = APIRouter(prefix="/grading-policies", tags=["Grading Policies"])


@router.get("", response_model=List[GradingPolicyResponse])
def list_grading_policies(db: Session = Depends(get_db)):
    """Lists registered grading policies."""
    return db.query(GradingPolicy).all()


@router.post("", response_model=GradingPolicyResponse, status_code=status.HTTP_201_CREATED)
def create_grading_policy(
    policy_in: GradingPolicyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRoles("SUPER_ADMIN", "ADMIN", "CENTRE_ADMIN")),
):
    """Registers a new root grading policy (Admin only)."""
    existing = db.query(GradingPolicy).filter(GradingPolicy.code == policy_in.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Policy code already exists.")

    policy = GradingPolicy(
        code=policy_in.code,
        name=policy_in.name,
        crop=policy_in.crop,
        is_active=policy_in.is_active,
    )
    db.add(policy)
    db.flush()

    AuditService.log_event(
        db=db,
        actor_id=current_user.id,
        action="POLICY_CREATED",
        entity_type="GradingPolicy",
        entity_id=policy.id,
        new_values={"code": policy.code, "name": policy.name},
    )
    db.commit()
    db.refresh(policy)
    return policy


@router.get("/{policy_code}/versions", response_model=List[GradingPolicyVersionResponse])
def list_policy_versions(policy_code: str, db: Session = Depends(get_db)):
    """Lists immutable versions for a grading policy."""
    policy = db.query(GradingPolicy).filter(GradingPolicy.code == policy_code).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Grading policy not found.")
    return db.query(GradingPolicyVersion).filter(GradingPolicyVersion.policy_id == policy.id).all()


@router.post("/{policy_code}/versions", response_model=GradingPolicyVersionResponse, status_code=status.HTTP_201_CREATED)
def create_policy_version(
    policy_code: str,
    version_in: GradingPolicyVersionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRoles("SUPER_ADMIN", "ADMIN", "CENTRE_ADMIN")),
):
    """Registers an immutable policy version configuration (Admin only)."""
    policy = db.query(GradingPolicy).filter(GradingPolicy.code == policy_code).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Grading policy not found.")

    existing_ver = (
        db.query(GradingPolicyVersion)
        .filter_by(policy_id=policy.id, version=version_in.version)
        .first()
    )
    if existing_ver:
        raise HTTPException(status_code=400, detail="Policy version already exists.")

    p_version = GradingPolicyVersion(
        policy_id=policy.id,
        version=version_in.version,
        configuration=version_in.configuration,
        effective_from=version_in.effective_from or datetime.now(timezone.utc),
        created_by=current_user.id,
    )
    db.add(p_version)
    db.flush()

    AuditService.log_event(
        db=db,
        actor_id=current_user.id,
        action="POLICY_VERSION_CREATED",
        entity_type="GradingPolicyVersion",
        entity_id=p_version.id,
        new_values={"policy_code": policy_code, "version": p_version.version},
    )
    db.commit()
    db.refresh(p_version)
    return p_version
