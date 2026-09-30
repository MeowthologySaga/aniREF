"""UX round 3: the comparison board scrolls and paints whole rows only, inline key caps
never break inside a chord, and buttons keep the icon gap however their icon is set."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    os.environ["ANIREF_DATA_DIR"] = str(tmp_path_factory.mktemp("appdata"))
    app = QApplication.instance() or QApplication([])
    from aniref.ui import i18n, theme

    i18n.set_language("ko")
    theme.apply(app)
    return app


def _board(rows: int):
    from aniref.core.model.project import KeyPose
    from aniref.ui.compare_board.grid import BoardState, Grid, Row
    from aniref.ui.compare_board.grid_view import GridView

    grid_rows = [
        Row(f"s{r}", f"video {r}", "", {"Contact": [KeyPose(f"s{r}", r, 0.0, f"p{r}", phase="Contact")]})
        for r in range(rows)
    ]
    view = GridView(ctx=None)
    view.resize(900, 600)
    view.show()
    view.set_content(Grid(["Contact"], grid_rows), BoardState(), 150, False)
    QCoreApplication.processEvents()
    return view, grid_rows


def test_board_scrolls_by_whole_rows_and_never_cuts_one(qapp):
    view, rows = _board(6)
    try:
        step = view._row_step
        bar = view.verticalScrollBar()
        assert bar.maximum() > 0 and bar.maximum() % step == 0
        assert bar.singleStep() == step and bar.pageStep() % step == 0
        bar.setValue(step + 7)  # a drag lands between rows: it snaps to one
        assert bar.value() % step == 0
        final_top = view._final_top()
        shown = view._visible_rows(final_top)
        for r in shown:
            assert view._row_top(r) >= view.HEADER_H - 0.5
            assert view._row_top(r) + view.row_h <= final_top + 0.5
        # the "▼ n more" strip stays clear of the last row's caption
        assert final_top - (view._row_top(shown.stop - 1) + view.row_h) >= view.MORE_H
        # keyboard focus on a row below the fold brings it in whole
        view._ensure_visible(rows[-1].cells["Contact"][0].id)
        assert bar.value() == bar.maximum()
        assert view._visible_rows(view._final_top()).stop == len(rows)
    finally:
        view.close()


def test_keycap_never_breaks_inside_a_chord(qapp):
    from aniref.ui.widgets import keycap_html

    html = keycap_html("Ctrl + →")
    assert "Ctrl&nbsp;+&nbsp;→" in html
    assert " + " not in html


def test_icon_set_later_keeps_the_gap_and_clearing_it_recentres(qapp):
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QPushButton

    from aniref.ui import icons
    from aniref.ui.widgets import button

    b = button("영상 불러오기", "primary")
    assert b.text() == "영상 불러오기"
    assert QPushButton.text(b) == "영상 불러오기"  # Qt's own label: no icon yet, no leading space
    b.setIcon(icons.icon("film", "#ffffff"))
    assert QPushButton.text(b) == " 영상 불러오기"
    assert b.text() == "영상 불러오기"
    b.setText("다른 글")
    assert QPushButton.text(b) == " 다른 글"
    b.setIcon(QIcon())
    assert QPushButton.text(b) == "다른 글"
