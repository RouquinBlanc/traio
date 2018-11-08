import asyncio
import logging

import pytest

from mock import Mock
from tests import run10

from traio import Nursery


def test_logging():
    """Logging Nursery"""
    Nursery.set_debug(True)
    nursery = Nursery()
    assert nursery.logger.level == logging.DEBUG
    Nursery.set_debug(False)
    assert nursery.logger.level >= logging.DEBUG


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
        n << run(mock)

    assert mock.called


@pytest.mark.asyncio
async def test_future():
    """Simple nursery with a future; should not timeout"""
    async with Nursery(timeout=0.1) as n:
        f = asyncio.Future()
        n.start_soon(f)
        f.set_result(None)


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
            n << raiser()


@pytest.mark.asyncio
async def test_task_count():
    """Raise an exception from a task"""
    async with Nursery() as out:
        for i in range(1, 11):
            out << run10()
            assert len(out.get_tasks()) == i

        async with out.fork() as inner:
            inner << run10()
            inner << run10()
            inner << run10()

            assert len(out.get_tasks()) == 11
            assert len(inner.get_tasks()) == 3

            # Now cancel both
            out.cancel()
