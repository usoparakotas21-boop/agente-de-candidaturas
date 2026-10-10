"""Pydantic contracts used by the isolated job-collection module.

These models intentionally live at the repository root so the collectors can be
used by a worker, a CLI, or the existing application without changing its
imports.  They do not create database tables or alter the current API.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


OrigemVaga = Literal["gupy", "remoteok", "weworkremotely", "vagas_com", "solides", "linkedin", "catho", "infojobs"]

class TipoModalidade(str, Enum):
    REMOTO = "remoto"
    HIBRIDO = "hibrido"
    PRESENCIAL = "presencial"
    NAO_INFORMADO = "nao_informado"


class VagaPadronizada(BaseModel):
    """Canonical representation of a publicly collected job posting."""

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    id_externo: str = Field(..., min_length=1, max_length=250)
    origem: OrigemVaga
    titulo: str = Field(..., min_length=2, max_length=300)
    empresa: str = Field(default="Não informado", max_length=250)
    localidade: str = Field(default="Não informado", max_length=300)
    tipo_modalidade: TipoModalidade = TipoModalidade.NAO_INFORMADO
    url_candidatura: str = Field(..., min_length=1, max_length=2000)
    url_origem: str | None = Field(default=None, max_length=2000)
    descricao: str = Field(default="", max_length=100_000)
    requisitos: list[str] = Field(default_factory=list)
    beneficios: list[str] = Field(default_factory=list)
    palavras_chave: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    tipo_contrato: str | None = Field(default=None, max_length=100)
    senioridade: str | None = Field(default=None, max_length=100)
    salario_minimo: float | None = Field(default=None, ge=0)
    salario_maximo: float | None = Field(default=None, ge=0)
    moeda: str = Field(default="BRL", min_length=3, max_length=6)
    data_publicacao: datetime | None = None
    data_coleta: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    hash_deduplicacao: str | None = Field(default=None, max_length=128)
    metadados: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url_candidatura", "url_origem")
    @classmethod
    def validate_public_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("A URL deve usar http ou https e conter um host.")
        return value

    @field_validator("tipo_modalidade", mode="before")
    @classmethod
    def normalize_modality(cls, value: Any) -> Any:
        if isinstance(value, TipoModalidade):
            return value
        normalized = str(value or "").casefold().strip()
        if any(token in normalized for token in ("remote", "remoto", "home office", "teletrabalho")):
            return TipoModalidade.REMOTO
        if any(token in normalized for token in ("hibrid", "hybrid")):
            return TipoModalidade.HIBRIDO
        if any(token in normalized for token in ("presencial", "on-site", "onsite")):
            return TipoModalidade.PRESENCIAL
        return TipoModalidade.NAO_INFORMADO

    @field_validator("palavras_chave", "tags", "requisitos", "beneficios")
    @classmethod
    def clean_string_lists(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in values if str(item).strip()))

    @model_validator(mode="after")
    def validate_salary_range(self) -> "VagaPadronizada":
        if (
            self.salario_minimo is not None
            and self.salario_maximo is not None
            and self.salario_minimo > self.salario_maximo
        ):
            raise ValueError("salario_minimo não pode ser maior que salario_maximo.")
        if self.data_coleta.tzinfo is None:
            self.data_coleta = self.data_coleta.replace(tzinfo=timezone.utc)
        if self.tags and not self.palavras_chave:
            self.palavras_chave = list(self.tags)
        elif self.palavras_chave and not self.tags:
            self.tags = list(self.palavras_chave)
        return self

    @property
    def chave_deduplicacao(self) -> str:
        """Stable key used by the collector when a source repeats a posting."""

        return self.hash_deduplicacao or f"{self.origem}:{self.id_externo}"


class CandidatoCadastro(BaseModel):
    """Input contract for registering a candidate in the collection pipeline."""

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    nome_completo: str = Field(..., min_length=2, max_length=160)
    email: str = Field(..., min_length=5, max_length=320)
    telefone: str | None = Field(default=None, max_length=40)
    localidade: str | None = Field(default=None, max_length=200)
    cargos_desejados: list[str] = Field(default_factory=list, min_length=1)
    competencias: list[str] = Field(default_factory=list)
    modalidades_preferidas: list[TipoModalidade] = Field(default_factory=list)
    pretensao_salarial_minima: float | None = Field(default=None, ge=0)
    pretensao_salarial_maxima: float | None = Field(default=None, ge=0)
    consentimento_lgpd: bool = Field(..., description="Consentimento para tratamento dos dados.")

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        value = value.strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Informe um e-mail válido.")
        return value

    @field_validator("cargos_desejados", "competencias")
    @classmethod
    def clean_candidate_lists(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in values if str(item).strip()))

    @model_validator(mode="after")
    def validate_candidate(self) -> "CandidatoCadastro":
        if not self.consentimento_lgpd:
            raise ValueError("O consentimento_lgpd é obrigatório para cadastrar o candidato.")
        if (
            self.pretensao_salarial_minima is not None
            and self.pretensao_salarial_maxima is not None
            and self.pretensao_salarial_minima > self.pretensao_salarial_maxima
        ):
            raise ValueError("A pretensão salarial mínima não pode superar a máxima.")
        return self

class CandidatoCadastroInput(BaseModel):
    """Payload simples para o primeiro cadastro no módulo de vagas."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    nome: str = Field(..., min_length=2, max_length=160)
    email: str = Field(..., min_length=5, max_length=320)
    telefone: str | None = Field(default=None, max_length=40)
    cargo_interesse: str = Field(..., min_length=2, max_length=160)
    modalidade_preferida: str = Field(default="Todas", max_length=40)

    @field_validator("email")
    @classmethod
    def validate_email_input(cls, value: str) -> str:
        value = value.strip().casefold()
        if not re.fullmatch(r"^[^ @]+@[^ @]+[.][^ @]+$", value):
            raise ValueError("Informe um e-mail válido.")
        return value



