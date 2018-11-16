"""
Testing the `bubble` flag feature of `Scope.spawn`
"""

import asyncio
import time

import pytest

from tests import run10
from traio import Scope


@pytest.mark.parametrize('awaited', [True, False])
@pytest.mark.asyncio
async def test_no_bubble(awaited):
    """
    Test if no bubble does not cancel scope
    This is independent of awaited flag
    """
    async def trivial():
        await asyncio.sleep(0.01)
        raise ValueError('not interesting')

    before = time.time()

    with pytest.raises(TimeoutError):
        async with Scope(timeout=0.5) as n:
            n.spawn(run10())
            n.spawn(trivial(), bubble=False, awaited=awaited)

    after = time.time()

    assert (after - before) > 0.4


@pytest.mark.parametrize('awaited', [True, False])
@pytest.mark.asyncio
async def test_no_bubble_master(awaited):
    """
    Test if no bubble does not raise, but cancels because of master=True
    This is independent of awaited flag
    """
    async def trivial():
        await asyncio.sleep(0.01)
        raise ValueError('not interesting')

    before = time.time()

    async with Scope(timeout=0.5) as n:
        n.spawn(run10())
        n.spawn(trivial(), bubble=False, master=True, awaited=awaited)

    after = time.time()

    assert (after - before) < 0.2
