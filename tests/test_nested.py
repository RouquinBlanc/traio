"""
Test nested Nurseries
"""

import time

import pytest

from tests import run10
from traio import Nursery


@pytest.mark.asyncio
async def test_nested_unrelated():
    """
    Two nested Nurseries, but completely unrelated.
    Remember that we cannot do magic (yet).
    As long as the inner code is blocking and
    not related to the surrounding Nursery,
    The outer timeout will be stuck!
    """
    before = time.time()

    with pytest.raises(TimeoutError):
        async with Nursery(timeout=0.2):
            async with Nursery(timeout=0.5) as inner:
                """
                A completely different
                """
                inner.start_soon(run10())

    after = time.time()
    assert (after - before) > 0.4, 'for now...'
