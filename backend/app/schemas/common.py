"""Shared Pydantic configuration for REST JSON (camelCase responses)."""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """Request/response base with camelCase JSON aliases."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
    )


class OrmResponseModel(ApiModel):
    """Response models built from SQLAlchemy ORM instances."""

    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        from_attributes=True,
    )
