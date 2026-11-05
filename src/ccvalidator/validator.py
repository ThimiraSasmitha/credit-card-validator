"""Core validation logic: Luhn checksum, brand detection, CVV and expiry checks.

Only *format* validation happens here. Nothing in this module can tell you whether
a card is real, active, or has funds; only a payment processor can do that.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any

__all__ = [
    "CardBrand",
    "ValidationResult",
    "clean_number",
    "detect_brand",
    "is_expiry_valid",
    "luhn_valid",
    "mask_number",
    "parse_expiry",
    "validate_card",
    "validate_card_number",
    "validate_cvv",
]

MIN_CARD_LENGTH = 12
MAX_CARD_LENGTH = 19  # ISO/IEC 7812 upper bound
MAX_EXPIRY_YEARS_AHEAD = 20

_DIGITS_ONLY = re.compile(r"[0-9]+")
_SEPARATORS = re.compile(r"[\s\-]")
_EXPIRY = re.compile(r"(0[1-9]|1[0-2])\s*[/\-]?\s*([0-9]{2}|[0-9]{4})")


class CardBrand(Enum):
    """Card networks that can be recognised from the number's prefix."""

    AMEX = "American Express"
    VISA = "Visa"
    MASTERCARD = "Mastercard"
    DISCOVER = "Discover"
    DINERS_CLUB = "Diners Club"
    JCB = "JCB"
    UNIONPAY = "UnionPay"
    MAESTRO = "Maestro"
    UNKNOWN = "Unknown"


@dataclass(frozen=True)
class _BrandSpec:
    brand: CardBrand
    prefix: re.Pattern[str]
    lengths: tuple[int, ...]
    cvv_length: int = 3


# Order matters: more specific ranges must come before broader ones
# (e.g. Discover's 622126-622925 before UnionPay's 62).
_BRANDS: tuple[_BrandSpec, ...] = (
    _BrandSpec(CardBrand.AMEX, re.compile(r"3[47]"), (15,), cvv_length=4),
    _BrandSpec(CardBrand.VISA, re.compile(r"4"), (13, 16, 19)),
    _BrandSpec(
        CardBrand.MASTERCARD,
        re.compile(r"5[1-5]|222[1-9]|22[3-9]|2[3-6]|27[01]|2720"),
        (16,),
    ),
    _BrandSpec(
        CardBrand.DISCOVER,
        re.compile(r"6011|65|64[4-9]|622(?:12[6-9]|1[3-9]\d|[2-8]\d{2}|9[01]\d|92[0-5])"),
        (16, 17, 18, 19),
    ),
    _BrandSpec(
        CardBrand.DINERS_CLUB, re.compile(r"30[0-5]|3095|36|3[89]"), (14, 15, 16, 17, 18, 19)
    ),
    _BrandSpec(CardBrand.JCB, re.compile(r"35(?:2[89]|[3-8]\d)"), (16, 17, 18, 19)),
    _BrandSpec(CardBrand.UNIONPAY, re.compile(r"62"), (16, 17, 18, 19)),
    _BrandSpec(
        CardBrand.MAESTRO,
        re.compile(r"5018|5020|5038|5893|6304|6759|676[1-3]"),
        tuple(range(12, 20)),
    ),
)

_SPEC_BY_BRAND = {spec.brand: spec for spec in _BRANDS}


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a card. Never contains the full card number."""

    valid: bool
    brand: CardBrand
    luhn_valid: bool
    length_valid: bool
    masked_number: str
    cvv_valid: bool | None = None
    expiry_valid: bool | None = None
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """JSON-friendly representation."""
        return {
            "valid": self.valid,
            "brand": self.brand.value,
            "luhn_valid": self.luhn_valid,
            "length_valid": self.length_valid,
            "masked_number": self.masked_number,
            "cvv_valid": self.cvv_valid,
            "expiry_valid": self.expiry_valid,
            "errors": list(self.errors),
        }

# Building blocks
def clean_number(number: str) -> str:
    """Strip spaces and dashes from a card number string."""
    return _SEPARATORS.sub("", number)


def luhn_valid(number: str) -> bool:
    """Return True if ``number`` (digits, spaces and dashes allowed) passes the Luhn check."""
    cleaned = clean_number(number)
    if not _DIGITS_ONLY.fullmatch(cleaned):
        return False

    total = 0
    for index, char in enumerate(reversed(cleaned)):
        digit = ord(char) - ord("0")
        if index % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def detect_brand(number: str) -> CardBrand:
    """Identify the card network from the number's prefix (no length or Luhn check)."""
    cleaned = clean_number(number)
    if not _DIGITS_ONLY.fullmatch(cleaned):
        return CardBrand.UNKNOWN
    spec = _find_spec(cleaned)
    return spec.brand if spec else CardBrand.UNKNOWN


