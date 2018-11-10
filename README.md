# A simple asyncio wrapper attempting to look like Trio

[![Build Status](https://travis-ci.org/RouquinBlanc/traio.svg?branch=master)](https://travis-ci.org/RouquinBlanc/traio) [![Coverage Status](https://coveralls.io/repos/github/RouquinBlanc/traio/badge.svg?branch=master)](https://coveralls.io/github/RouquinBlanc/traio?branch=master)

When going deeper and deeper with asyncio, and managing a lot of tasks
in parallel, you notice that on top of having a lot to deal with
to keep an eye on all your task, you also end up always doing the
same kind of boiler plate, and the code can become easily twisted and
unreadable.

[Trio](https://github.com/python-trio/trio) is there to make asynchronous programming easy and more "for humans".

Traio (as kind of Trio on top of Asyncio) let you use asyncio with a little of
the philosophy of Trio, mostly the Nursery concept (called Scope here).
It also synthesize the most common pattern we are using for handling async
tasks in a sane way.

## Disclaimer

This is *not* a replacement for Trio: if you do a full Trio-like project,
just use Trio! It's just truly awesome, but in some cases you get stuck 
with asyncio, but still want to have a code you can read and manage...

Because we run on top of asyncio, we are quite limited in how we can handle
cancellation, scopes, and coroutines. This is *just* on top of asyncio, this
is not an alternative! But on the good side, you can mix this with regular
asyncio code, which can look appealing.

## Examples

### Simple Scope

The main way to use the Scope is (like in Trio) as a context manager

```python
import asyncio
from traio import Scope

async def fetch_url(x):
    # Do something long
    await asyncio.sleep(3)

async def main():
    async with Scope(timeout=10) as scope:
        for i in range(10):
            scope.spawn(fetch_url(i))
```

The `Scope.spawn` method, called on an awaitable thing, will spawn a task and
register it on the scope. An equivalent exist using the `<<` operator (see next
example).

When reaching the end of the context block, the code will block until:
- all tasks are done
- or the timeout is over
- or the scope get's cancelled.

You can also use the Scope without context manager:

```python
import asyncio
from traio import Scope

async def fetch_url(x):
    # Do something long
    await asyncio.sleep(3)

async def main():
    # Equivalent to previous example
    scope = Scope(timeout=10)
    
    for i in range(10):
        scope << fetch_url(i)
        
    await scope.join()
```

### Names and logger

If you went deep enough in asyncio misteries, you know that tracing code is
(for now) kind of a nightmare... For that reason, Scope as well as tasks can
be instantiated with a name. The Scope can also take a logger which will be
used for tracing most of the calls and task life cycle, mostly with debug level. 

### Special tasks

`Scope.spawn` can be called with different parameters with interesting
effects:

- The `bubble` boolean parameter controls task error bubbling. A task will
bubble by default. This means that an error in the taskwill cause the task 
to stop (of course), but the scope will be cancelled as well and raise 
the given error. This is the desired default behavior.
But it can be useful in some cases not to do that, and just ignore a task.
Not that if you await manually a task, this cancels bubbling automatically:
if you take the pain of waiting for a task, it's not to get all the rest cancelled!

```python
import asyncio
from traio import Scope

async def fetch_url():
    # Do something long
    await asyncio.sleep(10)
    
async def trivial():
    await asyncio.sleep(0.01)
    raise ValueError('not interesting')

async def main():

    async with Scope(timeout=0.5) as n:
        # This will try to run for 10 seconds
        n << fetch_url()
        
        # This will run a bit then raise (but not 'bubble')
        n.spawn(trivial(), bubble=False)
        
    # Eventually after 0.5 seconds the Scope times out and
    # gives a TImeoutError
```

- A task can be marked as `master`, in that case the scope will die with the 
task when done. This is typically useful when you have one main task to be
performed and other background ones, which have no meaning if the main one stops.

```python
import asyncio
from traio import Scope

async def fetch_url():
    # Do something long
    await asyncio.sleep(10)
    
async def trivial():
    await asyncio.sleep(0.01)

async def main():

    async with Scope(timeout=0.5) as n:
        # This will try to run for 10 seconds
        n << fetch_url()
        
        # This will run a bit then scope gets cancelled when it ends
        n.spawn(trivial(), master=True)
```

Note you can combine both flags; If bubble is False and master is True,
the scope will exit silently when the task is done, even with an exception.

### Nested Scope

That's one of the most exciting ones: you can spawn a sub-scope from the
original one, which will follow the same rules as any Scope but will as well
die if the parent is cancelled!

```python
import asyncio
from traio import Scope

async def fetch_url():
    # Do something long
    await asyncio.sleep(10)

async def main():

    async with Scope(timeout=0.2):
        async with Scope(timeout=0.5) as inner:
            # This will try to run for 10 seconds
            inner << fetch_url()
        
    # Here the outer Scope will timeout first and will cancel the inner one!
```

### Getting current Scope

Using the awesome [contextvars](https://www.python.org/dev/peps/pep-0567/) and 
the current backport of it [aiocontextvars](https://github.com/fantix/aiocontextvars),
we can keep track of the current active scope without necessarily passing the
scope variable all along the call chain.

```python
async def handler(client):
    # This runs in the scope `main_scope`
    # Create a subscope of the current one
    async with Scope.get_current().fork() as s:
        # Here we are in the scope of `s`, as well as spawned tasks
        s << do_something(client)
        s << do_something_else(client)
        
async def server(main_scope):
    # This runs in the scope `main_scope`
    client = await new_connection()
    main_scope.spawn(handler(client))
        
async def main():
    async with Scope() as main_scope:
        main_scope << server(main_scope)
        main_scope << do_something_else()
```

### Caveat

Remember that **we do not modify the way asyncio works**. Asyncio is still
in charge of scheduling all tasks. In that aspect, if you block you scope
awaiting for something *not* handled by the scope, the timeouts and cancellation
won't apply until your current task is done. Instead, try to wrap your task in a
call to `Scope.spawn`.

So instead of this:
```python
async with Scope() as n:
    await my_very_long_task()
```
try to do this:
```python
async with Scope() as n:
    await n.spawn(my_very_long_task())
```

## Status

This is still alpha; the principle was validated and the various tests ensure
a pretty good coverage as well as examples. But the API may vary a bit for a while
until we figure out what to add.

## TODOS

- write more examples
- extend the API:
  - new `Scope` APIs
  - new kinds of tasks, for example executors (although we have no way to stop 
  a thread executor...)
  - After discovering a very similar project called [Ayo](https://github.com/Tygs/ayo), see what 
  good features can be integrated (love the `<<` operator!)
- play more with the real Trio and get a better feeling of it
- get some user feedback if possible!