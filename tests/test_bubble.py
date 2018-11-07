"""
Testing the `bubble` flag feature of `Nursery.start_soon`
"""

import asyncio
import time

import pytest

from tests import run10
from traio import Nursery


@pytest.mark.asyncio
async def test_no_bubble():
    """Test iif no bubble does not cancel nursery"""
    async def trivial():
        await asyncio.sleep(0.01)
        raise ValueError('not interesting')

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
        raise ValueError('not interesting')

    before = time.time()

    async with Nursery(timeout=0.5) as n:
        n.start_soon(run10())
        n.start_soon(trivial(), bubble=False, master=True)

    after = time.time()

    assert (after - before) < 0.2
