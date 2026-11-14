def contains_verbatim_quote(quote: str | None, transcript: str) -> bool:
    """Return whether a nonblank evidence quote appears in transcript text."""
    if not quote or not quote.strip():
        return False

    normalized_quote = " ".join(quote.casefold().split())
    normalized_transcript = " ".join(transcript.casefold().split())
    return normalized_quote in normalized_transcript
