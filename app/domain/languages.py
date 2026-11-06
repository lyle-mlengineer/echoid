"""The spoken languages the studio offers, keyed by ISO 639-1 code.

Whisper's ASR stage wants its own English language names, so the code travels
through the API and storage while the model call converts it here.
"""

LANGUAGES: tuple[tuple[str, str], ...] = (
    ("af", "Afrikaans"),
    ("ar", "Arabic"),
    ("de", "German"),
    ("el", "Greek"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("ha", "Hausa"),
    ("hi", "Hindi"),
    ("id", "Indonesian"),
    ("ig", "Igbo"),
    ("it", "Italian"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("ms", "Malay"),
    ("nl", "Dutch"),
    ("pl", "Polish"),
    ("pt", "Portuguese"),
    ("ru", "Russian"),
    ("so", "Somali"),
    ("sw", "Swahili"),
    ("ta", "Tamil"),
    ("th", "Thai"),
    ("tl", "Tagalog"),
    ("tr", "Turkish"),
    ("uk", "Ukrainian"),
    ("ur", "Urdu"),
    ("vi", "Vietnamese"),
    ("yo", "Yoruba"),
    ("zh", "Chinese"),
)

WHISPER_NAMES: dict[str, str] = {
    code: name.lower() for code, name in LANGUAGES
}

LANGUAGE_NAMES: dict[str, str] = dict(LANGUAGES)


def normalize_language(code: str | None) -> str | None:
    """Return a supported ISO code, or None when the caller wants auto-detect."""
    if code is None:
        return None
    cleaned = code.strip().lower()
    if not cleaned or cleaned == "auto":
        return None
    return cleaned if cleaned in LANGUAGE_NAMES else None
