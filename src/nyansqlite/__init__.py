from ._markers import CompositeIndex, Indexed, Searchable, UniqueIndexed
from .core import NyanSQLite
from .exceptions import FieldNotFoundError, ModelNotRegisteredError, SearchNotEnabledError

__all__ = [
    "NyanSQLite",
    "Indexed",
    "UniqueIndexed",
    "Searchable",
    "CompositeIndex",
    "FieldNotFoundError",
    "ModelNotRegisteredError",
    "SearchNotEnabledError",
]
__version__ = "1.0.0"
