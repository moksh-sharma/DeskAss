"""SQLAlchemy ORM models for session history persistence."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), default="New Session")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class MachineScanRecord(Base):
    """Persisted comprehensive machine scan (+ optional AI summary)."""

    __tablename__ = "machine_scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), default="Machine Scan")
    health_score: Mapped[int] = mapped_column(Integer, default=0)
    health_status: Mapped[str] = mapped_column(String(32), default="Unknown")
    scan_duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    has_ai_summary: Mapped[bool] = mapped_column(Boolean, default=False)
    # Full MachineScanReport JSON (hardware, software, health_report, ai_summary, …).
    report_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class StorageScanRecord(Base):
    """Persisted Advanced Storage Intelligence deep scan."""

    __tablename__ = "storage_scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), default="Storage Scan")
    health_score: Mapped[int] = mapped_column(Integer, default=0)
    health_status: Mapped[str] = mapped_column(String(32), default="Unknown")
    recoverable_gb: Mapped[float] = mapped_column(Float, default=0.0)
    primary_free_gb: Mapped[float] = mapped_column(Float, default=0.0)
    primary_used_pct: Mapped[float] = mapped_column(Float, default=0.0)
    scan_duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    # Full storage report JSON (tree, footprint, duplicates, cleanup, …).
    report_json: Mapped[str] = mapped_column(Text)
    # Light snapshot used for change-tracking / growth prediction on next run.
    snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class TelemetrySample(Base):
    """A single point-in-time telemetry sample from the continuous monitor."""

    __tablename__ = "telemetry_samples"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    tier: Mapped[str] = mapped_column(String(16), default="critical", index=True)
    cpu_pct: Mapped[float] = mapped_column(Float, default=0.0)
    cpu_freq_mhz: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    mem_used_pct: Mapped[float] = mapped_column(Float, default=0.0)
    mem_available_gb: Mapped[float] = mapped_column(Float, default=0.0)
    pagefile_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_free_gb: Mapped[float] = mapped_column(Float, default=0.0)
    disk_used_pct: Mapped[float] = mapped_column(Float, default=0.0)
    disk_read_mb_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    disk_write_mb_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_up_mb_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_down_mb_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_mem_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    process_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # JSON: top CPU / memory processes (only on detailed+ tiers).
    top_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class MonitorEvent(Base):
    """A discrete event detected by the monitor (change, anomaly, alert, boot…)."""

    __tablename__ = "monitor_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    # change | anomaly | alert | boot | crash | service | device | security | update | driver | network
    category: Mapped[str] = mapped_column(String(32), index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")
    title: Mapped[str] = mapped_column(String(255))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class MonitorInventorySnapshot(Base):
    """Periodic inventory snapshot used for change detection / diffing."""

    __tablename__ = "monitor_inventory_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    # apps | services | startup | devices | security | network | boot
    kind: Mapped[str] = mapped_column(String(32), index=True)
    data_json: Mapped[str] = mapped_column(Text)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    # JSON-serialised metadata (diagnostics snapshot, diagnosis result, etc.)
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped["Session"] = relationship(back_populates="messages")
