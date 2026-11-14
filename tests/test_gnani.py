import asyncio

import httpx
import pytest

from app import gnani


def test_sends_prisma_v3_request_with_server_side_key(monkeypatch):
    observed = {}

    async def handler(request):
        observed["url"] = str(request.url)
        observed["key"] = request.headers.get("X-API-Key-ID")
        observed["body"] = (await request.aread()).decode("latin-1")
        return httpx.Response(
            200,
            json={
                "success": True,
                "transcript": "2 kg rice at 60",
                "detected_language_code": "en-IN",
            },
        )

    transport = httpx.MockTransport(handler)
    original_client = gnani.httpx.AsyncClient
    monkeypatch.setattr(
        gnani.httpx,
        "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )

    result = asyncio.run(
        gnani.transcribe_audio(b"wav bytes", "order.wav", "audio/wav", "test-key")
    )

    assert observed["url"] == "https://api.vachana.ai/stt/v3"
    assert observed["key"] == "test-key"
    assert 'name="model"' in observed["body"]
    assert "prisma-v3.0" in observed["body"]
    assert "indic-auto" in observed["body"]
    assert result == {
        "transcript": "2 kg rice at 60",
        "detected_language_code": "en-IN",
    }


def test_rejects_non_success_response_from_gnani():
    async def handler(request):
        return httpx.Response(403, json={"success": False})

    transport = httpx.MockTransport(handler)
    original_client = gnani.httpx.AsyncClient
    gnani.httpx.AsyncClient = lambda **kwargs: original_client(
        transport=transport, **kwargs
    )
    try:
        with pytest.raises(gnani.GnaniAPIError):
            asyncio.run(
                gnani.transcribe_audio(
                    b"wav bytes", "order.wav", "audio/wav", "test-key"
                )
            )
    finally:
        gnani.httpx.AsyncClient = original_client
