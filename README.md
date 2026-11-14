# MandiVoice

MandiVoice turns a short spoken shop order into a bill draft that the shopkeeper can inspect before calculating. It is built for a counter workflow: capture the customer's order, get a transcript, extract only the quantities and prices the order states, review the draft, then calculate the total.

The transcript and extracted values are suggestions. Speech recognition can confuse item names, quantities, prices, or tax rates. The app requires an explicit review before it calculates a bill. It does not collect payment or save bill history.

## The order flow

1. Record up to 30 seconds or choose an audio file.
2. Send it to Gnani Prisma for transcription. The transcript appears on screen and remains editable.
3. MandiVoice parses Hindi and English order phrases into item rows when it can identify an explicit item, quantity, and unit price. It can also read an explicitly spoken GST rate.
4. Review or edit every value. In Hindi mode, you can ask Timbre to read the draft back aloud and compare it with what the customer said.
5. Check the review box and calculate. The server uses decimal arithmetic for subtotal, GST, and total.

Unclear or incomplete values are left blank instead of being guessed. You can add or edit rows manually. For example, the supplied demo recording transcribes as “भैया, चालीस रुपये के जी बासमती राइस, फिफ्टी सिक्स रुपये किलो बिल करो और फ़ाइव परसेंट जी एस टी लगाओ।” The parser proposes 40 kg of basmati rice at ₹56 per kg and 5% GST. Check those values against the audio before calculating.

## Requirements

- Python 3.11 or later
- `uv`
- A Gnani API key for Prisma transcription; the same key enables optional Timbre Hindi read-back
- A modern browser for microphone recording. Audio file upload is also supported.

## Run locally

From the repository directory:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
cp -n .env.example .env
```

Set `GNANI_API_KEY` in `.env`. The file is ignored by Git and the key is used only by the server. Start the app:

```bash
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Keep this development server bound to loopback. It has no login and is not suitable for public hosting as-is.

## API

- `POST /api/transcribe`: transcribes one audio file using Gnani Prisma v3.0 and automatic Indic language detection.
- `POST /api/bills/parse`: returns item rows and GST explicitly found in a transcript. A partial order can return no rows or an incomplete row.
- `POST /api/orders/readback`: synthesizes a Hindi read-back of the reviewed order using Gnani Timbre v2.5. It returns WAV audio.
- `POST /api/bills/calculate`: validates rows and returns decimal amounts as strings.
- `GET /api/health`: reports server status and whether the transcription key is configured. It never returns the key.

The current parser targets common short Hindi and English shop orders. It is not a general speech understanding system, product catalog, or tax adviser. Verify every extracted value and use the tax rate appropriate to the transaction.

## Development checks

```bash
.venv/bin/pytest -q
.venv/bin/ruff check app tests
.venv/bin/ruff format --check app tests
node --check app/static/app.js
```

The automated tests use local fixtures and mocked Gnani responses; they do not require an API call. See [architecture and data handling](docs/architecture.md) for request flow, rounding, and privacy boundaries.

## Privacy

Audio submitted for transcription and read-back requests is sent to Gnani. MandiVoice does not retain recordings or bills in a database. Do not commit `.env`, customer recordings, or personal data. Use a synthetic order for a public demo.

## License

MIT. See [LICENSE](LICENSE).
