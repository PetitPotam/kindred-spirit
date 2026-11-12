"""The gateway answers this computer only: a web page on another site can't send it changes."""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("kindred_gateway", os.path.join(HERE, "..", "..", "services", "kindred_gateway.py"))
gw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gw)


class Fake:
    foreign = gw.Handler.foreign

    def __init__(self, **headers):
        self.headers = headers


def test_other_sites_and_foreign_hosts_are_refused():
    assert Fake(Host="127.0.0.1:11437").foreign() is False, "scripts and the brain (no Origin)"
    assert Fake(Host="127.0.0.1:11437", Origin="http://127.0.0.1:11440").foreign() is False, "the dashboard"
    assert Fake(Host="localhost:11437", Origin="http://localhost:3000").foreign() is False
    assert Fake(Host="127.0.0.1:11437", Origin="https://evil.example").foreign() is True, "a page elsewhere"
    assert Fake(Host="127.0.0.1:11437", Origin="http://127.0.0.1.evil.example").foreign() is True
    assert Fake(Host="evil.example:11437").foreign() is True, "DNS rebinding"
