"""
User Management Router
Smart India Hackathon 2026 - Problem Statement PS26031

Endpoints:
- GET  /users     : List users with pagination and search (Admin only)
- GET  /users/{id}: Retrieve user details
- POST /users/{id}/roles : Assign roles to user (Admin only)
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ...database import get_db
from ...models.entities import User, Role, UserRole
from ...schemas.api_schemas import UserResponse, PaginatedResponse, MessageResponse
from ...security import get_current_user, RequireRoles
from ...services.audit_service import AuditService

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=PaginatedResponse[UserResponse])
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRoles("SUPER_ADMIN", "ADMIN", "CENTRE_ADMIN")),
):
    """Lists users with pagination and search filter (admin-level access only)."""
    query = db.query(User)
    if search:
        query = query.filter(
            (User.full_name.ilike(f"%{search}%")) | (User.email.ilike(f"%{search}%"))
        )

    total = query.count()
    offset = (page - 1) * page_size
    items = query.order_by(User.created_at.desc()).offset(offset).limit(page_size).all()
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/me", response_model=UserResponse)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    """Returns the currently authenticated user profile."""
    return current_user


@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieves specific user profile."""
    # Allow self or admin
    if current_user.id != user_id and not any(
        r.name.upper() in {"ADMIN", "SUPER_ADMIN", "CENTRE_ADMIN"} for r in current_user.roles
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: cannot view profile of another user",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("/{user_id}/roles", response_model=UserResponse)
def assign_role(
    user_id: str,
    role_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(RequireRoles("SUPER_ADMIN", "ADMIN", "CENTRE_ADMIN")),
):
    """Assigns an RBAC role to a user (admin-level access only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role = db.query(Role).filter(Role.name == role_name.upper()).first()
    if not role:
        role = Role(name=role_name.upper(), description=f"Role {role_name.upper()}")
        db.add(role)
        db.flush()

    existing_mapping = db.query(UserRole).filter_by(user_id=user.id, role_id=role.id).first()
    if not existing_mapping:
        ur = UserRole(user_id=user.id, role_id=role.id)
        db.add(ur)
        AuditService.log_event(
            db=db,
            actor_id=current_user.id,
            action="ROLE_ASSIGNED",
            entity_type="User",
            entity_id=user.id,
            new_values={"role": role.name},
        )
        db.commit()
        db.refresh(user)

    return user
