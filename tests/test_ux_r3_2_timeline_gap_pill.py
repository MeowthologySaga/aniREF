"""Timeline gap pills stay clear of the loop in/out brackets."""

from aniref.ui.player.timeline import Timeline


def test_pill_centred_without_brackets():
    assert Timeline._gap_pill_left(0, 200, 30, ()) == 85


def test_pill_moves_off_bracket_inside_gap():
    left = Timeline._gap_pill_left(0, 200, 30, (100,))
    assert left is not None
    # clear of the bracket by 6px on whichever side it landed, still inside the gap
    assert left + 30 <= 94 or left >= 106
    assert 10 <= left and left + 30 <= 190


def test_pill_picks_side_with_room():
    # bracket near the right diamond: only the left stretch fits
    left = Timeline._gap_pill_left(0, 100, 30, (70,))
    assert left is not None and left + 30 <= 64 and left >= 10


def test_pill_skipped_when_no_side_fits():
    assert Timeline._gap_pill_left(0, 60, 30, (30,)) is None
    # narrow gap without brackets is skipped as before
    assert Timeline._gap_pill_left(0, 45, 30, ()) is None


def test_bracket_outside_gap_ignored():
    assert Timeline._gap_pill_left(0, 200, 30, (300, -50)) == 85


def test_bracket_xs_follow_loop():
    from PySide6.QtCore import QRectF
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    t = Timeline()
    t.resize(1014, 80)
    t.set_count(100)
    track = QRectF(14, 22, 986, 22)
    assert t._loop_bracket_xs(track) == ()
    t.set_loop(10, 19, True)
    left, right = t._loop_bracket_xs(track)
    assert left == t._x_of(10) and right == t._x_of(20)


def test_ruler_labels_clear_of_playhead_badge():
    # Focus-mode / playblast width: labels every 5 frames, so the label beside the
    # current frame used to peek out from under the badge ("3|31").
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    t = Timeline()
    t.resize(900, 80)
    t.set_count(70)
    ppf = t._px_per_frame()
    major, _minor = t._ruler_steps(ppf)
    assert major == 5
    rfm = QFontMetrics(t._ruler_font())
    pfm = QFontMetrics(t._playhead_font())
    for frame in (29, 30, 31, 58, 59, 60, 0, 69):  # next to / on major ticks, and both clamped ends
        t.set_frame(frame)
        head = t._playhead_rect(pfm)
        avoid = head.adjusted(-3, 0, 3, 0)
        labels = t._ruler_label_rects(ppf, rfm, avoid)
        assert labels, "the rest of the ruler still gets its numbers"
        for r, _text in labels:
            assert not r.intersects(avoid), (frame, _text)
        # only labels actually under the badge are dropped
        assert len(labels) >= len(t._ruler_label_rects(ppf, rfm, None)) - 2
