"""
Test joining a task in the middle of the nursery
"""

import asyncio
import time

import pytest

from tests import run10
from traio import Nursery


async def trivial():
    await asyncio.sleep(0.2)
    return 3


async def raiser():
    await asyncio.sleep(0.1)
    raise ValueError('boom')


@pytest.mark.asyncio
async def test_join_task():
    """Test joining a task and check result"""
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
async def test_join_task_cancelled_no_env():
    """Test joining a task, but cancelled"""
    n = Nursery(timeout=1)

    t = n.start_soon(run10())

    t.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t

    await n.join()


@pytest.mark.asyncio
async def test_join_task_raises():
    """Test joining a task, but raises"""
    before = time.time()

    async with Nursery(timeout=1) as n:
        t = n.start_soon(raiser())
        with pytest.raises(ValueError):
            # Catching the error here prevents bubbling
            await t

    after = time.time()
    assert (after - before) < 0.3


@pytest.mark.asyncio
async def test_join_task_raises_no_env():
    """Test joining a task, but raises"""
    before = time.time()

    n = Nursery(timeout=1)

    t = n.start_soon(raiser())
    with pytest.raises(ValueError):
        # Catching the error here prevents bubbling
        await t

    await n.join()

    after = time.time()
    assert (after - before) < 0.3


@pytest.mark.asyncio
async def test_join_then_new():
    """Test joining a task, then spawn another one"""
    before = time.time()

    async with Nursery(timeout=1) as n:
        # takes 0.2 seconds
        await n.start_soon(trivial())
        assert (time.time() - before) < 0.3

        # At this point, the nursery should be still started
        assert not n.done()

        # will 0.2 seconds
        n.start_soon(trivial())

    after = time.time()
    assert (after - before) < 0.5


@pytest.mark.asyncio
async def test_join_then_new_no_env():
    """Test joining a task, then spawn another one"""
    before = time.time()

    n = Nursery(timeout=1)

    # takes 0.2 seconds
    await n.start_soon(trivial())
    assert (time.time() - before) < 0.3

    # At this point, the nursery should be still started
    assert not n.done()

    # will 0.2 seconds
    n.start_soon(trivial())

    await n.join()

    after = time.time()
    assert (after - before) < 0.5
