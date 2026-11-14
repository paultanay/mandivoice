# Architecture and data handling

MandiVoice is a local web app with a small FastAPI server. The browser handles recording and the review interface. The server calls Gnani for transcription and optional Hindi speech synthesis, parses explicit order details, and calculates bill totals.

## Request path

1. The browser records up to 30 seconds of audio or accepts an audio file.
2. It uploads the recording to `/api/transcribe`. The server reads `GNANI_API_KEY` from its environment and forwards the audio to Gnani Prisma v3.
3. The browser displays the transcript and submits it to `/api/bills/parse`. The parser extracts only details it can identify from supported Hindi and English patterns. Missing values stay missing.
4. The merchant reviews and edits the transcript and draft rows. For Hindi orders, `/api/orders/readback` can produce a Timbre v2.5 Hindi audio read-back of the displayed values.
5. The calculate action remains disabled until the merchant confirms the review. `/api/bills/calculate` validates the submitted rows and returns decimal strings.

## Financial behavior

Speech recognition and parsing are fallible. Neither is a source of verified financial data. The person preparing the bill must compare item names, quantities, prices, and tax with the customer's order. Changing the transcript or a bill field clears the review confirmation.

Arithmetic is deterministic. Each line amount is rounded to two decimal places using half-up rounding. GST is calculated on the rounded subtotal and rounded to two decimal places. The app does not determine which GST rate applies.

## Boundaries

- There is no payment connection, durable invoice storage, product catalog, customer ledger, or multi-user authentication.
- The parser covers common short order phrases. It does not resolve ambiguous speech or invent prices.
- The development server has no login or internet deployment protections. Keep it bound to loopback.

## Secrets and recordings

The `.env` file is local configuration and excluded from Git. Browser requests go to the local server; the API key is never sent to browser code or returned by health checks. Audio sent for transcription and speech synthesis is processed by Gnani. MandiVoice does not store recordings or bill history. Use synthetic information in public demonstrations.
