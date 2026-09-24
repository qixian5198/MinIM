from datetime import UTC, datetime

import pytest
from sqlalchemy import update

from app.db import session_factory
from app.models.enums import OutboxStatus
from app.models.outbox import Outbox
from app.repositories.outbox_repo import OutboxRepo
from app.tasks.outbox_worker import OutboxWorker


@pytest.fixture
async def pending_outbox():
    async with session_factory() as session:
        # 前置：把存量 PENDING 清成死信，保证 process_once 只看到自己这条
        result = await session.execute(
            update(Outbox)
            .where(
                Outbox.status == OutboxStatus.PENDING,
                Outbox.topic == "message.new",
            )
            .values(status=OutboxStatus.DEAD)
        )
        stale = result.rowcount or 0
        record = await OutboxRepo.create(
            session, topic="message.new", payload={"msg_id": 999, "room_id": 1}
        )
        await session.commit()
        oid = record.id
    yield oid, stale
    # 清理，避免污染其他测试
    async with session_factory() as session:
        await session.execute(
            update(Outbox).where(Outbox.id == oid).values(status=OutboxStatus.DEAD)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_dispatch_success_marks_sent(pending_outbox):
    oid, stale = pending_outbox
    calls = []

    async def dispatcher(payload, outbox_id):
        calls.append((payload["msg_id"], outbox_id))

    worker = OutboxWorker(dispatcher=dispatcher)
    count = await worker.process_once()

    assert count == 1
    assert calls == [(999, oid)]
    async with session_factory() as session:
        record = await session.get(Outbox, oid)
        assert record.status == OutboxStatus.SENT


@pytest.mark.asyncio
async def test_retry_backoff_then_dead_letter(pending_outbox):
    # 预置到 4 次失败，再跑一轮就进死信
    oid, _ = pending_outbox
    async with session_factory() as session:
        await session.execute(update(Outbox).where(Outbox.id == oid).values(retry_count=4))
        await session.commit()

    async def failing_dispatcher(payload, outbox_id):
        raise RuntimeError("boom")

    worker = OutboxWorker(dispatcher=failing_dispatcher)
    assert await worker.process_once() == 0

    async with session_factory() as session:
        record = await session.get(Outbox, oid)
        assert record.status == OutboxStatus.DEAD
        assert record.retry_count == 5


@pytest.mark.asyncio
async def test_failed_dispatch_sets_next_retry(pending_outbox):
    oid, _ = pending_outbox

    async def failing_dispatcher(payload, outbox_id):
        raise RuntimeError("boom")

    worker = OutboxWorker(dispatcher=failing_dispatcher)
    await worker.process_once()

    async with session_factory() as session:
        record = await session.get(Outbox, oid)
        assert record.status == OutboxStatus.PENDING
        assert record.retry_count == 1
        assert record.next_retry_at is not None


@pytest.mark.asyncio
async def test_unknown_topic_dropped_as_sent():
    async with session_factory() as session:
        record = await OutboxRepo.create(session, topic="nobody.cares", payload={"x": 1})
        await session.commit()
        oid = record.id

    async def dispatcher(payload, outbox_id):
        raise AssertionError("unknown topic must not reach dispatcher")

    worker = OutboxWorker(dispatcher=dispatcher)
    await worker.process_once()

    async with session_factory() as session:
        record = await session.get(Outbox, oid)
        assert record.status == OutboxStatus.SENT
        await session.execute(
            update(Outbox).where(Outbox.id == oid).values(status=OutboxStatus.DEAD)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_cleanup_only_deletes_old_sent():
    async with session_factory() as session:
        recent = await OutboxRepo.create(session, topic="message.new", payload={})
        old = await OutboxRepo.create(session, topic="message.new", payload={})
        await session.execute(
            update(Outbox)
            .where(Outbox.id == old.id)
            .values(status=OutboxStatus.SENT, created_at=datetime(2000, 1, 1, tzinfo=UTC))
        )
        await session.commit()
        old_id, recent_id = old.id, recent.id

    worker = OutboxWorker()
    assert await worker.cleanup_sent() == 1

    async with session_factory() as session:
        assert await session.get(Outbox, old_id) is None
        assert (await session.get(Outbox, recent_id)).status == OutboxStatus.PENDING
        # 还原现场
        await session.execute(
            update(Outbox).where(Outbox.id == recent_id).values(status=OutboxStatus.DEAD)
        )
        await session.commit()
