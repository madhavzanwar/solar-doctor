"""users router — admin-only account management (users mode).

Mounted with an admin access policy in app.py; nothing here re-checks roles.
"""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas import UserCreate, UserUpdate
from axalon.api.serializers import _serialize_user
from axalon.core.auth import (
    AuthValidationError, count_active_admins, create_user, hash_user_password,
    project_ids_for, revoke_user_sessions, set_user_projects, validate_password, validate_role,
)
from axalon.db.models import ROLE_ADMIN, ProjectMember, ShareLink, User, UserSession

router = APIRouter(tags=["users"])

_LAST_ADMIN = "At least one active admin must remain"


def _get_user(session, user_id: int) -> User:
    user = session.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _is_last_active_admin(session, user: User) -> bool:
    return (
        user.role == ROLE_ADMIN
        and not user.disabled
        and count_active_admins(session, exclude_user_id=user.id) == 0
    )


@router.get("/users")
def list_users():
    session = get_session()
    try:
        users = session.query(User).order_by(User.email.asc()).all()
        return [_serialize_user(u, project_ids_for(session, u.id)) for u in users]
    finally:
        session.close()


@router.post("/users", status_code=201)
def create_user_account(payload: UserCreate):
    data = payload.model_dump(exclude_unset=True)
    session = get_session()
    try:
        try:
            user = create_user(
                session,
                email=data.get("email"),
                password=data.get("password"),
                role=data.get("role"),
                project_ids=data.get("project_ids") or (),
            )
        except AuthValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except LookupError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return JSONResponse(
            content=_serialize_user(user, project_ids_for(session, user.id)), status_code=201,
        )
    finally:
        session.close()


@router.patch("/users/{user_id}")
def update_user_account(user_id: int, payload: UserUpdate):
    """Change role, enable/disable, reset password, or replace project access."""
    data = payload.model_dump(exclude_unset=True)
    session = get_session()
    try:
        user = _get_user(session, user_id)
        try:
            new_role = validate_role(data["role"]) if "role" in data else user.role
            new_disabled = bool(data["disabled"]) if data.get("disabled") is not None else bool(user.disabled)
            new_password = validate_password(data["password"]) if "password" in data else None
        except AuthValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        demoting = new_role != ROLE_ADMIN or new_disabled
        if demoting and _is_last_active_admin(session, user):
            raise HTTPException(status_code=400, detail=_LAST_ADMIN)

        user.role = new_role
        # Credentials or access withdrawn → every existing session dies with them.
        if (new_disabled and not user.disabled) or new_password is not None:
            revoke_user_sessions(session, user.id)
        user.disabled = new_disabled
        if new_password is not None:
            user.password_hash = hash_user_password(new_password)
        if "project_ids" in data:
            try:
                set_user_projects(session, user.id, data.get("project_ids") or ())
            except AuthValidationError as exc:
                session.rollback()
                raise HTTPException(status_code=400, detail=str(exc))
        session.commit()
        return _serialize_user(user, project_ids_for(session, user.id))
    finally:
        session.close()


@router.delete("/users/{user_id}", status_code=204)
def delete_user_account(user_id: int):
    session = get_session()
    try:
        user = _get_user(session, user_id)
        if _is_last_active_admin(session, user):
            raise HTTPException(status_code=400, detail=_LAST_ADMIN)
        # Explicit cleanup rather than relying on ON DELETE, which SQLite only
        # honours when foreign_keys is enabled on that connection.
        session.query(UserSession).filter(UserSession.user_id == user.id).delete(synchronize_session=False)
        session.query(ProjectMember).filter(ProjectMember.user_id == user.id).delete(synchronize_session=False)
        session.query(ShareLink).filter(ShareLink.created_by == user.id).update(
            {ShareLink.created_by: None}, synchronize_session=False,
        )
        session.delete(user)
        session.commit()
        return Response(status_code=204)
    finally:
        session.close()
