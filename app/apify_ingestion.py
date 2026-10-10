"""Explicitly authorized Apify Dataset integration for the market catalogue.

The connector is disabled by default. It only runs when the operator provides
an Actor output Dataset and records the source authorization in environment
variables; missing approval evidence fails closed before any network call.
"""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import httpx
from sqlalchemy.orm import Session

from .job_ingestion import IngestionResult, upsert_job_listings
from .source_governance import JobSource, SourceRegistry, SourceStatus, SourceUse

ACTOR_ID = "hKByXkMQaC5Qt9UMN"
SOURCE_ID = "apify-linkedin-jobs"
MAX_ITEMS = 500


def _configured_source() -> tuple[SourceRegistry, JobSource]:
    dataset_id = os.getenv("APIFY_DATASET_ID", "").strip()
    approved = os.getenv("APIFY_SOURCE_APPROVED", "").strip().lower() == "true"
    evidence = os.getenv("APIFY_PERMISSION_EVIDENCE", "").strip()
    terms = os.getenv("APIFY_TERMS_REFERENCE", "").strip()
    if not approved or not dataset_id or not evidence or not terms:
        raise RuntimeError("Apify está desativado até que Dataset e autorização estejam configurados.")
    source = JobSource(
        source_id=SOURCE_ID,
        display_name="Apify · LinkedIn Jobs Scraper",
        source_owner="Curious Coder / Apify",
        source_owner_reference=f"actor:{ACTOR_ID}",
        approved_domains=("api.apify.com",),
        endpoint_url=f"https://api.apify.com/v2/datasets/{dataset_id}/items",
        allowed_fields=("id", "link", "applyUrl", "apply_url", "title", "companyName", "company", "location", "salaryInfo", "salary_range", "descriptionText", "descriptionHtml", "description", "employmentType", "contract_type", "workplaceTypes", "work_mode", "workRemoteAllowed", "postedAt"),
        permitted_uses=frozenset({SourceUse.AUTOMATED_FETCH, SourceUse.COMMERCIAL_DISPLAY, SourceUse.AI_PROCESSING, SourceUse.DESCRIPTION_CACHING}),
        status=SourceStatus.APPROVED,
        permission_basis="Autorização operacional registrada pelo proprietário do projeto",
        permission_evidence=evidence,
        terms_reference=terms,
        robots_review=os.getenv("APIFY_ROBOTS_REVIEW", "Consulta feita pelo operador; manter revisão vigente."),
        attribution="Dados coletados por Apify; fonte original indicada no anúncio.",
        rate_limit_requests_per_minute=6,
        rate_limit_max_concurrency=1,
        raw_content_retention_ttl_days=30,
        reviewed_at=date.today(),
    )
    registry = SourceRegistry((source,))
    return registry, source


def _text(value: Any) -> str:
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value).strip()
    return ""


def normalize_apify_record(record: dict[str, Any]) -> dict[str, Any]:
    salary = record.get("salaryInfo")
    if isinstance(salary, list):
        salary = " - ".join(_text(item) for item in salary if _text(item))
    remote = record.get("workRemoteAllowed") is True
    workplace = record.get("workplaceTypes")
    if isinstance(workplace, list):
        workplace = " ".join(_text(item) for item in workplace)
    return {
        "external_id": _text(record.get("id")) or _text(record.get("link")),
        "title": _text(record.get("title")),
        "company": _text(record.get("companyName")),
        "location": _text(record.get("location")),
        "description": _text(record.get("descriptionText")) or _text(record.get("descriptionHtml")),
        "apply_url": _text(record.get("applyUrl")) or _text(record.get("link")),
        "salary_range": salary or "",
        "work_mode": "remote" if remote else _text(workplace),
        "contract_type": _text(record.get("employmentType")),
    }


async def sync_apify_dataset(db: Session) -> IngestionResult:
    token = os.getenv("APIFY_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("APIFY_API_TOKEN não configurado.")
    registry, source = _configured_source()
    url = source.endpoint_url + "?clean=true&format=json"
    async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or len(payload) > MAX_ITEMS:
        raise RuntimeError("Dataset do Apify inválido ou acima do limite configurado.")
    records = [normalize_apify_record(item) for item in payload if isinstance(item, dict)]
    return upsert_job_listings(db, source.source_id, records, registry=registry)

