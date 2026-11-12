"""The real gateway's memory store, in-process, for tests (keyword search only, no embedder)."""
import os
import sys
import tempfile

SERVICES = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "services")
sys.path.insert(0, SERVICES)
import memory_store  # noqa: E402

from kindred.memory import Memory  # noqa: E402


def memory_call(store, op, req):
    import kindred_gateway
    return kindred_gateway.memory_call(store, op, req)


class LocalStore:
    """Same interface as GatewayMemory, calling the store directly."""

    def __init__(self, embed=None, model=""):
        self.store = memory_store.Store(os.path.join(tempfile.mkdtemp(), "m.db"), embed=embed, model_name=model)

    strict = False  # like GatewayMemory: each world has its own companion

    def _call(self, op, body):
        if self.strict and body.get("world") and op in ("list", "search", "delete"):
            body = dict(body, strict=True)
        return memory_call(self.store, op, body)

    async def call(self, op, **body):
        if self.strict and body.get("world") and op in ("list", "search", "delete"):
            body = dict(body, strict=True)
        return memory_call(self.store, op, body)


def memory(clock=None, embed=None):
    import time
    return Memory(LocalStore(embed), clock=clock or time.time)
