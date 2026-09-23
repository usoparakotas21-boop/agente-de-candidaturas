import re
import unicodedata
from typing import Any
from urllib.parse import unquote, urlparse

from .decision_engine import HEURISTICS_VERSION
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
    "recrutador",
    "recrutadora",
    "estagiario",
    "estagiaria",
    "aprendiz",
    "tecnico",
    "tecnica",
    "engenheiro",
    "engenheira",
    "desenvolvedor",
    "desenvolvedora",
    "vendedor",
    "vendedora",
    "operador",
    "operadora",
    "recepcionista",
    "atendente",
    "motorista",
    "professor",
    "professora",
    "advogado",
    "advogada",
    "designer",
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
    "/job-listing/",
    "/joblisting",
    "/jobs/view/",
    "/vaga/",
    "/vagas/",
    "/cargos/",
    "/vacancy/",
    "/position/",
    "/rc/clk",
    "viewjob",
    "jobid=",
    "job_id=",
    "jk=",
)

# Source attribution is only inferred from a validated sender domain or a
# provider-specific job URL. Mentions of a brand in an email footer/body are
# not enough to claim that it supplied the opportunity.
JOB_SOURCE_DOMAINS = {
    "linkedin.com": "linkedin",
    "lnkd.in": "linkedin",
    "indeed.com": "indeed",
    "indeed.com.br": "indeed",
    "gupy.io": "gupy",
    "glassdoor.com": "glassdoor",
    "glassdoor.com.br": "glassdoor",
    "infojobs.com.br": "infojobs",
    "bebee.com": "bebee",
    "catho.com.br": "catho",
    "vagas.com.br": "vagas.com",
    "empregos.com.br": "empregos",
    "solides.com.br": "solides",
    "jobbol.com.br": "jobbol",
}

_PROVIDER_JOB_PATHS = {
    "linkedin.com": (r"/jobs/view/",),
    "indeed.com": (r"/rc/clk(?:/|$)", r"/viewjob(?:/|$)", r"/job(?:/|$)"),
    "indeed.com.br": (r"/rc/clk(?:/|$)", r"/viewjob(?:/|$)", r"/job(?:/|$)"),
    "glassdoor.com": (r"/job-listing/", r"/partner/joblisting\.htm"),
    "glassdoor.com.br": (r"/job-listing/", r"/partner/joblisting\.htm"),
    "gupy.io": (r"/jobs?/", r"/vaga/"),
    "bebee.com": (r"/br/jobs?/", r"/jobs?/"),
    "jobbol.com.br": (r"/cargos/", r"/vagas?/"),
    "catho.com.br": (r"/vagas?/", r"/cargos?/"),
    "vagas.com.br": (r"/vagas?/", r"/perfil/"),
    "infojobs.com.br": (r"/vagas?/", r"/ofertas?/"),
    "empregos.com.br": (r"/vagas?/", r"/empresa/"),
    "solides.com.br": (r"/vagas?/", r"/vaga/"),
}


def _host_matches(hostname: str, domain: str) -> bool:
    return hostname == domain or hostname.endswith("." + domain)


def job_source_from_url(url: str) -> str | None:
    """Return a known job-board source only for an actual URL host."""
    try:
        parsed = urlparse(url)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        hostname = parsed.hostname.casefold().rstrip(".")
    except (TypeError, ValueError):
        return None
    return next(
        (source for domain, source in JOB_SOURCE_DOMAINS.items() if _host_matches(hostname, domain)),
        None,
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
    if not isinstance(url, str) or not url:
        return False
    lowered = unquote(url).casefold()
    if any(marker in lowered for marker in IGNORED_URL_MARKERS):
        return False
    try:
        parsed = urlparse(url)
        if (
            parsed.scheme.casefold() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return False
        hostname = parsed.hostname.casefold().rstrip(".")
    except (TypeError, ValueError):
        return False
    for domain, patterns in _PROVIDER_JOB_PATHS.items():
        if _host_matches(hostname, domain):
            path = unquote(parsed.path).casefold()
            query = parsed.query.casefold()
            if domain == "indeed.com" and ("jk=" in query or "jobkey=" in query):
                return True
            return any(re.search(pattern, path) for pattern in patterns)
    return any(marker in lowered for marker in JOB_URL_MARKERS)


def _probable_title_line(line: str) -> bool:
    normalized = _normalized(line)
    if not (3 <= len(line) <= 120) or normalized in GENERIC_TITLES:
        return False
    if len(line.split()) > 14 or line.endswith((".", ";", ":")):
        return False
    if re.match(
        r"^(?:experiencia|requisitos|responsabilidades|responsabilidade|"
        r"atribuicoes|atividades|qualificacoes|buscamos|procuramos por)\b",
        normalized,
    ):
        return False
    return any(
        re.search(
            rf"(?<!\w){re.escape(role)}s?(?!\w)",
            normalized,
        )
        for role in ROLE_WORDS
    )


def is_grouped_job_summary(subject: str, content: str) -> bool:
    """Identifica alertas que anunciam várias vagas sem entregar um anúncio único."""
    sample = "\n".join([subject or "", *(content or "").splitlines()[:12]])
    normalized = _normalized(sample)
    return bool(re.search(r"\b(?:[2-9]|[1-9]\d+)\s+vagas?\s+abertas?\b", normalized))


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
            "heuristics_version": HEURISTICS_VERSION,
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
    if normalized_title in GENERIC_TITLES or len(title) < 3:
        decision = "DESCARTAR"
    elif health_override == "REVISAR":
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
        "heuristics_version": HEURISTICS_VERSION,
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
