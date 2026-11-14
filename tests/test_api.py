from fastapi.testclient import TestClient

from app.gnani import GnaniAPIError
from app.main import app

client = TestClient(app)


def test_calculate_endpoint_returns_deterministic_total():
    response = client.post(
        "/api/bills/calculate",
        json={
            "items": [{"name": "Rice", "quantity": "2", "unit_price": "60"}],
            "gst_percent": "5",
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == "126.00"


def test_calculate_endpoint_rejects_invalid_values():
    response = client.post(
        "/api/bills/calculate",
        json={"items": [{"name": "Rice", "quantity": "-1", "unit_price": "60"}]},
    )

    assert response.status_code == 422


def test_calculate_endpoint_explains_when_bill_has_no_items():
    response = client.post(
        "/api/bills/calculate",
        json={"items": [], "gst_percent": "5"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Add between 1 and 50 items"


def test_transcription_without_key_returns_configuration_error(monkeypatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    response = client.post(
        "/api/transcribe",
        files={"audio_file": ("order.wav", b"RIFFfake", "audio/wav")},
    )

    assert response.status_code == 503
    assert "GNANI_API_KEY" in response.json()["detail"]


def test_transcription_returns_transcript_from_gnani(monkeypatch):
    async def fake_transcribe(audio, filename, content_type, api_key):
        assert audio == b"RIFFfake"
        assert filename == "order.wav"
        assert content_type == "audio/wav"
        assert api_key == "test-key"
        return {"transcript": "2 kg rice at 60", "detected_language_code": "en-IN"}

    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setattr("app.main.transcribe_audio", fake_transcribe)
    response = client.post(
        "/api/transcribe",
        files={"audio_file": ("order.wav", b"RIFFfake", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "transcript": "2 kg rice at 60",
        "detected_language_code": "en-IN",
    }


def test_transcription_upstream_failure_is_safe_and_actionable(monkeypatch):
    async def fail_transcribe(audio, filename, content_type, api_key):
        raise GnaniAPIError("Gnani service returned 503")

    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setattr("app.main.transcribe_audio", fail_transcribe)
    response = client.post(
        "/api/transcribe",
        files={"audio_file": ("order.wav", b"RIFFfake", "audio/wav")},
    )

    assert response.status_code == 502
    assert (
        response.json()["detail"]
        == "Transcription failed. Check your API key, available credits, or connection and try again."
    )


def test_parse_endpoint_extracts_only_explicit_quantity_and_price():
    response = client.post(
        "/api/bills/parse",
        json={"transcript": "2 kg rice at 60, 3 packets tea at Rs 25"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"name": "rice (kg)", "quantity": "2", "unit_price": "60"},
            {"name": "tea (packets)", "quantity": "3", "unit_price": "25"},
        ],
        "gst_percent": None,
    }


def test_parse_endpoint_does_not_guess_missing_prices():
    response = client.post(
        "/api/bills/parse",
        json={"transcript": "2 kg rice and some tea"},
    )

    assert response.status_code == 200
    assert response.json() == {"items": [], "gst_percent": None}


def test_transcription_rejects_unsupported_media_type_before_upstream(monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    response = client.post(
        "/api/transcribe",
        files={"audio_file": ("order.webm", b"audio", "audio/webm")},
    )

    assert response.status_code == 415


def test_transcription_rejects_audio_larger_than_limit(monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    payload = b"x" * (20 * 1024 * 1024 + 1)
    response = client.post(
        "/api/transcribe",
        files={"audio_file": ("order.wav", payload, "audio/wav")},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Audio files must be 20 MB or smaller."


def test_health_reports_configuration_without_disclosing_key(monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "private-test-key")
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "transcription": "configured"}
    assert "private-test-key" not in response.text


def test_calculate_endpoint_bounds_input_size():
    response = client.post(
        "/api/bills/calculate",
        json={"items": [{"name": "Rice", "quantity": "1" * 25, "unit_price": "60"}]},
    )

    assert response.status_code == 422


def test_parse_endpoint_accepts_sentence_punctuation_after_price():
    response = client.post(
        "/api/bills/parse",
        json={"transcript": "2 kg rice at 60 rupees."},
    )

    assert response.status_code == 200
    assert response.json()["items"] == [
        {"name": "rice (kg)", "quantity": "2", "unit_price": "60"}
    ]


def test_parses_hindi_spoken_quantity_price_and_gst_from_real_order():
    transcript = "भैया, चालीस रुपये के जी बासमती राइस, फिफ्टी सिक्स रुपये किलो बिल करो और फ़ाइव परसेंट जी एस टी लगाओ।"
    response = client.post("/api/bills/parse", json={"transcript": transcript})

    assert response.status_code == 200
    assert response.json() == {
        "items": [{"name": "बासमती राइस (kg)", "quantity": "40", "unit_price": "56"}],
        "gst_percent": "5",
    }


def test_real_order_fields_produce_expected_reviewable_total():
    transcript = "भैया, चालीस रुपये के जी बासमती राइस, फिफ्टी सिक्स रुपये किलो बिल करो और फ़ाइव परसेंट जी एस टी लगाओ।"
    parsed = client.post("/api/bills/parse", json={"transcript": transcript}).json()
    response = client.post(
        "/api/bills/calculate",
        json={"items": parsed["items"], "gst_percent": parsed["gst_percent"]},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["quantity"] == "40"
    assert response.json()["subtotal"] == "2240.00"
    assert response.json()["gst_amount"] == "112.00"
    assert response.json()["total"] == "2352.00"


def test_hindi_readback_uses_reviewed_values_and_returns_wav(monkeypatch):
    async def fake_synthesize(text, api_key):
        assert "चालीस किलो बासमती राइस" in text
        assert "छप्पन रुपये प्रति किलो" in text
        assert "पाँच प्रतिशत जीएसटी" in text
        assert "कुल दो हजार तीन सौ बावन रुपये बनते हैं" in text
        assert api_key == "test-key"
        return b"RIFFtest-wav"

    monkeypatch.setenv("GNANI_API_KEY", "test-key")
    monkeypatch.setattr("app.main.synthesize_hindi", fake_synthesize)
    response = client.post(
        "/api/orders/readback",
        json={
            "items": [
                {"name": "बासमती राइस (kg)", "quantity": "40", "unit_price": "56"}
            ],
            "gst_percent": "5",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"RIFFtest-wav"


def test_hindi_readback_requires_api_key(monkeypatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    response = client.post(
        "/api/orders/readback",
        json={"items": [{"name": "Rice", "quantity": "1", "unit_price": "2"}]},
    )

    assert response.status_code == 503
    assert "GNANI_API_KEY" in response.json()["detail"]


def test_parser_does_not_suggest_zero_quantity_or_price():
    response = client.post(
        "/api/bills/parse",
        json={"transcript": "शून्य किलो आलू शून्य रुपये किलो, पाँच प्रतिशत जीएसटी"},
    )

    assert response.status_code == 200
    assert response.json() == {"items": [], "gst_percent": "5"}


def test_parses_multiple_hindi_items_and_pairs_each_price():
    transcript = (
        "दो किलो चावल, तीस रुपये किलो, एक किलो दाल, सत्तर रुपये किलो, पाँच प्रतिशत जीएसटी"
    )
    response = client.post("/api/bills/parse", json={"transcript": transcript})

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"name": "चावल (kg)", "quantity": "2", "unit_price": "30"},
            {"name": "दाल (kg)", "quantity": "1", "unit_price": "70"},
        ],
        "gst_percent": "5",
    }
