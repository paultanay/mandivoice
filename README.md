# MandiVoice

MandiVoice turns a spoken shop order into a bill draft that a shopkeeper can inspect before calculating. It combines Gnani Prisma transcription with a language model that structures multilingual order details, then uses ordinary decimal arithmetic for the bill.

The transcript and extracted values are suggestions. Speech recognition can confuse item names, quantities, prices, or tax rates. The app requires an explicit review before it calculates a bill. It does not collect payment or save bill history.

## The order flow

1. Record up to 30 seconds or choose an audio file.
2. Send it to Gnani Prisma for transcription. The transcript appears on screen and remains editable.
3. Send the transcript text to Groq for a structured draft. Each extracted detail includes a short phrase from the transcript as evidence.
4. Review or edit the item, quantity, price, tax, and any discounts or adjustments. Unclear details or mismatched evidence block automatic calculation until you correct the draft or switch to manual entry.
5. Check the review box and calculate. The server uses decimal arithmetic; the language model never calculates totals.

Unclear or incomplete values must be resolved before calculating. The draft can represent multiple item tax rates, GST-inclusive prices, line or order discounts, free quantities, charges, returns, prior balance, payments, round-off, and a customer GSTIN. These fields are still suggestions and need review. Manual entry remains available if Groq is unconfigured or unavailable.

## Requirements

- Python 3.11 or later
- `uv`
- A Gnani API key for Prisma transcription; the same key enables optional Timbre Hindi read-back
- A Groq API key for transcript interpretation
- A modern browser for microphone recording. Audio file upload is also supported.

## Run locally

From the repository directory:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp -n .env.example .env
```

Set `GNANI_API_KEY` and `GROQ_API_KEY` in `.env`. Keep each provider key separate. `GROQ_MODEL` defaults to `qwen/qwen3.8-27b`, which Groq currently lists as supporting strict JSON Schema output. You can change the model ID to another Groq model that supports this feature. The keys stay on the server and are never returned to the browser. Restart the server after changing `.env`. Start the app:

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Keep this development server bound to loopback. It has no login and is not suitable for public hosting as-is.

## API

- `POST /api/transcribe`: transcribes one audio file using Gnani Prisma v3.0 and automatic Indic language detection.
- `POST /api/orders/interpret`: sends transcript text to Groq and returns an evidence-linked order draft and deterministic preview when the draft is complete.
- `POST /api/orders/calculate`: calculates a user-reviewed structured draft after explicit review confirmation.
- `POST /api/bills/parse`: legacy deterministic parser for common short orders.
- `POST /api/orders/readback`: synthesizes a Hindi read-back of the reviewed order using Gnani Timbre v2.5. It returns WAV audio.
- `POST /api/bills/calculate`: validates rows and returns decimal amounts as strings.
- `GET /api/health`: reports whether Gnani transcription and Groq interpretation are configured. It never returns keys.

The language model can still misunderstand a transcript. Strict JSON output guarantees the shape of its response, not that the extracted values are true. MandiVoice checks that quoted evidence appears in the transcript and blocks unresolved drafts, but the merchant must verify every value and apply the tax treatment appropriate to the transaction. It is not a product catalog or tax adviser.

## Development checks

```bash
.venv/bin/pytest -q
.venv/bin/ruff check app tests
.venv/bin/ruff format --check app tests
node --check app/static/app.js
```

The automated tests use local fixtures and mocked Gnani responses; they do not require an API call. See [architecture and data handling](docs/architecture.md) for request flow, rounding, and privacy boundaries.

## Transcript benchmark

`benchmarks/retail_orders.jsonl` contains the supplied Hinglish edge cases plus short order transcripts in Bengali, Gujarati, Kannada, Malayalam, Marathi, Punjabi, Tamil, and Telugu. Run a live model check after configuring Groq:

```bash
.venv/bin/python scripts/evaluate_orders.py
```

The evaluator checks selected extracted fields, clarifications, unsupported requests, and totals. It uses Groq and may pause when the account reaches its output-token limit. It is a regression aid, not proof of accuracy for every accent or order.

## Privacy

Audio submitted for transcription and read-back requests is sent to Gnani. Transcript text, which can contain product, customer, payment, or tax details, is sent to Groq for interpretation. Review both providers' data policies before using real customer information. MandiVoice does not retain recordings or bills in a database. Do not commit `.env`, customer recordings, or personal data. Use a synthetic order for a public demo.

## License

MIT. See [LICENSE](LICENSE).
