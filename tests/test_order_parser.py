import pytest

from app.order_parser import build_hindi_readback


def test_builds_spoken_hindi_confirmation_from_parsed_order():
    text = build_hindi_readback(
        [{"name": "बासमती राइस (kg)", "quantity": "40", "unit_price": "56"}],
        gst_percent="5",
    )

    assert text == (
        "आपने चालीस किलो बासमती राइस, छप्पन रुपये प्रति किलो और पाँच प्रतिशत जीएसटी कहा है। "
        "कुल दो हजार तीन सौ बावन रुपये बनते हैं। क्या यह सही है?"
    )


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
