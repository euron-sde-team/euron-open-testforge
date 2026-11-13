"""A shopping cart."""

from __future__ import annotations

from app.pricing import apply_discount


class Cart:
    """Items and quantities, with a total.

    >>> cart = Cart()
    >>> cart.add("tea", 2, 3.5)
    >>> cart.total()
    7.0
    """

    def __init__(self) -> None:
        self.items: dict[str, tuple[int, float]] = {}

    def add(self, sku: str, quantity: int, unit_price: float) -> None:
        """Add ``quantity`` of ``sku`` at ``unit_price``."""
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if unit_price < 0:
            raise ValueError("unit price must not be negative")
        held, _ = self.items.get(sku, (0, unit_price))
        self.items[sku] = (held + quantity, unit_price)

    def remove(self, sku: str) -> None:
        """Remove an item entirely."""
        if sku not in self.items:
            raise KeyError(sku)
        del self.items[sku]

    def count(self) -> int:
        """How many units are in the cart.

        >>> cart = Cart()
        >>> cart.add("tea", 2, 3.5)
        >>> cart.add("cup", 1, 8.0)
        >>> cart.count()
        3
        """
        return sum(q for q, _ in self.items.values())

    def total(self, discount_percent: float = 0) -> float:
        """The cart total after an optional discount.

        >>> cart = Cart()
        >>> cart.add("cup", 2, 8.0)
        >>> cart.total(25)
        12.0
        """
        subtotal = sum(q * p for q, p in self.items.values())
        return apply_discount(subtotal, discount_percent)
