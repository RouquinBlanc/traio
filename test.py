
import asyncio

async def nasty():
    while True:
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            continue

loop = asyncio.get_event_loop()

loop.run_until_complete(asyncio.wait_for(asyncio.shield(nasty()), 2))

