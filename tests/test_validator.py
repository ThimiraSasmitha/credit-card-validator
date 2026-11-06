from datetime import date

import pytest

from ccvalidator import (
    CardBrand,
    clean_number,
    detect_brand,
    is_expiry_valid,
    luhn_valid,
    mask_number,
    parse_expiry,
    validate_card,
    validate_card_number,
    validate_cvv,
)

# Publicly documented test numbers (they are not real accounts).
VALID_NUMBERS = [
    ("4111111111111111", CardBrand.VISA),
    ("4012888888881881", CardBrand.VISA),
    ("4222222222222", CardBrand.VISA),  # 13-digit legacy Visa
    ("5555555555554444", CardBrand.MASTERCARD),
    ("5105105105105100", CardBrand.MASTERCARD),
    ("2223003122003222", CardBrand.MASTERCARD),  # 2-series range
    ("378282246310005", CardBrand.AMEX),
    ("371449635398431", CardBrand.AMEX),
    ("6011111111111117", CardBrand.DISCOVER),
    ("6011000990139424", CardBrand.DISCOVER),
    ("30569309025904", CardBrand.DINERS_CLUB),
    ("38520000023237", CardBrand.DINERS_CLUB),
    ("3530111333300000", CardBrand.JCB),
    ("3566002020360505", CardBrand.JCB),
    ("6200000000000005", CardBrand.UNIONPAY),
    ("6759649826438453", CardBrand.MAESTRO),
    ("6759649836438453", CardBrand.MAESTRO),

]

TODAY = date(2026, 11, 5)


class TestLuhn:
    @pytest.mark.parametrize(("number", "_brand"), VALID_NUMBERS)
    def test_valid_numbers_pass(self, number, _brand):
        assert luhn_valid(number)

    @pytest.mark.parametrize("number", ["4111111111111112", "1234567812345678", "378282246310006"])
    def test_bad_checksum_fails(self, number):
        assert not luhn_valid(number)

    @pytest.mark.parametrize("number", ["", "abcd", "4111-1111-1111-111x", "4111.1111"])
    def test_non_numeric_fails(self, number):
        assert not luhn_valid(number)

    def test_separators_are_ignored(self):
        assert luhn_valid("4111 1111 1111 1111")
        assert luhn_valid("4111-1111-1111-1111")

    def test_unicode_digits_are_rejected(self):
        assert not luhn_valid("４１１１１１１１１１１１１１１１")  # full-width digits


class TestBrandDetection:
    @pytest.mark.parametrize(("number", "brand"), VALID_NUMBERS)
    def test_known_numbers(self, number, brand):
        assert detect_brand(number) is brand

    @pytest.mark.parametrize(
        ("prefix", "brand"),
        [
            ("2221", CardBrand.MASTERCARD),
            ("2720", CardBrand.MASTERCARD),
            ("2220", CardBrand.UNKNOWN),
            ("2721", CardBrand.UNKNOWN),
            ("622126", CardBrand.DISCOVER),  # Discover/UnionPay overlap
            ("622925", CardBrand.DISCOVER),
            ("622125", CardBrand.UNIONPAY),
            ("622926", CardBrand.UNIONPAY),
            ("644", CardBrand.DISCOVER),
            ("65", CardBrand.DISCOVER),
            ("3528", CardBrand.JCB),
            ("3589", CardBrand.JCB),
            ("3095", CardBrand.DINERS_CLUB),
            ("300", CardBrand.DINERS_CLUB),
            ("9", CardBrand.UNKNOWN),
        ],
    )
    def test_prefix_boundaries(self, prefix, brand):
        assert detect_brand(prefix + "0" * 10) is brand

    def test_non_digits_are_unknown(self):
        assert detect_brand("4abc") is CardBrand.UNKNOWN


