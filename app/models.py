from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Boolean,
    JSON,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(50))
    linkedin: Mapped[str] = mapped_column(String(500))

    target_roles: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    profile_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_filename: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
    )
    preferences_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    experiences = relationship(
        "Experience",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )

    skills = relationship(
        "Skill",
        back_populates="candidate",
        cascade="all, delete-orphan",
    )


class Experience(Base):
    __tablename__ = "experiences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id"),
        nullable=False,
    )

    company: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[str] = mapped_column(String(50))
    end_date: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)

    candidate = relationship("Candidate", back_populates="experiences")


class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id"),
        nullable=False,
    )

    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100))
    proficiency: Mapped[str] = mapped_column(String(100))

    candidate = relationship("Candidate", back_populates="skills")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(100))
    external_id: Mapped[str] = mapped_column(String(300), unique=True)
    company: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(200))
    location: Mapped[str] = mapped_column(String(300))
    modality: Mapped[str] = mapped_column(String(100))
    contract_type: Mapped[str] = mapped_column(String(50), default="")
    modality_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary: Mapped[str] = mapped_column(String(200), default="")
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str] = mapped_column(String(1000))
    description: Mapped[str] = mapped_column(Text)

    analysis = relationship(
        "JobAnalysis",
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
    )

    application = relationship(
        "Application",
        back_populates="job",
        uselist=False,
        cascade="all, delete-orphan",
    )


class JobAnalysis(Base):
    __tablename__ = "job_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id"),
        nullable=False,
    )

    overall_score: Mapped[float] = mapped_column(Float)
    experience_score: Mapped[float] = mapped_column(Float)
    skills_score: Mapped[float] = mapped_column(Float)
    seniority_score: Mapped[float] = mapped_column(Float)
    education_score: Mapped[float] = mapped_column(Float)
    location_score: Mapped[float] = mapped_column(Float)
    language_score: Mapped[float] = mapped_column(Float)

    strengths: Mapped[str] = mapped_column(Text)
    gaps: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(String(100))

    job = relationship("Job", back_populates="analysis")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EmailIntegration(Base):
    __tablename__ = "email_integrations"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "provider",
            name="uq_email_integration_owner_provider",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="gmail",
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    encrypted_refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    connected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class ProcessedEmailMessage(Base):
    __tablename__ = "processed_email_messages"
    __table_args__ = (
        UniqueConstraint(
            "integration_id",
            "provider_message_id",
            name="uq_processed_email_integration_message",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    integration_id: Mapped[int] = mapped_column(
        ForeignKey("email_integrations.id"),
        nullable=False,
        index=True,
    )
    owner_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        index=True,
    )
    provider_message_id: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    sender: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id"),
        nullable=True,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id"),
        nullable=False,
        unique=True,
    )
    candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidates.id"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="IDENTIFICADA",
    )
    analysis_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    personalization_score: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    recommendation: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    queue_decision: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="REVISAR",
    )
    decision_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    capture_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    field_confidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_letter_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_letter_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cover_letter_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    health_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_band: Mapped[str | None] = mapped_column(String(20), nullable=True)
    health_signals: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    fraud_suspected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    risk_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    job = relationship("Job", back_populates="application")
    events = relationship(
        "ApplicationEvent",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationEvent.id",
    )
    generated_documents = relationship(
        "GeneratedDocument",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="GeneratedDocument.created_at.desc()",
    )


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    external_result: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resume_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cover_letter_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    application = relationship("Application", back_populates="events")


class DocumentExportPurchase(Base):
    """Pedido de exportação pago por um checkout configurado."""

    __tablename__ = "document_export_purchases"
    __table_args__ = (UniqueConstraint("order_nsu", name="uq_document_export_order_nsu"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    application_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    payer_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    order_nsu: Mapped[str] = mapped_column(String(120), nullable=False)
    invoice_slug: Mapped[str | None] = mapped_column(String(200), nullable=True)
    transaction_nsu: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    paid_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    receipt_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    receipt_email_status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    receipt_email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BillingSubscription(Base):
    """Current recurring Mercado Pago subscription for one account."""

    __tablename__ = "billing_subscriptions"
    __table_args__ = (
        UniqueConstraint("external_reference", name="uq_billing_subscription_external_reference"),
        UniqueConstraint("mercadopago_preapproval_id", name="uq_billing_subscription_mp_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    plan_code: Mapped[str] = mapped_column(String(24), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    mercadopago_preapproval_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    checkout_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payer_email: Mapped[str] = mapped_column(String(320), nullable=False)
    monthly_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="BRL")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="creating")
    next_payment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    access_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_payment_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_payment_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class GeneratedDocument(Base):
    """Private, durable version of a generated document stored in PostgreSQL."""

    __tablename__ = "generated_documents"
    __table_args__ = (
        UniqueConstraint(
            "application_id",
            "kind",
            "version",
            name="uq_generated_document_application_kind_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    company: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    application = relationship("Application", back_populates="generated_documents")


class DocumentDelivery(Base):
    """Idempotent e-mail delivery state for one resume/cover-letter version pair."""

    __tablename__ = "document_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "resume_document_id",
            "cover_letter_document_id",
            name="uq_document_delivery_document_pair",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resume_document_id: Mapped[int] = mapped_column(
        ForeignKey("generated_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    cover_letter_document_id: Mapped[int] = mapped_column(
        ForeignKey("generated_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(240), nullable=True)


# ============================================================
# NOVO PARA VERSÃO 0.23.0
# ============================================================

class QueueItem(Base):
    __tablename__ = "queue_items"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", 
            "dedup_hash", 
            name="uq_queue_owner_dedup"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36), 
        nullable=False, 
        index=True
    )

    # Origem
    source: Mapped[str] = mapped_column(
        String(50), 
        nullable=False
    )
    source_ref: Mapped[str | None] = mapped_column(
        String(200), 
        nullable=True
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )

    # Conteudo capturado
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    modality: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    salary: Mapped[str | None] = mapped_column(String(200), nullable=True)
    modality_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Confianca por campo (0-100)
    confidence_title: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_company: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_description: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_url: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_overall: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Decisao (imutavel)
    decision: Mapped[str] = mapped_column(
        String(20), 
        nullable=False
    )
    decision_reasons: Mapped[list] = mapped_column(
        JSON, 
        nullable=False, 
        default=list
    )
    decision_engine_version: Mapped[str] = mapped_column(
        String(20), 
        nullable=False
    )
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Ciclo de vida
    status: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default="PENDENTE"
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )
    resolved_by: Mapped[str | None] = mapped_column(
        String(50), 
        nullable=True
    )

    # Ligacao com o sistema
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id"), 
        nullable=True
    )
    dedup_hash: Mapped[str | None] = mapped_column(
        String(64), 
        nullable=True, 
        index=True
    )

    # Controle de duplicatas
    seen_count: Mapped[int] = mapped_column(
        Integer, 
        nullable=False, 
        default=1
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False
    )

    # Para versao 0.24.0 (ja adicionando)
    health_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    health_band: Mapped[str | None] = mapped_column(String(20), nullable=True)
    health_signals: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    fraud_suspected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relacionamentos
    job = relationship("Job", foreign_keys=[job_id])
