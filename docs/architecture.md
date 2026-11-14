# Architecture and data handling

MandiVoice is a local web app with a FastAPI server. The browser captures audio and provides the review form. The server delegates speech recognition to Gnani Prisma and transcript interpretation to Groq. It calculates the bill itself using decimal arithmetic.

## Request path

1. The browser records up to 30 seconds of audio or accepts an audio file.
2. It uploads the recording to `/api/transcribe`. The server reads `GNANI_API_KEY` and forwards the audio to Gnani Prisma v3.
3. The browser displays the transcript and submits the text to `/api/orders/interpret`. The server reads `GROQ_API_KEY`, requests a strict structured response, and validates the result as an `OrderDraft`. After a recognized strict-generation failure, it retries once and then tries JSON mode with the schema included in the prompt. Every response must pass local validation.
4. The draft includes short transcript quotes for extracted values. The server drops item lines whose name or source quote cannot be found in the transcript, and it asks for missing bill-critical values. The calculate request checks the remaining field evidence and returns an issue instead of a total when evidence is absent or a field is incomplete.
5. The merchant reviews the displayed values and edits the draft. A separate calculate request uses the reviewed values and requires explicit confirmation. Arithmetic is performed locally by the server; the language model does not calculate totals.
6. For simple Hindi orders, `/api/orders/readback` can produce a Timbre Hindi audio read-back.

## Draft fields and calculations

An order draft can contain several item lines, per-line or shared tax rates, tax-inclusive prices, discounts, free quantities, extra charges, returns, an earlier balance, payments received, round-off, and a customer GSTIN. The model must leave unclear values empty and ask for clarification. No tax rate is inferred from an item name.

Money is represented with `Decimal`, rounded to two places using half-up rounding. A line price marked inclusive of tax is divided by one plus its stated tax rate to derive the taxable amount. Discounts are applied before tax unless explicitly marked as after-tax. The response keeps gross amount due, prior balance, paid amount, and balance due separate. This is arithmetic behavior, not accounting or tax advice; have a qualified person verify the treatment of a real transaction.

Per-unit prices convert only across recognized units. Per-piece pricing for a pack uses the stated pack contents. Free quantities are excluded from the billable count. The calculator returns an issue when the units do not support a clear conversion.

## Reliability boundary

Groq strict structured output constrains the response shape when the configured model supports it. The JSON-mode fallback may return a valid object with incomplete information, so local model validation and evidence checks still apply. Neither mode proves the model interpreted a phrase correctly. An evidence quote can be valid while the selected interpretation is wrong. The interface keeps the transcript visible, shows source phrases, requires human confirmation, and provides manual entry. It cannot promise perfect interpretation for arbitrary accents, code-mixing, noisy recordings, or ambiguous orders.

Groq can rate limit output tokens independently of request count. MandiVoice waits once when `Retry-After` is at most 60 seconds, then retries the same response mode. Longer limits return a clear message so the merchant can retry later. The checked-in transcript benchmark records expected fields and clarifications for supplied Hinglish cases and short examples in the other Prisma-supported Indian languages; run it separately from the offline test suite.

## Secrets and recordings

The ignored `.env` file contains separate `GNANI_API_KEY` and `GROQ_API_KEY` values. Keys stay on the server and are not included in browser code or health responses. Audio goes to Gnani for transcription. Transcript text, potentially including customer identifiers, prices, payments, and tax details, goes to Groq. Review both providers' current data policies before processing real customer information. MandiVoice does not store recordings or bill history.

The development server has no login or public deployment protections. Keep it bound to loopback; it is not ready for public hosting as-is.
