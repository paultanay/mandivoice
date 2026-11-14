import pytest

from app.billing import calculate_bill


def test_calculates_subtotal_tax_and_total_without_float_rounding():
    bill = calculate_bill(
        [{"name": "Rice", "quantity": "1.5", "unit_price": "60.10"}],
        gst_percent="5",
    )

    assert bill == {
        "items": [
            {
                "name": "Rice",
                "quantity": "1.5",
                "unit_price": "60.10",
                "line_total": "90.15",
            }
        ],
        "subtotal": "90.15",
        "gst_percent": "5",
        "gst_amount": "4.51",
        "total": "94.66",
    }


@pytest.mark.parametrize(
    "items,gst_percent",
    [
        ([{"name": "", "quantity": "1", "unit_price": "2"}], "0"),
        ([{"name": "Rice", "quantity": "0", "unit_price": "2"}], "0"),
        ([{"name": "Rice", "quantity": "-1", "unit_price": "2"}], "0"),
        ([{"name": "Rice", "quantity": "1", "unit_price": "-2"}], "0"),
        ([{"name": "Rice", "quantity": "NaN", "unit_price": "2"}], "0"),
        ([{"name": "Rice", "quantity": "1", "unit_price": "2"}], "101"),
        ([], "0"),
    ],
)
def test_rejects_invalid_bill_values(items, gst_percent):
    with pytest.raises(ValueError):
        calculate_bill(items, gst_percent=gst_percent)


def test_rejects_extreme_decimal_precision_without_crashing():
    with pytest.raises(ValueError):
        calculate_bill([{"name": "Rice", "quantity": "1e-1000000", "unit_price": "2"}])
    with pytest.raises(ValueError):
        calculate_bill([{"name": "Rice", "quantity": "1", "unit_price": "1.123456789"}])
    with pytest.raises(ValueError):
        calculate_bill(
            [{"name": "Rice", "quantity": "1", "unit_price": "2"}],
            gst_percent="1e-1000000",
        )
