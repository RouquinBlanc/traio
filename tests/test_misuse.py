"""
Test various misuse of this library.
"""

import pytest

from traio import Scope


@pytest.mark.parametrize('arg', [
    None,
    1,
    'hello',
    lambda x: x + 1
])
@pytest.mark.asyncio
async def test_task_not_awaitable(arg):
    """Call spawn with different non-awaitable objects"""
    with pytest.raises(OSError):
        async with Scope() as n:
            n.spawn(arg)


@pytest.mark.asyncio
async def test_sync_ctx_manager():
    """Calling scope as a synchronous context manager"""
    with pytest.raises(RuntimeError):
        with Scope():
            pass
