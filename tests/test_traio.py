import asyncio
import time

import pytest

from mock import Mock

from traio import Nursery, TaskException
from traio.nursery import State


async def run10():
    """Simple utility"""
    await asyncio.sleep(10)


@pytest.mark.asyncio
async def test_empty():
    """Empty Nursery"""
    async with Nursery():
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
async def test_timeout():
    """Simple timeout"""
    before = time.time()

    with pytest.raises(TimeoutError):
        async with Nursery(timeout=0.1) as n:
            n.start_soon(run10())

    after = time.time()
    assert (after - before) < 0.5


@pytest.mark.asyncio
async def test_timeout_override():
    """Override timeout value"""
    before = time.time()

    with pytest.raises(TimeoutError):
        async with Nursery(timeout=5) as n:
            n.start_soon(run10())
            n.timeout = 0.1

    after = time.time()
    assert (after - before) < 0.5


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
async def test_master_raises():
    """Raise an exception from a task"""
    async def raiser():
        await asyncio.sleep(0.01)
        raise ValueError('boom')

    try:
        async with Nursery() as n:
            n.start_soon(run10())
            n.start_soon(raiser(), master=True)
    except TaskException as e:
        assert isinstance(e.__cause__, ValueError)
    else:
        raise Exception('DID NOT RAISE')


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
        async with Nursery(timeout=0.1) as n:
            n.start_soon(nasty(), cancel_timeout=0.5)

    after = time.time()
    assert 0.4 < (after - before) < 1


@pytest.mark.parametrize('arg', [
    None,
    1,
    'hello',
    lambda x: x + 1
])
@pytest.mark.asyncio
async def test_task_not_awaitable(arg):
    """Call start_soon with different non-awaitable objects"""
    with pytest.raises(OSError):
        async with Nursery() as n:
            n.start_soon(arg)


@pytest.mark.asyncio
async def test_external_cancel():
    """Raise an external cancellation"""
    async def run_me():
        n = Nursery()
        async with n:
            n.start_soon(run10())

        assert n.state == State.CANCELLED

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
async def test_internal_cancel():
    """Test an internal cancellation"""
    before = time.time()

    async with Nursery() as n:
        n.start_soon(run10())
        await asyncio.sleep(0.2)
        n.cancel()

    after = time.time()

    assert (after - before) < 0.5


@pytest.mark.asyncio
async def test_cancel_not_started():
    """cancel an unstarted nursery"""
    n = Nursery()

    with pytest.raises(AssertionError):
        n.cancel()


@pytest.mark.asyncio
async def test_cancel_already_finished():
    """Cancel a finished nursery"""
    n = Nursery()
    async with n:
        pass

    with pytest.raises(AssertionError):
        n.cancel()


@pytest.mark.asyncio
async def test_master():
    """Test if a master correctly cancels pending tasks"""
    async def master():
        await asyncio.sleep(0.01)

    before = time.time()

    async with Nursery() as n:
        n.start_soon(run10())
        n.start_soon(master(), master=True)

    after = time.time()

    assert (after - before) < 0.5


@pytest.mark.asyncio
async def test_no_bubble():
    """Test iif no bubble does not cancel nursery"""
    async def trivial():
        await asyncio.sleep(0.01)
        raise Exception('not interresting')

    before = time.time()

    with pytest.raises(TimeoutError):
        async with Nursery(timeout=0.5) as n:
            n.start_soon(run10())
            n.start_soon(trivial(), bubble=False)

    after = time.time()

    assert (after - before) > 0.4


@pytest.mark.asyncio
async def test_no_bubble_master():
    """Test if no bubble does not raise, but cancels because of master=True"""
    async def trivial():
        await asyncio.sleep(0.01)
        raise Exception('not interresting')

    before = time.time()

    async with Nursery(timeout=0.5) as n:
        n.start_soon(run10())
        n.start_soon(trivial(), bubble=False, master=True)

    after = time.time()

    assert (after - before) < 0.2


@pytest.mark.asyncio
async def test_cancel_master():
    """Test if cancelling master cancels the loop"""

    before = time.time()

    async with Nursery(timeout=0.5) as n:
        n.start_soon(run10())

        t = n.start_soon(run10(), master=True)

        await asyncio.sleep(0.05)
        t.cancel()

    after = time.time()

    assert (after - before) < 0.2


@pytest.mark.asyncio
async def test_join_task():
    """Test joining a task"""
    async def trivial():
        await asyncio.sleep(0.2)

    before = time.time()

    async with Nursery(timeout=0.5) as n:
        t = n.start_soon(trivial(), bubble=False)
        await t.join()
        n.cancel()

    after = time.time()

    assert 0.1 < (after - before) < 0.5
