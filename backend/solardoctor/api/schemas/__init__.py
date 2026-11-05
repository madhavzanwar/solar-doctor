"""Pydantic request schemas for the Axalon Platform API (Plan 02).

Schemas are intentionally permissive (optional fields, no Literal/ge constraints)
so the routers' existing domain validation continues to own business-rule errors
(400s). Pydantic adds type coercion + OpenAPI request-body documentation; routers
consume them via `model_dump(exclude_unset=True)`, preserving exact behavior.
"""
from solardoctor.api.schemas.inventory import (
    ComponentBody, PrototypeBody, AssignmentBody, OrderBody,
)
from solardoctor.api.schemas.projects import ProjectBody
from solardoctor.api.schemas.track import LoginRequest, PasswordSetRequest, NoteBody
from solardoctor.api.schemas.faults import FaultUpdate, CommentCreate
from solardoctor.api.schemas.missions import MissionCreate
from solardoctor.api.schemas.corrections import CorrectionCreate
from solardoctor.api.schemas.park import ParkUpdate
from solardoctor.api.schemas.settings import SettingsUpdate
from solardoctor.api.schemas.auth import (
    LogoutRequest, RefreshRequest, ShareLinkCreate, UserCreate, UserLogin, UserRegister, UserUpdate,
)

__all__ = [
    "ComponentBody", "PrototypeBody", "AssignmentBody", "OrderBody",
    "ProjectBody", "LoginRequest", "PasswordSetRequest", "NoteBody",
    "FaultUpdate", "CommentCreate", "MissionCreate", "CorrectionCreate",
    "ParkUpdate", "SettingsUpdate",
    "ShareLinkCreate", "UserCreate", "UserLogin", "UserUpdate",
    "LogoutRequest", "RefreshRequest", "UserRegister",
]
