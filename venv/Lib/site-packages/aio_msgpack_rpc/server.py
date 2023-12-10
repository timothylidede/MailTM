import asyncio
import msgpack
from .request import RequestType
import logging
from typing import Callable, Any


logger = logging.getLogger(__name__)


class Server(object):
    """RPC server"""

    def __init__(self,
                 handler: Any,
                 *,
                 packer: msgpack.Packer = None,
                 unpacker_factory: Callable[[], msgpack.Unpacker] = lambda: msgpack.Unpacker(raw=False),
                 loop: asyncio.AbstractEventLoop = None) -> None:
        self._handler = handler
        self._packer = packer if packer is not None else msgpack.Packer(use_bin_type=True)
        self._unpacked_factory = unpacker_factory
        self._loop = loop if loop is not None else asyncio.get_event_loop()

    async def __call__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """Coroutine to serve a client connection"""
        try:
            # create an unpacker for this connection
            unpacker = self._unpacked_factory()
            while True:
                data = await reader.read(n=4096)
                if not data:
                    raise ConnectionError("Client connection closed")
                unpacker.feed(data)
                for obj in unpacker:
                    # for every received object create a task to handle it
                    self._loop.create_task(self._handle_request(obj, writer))
        except ConnectionError:
            pass
        except Exception:
            logger.exception("Uncaught exception in client servicer")

    async def _handle_request(self, obj: Any, writer: asyncio.StreamWriter) -> None:
        try:
            if obj[0] == RequestType.REQUEST:
                _, msgid, name, params = obj
                try:
                    # handler can be a coroutine or a plain function
                    result = getattr(self._handler, name)(*params)
                    if asyncio.iscoroutine(result):
                        result = await result
                    response = (RequestType.RESPONSE, msgid, None, result)
                except Exception as e:
                    logger.info("Exception %r in call handler %r", e, name)
                    response = (RequestType.RESPONSE, msgid, str(e), None)
                writer.write(self._packer.pack(response))

            elif obj[0] == RequestType.NOTIFY:
                _, name, params = obj
                try:
                    result = getattr(self._handler, name)(*params)
                    if asyncio.iscoroutine(result):
                        result = await result
                except Exception:
                    logger.exception("Exception in notification handler %r", name)
            else:
                raise RuntimeError("unknown request type, {}".format(obj[0]))
        except Exception:
            logger.exception("Exception while handling rpc request: %r", obj)
