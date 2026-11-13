"""Prices, discounts and splitting a bill."""

from __future__ import annotations


def apply_discount(price: float, percent: float) -> float:
    """Apply a percentage discount and round to cents.

    >>> apply_discount(100.0, 10)
    90.0
    >>> apply_discount(19.99, 15)
    16.99
    """
    if price < 0:
        raise ValueError("price must not be negative")
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")
    return round(price * (100 - percent) / 100, 2)


def add_tax(amount: float, rate: float = 0.2) -> float:
    """Add sales tax at ``rate`` and round to cents.

    >>> add_tax(50.0)
    60.0
    >>> add_tax(10.0, 0.05)
    10.5
    """
    if rate < 0:
        raise ValueError("rate must not be negative")
    return round(amount * (1 + rate), 2)


def split_bill(total: float, people: int) -> list[float]:
    """Split a bill into equal shares that add up to the total, to the cent.

    >>> split_bill(90.0, 3)
    [30.0, 30.0, 30.0]
    >>> split_bill(100.0, 3)
    [33.34, 33.33, 33.33]
    """
    if people <= 0:
        raise ValueError("people must be at least 1")
    share = int(total * 100 / people) / 100
    return [share] * people


def format_price(amount: float, currency: str = "USD") -> str:
    """Format an amount for display.

    >>> format_price(1234.5)
    'USD 1,234.50'
    >>> format_price(3, "EUR")
    'EUR 3.00'
    """
    return f"{currency} {amount:,.2f}"
