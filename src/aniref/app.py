"""Application entry point."""

from __future__ import annotations

import logging
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QEventLoop, QSettings
from PySide6.QtWidgets import QApplication

from . import appdata


def main() -> None:
    appdata.setup_logging()
    if sys.platform == "win32":
        # Own taskbar identity, so Windows shows aniREF's icon instead of Python's.
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("aniREF.aniREF")

    app = QApplication(sys.argv)
    app.setApplicationName(appdata.APP_NAME)
    app.setApplicationVersion(appdata.VERSION)

    if "--selftest" in sys.argv[1:]:
        sys.exit(_selftest(app))

    window = _create_window(app)
    window.show()
    # Crash leftovers first: asked while the file below is being opened, the
    # recovery prompts would stack and one recovered project replace the other.
    window.offer_untitled_recovery()
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        window.open_path(args[0])
    sys.exit(app.exec())


def _create_window(app: QApplication, startup_prompts: bool = True):
    from .ui import i18n, theme

    settings = appdata.settings()
    i18n.set_language(str(settings.value("language", i18n.system_language())))
    theme.apply(app)

    from .ui import icons
    from .ui.main_window import MainWindow

    app.setWindowIcon(icons.app_icon())
    return MainWindow(startup_prompts=startup_prompts)


# ------------------------------------------------------------------ selftest
#
# `aniREF.exe --selftest` is the release gate for a build (packaging/build.ps1 runs
# it on the frozen exe): it opens a generated video through the real import/player
# path and steps it, which fails if FFmpeg DLLs, Qt plugins or package modules are
# missing from the bundle. The window is never shown, so it also runs with
# QT_QPA_PLATFORM=offscreen. Exit code 0 = passed, 1 = failed (reason in the log).

_ST_FRAMES, _ST_FPS = 30, 30
_ST_BITS, _ST_CELL, _ST_HEIGHT = 5, 64, 64  # frame number as 5 black/white columns
_ST_TIMEOUT = 30.0

_st_log = logging.getLogger("aniref.selftest")


class _SelftestFailure(Exception):
    pass


def _selftest(app: QApplication) -> int:
    _st_log.info("selftest: start (frozen=%s, platform=%s)", appdata.is_frozen(), app.platformName())
    slot_errors: list[str] = []
    previous_hook = sys.excepthook

    def record(exc_type, exc, tb):
        # PySide reports exceptions raised inside slots here and carries on;
        # any of them means the app is broken even if the frames came out right.
        slot_errors.append(f"{exc_type.__name__}: {exc}")
        previous_hook(exc_type, exc, tb)

    sys.excepthook = record
    # Everything is caught: a frozen windowed build turns an uncaught exception
    # into a modal dialog, which would hang an unattended build forever.
    try:
        with tempfile.TemporaryDirectory(prefix="aniref-selftest-", ignore_cleanup_errors=True) as tmp:
            _selftest_run(app, Path(tmp))
        if slot_errors:
            raise _SelftestFailure(f"exception in a slot: {slot_errors[0]}")
    except Exception as e:
        _st_log.error("selftest: FAILED: %s", e, exc_info=not isinstance(e, _SelftestFailure))
        return 1
    finally:
        sys.excepthook = previous_hook
    _st_log.info("selftest: passed")
    return 0


def _selftest_run(app: QApplication, tmp: Path) -> None:
    video = tmp / "selftest.mp4"
    codec = _selftest_write_video(video)
    _st_log.info("selftest: wrote %d-frame %s test video", _ST_FRAMES, codec)

    # No recovery offer or update notice: a modal question would hang the run
    # (someone may run the selftest on an install with a crash leftover).
    window = _create_window(app, startup_prompts=False)
    player = window.player
    settings = window.settings
    last_dir = settings.value("last_video_dir")
    images: dict[int, object] = {}
    failures: list[str] = []
    player.imageReady.connect(lambda n, image: images.__setitem__(n, image))
    player.failed.connect(failures.append)
    try:
        window.import_videos([str(video)])
        _selftest_wait(app, lambda: player.is_open or failures, "the video to open")
        if failures:
            raise _SelftestFailure(f"player could not open the video: {failures[0]}")
        if player.frame_count != _ST_FRAMES:
            raise _SelftestFailure(f"expected {_ST_FRAMES} frames, player reports {player.frame_count}")
        _selftest_expect(app, window, images, 0, None)
        last = _ST_FRAMES - 1
        # Forward steps, a jump, a step back inside the cache, seeks across
        # keyframes both ways: the moves an animator makes on the first video.
        for action_id, frame in (
            ("step_fwd", 1),
            ("step_fwd", 2),
            ("step_fwd_10", 12),
            ("step_back", 11),
            ("last_frame", last),
            ("step_back", last - 1),
            ("first_frame", 0),
        ):
            _selftest_expect(app, window, images, frame, action_id)
        # Settings must be writable where appdata puts them (portable: data\ next
        # to the exe); build.ps1 checks the file landed in the right folder.
        settings.setValue("selftest/last_passed", f"{appdata.VERSION} {time.strftime('%Y-%m-%d %H:%M:%S')}")
        settings.sync()
        if settings.status() != QSettings.Status.NoError or not Path(settings.fileName()).is_file():
            raise _SelftestFailure(f"cannot write settings to {settings.fileName()} ({settings.status()})")
    finally:
        # Importing remembers the folder; don't leave a deleted temp dir in the
        # user's settings when someone runs the selftest on their own install.
        if last_dir is None:
            settings.remove("last_video_dir")
        else:
            settings.setValue("last_video_dir", last_dir)
        player.close()
        # Joins the decoder thread, which closes the file so the temp dir can go.
        window.server.shutdown()


