"""
Scope timeout tests
"""
import pytest
import time

from tests import run10
from traio import Scope


@pytest.mark.asyncio
async def test_timeout():
    """Simple timeout"""
    before = time.time()

    with pytest.raises(TimeoutError):
        async with Scope(timeout=0.1) as n:
            n.spawn(run10())

    after = time.time()
    assert (after - before) < 0.5


@pytest.mark.asyncio
async def test_timeout_override():
    """Override timeout value"""
    before = time.time()

    with pytest.raises(TimeoutError):
        async with Scope(timeout=5) as n:
            n.spawn(run10())
            n.timeout = 0.1

    after = time.time()
    assert (after - before) < 0.5
