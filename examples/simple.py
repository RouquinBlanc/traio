import asyncio

from traio import Scope


async def main():
    """Example of usage"""

    async def run():
        """
        Run for 10 seconds, with an internal scope
        :return:
        """
        async with Scope(name='internal') as n2:
            print('running an internal scope')

            # Launch a background task loop
            async def periodic2():
                while True:
                    print('periodic2')
                    await asyncio.sleep(1)
            n2.spawn(periodic2(), name='periodic2')

            # Run content inside the scope env
            print("Sleep for 10 seconds...")
            await asyncio.sleep(10)
            print("done sleeping!")

            # Cancel the scope (as we have a periodic task)
            n2.cancel()

    async def _start_periodic_task():
        """
        Run a periodic task. This must be called with loop=True
        """
        for i in range(5, 0, -1):
            print('periodic, {} left'.format(i))
            await asyncio.sleep(1)
        raise Exception('boom!')

    async with Scope(timeout=10, name='main') as scope:
        # Launch a background task, catching exceptions if any
        scope.spawn(_start_periodic_task(), name='background task', bubble=False)

        # Run our main action which will cancel the scope as master
        scope.spawn(run(), name='main action', master=True)

        # You can reset the original timeout to shorter
        scope.timeout = 5

    print('all done')

asyncio.get_event_loop().run_until_complete(main())
