"""Update check: ask GitHub once a day whether a newer release exists.

Only the release's version number is fetched — no project data, no machine
info, no identifiers; the request carries aniREF's own User-Agent and nothing
else. Users who don't want it turn it off in settings.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QMessageBox, QWidget

from ... import __version__, appdata
from ..i18n import tr
from . import prefs

log = logging.getLogger(__name__)

RELEASES_API = "https://api.github.com/repos/{owner}/{repo}/releases/latest"
INTERVAL = timedelta(days=1)
TIMEOUT_MS = 10_000

_REPO = re.compile(r"^https?://github\.com/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")


def repo_api_url(github_url: str = "") -> str | None:
    """Releases endpoint for the project's GitHub URL ('' while there is none)."""
    match = _REPO.match((github_url or appdata.GITHUB_URL or "").strip())
    return RELEASES_API.format(owner=match[1], repo=match[2]) if match else None


def version_key(text: str):
    """Sortable key for '1.2.3' / 'v1.2.3-beta.2'; None when it isn't a version."""
    core = str(text or "").strip().lstrip("vV").split("+", 1)[0]
    core, _, pre = core.partition("-")
    parts = core.split(".")
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        return None
    numbers = tuple(int(p) for p in parts) + (0,) * (3 - len(parts))
    if not pre:
        return numbers + (1, ())  # a release outranks its pre-releases
    ids = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    return numbers + (0, ids)


def is_newer(candidate: str, current: str) -> bool:
    a, b = version_key(candidate), version_key(current)
    return a is not None and b is not None and a > b


class UpdateChecker(QObject):
    """Asks GitHub for the latest release, at most once a day."""

    updateAvailable = Signal(str, str)  # version, release page
    upToDate = Signal()
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._net: QNetworkAccessManager | None = None
        self._reply: QNetworkReply | None = None

    def available(self) -> bool:
        """Whether this build knows a repository to ask."""
        return repo_api_url() is not None

    def due(self) -> bool:
        last = prefs.last_update_check()
        now = datetime.now()
        return last is None or last > now or now - last >= INTERVAL

    def check(self, force: bool = False) -> bool:
        """Start a check; returns False when there is nothing to do right now."""
        url = repo_api_url()
        if url is None or self._reply is not None:
            return False
        if not force and (not prefs.check_updates() or not self.due()):
            return False
        prefs.set_last_update_check(datetime.now())
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, f"aniREF/{__version__}")
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"Accept-Language", b"en")  # fixed, so the system locale stays here
        request.setTransferTimeout(TIMEOUT_MS)
        if self._net is None:
            self._net = QNetworkAccessManager(self)
            self._net.setAutoDeleteReplies(True)
        self._reply = self._net.get(request)
        self._reply.finished.connect(self._finished)
        return True

    def _finished(self) -> None:
        reply, self._reply = self._reply, None
        if reply is None:
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            log.info("update check failed: %s", reply.errorString())
            self.failed.emit(reply.errorString())
            return
        self.handle_release(bytes(reply.readAll()))

    def handle_release(self, payload: bytes) -> None:
        """Read one release payload (kept separate so it can be tested offline)."""
        try:
            data = json.loads(payload.decode("utf-8"))
            tag = str(data["tag_name"])
        except (UnicodeDecodeError, ValueError, KeyError, TypeError):
            log.info("update check: unexpected response")
            self.failed.emit("invalid response")
            return
        page = str(data.get("html_url") or "")
        if not page.startswith("https://github.com/"):
            page = appdata.GITHUB_URL
        if is_newer(tag, __version__):
            self.updateAvailable.emit(tag.lstrip("vV"), page)
        else:
            self.upToDate.emit()


def show_update_notice(parent: QWidget | None, version: str, url: str) -> bool:
    """Tell the user about a new version; True if they opened the download page."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(tr("set.updates.notice.title"))
    box.setText(tr("set.updates.notice.body", version=version, current=__version__))
    open_page = box.addButton(tr("set.updates.open_page"), QMessageBox.ButtonRole.AcceptRole)
    box.addButton(tr("btn.later"), QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(open_page)
    box.exec()
    if box.clickedButton() is open_page and url:
        QDesktopServices.openUrl(QUrl(url))
        return True
    return False
