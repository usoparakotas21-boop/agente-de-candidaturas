import re
import unicodedata
from typing import Any
from urllib.parse import unquote, urlparse

from .job_health import JobHealthEvaluator
from .job_health_integration import (
    evaluate_job_health,
    should_block_by_health,
    get_health_decision_override,
    enrich_job_with_health
)


ROLE_WORDS = (
    "analista",
    "assistente",
    "auxiliar",
    "coordenador",
    "coordenadora",
    "supervisor",
    "supervisora",
    "gerente",
    "especialista",
    "consultor",
    "consultora",
    "recruiter",
    "developer",
    "desenvolvedor",
    "engenheiro",
    "engineer",
    "manager",
    "coordinator",
    "business partner",
    "diretor",
    "diretora",
    "head de",
)

GENERIC_TITLES = {
    "oportunidade profissional",
    "oportunidades",
    "vaga",
    "vagas",
    "mais vagas",
    "vagas para voce",
    "recomendacoes de vagas",
    "alerta de vagas",
}

GENERIC_COMPANIES = {
    "empresa nao identificada",
    "empresa",
    "confidencial",
    "mais vagas",
    "vagas",
    "linkedin",
    "indeed",
    "gmail",
}

IGNORED_URL_MARKERS = (
    "unsubscribe",
    "descadastrar",
    "privacy",
    "privacidade",
    "preferences",
    "configuracoes",
    "account",
    "login",
    "help",
    "ajuda",
)

JOB_URL_MARKERS = (
    "/jobs/",
    "/job/",
    "/jobs/view/",
    "/vaga/",
    "/vagas/",
    "/vacancy/",
    "/position/",
    "/rc/clk",
    "viewjob",
    "jobid=",
    "job_id=",
    "jk=",
)


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(value.casefold().split())


def _clean_lines(content: str) -> list[str]:
    lines: list[str] = []
    previous = ""
    for raw_line in (content or "").splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line or line == previous:
            continue
        lines.append(line)
        previous = line
    return lines


def _urls(value: str) -> list[str]:
    return [
        url.rstrip(".,;:!?)\"]'")
        for url in re.findall(r"https?://[^\s<>\[\]\"']+", value, flags=re.I)
    ]


def is_probable_job_url(url: str) -> bool:
    lowered = unquote(url).casefold()
    if any(marker in lowered for marker in IGNORED_URL_MARKERS):
        return False
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    return any(marker in lowered for marker in JOB_URL_MARKERS)


def _probable_title_line(line: str) -> bool:
    normalized = _normalized(line)
    if not (3 <= len(line) <= 120) or normalized in GENERIC_TITLES:
        return False
    if len(line.split()) > 14 or line.endswith((".", ";", ":")):
        return False
    return any(role in normalized for role in ROLE_WORDS)


def split_job_alert(subject: str, content: str) -> list[str]:
    """Divide um alerta-resumo em blocos, mantendo uma vaga por bloco."""
    lines = _clean_lines(content)
    if not lines:
        return []

    subject = " ".join((subject or "").split()).strip()

    def with_subject(block_lines: list[str]) -> str:
        if (
            _probable_title_line(subject)
            and not any(_probable_title_line(line) for line in block_lines)
        ):
            block_lines = [subject, *block_lines]
        return "\n".join(block_lines).strip()

    url_indexes: list[int] = []
    seen_urls: set[str] = set()
    for index, line in enumerate(lines):
        job_urls = [url for url in _urls(line) if is_probable_job_url(url)]
        new_urls = [url for url in job_urls if url.casefold() not in seen_urls]
        if new_urls:
            url_indexes.append(index)
            seen_urls.update(url.casefold() for url in new_urls)

    if len(url_indexes) == 1:
        return [with_subject(lines)]

    if len(url_indexes) > 1:
        blocks: list[str] = []
        start = 0
        for position, url_index in enumerate(url_indexes):
            if position:
                start = url_indexes[position - 1] + 1
            block_lines = lines[start:url_index + 1]
            title_positions = [
                i for i, line in enumerate(block_lines) if _probable_title_line(line)
            ]
            if title_positions:
                block_lines = block_lines[max(0, title_positions[0] - 1):]
            block = with_subject(block_lines)
            if block:
                blocks.append(block)
        if blocks:
            return blocks

    title_indexes = [
        index for index, line in enumerate(lines) if _probable_title_line(line)
    ]
    if len(title_indexes) < 2:
        return [with_subject(lines)]

    blocks = []
    for position, start in enumerate(title_indexes):
        end = title_indexes[position + 1] if position + 1 < len(title_indexes) else len(lines)
        block = with_subject(lines[start:end])
        if len(block) >= 60:
            blocks.append(block)
    return blocks or [with_subject(lines)]


