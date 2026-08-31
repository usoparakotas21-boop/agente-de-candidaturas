import hashlib
import html
import re
import unicodedata
from typing import Any
from urllib.parse import urlparse


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
    value = html.unescape(raw_text or "")
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", "\n", value)
    value = value.replace("\x00", " ")
    lines = [" ".join(line.split()) for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


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
            r"linkedin\.com|indeed\.com)/[^\s<>\]\[\)\(\"']+",
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


def _fallback_title(lines: list[str]) -> str:
    for line in lines[:40]:
        normalized = _normalized(line)
        if 3 <= len(line) <= 120 and any(word in normalized for word in ROLE_WORDS):
            if not any(prefix in normalized for prefix in ("experiencia como", "procuramos por", "requisitos")):
                return re.sub(r"^(vaga|oportunidade)\s*[:\-]\s*", "", line, flags=re.I).strip()
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
        if len(parts) >= 2 and parts[-2] not in {"linkedin", "indeed", "gupy"}:
            return parts[-2].replace("-", " ").title()
    return "Empresa nao identificada"


def _extract_location(lines: list[str], text: str) -> str:
    labeled = _labeled_value(lines, ("Localizacao", "Local", "Cidade"))
    if labeled:
        return labeled
    city_state = re.search(
        r"\b([^\W\d_][\w' -]{2,40})\s*[/,-]\s*([A-Z]{2})\b",
        text,
    )
    if city_state:
        return f"{city_state.group(1).strip()}/{city_state.group(2)}"
    city_country = re.search(
        r"\b([^\W\d_][\w' -]{2,40})\s*,\s*Brasil\b",
        text,
    )
    return f"{city_country.group(1).strip()}, Brasil" if city_country else ""


def _extract_modality(lines: list[str], text: str) -> str:
    labeled = _labeled_value(lines, ("Modalidade", "Modelo de trabalho"))
    normalized = _normalized(labeled or text)
    if "hibrid" in normalized:
        return "Hibrido"
    if "remot" in normalized or "home office" in normalized:
        return "Remoto"
    if "presencial" in normalized:
        return "Presencial"
    return labeled


def _extract_salary(lines: list[str], text: str) -> str:
    labeled = _labeled_value(lines, ("Salario", "Faixa salarial", "Remuneracao"))
    if labeled:
        return labeled
    match = re.search(
        r"R\$\s*[\d.]+(?:,\d{2})?(?:\s*(?:a|-|ate)\s*R?\$?\s*[\d.]+(?:,\d{2})?)?",
        text,
        flags=re.I,
    )
    return match.group(0) if match else ""


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
    title = _extend_title(lines, title)
    if not company:
        company = _fallback_company(lines, title, url)

    location = _extract_location(lines, text)
    modality = _extract_modality(lines, text)
    salary = _extract_salary(lines, text)
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
        "salary": salary,
        "url": url,
        "description": description,
    }
