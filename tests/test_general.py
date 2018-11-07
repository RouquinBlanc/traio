import asyncio

import pytest

from mock import Mock

from traio import Nursery


@pytest.mark.asyncio
async def test_empty():
    """Empty Nursery"""
    async with Nursery():
        pass


@pytest.mark.asyncio
async def test_empty_timeout():
    """Empty Nursery"""
    async with Nursery(timeout=0.1):
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

    with pytest.raises(ValueError):
        async with Nursery() as n:
            n.start_soon(raiser())
