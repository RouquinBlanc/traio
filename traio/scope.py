"""
Implement a kind-of Nursery like what you would get of Trio.
Except:
    - we do it on top of asyncio
    - we do not pretend implementing an equivalent of Trio; just the philosophy!
    - no pretensions; if you want more Trio-like, just switch to Trio!
"""

import asyncio
import logging
import sys
import time
from typing import Awaitable, Optional
from aiocontextvars import ContextVar

from traio.task import NamedFuture, TaskWrapper

SCOPE = ContextVar('traio_scope')
DEFAULT_LOGGER = logging.getLogger('traio')
DEFAULT_LOGGER.setLevel(logging.CRITICAL)
PY37 = sys.version_info >= (3, 7)


def current_task(loop=None):
    """
    Return current task. Wraps difference between before/after py37
    """
    if PY37:
        return asyncio.current_task(loop)
    return asyncio.Task.current_task(loop)


class Scope(NamedFuture):
    """
    Trio-like nursery (or at least a very light & dumb implementation...)

    At least it runs on top of asyncio, not "instead of" it.

    You can use it in 2 ways:

    1) With an environment, automatically joining the scope at exit

    ```
    async with Scope(...) as scope:
        scope.spawn(my_task1)
        scope.spawn(my_task2)
    ```

    2) Without it:
    ```
    scope = Scope(...)
    scope.spawn(my_task1)
    scope.spawn(my_task2)

    [...]
    await scope.join()
    ```

    At any point in time, the scope can be cancelled (with or without an exception).
    This will cause:
        - the stopping and cleaning up of all tasks
        - the scope to be marked as done (join() will return)
    """

    # pylint: disable=too-many-instance-attributes
    def __init__(self, *, logger=None, timeout=0, name=None):
        """
        Create a scope.

        :param logger: Can pass a logger. By default using `traio` logger
        :param timeout: timeout before cancelling all tasks
        :param name: scope name (for logging)
        """
        super().__init__('Scope', name)

        # Internal state variables
        self._pending_tasks = []
        self._auto_done = False
        self._done = False
        self._token = None
        self._task = None
        self._timeout_task = None

        assert timeout >= 0, 'timeout must me a positive number'
        self.timeout = self._timeout = timeout

        # Using default `traio` logger if none provided
        self.logger = logger or DEFAULT_LOGGER
        self.logger.debug('creating %s', self)

    async def __aenter__(self):
        """
        While entering a scope, we need to do 3 things:
            - Setting the current scope for the code in the context block as self
            - Storing the contextvars token for resetting context on exit
            - Storing the current active task in case of cancellation before exit
        """
        assert self._token is None, 'can only enter scope context once!'
        self._token = SCOPE.set(self)
        self._task = current_task()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._task = None

        if exc_type:
            # An exception occurred: cleanup
            self.cancel(exc_val)

        # If we are done entering here, remember it
        silent = self._done is True

        # From here, we are going to exit on last task
        self.finalize()
        try:
            await self
        finally:
            SCOPE.reset(self._token)
            if silent:
                # When we entered here done with no exception, just swallow any error
                return True  # pylint: disable=lost-exception

    def __enter__(self):
        """Protect against calling as regular context manager"""
        raise RuntimeError(
            "asynchronous context manager, use 'async with Scope(...)'!"
        )

    def __exit__(self, *_):  # pragma: no cover
        assert False, 'This should never be called'

    async def _timeout_handler(self):
        """When timeout is reached, scope is cancelled."""
        await asyncio.sleep(self.timeout)
        self.logger.info('timeout on scope %s', self)
        self.cancel(TimeoutError())

    def _on_task_done(self, task: TaskWrapper):
        """Perform task cleanup"""
        try:
            task.result()
        except asyncio.CancelledError:
            self.logger.debug('%s got cancelled', task)
        except Exception as ex:  # pylint: disable=broad-except
            self.logger.debug('%s got an exception: [%s] %s', task, ex.__class__.__name__, ex)
            if task.bubble:
                self.cancel(ex)
        else:
            self.logger.debug('%s done', task)
        finally:
            if task.master:
                self.cancel()

            if task in self._pending_tasks:
                self._pending_tasks.remove(task)

            # That may be the last standing task
            self._may_be_done()

    def _may_be_done(self):
        """
        Try to see if we may be done with this scope
        :return: True if we are all set
        """
        if not self._done and self._auto_done and not any(t.awaited for t in self._pending_tasks):
            # No more awaited tasks scheduled: cancel the scope
            self.cancel()

    async def _cancel_proper(self, task, timeout=1):
        """
        Cancel a task and wait for it to finish for `timeout` seconds.
        If it fails to terminate, raise an OSError; otherwise, swallow.
        """
        task.cancel()
        try:
            # Since python 3.7, after timeout the wait_for API
            # will try to cancel and await the future... which may block forever!
            await asyncio.wait_for(asyncio.shield(task), timeout)
        except asyncio.CancelledError:
            # Perfect.
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

    def _resolve(self, _):
        """
        Resolve the scope: set its result
        :param _:
        :return:
        """
        assert self._done
        if self._done is True:
            self.set_result(None)
        else:
            self.set_exception(self._done)

    async def _join(self):
        """
        Await for all tasks to be finished, or an error to go through.

        Call this last after spawning all your tasks to await for all of
        them and perform cleanup properly. This only needs to be called
        if the scope is *not* used as a context manager: The __aexit__
        function will call this automatically.
        """
        # We may still have pending tasks if the Scope is cancelled
        for task in self._pending_tasks:
            if not task.done():
                await self._cancel_proper(task, timeout=task.cancel_timeout)

        if self._timeout_task:
            await self._cancel_proper(self._timeout_task)

    @staticmethod
    def _set_current(scope: Optional['Scope']):
        """
        Change current active scope. Do not mess to much with this!
        :param scope: Scope or None
        """
        return SCOPE.set(scope)

    # --- Public API ---

    @staticmethod
    def get_current() -> Optional['Scope']:
        """
        Get the current Scope instance, if any is set.
        current scope is set:
            - On any task spawned by a Scope
            - Inside the context of a Scope when used with 'async with'
            - Or whenever the scope is set manually with `Scope.set_current()`
        :returns:
        """
        return SCOPE.get(None)

    @classmethod
    def set_debug(cls, enabled):
        """Enable Global traio logging or not"""
        DEFAULT_LOGGER.setLevel(logging.DEBUG if enabled else logging.CRITICAL)

    def get_tasks(self):
        """
        Get a recursive listing of all running tasks in a scope.
        It is a convenient tool to check if any future is staying alive
        for too long in your system.
        :return: dict containing task names and running time.
        """
        now = time.time()

        tasks = {}
        for task in self._pending_tasks:
            if isinstance(task.awaitable, Scope):
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
        assert not self._done, 'cannot set timeout on dead/dying scope'
        self._timeout = value
        if self._timeout_task:
            self._timeout_task.cancel()
            self._timeout_task = None
        if self.timeout > 0:
            self._timeout_task = asyncio.ensure_future(self._timeout_handler())

    # pylint: disable=arguments-differ
    def cancel(self, exception: Exception = None):
        """
        Cancel scope.

        This will instruct the scope to stop all remaining tasks,
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

        # We only effectively cancel once
        if not self._done:
            self._done = exception if exception else True

            canceller = asyncio.ensure_future(self._join())  # type: asyncio.Future
            canceller.add_done_callback(self._resolve)

            if self._task:
                # Tricky scenario: we are using the scope as a context manager
                # and still didn't exit from the code block: cancel current task
                # to force the code to exit.
                self._task.cancel()

    def spawn(self, awaitable: Awaitable, *,
              name=None, master=False, bubble=True, awaited=True, cancel_timeout=1):
        """
        Start a task on the scope.

        This is the way to attach some Awaitable elements to the current Scope.

        Depending on options, the behavior can be quite different:
        - A task will bubble by default. This means that an error in the task
        will cause the task to stop (of course), but the scope will be cancelled
        as well and raise the given error. This is the desired default behavior.
        But it can be useful in some cases not to do that, and just ignore a task.
        Not that if you await manually a task, this cancels bubbling automatically:
        if you take the pain of waiting for a task, it's not to get all the rest cancelled!
        - A task can be marked as master, and in that case the scope will die
        with the task when done. This is typically useful when you have one main task
        to be performed and other background ones, which have no meaning if the main one
        stops.
        - A task will be awaited when the scope is in finalisation state. If marked
        as not awaited, the scope will cancel that task if nothing else is running.

        Cancellation timeout represents the time we will wait a cancelled task
        before giving up; a task should not block cancellation at all, except for
        a brief resources cleanup. An OSError will pop in your face if cancellation
        takes too long!

        :param awaitable: Something to be awaited. Can be a future or a coroutine
        :param name: task name (for logging)
        :param master: If a master task is done, scope is cancelled
        :param bubble: errors in the task will cancel scope
        :param awaited: will await this task when scope is finalized
        :param cancel_timeout: Time we allow for cancellation
            (if the task wants to catch it and do cleanup)
        :returns: AsyncTask
        """
        assert not self._done, 'cannot spawn tasks on dead or dying scope'

        if asyncio.iscoroutine(awaitable) or asyncio.isfuture(awaitable):
            # This is already an awaitable object
            fut = awaitable
        else:
            raise OSError('this thing is not awaitable: {}!'.format(awaitable))

        # Set this scope as current while we spawn a task
        token = SCOPE.set(self)
        task = TaskWrapper(
            fut, cancel_timeout=cancel_timeout,
            bubble=bubble, master=master, awaited=awaited, name=name)
        SCOPE.reset(token)
        task.add_done_callback(self._on_task_done)
        self.logger.debug('adding %s to %s', task, self)
        self._pending_tasks.append(task)
        return task

    def __lshift__(self, other: Awaitable):
        """Pretty equivalent of `spawn`"""
        return self.spawn(other)

    def fork(self, *, name=None, timeout=0):
        """
        Fork a new Scope from the current one!

        This is useful for keeping a long term scope,
        but then spawning an ad-hoc one for some sub-task to be performed.
        The key feature here is that if the parent scope is cancelled,
        the child one gets cancelled as well!

        You will note that an error in the child scope will not bubble and
        cancel the parent Scope automatically. But it will still raise an
        exception, which can be handled to closes things properly!
        The main reason for this choice is that if we had wanted to perform
        some tasks which would cause the parent to die, we would not have need
        an inner scope for that...

        :param name: name for logging
        :param timeout: None by default
        :returns: Scope
        """
        assert not self._done, 'cannot fork a dead or dying scope'
        scope = Scope(logger=self.logger, timeout=timeout, name=name)
        self.spawn(scope, bubble=False, name=str(scope))
        return scope

    def finalize(self):
        """
        Mark the scope as finalized:
        from now one, it will be cancelled automatically
        upon last task done.
        """
        self._auto_done = True
        self._may_be_done()
