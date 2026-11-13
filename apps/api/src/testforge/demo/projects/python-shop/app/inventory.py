"""Stock levels and reservations."""

from __future__ import annotations


def reserve(stock: int, quantity: int) -> int:
    """Reserve ``quantity`` units and return the stock left.

    >>> reserve(10, 3)
    7
    """
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if quantity > stock:
        raise ValueError("not enough stock")
    return stock - quantity


def needs_reorder(stock: int, threshold: int = 5) -> bool:
    """Whether stock has fallen to the reorder threshold.

    >>> needs_reorder(3)
    True
    >>> needs_reorder(12)
    False
    """
    return stock <= threshold


def restock_plan(levels: dict[str, int], target: int) -> dict[str, int]:
    """Units to order per SKU to bring each one up to ``target``.

    >>> restock_plan({"tea": 2, "cup": 9}, 10)
    {'tea': 8, 'cup': 1}
    """
    if target < 0:
        raise ValueError("target must not be negative")
    return {sku: max(target - level, 0) for sku, level in levels.items()}