def mask_number(number: str) -> str:
    """Mask a card number, keeping only the last four digits (e.g. ``************1111``)."""
    cleaned = clean_number(number)
    if len(cleaned) <= 4 or not _DIGITS_ONLY.fullmatch(cleaned):
        return "*" * len(cleaned)
    return "*" * (len(cleaned) - 4) + cleaned[-4:]


def validate_cvv(cvv: str, brand: CardBrand | None = None) -> bool:
    """Check CVV format: 4 digits for American Express, 3 for other known brands.

    If the brand is unknown or omitted, either 3 or 4 digits are accepted.
    """
    if not _DIGITS_ONLY.fullmatch(cvv):
        return False
    if brand is None or brand is CardBrand.UNKNOWN:
        return len(cvv) in (3, 4)
    return len(cvv) == _SPEC_BY_BRAND[brand].cvv_length


def parse_expiry(expiry: str) -> tuple[int, int]:
    """Parse ``MM/YY``, ``MM/YYYY``, ``MM-YY`` or ``MMYY`` into ``(month, four_digit_year)``.

    Raises ``ValueError`` if the string is not a valid expiry format.
    """
    match = _EXPIRY.fullmatch(expiry.strip())
    if not match:
        raise ValueError("Expiry must look like MM/YY or MM/YYYY.")
    month = int(match.group(1))
    year = int(match.group(2))
    if year < 100:
        year += 2000
    return month, year


def is_expiry_valid(expiry: str, today: date | None = None) -> bool:
    """True if the expiry parses, is not in the past, and is at most 20 years ahead.

    Cards are valid through the *last day* of their expiry month.
    """
    try:
        month, year = parse_expiry(expiry)
    except ValueError:
        return False
    today = today or date.today()
    if (year, month) < (today.year, today.month):
        return False
    return year <= today.year + MAX_EXPIRY_YEARS_AHEAD

# High-level API
def validate_card(
    number: str,
    cvv: str | None = None,
    expiry: str | None = None,
    *,
    today: date | None = None,
    allow_unknown_brand: bool = False,
) -> ValidationResult:
    """Validate a card number and, optionally, its CVV and expiry date.

    By default the number must belong to a recognised brand, have a length that is
    legal for that brand, and pass the Luhn checksum. Set ``allow_unknown_brand=True``
    to accept any Luhn-valid number of 12-19 digits.

    Error messages never echo the card number, CVV or expiry back.
    """
    errors: list[str] = []
    cleaned = clean_number(number)
    brand = CardBrand.UNKNOWN
    luhn_ok = False
    length_ok = False

    if not cleaned:
        errors.append("Card number is empty.")
    elif not _DIGITS_ONLY.fullmatch(cleaned):
        errors.append("Card number may contain only digits, spaces and dashes.")
    else:
        spec = _find_spec(cleaned)
        if spec is not None:
            brand = spec.brand
            length_ok = len(cleaned) in spec.lengths
            expected = _describe_lengths(spec.lengths)
            length_error = (
                f"{brand.value} numbers must be {expected} digits long (got {len(cleaned)})."
            )
        else:
            length_ok = MIN_CARD_LENGTH <= len(cleaned) <= MAX_CARD_LENGTH
            length_error = (
                f"Card number must be {MIN_CARD_LENGTH}-{MAX_CARD_LENGTH} digits long "
                f"(got {len(cleaned)})."
            )
            if not allow_unknown_brand:
                errors.append("Unrecognised card brand.")

        if not length_ok:
            errors.append(length_error)
        luhn_ok = luhn_valid(cleaned)
        if not luhn_ok:
            errors.append("Card number fails the Luhn checksum.")

    cvv_ok: bool | None = None
    if cvv is not None:
        cvv_ok = validate_cvv(cvv, brand)
        if not cvv_ok:
            errors.append("CVV is not valid for this card type.")

    expiry_ok: bool | None = None
    if expiry is not None:
        expiry_ok = is_expiry_valid(expiry, today)
        if not expiry_ok:
            errors.append("Expiry date is malformed, in the past, or too far in the future.")

    return ValidationResult(
        valid=not errors,
        brand=brand,
        luhn_valid=luhn_ok,
        length_valid=length_ok,
        masked_number=mask_number(cleaned),
        cvv_valid=cvv_ok,
        expiry_valid=expiry_ok,
        errors=tuple(errors),
    )


def validate_card_number(number: str, *, allow_unknown_brand: bool = False) -> ValidationResult:
    """Shortcut for ``validate_card(number)`` when you only have a card number."""
    return validate_card(number, allow_unknown_brand=allow_unknown_brand)

# Helpers
def _find_spec(cleaned: str) -> _BrandSpec | None:
    for spec in _BRANDS:
        if spec.prefix.match(cleaned):
            return spec
    return None


def _describe_lengths(lengths: tuple[int, ...]) -> str:
    if len(lengths) == 1:
        return str(lengths[0])
    if list(lengths) == list(range(lengths[0], lengths[-1] + 1)):
        return f"{lengths[0]}-{lengths[-1]}"
    return f"{', '.join(str(n) for n in lengths[:-1])} or {lengths[-1]}"
