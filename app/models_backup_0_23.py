from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
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
    salary: Mapped[str] = mapped_column(String(200), default="")
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


class ApplicationEvent(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.id"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    application = relationship("Application", back_populates="events")
