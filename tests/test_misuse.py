"""
Test various misuse of this library.
"""

import pytest

from traio import Nursery


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
async def test_sync_ctx_manager():
    """Calling nursery as a synchronous context manager"""
    with pytest.raises(RuntimeError):
        with Nursery():
            pass
