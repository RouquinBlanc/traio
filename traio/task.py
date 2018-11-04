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


class AsyncTask:
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
        self.nursery = nursery
        self.cancel_timeout = cancel_timeout
        self.bubble = bubble
        self.master = master
        self.name = name

        self.start_time = time.time()
        self.future = asyncio.ensure_future(awaitable)
        self.future.add_done_callback(self._cleanup)

    def __repr__(self):
        return self.name if self.name is not None else str(self.future)

    def _cleanup(self, fut: asyncio.Future):
        if fut.cancelled():
            self.nursery.logger.info('task `%s` got cancelled', self)
        else:
            try:
                fut.result()
            except asyncio.CancelledError:
                self.nursery.logger.info(
                    'task `%s` got cancelled', self)
            except Exception as ex:  # pylint: disable=broad-except
                self.nursery.logger.error(
                    'task `%s` got an exception: %s', self, ex)
                if self.bubble:
                    self.nursery.cancel(TaskException(ex))
            else:
                self.nursery.logger.info('task `%s` done', self)
            finally:
                # No exception
                if self.master:
                    # This was set as master task: finish at once
                    self.nursery.cancel()
                self.nursery.remove_task(self)

    # --- API ---

    async def join(self):
        """
        Wait for internal future to terminate
        :returns: whatever the internal things returned
        """
        return await self.future

    def done(self):
        """Internal future is done"""
        return self.future.done()

    def cancel(self):
        """Perform cancellation on internal future"""
        self.future.cancel()

    async def ensure_cancelled(self):
        """
        Ensure cancelled task has finished
        (a coro may catch cancel error for cleanup...)
        """
        self.cancel()
        try:
            await asyncio.wait_for(
                # Since python 3.7, after timeout the wait_for API
                # will try to cancel and await the future... which may block forever!
                asyncio.shield(self.future),
                self.cancel_timeout
            )
        except asyncio.CancelledError:
            pass
        except asyncio.TimeoutError as ex:
            self.nursery.logger.error(
                'task `%s` could not be cancelled in time', self)
            raise OSError(
                'Could not cancel task `{}`!!! Check your code!'.format(self)) from ex
