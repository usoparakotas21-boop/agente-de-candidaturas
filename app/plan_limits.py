"""Monthly opportunity allowances for the Essential, Start and Pro plans."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import exists, func, select, text
from sqlalchemy.orm import Session

from .models import Application, BillingSubscription, Job, QueueItem, utc_now


MONTHLY_OPPORTUNITY_LIMITS = {
    "essential": 50,
    "start": 250,
    "pro": 1000,
}
BRAZIL_TZ = ZoneInfo("America/Sao_Paulo")


class PlanLimitReachedError(Exception):
    def __init__(self, plan: str, used: int, limit: int, resets_at: datetime):
        self.plan = plan
        self.used = used
        self.limit = limit
        self.resets_at = resets_at
        next_step = {
            "essential": "Para continuar agora, escolha Start ou Pro em Configurações → Plano e cobrança.",
            "start": "Para continuar agora, escolha Pro em Configurações → Plano e cobrança.",
            "pro": "Novas vagas poderão ser capturadas após a renovação do limite.",
        }.get(plan, "Novas vagas poderão ser capturadas após a renovação do limite.")
        super().__init__(
            f"Você atingiu o limite de {limit} vagas deste mês no plano "
            f"{plan.title()}. Ele renova em {resets_at:%d/%m/%Y}. {next_step}"
        )


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def month_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = _utc(now or utc_now()).astimezone(BRAZIL_TZ)
    start_local = current.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    end_local = (start_local.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _effective_plan(session: Session, owner_id: str, now: datetime) -> str:
    subscription = session.scalar(
        select(BillingSubscription)
        .where(BillingSubscription.owner_id == owner_id)
        .order_by(BillingSubscription.updated_at.desc())
        .limit(1)
    )
    if subscription is None or str(subscription.plan_code or "").casefold() not in {"start", "pro"}:
        return "essential"
    if str(subscription.status or "").casefold() not in {"authorized", "paused", "canceled"}:
        return "essential"
    if subscription.access_until is None or _utc(subscription.access_until) <= now:
        return "essential"
    return str(subscription.plan_code).casefold()


def monthly_opportunity_usage(
    session: Session,
    owner_id: str,
    now: datetime | None = None,
) -> dict:
    """Count distinct new queue captures and directly added jobs this calendar month."""
    current = _utc(now or utc_now())
    period_start, period_end = month_window(current)
    plan = _effective_plan(session, owner_id, current)
    limit = MONTHLY_OPPORTUNITY_LIMITS[plan]

    queued = int(
        session.scalar(
            select(func.count(QueueItem.id)).where(
                QueueItem.owner_id == owner_id,
                QueueItem.captured_at >= period_start,
                QueueItem.captured_at < period_end,
            )
        )
        or 0
    )
    direct_jobs = int(
        session.scalar(
            select(func.count(Application.id))
            .join(Job, Job.id == Application.job_id)
            .where(
                Job.owner_id == owner_id,
                Application.created_at >= period_start,
                Application.created_at < period_end,
                ~exists(
                    select(QueueItem.id).where(QueueItem.job_id == Application.job_id)
                ),
            )
        )
        or 0
    )
    used = queued + direct_jobs
    return {
        "plan_code": plan,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used),
        "period_start": period_start,
        "resets_at": period_end,
    }


def ensure_opportunity_capacity(
    session: Session,
    owner_id: str | None,
    now: datetime | None = None,
) -> dict | None:
    """Raise before adding a new listing when an authenticated user used the monthly allowance."""
    normalized_owner = str(owner_id or "").strip()
    # Preserve local/demo flows that have no authenticated account owner.
    if not normalized_owner or normalized_owner == "local_user":
        return None
    current = _utc(now or utc_now())
    period_start, _ = month_window(current)
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        # Serialize allowance checks for the same account/month across workers.
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:scope), hashtext(:owner_period))"),
            {
                "scope": "monthly-opportunity-limit",
                "owner_period": f"{normalized_owner}:{period_start.date().isoformat()}",
            },
        )
    usage = monthly_opportunity_usage(session, normalized_owner, current)
    if usage["used"] >= usage["limit"]:
        raise PlanLimitReachedError(
            usage["plan_code"], usage["used"], usage["limit"], usage["resets_at"]
        )
    return usage
