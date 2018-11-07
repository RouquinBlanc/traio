"""
AsyncTask wrapping an asyncio task, with a bit of boiler plate.
"""

import asyncio
import time
from typing import Awaitable


class TaskException(Exception):
    """Exception raised inside a Task will be wrapped"""

    def __init__(self, cause):
        super().__init__()
        self.__cause__ = cause


class AsyncTask(asyncio.Future):
    """
    Task convenient object used by nursery
    """

    def __init__(self, nursery, awaitable: Awaitable, *,
                 cancel_timeout=1, bubble=True, master=False, name=None):
        """
        Create a Task to be executed
        :param nursery: Parent nursery
        :param awaitable: awaitable we are wrapping
        :param cancel_timeout: When cancelling, ensure the coroutine has finished
        :param bubble: an exception in this task will pop in the nursery
        :param master: when this task finishes, cancel nursery
        :param name: convenient name for logging
        """
        super().__init__()
        self.nursery = nursery
        self.cancel_timeout = cancel_timeout
        self.bubble = bubble
        self.master = master
        self.name = name

        self.start_time = time.time()
        self.awaitable = asyncio.ensure_future(awaitable)
        self.awaitable.add_done_callback(self._cleanup)

    def __repr__(self):
        return self.name if self.name is not None else str(self.awaitable)

    def _cleanup(self, fut: asyncio.Future):
        try:
            self.set_result(fut.result())
        except asyncio.CancelledError:
            self.nursery.logger.info('task `%s` got cancelled', self)
            super().cancel()
        except Exception as ex:  # pylint: disable=broad-except
            self.nursery.logger.error(
                'task `%s` got an exception: %s', self, ex)
            self.set_exception(ex)
            if self.bubble:
                self.nursery.cancel(TaskException(ex))
        else:
            self.nursery.logger.info('task `%s` done', self)
        finally:
            if self.master:
                self.nursery.cancel()
            self.nursery.remove_task(self)

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
