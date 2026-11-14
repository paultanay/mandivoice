from __future__ import annotations

import httpx

STT_URL = "https://api.vachana.ai/stt/v3"


class GnaniAPIError(RuntimeError):
    """The Gnani service rejected a request or returned an invalid response."""


async def transcribe_audio(
    audio: bytes,
    filename: str,
    content_type: str,
    api_key: str,
) -> dict[str, str | None]:
    timeout = httpx.Timeout(45.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            STT_URL,
            headers={"X-API-Key-ID": api_key},
            files={"audio_file": (filename, audio, content_type)},
            data={"model": "prisma-v3.0", "language_code": "indic-auto"},
        )

    if response.status_code != 200:
        raise GnaniAPIError(f"Gnani returned HTTP {response.status_code}")

    try:
        body = response.json()
    except ValueError:
        raise GnaniAPIError("Gnani returned an unreadable response") from None

    if not isinstance(body, dict) or body.get("success") is not True:
        raise GnaniAPIError("Gnani could not transcribe this recording")
    transcript = body.get("transcript")
    if not isinstance(transcript, str) or not transcript.strip():
        raise GnaniAPIError("Gnani returned an empty transcript")

    language = body.get("detected_language_code")
    return {
        "transcript": transcript.strip(),
        "detected_language_code": language if isinstance(language, str) else None,
    }
