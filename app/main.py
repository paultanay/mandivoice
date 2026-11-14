from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.billing import calculate_bill, calculate_order
from app.gnani import GnaniAPIError, synthesize_hindi, transcribe_audio
from app.order_extractor import OrderExtractionError, extract_order
from app.order_models import OrderDraft
from app.order_parser import build_hindi_readback, parse_order

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


class OrderInterpretRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=4000)


class OrderCalculateRequest(BaseModel):
    draft: OrderDraft
    review_confirmed: bool


class BillRequest(BaseModel):
    items: list[LineItem] = Field(max_length=50)
    gst_percent: str = Field(default="0", max_length=12)


class ReadbackRequest(BaseModel):
    items: list[LineItem] = Field(max_length=50)
    gst_percent: str = Field(default="0", max_length=12)


@app.get("/")
async def home() -> FileResponse:
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "transcription": "configured"
        if os.getenv("GNANI_API_KEY", "").strip()
        else "not_configured",
        "order_interpretation": "configured"
        if os.getenv("GROQ_API_KEY", "").strip()
        else "not_configured",
    }


@app.post("/api/bills/parse")
async def parse(request: ParseRequest) -> dict[str, object]:
    return parse_order(request.transcript)


@app.post("/api/orders/interpret")
async def interpret_order(request: OrderInterpretRequest) -> dict[str, object]:
    provider = os.getenv("ORDER_LLM_PROVIDER", "groq").strip().lower()
    if provider != "groq":
        raise HTTPException(
            status_code=503,
            detail="Set ORDER_LLM_PROVIDER to groq or leave it unset.",
        )
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Set GROQ_API_KEY in your local .env to interpret orders.",
        )
    model = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b").strip()
    if not model:
        raise HTTPException(
            status_code=503, detail="Set GROQ_MODEL to a supported model."
        )

    try:
        draft = await extract_order(request.transcript, api_key, model)
    except OrderExtractionError as error:
        raise HTTPException(status_code=502, detail=str(error)) from None

    if draft.clarifications:
        return {
            "status": "needs_clarification",
            "draft": draft.model_dump(),
            "calculation": None,
            "issues": draft.clarifications,
        }
    try:
        calculation = calculate_order(draft, transcript=request.transcript)
    except ValueError as error:
        return {
            "status": "needs_review",
            "draft": draft.model_dump(),
            "calculation": None,
            "issues": [str(error)],
        }
    return {
        "status": "ready_for_review",
        "draft": draft.model_dump(),
        "calculation": calculation,
        "issues": [],
    }


@app.post("/api/orders/calculate")
async def calculate_order_endpoint(request: OrderCalculateRequest) -> dict[str, object]:
    if not request.review_confirmed:
        raise HTTPException(
            status_code=422,
            detail="Review the transcript and order draft before calculating.",
        )
    try:
        return calculate_order(request.draft)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


@app.post("/api/bills/calculate")
async def calculate(request: BillRequest) -> dict:
    try:
        return calculate_bill(
            [item.model_dump() for item in request.items],
            gst_percent=request.gst_percent,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None


@app.post("/api/orders/readback")
async def order_readback(request: ReadbackRequest) -> Response:
    api_key = os.getenv("GNANI_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Set GNANI_API_KEY in your environment to enable voice confirmation.",
        )
    try:
        text = build_hindi_readback(
            [item.model_dump() for item in request.items],
            gst_percent=request.gst_percent,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    try:
        audio = await synthesize_hindi(text, api_key)
    except (GnaniAPIError, httpx.RequestError):
        raise HTTPException(
            status_code=502,
            detail="Voice confirmation failed. Check your API key, credits, or connection.",
        ) from None
    return Response(content=audio, media_type="audio/wav")


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
