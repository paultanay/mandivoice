from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_NUMERIC_FIELDS = {
    "quantity",
    "unit_price",
    "tax_rate_percent",
    "discount_value",
    "free_quantity",
    "amount",
    "default_tax_rate_percent",
    "order_discount_value",
    "previous_balance",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def normalize_extracted_values(cls, values):
        if not isinstance(values, dict):
            return values
        values = values.copy()
        unit = values.get("unit")
        for key in _NUMERIC_FIELDS.intersection(values):
            value = values[key]
            if key == "free_quantity" and value in (None, ""):
                values[key] = "0"
                continue
            if value is None:
                continue
            text = str(value).strip().replace("₹", "").replace(",", "")
            if key == "quantity" and unit:
                match = re.fullmatch(
                    rf"([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s+{re.escape(str(unit))}",
                    text,
                    flags=re.IGNORECASE,
                )
                if match:
                    text = match.group(1)
            if text and not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)", text):
                if key == "free_quantity" and not values.get("free_quantity_evidence"):
                    values[key] = "0"
                else:
                    values[key] = None
            else:
                values[key] = text or None
        if isinstance(values.get("pack_size"), str) and not values["pack_size"].strip():
            values["pack_size"] = None
        for key in ("unit", "price_unit"):
            if isinstance(values.get(key), str) and not values[key].strip():
                values[key] = None
        return values


AdjustmentKind = Literal["none", "percent", "amount"]


class OrderLine(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    name_evidence: str
    quantity: str | None
    quantity_evidence: str | None
    unit: str | None
    unit_evidence: str | None
    price_unit: str | None = None
    price_unit_evidence: str | None = None
    pack_size: str | None
    pack_size_evidence: str | None
    unit_price: str | None
    unit_price_evidence: str | None
    price_basis: Literal["unit", "pack", "line_total"] | None
    tax_rate_percent: str | None
    tax_evidence: str | None
    tax_inclusive: bool
    discount_kind: AdjustmentKind
    discount_value: str | None
    discount_evidence: str | None
    free_quantity: str
    free_quantity_evidence: str | None
    source_quote: str


class Charge(StrictModel):
    name: str
    amount: str | None
    tax_rate_percent: str | None
    tax_inclusive: bool
    source_quote: str


class ReturnEntry(StrictModel):
    name: str
    amount: str | None
    tax_rate_percent: str | None
    tax_inclusive: bool
    source_quote: str


class Payment(StrictModel):
    method: str
    amount: str | None
    source_quote: str


class OrderDraft(StrictModel):
    language_code: str | None
    currency: Literal["INR"]
    lines: list[OrderLine] = Field(max_length=50)
    default_tax_rate_percent: str | None
    tax_evidence: str | None
    order_discount_kind: AdjustmentKind
    order_discount_value: str | None
    order_discount_after_tax: bool
    order_discount_evidence: str | None
    charges: list[Charge] = Field(max_length=20)
    returns: list[ReturnEntry] = Field(max_length=20)
    previous_balance: str | None
    previous_balance_evidence: str | None
    payments: list[Payment] = Field(max_length=20)
    round_off: bool
    round_off_evidence: str | None
    customer_gstin: str | None
    customer_gstin_evidence: str | None
    clarifications: list[str] = Field(max_length=30)
    unsupported_requests: list[str] = Field(max_length=20)
