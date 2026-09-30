"""UX round 2: refreshing the welcome page's recent list must not leave the old
entries behind as visible, unmanaged children painting over the card."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtWidgets import QApplication, QLabel


@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    os.environ["ANIREF_DATA_DIR"] = str(tmp_path_factory.mktemp("appdata"))
    app = QApplication.instance() or QApplication([])
    from aniref.ui import i18n, theme

    i18n.set_language("ko")
    theme.apply(app)
    return app


def test_set_recent_twice_leaves_one_placeholder(qapp):
    from aniref.ui.i18n import tr
    from aniref.ui.welcome import WelcomePage

    page = WelcomePage()
    page.resize(1200, 800)
    page.show()
    # No event loop turn in between: deleteLater has not run yet, so an entry
    # that was only deleteLater'd is still a child of the page and can paint.
    page.set_recent([])
    page.set_recent([])
    empty = tr("welcome.recent_empty")
    stale = [lb for lb in page.findChildren(QLabel) if lb.text() == empty]
    assert len(stale) == 1
    page.close()
