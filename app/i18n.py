from __future__ import annotations

from typing import Literal

Lang = Literal["ko", "en", "fr"]

_SUMMARY: dict[str, dict[Lang, str]] = {
    "no_supplements": {
        "ko": "분석할 건강기능식품이 없습니다.",
        "en": "No supplements provided for analysis.",
        "fr": "Aucun complément alimentaire fourni pour l'analyse.",
    },
    "no_interactions": {
        "ko": "확인된 상호작용이 없습니다. 복용 전 전문가와 상담하세요.",
        "en": "No known interactions found. Please consult a professional before use.",
        "fr": "Aucune interaction connue. Consultez un professionnel avant toute prise.",
    },
    "danger": {
        "ko": "위험한 조합이 있습니다. 복용 전 반드시 전문가와 상담하세요.",
        "en": "A dangerous combination was found. Consult a professional before use.",
        "fr": "Une combinaison dangereuse a été détectée. Consultez un professionnel avant toute prise.",
    },
    "caution": {
        "ko": "일부 조합에서 주의가 필요합니다. 전문가와 상담을 권장합니다.",
        "en": "Some combinations require caution. We recommend consulting a professional.",
        "fr": "Certaines combinaisons nécessitent de la prudence. Il est conseillé de consulter un professionnel.",
    },
    "safe": {
        "ko": "확인된 주의 사항이 없습니다. 복용 전 전문가와 상담하세요.",
        "en": "No known precautions found. Please consult a professional before use.",
        "fr": "Aucune précaution connue. Consultez un professionnel avant toute prise.",
    },
}


def get_summary(key: str, lang: Lang) -> str:
    return _SUMMARY[key].get(lang, _SUMMARY[key]["ko"])


def parse_lang(raw: str | None) -> Lang:
    if raw in ("en", "fr"):
        return raw  # type: ignore[return-value]
    return "ko"
