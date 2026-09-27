"""Select the Pydantic row validator for ordinary models."""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_core import SchemaValidator


def direct_row_validator(model: type[BaseModel]) -> SchemaValidator | None:
    """Use Pydantic Core when it has the same construction semantics as ``model(**data)``.

    The model constructor supplies ``self_instance`` to the same validator.
    A model validator can return a different instance in the direct path, so
    models with custom construction or model validators use their constructor.
    """
    if model.__mro__[1] is not BaseModel or model.__init__ is not BaseModel.__init__:
        return None
    if model.__pydantic_post_init__ is not None or model.__pydantic_decorators__.model_validators:
        return None
    if any(field.default_factory is not None for field in model.model_fields.values()):
        return None
    if any(name in model.__dict__ for name in ("__new__", "__getattribute__", "__get_pydantic_core_schema__")):
        return None
    validator = model.__pydantic_validator__
    return validator if isinstance(validator, SchemaValidator) else None
