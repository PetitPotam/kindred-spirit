"""#180 (session 2026-11-14): the Setup's health check filled the dashboard with "opening handshake failed"."""
import logging
import sys

from kindred.server import QuietProbes


def _record(msg, exc):
    try:
        raise exc
    except Exception:
        info = sys.exc_info()
    return logging.LogRecord("websockets.server", logging.ERROR, __file__, 1, msg, None, info)


def test_a_probe_that_closes_at_once_is_quiet():
    logging.getLogger("websockets.server").setLevel(logging.INFO)
    probe = _record("opening handshake failed", EOFError("connection closed while reading HTTP request line"))
    assert QuietProbes().filter(probe) is False, "not shown at the usual INFO level"
    assert probe.levelname == "DEBUG" and probe.exc_info is None


def test_real_handshake_problems_still_show():
    bad = _record("opening handshake failed", ValueError("invalid Sec-WebSocket-Key"))
    assert QuietProbes().filter(bad) is True and bad.levelname == "ERROR"
    other = logging.LogRecord("websockets.server", logging.INFO, __file__, 1, "connection open", None, None)
    assert QuietProbes().filter(other) is True


def test_a_real_knock_and_leave_logs_no_error(caplog):
    import asyncio
    import socket
    from websockets.asyncio.server import serve

    async def handler(ws):
        await ws.close()
    logger = logging.getLogger("websockets.server")
    logger.addFilter(QuietProbes())

    async def run():
        async with serve(handler, "127.0.0.1", 0) as srv:
            port = srv.sockets[0].getsockname()[1]
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                pass  # (what the Setup's health check does)
            await asyncio.sleep(0.3)
    try:
        with caplog.at_level(logging.INFO, logger="websockets.server"):
            asyncio.run(run())
    finally:
        for f in [f for f in logger.filters if isinstance(f, QuietProbes)]:
            logger.removeFilter(f)
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR], [r.getMessage() for r in caplog.records]
