import asyncio
import time

import pytest

from mock import Mock

from tests import run10
from traio import Nursery, TaskException


@pytest.mark.asyncio
async def test_empty():
    """Empty Nursery"""
    async with Nursery():
        pass


@pytest.mark.asyncio
async def test_empty_timeout():
    """Empty Nursery"""
    async with Nursery(timeout=0.1):
        pass


@pytest.mark.asyncio
async def test_simple():
    """Simple nursery with one execution"""
    async def run(m):
        await asyncio.sleep(0.01)
        m()

    mock = Mock()

    async with Nursery() as n:
        n.start_soon(run(mock))

    assert mock.called


@pytest.mark.asyncio
async def test_block_raises():
    """Raise an exception from the block"""
    with pytest.raises(ValueError):
        async with Nursery():
            raise ValueError('boom')


@pytest.mark.asyncio
async def test_task_raises():
    """Raise an exception from a task"""
    async def raiser():
        await asyncio.sleep(0.01)
        raise ValueError('boom')

    try:
        async with Nursery() as n:
            n.start_soon(raiser())
    except TaskException as e:
        assert isinstance(e.__cause__, ValueError)
    else:
        raise Exception('DID NOT RAISE')


@pytest.mark.asyncio
async def test_join_task():
    """Test joining a task and check result"""
    async def trivial():
        await asyncio.sleep(0.2)
        return 3

    before = time.time()

    async with Nursery(timeout=0.5) as n:
        ret = await n.start_soon(trivial())
        assert ret == 3

        t = n.start_soon(trivial())
        assert 3 == await t

        # Cancel directly
        n.cancel()

    after = time.time()
    assert 0.1 < (after - before) < 0.5


@pytest.mark.asyncio
async def test_join_task_cancelled():
    """Test joining a task, but cancelled"""
    async with Nursery(timeout=1) as n:
        t = n.start_soon(run10())

        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t


@pytest.mark.asyncio
async def test_join_task_raises():
    """Test joining a task, but raises"""
    async def raiser():
        await asyncio.sleep(0.1)
        raise ValueError('boom')

    before = time.time()

    async with Nursery(timeout=1) as n:
        t = n.start_soon(raiser())
        with pytest.raises(ValueError):
            await t

    after = time.time()
    assert (after - before) < 0.3
