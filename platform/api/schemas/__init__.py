"""Pydantic request schemas for the Axalon Platform API (Plan 02).

Schemas are intentionally permissive (optional fields, no Literal/ge constraints)
so the routers' existing domain validation continues to own business-rule errors
(400s). Pydantic adds type coercion + OpenAPI request-body documentation; routers
consume them via `model_dump(exclude_unset=True)`, preserving exact behavior.
"""
from axalon.api.schemas.inventory import (
    ComponentBody, PrototypeBody, AssignmentBody, OrderBody,
)
from axalon.api.schemas.projects import ProjectBody
from axalon.api.schemas.track import LoginRequest, PasswordSetRequest, NoteBody
from axalon.api.schemas.faults import FaultUpdate, CommentCreate
from axalon.api.schemas.missions import MissionCreate
from axalon.api.schemas.corrections import CorrectionCreate
from axalon.api.schemas.park import ParkUpdate
from axalon.api.schemas.settings import SettingsUpdate
from axalon.api.schemas.auth import ShareLinkCreate, UserCreate, UserLogin, UserUpdate

__all__ = [
    "ComponentBody", "PrototypeBody", "AssignmentBody", "OrderBody",
    "ProjectBody", "LoginRequest", "PasswordSetRequest", "NoteBody",
    "FaultUpdate", "CommentCreate", "MissionCreate", "CorrectionCreate",
    "ParkUpdate", "SettingsUpdate",
    "ShareLinkCreate", "UserCreate", "UserLogin", "UserUpdate",
]
