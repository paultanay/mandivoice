import pytest

from app.order_models import OrderDraft
from app.order_parser import build_hindi_order_readback, build_hindi_readback


def _mixed_unit_order():
    lines = []
    for name, quantity, unit, price, price_unit, quote in (
        ("paneer", "250", "g", "50", "kg", "250 gram paneer at 50 rupees per kg"),
        (
            "brown bread",
            "1",
            "packet",
            "40",
            "packet",
            "one packet brown bread at 40 rupees per packet",
        ),
    ):
        lines.append(
            {
                "name": name,
                "name_evidence": name,
                "quantity": quantity,
                "quantity_evidence": quote,
                "unit": unit,
                "unit_evidence": unit,
                "price_unit": price_unit,
                "price_unit_evidence": quote,
                "pack_size": None,
                "pack_size_evidence": None,
                "unit_price": price,
                "unit_price_evidence": quote,
                "price_basis": "unit",
                "tax_rate_percent": None,
                "tax_evidence": None,
                "tax_inclusive": False,
                "discount_kind": "none",
                "discount_value": None,
                "discount_evidence": None,
                "free_quantity": "0",
                "free_quantity_evidence": None,
                "source_quote": quote,
            }
        )
    return OrderDraft.model_validate(
        {
            "language_code": "hi-IN",
            "currency": "INR",
            "lines": lines,
            "default_tax_rate_percent": None,
            "tax_evidence": None,
            "order_discount_kind": "none",
            "order_discount_value": None,
            "order_discount_after_tax": False,
            "order_discount_evidence": None,
            "charges": [],
            "returns": [],
            "previous_balance": None,
            "previous_balance_evidence": None,
            "payments": [],
            "round_off": False,
            "round_off_evidence": None,
            "customer_gstin": None,
            "customer_gstin_evidence": None,
            "clarifications": [],
            "unsupported_requests": [],
        }
    )


def test_builds_spoken_hindi_confirmation_from_parsed_order():
    text = build_hindi_readback(
        [{"name": "बासमती राइस (kg)", "quantity": "40", "unit_price": "56"}],
        gst_percent="5",
    )
    assert text == (
        "आपने चालीस किलो बासमती राइस, छप्पन रुपये प्रति किलो और पाँच प्रतिशत जीएसटी कहा है। "
        "कुल दो हजार तीन सौ बावन रुपये बनते हैं। क्या यह सही है?"
    )


def test_order_readback_uses_calculated_mixed_units_and_exact_bill_total():
    text = build_hindi_order_readback(_mixed_unit_order())

    assert "दो सौ पचास ग्राम paneer" in text
    assert "पचास रुपये प्रति किलो" in text
    assert "बारह रुपये पचास पैसे" in text
    assert "एक पैकेट brown bread" in text
    assert "कुल देय बावन रुपये पचास पैसे" in text


def test_readback_rejects_invalid_bill_values():
    with pytest.raises(ValueError):
        build_hindi_readback([], gst_percent="5")


def test_readback_speaks_currency_fraction_as_paise():
    text = build_hindi_readback(
        [{"name": "चावल (kg)", "quantity": "1", "unit_price": "56.10"}],
        gst_percent="0",
    )

    assert "छप्पन रुपये दस पैसे प्रति किलो" in text
    assert "छप्पन रुपये दस पैसे बनते हैं" in text


def test_readback_treats_pack_size_as_description_not_bill_unit():
    text = build_hindi_readback(
        [{"name": "10 ग्राम तेल (packet)", "quantity": "1", "unit_price": "20"}],
        gst_percent="0",
    )

    assert "एक पैकेट 10 ग्राम तेल" in text
    assert "बीस रुपये प्रति पैकेट" in text
