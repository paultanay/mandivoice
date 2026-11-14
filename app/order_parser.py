from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation

from app.billing import calculate_bill

_ITEM_PATTERN = re.compile(
    r"^\s*(?P<quantity>\d+(?:\.\d+)?)\s*"
    r"(?:(?P<unit>kg|kgs|g|gram|grams|l|litre|litres|liter|liters|"
    r"packet|packets|piece|pieces|pcs)\s+)?"
    r"(?P<name>.+?)\s+(?:at|for|@)\s*"
    r"(?:₹|rs\.?\s*|rupees?\s*)?"
    r"(?P<price>\d+(?:\.\d{1,2})?)\s*(?:rupees?)?\s*$",
    re.IGNORECASE,
)

_NUMBER_WORDS = {
    "zero": 0,
    "शून्य": 0,
    "वन": 1,
    "one": 1,
    "एक": 1,
    "टू": 2,
    "two": 2,
    "दो": 2,
    "थ्री": 3,
    "three": 3,
    "तीन": 3,
    "फोर": 4,
    "four": 4,
    "चार": 4,
    "फाइव": 5,
    "five": 5,
    "पांच": 5,
    "पाँच": 5,
    "सिक्स": 6,
    "six": 6,
    "छह": 6,
    "छः": 6,
    "सेवन": 7,
    "seven": 7,
    "सात": 7,
    "एट": 8,
    "eight": 8,
    "आठ": 8,
    "नाइन": 9,
    "nine": 9,
    "नौ": 9,
    "टेन": 10,
    "ten": 10,
    "दस": 10,
    "इलेवन": 11,
    "eleven": 11,
    "ग्यारह": 11,
    "ट्वेल्व": 12,
    "twelve": 12,
    "बारह": 12,
    "थर्टीन": 13,
    "thirteen": 13,
    "तेरह": 13,
    "फोर्टीन": 14,
    "fourteen": 14,
    "चौदह": 14,
    "फिफ्टीन": 15,
    "fifteen": 15,
    "पंद्रह": 15,
    "सोलह": 16,
    "sixteen": 16,
    "सत्रह": 17,
    "seventeen": 17,
    "अठारह": 18,
    "eighteen": 18,
    "उन्नीस": 19,
    "nineteen": 19,
    "बीस": 20,
    "twenty": 20,
    "ट्वेंटी": 20,
    "इक्कीस": 21,
    "बाईस": 22,
    "तेईस": 23,
    "चौबीस": 24,
    "पच्चीस": 25,
    "छब्बीस": 26,
    "सत्ताईस": 27,
    "अट्ठाईस": 28,
    "उनतीस": 29,
    "तीस": 30,
    "thirty": 30,
    "थर्टी": 30,
    "इकतीस": 31,
    "बत्तीस": 32,
    "तैंतीस": 33,
    "चौंतीस": 34,
    "पैंतीस": 35,
    "छत्तीस": 36,
    "सैंतीस": 37,
    "अड़तीस": 38,
    "अडतीस": 38,
    "उनतालीस": 39,
    "चालीस": 40,
    "forty": 40,
    "फोर्टी": 40,
    "इकतालीस": 41,
    "बयालीस": 42,
    "तैंतालीस": 43,
    "चवालीस": 44,
    "पैंतालीस": 45,
    "छियालीस": 46,
    "सैंतालीस": 47,
    "अड़तालीस": 48,
    "अडतालीस": 48,
    "उनचास": 49,
    "पचास": 50,
    "fifty": 50,
    "फिफ्टी": 50,
    "इक्यावन": 51,
    "बावन": 52,
    "तिरपन": 53,
    "चौवन": 54,
    "पचपन": 55,
    "छप्पन": 56,
    "सत्तावन": 57,
    "अट्ठावन": 58,
    "उनसठ": 59,
    "साठ": 60,
    "sixty": 60,
    "सिक्स्टी": 60,
    "इकसठ": 61,
    "बासठ": 62,
    "तिरसठ": 63,
    "चौंसठ": 64,
    "पैंसठ": 65,
    "छियासठ": 66,
    "सड़सठ": 67,
    "अड़सठ": 68,
    "अडसठ": 68,
    "उनहत्तर": 69,
    "सत्तर": 70,
    "seventy": 70,
    "सेवेंटी": 70,
    "इकहत्तर": 71,
    "बहत्तर": 72,
    "तिहत्तर": 73,
    "चौहत्तर": 74,
    "पचहत्तर": 75,
    "छिहत्तर": 76,
    "सतहत्तर": 77,
    "अठहत्तर": 78,
    "उन्नासी": 79,
    "अस्सी": 80,
    "eighty": 80,
    "एटी": 80,
    "इक्यासी": 81,
    "बयासी": 82,
    "तिरासी": 83,
    "चौरासी": 84,
    "पचासी": 85,
    "छियासी": 86,
    "सत्तासी": 87,
    "अट्ठासी": 88,
    "नवासी": 89,
    "नब्बे": 90,
    "ninety": 90,
    "नाइंटी": 90,
    "इक्यानवे": 91,
    "बानवे": 92,
    "तिरानवे": 93,
    "चौरानवे": 94,
    "पंचानवे": 95,
    "छियानवे": 96,
    "सत्तानवे": 97,
    "अट्ठानवे": 98,
    "निन्यानवे": 99,
    "सौ": 100,
    "hundred": 100,
}
_HINDI_NUMBERS = (
    "शून्य",
    "एक",
    "दो",
    "तीन",
    "चार",
    "पाँच",
    "छह",
    "सात",
    "आठ",
    "नौ",
    "दस",
    "ग्यारह",
    "बारह",
    "तेरह",
    "चौदह",
    "पंद्रह",
    "सोलह",
    "सत्रह",
    "अठारह",
    "उन्नीस",
    "बीस",
    "इक्कीस",
    "बाईस",
    "तेईस",
    "चौबीस",
    "पच्चीस",
    "छब्बीस",
    "सत्ताईस",
    "अट्ठाईस",
    "उनतीस",
    "तीस",
    "इकतीस",
    "बत्तीस",
    "तैंतीस",
    "चौंतीस",
    "पैंतीस",
    "छत्तीस",
    "सैंतीस",
    "अड़तीस",
    "उनतालीस",
    "चालीस",
    "इकतालीस",
    "बयालीस",
    "तैंतालीस",
    "चवालीस",
    "पैंतालीस",
    "छियालीस",
    "सैंतालीस",
    "अड़तालीस",
    "उनचास",
    "पचास",
    "इक्यावन",
    "बावन",
    "तिरपन",
    "चौवन",
    "पचपन",
    "छप्पन",
    "सत्तावन",
    "अट्ठावन",
    "उनसठ",
    "साठ",
    "इकसठ",
    "बासठ",
    "तिरसठ",
    "चौंसठ",
    "पैंसठ",
    "छियासठ",
    "सड़सठ",
    "अड़सठ",
    "उनहत्तर",
    "सत्तर",
    "इकहत्तर",
    "बहत्तर",
    "तिहत्तर",
    "चौहत्तर",
    "पचहत्तर",
    "छिहत्तर",
    "सतहत्तर",
    "अठहत्तर",
    "उन्नासी",
    "अस्सी",
    "इक्यासी",
    "बयासी",
    "तिरासी",
    "चौरासी",
    "पचासी",
    "छियासी",
    "सत्तासी",
    "अट्ठासी",
    "नवासी",
    "नब्बे",
    "इक्यानवे",
    "बानवे",
    "तिरानवे",
    "चौरानवे",
    "पंचानवे",
    "छियानवे",
    "सत्तानवे",
    "अट्ठानवे",
    "निन्यानवे",
)

