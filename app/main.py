from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.billing import calculate_bill
from app.gnani import GnaniAPIError, transcribe_audio
from app.order_parser import parse_order_items

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")
MAX_AUDIO_BYTES = 20 * 1024 * 1024
ALLOWED_AUDIO_TYPES = {
    "audio/wav",
    "audio/wave",
    "audio/x-wav",
    "audio/mpeg",
    "audio/ogg",
    "audio/flac",
    "audio/aac",
    "audio/mp4",
    "audio/x-m4a",
}

app = FastAPI(title="MandiVoice", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class LineItem(BaseModel):
    name: str = Field(max_length=80)
    quantity: str = Field(max_length=24)
    unit_price: str = Field(max_length=24)


class ParseRequest(BaseModel):
    transcript: str = Field(max_length=4000)


class BillRequest(BaseModel):
    items: list[LineItem] = Field(min_length=1, max_length=50)
    gst_percent: str = Field(default="0", max_length=12)


@app.get("/")
async def home() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "transcription": "configured"
        if os.getenv("GNANI_API_KEY", "").strip()
        else "not_configured",
    }


@app.post("/api/bills/parse")
async def parse(request: ParseRequest) -> dict[str, list[dict[str, str]]]:
    return {"items": parse_order_items(request.transcript)}


@app.post("/api/bills/calculate")
async def calculate(request: BillRequest) -> dict:
    try:
        return calculate_bill(
            [item.model_dump() for item in request.items],
            gst_percent=request.gst_percent,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


@app.post("/api/transcribe")
async def transcribe(
    audio_file: Annotated[UploadFile, File()],
) -> dict[str, str | None]:
    api_key = os.getenv("GNANI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Set GNANI_API_KEY in your environment to enable transcription.",
        )

    content_type = (audio_file.content_type or "").split(";")[0].strip().lower()
    if content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Use a WAV, MP3, OGG, FLAC, AAC, or M4A recording.",
        )
    audio = await audio_file.read(MAX_AUDIO_BYTES + 1)
    if not audio:
        raise HTTPException(status_code=400, detail="The selected audio file is empty.")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=413, detail="Audio files must be 20 MB or smaller."
        )

    try:
        return await transcribe_audio(
            audio,
            audio_file.filename or "recording.wav",
            content_type,
            api_key,
        )
    except (GnaniAPIError, httpx.RequestError):
        raise HTTPException(
            status_code=502,
            detail="Transcription failed. Check your API key, available credits, or connection and try again.",
        ) from None
