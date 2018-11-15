"""
    Traio: A simple asyncio wrapper attempting to look like Trio

    When going deeper and deeper with asyncio, and managing a lot of tasks
    in parallel, you notice that on top of having a lot to deal with
    to keep an eye on all your task, but you also end up always doing the
    same kind of boiler plate...

    Traio (as Trio on asyncio) let you use asyncio with the philosophy of Trio.
    This is *not* a replacement for Trio: if you do a full Trio-like project,
    just switch to it!
    Trio is just awesome, but in some cases you get stuck with asyncio,
    but still want to have a code you can read and manage...
"""

from .scope import Scope

__all__ = [
    'Scope'
]
