import pytest

from app.billing import calculate_order
from app.order_models import OrderDraft


def test_calculates_multi_item_order_with_shared_tax():
    draft = OrderDraft.model_validate(
        {
            "language_code": "hi-IN",
            "currency": "INR",
            "lines": [
                {
                    "name": "अरहर दाल",
                    "name_evidence": "अरहर दाल",
                    "quantity": "10",
                    "quantity_evidence": "10 kg",
                    "unit": "kg",
                    "unit_evidence": "kg",
                    "pack_size": None,
                    "pack_size_evidence": None,
                    "unit_price": "135",
                    "unit_price_evidence": "135 रुपये किलो",
                    "price_basis": "unit",
                    "tax_rate_percent": None,
                    "tax_evidence": None,
                    "tax_inclusive": False,
                    "discount_kind": "none",
                    "discount_value": None,
                    "discount_evidence": None,
                    "free_quantity": "0",
                    "free_quantity_evidence": None,
                    "source_quote": "10 kg अरहर दाल 135 रुपये किलो",
                },
                {
                    "name": "refined oil",
                    "name_evidence": "refined oil",
                    "quantity": "5",
                    "quantity_evidence": "5 litre",
                    "unit": "litre",
                    "unit_evidence": "litre",
                    "pack_size": None,
                    "pack_size_evidence": None,
                    "unit_price": "125",
                    "unit_price_evidence": "125 रुपये litre",
                    "price_basis": "unit",
                    "tax_rate_percent": None,
                    "tax_evidence": None,
                    "tax_inclusive": False,
                    "discount_kind": "none",
                    "discount_value": None,
                    "discount_evidence": None,
                    "free_quantity": "0",
                    "free_quantity_evidence": None,
                    "source_quote": "5 litre refined oil 125 रुपये litre",
                },
                {
                    "name": "चाय पत्ती",
                    "name_evidence": "चाय पत्ती",
                    "quantity": "6",
                    "quantity_evidence": "6 packet",
                    "unit": "packet",
                    "unit_evidence": "packet",
                    "pack_size": None,
                    "pack_size_evidence": None,
                    "unit_price": "110",
                    "unit_price_evidence": "110 रुपये वाली",
                    "price_basis": "unit",
                    "tax_rate_percent": None,
                    "tax_evidence": None,
                    "tax_inclusive": False,
                    "discount_kind": "none",
                    "discount_value": None,
                    "discount_evidence": None,
                    "free_quantity": "0",
                    "free_quantity_evidence": None,
                    "source_quote": "6 packet चाय पत्ती 110 रुपये वाली",
                },
            ],
            "default_tax_rate_percent": "5",
            "tax_evidence": "सब पे 5% GST लगाओ",
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

    result = calculate_order(draft)

    assert result["subtotal"] == "2635.00"
    assert result["tax_amount"] == "131.75"
    assert result["gross_due"] == "2766.75"


def test_blocks_calculation_when_a_line_lacks_amount_evidence():
    draft = OrderDraft.model_validate(
        {
            "language_code": "hi-IN",
            "currency": "INR",
            "lines": [
                {
                    "name": "दाल",
                    "name_evidence": "दाल",
                    "quantity": "10",
                    "quantity_evidence": "10 kg",
                    "unit": "kg",
                    "unit_evidence": "kg",
                    "pack_size": None,
                    "pack_size_evidence": None,
                    "unit_price": "135",
                    "unit_price_evidence": None,
                    "price_basis": "unit",
                    "tax_rate_percent": None,
                    "tax_evidence": None,
                    "tax_inclusive": False,
                    "discount_kind": "none",
                    "discount_value": None,
                    "discount_evidence": None,
                    "free_quantity": "0",
                    "free_quantity_evidence": None,
                    "source_quote": "10 kg दाल 135 रुपये किलो",
                }
            ],
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

    try:
        calculate_order(draft, transcript="10 kg दाल")
    except ValueError as error:
        assert "evidence" in str(error).lower()
    else:
        raise AssertionError("calculation should reject an unsupported price")


def _draft_with_line(line, **overrides):
    data = {
        "language_code": "hi-IN",
        "currency": "INR",
        "lines": [line],
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
    data.update(overrides)
    return OrderDraft.model_validate(data)


def test_normalizes_numeric_quantity_when_model_repeats_its_unit():
    draft = _draft_with_line(
        {
            "name": "paneer",
            "name_evidence": "paneer",
            "quantity": "250 g",
            "quantity_evidence": "250 gram paneer",
            "unit": "g",
            "unit_evidence": "gram",
            "pack_size": "",
            "pack_size_evidence": None,
            "unit_price": None,
            "unit_price_evidence": None,
            "price_basis": "unit",
            "tax_rate_percent": None,
            "tax_evidence": None,
            "tax_inclusive": False,
            "discount_kind": "none",
            "discount_value": None,
            "discount_evidence": None,
            "free_quantity": "",
            "free_quantity_evidence": None,
            "source_quote": "250 gram paneer",
        }
    )

    assert draft.lines[0].quantity == "250"
    assert draft.lines[0].unit == "g"
    assert draft.lines[0].pack_size is None
    assert draft.lines[0].free_quantity == "0"
    with pytest.raises(ValueError, match="missing its quantity or price"):
        calculate_order(draft)


def test_discards_non_numeric_extractions_instead_of_forwarding_them_to_billing():
    draft = _draft_with_line(
        {
            "name": "rice",
            "name_evidence": "rice",
            "quantity": "Evidence: rice",
            "quantity_evidence": None,
            "unit": "kg",
            "unit_evidence": None,
            "pack_size": None,
            "pack_size_evidence": None,
            "unit_price": "not stated",
            "unit_price_evidence": None,
            "price_basis": "unit",
            "tax_rate_percent": None,
            "tax_evidence": None,
            "tax_inclusive": False,
            "discount_kind": "none",
            "discount_value": None,
            "discount_evidence": None,
            "free_quantity": 'Evidence: "rice"',
            "free_quantity_evidence": None,
            "source_quote": "rice",
        }
    )

    assert draft.lines[0].quantity is None
    assert draft.lines[0].unit_price is None
    assert draft.lines[0].free_quantity == "0"


def test_calculates_box_quantity_at_a_per_piece_price():
    draft = _draft_with_line(
        {
            "name": "Classmate notebooks",
            "name_evidence": "Classmate notebooks",
            "quantity": "15",
            "quantity_evidence": "15 box",
            "unit": "box",
            "unit_evidence": "box",
            "price_unit": "piece",
            "price_unit_evidence": "32 rupay per piece",
            "pack_size": "50 pieces per box",
            "pack_size_evidence": "50 piece in every box",
            "unit_price": "32",
            "unit_price_evidence": "32 rupay per piece",
            "price_basis": "unit",
            "tax_rate_percent": None,
            "tax_evidence": None,
            "tax_inclusive": False,
            "discount_kind": "none",
            "discount_value": None,
            "discount_evidence": None,
            "free_quantity": "0",
            "free_quantity_evidence": None,
            "source_quote": "15 box notebooks, 50 pieces per box, 32 rupay per piece",
        }
    )

    result = calculate_order(draft)

    assert result["subtotal"] == "24000.00"


def test_deducts_explicit_free_units_from_the_billable_quantity():
    draft = _draft_with_line(
        {
            "name": "soap",
            "name_evidence": "soap",
            "quantity": "50",
            "quantity_evidence": "50 soap",
            "unit": "piece",
            "unit_evidence": "soap",
            "pack_size": None,
            "pack_size_evidence": None,
            "unit_price": "10",
            "unit_price_evidence": "10 rupees per soap",
            "price_basis": "unit",
            "tax_rate_percent": None,
            "tax_evidence": None,
            "tax_inclusive": False,
            "discount_kind": "none",
            "discount_value": None,
            "discount_evidence": None,
            "free_quantity": "5",
            "free_quantity_evidence": "every 10 soap gets 1 free",
            "source_quote": "50 soap, 10 rupees each, every 10 soap gets 1 free",
        }
    )

    result = calculate_order(draft)

    assert result["subtotal"] == "450.00"
    assert result["lines"][0]["quantity"] == "50"
    assert result["lines"][0]["free_quantity"] == "5"


def test_calculates_tax_inclusive_line_price_after_line_and_order_discounts():
    line = {
        "name": "LG LED TV",
        "name_evidence": "LG LED TV",
        "quantity": "3",
        "quantity_evidence": "3 LG LED TV",
        "unit": "piece",
        "unit_evidence": "piece",
        "pack_size": "32 inch",
        "pack_size_evidence": "32 inch",
        "unit_price": "14500",
        "unit_price_evidence": "14,500 rupay piece",
        "price_basis": "unit",
        "tax_rate_percent": "18",
        "tax_evidence": "18% GST inclusive",
        "tax_inclusive": True,
        "discount_kind": "percent",
        "discount_value": "10",
        "discount_evidence": "10% trade discount",
        "free_quantity": "0",
        "free_quantity_evidence": None,
        "source_quote": "3 LG LED TV 32 inch 14,500 rupay piece, 10% trade discount, 18% GST inclusive",
    }
    draft = _draft_with_line(
        line,
        order_discount_kind="amount",
        order_discount_value="1500",
        order_discount_evidence="1500 rupay exchange discount",
    )

    result = calculate_order(draft)

    assert result["gross_due"] == "37380.00"
    assert result["subtotal"] == "31677.97"
    assert result["tax_amount"] == "5702.03"


def test_applies_free_quantity_without_charging_for_free_items():
    line = {
        "name": "Surf Excel soap",
        "name_evidence": "surf excel sabun",
        "quantity": "50",
        "quantity_evidence": "50 kahan",
        "unit": "piece",
        "unit_evidence": "pieces",
        "pack_size": None,
        "pack_size_evidence": None,
        "unit_price": "10",
        "unit_price_evidence": "10 rupay wala",
        "price_basis": "unit",
        "tax_rate_percent": "18",
        "tax_evidence": "18% GST",
        "tax_inclusive": False,
        "discount_kind": "none",
        "discount_value": None,
        "discount_evidence": None,
        "free_quantity": "5",
        "free_quantity_evidence": "har 10 sabun pe 1 sabun free",
        "source_quote": "50 kahan surf excel sabun 10 rupay wala, har 10 sabun pe 1 sabun free, 18% GST",
    }
    draft = _draft_with_line(line)

    result = calculate_order(draft)

    assert result["lines"][0]["free_quantity"] == "5"
    assert result["subtotal"] == "450.00"
    assert result["gross_due"] == "531.00"


def test_calculates_charge_return_previous_balance_payment_and_roundoff():
    line = {
        "name": "rice",
        "name_evidence": "rice",
        "quantity": "2",
        "quantity_evidence": "2 bag",
        "unit": "bag",
        "unit_evidence": "bag",
        "pack_size": None,
        "pack_size_evidence": None,
        "unit_price": "100",
        "unit_price_evidence": "100 rupees per bag",
        "price_basis": "unit",
        "tax_rate_percent": "5",
        "tax_evidence": "5% GST",
        "tax_inclusive": False,
        "discount_kind": "none",
        "discount_value": None,
        "discount_evidence": None,
        "free_quantity": "0",
        "free_quantity_evidence": None,
        "source_quote": "2 bag rice at 100 rupees per bag, 5% GST",
    }
    draft = _draft_with_line(
        line,
        charges=[
            {
                "name": "delivery",
                "amount": "50",
                "tax_rate_percent": "5",
                "tax_inclusive": False,
                "source_quote": "50 rupees delivery",
            }
        ],
        returns=[
            {
                "name": "damaged goods",
                "amount": "20",
                "tax_rate_percent": "5",
                "tax_inclusive": False,
                "source_quote": "20 rupees damaged goods return",
            }
        ],
        previous_balance="100",
        previous_balance_evidence="previous balance 100 rupees",
        payments=[
            {"method": "cash", "amount": "100", "source_quote": "100 rupees cash"}
        ],
        round_off=True,
        round_off_evidence="round off",
    )

    result = calculate_order(draft)

    assert result["subtotal"] == "230.00"
    assert result["tax_amount"] == "11.50"
    assert result["gross_due"] == "242.00"
    assert result["amount_due"] == "342.00"
    assert result["amount_paid"] == "100.00"
    assert result["balance_due"] == "242.00"
