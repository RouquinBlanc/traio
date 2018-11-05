# A simple asyncio wrapper attempting to look like Trio

[![Build Status](https://travis-ci.org/RouquinBlanc/traio.svg?branch=master)](https://travis-ci.org/RouquinBlanc/traio) [![Coverage Status](https://coveralls.io/repos/github/RouquinBlanc/traio/badge.svg?branch=master)](https://coveralls.io/github/RouquinBlanc/traio?branch=master)

When going deeper and deeper with asyncio, and managing a lot of tasks
in parallel, you notice that on top of having a lot to deal with
to keep an eye on all your task, but you also end up always doing the
same kind of boiler plate...

Traio (as Trio on asyncio) let you use asyncio with the philosophy of Trio.
This is *not* a replacement for Trio: if you do a full Trio-like project,
just switch to it!
Trio is just awesome, but in some cases you get stuck with asyncio,
but still want to have a code you can read and manage...

Example:

```python
import asyncio
from traio import Nursery

async def main():

    async def fetch_url(x):
        # Do something long
        await asyncio.sleep(3)

    async with Nursery(timeout=10) as nursery:
        for i in range(10):
            nursery.start_soon(fetch_url(i))
```

## Status

This is still alpha...

## TODOS

- write more examples
- write more test
- extend the API
- put CI in place