_ONES = {1, 2, 3, 4, 5, 6, 7, 8, 9}
_CURRENCY = {"रुपये", "रुपया", "रूपये", "रूपया", "rupee", "rupees", "rs"}
_UNIT_WORDS = {"kg", "kgs", "किलो", "किलोग्राम", "kilo", "kilogram"}
_PERCENT_WORDS = {"percent", "परसेंट", "प्रतिशत", "%"}


def _normalize(transcript: str) -> list[str]:
    text = unicodedata.normalize("NFKC", transcript).lower().replace("़", "")
    text = text.replace("\u200c", " ").replace("\u200d", " ")
    return re.findall(r"\d+(?:\.\d+)?|[a-z]+|[\u0900-\u097f]+", text)


def _read_number(
    tokens: list[str], start: int, end: int | None = None
) -> tuple[Decimal | None, int]:
    limit = min(len(tokens), end if end is not None else len(tokens))
    if start >= limit:
        return None, start
    token = tokens[start]
    try:
        value = Decimal(token)
        if value.is_finite() and value >= 0 and value <= Decimal(100000000):
            return value, start + 1
    except InvalidOperation:
        pass

    value = _NUMBER_WORDS.get(token)
    if value is None:
        return None, start
    consumed = start + 1
    if value in {20, 30, 40, 50, 60, 70, 80, 90} and consumed < limit:
        tail = _NUMBER_WORDS.get(tokens[consumed])
        if tail in _ONES:
            value += tail
            consumed += 1
    return Decimal(value), consumed


