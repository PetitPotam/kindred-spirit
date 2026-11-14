"""#199: CI and her Docker image install their Python packages from hash-locked files. Those locks must still give
what brain/requirements.txt (and the dev tools, and the Docker image's extras) ask for: change one without the other
and this fails, with the command that brings the lock up to date."""
import os
import re

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def wanted(path):
    """The requirements a requirements file asks for, following its -r includes."""
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-r"):
            out += wanted(os.path.join(os.path.dirname(path), line[2:].strip()))
        else:
            out.append(Requirement(line))
    return out


def locked(path):
    """{name: version} of a pip-compile lock, and whether every pin carries hashes."""
    text = open(path, encoding="utf-8").read()
    pins = {canonicalize_name(m[1]): m[2] for m in re.finditer(r"^([A-Za-z0-9_.\-]+)==([^\s\;]+)", text, re.M)}
    blocks = re.split(r"\n(?=[A-Za-z0-9_.\-]+==)", text.split("\n", 1)[1])
    unhashed = [b.split("==")[0] for b in blocks if "==" in b.split("\n")[0] and "--hash=sha256:" not in b]
    return pins, unhashed


@pytest.mark.parametrize("source, lock", [
    ("brain/requirements-ci.in", "brain/requirements-ci.txt"),
    ("docker/requirements.in", "docker/requirements.txt"),
])
def test_the_lock_gives_what_the_requirements_ask_for(source, lock):
    pins, unhashed = locked(os.path.join(ROOT, lock))
    assert not unhashed, f"{lock}: pins without hashes: {unhashed}"
    for req in wanted(os.path.join(ROOT, source)):
        name = canonicalize_name(req.name)
        assert name in pins, f"{lock} has no {req.name}: update it with the command at its top"
        assert req.specifier.contains(pins[name], prereleases=True), \
            f"{lock} has {req.name}=={pins[name]}, {source} asks for {req}: update it with the command at its top"


def test_ci_and_the_image_install_by_hash():
    for path in (".github/workflows/ci.yml", ".github/workflows/platforms.yml", ".github/workflows/release.yml",
                 "docker/Dockerfile"):
        text = open(os.path.join(ROOT, path), encoding="utf-8").read()
        for cmd in re.findall(r"pip install[^\n]*(?:\\\n[^\n]*)*", text):
            if " -r " in cmd:
                assert "--require-hashes" in cmd, f"{path}: {cmd.strip()}"
