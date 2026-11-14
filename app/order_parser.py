from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_ITEM_PATTERN = re.compile(
    r"^\s*(?P<quantity>\d+(?:\.\d+)?)\s*"
    r"(?:(?P<unit>kg|kgs|g|gram|grams|l|litre|litres|liter|liters|"
    r"packet|packets|piece|pieces|pcs)\s+)?"
    r"(?P<name>.+?)\s+(?:at|for|@)\s*"
    r"(?:₹|rs\.?\s*|rupees?\s*)?"
    r"(?P<price>\d+(?:\.\d{1,2})?)\s*(?:rupees?)?\s*$",
    re.IGNORECASE,
)


def _positive_number(value: str) -> str | None:
    if len(value) > 24:
        return None
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if (
        not number.is_finite()
        or number <= 0
        or number > Decimal(100000000)
        or number.as_tuple().exponent < -6
        or len(number.as_tuple().digits) > 14
    ):
        return None
    return format(number.normalize(), "f")


def parse_order_items(transcript: str) -> list[dict[str, str]]:
    if not isinstance(transcript, str) or len(transcript) > 4000:
        return []

    items: list[dict[str, str]] = []
    for segment in re.split(r",|\n|\s+and\s+", transcript, flags=re.IGNORECASE):
        segment = segment.strip().rstrip(".!?;")
        match = _ITEM_PATTERN.fullmatch(segment)
        if not match:
            continue
        quantity = _positive_number(match.group("quantity"))
        unit_price = _positive_number(match.group("price"))
        name = match.group("name").strip(" .;:-")
        if not quantity or not unit_price or not name or len(name) > 80:
            continue
        unit = match.group("unit")
        display_name = f"{name} ({unit})" if unit else name
        items.append(
            {"name": display_name, "quantity": quantity, "unit_price": unit_price}
        )
        if len(items) == 50:
            break
    return items
