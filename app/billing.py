import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.order_models import OrderDraft

_CENT = Decimal("0.01")
_MAX_ITEMS = 50
_MAX_AMOUNT = Decimal(100000000)
_UNIT_FACTORS = {
    "g": ("mass", Decimal(1)),
    "gram": ("mass", Decimal(1)),
    "grams": ("mass", Decimal(1)),
    "kg": ("mass", Decimal(1000)),
    "kilo": ("mass", Decimal(1000)),
    "kilos": ("mass", Decimal(1000)),
    "kilogram": ("mass", Decimal(1000)),
    "kilograms": ("mass", Decimal(1000)),
    "ml": ("volume", Decimal(1)),
    "milliliter": ("volume", Decimal(1)),
    "millilitre": ("volume", Decimal(1)),
    "l": ("volume", Decimal(1000)),
    "litre": ("volume", Decimal(1000)),
    "liter": ("volume", Decimal(1000)),
    "liters": ("volume", Decimal(1000)),
    "litres": ("volume", Decimal(1000)),
    "piece": ("count", Decimal(1)),
    "pieces": ("count", Decimal(1)),
    "pc": ("count", Decimal(1)),
    "pcs": ("count", Decimal(1)),
    "dozen": ("count", Decimal(12)),
}


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


def _nonnegative(value: Any, field: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{field} must be a valid number") from None
    if (
        not amount.is_finite()
        or amount < 0
        or amount > _MAX_AMOUNT
        or amount.as_tuple().exponent < -6
        or len(amount.as_tuple().digits) > 14
    ):
        raise ValueError(
            f"{field} must be zero or greater and within the supported range"
        )
    return amount


def _rate(value: Any, field: str = "Tax rate") -> Decimal:
    rate = _nonnegative(value, field)
    if rate > 100:
        raise ValueError(f"{field} must be between 0 and 100")
    return rate


def _evidence_is_present(quote: str | None, transcript: str) -> bool:
    if not quote or not quote.strip():
        return False
    normalized_quote = " ".join(quote.casefold().split())
    normalized_transcript = " ".join(transcript.casefold().split())
    return normalized_quote in normalized_transcript


def _require_evidence(quote: str | None, transcript: str, field: str) -> None:
    if not _evidence_is_present(quote, transcript):
        raise ValueError(f"Could not verify transcript evidence for {field}")


def _unit_factor(source: str, target: str) -> Decimal | None:
    if source.casefold().strip() == target.casefold().strip():
        return Decimal(1)
    source_unit = _UNIT_FACTORS.get(source.casefold().strip())
    target_unit = _UNIT_FACTORS.get(target.casefold().strip())
    if source_unit is None or target_unit is None or source_unit[0] != target_unit[0]:
        return None
    return source_unit[1] / target_unit[1]


def _pack_factor(
    pack_size: str | None, ordered_unit: str, price_unit: str
) -> Decimal | None:
    if not pack_size:
        return None
    match = re.fullmatch(
        r"\s*(\d+(?:\.\d+)?)\s*([A-Za-z]+)(?:\s+(?:per|/)\s*([A-Za-z]+))?\s*",
        pack_size,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    count, contained_unit, outer_unit = match.groups()
    if _unit_factor(contained_unit, price_unit) != Decimal(1):
        return None
    if outer_unit and _unit_factor(outer_unit, ordered_unit) != Decimal(1):
        return None
    try:
        return Decimal(count)
    except InvalidOperation:
        return None


def _adjustment_amount(amount: Decimal, kind: str, value: Any, field: str) -> Decimal:
    if kind == "none":
        return Decimal(0)
    if value is None:
        raise ValueError(f"{field} value is missing")
    adjustment = _nonnegative(value, field)
    if kind == "percent":
        if adjustment > 100:
            raise ValueError(f"{field} percentage must be between 0 and 100")
        return _money(amount * adjustment / Decimal(100))
    if adjustment > amount:
        raise ValueError(f"{field} cannot exceed its amount")
    return _money(adjustment)


def calculate_order(draft: OrderDraft, transcript: str | None = None) -> dict[str, Any]:
    if draft.clarifications:
        raise ValueError("Resolve the order questions before calculating")
    if not draft.lines:
        raise ValueError("Add at least one priced item")

    if transcript is not None:
        for index, line in enumerate(draft.lines, start=1):
            _require_evidence(line.name_evidence, transcript, f"item {index} name")
            if line.quantity is None or line.unit_price is None or not line.price_basis:
                raise ValueError(f"Item {index} is missing its quantity or price")
            _require_evidence(
                line.quantity_evidence, transcript, f"item {index} quantity"
            )
            if line.unit is not None:
                _require_evidence(line.unit_evidence, transcript, f"item {index} unit")
            if line.price_unit is not None:
                _require_evidence(
                    line.price_unit_evidence,
                    transcript,
                    f"item {index} price unit",
                )
            _require_evidence(
                line.unit_price_evidence, transcript, f"item {index} price"
            )
            _require_evidence(line.source_quote, transcript, f"item {index}")
            if line.tax_rate_percent is not None:
                _require_evidence(line.tax_evidence, transcript, f"item {index} tax")
            if line.tax_inclusive:
                _require_evidence(
                    line.tax_evidence or draft.tax_evidence,
                    transcript,
                    f"item {index} inclusive tax",
                )
            if line.pack_size is not None:
                _require_evidence(
                    line.pack_size_evidence, transcript, f"item {index} pack size"
                )
            if line.discount_kind != "none":
                _require_evidence(
                    line.discount_evidence, transcript, f"item {index} discount"
                )
            if _nonnegative(line.free_quantity, f"Item {index} free quantity") > 0:
                _require_evidence(
                    line.free_quantity_evidence,
                    transcript,
                    f"item {index} free quantity",
                )
        if draft.default_tax_rate_percent is not None:
            _require_evidence(draft.tax_evidence, transcript, "default tax")
        if draft.order_discount_kind != "none":
            _require_evidence(
                draft.order_discount_evidence, transcript, "order discount"
            )
        if draft.previous_balance is not None:
            _require_evidence(
                draft.previous_balance_evidence, transcript, "previous balance"
            )
        if draft.round_off:
            _require_evidence(draft.round_off_evidence, transcript, "round-off")
        for charge in draft.charges:
            _require_evidence(charge.source_quote, transcript, f"charge {charge.name}")
        for entry in draft.returns:
            _require_evidence(entry.source_quote, transcript, f"return {entry.name}")
        for payment in draft.payments:
            _require_evidence(
                payment.source_quote, transcript, f"payment {payment.method}"
            )

    line_results: list[dict[str, str]] = []
    taxable_values: list[Decimal] = []
    tax_values: list[Decimal] = []
    gross_values: list[Decimal] = []
    subtotal = Decimal(0)
    tax_amount = Decimal(0)

    for index, line in enumerate(draft.lines, start=1):
        if line.quantity is None or line.unit_price is None or not line.price_basis:
            raise ValueError(f"Item {index} is missing its quantity or price")
        quantity = _amount(line.quantity, f"Item {index} quantity")
        unit_price = _nonnegative(line.unit_price, f"Item {index} price")
        free_quantity = _nonnegative(line.free_quantity, f"Item {index} free quantity")
        if free_quantity > quantity:
            raise ValueError(
                f"Item {index} free quantity cannot exceed ordered quantity"
            )
        billable_quantity = quantity - free_quantity
        if line.price_basis == "line_total":
            if free_quantity:
                raise ValueError(
                    f"Item {index} needs a unit or pack price to account for free items"
                )
            amount = unit_price
        elif line.price_basis == "pack":
            amount = billable_quantity * unit_price
        else:
            ordered_unit = line.unit or "unit"
            price_unit = line.price_unit or ordered_unit
            factor = _unit_factor(ordered_unit, price_unit)
            if factor is None:
                factor = _pack_factor(line.pack_size, ordered_unit, price_unit)
            if factor is None:
                raise ValueError(
                    f"Item {index} price unit cannot be converted to its ordered unit"
                )
            amount = billable_quantity * factor * unit_price
        if amount > _MAX_AMOUNT:
            raise ValueError(f"Item {index} amount exceeds the supported range")
        rate = _rate(
            line.tax_rate_percent
            if line.tax_rate_percent is not None
            else (
                draft.default_tax_rate_percent
                if draft.default_tax_rate_percent is not None
                else "0"
            ),
            f"Item {index} tax rate",
        )
        if (
            line.tax_inclusive
            and line.tax_rate_percent is None
            and draft.default_tax_rate_percent is None
        ):
            raise ValueError(
                f"Item {index} needs an explicit tax rate for an inclusive price"
            )
        line_discount = _adjustment_amount(
            amount, line.discount_kind, line.discount_value, f"Item {index} discount"
        )
        if line.tax_inclusive:
            gross = _money(amount - line_discount)
            divisor = Decimal(1) + rate / Decimal(100)
            taxable = _money(gross / divisor)
            line_tax = gross - taxable
        else:
            taxable = _money(amount - line_discount)
            line_tax = _money(taxable * rate / Decimal(100))
            gross = taxable + line_tax
        if gross < 0:
            raise ValueError(f"Item {index} total cannot be negative")
        subtotal += taxable
        tax_amount += line_tax
        taxable_values.append(taxable)
        tax_values.append(line_tax)
        gross_values.append(gross)
        line_results.append(
            {
                "name": line.name,
                "quantity": format(quantity.normalize(), "f"),
                "free_quantity": format(free_quantity.normalize(), "f"),
                "unit": line.unit or "",
                "price_unit": line.price_unit or line.unit or "",
                "pack_size": line.pack_size or "",
                "unit_price": _format(unit_price),
                "tax_rate_percent": format(rate.normalize(), "f"),
                "taxable_amount": _format(taxable),
                "tax_amount": _format(line_tax),
                "total": _format(gross),
            }
        )

    pre_discount_gross = sum(gross_values, Decimal(0))
    pre_discount_taxable = sum(taxable_values, Decimal(0))
    order_discount = _adjustment_amount(
        pre_discount_gross if draft.order_discount_after_tax else pre_discount_taxable,
        draft.order_discount_kind,
        draft.order_discount_value,
        "Order discount",
    )
    if order_discount:
        weights = gross_values if draft.order_discount_after_tax else taxable_values
        weight_total = sum(weights, Decimal(0))
        if order_discount > weight_total:
            raise ValueError("Order discount cannot exceed the order amount")
        remaining = order_discount
        for index, weight in enumerate(weights):
            allocated = (
                remaining
                if index == len(weights) - 1
                else _money(order_discount * weight / weight_total)
            )
            remaining -= allocated
            if draft.order_discount_after_tax:
                gross_values[index] -= allocated
            else:
                rate = _rate(
                    draft.lines[index].tax_rate_percent
                    if draft.lines[index].tax_rate_percent is not None
                    else (
                        draft.default_tax_rate_percent
                        if draft.default_tax_rate_percent is not None
                        else "0"
                    )
                )
                taxable_values[index] -= allocated
                if draft.lines[index].tax_inclusive:
                    gross_values[index] -= _money(
                        allocated * (Decimal(1) + rate / Decimal(100))
                    )
                    tax_values[index] = gross_values[index] - taxable_values[index]
                else:
                    tax_values[index] = _money(
                        taxable_values[index] * rate / Decimal(100)
                    )
                    gross_values[index] = taxable_values[index] + tax_values[index]
        subtotal = sum(taxable_values, Decimal(0))
        tax_amount = sum(tax_values, Decimal(0))

        for index, result in enumerate(line_results):
            result["taxable_amount"] = _format(taxable_values[index])
            result["tax_amount"] = _format(tax_values[index])
            result["total"] = _format(gross_values[index])

    charge_total = Decimal(0)
    for charge in draft.charges:
        if charge.amount is None:
            raise ValueError(f"Charge {charge.name} is missing its amount")
        amount = _money(_nonnegative(charge.amount, f"Charge {charge.name}"))
        rate = _rate(
            charge.tax_rate_percent if charge.tax_rate_percent is not None else "0",
            f"Charge {charge.name} tax rate",
        )
        if charge.tax_inclusive and charge.tax_rate_percent is None:
            raise ValueError(
                f"Charge {charge.name} needs a tax rate for an inclusive amount"
            )
        if charge.tax_inclusive:
            base = _money(amount / (Decimal(1) + rate / Decimal(100)))
            charge_tax = amount - base
            charge_gross = amount
        else:
            base = amount
            charge_tax = _money(base * rate / Decimal(100))
            charge_gross = base + charge_tax
        subtotal += base
        tax_amount += charge_tax
        charge_total += charge_gross

    return_total = Decimal(0)
    for entry in draft.returns:
        if entry.amount is None:
            raise ValueError(f"Return {entry.name} is missing its amount")
        amount = _money(_nonnegative(entry.amount, f"Return {entry.name}"))
        rate = _rate(
            entry.tax_rate_percent if entry.tax_rate_percent is not None else "0",
            f"Return {entry.name} tax rate",
        )
        if entry.tax_inclusive and entry.tax_rate_percent is None:
            raise ValueError(
                f"Return {entry.name} needs a tax rate for an inclusive amount"
            )
        if entry.tax_inclusive:
            base = _money(amount / (Decimal(1) + rate / Decimal(100)))
            returned_tax = amount - base
            return_gross = amount
        else:
            base = amount
            returned_tax = _money(base * rate / Decimal(100))
            return_gross = base + returned_tax
        subtotal -= base
        tax_amount -= returned_tax
        return_total += return_gross

    subtotal = _money(subtotal)
    tax_amount = _money(tax_amount)
    gross_due = _money(sum(gross_values, Decimal(0)) + charge_total - return_total)
    if draft.round_off:
        rounded = gross_due.quantize(Decimal(1), rounding=ROUND_HALF_UP)
        round_off_amount = rounded - gross_due
        gross_due = rounded
    else:
        round_off_amount = Decimal(0)
    previous_balance = _money(
        _nonnegative(
            draft.previous_balance if draft.previous_balance is not None else "0",
            "Previous balance",
        )
    )
    amount_due = _money(gross_due + previous_balance)
    paid = Decimal(0)
    for payment in draft.payments:
        if payment.amount is None:
            raise ValueError(f"Payment {payment.method} is missing its amount")
        paid += _money(_nonnegative(payment.amount, f"Payment {payment.method}"))
    paid = _money(paid)
    balance_due = _money(amount_due - paid)
    return {
        "lines": line_results,
        "subtotal": _format(subtotal),
        "tax_amount": _format(tax_amount),
        "charges_total": _format(charge_total),
        "returns_total": _format(return_total),
        "order_discount": _format(order_discount),
        "round_off": _format(round_off_amount),
        "gross_due": _format(gross_due),
        "previous_balance": _format(previous_balance),
        "amount_due": _format(amount_due),
        "amount_paid": _format(paid),
        "balance_due": _format(balance_due),
        "customer_gstin": draft.customer_gstin,
    }
