from __future__ import annotations

import json
import os
import re
from pathlib import Path

from app.services.translator import translate

CACHE_PATH = Path(os.getenv("CLICK_NAME_LOCALIZATION_CACHE_PATH", "/tmp/click-name-localization-cache.json"))
_SUPPORTED_LANGS = {"en", "fr"}
_HANGUL_RE = re.compile(r"[가-힣]")
_DOSE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(밀리그램|마이크로그램|그램|밀리리터|mg|mcg|μg|ug|g|ml|mL)", re.IGNORECASE)

_INGREDIENT_OVERRIDES: dict[str, dict[str, str]] = {
    "아세트아미노펜": {"en": "Acetaminophen", "fr": "Paracetamol"},
    "아세트아미노펜 과립": {"en": "Acetaminophen granules", "fr": "Paracetamol granules"},
    "파라세타몰": {"en": "Acetaminophen", "fr": "Paracetamol"},
    "이부프로펜": {"en": "Ibuprofen", "fr": "Ibuprofen"},
    "아스피린": {"en": "Aspirin", "fr": "Aspirin"},
    "펠루비프로펜": {"en": "Pelubiprofen", "fr": "Pelubiprofen"},
    "에페리손염산염": {"en": "Eperisone HCl", "fr": "Eperisone HCl"},
    "프로나제": {"en": "Pronase", "fr": "Pronase"},
    "트리메부틴말레산염": {"en": "Trimebutine maleate", "fr": "Trimebutine maleate"},
    "자스타프라잔": {"en": "Zastaprazan", "fr": "Zastaprazan"},
    "자스타프라잔시트르산염": {"en": "Zastaprazan citrate", "fr": "Zastaprazan citrate"},
    "스트렙토키나제": {"en": "Streptokinase", "fr": "Streptokinase"},
    "스트렙토도르나제분말": {"en": "Streptodornase powder", "fr": "Streptodornase powder"},
    "이토프리드염산염": {"en": "Itopride HCl", "fr": "Itopride HCl"},
    "아목시실린수화물": {"en": "Amoxicillin hydrate", "fr": "Amoxicillin hydrate"},
    "암로디핀": {"en": "Amlodipine", "fr": "Amlodipine"},
    "암로디핀캄실산염": {"en": "Amlodipine camsylate", "fr": "Amlodipine camsylate"},
    "트라마돌염산염": {"en": "Tramadol HCl", "fr": "Tramadol HCl"},
    "니페디핀": {"en": "Nifedipine", "fr": "Nifedipine"},
    "레보설피리드": {"en": "Levosulpiride", "fr": "Levosulpiride"},
    "오메가-3": {"en": "Omega-3 fatty acids", "fr": "Omega-3 fatty acids"},
    "오메가3": {"en": "Omega-3 fatty acids", "fr": "Omega-3 fatty acids"},
    "EPA 및 DHA 함유 유지": {"en": "EPA and DHA-containing oil", "fr": "Huile contenant EPA et DHA"},
    "은행잎": {"en": "Ginkgo leaf", "fr": "Ginkgo leaf"},
    "마늘": {"en": "Garlic", "fr": "Garlic"},
    "인삼": {"en": "Ginseng", "fr": "Ginseng"},
    "홍삼": {"en": "Red ginseng", "fr": "Red ginseng"},
    "울금": {"en": "Turmeric", "fr": "Turmeric"},
    "커큐민": {"en": "Curcumin", "fr": "Curcumin"},
    "칼슘": {"en": "Calcium", "fr": "Calcium"},
    "마그네슘": {"en": "Magnesium", "fr": "Magnesium"},
    "철": {"en": "Iron", "fr": "Iron"},
    "비타민 D": {"en": "Vitamin D", "fr": "Vitamin D"},
    "비타민 D3": {"en": "Vitamin D3", "fr": "Vitamin D3"},
    "녹차": {"en": "Green tea", "fr": "Thé vert"},
    "녹차추출물": {"en": "Green tea extract", "fr": "Extrait de thé vert"},
    "카테킨": {"en": "Catechin", "fr": "Catéchine"},
    "카페인": {"en": "Caffeine", "fr": "Caféine"},
    "에피갈로카테킨갈레이트-epigallocatechin gallate": {"en": "Epigallocatechin gallate (EGCG)", "fr": "Gallate d\'épigallocatéchine (EGCG)"},
    "EGCG)": {"en": "EGCG", "fr": "EGCG"},
}

