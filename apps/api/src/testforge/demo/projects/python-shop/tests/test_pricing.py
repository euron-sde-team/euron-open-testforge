import pytest

from app.pricing import apply_discount


def test_apply_discount_takes_ten_percent_off():
    assert apply_discount(100.0, 10) == 90.0


def test_apply_discount_refuses_a_negative_price():
    with pytest.raises(ValueError):
        apply_discount(-1.0, 10)
