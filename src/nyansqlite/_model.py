from __future__ import annotations

from functools import lru_cache
from typing import Any, TypeVar

from pydantic import AliasChoices, AliasPath, BaseModel

from ._markers import _NyanIndexedMarker, _NyanSearchableMarker
from ._types import resolve_type, serialize_value

M = TypeVar("M", bound=BaseModel)


@lru_cache(maxsize=256)
def _input_paths(model: type[BaseModel]) -> dict[str, list[Any]]:
    if model.model_config.get("validate_by_alias") is False:
        return {}
    paths = {}
    for name, field in model.model_fields.items():
        alias = field.validation_alias
        if isinstance(alias, AliasChoices):
            alias = alias.choices[0]
        if isinstance(alias, AliasPath):
            paths[name] = alias.path
        elif isinstance(alias, str) and alias != name:
            paths[name] = [alias]
    return paths


@lru_cache(maxsize=256)
def _alias_list_sizes(model: type[BaseModel]) -> dict[tuple, int]:
    bounds: dict[tuple, tuple[int, int]] = {}
    for path in _input_paths(model).values():
        for index, component in enumerate(path):
            if isinstance(component, int):
                prefix = tuple(path[:index])
                positive, negative = bounds.get(prefix, (0, 0))
                if component >= 0:
                    positive = max(positive, component + 1)
                else:
                    negative = max(negative, -component)
                bounds[prefix] = (positive, negative)
    return {prefix: positive + negative for prefix, (positive, negative) in bounds.items()}


def _put_path(container: Any, path: list[Any], value: Any, sizes: dict, prefix: tuple = ()) -> None:
    key = path[0]
    if isinstance(container, list):
        needed = sizes[prefix]
        while len(container) < needed:
            container.append(None)
    if len(path) == 1:
        container[key] = value
        return
    missing = key not in container if isinstance(container, dict) else container[key] is None
    if missing:
        container[key] = [] if isinstance(path[1], int) else {}
    _put_path(container[key], path[1:], value, sizes, (*prefix, key))


def model_input(model: type[BaseModel], data: dict[str, Any]) -> dict[str, Any]:
    paths = _input_paths(model)
    if paths:
        inputs = {name: value for name, value in data.items() if name not in paths}
        for name, path in paths.items():
            if name in data:
                _put_path(inputs, path, data[name], _alias_list_sizes(model))
        data = inputs
    return data


def validate_model(model: type[M], data: dict[str, Any]) -> M:
    """Validate canonical database field names without changing the user's config."""
    return model.model_validate(model_input(model, data))


def validation_data(value: Any) -> Any:
    """Include excluded fields and revalidate nested instances after mutation."""
    if isinstance(value, BaseModel):
        data = {name: validation_data(getattr(value, name)) for name in type(value).model_fields
                if name in value.__dict__}
        return model_input(type(value), data)
    if isinstance(value, list):
        return [validation_data(item) for item in value]
    if isinstance(value, dict):
        return {key: validation_data(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(validation_data(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return [validation_data(item) for item in value]
    return value


@lru_cache(maxsize=256)
def _primitive_plan(model: type[BaseModel]) -> tuple:
    from ._update_validation import needs_row_validation
    if needs_row_validation(model):
        return ()
    plan = []
    for name, field in model.model_fields.items():
        base, optional = resolve_type(field.rebuild_annotation())
        if base not in (str, int, float, bool, bytes) or any(
            not isinstance(marker, (_NyanIndexedMarker, _NyanSearchableMarker)) for marker in field.metadata
        ):
            return ()
        plan.append((name, base, optional))
    return tuple(plan)


def validate_instance(obj: M) -> M:
    plan = _primitive_plan(type(obj))
    if plan:
        data = obj.__dict__
        for name, base, optional in plan:
            if name not in data:
                break
            value = data[name]
            if type(value) is not base and not (value is None and optional):
                break
        else:
            return obj
    return type(obj).model_validate(validation_data(obj))


def instance_values(obj: BaseModel, hints: dict[str, Any]) -> tuple:
    """One insertion path for single/bulk calls, bypassing dump exclusions."""
    validated = validate_instance(obj)
    if _primitive_plan(type(obj)):
        return tuple(validated.__dict__[name] for name in hints)
    return tuple(serialize_value(getattr(validated, name), annotation) for name, annotation in hints.items())
