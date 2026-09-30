"""UX round 5: the comparison board at smaller windows — the key strip drops whole items
(Esc last, never dropped), "▼ n more" moves off the cards when only one row fits, and the
preview image gives way so its buttons stay in view."""

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


def pump() -> None:
    for _ in range(3):
        QCoreApplication.processEvents()


def test_key_strip_drops_whole_items_and_keeps_esc_last(qapp):
    from aniref.ui.compare_board.board import HINT_KEYS, _KeyStrip

    strip = _KeyStrip(HINT_KEYS)
    strip.show()
    try:
        everything = tuple(k for k, _ in HINT_KEYS)
        strip.resize(2000, 30)
        pump()
        assert strip.shown() == everything and not strip.toolTip()
        seen = [everything]
        for width in range(1200, 0, -20):
            strip.resize(width, 30)
            pump()
            if strip.shown() != seen[-1]:
                seen.append(strip.shown())
        # open goes first, then move, then pick; Esc stays, at the end
        assert seen == [
            everything,
            ("cmp_move", "cmp_pick", "cmp_back"),
            ("cmp_pick", "cmp_back"),
            ("cmp_back",),
        ]
        assert strip.toolTip()  # the dropped keys are one hover away
    finally:
        strip.close()


def test_more_cue_leaves_the_cards_when_only_one_row_fits(qapp):
    from aniref.core.model.project import KeyPose
    from aniref.ui.compare_board.grid import BoardState, Grid, Row
    from aniref.ui.compare_board.grid_view import GridView
    from aniref.ui.context import AppContext

    rows = [
        Row(f"s{r}", f"video {r}", "", {"Contact": [KeyPose(f"s{r}", r, 0.0, f"p{r}", phase="Contact")]})
        for r in range(6)
    ]
    ctx = AppContext()  # painting reads it (a None ctx aborts mid-paint)
    view = GridView(ctx)
    view.show()
    view.set_content(Grid(["Contact"], rows), BoardState(), 150, False)
    try:
        view.resize(900, 700)  # room for a row and the strip: the cue sits over the cards
        pump()
        assert not view._more_in_labels(view._final_top())
        # one row plus the strip don't fit, one row is forced: the cue goes to the side
        tight = int(view.HEADER_H + view.row_h + view.final_h + view.MORE_H / 2)
        view.resize(900, tight)
        pump()
        final_top = view._final_top()
        assert len(view._visible_rows(final_top)) == 1
        assert view._more_in_labels(final_top)
        view.viewport().grab()  # paints that path without error
    finally:
        view.close()
        ctx.poses.shutdown()
        ctx.undo.blockSignals(True)


def test_preview_image_gives_way_before_the_buttons_scroll_off(qapp):
    from PySide6.QtWidgets import QScrollArea

    from aniref.core.model.project import KeyPose
    from aniref.ui.compare_board.preview import IMAGE_H, IMAGE_MIN_H, PosePreview
    from aniref.ui.context import AppContext

    ctx = AppContext()
    preview = PosePreview(ctx)
    preview.show()
    try:
        preview.set_pose(KeyPose("s", 3, 0.1, "pose", phase="Contact", tags=["t"], notes="note"), False)
        scroll = preview.findChild(QScrollArea)
        preview.resize(preview.width(), 900)
        pump()
        assert preview.image.height() == IMAGE_H
        preview.resize(preview.width(), 440)
        pump()
        assert IMAGE_MIN_H <= preview.image.height() < IMAGE_H
        bottom = preview.jump.mapTo(scroll.viewport(), preview.jump.rect().bottomLeft()).y()
        assert bottom <= scroll.viewport().height()
        preview.resize(preview.width(), 900)
        pump()
        assert preview.image.height() == IMAGE_H  # and grows back
    finally:
        preview.close()
        ctx.poses.shutdown()
        ctx.undo.blockSignals(True)
