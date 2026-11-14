"""Code scanning fixes (#163): voice text cleaning stays quick on hostile input, and proxied headers stay one line."""
import time

import pytest

import gateway_stub  # noqa: F401  (puts services/ on the path)
import kindred_gateway as gw


def test_gateway_speech_text_drops_tags_and_stays_quick_on_a_flood_of_brackets():
    said = gw.speech_text("[happy] Hello *there*! {wave}")
    assert said.startswith("Hello there") and not any(c in said for c in "[]{}*")
    started = time.time()
    out = gw.speech_text("[" * 200_000 + "hi")
    assert time.time() - started < 0.5 and len(out) <= 800


def test_kokoro_cleans_tags_and_stays_quick_on_a_flood_of_brackets():
    pytest.importorskip("onnxruntime")  # (the Kokoro server needs its voice engine to load)
    import kokoro_server as kokoro
    assert kokoro.clean_text("[happy] Hello *there*! [wave]") == "Hello there!"
    started = time.time()
    out = kokoro.clean_text("[" * 200_000 + "hi")
    assert time.time() - started < 0.5 and len(out) <= kokoro.MAX_CHARS


def test_gateway_headers_never_carry_a_line_break():
    assert gw.safe_header("audio/wav") == "audio/wav"
    assert "\n" not in gw.safe_header("text/plain\r\nSet-Cookie: x=1") and "\r" not in gw.safe_header("a\rb")
    assert gw.safe_header(None) == "application/octet-stream"
