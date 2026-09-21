import re
import unicodedata
from typing import Any


DEFAULT_MINIMUM_SCORE = 65
DEFAULT_AUTOMATIC_SCORE = 85
HEURISTICS_VERSION = "br-rh-2"


def _decision_result(
    decision: str,
    reasons: list[str],
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Retorna a decisão com versão e códigos estáveis para auditoria."""
    return {
        "decision": decision,
        "reasons": reasons,
        "reason_codes": list(dict.fromkeys(reason_codes or [])),
        "heuristics_version": HEURISTICS_VERSION,
    }


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(value.casefold().split())


def _contains_term(value: str, term: str) -> bool:
    """Match a normalized word/phrase boundary, avoiding accidental substrings."""
    normalized_value = _normalized(value)
    normalized_term = _normalized(term)
    if not normalized_value or not normalized_term:
        return False
    return bool(
        re.search(
            rf"(?<!\w){re.escape(normalized_term)}(?!\w)",
            normalized_value,
        )
    )


def _contract_family(value: str) -> str:
    normalized = _normalized(value)
    if normalized in {"pj", "pessoa juridica", "pessoa juridica (pj)"}:
        return "pj"
    if normalized in {"clt", "mei", "estagio", "temporario", "freelance"}:
        return normalized
    return normalized


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
        "contract_types": [],
        "schedules": [],
        "industries": [],
        "excluded_companies": [],
        "required_keywords": [],
        "excluded_keywords": [],
        "minimum_score": DEFAULT_MINIMUM_SCORE,
        "automatic_score": DEFAULT_AUTOMATIC_SCORE,
        "allow_automatic": False,
        "max_daily_applications": 5,
        "salary_min": None,
        "salary_max": None,
        "notification_frequency": "daily",
        "notify_interviews": False,
        "notify_interviews_consent_at": None,
        "notify_expiring": False,
        "notify_followups": False,
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
        "contract_types",
        "schedules",
        "industries",
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
    frequency = str(supplied.get("notification_frequency", "daily")).strip().casefold()
    result["notification_frequency"] = frequency if frequency in {"daily", "immediate", "weekly", "none"} else "daily"
    interview_consent = supplied.get("notify_interviews_consent_at")
    result["notify_interviews_consent_at"] = interview_consent if isinstance(interview_consent, str) and interview_consent.strip() else None
    result["notify_interviews"] = bool(supplied.get("notify_interviews", False) and result["notify_interviews_consent_at"])
    result["notify_expiring"] = bool(supplied.get("notify_expiring", False))
    consented_at = supplied.get("notify_followups_consent_at")
    result["notify_followups_consent_at"] = consented_at if isinstance(consented_at, str) and consented_at.strip() else None
    result["notify_followups"] = bool(supplied.get("notify_followups", False) and result["notify_followups_consent_at"])
    for field in ("salary_min", "salary_max"):
        try:
            value = supplied.get(field)
            result[field] = int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            result[field] = None
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
    discard_codes: list[str] = []
    review_reasons: list[str] = []
    review_codes: list[str] = []

    for excluded in prefs["excluded_companies"]:
        if _contains_term(company, excluded):
            discard_reasons.append(f"empresa excluida: {excluded}")
            discard_codes.append("COMPANY_EXCLUDED")
    for keyword in prefs["excluded_keywords"]:
        if _contains_term(searchable, keyword):
            discard_reasons.append(f"termo excluido encontrado: {keyword}")
            discard_codes.append("EXCLUDED_KEYWORD_FOUND")
    missing_required = [
        keyword
        for keyword in prefs["required_keywords"]
        if not _contains_term(searchable, keyword)
    ]
    if missing_required:
        discard_reasons.append(
            "termos obrigatorios ausentes: " + ", ".join(missing_required)
        )
        discard_codes.append("REQUIRED_KEYWORD_MISSING")
    if score is not None and score < prefs["minimum_score"]:
        discard_reasons.append(
            f"score {round(score)} abaixo do minimo {prefs['minimum_score']}"
        )
        discard_codes.append("MATCH_BELOW_MINIMUM")
    if discard_reasons:
        return _decision_result("DESCARTAR", discard_reasons, discard_codes)

    roles = [_normalized(value) for value in prefs["target_roles"]]
    if roles and not title:
        review_reasons.append("cargo nao informado; preferencia nao pode ser verificada")
        review_codes.append("ROLE_UNVERIFIED")
    elif roles and not any(
        _contains_term(title, role) or _contains_term(role, title)
        for role in roles
    ):
        review_reasons.append("cargo fora dos cargos preferidos")
        review_codes.append("ROLE_PREFERENCE_MISMATCH")

    modalities = [_normalized(value) for value in prefs["modalities"]]
    if modalities and not modality:
        review_reasons.append("modalidade nao informada; preferencia nao pode ser verificada")
        review_codes.append("MODALITY_UNVERIFIED")
    elif modalities and not any(_contains_term(modality, value) for value in modalities):
        review_reasons.append("modalidade fora das preferencias")
        review_codes.append("MODALITY_PREFERENCE_MISMATCH")

    locations = [_normalized(value) for value in prefs["locations"]]
    remote = "remot" in modality
    if locations and not remote and not location:
        review_reasons.append("localizacao nao informada; preferencia nao pode ser verificada")
        review_codes.append("LOCATION_UNVERIFIED")
    elif locations and not remote and not any(
        _contains_term(location, value) or _contains_term(value, location)
        for value in locations
    ):
        review_reasons.append("localizacao fora das preferencias")
        review_codes.append("LOCATION_PREFERENCE_MISMATCH")

    # Preferências adicionais permanecem sinais suaves. Regime usa o campo
    # estruturado persistido pelo intake; sem dado estruturado, não inferimos.
    contract_preferences = prefs.get("contract_types", [])
    contract_type = str(job.get("contract_type", "") or "")
    if contract_preferences and not contract_type:
        review_reasons.append("tipo de contrato nao informado; preferencia nao pode ser verificada")
        review_codes.append("CONTRACT_TYPE_UNVERIFIED")
    elif contract_preferences and _contract_family(contract_type) not in {
        _contract_family(value) for value in contract_preferences
    }:
        review_reasons.append("tipo de contrato fora das preferencias")
        review_codes.append("CONTRACT_TYPE_PREFERENCE_MISMATCH")

    # Há preferências livres de horário/setor, mas ainda não há campos
    # estruturados no anúncio. A falta da expressão é desconhecida, não prova
    # incompatibilidade; encaminha para revisão sem descartar.
    for field, label, code in (
        ("schedules", "horario", "SCHEDULE_UNVERIFIED"),
        ("industries", "setor", "INDUSTRY_UNVERIFIED"),
    ):
        values = prefs.get(field, [])
        if values and not any(_contains_term(searchable, value) for value in values):
            review_reasons.append(f"{label} nao identificado; preferencia nao pode ser verificada")
            review_codes.append(code)
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")
    if salary_min is None and salary_max is None:
        salary_text = str(job.get("salary", ""))
        salary_values = []
        for raw in re.findall(r"\d[\d.]*", salary_text):
            try:
                salary_values.append(float(raw.replace(".", "")))
            except ValueError:
                pass
        if salary_values:
            salary_min, salary_max = min(salary_values), max(salary_values)
    if salary_max is not None and prefs.get("salary_min") is not None and salary_max < prefs["salary_min"]:
        review_reasons.append("faixa salarial abaixo da preferência")
        review_codes.append("SALARY_BELOW_PREFERENCE")
    if salary_min is not None and prefs.get("salary_max") is not None and salary_min > prefs["salary_max"]:
        review_reasons.append("faixa salarial acima da preferência")
        review_codes.append("SALARY_ABOVE_PREFERENCE")
    if (
        (prefs.get("salary_min") is not None or prefs.get("salary_max") is not None)
        and salary_min is None
        and salary_max is None
    ):
        review_reasons.append("faixa salarial nao informada; preferencia nao pode ser verificada")
        review_codes.append("SALARY_UNVERIFIED")

    if analysis is None:
        review_reasons.append("aderencia ainda nao analisada")
        review_codes.append("ANALYSIS_PENDING")
    if capture_confidence is not None and capture_confidence < 80:
        review_reasons.append("captura com confianca abaixo de 80%")
        review_codes.append("CAPTURE_CONFIDENCE_LOW")

    can_be_automatic = (
        prefs["allow_automatic"]
        and score is not None
        and score >= prefs["automatic_score"]
        and not review_reasons
    )
    if can_be_automatic:
        return _decision_result(
            "AUTOMATICA",
            [
                f"score {round(score)} atingiu o limite automatico "
                f"de {prefs['automatic_score']}"
            ],
            ["AUTOMATIC_SCORE_REACHED"],
        )

    if not prefs["allow_automatic"]:
        review_reasons.append("automacao desativada pelo usuario")
        review_codes.append("AUTOMATION_DISABLED")
    elif score is not None and score < prefs["automatic_score"]:
        review_reasons.append(
            f"score {round(score)} abaixo do limite automatico "
            f"{prefs['automatic_score']}"
        )
        review_codes.append("MATCH_BELOW_AUTOMATIC_THRESHOLD")
    return _decision_result("REVISAR", review_reasons, review_codes)
