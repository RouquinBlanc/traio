"""
AsyncTask wrapping an asyncio task, with a bit of boiler plate.
"""

import asyncio
import time
from typing import Awaitable


class AsyncTask(asyncio.Future):
    """
    Task convenient object used by nursery
    """

    def __init__(self, awaitable: Awaitable, *,
                 cancel_timeout=1, bubble=True, master=False, name=None):
        """
        Create a Task to be executed
        :param awaitable: awaitable we are wrapping
        :param cancel_timeout: When cancelling, ensure the coroutine has finished
        :param bubble: an exception in this task will pop in the nursery
        :param master: when this task finishes, cancel nursery
        :param name: convenient name for logging
        """
        super().__init__()
        self.cancel_timeout = cancel_timeout
        self.bubble = bubble
        self.master = master
        self.name = name

        self.start_time = time.time()
        self.awaitable = asyncio.ensure_future(awaitable)
        self.awaitable.add_done_callback(self._awaitable_done)

    def __repr__(self):
        return self.name if self.name is not None else str(self.awaitable)

    def _awaitable_done(self, fut: asyncio.Future):
        try:
            self.set_result(fut.result())
        except asyncio.CancelledError:
            super().cancel()
        except Exception as ex:  # pylint: disable=broad-except
            self.set_exception(ex)

    # --- API ---

    def __await__(self, *args, **kwargs):
        """
        Awaiting explicitly a task (never done internally),
        """
        self.bubble = False
        return super().__await__(*args, **kwargs)

    def cancel(self):
        """Perform cancellation on internal future"""
        self.awaitable.cancel()
