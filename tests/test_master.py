"""
Test the `master` feature of `Nursery.start_soon`
"""

import asyncio
import time

import pytest

from tests import run10
from traio import Nursery, TaskException


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
