"""
Test joining a task in the middle of the scope
"""

import asyncio
import time

import pytest

from tests import run10
from traio import Scope


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

    async with Scope(timeout=0.5) as n:
        ret = await n.spawn(trivial())
        assert ret == 3

        t = n.spawn(trivial())
        assert 3 == await t

        # Cancel directly
        n.cancel()

    after = time.time()
    assert 0.1 < (after - before) < 0.5


@pytest.mark.asyncio
async def test_join_task_cancelled():
    """Test joining a task, but cancelled"""
    async with Scope(timeout=1) as n:
        t = n.spawn(run10())

        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t


@pytest.mark.parametrize('wait', [True, False])
@pytest.mark.asyncio
async def test_join_task_cancelled_no_env(wait):
    """Test joining a task, but cancelled"""
    n = Scope(timeout=1)

    t = n.spawn(run10())

    t.cancel()
    with pytest.raises(asyncio.CancelledError):
        await t

    n.finalize()
    if wait:
        await asyncio.wait_for(n, 2)
    else:
        await n


@pytest.mark.asyncio
async def test_join_task_raises():
    """Test joining a task, but raises"""
    before = time.time()

    async with Scope(timeout=1) as n:
        t = n.spawn(raiser())
        with pytest.raises(ValueError):
            # Catching the error here prevents bubbling
            await t

    after = time.time()
    assert (after - before) < 0.3


@pytest.mark.asyncio
async def test_join_task_raises_no_env():
    """Test joining a task, but raises"""
    before = time.time()

    n = Scope(timeout=1)

    t = n.spawn(raiser())
    with pytest.raises(ValueError):
        # Catching the error here prevents bubbling
        await t

    n.finalize()
    await n

    after = time.time()
    assert (after - before) < 0.3


@pytest.mark.asyncio
async def test_join_then_new():
    """Test joining a task, then spawn another one"""
    before = time.time()

    async with Scope(timeout=1) as n:
        # takes 0.2 seconds
        await n.spawn(trivial())
        assert (time.time() - before) < 0.3

        # At this point, the scope should be still started
        assert not n.done()

        # will 0.2 seconds
        n.spawn(trivial())

    after = time.time()
    assert (after - before) < 0.5


@pytest.mark.asyncio
async def test_join_then_new_no_env():
    """Test joining a task, then spawn another one"""
    before = time.time()

    n = Scope(timeout=1)

    # takes 0.2 seconds
    await n.spawn(trivial())
    assert (time.time() - before) < 0.3

    # At this point, the scope should be still started
    assert not n.done()

    # will 0.2 seconds
    n.spawn(trivial())

    n.finalize()
    await n

    after = time.time()
    assert (after - before) < 0.5


@pytest.mark.asyncio
async def test_join_forever():
    """Test joining a task, then joining forever"""
    n = Scope(timeout=0.5)

    # will run 0.2 seconds
    n << trivial()

    with pytest.raises(TimeoutError):
        # We join forever: this will stay alive even if the trivial task is done!
        await n


@pytest.mark.asyncio
async def test_join_cleanup():
    """
    Ensure that when the scope is done,
    all tasks have been cleaned properly.
    """
    done = False

    async def job():
        nonlocal done
        try:
            await asyncio.sleep(10)
        finally:
            done = True

    scope = Scope()

    # will run 0.2 seconds
    scope << job()

    await asyncio.sleep(0.1)

    scope.cancel()
    await scope

    assert done


@pytest.mark.asyncio
async def test_join_cleanup_external():
    """
    Ensure that when the scope is done,
    all tasks have been cleaned properly.
    """
    done = False

    async def job():
        nonlocal done
        try:
            await asyncio.sleep(10)
        finally:
            done = True

    async def cleaner(scope):
        await asyncio.sleep(0.2)
        scope.cancel()

    scope = Scope()
    c = asyncio.ensure_future(cleaner(scope))

    async with scope:
        scope << job()

    await c
    assert done


@pytest.mark.asyncio
async def test_join_cleanup_external2():
    """
    Ensure that when the scope is done,
    all tasks have been cleaned properly.
    """
    done = False
    scope = Scope()

    async def job():
        nonlocal done
        try:
            await asyncio.sleep(10)
        finally:
            done = True

    async def runner(scope):
        async with scope:
            scope << job()

    task = asyncio.ensure_future(runner(scope))

    # Wait a bit so that everyone is started and blocked
    await asyncio.sleep(0.2)

    # Now: scope should be joining, pending on job
    assert not done

    # Cancel the scope and await the scope
    scope.cancel()
    await scope

    # As soon as scope is done, we should have cleaned up job
    assert done

    await task


@pytest.mark.asyncio
async def test_join_not_waited_alone():
    """
    Ensure that when the scope is done,
    all tasks not awaited are cancelled without waiting
    """
    before = time.time()

    async with Scope() as scope:
        scope.spawn(run10(), awaited=False)

    after = time.time()
    assert (after - before) < 0.1


@pytest.mark.asyncio
async def test_join_not_waited_with_task():
    """
    Ensure that when the scope is done,
    all tasks not awaited are cancelled without waiting
    """
    before = time.time()

    async with Scope() as scope:
        scope.spawn(run10(), awaited=False)
        scope << asyncio.sleep(0.2)

    after = time.time()
    assert 0.1 < (after - before) < 0.3


@pytest.mark.asyncio
async def test_join_not_waited_with_timeout():
    """
    Ensure that when the scope is done,
    all tasks not awaited are cancelled without waiting
    """
    before = time.time()

    with pytest.raises(TimeoutError):
        async with Scope(timeout=0.2) as scope:
            scope.spawn(run10(), awaited=False)
            scope << run10()

    after = time.time()
    assert 0.1 < (after - before) < 0.3


@pytest.mark.asyncio
async def test_join_not_waited_but_clean():
    """
    Ensure that when the scope is done,
    all tasks not awaited are cancelled without waiting.
    But also check that tasks are properly finalised (cancelled and awaited)
    """
    before = time.time()
    done = False

    async def background():
        nonlocal done
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            done = True

    with pytest.raises(TimeoutError):
        async with Scope(timeout=0.2) as scope:
            scope.spawn(background(), awaited=False)
            scope << asyncio.sleep(0.2)

    after = time.time()
    assert 0.1 < (after - before) < 0.3
    assert done is True