def _unit_after(tokens: list[str], index: int) -> tuple[str | None, int]:
    if index + 1 < len(tokens) and tokens[index : index + 2] == ["के", "जी"]:
        return "kg", index + 2
    if index < len(tokens) and tokens[index] in {
        "केजी",
        "kg",
        "kgs",
        "किलो",
        "किलोग्राम",
        "kilo",
        "kilogram",
    }:
        return "kg", index + 1
    return None, index


def _price_markers(tokens: list[str]) -> list[tuple[int, Decimal]]:
    markers = []
    for marker, token in enumerate(tokens):
        if token not in _CURRENCY:
            continue
        price_unit = marker + 1
        if price_unit < len(tokens) and tokens[price_unit] in {"प्रति", "per"}:
            price_unit += 1
        if price_unit >= len(tokens) or tokens[price_unit] not in _UNIT_WORDS:
            continue
        for number_start in range(max(0, marker - 3), marker):
            value, consumed = _read_number(tokens, number_start, marker)
            if value is not None and value > 0 and consumed == marker:
                markers.append((number_start, value))
                break
    return markers


def _trim_order_action(tokens: list[str]) -> list[str]:
    suffixes = (
        ("दे", "दो"),
        ("दे", "दीजिए"),
        ("दे", "दीजिये"),
        ("देना",),
        ("चाहिए",),
    )
    cleaned = list(tokens)
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if len(cleaned) >= len(suffix) and tuple(cleaned[-len(suffix) :]) == suffix:
                del cleaned[-len(suffix) :]
                changed = True
                break
    return cleaned


def _parse_hindi_price_first(transcript: str) -> list[dict[str, str]]:
    """Parse explicit Hindi price-first orders and pack-size clauses.

    In counter speech, a price-per-unit often comes before the item, while its
    quantity follows the item: “चालीस रुपये किलो चावल, पच्चीस किलो”. Keep
    those roles tied to their markers instead of treating the first number as
    the quantity.
    """
    clauses = [
        _normalize(clause)
        for clause in re.split(r"[,;।.!?]+|\s+और\s+", transcript, flags=re.IGNORECASE)
    ]
    drafts: list[dict[str, str | None]] = []

    for tokens in clauses:
        if tokens and tokens[0] in {"भैया", "भाई", "सुनिए"}:
            tokens = tokens[1:]
        if not tokens:
            continue

        amount, after_amount = _read_number(tokens, 0)
        if amount is None or amount <= 0:
            continue

        # Price first: “40 रुपये किलो चावल दे दो”. The next bare quantity
        # clause belongs to this item until another item is introduced.
        if after_amount < len(tokens) and tokens[after_amount] in _CURRENCY:
            unit_index = after_amount + 1
            if unit_index < len(tokens) and tokens[unit_index] in {"प्रति", "per"}:
                unit_index += 1
            unit, name_start = _unit_after(tokens, unit_index)
            if unit and name_start < len(tokens):
                name_tokens = _trim_order_action(tokens[name_start:])
                name = " ".join(name_tokens).strip()
                if name:
                    drafts.append(
                        {
                            "name": f"{name} ({unit})",
                            "quantity": None,
                            "unit_price": _format_number(amount),
                            "kind": "price_first",
                        }
                    )
                    continue

        # Pack size: “10 ग्राम तेल की पैकेट”. This describes one pack; it is
        # not an order for ten separate grams or ten packs.
        if after_amount < len(tokens) and tokens[after_amount] in {
            "ग्राम",
            "g",
            "gram",
            "grams",
        }:
            name_tokens = _trim_order_action(tokens[after_amount + 1 :])
            if any(
                token in {"पैकेट", "पैकेट्स", "packet", "packets"} for token in name_tokens
            ):
                for suffix in (
                    ("की", "पैकेट"),
                    ("का", "पैकेट"),
                    ("के", "पैकेट"),
                    ("packet",),
                    ("packets",),
                ):
                    if (
                        len(name_tokens) >= len(suffix)
                        and tuple(name_tokens[-len(suffix) :]) == suffix
                    ):
                        name_tokens = name_tokens[: -len(suffix)]
                        break
                name = " ".join(name_tokens).strip()
                if not name:
                    continue
                drafts.append(
                    {
                        "name": f"{_format_number(amount)} ग्राम {name} (packet)",
                        "quantity": "1",
                        "unit_price": None,
                        "kind": "pack",
                    }
                )
                continue

        # A standalone quantity (“25 किलो”) completes the nearest price-first
        # item that does not yet have a quantity.
        unit, end = _unit_after(tokens, after_amount)
        if unit and end == len(tokens):
            pending = next(
                (
                    draft
                    for draft in reversed(drafts)
                    if draft["kind"] == "price_first" and draft["quantity"] is None
                ),
                None,
            )
            if pending is not None:
                pending["quantity"] = _format_number(amount)
                continue

        # A standalone amount (“20 रुपये”) supplies the price for the nearest
        # package whose size and product were already spoken.
        if after_amount == len(tokens) - 1 and tokens[-1] in _CURRENCY:
            pending = next(
                (
                    draft
                    for draft in reversed(drafts)
                    if draft["kind"] == "pack" and draft["unit_price"] is None
                ),
                None,
            )
            if pending is not None:
                pending["unit_price"] = _format_number(amount)
    items = [
        {
            "name": str(draft["name"]),
            "quantity": str(draft["quantity"]),
            "unit_price": str(draft["unit_price"]),
        }
        for draft in drafts
        if draft["name"] and draft["quantity"] and draft["unit_price"]
    ]
    return items


