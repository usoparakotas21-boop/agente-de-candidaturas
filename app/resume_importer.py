import io
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Any

from docx import Document
from pypdf import PdfReader


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 25 * 1024 * 1024
MAX_ZIP_ENTRIES = 1000


def _normalized_heading(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return " ".join(value.upper().split())


def _validate_docx(content: bytes) -> None:
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("O arquivo deve ter no maximo 5 MB.")

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES:
                raise ValueError("O documento possui arquivos internos demais.")
            if sum(entry.file_size for entry in entries) > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("O documento descompactado excede 25 MB.")
            names = {entry.filename for entry in entries}
            if "word/document.xml" not in names:
                raise ValueError("O arquivo nao possui uma estrutura DOCX valida.")
    except zipfile.BadZipFile as exc:
        raise ValueError("O arquivo enviado nao e um DOCX valido.") from exc


def _section_ranges(lines: list[dict[str, str]]) -> dict[str, tuple[int, int]]:
    headings = {
        "RESUMO PROFISSIONAL": "summary",
        "COMPETENCIAS TECNICAS": "skills",
        "EXPERIENCIA PROFISSIONAL": "experiences",
        "EXPERIENCIAS PROFISSIONAIS": "experiences",
        "EXPERIENCIAS PROFISSIONAL": "experiences",
        "FORMACAO ACADEMICA": "education",
        "IDIOMAS": "languages",
    }
    found: list[tuple[int, str]] = []
    for index, item in enumerate(lines):
        key = headings.get(_normalized_heading(item["text"]))
        if key:
            found.append((index, key))

    ranges: dict[str, tuple[int, int]] = {}
    for position, (start, key) in enumerate(found):
        end = found[position + 1][0] if position + 1 < len(found) else len(lines)
        ranges[key] = (start + 1, end)
    return ranges


def _slice(
    lines: list[dict[str, str]],
    ranges: dict[str, tuple[int, int]],
    key: str,
) -> list[dict[str, str]]:
    start, end = ranges.get(key, (0, 0))
    return lines[start:end]


def _parse_experiences(items: list[dict[str, str]]) -> list[dict[str, Any]]:
    experiences: list[dict[str, Any]] = []
    index = 0
    while index < len(items):
        if items[index]["is_bullet"]:
            index += 1
            continue

        company = items[index]["text"]
        index += 1
        if index >= len(items) or items[index]["is_bullet"]:
            continue

        role_line = items[index]["text"]
        index += 1
        role, _, period = role_line.partition("|")
        bullets: list[str] = []
        while index < len(items) and items[index]["is_bullet"]:
            bullets.append(items[index]["text"])
            index += 1

        start_date = period.strip()
        end_date = ""
        parts = re.split(r"\s+[\u2013\u2014-]\s+", period.strip(), maxsplit=1)
        if len(parts) == 2:
            start_date, end_date = parts

        experiences.append(
            {
                "company": company,
                "role": role.strip(),
                "period": period.strip(),
                "start_date": start_date.strip(),
                "end_date": end_date.strip(),
                "bullets": bullets,
                "description": "\n".join(bullets),
            }
        )
    return experiences


def _parse_education(items: list[dict[str, str]]) -> list[dict[str, str]]:
    values = [item["text"] for item in items if not item["is_bullet"]]
    education: list[dict[str, str]] = []
    for index in range(0, len(values), 2):
        course = values[index]
        institution_line = values[index + 1] if index + 1 < len(values) else ""
        institution, _, period = institution_line.partition("—")
        if not period:
            institution, _, period = institution_line.partition("–")
        education.append(
            {
                "course": course.strip(),
                "institution": institution.strip(),
                "period": period.strip(),
            }
        )
    return education


def parse_resume_docx(content: bytes, filename: str) -> dict[str, Any]:
    if Path(filename).suffix.lower() != ".docx":
        raise ValueError("Nesta versao, envie um curriculo em formato DOCX.")
    _validate_docx(content)

    try:
        document = Document(io.BytesIO(content))
    except Exception as exc:
        raise ValueError("Nao foi possivel ler o documento DOCX.") from exc

    lines = []
    for paragraph in document.paragraphs:
        value = " ".join(paragraph.text.split())
        if value:
            style_name = paragraph.style.name if paragraph.style else ""
            lines.append(
                {
                    "text": value,
                    "is_bullet": style_name.casefold().startswith("list"),
                }
            )

    if len(lines) < 8:
        raise ValueError("O curriculo possui pouco texto para importacao.")

    ranges = _section_ranges(lines)
    required = {"summary", "skills", "experiences"}
    if not required.issubset(ranges):
        raise ValueError(
            "Nao localizei as secoes Resumo, Competencias e Experiencia."
        )

    contact_parts = [part.strip() for part in lines[3]["text"].split("|")]
    location = contact_parts[0] if contact_parts else ""
    phone = next((part for part in contact_parts if re.search(r"\d", part)), "")
    email = next((part for part in contact_parts if "@" in part), "")

    skill_items = _slice(lines, ranges, "skills")
    skills: list[str] = []
    for item in skill_items:
        value = item["text"].split(":", 1)[-1]
        skills.extend(part.strip() for part in value.split("•") if part.strip())
    skills = list(dict.fromkeys(skills))

    summary = " ".join(item["text"] for item in _slice(lines, ranges, "summary"))
    experiences = _parse_experiences(_slice(lines, ranges, "experiences"))
    education = _parse_education(_slice(lines, ranges, "education"))
    languages = [
        item["text"] for item in _slice(lines, ranges, "languages")
        if item["text"]
    ]

    if not experiences or not skills:
        raise ValueError("Nao foi possivel extrair experiencias e competencias.")

    return {
        "name": lines[0]["text"],
        "target_roles": lines[1]["text"],
        "headline": lines[2]["text"],
        "location": location,
        "phone": phone,
        "email": email,
        "linkedin": lines[4]["text"] if len(lines) > 4 else "",
        "summary": summary,
        "skills": skills,
        "experiences": experiences,
        "education": education,
        "languages": languages,
        "source_filename": Path(filename).name,
    }


def parse_resume_pdf(content: bytes, filename: str) -> dict[str, Any]:
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("O arquivo deve ter no maximo 5 MB.")
    try:
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ValueError("PDF protegido por senha nao pode ser importado.")
        if not reader.pages or len(reader.pages) > 20:
            raise ValueError("O PDF deve possuir entre 1 e 20 paginas.")
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("O arquivo enviado nao e um PDF valido.") from exc

    if len(text.strip()) < 100:
        raise ValueError(
            "O PDF parece ser escaneado e nao possui texto extraivel. "
            "Envie o DOCX ou aguarde o modulo de OCR."
        )
    if len(text) > 250_000:
        raise ValueError("O PDF possui texto demais para importacao.")

    bullet_pattern = re.compile(r"^[\u2022\u25cf\u25aa\uf0b7\-*]\s*")
    lines: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        value = " ".join(raw_line.split())
        if not value:
            continue
        is_bullet = bool(bullet_pattern.match(value))
        value = bullet_pattern.sub("", value).strip()
        if value:
            lines.append({"text": value, "is_bullet": is_bullet})

    ranges = _section_ranges(lines)
    required = {"summary", "skills", "experiences"}
    if not required.issubset(ranges):
        raise ValueError(
            "Nao localizei as secoes Resumo, Competencias e Experiencia."
        )

    summary = " ".join(
        item["text"] for item in _slice(lines, ranges, "summary")
    )

    contact_end = ranges["summary"][0] - 1
    contact_lines = [item["text"] for item in lines[:contact_end]]
    email = next((value for value in contact_lines if "@" in value), "")
    linkedin = next(
        (value for value in contact_lines if "linkedin.com" in value.casefold()),
        "",
    )
    phone = next(
        (
            value
            for value in contact_lines
            if re.search(r"(?:\+?55\s*)?\(?\d{2}\)?\s*\d{4,5}[-\s]?\d{4}", value)
        ),
        "",
    )
    location = next(
        (
            value.split(":", 1)[-1].strip()
            for value in contact_lines
            if _normalized_heading(value).startswith("LOCALIZACAO")
        ),
        "",
    )

    for prefix in ("TELEFONE:", "E-MAIL:", "EMAIL:", "LINKEDIN:"):
        if _normalized_heading(phone).startswith(prefix):
            phone = phone.split(":", 1)[-1].strip()
        if _normalized_heading(email).startswith(prefix):
            email = email.split(":", 1)[-1].strip()
        if _normalized_heading(linkedin).startswith(prefix):
            linkedin = linkedin.split(":", 1)[-1].strip()

    skill_lines: list[str] = []
    for item in _slice(lines, ranges, "skills"):
        if item["is_bullet"] or not skill_lines:
            skill_lines.append(item["text"])
        else:
            skill_lines[-1] += " " + item["text"]

    skill_values: list[str] = []
    for skill_line in skill_lines:
        value = skill_line.split(":", 1)[-1]
        parts = re.split(r"\s*[•;]\s*|\s*,\s*(?![^()]*\))", value)
        skill_values.extend(part.strip(" .") for part in parts if part.strip(" ."))
    skills = list(dict.fromkeys(skill_values))

    experience_items = _slice(lines, ranges, "experiences")
    experiences: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    def finish_experience() -> None:
        nonlocal current
        if current is None:
            return
        current["description"] = "\n".join(current["bullets"])
        experiences.append(current)
        current = None

    index = 0
    while index < len(experience_items):
        item = experience_items[index]
        value = item["text"]
        next_value = (
            experience_items[index + 1]["text"]
            if index + 1 < len(experience_items)
            else ""
        )
        next_is_bullet = (
            experience_items[index + 1]["is_bullet"]
            if index + 1 < len(experience_items)
            else False
        )

        has_company_separator = bool(
            re.search(r"\s+[\u2013\u2014-]\s+", value)
        )
        starts_header = not item["is_bullet"] and (
            "|" in value
            or (
                has_company_separator
                and not next_is_bullet
                and "|" in next_value
            )
        )
        if starts_header:
            finish_experience()
            header_parts = [value]
            while "|" not in " ".join(header_parts) and index + 1 < len(experience_items):
                index += 1
                header_parts.append(experience_items[index]["text"])
            # PDF extractors frequently wrap only the date range onto the
            # following line.  Keep joining non-bullet date fragments until
            # the first responsibility bullet or the next job header.
            while index + 1 < len(experience_items):
                continuation = experience_items[index + 1]
                if continuation["is_bullet"]:
                    break
                continuation_text = continuation["text"]
                following_text = (
                    experience_items[index + 2]["text"]
                    if index + 2 < len(experience_items)
                    else ""
                )
                continuation_is_header = (
                    "|" in continuation_text
                    or (
                        bool(re.search(r"\s+[\u2013\u2014-]\s+", continuation_text))
                        and "|" in following_text
                    )
                )
                if continuation_is_header:
                    break
                index += 1
                header_parts.append(continuation_text)
            header = " ".join(header_parts)
            left, _, period = header.partition("|")
            company = left.strip()
            role = ""
            split = re.split(r"\s+[\u2013\u2014-]\s+", left.strip())
            if len(split) >= 2:
                company = " - ".join(split[:-1]).strip()
                role = split[-1].strip()
            dates = re.split(r"\s+[\u2013\u2014-]\s+", period.strip(), maxsplit=1)
            start_date = dates[0].strip() if dates else ""
            end_date = dates[1].strip() if len(dates) == 2 else ""
            current = {
                "company": company,
                "role": role,
                "period": period.strip(),
                "start_date": start_date,
                "end_date": end_date,
                "bullets": [],
                "description": "",
            }
        elif item["is_bullet"]:
            if current is not None:
                current["bullets"].append(value)
        elif current is not None and current["bullets"]:
            current["bullets"][-1] += " " + value
        index += 1
    finish_experience()

    education_lines: list[str] = []
    for item in _slice(lines, ranges, "education"):
        if item["is_bullet"] or not education_lines:
            education_lines.append(item["text"])
        else:
            education_lines[-1] += " " + item["text"]

    education: list[dict[str, str]] = []
    for value in education_lines:
        pieces = re.split(r"\s+[\u2013\u2014-]\s+", value)
        education.append(
            {
                "course": pieces[0].strip(),
                "institution": pieces[1].strip() if len(pieces) > 1 else "",
                "period": " - ".join(pieces[2:]).strip() if len(pieces) > 2 else "",
            }
        )

    languages = [
        item["text"] for item in _slice(lines, ranges, "languages")
        if item["text"]
    ]
    if not experiences or not skills:
        raise ValueError("Nao foi possivel extrair experiencias e competencias.")

    return {
        "name": lines[0]["text"],
        "target_roles": experiences[0]["role"] if experiences else "",
        "headline": "Recursos Humanos",
        "location": location,
        "phone": phone,
        "email": email,
        "linkedin": linkedin,
        "summary": summary,
        "skills": skills,
        "experiences": experiences,
        "education": education,
        "languages": languages,
        "source_filename": Path(filename).name,
    }


def parse_resume(content: bytes, filename: str) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return parse_resume_docx(content, filename)
    if suffix == ".pdf":
        return parse_resume_pdf(content, filename)
    raise ValueError("Envie um curriculo nos formatos DOCX ou PDF.")
