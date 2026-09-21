import hashlib
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse

from .text_sanitization import sanitize_untrusted_text


MAX_INTAKE_CHARS = 80_000
MIN_INTAKE_CHARS = 60

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
    "business partner",
    "head",
    "diretor",
    "diretora",
    "recruiter",
)

COMPANY_NOISE = {
    "entra",
    "entrar",
    "candidatar",
    "candidate-se",
    "salvar",
    "compartilhar",
    "voltar",
    "vagas",
    "pessoas",
    "servicos",
    "curriculo",
    "blog",
    "descricao da vaga",
    "descricao",
    "requisitos",
    "o que buscamos",
    "missao do cargo",
    "grandes desafios da posicao",
    "condicoes e beneficios",
    "beneficios",
    "local da vaga",
    "responsabilidades",
    "atribuicoes",
}

TITLE_CONTINUATIONS = {
    "generalista",
    "junior",
    "jr",
    "pleno",
    "senior",
    "sr",
    "i",
    "ii",
    "iii",
}


def _normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(value.casefold().split())


def _clean_text(raw_text: str) -> str:
    return sanitize_untrusted_text(raw_text)


def _labeled_value(lines: list[str], labels: tuple[str, ...]) -> str:
    normalized_labels = tuple(_normalized(label) for label in labels)
    for index, line in enumerate(lines):
        normalized_line = _normalized(line)
        for label in normalized_labels:
            match = re.match(rf"^{re.escape(label)}\s*[:\-]\s*(.+)$", normalized_line)
            if match:
                separator = re.search(r"[:\-]", line)
                return line[separator.end():].strip() if separator else match.group(1).strip()
            if normalized_line == label and index + 1 < len(lines):
                return lines[index + 1]
    return ""


def _extract_url(text: str) -> str:
    urls = re.findall(r"https?://[^\s<>\]\[\)\(\"']+", text, flags=re.I)
    if not urls:
        naked_urls = re.findall(
            r"(?<!@)\b(?:www\.)?(?:bebee\.com|(?:[a-z0-9-]+\.)?gupy\.io|"
            r"linkedin\.com|(?:[a-z0-9-]+\.)?indeed\.com|"
            r"glassdoor\.com(?:\.br)?|infojobs\.com\.br|"
            r"catho\.com\.br|vagas\.com\.br|jobbol\.com\.br)/[^\s<>\]\[\)\(\"']+",
            text,
            flags=re.I,
        )
        urls = [f"https://{value}" for value in naked_urls]
    if not urls:
        return ""
    preferred_hosts = ("gupy.io", "linkedin.com", "indeed.com", "jobs.", "careers.")
    for url in urls:
        if any(host in url.casefold() for host in preferred_hosts):
            return url.rstrip(".,;:")
    for url in urls:
        lowered = url.casefold()
        if not any(word in lowered for word in ("unsubscribe", "descadastrar", "privacy")):
            return url.rstrip(".,;:")
    return urls[0].rstrip(".,;:")


def _title_from_url(value: str) -> str:
    """Converte uma URL de anúncio em um título legível quando necessário."""
    candidate = (value or "").strip()
    if not re.match(r"^https?://", candidate, flags=re.I):
        return ""
    parsed = urlparse(candidate)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if not segments:
        return ""
    slug = re.sub(r"[-_]+", " ", segments[-1])
    slug = re.sub(r"\b(?:vaga|job|jobs|view|position|vacancy)\b", " ", slug, flags=re.I)
    slug = re.sub(r"\b\d{2,}\b", " ", slug)
    slug = " ".join(slug.split()).strip(" -")
    return slug.title() if slug else ""


def _normalize_company_name(value: str) -> str:
    """Remove prefixos de CNPJ que poluem o nome exibido da empresa."""
    original = (value or "").strip()
    normalized = re.sub(
        r"^\s*\d{1,3}(?:\.\d{3}){1,3}(?:[-/]\d{1,2})?\s+",
        "",
        original,
    )
    return normalized or original


def _clean_alert_title(value: str) -> str:
    """Remove saudações e frases de alerta que antecedem o cargo real."""
    title = (value or "").strip()
    normalized = _normalized(title)
    alert_prefixes = (
        "ola ",
        "olá ",
        "temos novas vagas",
        "novas vagas de",
        "vagas recomendadas",
        "veja vagas",
    )
    if not any(prefix in normalized for prefix in alert_prefixes):
        return title
    match = re.search(
        r"\b(?:analista|assistente|auxiliar|coordenador(?:a)?|supervisor(?:a)?|gerente|especialista|consultor(?:a)?|business partner|head|diretor(?:a)?|recruiter)\b.*",
        title,
        flags=re.I,
    )
    return match.group(0).strip(" -:,") if match else title


