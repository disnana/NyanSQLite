from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, TypeAdapter


def needs_row_validation(model: type[BaseModel]) -> bool:
    """Use full models when validation can depend on other fields or config."""
    decorators = getattr(model, "__pydantic_decorators__", None)
    if decorators is None or model.model_config:
        return True
    if model.__init__ is not BaseModel.__init__ or model.model_post_init is not BaseModel.model_post_init:
        return True
    if any(
        "__get_pydantic_core_schema__" in cls.__dict__
        for cls in model.__mro__ if cls not in (BaseModel, object)
    ):
        return True
    return any(
        getattr(decorators, name, None)
        for name in ("validators", "field_validators", "root_validators", "model_validators")
    )


@lru_cache(maxsize=256)
def _adapter(model: type[BaseModel], field_name: str) -> TypeAdapter:
    return TypeAdapter(model.model_fields[field_name].rebuild_annotation())


def prepare_update(
    model: type[BaseModel], fields: dict[str, Any], needs_rows: bool
) -> tuple[dict[str, Any], bool]:
    """Validate ordinary fields quickly; flag models needing row validation."""
    if needs_rows or any(name not in model.model_fields for name in fields):
        return fields, True
    return {name: _adapter(model, name).validate_python(value) for name, value in fields.items()}, False
