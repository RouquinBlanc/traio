"""
AsyncTask wrapping an asyncio task, with a bit of boiler plate.
"""

import asyncio
import time
from typing import Awaitable


def describe(thing):
    """Try to make a pretty description of a thing"""
    if hasattr(thing, '__name__'):
        return thing.__name__
    return thing.__repr__()


class NamedFuture(asyncio.Future):
    """
    Just a future with a little of logging support
    """
    def __init__(self, kind, name):
        super().__init__()
        self._repr = '{}({}, {})'.format(kind, str(id(self)), name if name else '-')
        self.name = name

    def __repr__(self):
        return self._repr


class TaskWrapper(NamedFuture):
    """
    Task convenient object used by nursery
    """

    def __init__(self, awaitable: Awaitable, *,
                 cancel_timeout=1, bubble=True, master=False, awaited=True, name=None):
        """
        Create a Task to be executed
        :param awaitable: awaitable we are wrapping
        :param cancel_timeout: When cancelling, ensure the coroutine has finished
        :param bubble: an exception in this task will pop in the nursery
        :param master: when this task finishes, cancel nursery
        :param name: convenient name for logging
        """
        super().__init__('Task', name or describe(awaitable))
        self.cancel_timeout = cancel_timeout
        self.bubble = bubble
        self.master = master
        self.awaited = awaited

        self.start_time = time.time()
        self.awaitable = asyncio.ensure_future(awaitable)
        self.awaitable.add_done_callback(self._awaitable_done)

    def _awaitable_done(self, fut: asyncio.Future):
        try:
            self.set_result(fut.result())
        except asyncio.CancelledError:
            super().cancel()
        except Exception as ex:  # pylint: disable=broad-except
            self.set_exception(ex)

    # --- API ---

    def __await__(self):
        """
        Awaiting explicitly a task (never done internally);
        mark as no bubble: the awaiter is responsible for raising
        """
        self.bubble = False
        return super().__await__()

    # pylint: disable=arguments-differ
    def add_done_callback(self, *args, **kwargs):
        """
        When adding a done callback, mark as no bubble as well,
        the callback is responsible for raising
        """
        self.bubble = False
        return super().add_done_callback(*args, **kwargs)

    def cancel(self):
        """Perform cancellation on internal future"""
        self.awaitable.cancel()
