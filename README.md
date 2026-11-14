# MandiVoice

MandiVoice turns a short spoken shop order into an editable bill draft. Gnani Prisma transcribes the recording; MandiVoice suggests only the item lines that include an explicit quantity and price. You review the transcript and every field. The server calculates subtotal, optional GST, and total with decimal arithmetic.

There is no payment flow, automatic invoice submission, or stored customer ledger. An unclear line stays out of the suggestion rather than receiving an invented price.

## What works

- Record up to 30 seconds in the browser or upload a WAV, MP3, OGG, FLAC, AAC, or M4A file.
- Transcribe with Gnani Prisma v3.0, using automatic language detection.
- Suggest item rows from explicit patterns such as `2 kg rice at 60` or `3 packets tea at Rs 25`.
- Edit, remove, and add items before calculating.
- Calculate subtotal and optional GST with Python `Decimal` and standard half-up currency rounding.
- Run on your own machine. The API key stays on the server.

The item suggestion parser is intentionally narrow. It recognizes quantities and prices written in that order and does not translate a transcript into a full invoice. If a line is not recognized, enter it yourself. Speech recognition can mishear prices, so check the transcript and bill against the spoken order.

## Requirements

- Python 3.11 or later
- An API key from the Gnani speech API dashboard to use transcription
- A modern browser with microphone permission for recording; file upload also works

## Run locally

From this directory:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and set `GNANI_API_KEY` to your Gnani API key. Keep the file private. It is ignored by Git.

Start the server:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Microphone permissions work on `localhost` and secure HTTPS pages. Keep this development server bound to `127.0.0.1`; it has no login and is not intended to be exposed to the public internet.

## Example order

Say or type:

> 2 kg rice at 60, 3 packets tea at Rs 25

Select **Find priced items**. The app proposes two editable rows. Review their names and values, enter a GST rate if needed, and calculate the total. If you enter only `2 kg rice`, no price is filled in for you.

## API behavior

- `POST /api/transcribe`: accepts one audio file up to 20 MB and calls `POST https://api.vachana.ai/stt/v3` with `model=prisma-v3.0` and `language_code=indic-auto`.
- `POST /api/bills/parse`: extracts only explicit quantity and unit-price patterns. Unrecognized text returns an empty item list.
- `POST /api/bills/calculate`: validates line items and returns amounts as decimal strings.
- `GET /api/health`: reports server health and whether transcription is configured. It never returns the key.

Gnani's documentation lists WAV, MP3, OGG, FLAC, AAC, and M4A for short STT requests, and documents Prisma v3.0 as opt-in. See [Prisma v3.0](https://docs.gnani.ai/api/STT/models/prisma-v3) and [API authentication](https://docs.gnani.ai/api/introduction/introduction).

## Development checks

```bash
.venv/bin/pytest -q
node --check app/static/app.js
.venv/bin/ruff check app tests
.venv/bin/ruff format --check app tests
```

Tests cover arithmetic, validation, parser behavior, API error handling, and transcription responses without making live API calls. To verify your own API key, run the app and transcribe a short synthetic order recording.

## Privacy and security

- Do not commit `.env`, customer recordings, real account details, or personal data.
- Transcription audio is sent to Gnani's API. MandiVoice does not retain a bill history.
- The server keeps the API key out of browser code and does not log it.
- Use synthetic examples when recording a public demo.

## License

MIT. See [LICENSE](LICENSE).
