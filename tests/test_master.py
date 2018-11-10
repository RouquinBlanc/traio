"""
Test the `master` feature of `Scope.spawn`
"""

import asyncio
import time

import pytest

from tests import run10
from traio import Scope


@pytest.mark.asyncio
async def test_master():
    """Test if a master correctly cancels pending tasks"""
    async def master():
        await asyncio.sleep(0.01)

    before = time.time()

    async with Scope() as n:
        n.spawn(run10())
        n.spawn(master(), master=True)

    after = time.time()

    assert (after - before) < 0.5


@pytest.mark.asyncio
async def test_master_raises():
    """Raise an exception from a task"""
    async def raiser():
        await asyncio.sleep(0.01)
        raise ValueError('boom')

    with pytest.raises(ValueError):
        async with Scope() as n:
            n.spawn(run10())
            n.spawn(raiser(), master=True)


@pytest.mark.asyncio
async def test_cancel_master():
    """Test if cancelling master cancels the loop"""

    before = time.time()

    async with Scope(timeout=0.5) as n:
        n.spawn(run10())

        t = n.spawn(run10(), master=True)

        await asyncio.sleep(0.05)
        t.cancel()

    after = time.time()

    assert (after - before) < 0.2
