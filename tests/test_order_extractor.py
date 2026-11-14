import asyncio
import json

import httpx
import pytest

from app.billing import calculate_order
from app.order_extractor import (
    _SYSTEM_PROMPT,
    OrderExtractionError,
    _strict_schema,
    extract_order,
)

ORDER_TRANSCRIPT = "दस किलो दाल, एक सौ पैंतीस रुपये किलो, पाँच प्रतिशत GST"


def test_extraction_prompt_keeps_complete_items_when_another_item_needs_clarification():
    prompt = " ".join(_SYSTEM_PROMPT.casefold().split())
    assert "include every distinct requested item" in prompt
    assert "do not ask about details that are explicitly stated" in prompt
    assert "do not include items whose required details are already stated" not in (
        prompt
    )


def test_groq_schema_uses_strict_supported_shape():
    schema = _strict_schema()
    unsupported = {"minLength", "maxLength", "minItems", "maxItems", "const", "default"}

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
        "unsupported_requests": [],
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


def test_explains_groq_bad_request_without_exposing_credentials(monkeypatch):
    async def handler(request):
        return httpx.Response(
            400,
            json={"error": {"message": "Schema rejected for credential secret-key"}},
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.order_extractor.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    with pytest.raises(OrderExtractionError) as error:
        asyncio.run(extract_order(ORDER_TRANSCRIPT, "secret-key", "test-model"))

    assert "HTTP 400" in str(error.value)
    assert "Schema rejected" in str(error.value)
    assert "secret-key" not in str(error.value)


def test_retries_once_after_groq_rate_limit(monkeypatch):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
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

    assert draft.lines[0].unit_price == "135"
    assert calls == 2


def test_rate_limit_error_shows_retry_delay(monkeypatch):
    async def skip_wait(_seconds):
        return None

    monkeypatch.setattr("app.order_extractor.asyncio.sleep", skip_wait)

    async def handler(request):
        return httpx.Response(429, headers={"Retry-After": "40"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.order_extractor.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    with pytest.raises(OrderExtractionError) as error:
        asyncio.run(extract_order(ORDER_TRANSCRIPT, "groq-test-key", "test-model"))

    assert "rate limited" in str(error.value).lower()
    assert "40 seconds" in str(error.value)


@pytest.mark.parametrize(
    "provider_message",
    [
        "Failed to generate JSON. Please adjust your prompt.",
        "Generated JSON does not match the expected schema.",
    ],
)
def test_retries_transient_strict_json_generation_failure(
    monkeypatch, provider_message
):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": provider_message,
                        "failed_generation": "{",
                    }
                },
            )
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

    assert draft.lines[0].unit_price == "135"
    assert calls == 2


def test_falls_back_to_validated_json_mode_after_strict_generation_retries(monkeypatch):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        body = json.loads(await request.aread())
        if calls <= 2:
            assert body["response_format"]["type"] == "json_schema"
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "Failed to generate JSON. Please adjust your prompt."
                    }
                },
            )
        assert body["response_format"]["type"] == "json_object"
        assert "JSON Schema" in body["messages"][0]["content"]
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

    assert draft.lines[0].unit_price == "135"
    assert calls == 3


def test_rate_limit_retry_preserves_json_mode_fallback(monkeypatch):
    calls = 0

    async def skip_wait(_seconds):
        return None

    monkeypatch.setattr("app.order_extractor.asyncio.sleep", skip_wait)

    async def handler(request):
        nonlocal calls
        calls += 1
        body = json.loads(await request.aread())
        if calls <= 2:
            return httpx.Response(
                400,
                json={"error": {"message": "Failed to generate JSON."}},
            )
        if calls == 3:
            assert body["response_format"]["type"] == "json_object"
            return httpx.Response(429, headers={"Retry-After": "0"})
        assert body["response_format"]["type"] == "json_object"
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

    assert draft.lines[0].unit_price == "135"
    assert calls == 4


def test_drops_model_lines_without_verbatim_item_evidence(monkeypatch):
    body = _response_body()
    body["lines"][0].update(
        {
            "name": "E",
            "name_evidence": "E",
            "quantity_evidence": "E",
            "unit_price_evidence": "E",
            "source_quote": "E",
        }
    )

    async def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(body, ensure_ascii=False)}}
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

    assert draft.lines == []
    assert any("couldn't verify" in item.casefold() for item in draft.clarifications)


def test_adds_missing_price_question_and_discards_unpriced_price_basis(monkeypatch):
    body = _response_body()
    body["lines"][0].update(
        {
            "name": "paneer",
            "name_evidence": "paneer",
            "quantity": "250",
            "quantity_evidence": "250 gram",
            "unit": "g",
            "unit_evidence": "gram",
            "price_unit": "g",
            "price_unit_evidence": "250 gram",
            "unit_price": None,
            "unit_price_evidence": None,
            "price_basis": "unit",
            "source_quote": "250 gram paneer",
        }
    )
    body["lines"] = [body["lines"][0]]
    body["default_tax_rate_percent"] = None
    body["tax_evidence"] = None

    async def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(body, ensure_ascii=False)}}
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.order_extractor.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    draft = asyncio.run(extract_order("250 gram paneer", "groq-test-key", "test-model"))

    assert len(draft.clarifications) == 1
    assert "paneer" in draft.clarifications[0].casefold()
    assert "price" in draft.clarifications[0].casefold()
    assert draft.lines[0].price_unit is None
    assert draft.lines[0].price_basis is None