class TestValidateCard:
    @pytest.mark.parametrize(("number", "brand"), VALID_NUMBERS)
    def test_valid_cards(self, number, brand):
        result = validate_card(number)
        assert result.valid
        assert result.brand is brand
        assert result.luhn_valid and result.length_valid
        assert result.errors == ()

    def test_formatted_input_is_accepted(self):
        assert validate_card("4111 1111 1111 1111").valid
        assert validate_card("3782-822463-10005").valid

    def test_bad_luhn(self):
        result = validate_card("4111111111111112")
        assert not result.valid
        assert not result.luhn_valid
        assert result.brand is CardBrand.VISA

    def test_wrong_length_for_brand(self):
        # Valid Luhn, Amex prefix, but 16 digits
        result = validate_card("3782822463100050")
        assert not result.length_valid
        assert any("American Express" in e for e in result.errors)

    def test_empty(self):
        result = validate_card("   ")
        assert not result.valid
        assert result.errors == ("Card number is empty.",)

    def test_letters_rejected(self):
        result = validate_card("4111 1111 1111 111a")
        assert not result.valid
        assert result.brand is CardBrand.UNKNOWN

    def test_unknown_brand_strict_by_default(self):
        number = "9000000000000001"  # Luhn-valid, no known brand
        assert luhn_valid(number)
        assert not validate_card(number).valid
        assert validate_card(number, allow_unknown_brand=True).valid
        assert validate_card_number(number, allow_unknown_brand=True).valid

    def test_unknown_brand_length_still_enforced(self):
        assert not validate_card("90000000009", allow_unknown_brand=True).valid  # 11 digits

    def test_errors_never_leak_the_number(self):
        number = "4111111111111112"
        result = validate_card(number, cvv="12", expiry="nope")
        flat = " ".join(result.errors) + result.masked_number
        assert number not in flat
        assert "nope" not in flat

    def test_cvv_and_expiry_are_part_of_overall_validity(self):
        ok = validate_card("4111111111111111", cvv="123", expiry="12/27", today=TODAY)
        assert ok.valid and ok.cvv_valid and ok.expiry_valid

        bad_cvv = validate_card("4111111111111111", cvv="1234", expiry="12/27", today=TODAY)
        assert not bad_cvv.valid and bad_cvv.cvv_valid is False

        expired = validate_card("4111111111111111", cvv="123", expiry="01/20", today=TODAY)
        assert not expired.valid and expired.expiry_valid is False

    def test_optional_checks_default_to_none(self):
        result = validate_card("4111111111111111")
        assert result.cvv_valid is None
        assert result.expiry_valid is None

    def test_to_dict(self):
        data = validate_card("4111111111111111").to_dict()
        assert data["brand"] == "Visa"
        assert data["valid"] is True
        assert data["masked_number"] == "************1111"
        assert data["errors"] == []


class TestMasking:
    def test_masks_all_but_last_four(self):
        assert mask_number("4111 1111 1111 1111") == "************1111"
        assert mask_number("378282246310005") == "***********0005"

    def test_short_and_non_numeric_input_fully_masked(self):
        assert mask_number("1234") == "****"
        assert mask_number("abcd1234") == "********"
        assert mask_number("") == ""


class TestCvv:
    @pytest.mark.parametrize(
        ("cvv", "brand", "expected"),
        [
            ("123", CardBrand.VISA, True),
            ("1234", CardBrand.VISA, False),
            ("1234", CardBrand.AMEX, True),
            ("123", CardBrand.AMEX, False),
            ("12a", CardBrand.VISA, False),
            ("", CardBrand.VISA, False),
            ("123", None, True),
            ("1234", None, True),
            ("12", None, False),
            ("12345", None, False),
            ("123", CardBrand.UNKNOWN, True),
        ],
    )
    def test_cvv(self, cvv, brand, expected):
        assert validate_cvv(cvv, brand) is expected


class TestExpiry:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("11/26", True),  # current month is still valid
            ("12/2026", True),
            ("01/27", True),
            ("1126", True),
            ("11-26", True),
            ("112026", True),
            ("10/26", False),  # last month
            ("12/2025", False),
            ("13/26", False),
            ("00/26", False),
            ("1/26", False),
            ("abc", False),
            ("", False),
            ("12/2046", True),  # exactly 20 years ahead
            ("12/2047", False),
        ],
    )
    def test_is_expiry_valid(self, text, expected):
        assert is_expiry_valid(text, today=TODAY) is expected

    def test_parse_expiry(self):
        assert parse_expiry("03/28") == (3, 2028)
        assert parse_expiry("03/2028") == (3, 2028)
        assert parse_expiry(" 0328 ") == (3, 2028)

    def test_parse_expiry_rejects_garbage(self):
        with pytest.raises(ValueError):
            parse_expiry("March 2028")


def test_clean_number():
    assert clean_number(" 4111-1111 1111\t1111 ") == "4111111111111111"