def assess_job_capture(parsed: dict[str, Any], history: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Pontua os campos essenciais e decide se a captura pode ser persistida.
    Inclui avaliação de saúde da vaga (v0.24.0).
    """
    title = str(parsed.get("title", "")).strip()
    company = str(parsed.get("company", "")).strip()
    description = str(parsed.get("description", "")).strip()
    url = str(parsed.get("url", "")).strip()
    normalized_title = _normalized(title)
    normalized_company = _normalized(company)

    # ========== AVALIAÇÃO DE SAÚDE DA VAGA (NOVO) ==========
    health_result = evaluate_job_health(parsed, history)
    health_override = get_health_decision_override(health_result)
    
    # Se a saúde for SUSPEITA, descarta imediatamente
    if health_override == "DESCARTAR":
        return {
            "confidence": 0,
            "field_confidence": {
                "title": 0,
                "company": 0,
                "description": 0,
                "url": 0,
            },
            "decision": "DESCARTAR",
            "reasons": ["Saúde da vaga suspeita - possível golpe ou vaga fantasma"],
            "health": {
                "score": health_result.score,
                "band": health_result.band,
                "fraud_suspected": health_result.fraud_suspected,
                "signals": [
                    {"code": s.code, "label": s.label, "group": s.group, 
                     "adjustment": s.adjustment, "evidence": s.evidence}
                    for s in health_result.signals
                ]
            }
        }
    
    # ========== AVALIAÇÃO DE QUALIDADE (EXISTENTE) ==========
    if normalized_title in GENERIC_TITLES or len(title) < 3:
        title_score = 0
    elif any(role in normalized_title for role in ROLE_WORDS):
        title_score = 95
    else:
        title_score = 60

    if normalized_company in GENERIC_COMPANIES or len(company) < 2:
        company_score = 0
    elif len(company) <= 100:
        company_score = 85
    else:
        company_score = 50

    normalized_description = _normalized(description)
    job_signals = sum(
        marker in normalized_description
        for marker in ("requisit", "responsabil", "experien", "beneficio", "atividad")
    )
    if len(description) >= 400:
        description_score = min(100, 75 + (job_signals * 5))
    elif len(description) >= 180:
        description_score = min(85, 55 + (job_signals * 6))
    elif len(description) >= 80:
        description_score = 42
    else:
        description_score = 10

    if is_probable_job_url(url):
        url_score = 95
    elif urlparse(url).scheme in {"http", "https"} and urlparse(url).netloc:
        url_score = 55
    else:
        url_score = 0

    field_confidence = {
        "title": title_score,
        "company": company_score,
        "description": description_score,
        "url": url_score,
    }
    confidence = round(
        title_score * 0.25
        + company_score * 0.20
        + description_score * 0.35
        + url_score * 0.20
    )

    reasons: list[str] = []
    labels = {
        "title": "cargo",
        "company": "empresa",
        "description": "descricao",
        "url": "URL",
    }
    for field, score in field_confidence.items():
        if score < 50:
            reasons.append(f"{labels[field]} com baixa confianca")

    # ========== DECISÃO FINAL ==========
    # Se a saúde for DUVIDOSA, força REVISAR
    if health_override == "REVISAR":
        decision = "REVISAR"
        reasons.append("Saúde da vaga duvidosa - requer revisão")
    elif title_score < 40 or description_score < 35 or confidence < 45:
        decision = "DESCARTAR"
    elif confidence < 72 or company_score < 50 or url_score < 50:
        decision = "REVISAR"
    else:
        decision = "CAPTURAR"

    # ========== RESULTADO ==========
    result = {
        "confidence": confidence,
        "field_confidence": field_confidence,
        "decision": decision,
        "reasons": reasons,
        "health": {
            "score": health_result.score,
            "band": health_result.band,
            "fraud_suspected": health_result.fraud_suspected,
            "signals": [
                {"code": s.code, "label": s.label, "group": s.group, 
                 "adjustment": s.adjustment, "evidence": s.evidence}
                for s in health_result.signals
            ]
        }
    }
    
    return result