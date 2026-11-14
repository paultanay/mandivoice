from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.billing import calculate_order
from app.order_extractor import OrderExtractionError, extract_order
from app.order_models import OrderDraft

DATASET = ROOT / "benchmarks" / "retail_orders.jsonl"
UNIT_ALIASES = {
    "kilo": "kg",
    "kilos": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "gram": "g",
    "grams": "g",
    "liter": "litre",
    "liters": "litre",
    "litres": "litre",
    "piece": "pieces",
    "pc": "pieces",
    "pcs": "pieces",
    "packets": "packet",
    "boxes": "box",
}


def canonical_unit(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.casefold().split())
    return UNIT_ALIASES.get(normalized, normalized)


def same_number(actual: str | None, expected: str | None) -> bool:
    if actual is None or expected is None:
        return actual == expected
    try:
        return Decimal(actual) == Decimal(expected)
    except InvalidOperation:
        return actual == expected


def evaluate(draft: OrderDraft, transcript: str, expected: dict) -> list[str]:
    problems = []
    lines = draft.lines
    if "line_count" in expected and len(lines) != expected["line_count"]:
        problems.append(f"expected {expected['line_count']} lines, got {len(lines)}")

    for index, check in enumerate(expected.get("lines", [])):
        if "name_contains" in check:
            needle = check["name_contains"].casefold()
            line = next(
                (item for item in lines if needle in item.name.casefold()), None
            )
        else:
            line = lines[index] if index < len(lines) else None
        if line is None:
            problems.append(f"line {index + 1} not found: {check}")
            continue
        for field in ("quantity", "unit_price", "price_unit"):
            if field in check and not same_number(getattr(line, field), check[field]):
                problems.append(
                    f"{line.name}.{field}: expected {check[field]!r}, got {getattr(line, field)!r}"
                )
        if "unit" in check and canonical_unit(line.unit) != canonical_unit(
            check["unit"]
        ):
            problems.append(
                f"{line.name}.unit: expected {check['unit']!r}, got {line.unit!r}"
            )
        if (
            "pack_size" in check
            and (line.pack_size or "").casefold() != check["pack_size"].casefold()
        ):
            problems.append(
                f"{line.name}.pack_size: expected {check['pack_size']!r}, got {line.pack_size!r}"
            )

    if "default_tax_rate_percent" in expected and not same_number(
        draft.default_tax_rate_percent, expected["default_tax_rate_percent"]
    ):
        problems.append(
            "default_tax_rate_percent: "
            f"expected {expected['default_tax_rate_percent']!r}, "
            f"got {draft.default_tax_rate_percent!r}"
        )
    if "round_off" in expected and draft.round_off != expected["round_off"]:
        problems.append(
            f"round_off: expected {expected['round_off']}, got {draft.round_off}"
        )

    clarifications = " ".join(draft.clarifications).casefold()
    for phrase in expected.get("clarification_contains", []):
        if phrase.casefold() not in clarifications:
            problems.append(f"clarification did not mention {phrase!r}")
    for phrase in expected.get("clarification_excludes", []):
        if phrase.casefold() in clarifications:
            problems.append(f"clarification unnecessarily asked about {phrase!r}")
    unsupported = " ".join(draft.unsupported_requests).casefold()
    for phrase in expected.get("unsupported_contains", []):
        if phrase.casefold() not in unsupported:
            problems.append(f"unsupported request was not reported: {phrase!r}")

    total = None
    if not draft.clarifications:
        try:
            total = calculate_order(draft, transcript=transcript)["gross_due"]
        except ValueError:
            pass
    if "total" in expected and total != expected["total"]:
        problems.append(f"total: expected {expected['total']!r}, got {total!r}")
    return problems


async def run(cases: list[dict], key: str, model: str) -> int:
    passed = 0
    for case in cases:
        try:
            draft = await extract_order(case["transcript"], key, model)
            problems = evaluate(draft, case["transcript"], case.get("expect", {}))
        except (OrderExtractionError, KeyError, ValueError) as error:
            problems = [str(error)]
            draft = None
        if problems:
            print(f"FAIL {case['id']}: " + "; ".join(problems))
            if draft is not None:
                print(
                    "  draft:",
                    json.dumps(
                        draft.model_dump(), ensure_ascii=False, separators=(",", ":")
                    ),
                )
        else:
            print(f"PASS {case['id']}")
            passed += 1
    print(f"\n{passed}/{len(cases)} cases passed")
    return 0 if passed == len(cases) else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the retail transcript benchmark against Groq."
    )
    parser.add_argument(
        "--id", action="append", help="Run only this case ID; repeat to select several."
    )
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        parser.error("GROQ_API_KEY is not set in .env")
    cases = [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if args.id:
        wanted = set(args.id)
        cases = [case for case in cases if case["id"] in wanted]
        missing = wanted - {case["id"] for case in cases}
        if missing:
            parser.error(f"Unknown case IDs: {', '.join(sorted(missing))}")
    if not cases:
        parser.error("No benchmark cases selected")
    model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b").strip()
    print(
        f"Running {len(cases)} cases with {model}; rate-limit retries may pause between calls."
    )
    return asyncio.run(run(cases, key, model))


if __name__ == "__main__":
    raise SystemExit(main())
