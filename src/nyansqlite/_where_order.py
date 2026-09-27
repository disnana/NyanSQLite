"""Cache the field permutation used for equivalent keyword predicates."""

from functools import lru_cache


@lru_cache(maxsize=1024)
def keyword_order(keys: tuple[str, ...]) -> tuple[int, ...]:
    """Return sorted positions, or an empty tuple when already ordered."""
    order = tuple(sorted(range(len(keys)), key=keys.__getitem__))
    if order == tuple(range(len(keys))):
        return ()
    return order
