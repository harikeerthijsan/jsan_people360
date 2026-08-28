"""Money in words, for payslips.

Indian-style grouping (lakh, crore) for INR — the convention a payslip
reader in India expects — and thousand/million/billion for every other
currency. Pure functions, no locale dependency, so the words on a payslip
cannot change with the server's environment.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_ONES = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")

#: (major unit singular, major plural, minor singular, minor plural)
_UNITS: dict[str, tuple[str, str, str, str]] = {
    "INR": ("rupee", "rupees", "paisa", "paise"),
    "USD": ("dollar", "dollars", "cent", "cents"),
    "EUR": ("euro", "euros", "cent", "cents"),
    "GBP": ("pound", "pounds", "penny", "pence"),
    "AED": ("dirham", "dirhams", "fils", "fils"),
    "SGD": ("dollar", "dollars", "cent", "cents"),
    "AUD": ("dollar", "dollars", "cent", "cents"),
    "CAD": ("dollar", "dollars", "cent", "cents"),
}


def _below_thousand(number: int) -> str:
    """0..999 in words."""
    parts: list[str] = []
    hundreds, rest = divmod(number, 100)
    if hundreds:
        parts.append(f"{_ONES[hundreds]} hundred")
    if rest:
        if rest < 20:
            parts.append(_ONES[rest])
        else:
            tens, ones = divmod(rest, 10)
            parts.append(_TENS[tens] + (f"-{_ONES[ones]}" if ones else ""))
    return " ".join(parts)


def _indian(number: int) -> str:
    if number == 0:
        return _ONES[0]
    parts: list[str] = []
    crore, number = divmod(number, 10_000_000)
    lakh, number = divmod(number, 100_000)
    thousand, number = divmod(number, 1_000)
    if crore:
        parts.append(f"{_indian(crore)} crore")
    if lakh:
        parts.append(f"{_below_thousand(lakh)} lakh")
    if thousand:
        parts.append(f"{_below_thousand(thousand)} thousand")
    if number:
        parts.append(_below_thousand(number))
    return " ".join(parts)


def _international(number: int) -> str:
    if number == 0:
        return _ONES[0]
    scales = ("", "thousand", "million", "billion", "trillion")
    parts: list[str] = []
    index = 0
    while number and index < len(scales):
        number, chunk = divmod(number, 1000)
        if chunk:
            words = _below_thousand(chunk)
            parts.append(f"{words} {scales[index]}".strip())
        index += 1
    return " ".join(reversed(parts))


def amount_to_words(amount: Decimal, currency: str) -> str:
    """``Decimal("42489.13"), "INR"`` -> ``"Forty-two thousand four hundred
    eighty-nine rupees and thirteen paise only"``."""
    quantized = amount.quantize(Decimal("0.01"), ROUND_HALF_UP)
    negative = quantized < 0
    major = int(abs(quantized))
    minor = int((abs(quantized) - major) * 100)
    code = currency.upper()
    major_one, major_many, minor_one, minor_many = _UNITS.get(code, (code, code, "cent", "cents"))
    words = _indian(major) if code == "INR" else _international(major)
    text = f"{words} {major_one if major == 1 else major_many}"
    if minor:
        minor_words = _below_thousand(minor)
        text += f" and {minor_words} {minor_one if minor == 1 else minor_many}"
    text = f"minus {text}" if negative else text
    return f"{text[0].upper()}{text[1:]} only"