def _readback_items(transcript: str) -> list[dict[str, str]]:
    clauses = [
        _normalize(clause)
        for clause in re.split(
            r"[,;\n]+|\s+and\s+|\s+और\s+", transcript, flags=re.IGNORECASE
        )
    ]
    candidates = []
    prices = []
    action_words = {"बिल", "करो", "लगाओ", "bill", "karo", "add", "please"}

    for clause_index, tokens in enumerate(clauses):
        prices.extend((clause_index, price) for _, price in _price_markers(tokens))
        start = 1 if tokens and tokens[0] in {"भैया", "भाई", "सुनिए"} else 0
        quantity, after_quantity = _read_number(tokens, start)
        if quantity is None or quantity <= 0:
            continue
        unit_index = after_quantity
        if unit_index < len(tokens) and tokens[unit_index] in _CURRENCY:
            unit_index += 1
        unit, name_start = _unit_after(tokens, unit_index)
        if unit is None or name_start >= len(tokens):
            continue
        name_tokens = tokens[name_start:]
        if name_tokens[0] in action_words or name_tokens[0] in _PERCENT_WORDS:
            continue
        name = " ".join(name_tokens).strip(" ,.;:-")
        if name and len(name) <= 80:
            candidates.append((clause_index, name, quantity, unit))

    items = []
    used_prices: set[int] = set()
    for clause_index, name, quantity, unit in candidates:
        price_index = next(
            (
                index
                for index, (clause, _) in enumerate(prices)
                if index not in used_prices and clause >= clause_index
            ),
            None,
        )
        if price_index is None:
            continue
        price = prices[price_index][1]
        formatted_quantity = _format_number(quantity)
        formatted_price = _format_number(price)
        if not formatted_quantity or not formatted_price:
            continue
        used_prices.add(price_index)
        items.append(
            {
                "name": f"{name} ({unit})",
                "quantity": formatted_quantity,
                "unit_price": formatted_price,
            }
        )
        if len(items) == 50:
            break
    return items


def _format_number(value: Decimal) -> str | None:
    if not value.is_finite() or value <= 0 or value > Decimal(100000000):
        return None
    if value.as_tuple().exponent < -6 or len(value.as_tuple().digits) > 14:
        return None
    return format(value.normalize(), "f")


def _read_gst(tokens: list[str]) -> str | None:
    for marker, token in enumerate(tokens):
        if token not in _PERCENT_WORDS:
            continue
        for start in range(max(0, marker - 3), marker):
            value, consumed = _read_number(tokens, start, marker)
            if (
                value is not None
                and consumed == marker
                and Decimal(0) <= value <= Decimal(100)
            ):
                return _format_number(value) if value else "0"
    return None


