import json
from pathlib import Path


def test_retail_benchmark_contains_unique_multilingual_cases():
    dataset = Path(__file__).parent.parent / "benchmarks" / "retail_orders.jsonl"
    cases = [
        json.loads(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [case["id"] for case in cases]

    assert len(cases) >= 20
    assert len(ids) == len(set(ids))
    assert {"bn", "gu", "kn", "ml", "mr", "pa", "ta", "te"}.issubset(
        {case["language"] for case in cases}
    )
    assert all(case["transcript"].strip() and "expect" in case for case in cases)
