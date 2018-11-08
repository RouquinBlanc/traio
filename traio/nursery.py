"""
Implement a kind-of Nursery like what you would get of Trio.
Except:
    - we do it on top of asyncio
    - we do not pretend implementing an equivalent of Trio; just the philosophy!
    - no pretensions; if you want more Trio-like, just switch to Trio!
"""

import asyncio
import logging
import time
from typing import Awaitable

from .task import AsyncTask, NamedFuture


DEFAULT_LOGGER = logging.getLogger('traio')
DEFAULT_LOGGER.setLevel(logging.CRITICAL)


class Nursery(NamedFuture):
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

    [...]
    await nursery.join()
    ```

    At any point in time, the nursery can be cancelled (with or without an exception).
    This will cause:
        - the stopping and cleaning up of all tasks
        - the nursery to be marked as done (join() will return)
    """

    def __init__(self, *, logger=None, timeout=0, name=None):
        """
        Create a nursery.

        :param logger: Can pass a logger. By default using `traio` logger
        :param timeout: timeout before cancelling all tasks
        :param name: nursery name (for logging)
        """
        super().__init__('Nursery', name)

        self.logger = logger or DEFAULT_LOGGER

        self._pending_tasks = []

        assert timeout >= 0, 'timeout must me a positive number'
        self._timeout_task = None
        self.timeout = self._timeout = timeout

        self._joining = False
        self.logger.debug('creating %s', self)

    async def __aenter__(self):
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
        """When timeout is reached, nursery is cancelled."""
        await asyncio.sleep(self.timeout)
        self.cancel(TimeoutError())

    def _on_task_done(self, task: AsyncTask):
        """Perform task cleanup"""
        try:
            task.result()
        except asyncio.CancelledError:
            self.logger.debug('%s got cancelled', task)
        except Exception as ex:  # pylint: disable=broad-except
            self.logger.debug('%s got an exception: %s', task, ex)
            if task.bubble:
                self.cancel(ex)
        else:
            self.logger.debug('%s done', task)
        finally:
            if task.master:
                self.cancel()

            if task in self._pending_tasks:
                self._pending_tasks.remove(task)

            if not self._pending_tasks and not self.done() and self._joining:
                # No more tasks scheduled: cancel the
                self.cancel()

    # --- Public API ---

    @classmethod
    def set_debug(cls, enabled):
        """Enable Global traio logging or not"""
        DEFAULT_LOGGER.setLevel(logging.DEBUG if enabled else logging.CRITICAL)

    def get_tasks(self):
        """
        Get a recursive listing of all running tasks in a nursery.
        It is a convenient tool to check if any future is staying alive
        for too long in your system.
        :return: dict containing task names and running time.
        """
        now = time.time()

        tasks = {}
        for task in self._pending_tasks:
            if isinstance(task.awaitable, Nursery):
                tasks[task.awaitable.__repr__()] = task.awaitable.get_tasks()
            else:
                tasks[task.__repr__()] = (now - task.start_time)

        return tasks

    @property
    def timeout(self) -> float:
        """Get current timeout value"""
        return self._timeout

    @timeout.setter
    def timeout(self, value: float):
        """Reset timeout to given value."""
        self._timeout = value
        if self._timeout_task:
            self._timeout_task.cancel()
            self._timeout_task = None
        if self.timeout > 0:
            self._timeout_task = asyncio.ensure_future(self._timeout_handler())

    # pylint: disable=arguments-differ
    def cancel(self, exception: Exception = None):
        """
        Cancel nursery.

        This will instruct the nursery to stop all remaining tasks,
        and eventually (after joining or exiting async context) will
        raise the provided exception.

        :param exception: Exception to be raised
        """
        if self._timeout_task:
            self._timeout_task.cancel()

        for task in self._pending_tasks:
            if not task.done():
                self.logger.debug(
                    'cancelling active %s from %s', task, self)
                task.cancel()

        if not self.done():
            if exception:
                self.logger.warning(
                    'cancelling %s with %s: %s',
                    self, exception.__class__.__name__, exception
                )
                self.set_exception(exception)
            else:
                self.logger.debug('cancelling %s', self)
                self.set_result(None)

    async def join(self, forever=False):
        """
        Await for all tasks to be finished, or an error to go through.

        Call this last after spawning all your tasks to await for all of
        them and perform cleanup properly. This only needs to be called
        if the nursery is *not* used as a context manager: The __aexit__
        function will call this automatically.
        """
        assert not self._joining, 'can only join a running nursery'

        if not forever:
            self._joining = True

            if not forever and not self._pending_tasks and not self.done():
                # There is no task left.
                self.set_result(None)

        try:
            await self
        except asyncio.CancelledError:
            self.logger.debug('%s cancelled from outside!', self)
            raise
        finally:
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
                        self.logger.error('%s could not be cancelled in time', self)
                        raise OSError(
                            'Could not cancel {}!!! Check your code!'.format(self)) from ex
                    except Exception as ex:  # pylint: disable=broad-except
                        # Too late for raising... and we need to move on cleaning other tasks!
                        self.logger.warning(
                            '%s failed to cancel with exception: %s %s',
                            task, ex.__class__.__name__, ex)

            if self._timeout_task:
                self._timeout_task.cancel()
                try:
                    await self._timeout_task
                except asyncio.CancelledError:
                    pass

    def start_soon(self, awaitable: Awaitable, *,
                   name=None, master=False, bubble=True, cancel_timeout=1):
        """
        Start a task on the nursery.

        This is the way to attach some Awaitable elements to the current Nursery.

        Depending on options, the behavior can be quite different:
        - A task will bubble by default. This means that an error in the task
        will cause the task to stop (of course), but the nursery will be cancelled
        as well and raise the given error. This is the desired default behavior.
        But it can be useful in some cases not to do that, and just ignore a task.
        Not that if you await manually a task, this cancels bubbling automatically:
        if you take the pain of waiting for a task, it's not to get all the rest cancelled!
        - A task can be marked as master, and in that case the nursery will die
        with the task when done. This is typically useful when you have one main task
        to be performed and other background ones, which have no meaning if the main one
        stops.

        Cancellation timeout represents the time we will wait a cancelled task
        before giving up; a task should not block cancellation at all, except for
        a brief resources cleanup. An OSError will pop in your face if cancellation
        takes too long!

        :param awaitable: Something to be awaited. Can be a future or a coroutine
        :param name: task name (for logging)
        :param master: If a master task is done, nursery is cancelled
        :param bubble: errors in the task will cancel nursery
        :param cancel_timeout: Time we allow for cancellation
            (if the task wants to catch it and do cleanup)
        :returns: AsyncTask
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
        self.logger.debug('adding %s to %s', task, self)
        self._pending_tasks.append(task)
        return task

    def __lshift__(self, other: Awaitable):
        """Pretty equivalent of `start_soon`"""
        return self.start_soon(other)

    def fork(self, *, name=None, timeout=0):
        """
        Fork a new Nursery from the current one!

        This is useful for keeping a long term nursery,
        but then spawning an ad-hoc one for some sub-task to be performed.
        The key feature here is that if the parent nursery is cancelled,
        the child one gets cancelled as well!

        You will note that an error in the child nursery will not bubble and
        cancel the parent Nursery automatically. But it will still raise an
        exception, which can be handled to closes things properly!
        The main reason for this choice is that if we had wanted to perform
        some tasks which would cause the parent to die, we would not have need
        an inner nursery for that...

        :param name: name for logging
        :param timeout: None by default
        :returns: Nursery
        """
        nursery = Nursery(logger=self.logger, timeout=timeout, name=name)
        self.start_soon(nursery, bubble=False, name=str(nursery))
        return nursery