def _parse_english_style(transcript: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for segment in re.split(r",|\n|\s+and\s+", transcript, flags=re.IGNORECASE):
        segment = segment.strip().rstrip(".!?;")
        match = _ITEM_PATTERN.fullmatch(segment)
        if not match:
            continue
        quantity = _format_number(Decimal(match.group("quantity")))
        unit_price = _format_number(Decimal(match.group("price")))
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


def parse_order(transcript: str) -> dict[str, object]:
    if not isinstance(transcript, str) or len(transcript) > 4000:
        return {"items": [], "gst_percent": None}

    tokens = _normalize(transcript)
    hindi_items = _parse_hindi_price_first(transcript)
    if hindi_items:
        return {"items": hindi_items, "gst_percent": _read_gst(tokens)}
    items = _readback_items(transcript)
    gst_percent = _read_gst(tokens)
    if items:
        return {"items": items, "gst_percent": gst_percent}
    return {"items": _parse_english_style(transcript), "gst_percent": gst_percent}


def parse_order_items(transcript: str) -> list[dict[str, str]]:
    return parse_order(transcript)["items"]


def _hindi_integer(value: int) -> str:
    if value < 100:
        return _HINDI_NUMBERS[value]
    for divisor, unit in (
        (10000000, "करोड़"),
        (100000, "लाख"),
        (1000, "हजार"),
        (100, "सौ"),
    ):
        if value >= divisor:
            quotient, remainder = divmod(value, divisor)
            suffix = f" {_hindi_integer(remainder)}" if remainder else ""
            return f"{_hindi_integer(quotient)} {unit}{suffix}"
    raise ValueError("Number is outside the supported range")


def _hindi_decimal(value: str) -> str:
    number = Decimal(value)
    if not number.is_finite() or number < 0 or number > Decimal(100000000):
        raise ValueError("Number is outside the supported range")
    normalized = format(number.normalize(), "f")
    whole, dot, fraction = normalized.partition(".")
    spoken = _hindi_integer(int(whole))
    if dot and fraction:
        spoken += " दशमलव " + " ".join(_HINDI_NUMBERS[int(digit)] for digit in fraction)
    return spoken


def _hindi_currency(value: str) -> str:
    number = Decimal(value).quantize(Decimal("0.01"))
    if not number.is_finite() or number < 0 or number > Decimal(100000000):
        raise ValueError("Currency value is outside the supported range")
    rupees = int(number)
    paise = int((number - rupees) * 100)
    spoken = f"{_hindi_integer(rupees)} रुपये"
    if paise:
        spoken += f" {_hindi_integer(paise)} पैसे"
    return spoken


def _hindi_unit(unit: str) -> str:
    return {
        "kg": "किलो",
        "kgs": "किलो",
        "kilo": "किलो",
        "kilogram": "किलो",
        "g": "ग्राम",
        "gram": "ग्राम",
        "grams": "ग्राम",
        "l": "लीटर",
        "litre": "लीटर",
        "litres": "लीटर",
        "liter": "लीटर",
        "liters": "लीटर",
        "packet": "पैकेट",
        "packets": "पैकेट",
        "पैकेट": "पैकेट",
        "पैकेट्स": "पैकेट",
        "piece": "नग",
        "pieces": "नग",
        "pcs": "नग",
    }.get(unit.lower(), unit)


def build_hindi_readback(items: list[dict[str, str]], gst_percent: str = "0") -> str:
    bill = calculate_bill(items, gst_percent=gst_percent)
    descriptions = []
    for item in bill["items"]:
        match = re.search(r"\s+\(([^()]*)\)$", item["name"])
        unit = _hindi_unit(match.group(1)) if match else "आइटम"
        name = item["name"][: match.start()].strip() if match else item["name"]
        quantity = _hindi_decimal(item["quantity"])
        price = _hindi_currency(item["unit_price"])
        descriptions.append(f"{quantity} {unit} {name}, {price} प्रति {unit}")
    order = " और ".join(descriptions)
    gst = _hindi_decimal(bill["gst_percent"])
    total = _hindi_currency(bill["total"])
    return f"आपने {order} और {gst} प्रतिशत जीएसटी कहा है। कुल {total} बनते हैं। क्या यह सही है?"
