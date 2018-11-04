import asyncio

from traio import Nursery


async def main():
    """Example of usage"""

    async def run():
        """
        Run for 10 seconds, with an internal nursery
        :return:
        """
        async with Nursery(name='internal') as n2:
            print('running an internal nursery')

            # Launch a background task loop
            async def periodic2():
                while True:
                    print('periodic2')
                    await asyncio.sleep(1)
            n2.start_soon(periodic2(), name='periodic2')

            # Run content inside the nursery env
            print("Sleep for 10 seconds...")
            await asyncio.sleep(10)
            print("done sleeping!")

            # Cancel the nursery (as we have a periodic task)
            n2.cancel()

    async def _start_periodic_task():
        """
        Run a periodic task. This must be called with loop=True
        """
        for i in range(5, 0, -1):
            print('periodic, {} left'.format(i))
            await asyncio.sleep(1)
        raise Exception('boom!')

    async with Nursery(timeout=10, name='main') as nursery:
        # Launch a background task, catching exceptions if any
        nursery.start_soon(_start_periodic_task(), name='background task', bubble=False)

        # Run our main action which will cancel the nursery as master
        nursery.start_soon(run(), name='main action', master=True)

        # You can reset the original timeout to shorter
        nursery.timeout = 5

    print('all done')

asyncio.get_event_loop().run_until_complete(main())
