"""SQLAlchemy ORM models for the appointment booking bot."""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ─── Enums ────────────────────────────────────────────────────────────────────


class AppointmentStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"


# ─── Models ───────────────────────────────────────────────────────────────────


class User(Base):
    """Telegram user / client."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False
    )

    appointments: Mapped[list[Appointment]] = relationship(
        "Appointment", back_populates="user"
    )


class Service(Base):
    """A type of appointment / procedure available for booking."""

    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    duration_min: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    specialist_links: Mapped[list[SpecialistService]] = relationship(
        "SpecialistService", back_populates="service"
    )
    appointments: Mapped[list[Appointment]] = relationship(
        "Appointment", back_populates="service"
    )


class Specialist(Base):
    """A doctor / specialist who provides services."""

    __tablename__ = "specialists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    specialization: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    service_links: Mapped[list[SpecialistService]] = relationship(
        "SpecialistService", back_populates="specialist"
    )
    schedules: Mapped[list[WorkSchedule]] = relationship(
        "WorkSchedule", back_populates="specialist"
    )
    appointments: Mapped[list[Appointment]] = relationship(
        "Appointment", back_populates="specialist"
    )


class SpecialistService(Base):
    """Many-to-many: which specialist provides which service."""

    __tablename__ = "specialist_services"
    __table_args__ = (UniqueConstraint("specialist_id", "service_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    specialist_id: Mapped[int] = mapped_column(
        ForeignKey("specialists.id", ondelete="CASCADE")
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE")
    )

    specialist: Mapped[Specialist] = relationship(
        "Specialist", back_populates="service_links"
    )
    service: Mapped[Service] = relationship(
        "Service", back_populates="specialist_links"
    )


class WorkSchedule(Base):
    """Weekly work schedule for a specialist (per weekday)."""

    __tablename__ = "work_schedules"
    __table_args__ = (UniqueConstraint("specialist_id", "weekday"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    specialist_id: Mapped[int] = mapped_column(
        ForeignKey("specialists.id", ondelete="CASCADE")
    )
    # weekday: Monday=0 … Sunday=6
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), default="09:00")  # "HH:MM"
    end_time: Mapped[str] = mapped_column(String(5), default="18:00")
    is_day_off: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    specialist: Mapped[Specialist] = relationship(
        "Specialist", back_populates="schedules"
    )


class Appointment(Base):
    """A single booking by a client with a specialist for a service."""

    __tablename__ = "appointments"
    __table_args__ = (
        # Prevent double-booking: unique (specialist, time) for non-cancelled appointments
        # SQLAlchemy doesn't natively support partial indexes in SQLite via ORM,
        # so we enforce this at service layer too (SELECT FOR UPDATE pattern).
        UniqueConstraint("specialist_id", "scheduled_at", name="uq_specialist_slot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    specialist_id: Mapped[int] = mapped_column(
        ForeignKey("specialists.id", ondelete="CASCADE")
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("services.id", ondelete="CASCADE")
    )

    # Stored in UTC; displayed as UTC+3 to the user
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    status: Mapped[AppointmentStatus] = mapped_column(
        Enum(AppointmentStatus), default=AppointmentStatus.CONFIRMED, nullable=False
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # APScheduler job id for the 24-hour reminder
    reminder_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="appointments")
    specialist: Mapped[Specialist] = relationship(
        "Specialist", back_populates="appointments"
    )
    service: Mapped[Service] = relationship("Service", back_populates="appointments")
