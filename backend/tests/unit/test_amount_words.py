"""The words on a payslip must not depend on the server's locale."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.utils.amount_words import amount_to_words


@pytest.mark.parametrize(
    ("amount", "currency", "expected"),
    [
        ("0", "INR", "Zero rupees only"),
        ("1", "INR", "One rupee only"),
        ("1.01", "INR", "One rupee and one paisa only"),
        ("41989.13", "INR", "Forty-one thousand nine hundred eighty-nine rupees and thirteen paise only"),
        ("100000", "INR", "One lakh rupees only"),
        (
            "12345678.90",
            "INR",
            "One crore twenty-three lakh forty-five thousand six hundred seventy-eight rupees "
            "and ninety paise only",
        ),
        (
            "1234567.05",
            "USD",
            "One million two hundred thirty-four thousand five hundred sixty-seven dollars "
            "and five cents only",
        ),
        ("2.50", "GBP", "Two pounds and fifty pence only"),
        ("15", "XYZ", "Fifteen XYZ only"),
    ],
)
def test_amount_to_words(amount: str, currency: str, expected: str) -> None:
    assert amount_to_words(Decimal(amount), currency) == expected


def test_rounds_to_the_cent_before_speaking() -> None:
    assert amount_to_words(Decimal("9.999"), "USD") == "Ten dollars only"
