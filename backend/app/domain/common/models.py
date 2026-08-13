"""Shared user-scoped domain primitives."""

from uuid import UUID

from pydantic import BaseModel, Field

DEFAULT_SINGLE_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


class UserScopedModel(BaseModel):
    """Base model for records that must remain multi-user ready."""

    user_id: UUID = Field(
        default=DEFAULT_SINGLE_USER_ID,
        description="Owner of the record. A fixed user is used until multi-user support is enabled.",
    )