def _selftest_write_video(path: Path) -> str:
    """Write a short H.264 clip whose frames show their own number as a barcode."""
    from fractions import Fraction

    import av
    import numpy as np

    width = _ST_BITS * _ST_CELL
    error: Exception | None = None
    # mpeg4 is only a fallback in case an FFmpeg build ships without x264;
    # decoding is what the app needs, encoding just feeds the test.
    for codec in ("libx264", "mpeg4"):
        try:
            with av.open(str(path), "w") as out:
                stream = out.add_stream(codec, rate=_ST_FPS)
                stream.width, stream.height, stream.pix_fmt = width, _ST_HEIGHT, "yuv420p"
                # Several keyframes and B-frames, like real footage: seeks and
                # reordering are exercised, not just straight decoding.
                stream.codec_context.gop_size = 10
                stream.codec_context.max_b_frames = 2
                for n in range(_ST_FRAMES):
                    img = np.zeros((_ST_HEIGHT, width, 3), np.uint8)
                    for b in range(_ST_BITS):
                        if (n >> b) & 1:
                            img[:, b * _ST_CELL : (b + 1) * _ST_CELL] = 255
                    frame = av.VideoFrame.from_ndarray(img, format="rgb24")
                    frame.pts = n
                    frame.time_base = Fraction(1, _ST_FPS)
                    out.mux(stream.encode(frame))
                out.mux(stream.encode(None))
            return codec
        except Exception as e:
            _st_log.warning("selftest: cannot encode with %s: %s", codec, e)
            error = e
    raise _SelftestFailure(f"cannot write a test video: {error}")


def _selftest_read_number(image) -> int:
    """Frame number from a decoded BGRA frame of the test video."""
    n = 0
    cy = _ST_HEIGHT // 2
    for b in range(_ST_BITS):
        cx = b * _ST_CELL + _ST_CELL // 2
        if image[cy - 8 : cy + 8, cx - 8 : cx + 8, :3].mean() > 128:
            n |= 1 << b
    return n


def _selftest_expect(app: QApplication, window, images: dict, frame: int, action_id: str | None) -> None:
    if action_id is not None:
        action = window.act[action_id]
        if not action.isEnabled():
            raise _SelftestFailure(f"action {action_id!r} is disabled with a video open")
        images.clear()
        action.trigger()
    what = f"frame {frame}" + (f" after {action_id!r}" if action_id else "")
    _selftest_wait(app, lambda: frame in images, what)
    image = images[frame]
    if window.player.frame != frame:
        raise _SelftestFailure(f"{what}: player is at frame {window.player.frame}")
    if image.shape[:2] != (_ST_HEIGHT, _ST_BITS * _ST_CELL):
        raise _SelftestFailure(f"{what}: decoded image has shape {image.shape}")
    shown = _selftest_read_number(image)
    if shown != frame:
        raise _SelftestFailure(f"{what}: decoded picture is frame {shown}")
    _st_log.info("selftest: %s ok", what)


def _selftest_wait(app: QApplication, done, what: str) -> None:
    deadline = time.monotonic() + _ST_TIMEOUT
    while not done():
        if time.monotonic() > deadline:
            raise _SelftestFailure(f"timed out after {_ST_TIMEOUT:g} s waiting for {what}")
        # Decoder results arrive as queued signals from the worker thread.
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 20)
        time.sleep(0.002)
