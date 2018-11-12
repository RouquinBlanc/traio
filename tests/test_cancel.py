"""
Various task & scope cancellation tests
"""

import asyncio
import time

import pytest

from tests import run10
from traio import Scope


@pytest.mark.asyncio
async def test_task_catches_cancel():
    """A nasty task catches all exceptions"""
    async def nasty():
        while True:
            try:
                await asyncio.sleep(1)
                print('loop')
            except asyncio.CancelledError:
                # Prevent the bloody cancel!
                pass

    before = time.time()

    with pytest.raises(OSError):
        async with Scope(timeout=0.1) as n:
            n.spawn(nasty(), cancel_timeout=0.5)

    after = time.time()
    assert 0.4 < (after - before) < 1


@pytest.mark.asyncio
async def test_external_cancel():
    """Raise an external cancellation"""
    async def run_me():
        n = Scope()
        async with n:
            n.spawn(run10())

        assert n.cancelled()

    task = asyncio.ensure_future(run_me())

    try:
        await asyncio.wait_for(asyncio.shield(task), 0.1)
    except asyncio.TimeoutError:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        raise Exception('should have raised')


@pytest.mark.asyncio
async def test_external_cancel_nasty():
    """Raise an external cancellation with task which fails cancelling"""
    async def nasty():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            # Something bad happens
            raise ValueError('boom')

    async def run_me():
        n = Scope()
        async with n:
            n.spawn(nasty())

        assert n.cancelled()

    task = asyncio.ensure_future(run_me())

    try:
        await asyncio.wait_for(task, 0.1)
    except asyncio.TimeoutError:
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        raise Exception('should have raised')


@pytest.mark.asyncio
async def test_internal_cancel():
    """Test an internal cancellation"""
    before = time.time()

    async with Scope() as n:
        n.spawn(run10())
        await asyncio.sleep(0.2)
        n.cancel()

    after = time.time()

    assert (after - before) < 0.5


@pytest.mark.asyncio
async def test_cancelling_going_bad():
    """Test cancelling a pending task, but things go wrong..."""
    async def nasty():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            # Something bad happens
            raise ValueError('boom')

    with pytest.raises(TimeoutError):
        async with Scope(timeout=0.5) as n:
            n.spawn(nasty())

    await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_cancel_not_joined_yet():
    """
    When we cancel the nursery, it hasn't been joined yet.
    This should cancel it anyway.
    """
    async def cleaner():
        await asyncio.sleep(0.2)
        Scope.get_current().cancel()
        await asyncio.sleep(10)

    before = time.time()

    async with Scope() as s:
        s << cleaner()

        await asyncio.sleep(1)
        raise Exception('never called')

    after = time.time()
    assert (after - before) < 0.4, 'for now...'
