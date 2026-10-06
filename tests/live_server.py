import socket
from collections.abc import Generator
from contextlib import contextmanager
from threading import Event, Thread
from typing import override

import uvicorn
from fastapi import FastAPI


class ReadyServer(uvicorn.Server):
    def __init__(self, config: uvicorn.Config, ready: Event) -> None:
        super().__init__(config)
        self.ready: Event = ready

    @override
    async def startup(self, sockets: list[socket.socket] | None = None) -> None:
        await super().startup(sockets)
        self.ready.set()


@contextmanager
def live_server(app: FastAPI) -> Generator[str, None, None]:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        ready = Event()
        server = ReadyServer(uvicorn.Config(app, log_level="critical"), ready)
        thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        assert ready.wait(10)
        try:
            yield f"http://127.0.0.1:{listener.getsockname()[1]}"
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive()
