"""
Test running synchronous code in executor, from a Scope!
"""
import asyncio
import time

import pytest

from traio import Scope


@pytest.mark.asyncio
async def test_executor():
    """Test simple task running in an executor"""
    before = time.time()

    def job():
        time.sleep(0.2)
        return 42

    async with Scope(timeout=1) as n:
        t = n.spawn(asyncio.get_event_loop().run_in_executor(None, job))
        assert 42 == await t

    after = time.time()
    assert (after - before) < 0.3


@pytest.mark.asyncio
async def test_executor_raises():
    """Test simple task running in an executor, raising"""
    before = time.time()

    def raiser():
        time.sleep(0.2)
        raise ValueError('boom')

    async with Scope(timeout=1) as n:
        t = n.spawn(asyncio.get_event_loop().run_in_executor(None, raiser))
        with pytest.raises(ValueError):
            await t

    after = time.time()
    assert (after - before) < 0.3


@pytest.mark.asyncio
async def test_executor_timeout():
    """Test simple task running in an executor, raising"""
    before = time.time()
    started = False
    done = False

    def job():
        nonlocal started, done
        started = True
        time.sleep(0.3)
        done = True

    with pytest.raises(TimeoutError):
        async with Scope(timeout=0.1) as n:
            n << asyncio.get_event_loop().run_in_executor(None, job)

    after = time.time()
    assert (after - before) < 0.2
    assert started is True
    assert done is False

    # The task is still running though...
    await asyncio.sleep(0.3)
    assert done is True
