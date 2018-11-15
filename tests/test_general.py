import asyncio
import logging

import pytest

from mock import Mock
from tests import run10

from traio import Scope


def test_version():
    """Just ensure we have a version string"""
    from traio.__version__ import __version__
    assert isinstance(__version__, str)


def test_logging():
    """Logging Scope"""
    Scope.set_debug(True)
    scope = Scope()
    assert scope.logger.level == logging.DEBUG
    Scope.set_debug(False)
    assert scope.logger.level >= logging.DEBUG


@pytest.mark.asyncio
async def test_empty():
    """Empty Scope"""
    async with Scope():
        pass


@pytest.mark.asyncio
async def test_empty_timeout():
    """Empty Scope"""
    async with Scope(timeout=0.1):
        pass


@pytest.mark.asyncio
async def test_simple():
    """Simple scope with one execution"""
    async def run(m):
        await asyncio.sleep(0.01)
        m()

    mock = Mock()

    async with Scope() as n:
        n << run(mock)

    assert mock.called


@pytest.mark.asyncio
async def test_future():
    """Simple scope with a future; should not timeout"""
    async with Scope(timeout=0.1) as n:
        f = asyncio.Future()
        n.spawn(f)
        f.set_result(None)


@pytest.mark.asyncio
async def test_block_raises():
    """Raise an exception from the block"""
    with pytest.raises(ValueError):
        async with Scope():
            raise ValueError('boom')


@pytest.mark.asyncio
async def test_task_raises():
    """Raise an exception from a task"""
    async def raiser():
        await asyncio.sleep(0.01)
        raise ValueError('boom')

    with pytest.raises(ValueError):
        async with Scope() as n:
            n << raiser()


@pytest.mark.asyncio
async def test_task_count():
    """Raise an exception from a task"""
    async with Scope() as out:
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
