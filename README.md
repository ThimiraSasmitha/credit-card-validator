# credit-card-validator

[![CI](https://github.com/ThimiraSasmitha/credit-card-validator/actions/workflows/ci.yml/badge.svg)](https://github.com/ThimiraSasmitha/credit-card-validator/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

A small, dependency-free Python library and command-line tool that validates payment card numbers.

- **Luhn checksum** verification
- **Brand detection** (Visa, Mastercard, American Express, Discover, Diners Club, JCB, UnionPay, Maestro)
- **Per-brand length rules**
- **CVV format** check (4 digits for Amex, 3 for everything else)
- **Expiry date** check (`MM/YY` or `MM/YYYY`; valid through the end of the expiry month)
- **Safe by design**: results only ever contain a masked number, and error messages never echo input
- Fully typed (`py.typed`), no runtime dependencies

> **Scope:** this checks that a number is *well-formed*. It cannot tell you whether a card exists,
> is active, or has funds. Only your payment processor can do that.

## Install

```bash
git clone https://github.com/ThimiraSasmitha/credit-card-validator.git
cd credit-card-validator
pip install .
```

For development: `pip install -e ".[dev]"`

## Command line

```console
$ ccvalidator 4111-1111-1111-1111 --cvv 123 --expiry 12/2030
Card:    ************1111
Brand:   Visa
Luhn:    ok
Length:  ok
CVV:     ok
Expiry:  ok
Result:  VALID

$ ccvalidator 4111111111111112
Card:    ************1112
Brand:   Visa
Luhn:    FAILED
Length:  ok
Result:  INVALID
  - Card number fails the Luhn checksum.

$ echo 378282246310005 | ccvalidator --json
{
  "valid": true,
  "brand": "American Express",
  "luhn_valid": true,
  "length_valid": true,
  "masked_number": "***********0005",
  "cvv_valid": null,
  "expiry_valid": null,
  "errors": []
}
```

| Option | Description |
| --- | --- |
| `NUMBER` | Card number (spaces/dashes OK). Omit it, or pass `-`, to type it hidden or pipe it via stdin. |
| `--cvv CVV` | Also validate the CVV format. |
| `--expiry MM/YY` | Also validate the expiry date. |
| `--allow-unknown-brand` | Accept Luhn-valid numbers of 12-19 digits from unrecognised networks. |
| `--json` | Machine-readable output. |

Exit status is `0` if valid, `1` if invalid, `2` for usage errors. `python -m ccvalidator` works too.

## Library

```python
from ccvalidator import validate_card, luhn_valid, detect_brand, mask_number

result = validate_card("4111 1111 1111 1111", cvv="123", expiry="12/2030")

result.valid          # True
result.brand.value    # "Visa"
result.masked_number  # "************1111"
result.errors         # ()

bad = validate_card("3782822463100050")   # 16 digits is not a legal Amex length
bad.errors            # ("American Express numbers must be 15 digits long (got 16).",
                      #  "Card number fails the Luhn checksum.")

luhn_valid("4111111111111111")   # True
detect_brand("5555555555554444") # CardBrand.MASTERCARD
mask_number("378282246310005")   # "***********0005"
```

Pass `allow_unknown_brand=True` to `validate_card` to accept any Luhn-valid 12-19 digit number, and
`today=date(...)` to make expiry checks deterministic in your own tests.

## Supported brands

| Brand | Prefix (IIN) | Length | CVV |
| --- | --- | --- | --- |
| American Express | 34, 37 | 15 | 4 |
| Visa | 4 | 13, 16, 19 | 3 |
| Mastercard | 51-55, 2221-2720 | 16 | 3 |
| Discover | 6011, 622126-622925, 644-649, 65 | 16-19 | 3 |
| Diners Club | 300-305, 3095, 36, 38-39 | 14-19 | 3 |
| JCB | 3528-3589 | 16-19 | 3 |
| UnionPay | 62 (outside Discover's range) | 16-19 | 3 |
| Maestro | 5018, 5020, 5038, 5893, 6304, 6759, 6761-6763 | 12-19 | 3 |

Network ranges change over time. If you need to support a new range, add a `_BrandSpec` entry to
`src/ccvalidator/validator.py` (order matters: put narrower prefixes before broader ones) and add a test.

## Security notes

- **Use test numbers.** The tests use publicly documented sandbox numbers such as `4111111111111111`.
  Avoid pasting real card numbers into any tool, including this one, unless you control the environment.
- Passing a number as a CLI argument leaves it in your shell history. Omit it to be prompted with hidden
  input, or pipe it in.
- This project does not log, store, or transmit anything.
- If you handle real card data in production, you are in scope for [PCI DSS](https://www.pcisecuritystandards.org/).
  Prefer your processor's hosted fields or tokenization so card numbers never touch your servers.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

pytest --cov=ccvalidator   # tests
ruff check . && ruff format --check .   # lint
mypy                       # strict type checking
```

GitHub Actions runs all of the above on Python 3.10-3.13 for every push and pull request.

## Project layout

```
.
├── .github/workflows/ci.yml   # lint, type-check, test matrix
├── src/ccvalidator/
│   ├── __init__.py            # public API
│   ├── __main__.py            # python -m ccvalidator
│   ├── cli.py                 # command-line interface
│   ├── py.typed
│   └── validator.py           # Luhn, brands, CVV, expiry, validate_card()
├── tests/
│   ├── test_cli.py
│   └── test_validator.py
├── pyproject.toml
├── LICENSE
└── README.md
```

## License

[MIT](LICENSE)
