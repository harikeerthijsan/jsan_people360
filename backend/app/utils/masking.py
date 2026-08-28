"""Masking for sensitive identifiers.

Every read response returns masked values. The unmasked form is available from
exactly one endpoint, which audits the access -- see
``docs/EmployeeModule.md``.

Masks keep the *last* few characters rather than the first. That is the half a
person uses to confirm "yes, that's my account", and it is the half that is
useless on its own to someone who has only seen the response.
"""

from __future__ import annotations

#: Character the masked portion is replaced with. A fixed glyph rather than one
#: per hidden character would leak nothing, but it also stops the reader
#: sanity-checking the length of what they entered.
MASK_CHARACTER = "X"


def mask_tail(value: str | None, *, visible: int = 4) -> str | None:
    """Hide everything but the last ``visible`` characters.

    ``123456789012`` -> ``XXXXXXXX9012``

    A value no longer than ``visible`` is masked entirely: revealing all of a
    short value would defeat the point.
    """
    if value is None:
        return None

    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) <= visible:
        return MASK_CHARACTER * len(cleaned)

    return MASK_CHARACTER * (len(cleaned) - visible) + cleaned[-visible:]


def mask_aadhaar(value: str | None) -> str | None:
    """``XXXXXXXX9012`` -- the last four digits, as the UIDAI itself displays it."""
    return mask_tail(value, visible=4)


def mask_pan(value: str | None) -> str | None:
    """``XXXXXX234F`` -- enough to distinguish two people's PANs, not enough to use."""
    return mask_tail(value, visible=4)


def mask_account_number(value: str | None) -> str | None:
    """``XXXXXXXX3210`` -- the last four digits, matching how banks print them."""
    return mask_tail(value, visible=4)
