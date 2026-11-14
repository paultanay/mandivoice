from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

_CENT = Decimal("0.01")
_MAX_ITEMS = 50
_MAX_AMOUNT = Decimal(100000000)


def _amount(value: Any, field: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a valid number") from None
    if (
        not amount.is_finite()
        or amount <= 0
        or amount > _MAX_AMOUNT
        or amount.as_tuple().exponent < -6
        or len(amount.as_tuple().digits) > 14
    ):
        raise ValueError(
            f"{field} must be greater than zero and within the supported range"
        )
    return amount


def _money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _format(value: Decimal) -> str:
    return f"{value:.2f}"


def calculate_bill(
    items: list[dict[str, Any]], gst_percent: Any = "0"
) -> dict[str, Any]:
    if not isinstance(items, list) or not items or len(items) > _MAX_ITEMS:
        raise ValueError("Add between 1 and 50 items")

    try:
        tax_rate = Decimal(str(gst_percent))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("GST must be a number between 0 and 100") from None
    if (
        not tax_rate.is_finite()
        or tax_rate < 0
        or tax_rate > 100
        or tax_rate.as_tuple().exponent < -6
        or len(tax_rate.as_tuple().digits) > 8
    ):
        raise ValueError("GST must be a number between 0 and 100")

    normalized: list[dict[str, str]] = []
    subtotal = Decimal(0)
    for item in items:
        if not isinstance(item, dict):
            raise TypeError("Each item must have a name, quantity, and unit price")
        name = str(item.get("name", "")).strip()
        if not name or len(name) > 80:
            raise ValueError("Item names must be between 1 and 80 characters")
        quantity = _amount(item.get("quantity"), "Quantity")
        unit_price = _amount(item.get("unit_price"), "Unit price")
        line_total = _money(quantity * unit_price)
        subtotal += line_total
        normalized.append(
            {
                "name": name,
                "quantity": format(quantity.normalize(), "f"),
                "unit_price": _format(unit_price),
                "line_total": _format(line_total),
            }
        )

    subtotal = _money(subtotal)
    gst_amount = _money(subtotal * tax_rate / Decimal(100))
    total = subtotal + gst_amount
    return {
        "items": normalized,
        "subtotal": _format(subtotal),
        "gst_percent": format(tax_rate.normalize(), "f"),
        "gst_amount": _format(gst_amount),
        "total": _format(total),
    }
