from __future__ import annotations

import deepl

from app.core.config import DEEPL_API_KEY

_DEEPL_TARGET = {"en": "EN-US", "fr": "FR"}

_client: deepl.Translator | None = None
if DEEPL_API_KEY:
    _client = deepl.Translator(DEEPL_API_KEY)


def translate(text: str, lang: str) -> str:
    """text를 lang으로 번역. lang이 ko이거나 키가 없으면 원문 그대로 반환."""
    if lang == "ko" or not text or _client is None:
        return text
    target = _DEEPL_TARGET.get(lang)
    if not target:
        return text
    try:
        result = _client.translate_text(text, source_lang="KO", target_lang=target)
        return result.text
    except deepl.DeepLException:
        return text
