"""Renewing Windows' trust in Magic Set Editor (app/mse_trust.py) and the session's MSE
status, with Windows faked: no real program is started."""
import subprocess

import pytest

from setdesigner.app import mse_trust
from setdesigner.app.session import SetSession
from setdesigner.render import CardRenderer


class FakeWindows:
    """Blocks MSE until a hidden launch of one of `accepted` (file names) has run."""

    def __init__(self, accepted=("magicseteditor.com",)):
        self.accepted = set(accepted)
        self.trusted = False
        self.launches = []                     # (file name, args)
        self.running_handles = set()
        self.ended = []

    def popen(self, *args, **kwargs):          # the app's own start of MSE
        if not self.trusted:
            error = OSError(22, "An Application Control policy has blocked this file")
            error.winerror = 4551
            raise error
        raise OSError(2, "not a real MSE")      # trusted: past the block (then MSE "fails")

    def start(self, exe, args):
        self.launches.append((exe.name, args))
        if exe.name in self.accepted:
            self.trusted = True
        handle = len(self.launches)
        self.running_handles.add(handle)
        return handle

    def running(self, handle):
        return False                           # --version exits at once

    def end(self, handle):
        self.ended.append(handle)
        self.running_handles.discard(handle)


@pytest.fixture
def windows(monkeypatch):
    fake = FakeWindows()
    monkeypatch.setattr(subprocess, "Popen", fake.popen)
    return fake


@pytest.fixture
def session(tmp_path):
    folder = tmp_path / "mse"
    folder.mkdir()
    for name in ("magicseteditor.com", "magicseteditor.exe"):
        (folder / name).write_bytes(b"")
    s = SetSession.create(tmp_path / "set", "My Set", "mys", "m15", thumbnail_dir=tmp_path / "thumbs",
                          renderer_factory=lambda p: CardRenderer(p, mse_exe=folder / "magicseteditor.com"))
    yield s
    s.close()


def test_status_says_blocked_and_retry_tries_again(session, windows) -> None:
    kind, message = session.mse_status()
    assert kind == "blocked" and "Windows blocked Magic Set Editor" in message
    assert session.mse_blocked
    windows.trusted = True
    assert session.retry_mse()[0] == "failed"            # past Windows; our fake MSE then fails


def test_renew_tries_each_route_and_ends_what_it_started(session, windows) -> None:
    session.mse_status()
    route = mse_trust.renew(session, windows)
    # the fake MSE "fails" after the block, so retry_mse isn't "ok": every route is tried
    assert route == ""
    assert windows.launches == [("magicseteditor.com", "--version"), ("magicseteditor.exe", "--version")]
    assert sorted(windows.ended) == [1, 2] and not windows.running_handles   # all ended


def test_renew_reports_the_route_that_worked(session, windows, monkeypatch) -> None:
    session.mse_status()
    monkeypatch.setattr(SetSession, "retry_mse", lambda self: ("ok", "") if windows.trusted else ("blocked", ""))
    windows.accepted = {"magicseteditor.exe"}
    assert mse_trust.renew(session, windows) == "hidden-gui"
    assert windows.launches[-1] == ("magicseteditor.exe", "--version")
    assert not windows.running_handles


def test_a_renderer_without_mse_is_off(tmp_path) -> None:
    s = SetSession.create(tmp_path / "set", "My Set", "mys", "m15",
                          renderer_factory=lambda p: CardRenderer(p, use_mse=False))
    try:
        assert s.mse_status() == ("off", "") and not s.mse_blocked
        assert mse_trust.renew(s, FakeWindows()) == ""
    finally:
        s.close()
