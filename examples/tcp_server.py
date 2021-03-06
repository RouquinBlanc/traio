"""
An example using a TCP server.

This looks overkill because you just need to Ctrl-C
or close the loop to reach the same, but thing that this
could be run in a corner of your code, with a running loop,
and allow you to clean up all your tasks related to your TCP server
with just a cancel on the main scope!
"""
import asyncio
import logging

from traio import Scope


class Server:
    """Async TCP server using a scope to clean up everything"""
    def __init__(self):
        self.scope = Scope(name='TCP')
        self.scope.add_done_callback(self.stop)
        self.server = None

    def stop(self, _):
        print('scope done. closing server')
        if self.server:
            self.server.close()

    async def run(self):
        # Start TCP server
        self.server = await asyncio.start_server(self.client_connected, '0.0.0.0', 5000)

        # Join the scope forever
        await self.scope

    async def client_connected(self, reader, writer):
        peer = writer.get_extra_info('peername')
        print(peer, 'connected')

        async with self.scope.fork(name=peer) as ctx:
            # We make one context for this connection
            # Here it's overkill, but you could have to spawn many jobs!
            try:
                while True:
                    try:
                        data = await (ctx << reader.readline())
                    except OSError as ex:
                        print(peer, 'socket error:', ex)
                        break

                    if not data:
                        # Connection closed
                        break

                    txt = data.decode().strip()
                    print(peer, 'received:', txt)

                    if txt == 'stop':
                        # Cancel the scope and exit
                        print('>>> stopping server')
                        writer.write('Closing!\n'.encode())
                        self.scope.cancel()
                        break

                    # Write reply and loop
                    writer.write('Hello {}!\n'.format(txt).encode())

                    # Just for fun, print later the received message
                    ctx << self.print_later(txt)
            finally:
                # Always say goodbye
                writer.write('Bye!\n'.encode())
                writer.close()
                print(peer, 'closed')

    @staticmethod
    async def print_later(txt):
        await asyncio.sleep(1)
        print('received earlier:', txt)


async def main():
    # Enable traio internal logging
    logging.basicConfig()
    Scope.set_debug(True)

    await Server().run()

# Beauty of python 3.7!
asyncio.run(main())
