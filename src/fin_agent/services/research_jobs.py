"""A bounded, single-worker local queue independent of browser connections."""

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

from fin_agent.domain.research_jobs import JobInput, ResearchJob
from fin_agent.domain.types import ResearchProgress
from fin_agent.storage.job_store import JobStore


class ResearchJobs:
    def __init__(self, container, store: JobStore):
        self.container = container
        self.store = store
        self.queue: asyncio.Queue[ResearchJob] = asyncio.Queue(maxsize=20)
        self.worker: asyncio.Task | None = None

    def start(self) -> None:
        self.store.interrupt_pending()
        self.worker = asyncio.create_task(self._work())

    async def close(self) -> None:
        if self.worker:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        self.store.interrupt_pending()

    def submit(self, payload: JobInput, owner: str) -> ResearchJob:
        previous = self.store.find(owner, payload.client_id)
        if previous:
            return previous
        if self.queue.full():
            raise ValueError("任务队列已满，请稍后提交。 / Research queue is full.")
        job = ResearchJob(
            id=uuid4().hex,
            owner=owner,
            client_id=payload.client_id,
            request=payload.request.model_copy(update={"template": "illustrated_research"}),
            source=payload.source,
        )
        self.store.save(job)
        self.queue.put_nowait(job)
        return job

    @asynccontextmanager
    async def _service(self, job: ResearchJob):
        container = self.container
        owner = None if job.owner == "local" else job.owner
        if job.source == "personal":
            connection = container.model_connections.get(job.owner)
            if connection is None:
                raise ValueError("个人 API 已断开或过期，请重新连接后重试。")
            async with container.model_connections.client(connection.config) as llm:
                yield container.research_service.with_llm(
                    llm,
                    model=connection.config.model,
                    protocol=connection.config.protocol,
                    owner_user_id=owner,
                )
        elif job.source == "codex":
            async with container.local_codex.client() as llm:
                yield container.research_service.with_llm(
                    llm,
                    model=llm.model,
                    protocol="codex",
                    owner_user_id=owner,
                    source="local_codex",
                )
        else:
            yield container.research_service.with_owner(owner)

    async def _work(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                job.status, job.stage = "running", "intake"
                self.store.save(job)

                def progress(event: ResearchProgress, current=job) -> None:
                    current.stage = event.stage
                    self.store.save(current)

                async with asyncio.timeout(1800), self._service(job) as service:
                    job.result = await service.run(job.request, on_progress=progress)
                job.status = "completed" if job.result.status == "completed" else "failed"
                job.stage = job.status
                if job.status == "failed":
                    job.error = "AI 研究未完成或未通过审查，已保留取得的数据和执行记录。"
            except asyncio.CancelledError:
                job.status = "interrupted"
                job.error = "服务停止，任务已中断，可重试。"
                raise
            except Exception:
                # Provider exceptions can include credentials or request payloads.
                job.status = "failed"
                job.stage = "failed"
                job.error = "任务未完成，请检查模型连接、额度及数据源后重试。"
            finally:
                self.store.save(job)
                self.queue.task_done()