def test_adds_each_missing_detail_even_when_another_question_names_the_item(
    monkeypatch,
):
    body = _response_body()
    body["lines"][0].update(
        {
            "name": "paneer",
            "name_evidence": "paneer",
            "quantity": None,
            "quantity_evidence": None,
            "unit": "g",
            "unit_evidence": "gram",
            "unit_price": None,
            "unit_price_evidence": None,
            "price_basis": "unit",
            "source_quote": "paneer",
        }
    )
    body["lines"][0]["price_unit"] = None
    body["lines"][0]["price_unit_evidence"] = None
    body["lines"] = [body["lines"][0]]
    body["default_tax_rate_percent"] = None
    body["tax_evidence"] = None
    body["clarifications"] = ["What price should I use for paneer?"]

    async def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(body, ensure_ascii=False)}}
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.order_extractor.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    draft = asyncio.run(extract_order("paneer", "groq-test-key", "test-model"))

    assert len(draft.clarifications) == 2
    assert any("quantity" in item.casefold() for item in draft.clarifications)
    assert sum("price" in item.casefold() for item in draft.clarifications) == 1


def test_recovers_numeric_tax_from_verbatim_multilingual_evidence(monkeypatch):
    body = _response_body()
    body["default_tax_rate_percent"] = None
    body["tax_evidence"] = "કુલ પર 5 ટકા GST ઉમેરો"
    body["lines"] = [body["lines"][0].copy(), body["lines"][0].copy()]
    body["lines"][0]["name"] = "ચોખા"
    body["lines"][0]["name_evidence"] = "ચોખા"
    body["lines"][0]["quantity"] = "2"
    body["lines"][0]["unit_price"] = "60"
    body["lines"][0]["quantity_evidence"] = "બે કિલો"
    body["lines"][0]["unit_evidence"] = "કિલો"
    body["lines"][0]["unit_price_evidence"] = "60 રૂપિયા કિલો"
    body["lines"][0]["price_unit"] = "kg"
    body["lines"][0]["price_unit_evidence"] = "60 રૂપિયા કિલો"
    body["lines"][0]["source_quote"] = "બે કિલો ચોખા 60 રૂપિયા કિલો"
    body["lines"][1]["name"] = "દાળ"
    body["lines"][1]["name_evidence"] = "દાળ"
    body["lines"][1]["quantity"] = "5"
    body["lines"][1]["unit_price"] = "120"
    body["lines"][1]["quantity_evidence"] = "પાંચ કિલો"
    body["lines"][1]["unit_evidence"] = "કિલો"
    body["lines"][1]["unit_price_evidence"] = "120 રૂપિયા કિલો"
    body["lines"][1]["price_unit"] = "kg"
    body["lines"][1]["price_unit_evidence"] = "120 રૂપિયા કિલો"
    body["lines"][1]["source_quote"] = "પાંચ કિલો દાળ 120 રૂપિયા કિલો"
    transcript = (
        "બે કિલો ચોખા 60 રૂપિયા કિલો અને પાંચ કિલો દાળ 120 રૂપિયા કિલો. "
        "કુલ પર 5 ટકા GST ઉમેરો."
    )

    async def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(body, ensure_ascii=False)}}
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.order_extractor.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    draft = asyncio.run(extract_order(transcript, "groq-test-key", "test-model"))

    assert draft.default_tax_rate_percent == "5"
    assert calculate_order(draft, transcript=transcript)["gross_due"] == "756.00"


def test_applies_spoken_gst_to_the_referenced_item(monkeypatch):
    body = _response_body()
    body["default_tax_rate_percent"] = None
    body["tax_evidence"] = None
    line = body["lines"][0]
    line.update(
        {
            "name": "Basmati Rice",
            "name_evidence": "बासमती राइस",
            "quantity": "5",
            "quantity_evidence": "पाँच के जी",
            "unit": "kg",
            "unit_evidence": "के जी",
            "price_unit": "kg",
            "price_unit_evidence": "रुपये किलो",
            "unit_price": "150",
            "unit_price_evidence": "एक सौ पचास रुपये किलो",
            "source_quote": "बासमती राइस दे दो पाँच के जी, वो जो एक सौ पचास रुपये किलो करके है",
        }
    )
    transcript = (
        "बासमती राइस दे दो पाँच के जी, वो जो एक सौ पचास रुपये किलो करके है "
        "और उस पर फाइव परसेंट जी एस टी भी लगाना, ठीक है?"
    )

    async def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(body, ensure_ascii=False)}}
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.order_extractor.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    draft = asyncio.run(extract_order(transcript, "groq-test-key", "test-model"))

    assert draft.default_tax_rate_percent is None
    assert draft.lines[0].tax_rate_percent == "5"
    assert calculate_order(draft, transcript=transcript)["gross_due"] == "787.50"


def test_does_not_treat_a_discount_rate_as_a_gst_rate(monkeypatch):
    body = _response_body()
    body["default_tax_rate_percent"] = None
    body["tax_evidence"] = None
    transcript = "दस किलो दाल, एक सौ पैंतीस रुपये किलो, 5% discount, GST लगाना."

    async def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(body, ensure_ascii=False)}}
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        "app.order_extractor.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    draft = asyncio.run(extract_order(transcript, "groq-test-key", "test-model"))

    assert draft.default_tax_rate_percent is None
    assert draft.lines[0].tax_rate_percent is None


def test_asks_for_tax_rate_when_tax_was_requested_but_rate_is_missing(monkeypatch):
    body = _response_body()
    body["default_tax_rate_percent"] = None
    body["tax_evidence"] = "GST lagao"

    async def handler(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(body, ensure_ascii=False)}}
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

    assert len(draft.clarifications) == 1
    assert "gst" in draft.clarifications[0].casefold()
    assert "rate" in draft.clarifications[0].casefold()


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
