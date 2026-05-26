"""SQLAlchemy ORM models for run persistence."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    request_json: Mapped[str] = mapped_column(Text, nullable=False)
    providers_json: Mapped[str] = mapped_column(Text, nullable=False)
    planned_stages_json: Mapped[str] = mapped_column(Text, nullable=False)
    report: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    trace_records: Mapped[list[TraceRecordRow]] = relationship(
        "TraceRecordRow",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="TraceRecordRow.seq",
        lazy="selectin",
    )


class TraceRecordRow(Base):
    __tablename__ = "trace_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("runs.run_id"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)

    run: Mapped[RunRow] = relationship("RunRow", back_populates="trace_records")
