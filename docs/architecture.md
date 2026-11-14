# Architecture and data handling

MandiVoice runs as a local web application. The browser handles microphone access and the review interface. A small FastAPI server serves the page, forwards audio to Gnani, interprets a narrow set of explicit item phrases, and calculates totals.

## Request path

1. The browser captures up to 30 seconds of mono microphone audio and encodes a WAV file, or the merchant chooses an existing recording.
2. The browser uploads the file to `/api/transcribe` on the local server.
3. The server reads `GNANI_API_KEY` from its environment and sends the audio to Gnani's Prisma v3 REST endpoint. The key is never returned to the browser.
4. The transcript stays editable. `/api/bills/parse` recognizes only lines with an explicit quantity, item name, and per-unit price. An unrecognized line is left for the merchant to enter.
5. The browser sends reviewed line items and the optional GST rate to `/api/bills/calculate`. The server validates values and returns decimal strings.

## Boundaries

- Speech recognition provides words, not verified financial data. The merchant checks all names and numbers.
- The parser is a convenience for common short order phrases. It does not infer a missing price, translate text, or guarantee that every utterance becomes an item.
- Billing arithmetic is deterministic. Each line amount is rounded to two decimal places with half-up rounding; tax is calculated on the rounded subtotal and rounded to two places.
- There is no payment connection, durable invoice storage, customer profile, or multi-user authentication.
- The development server must remain on loopback. It has no login or protection against cross-origin requests suitable for an internet deployment.

## Secrets and recordings

The `.env` file is local configuration and is excluded from Git. The server reads uploaded audio for the request and forwards it to Gnani. MandiVoice has no draft database and does not create a bill history. Use synthetic information in demonstrations.
