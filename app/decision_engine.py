import re
import unicodedata
from typing import Any


DEFAULT_MINIMUM_SCORE = 65
DEFAULT_AUTOMATIC_SCORE = 85


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(value.casefold().split())


def _items(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;\n]", value) if item.strip()]
    return []


def default_preferences(
    *,
    target_roles: str = "",
    location: str = "",
) -> dict[str, Any]:
    return {
        "target_roles": _items(target_roles),
        "locations": _items(location),
        "modalities": [],
        "excluded_companies": [],
        "required_keywords": [],
        "excluded_keywords": [],
        "minimum_score": DEFAULT_MINIMUM_SCORE,
        "automatic_score": DEFAULT_AUTOMATIC_SCORE,
        "allow_automatic": False,
        "max_daily_applications": 5,
    }


def normalize_preferences(
    preferences: dict[str, Any] | None,
    *,
    target_roles: str = "",
    location: str = "",
) -> dict[str, Any]:
    result = default_preferences(target_roles=target_roles, location=location)
    supplied = preferences or {}
    for field in (
        "target_roles",
        "locations",
        "modalities",
        "excluded_companies",
        "required_keywords",
        "excluded_keywords",
    ):
        if field in supplied:
            result[field] = _items(supplied[field])
    for field, default, minimum, maximum in (
        ("minimum_score", DEFAULT_MINIMUM_SCORE, 0, 100),
        ("automatic_score", DEFAULT_AUTOMATIC_SCORE, 0, 100),
        ("max_daily_applications", 5, 1, 50),
    ):
        try:
            value = int(supplied.get(field, default))
        except (TypeError, ValueError):
            value = default
        result[field] = min(max(value, minimum), maximum)
    result["automatic_score"] = max(
        result["automatic_score"],
        result["minimum_score"],
    )
    result["allow_automatic"] = bool(supplied.get("allow_automatic", False))
    return result


def decide_opportunity(
    job: dict[str, Any],
    analysis: dict[str, Any] | None,
    preferences: dict[str, Any],
    *,
    capture_confidence: int | None = None,
) -> dict[str, Any]:
    prefs = normalize_preferences(preferences)
    title = _normalized(str(job.get("title", "")))
    company = _normalized(str(job.get("company", "")))
    location = _normalized(str(job.get("location", "")))
    modality = _normalized(str(job.get("modality", "")))
    searchable = _normalized(
        f"{job.get('title', '')}\n{job.get('description', '')}"
    )
    score = None if analysis is None else float(analysis.get("score", 0))

    discard_reasons: list[str] = []
    review_reasons: list[str] = []

    for excluded in prefs["excluded_companies"]:
        if _normalized(excluded) in company:
            discard_reasons.append(f"empresa excluida: {excluded}")
    for keyword in prefs["excluded_keywords"]:
        if _normalized(keyword) in searchable:
            discard_reasons.append(f"termo excluido encontrado: {keyword}")
    missing_required = [
        keyword
        for keyword in prefs["required_keywords"]
        if _normalized(keyword) not in searchable
    ]
    if missing_required:
        discard_reasons.append(
            "termos obrigatorios ausentes: " + ", ".join(missing_required)
        )
    if score is not None and score < prefs["minimum_score"]:
        discard_reasons.append(
            f"score {round(score)} abaixo do minimo {prefs['minimum_score']}"
        )
    if discard_reasons:
        return {"decision": "DESCARTAR", "reasons": discard_reasons}

    roles = [_normalized(value) for value in prefs["target_roles"]]
    if roles and not any(role in title or title in role for role in roles):
        review_reasons.append("cargo fora dos cargos preferidos")

    modalities = [_normalized(value) for value in prefs["modalities"]]
    if modalities and modality and not any(value in modality for value in modalities):
        review_reasons.append("modalidade fora das preferencias")

    locations = [_normalized(value) for value in prefs["locations"]]
    remote = "remot" in modality
    if locations and location and not remote and not any(
        value in location or location in value for value in locations
    ):
        review_reasons.append("localizacao fora das preferencias")

    if analysis is None:
        review_reasons.append("aderencia ainda nao analisada")
    if capture_confidence is not None and capture_confidence < 80:
        review_reasons.append("captura com confianca abaixo de 80%")

    can_be_automatic = (
        prefs["allow_automatic"]
        and score is not None
        and score >= prefs["automatic_score"]
        and not review_reasons
    )
    if can_be_automatic:
        return {
            "decision": "AUTOMATICA",
            "reasons": [
                f"score {round(score)} atingiu o limite automatico "
                f"de {prefs['automatic_score']}"
            ],
        }

    if not prefs["allow_automatic"]:
        review_reasons.append("automacao desativada pelo usuario")
    elif score is not None and score < prefs["automatic_score"]:
        review_reasons.append(
            f"score {round(score)} abaixo do limite automatico "
            f"{prefs['automatic_score']}"
        )
    return {"decision": "REVISAR", "reasons": review_reasons}