_PRODUCT_OVERRIDES: dict[str, dict[str, str]] = {
    "타이레놀정500밀리그람": {"en": "Tylenol Tab. 500 mg", "fr": "Tylenol cp. 500 mg"},
    "타이레놀이알서방정": {"en": "Tylenol ER Tab.", "fr": "Tylenol LP cp."},
    "펠루비서방정": {"en": "Pelubi SR Tab. 45mg", "fr": "Pelubi LP cp. 45 mg"},
    "에페리날서방정": {"en": "Eperinal SR Tab.", "fr": "Eperinal LP cp."},
    "안티라제정": {"en": "Antirase Tab.", "fr": "Antirase cp."},
    "포리부틴서방정": {"en": "Polybutine SR Tab. 300mg", "fr": "Polybutine LP cp. 300 mg"},
    "프리부틴서방정": {"en": "Polybutine SR Tab. 300mg", "fr": "Polybutine LP cp. 300 mg"},
    "자큐보정": {"en": "JAQBO Tab.", "fr": "JAQBO cp."},
    "자큐보정20mg": {"en": "JAQBO Tab. 20mg", "fr": "JAQBO cp. 20 mg"},
    "자큐보정20밀리그램": {"en": "JAQBO Tab. 20mg", "fr": "JAQBO cp. 20 mg"},
    "뮤코라제정": {"en": "Mucolase Tab.", "fr": "Mucolase cp."},
    "가나톤정": {"en": "Ganaton Tab.", "fr": "Ganaton cp."},
    "가나톤정50밀리그램": {"en": "Ganaton Tab. 50 mg", "fr": "Ganaton cp. 50 mg"},
    "금실린캡슐250밀리그램": {"en": "Geumsilin Cap. 250 mg", "fr": "Geumsilin gél. 250 mg"},
    "노바스크정10밀리그램": {"en": "Norvasc Tab. 10 mg", "fr": "Norvasc cp. 10 mg"},
    "울트라셋이알서방정": {"en": "Ultracet ER Tab.", "fr": "Ultracet LP cp."},
    "아달라트오로스정30": {"en": "Adalat OROS Tab. 30", "fr": "Adalat OROS cp. 30"},
    "레보프라이드정": {"en": "Levopride Tab.", "fr": "Levopride cp."},
    "녹차카테킨 플러스": {"en": "Green Tea Catechin Plus", "fr": "Green Tea Catechin Plus"},
}

_FORM_RULES: list[tuple[str, str, str]] = [
    ("이알서방정", "ER Tab.", "LP cp."),
    ("오로스정", "OROS Tab.", "OROS cp."),
    ("서방정", "SR Tab.", "LP cp."),
    ("장용정", "EC Tab.", "cp. gastro-résistant"),
    ("필름코팅정", "F.C. Tab.", "cp. pelliculé"),
    ("연질캡슐", "Soft Cap.", "caps. molle"),
    ("캡슐", "Cap.", "gél."),
    ("정", "Tab.", "cp."),
    ("시럽", "Syr.", "sirop"),
    ("액", "Soln.", "sol."),
]


def _has_hangul(value: str) -> bool:
    return bool(_HANGUL_RE.search(value))


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def _load_cache() -> dict[str, str]:
    try:
        if CACHE_PATH.exists():
            data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def _save_cache(cache: dict[str, str]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(CACHE_PATH)
    except Exception:
        pass


def _cache_key(lang: str, value: str) -> str:
    return f"{lang}:{value}"


def _translate_cached(value: str, lang: str) -> str:
    cache = _load_cache()
    key = _cache_key(lang, value)
    cached = cache.get(key)
    if cached:
        return cached

    translated = translate(value, lang).strip()
    result = translated if translated else value
    if result != value:
        cache[key] = result
        _save_cache(cache)
    return result


def _lookup_override(raw: str, lang: str) -> str | None:
    for table in (_INGREDIENT_OVERRIDES, _PRODUCT_OVERRIDES):
        override = table.get(raw)
        if override:
            return override.get(lang) or override.get("en") or raw
    return None


def _format_dose(text: str) -> tuple[str, list[str]]:
    doses: list[str] = []

    def repl(match: re.Match[str]) -> str:
        amount = match.group(1)
        unit = match.group(2).lower()
        mapped = {
            "밀리그램": "mg",
            "마이크로그램": "mcg",
            "그램": "g",
            "밀리리터": "mL",
            "μg": "mcg",
            "ug": "mcg",
            "ml": "mL",
        }.get(unit, unit)
        doses.append(f"{amount} {mapped}")
        return ""

    return _DOSE_RE.sub(repl, text).strip(), doses


def _pharma_product_name(raw: str, lang: str) -> str | None:
    stripped, doses = _format_dose(raw)
    form_label = ""
    stem = stripped
    for suffix, en_form, fr_form in _FORM_RULES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)].strip()
            form_label = fr_form if lang == "fr" else en_form
            break
    if not stem or stem == raw:
        return None

    brand = _lookup_override(stem, lang)
    if not brand:
        brand = _translate_cached(stem, lang)
    parts = [brand]
    if form_label:
        parts.append(form_label)
    parts.extend(doses)
    result = " ".join(part for part in parts if part).replace("  ", " ").strip()
    if result and result != raw and not re.search(r"\bCorrection\b|\bTablet[s]?\b", result):
        return result
    return None


def localize_medical_name(name: str | None, lang: str, english_name: str | None = None) -> str:
    """Return a display-only localized medical name without changing canonical DB values."""
    raw = _clean(name)
    if not raw or lang == "ko" or lang not in _SUPPORTED_LANGS:
        return raw

    override = _lookup_override(raw, lang)
    if override:
        return override

    english = _clean(english_name)
    if english and not _has_hangul(english):
        return english

    if not _has_hangul(raw):
        return raw

    product = _pharma_product_name(raw, lang)
    if product:
        return product

    return _translate_cached(raw, lang)


def localize_names(names: list[str], lang: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in names:
        clean = _clean(name)
        if clean and clean not in result:
            result[clean] = localize_medical_name(clean, lang)
    return result

def localize_texts(texts: list[str], lang: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for text in texts:
        clean = _clean(text)
        if clean and clean not in result:
            result[clean] = _translate_cached(clean, lang) if lang in _SUPPORTED_LANGS else clean
    return result

