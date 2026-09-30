"""Library empty states: the designed first-run block vs the plain no-match line."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from aniref.core.model import KeyPose, Project, Source
from aniref.ui.context import AppContext
from aniref.ui.i18n import tr
from aniref.ui.library.panel import LibraryPanel
from aniref.ui.shortcuts import key_text


@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    os.environ["ANIREF_DATA_DIR"] = str(tmp_path_factory.mktemp("appdata"))
    app = QApplication.instance() or QApplication([])
    from aniref.ui import i18n, theme

    i18n.set_language("ko")
    theme.apply(app)
    return app


def test_empty_project_shows_designed_state_with_keycap(qapp):
    ctx = AppContext()
    ctx.project = Project(name="t")
    panel = LibraryPanel(ctx)
    panel.refresh()
    assert panel.stack.currentWidget() is panel.empty
    assert panel.empty_title.text() == tr("library.empty.title")
    body = panel.empty_body.text()
    # the key is a rich-text cap and the translation's line break survives as <br>
    assert "<span" in body and f"&nbsp;{key_text('add_key_pose')}&nbsp;" in body and "<br>" in body


def test_filter_hiding_everything_shows_plain_no_match(qapp):
    ctx = AppContext()
    project = Project(name="t")
    src = Source(id="s1", path="a.mp4", label="a")
    project.sources.append(src)
    project.key_poses.append(KeyPose(id="k1", source_id="s1", frame=3, time=0.1, name="a F4"))
    ctx.project = project
    panel = LibraryPanel(ctx)
    panel.refresh()
    assert panel.stack.currentWidget() is panel.view
    panel.search.setText("zzz-nothing")
    assert panel.stack.currentWidget() is panel.no_match
    assert panel.no_match.text() == tr("library.no_match")
