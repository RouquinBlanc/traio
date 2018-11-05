"""
Implement a kind-of Nursery like what you would get of Trio.
Except:
    - we do it on top of asyncio
    - we do not pretend implementing an equivalent of Trio; just the philosophy!
    - no pretensions; if you want more Trio-like, just switch to Trio!
"""
import asyncio
import logging
from enum import Enum
from typing import Awaitable

from .task import AsyncTask


class State(Enum):
    """States of a nursery instance"""
    INIT = 0
    STARTED = 1
    DONE = 2
    CANCELLED = 3
    ERROR = 4


class Nursery:
    """
    Trio-like nursery (or at least a very light & dumb implementation...)

    At least it runs on top of asyncio, not "instead of" it.

    You can use it in 2 ways:

    1) With an environment, automatically joining the nursery at exit

    ```
    async with Nursery(...) as nursery:
        nursery.start_soon(my_task1)
        nursery.start_soon(my_task2)
    ```

    2) Without it:
    ```
    nursery = Nursery(...)
    nursery.start_soon(my_task1)
    nursery.start_soon(my_task2)
    nursery.start()

    [...]
    await nursery.join()
    ```

    At any point in time, the nursery can be cancelled (with or without an exception).
    This will cause:
        - the stopping and cleaning up of all tasks
        - the nursery to be marked as done (join() will return)
    """

    # pylint: disable=too-many-instance-attributes
    def __init__(self, logger=None, timeout=None, name=None):
        """
        Create a nursery.

        :param logger: Can pass a logger. By default using `traio` logger
        :param timeout: if timeout is specified
        :param name:
        """
        self.logger = logger or logging.getLogger('traio')

        self._pending_tasks = []

        assert timeout is None or timeout >= 0, \
            'timeout should be a positive integer or (0, None) when disabled'
        self._timeout_task = None
        self.timeout = 0
        self._timeout = timeout

        self._name = name or '-'
        self._done = asyncio.Future()
        self.state = State.INIT

    def __repr__(self):
        """For printing"""
        return self._name

    async def __aenter__(self):
        self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            # An exception occurred: cleanup
            self.cancel(exc_val)
        await self.join()

    async def _timeout_handler(self):
        await asyncio.sleep(self.timeout)
        self.cancel(TimeoutError())

    def remove_task(self, task: AsyncTask):
        """Remove a task from the nursery"""
        if task in self._pending_tasks:
            self._pending_tasks.remove(task)

        if not self._pending_tasks and not self._done.done():
            self.cancel()

    @property
    def timeout(self) -> float:
        """Get current timeout value"""
        return self._timeout

    @timeout.setter
    def timeout(self, value: float):
        """
        Reset timeout to value
        """
        self._timeout = value
        if self._timeout_task:
            self._timeout_task.cancel()
            self._timeout_task = None
        if self.timeout > 0:
            self._timeout_task = self.start_soon(
                self._timeout_handler(), name='nursery timeout')

    def cancel(self, exception: Exception = None):
        """
        Cancel nursery.
        This will stop whatever was started by the nursery,
        and raise given Exception if needed.
        :param exception: Exception to be raised
        """
        assert self.state == State.STARTED, 'can only cancel a running nursery'

        for task in self._pending_tasks:
            if not task.done():
                self.logger.info(
                    'cancelling active `%s` task from nursery `%s`', task, self)
                task.cancel()

        if exception:
            self.logger.warning(
                'cancelling nursery `%s` with %s: %s',
                self, exception.__class__.__name__, exception
            )
            self._done.set_exception(exception)
        else:
            self.logger.info('cancelling nursery `%s`', self)
            self._done.set_result(None)

    def start(self):
        """
        Start the Nursery. If any timeout is configured, we start counting from now.
        """
        assert self.state == State.INIT, 'can only start a nursery once'
        self.state = State.STARTED

        if self._timeout:
            # Force timeout reset to now
            self.timeout = self._timeout

    async def join(self):
        """Await for all tasks to be finished, or an error to go through"""
        assert self.state == State.STARTED, 'can only join a started nursery'

        if not self._pending_tasks and not self._done.done():
            # There is no task registered or left.
            self._done.set_result(None)

        try:
            await self._done
            self.state = State.DONE
        except asyncio.CancelledError:
            self.logger.info('nursery `%s` cancelled from outside!', self)
            self.state = State.CANCELLED
            raise
        finally:
            if self.state == State.STARTED:
                self.state = State.ERROR

            # We may still have pending tasks if the Nursery is cancelled
            for task in self._pending_tasks:
                if not task.done():
                    await task.ensure_cancelled()

    def start_soon(
            self, awaitable: Awaitable, *,
            bubble=True, cancel_timeout=1, master=False, name=None
    ) -> AsyncTask:
        """
        Start a task on the nursery.

        :param awaitable: Something to be awaited. Can be a future or a coroutine
        :param bubble: errors in the task will cancel nursery
        :param cancel_timeout: Time we allow for cancellation
            (if the task wants to catch it and do cleanup)
        :param master: If a master task is done, nursery is cancelled
        :param name: task name (for logging)
        :return: the task created
        """
        if asyncio.iscoroutine(awaitable) or asyncio.isfuture(awaitable):
            # This is already an awaitable object
            fut = awaitable
        else:
            raise OSError('this thing is not awaitable: {}!'.format(awaitable))

        task = AsyncTask(
            self, fut, cancel_timeout=cancel_timeout,
            bubble=bubble, master=master, name=name)
        self.logger.info('adding task `%s` to nursery `%s`', task, self)
        self._pending_tasks.append(task)
        return task
