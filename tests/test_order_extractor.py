import asyncio
import json

import httpx
import pytest

from app.order_extractor import OrderExtractionError, _strict_schema, extract_order

ORDER_TRANSCRIPT = "दस किलो दाल, एक सौ पैंतीस रुपये किलो, पाँच प्रतिशत GST"


def test_groq_schema_uses_strict_supported_shape():
    schema = _strict_schema()
    unsupported = {"minLength", "maxLength", "minItems", "maxItems", "const"}

    def inspect(value):
        if isinstance(value, dict):
            assert not unsupported.intersection(value)
            if value.get("type") == "object":
                assert value["additionalProperties"] is False
                assert set(value["properties"]) == set(value["required"])
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)

    inspect(schema)
    assert schema["properties"]["currency"]["enum"] == ["INR"]


def _response_body():
    return {
        "language_code": "hi-IN",
        "currency": "INR",
        "lines": [
            {
                "name": "दाल",
                "name_evidence": "दाल",
                "quantity": "10",
                "quantity_evidence": "दस किलो",
                "unit": "kg",
                "unit_evidence": "किलो",
                "pack_size": None,
                "pack_size_evidence": None,
                "unit_price": "135",
                "unit_price_evidence": "एक सौ पैंतीस रुपये किलो",
                "price_basis": "unit",
                "tax_rate_percent": None,
                "tax_evidence": None,
                "tax_inclusive": False,
                "discount_kind": "none",
                "discount_value": None,
                "discount_evidence": None,
                "free_quantity": "0",
                "free_quantity_evidence": None,
                "source_quote": "दस किलो दाल, एक सौ पैंतीस रुपये किलो",
            }
        ],
        "default_tax_rate_percent": "5",
        "tax_evidence": "पाँच प्रतिशत GST",
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
    }


def test_sends_transcript_to_groq_with_strict_order_schema(monkeypatch):
    observed = {}

    async def handler(request):
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers.get("Authorization")
        observed["body"] = json.loads(await request.aread())
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(_response_body(), ensure_ascii=False)
                        }
                    }
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.order_extractor.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    draft = asyncio.run(extract_order(ORDER_TRANSCRIPT, "groq-test-key", "test-model"))

    assert observed["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert observed["authorization"] == "Bearer groq-test-key"
    assert observed["body"]["model"] == "test-model"
    assert observed["body"]["response_format"]["json_schema"]["strict"] is True
    assert ORDER_TRANSCRIPT in json.dumps(observed["body"], ensure_ascii=False)
    assert draft.lines[0].unit_price == "135"


def test_rejects_groq_error_without_echoing_response_body(monkeypatch):
    async def handler(request):
        return httpx.Response(401, text="secret diagnostic payload")

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.order_extractor.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    with pytest.raises(OrderExtractionError) as error:
        asyncio.run(extract_order(ORDER_TRANSCRIPT, "groq-test-key", "test-model"))

    assert "secret diagnostic payload" not in str(error.value)


def test_rejects_malformed_model_output(monkeypatch):
    async def handler(request):
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"lines":['}}]}
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.order_extractor.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    with pytest.raises(OrderExtractionError):
        asyncio.run(extract_order(ORDER_TRANSCRIPT, "groq-test-key", "test-model"))
