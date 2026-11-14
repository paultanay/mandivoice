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
    assert response.json()["items"] == [
        {"name": "rice (kg)", "quantity": "2", "unit_price": "60"},
        {"name": "tea (packets)", "quantity": "3", "unit_price": "25"},
    ]


def test_parse_endpoint_does_not_guess_missing_prices():
    response = client.post(
        "/api/bills/parse",
        json={"transcript": "2 kg rice and some tea"},
    )

    assert response.status_code == 200
    assert response.json() == {"items": []}


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