def _fallback_title(lines: list[str]) -> str:
    for line in lines[:40]:
        normalized = _normalized(line)
        if 3 <= len(line) <= 120 and any(word in normalized for word in ROLE_WORDS):
            if not any(prefix in normalized for prefix in ("experiencia como", "procuramos por", "requisitos")):
                title = re.sub(r"^(vaga|oportunidade)\s*[:\-]\s*", "", line, flags=re.I).strip()
                return _clean_alert_title(title)
    return "Oportunidade profissional"


def _extend_title(lines: list[str], title: str) -> str:
    title_index = next(
        (i for i, line in enumerate(lines) if _normalized(line) == _normalized(title)),
        -1,
    )
    if title_index < 0 or title_index + 1 >= len(lines):
        return title
    continuation = lines[title_index + 1].strip()
    if _normalized(continuation) in TITLE_CONTINUATIONS:
        return f"{title} {continuation}"
    return title


def _fallback_company(lines: list[str], title: str, url: str) -> str:
    normalized_title = _normalized(title)
    title_index = next(
        (
            i
            for i, line in enumerate(lines)
            if normalized_title == _normalized(line)
            or normalized_title.startswith(f"{_normalized(line)} ")
        ),
        -1,
    )
    if title_index >= 0:
        company_start = title_index + 1
        if company_start < len(lines):
            continuation = _normalized(lines[company_start])
            if continuation in TITLE_CONTINUATIONS and normalized_title.endswith(
                f" {continuation}"
            ):
                company_start += 1
        nearby = (
            lines[company_start:company_start + 4]
            + lines[max(0, title_index - 4):title_index]
        )
        for candidate in nearby:
            normalized = _normalized(candidate)
            if normalized in COMPANY_NOISE:
                continue
            if any(
                noise in normalized
                for noise in ("tempo integral", "presencial", "remoto", "hibrido")
            ):
                continue
            if re.search(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", candidate):
                continue
            if (
                2 <= len(candidate) <= 100
                and not any(word in normalized for word in ROLE_WORDS)
            ):
                return candidate
    if url:
        host = urlparse(url).hostname or ""
        host = host.removeprefix("www.")
        parts = host.split(".")
        provider_domains = (
            "linkedin.com", "lnkd.in", "indeed.com", "gupy.io", "glassdoor.com",
            "glassdoor.com.br", "infojobs.com.br", "bebee.com", "catho.com.br",
            "vagas.com.br", "jobbol.com.br", "empregos.com.br", "solides.com",
            "kenoby.com",
        )
        is_provider = any(host == domain or host.endswith("." + domain) for domain in provider_domains)
        if is_provider:
            return "Empresa nao identificada"
        # For Brazilian company domains such as careers.empresa.com.br, the
        # employer label is third from the end, not the generic `com` label.
        company_part = parts[-3] if host.endswith(".com.br") and len(parts) >= 3 else (parts[-2] if len(parts) >= 2 else "")
        if company_part:
            return company_part.replace("-", " ").title()
    return "Empresa nao identificada"


def _extract_location(lines: list[str], text: str) -> str:
    labeled = _labeled_value(lines, ("Localizacao", "Local", "Cidade"))
    if labeled:
        return labeled
    city_states = re.findall(
        r"\b([^\W\d_][\w' -]{2,40}?)\s*[/,-]\s*([A-Z]{2})\b",
        text,
    )
    # A title may end immediately before the location (for example,
    # "Analista de RH - Salvador/BA"). Do not turn the whole prefix into a
    # city; an explicit Local:/Cidade: label above remains authoritative.
    role_prefix = re.compile(
        r"\b(?:analista|assistente|auxiliar|coordenador(?:a)?|supervisor(?:a)?|"
        r"gerente|especialista|consultor(?:a)?|recruiter|recrutador(?:a)?|"
        r"business partner|head|diretor(?:a)?|estagiari[oa]|aprendiz|"
        r"tecnic[oa]|engenheir[oa]|desenvolvedor(?:a)?)\b",
        flags=re.I,
    )
    city_states = [
        (city, state)
        for city, state in city_states
        if not role_prefix.search(city)
    ]
    unique_city_states = {
        (city.strip().casefold(), state.upper()): f"{city.strip()}/{state.upper()}"
        for city, state in city_states
    }
    if len(unique_city_states) == 1:
        return next(iter(unique_city_states.values()))
    if len(unique_city_states) > 1:
        return ""
    city_country = re.search(
        r"\b([^\W\d_][\w' -]{2,40})\s*,\s*Brasil\b",
        text,
    )
    return f"{city_country.group(1).strip()}, Brasil" if city_country else ""


def _extract_modality(lines: list[str], text: str) -> str:
    labeled = _labeled_value(lines, ("Modalidade", "Modelo de trabalho"))
    normalized = _normalized(labeled or text)
    matches = set()
    if re.search(r"\bhibrid\w*\b", normalized):
        matches.add("Hibrido")
    if re.search(r"\b(?:remot\w*|home office)\b", normalized):
        matches.add("Remoto")
    if re.search(r"\bpresencial\b", normalized):
        matches.add("Presencial")
    # A conflicting field or a description that merely lists several models
    # does not tell us which one belongs to this specific job.
    return next(iter(matches)) if len(matches) == 1 else ""


def _extract_salary(lines: list[str], text: str) -> str:
    labeled = _labeled_value(lines, ("Salario", "Faixa salarial", "Remuneracao"))
    if labeled:
        return labeled
    matches = re.findall(
        r"R\$\s*[\d.]+(?:,\d{2})?(?:\s*(?:a|-|ate)\s*R?\$?\s*[\d.]+(?:,\d{2})?)?",
        text,
        flags=re.I,
    )
    # Without a salary label, multiple currency values can refer to benefits,
    # fees, or unrelated amounts. Keep that field unknown for manual review.
    return matches[0] if len(matches) == 1 else ""


def _salary_bounds(value: str) -> tuple[int | None, int | None]:
    """Return offered salary bounds in whole BRL, keeping candidate preferences separate."""
    numbers: list[int] = []
    for raw in re.findall(r"\d[\d.]*", value or ""):
        try:
            parsed = int(raw.replace(".", ""))
        except ValueError:
            continue
        if parsed >= 100:
            numbers.append(parsed)
    if not numbers:
        return None, None
    return min(numbers), max(numbers)


def _extract_contract_type(lines: list[str], text: str) -> str:
    """Classifica o regime brasileiro mais explícito no anúncio."""
    labeled = _labeled_value(lines, ("Regime", "Tipo de contrato", "Contrato", "Modelo de contratação"))
    normalized = _normalized(labeled or text)
    patterns = (
        (r"\bclt\b", "CLT"),
        (r"\b(?:pj|pessoa juridica)\b", "PJ"),
        (r"\bmei\b", "MEI"),
        (r"\bestagio\b", "Estágio"),
        (r"\btemporar\w*\b", "Temporário"),
        (r"\bfreelance\b", "Freelance"),
    )
    matches = {label for pattern, label in patterns if re.search(pattern, normalized)}
    return next(iter(matches)) if len(matches) == 1 else ""


def _field_confidence(lines: list[str], labels: tuple[str, ...], value: str, text: str) -> int:
    if not value:
        return 0
    if _labeled_value(lines, labels):
        return 95
    return 75


def parse_job_text(raw_text: str, source: str = "texto") -> dict:
    """
    Extrai informações de uma vaga a partir do texto bruto.
    Versão melhorada com reconhecimento de título e empresa.
    """
    text = _clean_text(raw_text)
    if len(text) < MIN_INTAKE_CHARS:
        raise ValueError("Texto da vaga muito curto.")
    if len(text) > MAX_INTAKE_CHARS:
        text = text[:MAX_INTAKE_CHARS]

    lines = text.splitlines()
    title = _labeled_value(lines, ("Cargo", "Titulo", "Título", "Vaga"))
    company = _labeled_value(lines, ("Empresa", "Companhia"))
    url = _extract_url(text)

    if not title:
        title = _fallback_title(lines)
    title = _title_from_url(title) or _clean_alert_title(title)
    title = _extend_title(lines, title)
    if not company:
        company = _fallback_company(lines, title, url)
    company = _normalize_company_name(company)

    location = _extract_location(lines, text)
    modality = _extract_modality(lines, text)
    salary = _extract_salary(lines, text)
    salary_min, salary_max = _salary_bounds(salary)
    contract_type = _extract_contract_type(lines, text)
    description = text

    # O identificador é determinístico: a mesma vaga, recebida por fontes
    # diferentes, cai no mesmo item de fila.
    fingerprint = "|".join((_normalized(title), _normalized(company), _normalized(url or location)))
    external_id = f"intake-{hashlib.sha256(fingerprint.encode()).hexdigest()[:24]}"
    
    return {
        "source": source,
        "external_id": external_id,
        "title": title,
        "company": company,
        "location": location,
        "modality": modality,
        "modality_confidence": _field_confidence(lines, ("Modalidade", "Modelo de trabalho"), modality, text),
        "salary": salary,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_confidence": _field_confidence(lines, ("Salario", "Faixa salarial", "Remuneracao"), salary, text),
        "contract_type": contract_type,
        "contract_confidence": _field_confidence(lines, ("Regime", "Tipo de contrato", "Contrato", "Modelo de contratação"), contract_type, text),
        "url": url,
        "description": description,
    }
