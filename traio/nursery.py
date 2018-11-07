"""
Implement a kind-of Nursery like what you would get of Trio.
Except:
    - we do it on top of asyncio
    - we do not pretend implementing an equivalent of Trio; just the philosophy!
    - no pretensions; if you want more Trio-like, just switch to Trio!
"""
import asyncio
import logging
from enum import IntEnum
from typing import Awaitable

from .task import AsyncTask


class State(IntEnum):
    """States of a nursery instance"""
    INIT = 0
    STARTED = 1
    JOINING = 2
    DONE = 3
    CANCELLED = 4
    ERROR = 5


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

    @property
    def _joining(self):
        return self.state.value >= State.JOINING.value

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

    def __enter__(self):
        """Protect against calling as regular context manager"""
        raise RuntimeError(
            "asynchronous context manager, use 'async with Nursery(...)'!"
        )

    def __exit__(self, *_):  # pragma: no cover
        assert False, 'This should never be called'

    async def _timeout_handler(self):
        await asyncio.sleep(self.timeout)
        self.cancel(TimeoutError())

    def _on_task_done(self, task: AsyncTask):

        try:
            task.result()
        except asyncio.CancelledError:
            self.logger.info('task `%s` got cancelled', task)
        except Exception as ex:  # pylint: disable=broad-except
            self.logger.error('task `%s` got an exception: %s', task, ex)
            if task.bubble:
                self.cancel(ex)
        else:
            self.logger.info('task `%s` done', task)
        finally:
            if task.master:
                self.cancel()

            if task in self._pending_tasks:
                self._pending_tasks.remove(task)

            if not self._pending_tasks and not self._done.done() and self._joining:
                # No more tasks scheduled: cancel the
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
            self._timeout_task = asyncio.ensure_future(self._timeout_handler())

    def cancel(self, exception: Exception = None):
        """
        Cancel nursery.
        This will stop whatever was started by the nursery,
        and raise given Exception if needed.
        :param exception: Exception to be raised
        """
        assert self.state != State.INIT, 'cannot cancel before even starting'

        if self._timeout_task:
            self._timeout_task.cancel()

        for task in self._pending_tasks:
            if not task.done():
                self.logger.info(
                    'cancelling active `%s` task from nursery `%s`', task, self)
                task.cancel()

        if not self._done.done():
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
        :return self for convenience
        """
        assert self.state == State.INIT, 'can only start a nursery once'
        self.state = State.STARTED

        if self._timeout:
            # Force timeout reset to now
            self.timeout = self._timeout

        return self

    async def join(self):
        """Await for all tasks to be finished, or an error to go through"""
        assert self.state == State.STARTED, 'can only join a started nursery'
        self.state = State.JOINING

        if not self._pending_tasks and not self._done.done():
            # There is no task left.
            self._done.set_result(None)

        try:
            await self._done
            self.state = State.DONE
        except asyncio.CancelledError:
            self.logger.info('nursery `%s` cancelled from outside!', self)
            self.state = State.CANCELLED
            raise
        finally:
            if self.state == State.JOINING:
                # Neither DONE nor CANCELLED
                self.state = State.ERROR

            # We may still have pending tasks if the Nursery is cancelled
            for task in self._pending_tasks:
                if not task.done():
                    task.cancel()
                    try:
                        await asyncio.wait_for(
                            # Since python 3.7, after timeout the wait_for API
                            # will try to cancel and await the future... which may block forever!
                            asyncio.shield(task),
                            task.cancel_timeout
                        )
                    except asyncio.CancelledError:
                        pass
                    except asyncio.TimeoutError as ex:
                        self.logger.error(
                            'task `%s` could not be cancelled in time', self)
                        raise OSError(
                            'Could not cancel task `{}`!!! Check your code!'.format(self)) from ex
                    except Exception as ex:  # pylint: disable=broad-except
                        # Too late for raising... and we need to move on cleaning other tasks!
                        self.logger.error(
                            'task `%s` failed to cancel with exception: %s %s',
                            task, ex.__class__.__name__, ex)

            if self._timeout_task:
                self._timeout_task.cancel()
                try:
                    await self._timeout_task
                except asyncio.CancelledError:
                    pass

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
            fut, cancel_timeout=cancel_timeout,
            bubble=bubble, master=master, name=name)
        task.add_done_callback(self._on_task_done)
        self.logger.info('adding task `%s` to nursery `%s`', task, self)
        self._pending_tasks.append(task)
        return task
