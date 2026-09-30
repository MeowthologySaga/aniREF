"""UX round 6: the sequence header's export buttons name their keys, follow a rebind
(also once they have dropped to icons) and card / playblast tooltips read keys from
the key tables instead of typing them."""

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
    import aniref.ui.main_window  # noqa: F401  (feature modules register their shortcuts)

    return app


@pytest.fixture
def board(qapp):
    from aniref.ui import shortcuts
    from aniref.ui.context import AppContext
    from aniref.ui.sequence import SequenceBoard

    b = SequenceBoard(AppContext())
    b.resize(1200, 240)
    b.show()
    QCoreApplication.processEvents()
    yield b
    shortcuts.set_overrides({})
    b.close()


def test_export_buttons_name_their_keys_and_follow_a_rebind(board):
    from aniref.ui import shortcuts

    assert "Ctrl + E" in board.contact_btn.toolTip()
    assert "Ctrl + Shift + E" in board.markers_btn.toolTip()
    assert "(P)" in board.flipbook_btn.toolTip()

    shortcuts.set_overrides({"export_contact_sheet": ("Ctrl+K",), "flipbook": ("F9",), "export_markers": ()})
    board.refresh_keys()
    assert "Ctrl + K" in board.contact_btn.toolTip() and "Ctrl + E" not in board.contact_btn.toolTip()
    assert "F9" in board.flipbook_btn.toolTip()
    assert "Ctrl" not in board.markers_btn.toolTip()  # no key bound: no empty "()" either

    # icon-only: the name leads the tooltip, and a rebind now still reaches it
    board.resize(620, 240)
    QCoreApplication.processEvents()
    assert board.contact_btn.text() == ""
    assert board.contact_btn.toolTip().startswith("Contact Sheet\n")
    shortcuts.set_overrides({"export_contact_sheet": ("Ctrl+J",)})
    board.refresh_keys()
    tip = board.contact_btn.toolTip()
    assert tip.startswith("Contact Sheet\n") and "Ctrl + J" in tip
    assert board.contact_btn.text() == ""

    board.resize(1200, 240)
    QCoreApplication.processEvents()
    assert board.contact_btn.text() and not board.contact_btn.toolTip().startswith("Contact Sheet\n")


def test_card_and_playblast_tips_read_the_key_tables(qapp):
    from aniref.ui.i18n import tr
    from aniref.ui.playblast import keys
    from aniref.ui.playblast.window import _key_pair
    from aniref.ui.shortcuts import board_key_text

    assert "F2" in tr("seq.card.help", key=board_key_text("seq_rename"))
    offset = tr("pb.tip.offset", keys=_key_pair("offset_back", "offset_fwd"))
    assert keys.key_text("offset_back") in offset and keys.key_text("offset_fwd") in offset
    assert "{keys}" not in tr("pb.tip.opacity", keys=_key_pair("opacity_down", "opacity_up"))
