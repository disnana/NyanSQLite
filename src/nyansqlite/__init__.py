from ._markers import CompositeIndex, Indexed, Searchable, UniqueIndexed
from .core import NyanSQLite
from .exceptions import (
    FieldNotFoundError,
    ModelNotRegisteredError,
    SearchNotEnabledError,
    TableNameCollisionError,
)

__all__ = [
    "NyanSQLite",
    "Indexed",
    "UniqueIndexed",
    "Searchable",
    "CompositeIndex",
    "FieldNotFoundError",
    "ModelNotRegisteredError",
    "SearchNotEnabledError",
    "TableNameCollisionError",
]
__version__ = "1.0.0"
