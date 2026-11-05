"""Command-line interface for ccvalidator."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from collections.abc import Sequence

from . import __version__
from .validator import ValidationResult, validate_card


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ccvalidator",
        description=(
            "Validate a payment card number (Luhn checksum, brand, length) and, "
            "optionally, its CVV and expiry date. Exit status is 0 if valid, 1 if not."
        ),
        epilog=(
            "Tip: omit NUMBER (or pass '-') to type it privately or pipe it in, "
            "instead of leaving it in your shell history."
        ),
    )
    parser.add_argument(
        "number",
        nargs="?",
        help="card number; spaces and dashes are allowed. Omit or use '-' to read it from stdin.",
    )
    parser.add_argument("--cvv", help="also check the CVV format (4 digits for Amex, else 3)")
    parser.add_argument(
        "--expiry", metavar="MM/YY", help="also check the expiry date (MM/YY or MM/YYYY)"
    )
    parser.add_argument(
        "--allow-unknown-brand",
        action="store_true",
        help="accept Luhn-valid numbers of 12-19 digits even if the brand is not recognised",
    )
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _read_number(value: str | None) -> str:
    if value not in (None, "-"):
        return str(value)
    if sys.stdin.isatty():
        return getpass.getpass("Card number (input hidden): ")
    return sys.stdin.readline().strip()


def _format_text(result: ValidationResult) -> str:
    lines = [
        f"Card:    {result.masked_number or '(none)'}",
        f"Brand:   {result.brand.value}",
        f"Luhn:    {'ok' if result.luhn_valid else 'FAILED'}",
        f"Length:  {'ok' if result.length_valid else 'INVALID'}",
    ]
    if result.cvv_valid is not None:
        lines.append(f"CVV:     {'ok' if result.cvv_valid else 'INVALID'}")
    if result.expiry_valid is not None:
        lines.append(f"Expiry:  {'ok' if result.expiry_valid else 'INVALID'}")
    lines.append(f"Result:  {'VALID' if result.valid else 'INVALID'}")
    lines.extend(f"  - {error}" for error in result.errors)
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns the process exit status."""
    args = _build_parser().parse_args(argv)
    result = validate_card(
        _read_number(args.number),
        cvv=args.cvv,
        expiry=args.expiry,
        allow_unknown_brand=args.allow_unknown_brand,
    )
    print(json.dumps(result.to_dict(), indent=2) if args.json else _format_text(result))
    return 0 if result.valid else 1


if __name__ == "__main__":
    sys.exit(main())
