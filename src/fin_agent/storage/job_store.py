"""Small SQL-backed queue ledger, sharing the configured run database."""

import json

from sqlalchemy import Engine, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from fin_agent.domain.research_jobs import ResearchJob, now
from fin_agent.storage.models import Base


class JobRow(Base):
    __tablename__ = "research_jobs"
    __table_args__ = (UniqueConstraint("owner", "client_id"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str] = mapped_column(String(64), index=True)
    client_id: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[str] = mapped_column(Text)


class JobStore:
    def __init__(self, engine: Engine):
        self.engine = engine
        JobRow.__table__.create(engine, checkfirst=True)

    @staticmethod
    def _read(row: JobRow) -> ResearchJob:
        return ResearchJob.model_validate({**json.loads(row.payload), "owner": row.owner})

    def save(self, job: ResearchJob) -> None:
        job.updated_at = now()
        with Session(self.engine) as session:
            session.merge(
                JobRow(
                    id=job.id,
                    owner=job.owner,
                    client_id=job.client_id,
                    created_at=job.created_at,
                    payload=job.model_dump_json(),
                )
            )
            session.commit()

    def get(self, job_id: str, owner: str) -> ResearchJob | None:
        with Session(self.engine) as session:
            row = session.get(JobRow, job_id)
            return self._read(row) if row is not None and row.owner == owner else None

    def find(self, owner: str, client_id: str) -> ResearchJob | None:
        with Session(self.engine) as session:
            row = session.scalar(
                select(JobRow).where(
                    JobRow.owner == owner,
                    JobRow.client_id == client_id,
                )
            )
            return self._read(row) if row is not None else None

    def list(self, owner: str, offset: int = 0) -> list[ResearchJob]:
        with Session(self.engine) as session:
            rows = session.scalars(
                select(JobRow)
                .where(JobRow.owner == owner)
                .order_by(JobRow.created_at.desc())
                .offset(offset)
                .limit(50)
            )
            return [self._read(row) for row in rows]

    def interrupt_pending(self) -> None:
        with Session(self.engine) as session:
            for row in session.scalars(select(JobRow)):
                job = self._read(row)
                if job.status in {"queued", "running"}:
                    job.status = "interrupted"
                    job.stage = "interrupted"
                    job.error = "服务已重启，任务中断。可重试；不会自动重复调用模型。"
                    job.updated_at = now()
                    row.payload = job.model_dump_json()
            session.commit()
