"""Export: contact sheet rendering, Maya markers, the Maya script and the dialog (headless)."""

import csv
import importlib.util
import io
import json
import os
import re
import tokenize
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"))

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication

from aniref.core.export import (
    CSV_FIELDS,
    Cell,
    SheetOptions,
    markers_csv,
    markers_json,
    pose_cells,
    render_contact_sheet,
    sequence_cells,
    sheet_grid,
    sheet_size,
    write_markers,
)
from aniref.core.export.contact_sheet import BASE_CELL, MARGIN, PALETTES
from aniref.core.model import KeyPose, Project, Sequence, SequenceItem, Source, Stroke, phase_color
from aniref.core.model.phases import CUSTOM_PHASE_COLOR

ROOT = Path(__file__).resolve().parent.parent
MAYA = ROOT / "maya"


@pytest.fixture(scope="session")
def qapp(tmp_path_factory):
    os.environ["ANIREF_DATA_DIR"] = str(tmp_path_factory.mktemp("appdata"))
    app = QApplication.instance() or QApplication([])
    from aniref.ui import i18n, theme

    i18n.set_language("ko")
    theme.apply(app)
    return app


def solid(color: str, w: int = 640, h: int = 360) -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    return img


def halves(left: str, right: str, w: int = 640, h: int = 360) -> QImage:
    img = solid(left, w, h)
    p = QPainter(img)
    p.fillRect(w // 2, 0, w - w // 2, h, QColor(right))
    p.end()
    return img


def pixel(img: QImage, x: float, y: float) -> QColor:
    return QColor(img.pixel(int(x), int(y)))


def cells(n: int, image: QImage | None = None) -> list[Cell]:
    return [Cell(image=image if image is not None else solid("#c83232"), number=i + 1, title="Contact") for i in range(n)]


# -- contact sheet: layout ---------------------------------------------------------


@pytest.mark.parametrize(
    "layout, columns, count, grid",
    [
        ("auto", 4, 6, (2, 3)),
        ("2x3", 4, 6, (2, 3)),
        ("2x3", 4, 4, (2, 3)),  # a fixed page keeps its size
        ("2x3", 4, 8, (3, 3)),  # more poses than slots: rows are added
        ("2x4", 4, 8, (2, 4)),
        ("3x3", 4, 5, (3, 3)),
        ("strip", 4, 7, (1, 7)),
        ("columns", 4, 10, (3, 4)),
        ("columns", 4, 2, (1, 2)),
    ],
)
def test_grid_for_each_layout(qapp, layout, columns, count, grid):
    options = SheetOptions(layout=layout, columns=columns)
    assert sheet_grid(cells(count), options) == grid


def test_auto_layout_reads_well(qapp):
    auto = SheetOptions()
    assert [sheet_grid(cells(n), auto)[1] for n in (1, 2, 3, 4, 6, 8, 12)] == [1, 2, 3, 2, 3, 4, 4]
    assert sheet_grid([], auto) == (0, 0)


def test_size_matches_render_and_scales_with_cell_width(qapp):
    six = cells(6)
    small = SheetOptions(cell_width=480, sheet_title="질풍참", subtitle="P · 30f")
    big = SheetOptions(cell_width=960, sheet_title="질풍참", subtitle="P · 30f")
    size = sheet_size(six, small)
    assert render_contact_sheet(six, small).size() == size
    doubled = sheet_size(six, big)
    assert abs(doubled.width() - 2 * size.width()) <= 2 and abs(doubled.height() - 2 * size.height()) <= 2
    # 3 columns of 480 plus margins and arrow gaps
    assert size.width() > 3 * BASE_CELL and size.width() > size.height()
    # a header adds height
    assert sheet_size(six, SheetOptions()).height() < size.height()


def test_fit_makes_an_exact_miniature(qapp):
    six = cells(6)
    image = render_contact_sheet(six, SheetOptions(), fit=QSize(400, 300))
    assert image.width() <= 400 and image.height() <= 300
    full = sheet_size(six, SheetOptions())
    assert abs(image.width() / image.height() - full.width() / full.height()) < 0.02


def test_strip_is_one_row(qapp):
    five = cells(5)
    options = SheetOptions(layout="strip")
    size = sheet_size(five, options)
    assert sheet_grid(five, options) == (1, 5)
    assert size.width() > 4 * size.height()


# -- contact sheet: painting -------------------------------------------------------

# First cell's image box without a header: x from MARGIN, y from MARGIN, 270 high for 16:9.
BOX_X, BOX_Y = MARGIN + 60, MARGIN + 150


def test_image_is_drawn_and_missing_image_gets_placeholder(qapp):
    options = SheetOptions()
    with_image = render_contact_sheet(cells(1), options)
    assert pixel(with_image, BOX_X, BOX_Y).name() == "#c83232"
    missing = render_contact_sheet([Cell(number=1, title="Idle")], options)
    assert pixel(missing, BOX_X, BOX_Y).name() == PALETTES["dark"].well


@pytest.mark.parametrize("background", ["dark", "light"])
def test_background(qapp, background):
    image = render_contact_sheet(cells(2), SheetOptions(background=background))
    assert pixel(image, 2, 2).name() == PALETTES[background].bg


def test_mirror_flips_the_image(qapp):
    frame = halves("#ff0000", "#0000ff")
    plain = render_contact_sheet([Cell(image=frame, number=1)], SheetOptions())
    mirrored = render_contact_sheet([Cell(image=frame, number=1, mirrored=True)], SheetOptions())
    assert pixel(plain, BOX_X, BOX_Y).name() == "#ff0000"
    assert pixel(mirrored, BOX_X, BOX_Y).name() == "#0000ff"


def test_drawings_follow_the_toggle(qapp):
    from aniref.ui.drawing.render import paint_strokes

    stroke = Stroke("line", "#00ff00", 0.03, [(0.0, 0.5), (1.0, 0.5)])
    cell = Cell(image=solid("#202020"), number=1, strokes=[stroke])
    center = (MARGIN + BASE_CELL / 2, MARGIN + 135)
    on = render_contact_sheet([cell], SheetOptions(drawings=True), paint_strokes)
    off = render_contact_sheet([cell], SheetOptions(drawings=False), paint_strokes)
    assert pixel(on, *center).green() > 200 and pixel(on, *center).red() < 80
    assert pixel(off, *center).name() == "#202020"


def test_every_option_renders(qapp):
    rich = [
        Cell(
            image=solid("#406080", 360, 640), number=i + 1, title="Anticipation" * (i + 1),
            color="#f28c28", source="MH_SnS_01", source_frame="F37", timing="6f · 0.20s",
            anim_frame=f"@{1 + 6 * i}", notes="몸이 낮아서 질풍참에 적합 " * 6, mirrored=bool(i % 2),
        )
        for i in range(4)
    ]
    for layout in ("auto", "2x3", "2x4", "3x3", "strip", "columns"):
        for background in ("dark", "light"):
            options = SheetOptions(layout=layout, background=background, notes=True, sheet_title="T", subtitle="S")
            image = render_contact_sheet(rich, options)
            assert image.size() == sheet_size(rich, options) and not image.isNull()
    bare = SheetOptions(number=False, title=False, source=False, timing=False, notes=False, arrows=False)
    assert render_contact_sheet(rich, bare).height() < render_contact_sheet(rich, SheetOptions()).height()


# -- building cells from a project ----------------------------------------------------


def make_project(frame_base: int = 1):
    project = Project("Sword_Shield_DashAttack")
    project.settings.frame_base = frame_base
    src = Source(path="refs/mh.mp4", label="MH_SnS_01")
    src.guides.append(Stroke("line", "#00ffcc", 0.004, [(0, 0.9), (1, 0.9)]))
    project.sources.append(src)
    a = KeyPose(src.id, 36, 0.6, "MH_SnS_01 / F37", phase="Anticipation", notes="낮은 자세", mirrored=True)
    b = KeyPose(src.id, 111, 1.85, "MH_SnS_01 / F112", phase="Contact")
    c = KeyPose(src.id, 200, 3.3, "MH_SnS_01 / F201")
    project.key_poses += [a, b, c]
    seq = Sequence(
        "질풍참",
        start_frame=101,
        items=[
            SequenceItem(a.id, 6),
            SequenceItem(b.id, 4, label="Dash", notes="타격"),
            SequenceItem(c.id, 2),
            SequenceItem("kp_gone", 3),
        ],
    )
    project.sequences.append(seq)
    return project, seq, (a, b, c)


def strokes_for(project):
    def fn(kp):
        src = project.source(kp.source_id)
        return list(src.guides) + list(src.drawings.get(kp.frame, []))

    return fn


def test_sequence_cells(qapp):
    project, seq, (a, b, c) = make_project()
    images = {a.id: solid("#123456")}
    result = sequence_cells(project, seq, lambda kp: images.get(kp.id), strokes_for(project))
    assert [x.number for x in result] == [1, 2, 3, 4]
    assert [x.anim_frame for x in result] == ["@101", "@107", "@111", "@113"]
    assert [x.timing for x in result] == ["6f · 0.20s", "4f · 0.13s", "2f · 0.07s", "3f · 0.10s"]
    assert [x.title for x in result[:3]] == ["Anticipation", "Dash", "MH_SnS_01 / F201"]
    assert [x.source_frame for x in result[:3]] == ["F37", "F112", "F201"]
    assert result[0].color == phase_color("Anticipation") and result[2].color == CUSTOM_PHASE_COLOR
    assert result[0].mirrored and result[0].image is images[a.id] and result[1].image is None
    assert result[0].strokes and result[0].notes == "낮은 자세" and result[1].notes == "타격"
    assert result[3].image is None and result[3].source == ""  # key pose deleted: placeholder

    zero, seq0, _ = make_project(frame_base=0)
    assert sequence_cells(zero, seq0, lambda kp: None, strokes_for(zero))[0].source_frame == "F36"


def test_pose_cells_skip_missing(qapp):
    project, _seq, (a, b, c) = make_project()
    result = pose_cells(project, [c.id, "nope", a.id], lambda kp: None, strokes_for(project))
    assert [x.number for x in result] == [1, 2]
    assert [x.source_frame for x in result] == ["F201", "F37"]
    assert all(x.timing == "" and x.anim_frame == "" for x in result)


# -- Maya markers -------------------------------------------------------------------


def test_markers_json_frames_follow_start_and_holds():
    project, seq, _ = make_project()
    data = markers_json(project, seq)
    assert data["format"] == "aniref.markers" and data["version"] == 1
    assert data["sequence"] == "질풍참" and data["project"] == "Sword_Shield_DashAttack"
    assert data["anim_fps"] == 30 and isinstance(data["anim_fps"], int)
    assert (data["start_frame"], data["end_frame"]) == (101, 115)
    m = data["markers"]
    assert [x["frame"] for x in m] == [101, 107, 111, 113]
    assert [x["end_frame"] for x in m] == [106, 110, 112, 115]
    assert [x["hold"] for x in m] == [6, 4, 2, 3]
    assert [x["name"] for x in m] == ["Anticipation", "Dash", "MH_SnS_01 / F201", "Pose 4"]
    assert [x["phase"] for x in m] == ["Anticipation", "Contact", "", ""]
    assert m[0]["color"] == phase_color("Anticipation") and m[2]["color"] == CUSTOM_PHASE_COLOR
    assert [x["source"] for x in m] == ["MH_SnS_01", "MH_SnS_01", "MH_SnS_01", ""]
    assert m[1]["notes"] == "타격" and m[0]["notes"] == "낮은 자세"


@pytest.mark.parametrize("frame_base, expected", [(1, [37, 112, 201, None]), (0, [36, 111, 200, None])])
def test_markers_source_frames_use_frame_base(frame_base, expected):
    project, seq, _ = make_project(frame_base)
    assert [x["source_frame"] for x in markers_json(project, seq)["markers"]] == expected


def test_markers_csv():
    project, seq, _ = make_project()
    rows = list(csv.DictReader(io.StringIO(markers_csv(project, seq))))
    assert list(rows[0]) == list(CSV_FIELDS)
    assert [r["frame"] for r in rows] == ["101", "107", "111", "113"]
    assert [r["end_frame"] for r in rows] == ["106", "110", "112", "115"]
    assert rows[1]["name"] == "Dash" and rows[0]["source_frame"] == "37" and rows[3]["source_frame"] == ""


def test_write_markers(tmp_path):
    project, seq, _ = make_project()
    json_path = write_markers(project, seq, tmp_path / "exports" / "질풍참_markers.json")
    assert json.loads(json_path.read_text(encoding="utf-8"))["markers"][1]["name"] == "Dash"
    csv_path = write_markers(project, seq, tmp_path / "m.csv")
    raw = csv_path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # BOM so Excel reads Korean
    assert "타격" in raw.decode("utf-8-sig")
    forced = write_markers(project, seq, tmp_path / "table.txt", fmt="csv")
    assert forced.read_text(encoding="utf-8-sig").startswith("frame,end_frame")


# -- Maya script (pure parts; Maya itself isn't available here) ----------------------


def maya_module():
    spec = importlib.util.spec_from_file_location("aniref_markers", MAYA / "aniref_markers.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_maya_script_reads_what_the_app_writes(tmp_path):
    mod = maya_module()
    project, seq, _ = make_project()
    path = write_markers(project, seq, tmp_path / "m.json")
    data = mod.load_markers(str(path))
    specs = mod.bookmark_specs(data)
    assert [(s["start"], s["stop"]) for s in specs] == [(101, 106), (107, 110), (111, 112), (113, 115)]
    assert [s["name"] for s in specs] == ["Anticipation", "Dash", "MH_SnS_01 / F201", "Pose 4"]
    assert specs[0]["source"] == "MH_SnS_01 F37" and specs[3]["source"] == ""
    r, g, b = specs[0]["color"]
    assert (round(r * 255), round(g * 255), round(b * 255)) == (0xF2, 0x8C, 0x28)
    assert mod.sequence_range(data, specs) == (101.0, 115.0)
    from aniref.core.model import DEFAULT_PHASES

    assert mod.PHASE_COLORS == DEFAULT_PHASES and mod.DEFAULT_COLOR == CUSTOM_PHASE_COLOR


def test_maya_script_helpers(tmp_path):
    mod = maya_module()
    assert mod.fps_from_unit("ntsc") == 30 and mod.fps_from_unit("film") == 24
    assert mod.fps_from_unit("29.97fps") == 29.97 and mod.fps_from_unit("weird") is None
    assert mod.hex_to_rgb("bad") == mod.hex_to_rgb(mod.DEFAULT_COLOR)
    wrong = tmp_path / "project.json"
    wrong.write_text('{"format": "aniref.project"}', encoding="utf-8")
    with pytest.raises(ValueError):
        mod.load_markers(str(wrong))
    with pytest.raises(RuntimeError):
        mod.import_markers(str(wrong))  # outside Maya


def test_maya_files_stay_compatible():
    source = (MAYA / "aniref_markers.py").read_text(encoding="utf-8")
    assert source.startswith("# -*- coding: utf-8 -*-")
    # Maya 2020 runs Python 2.7: no f-strings
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    fstrings = [t.string for t in tokens if t.type == tokenize.STRING and re.match(r"[rRbBuU]*[fF]", t.string)]
    assert not fstrings
    mel = (MAYA / "install_aniref.mel").read_bytes()
    assert all(byte < 128 for byte in mel)  # MEL is read in the system code page
    text = mel.decode("ascii")
    assert "aniref_markers.py" in text and "aniref_markers.import_markers()" in text
    assert text.count("{") == text.count("}") and text.count("(") == text.count(")")


# -- UI ------------------------------------------------------------------------------


@pytest.fixture
def ctx(qapp, tmp_path):
    from aniref.ui.context import AppContext

    project, seq, poses = make_project()
    context = AppContext()
    folder = tmp_path / "Sword_Shield_DashAttack"
    context.set_project(project, folder)
    for kp, color in zip(poses, ("#c83232", "#3264c8", "#32c864")):
        context.poses.add(kp, solid(color, 1920, 1080))
    project.ui.active_sequence_id = seq.id
    context.shown = []
    context.osd.connect(context.shown.append)
    yield context
    context.poses.shutdown()


def test_shortcuts_strings_and_help_are_registered(qapp):
    import aniref.ui.export  # noqa: F401
    from aniref.ui import i18n
    from aniref.ui.help.content import build_pages
    from aniref.ui.shortcuts import BY_ID, keys_for

    assert keys_for("export_contact_sheet") == ("Ctrl+E",)
    assert keys_for("export_markers") == ("Ctrl+Shift+E",)
    assert BY_ID["export_markers"].group == "project"
    for lang in ("ko", "en"):
        i18n.set_language(lang)
        try:
            page = next(p for p in build_pages() if p.id == "export")
            text = page.summary + " ".join(str(b.data) for b in page.blocks)
            assert set(re.findall(r"\{a:([a-z0-9_]+)\}", text)) <= set(BY_ID)
            assert i18n.tr("act.export_contact_sheet") != "act.export_contact_sheet"
        finally:
            i18n.set_language("ko")
    used = set(re.findall(r"\btr\(\s*\"([a-z0-9_.]+)\"", "".join(
        p.read_text(encoding="utf-8") for p in (ROOT / "src" / "aniref" / "ui" / "export").glob("*.py")
    )))
    assert used and used <= set(i18n.STRINGS)


def test_help_page_renders(qapp):
    import aniref.ui.export  # noqa: F401
    from aniref.ui.help.window import HelpWindow

    window = HelpWindow()
    window.show_page("export")
    assert window.nav.currentItem().data(Qt.ItemDataRole.UserRole) == "export"
    window.close()


def test_dialog_previews_and_saves(ctx):
    from aniref.core.export.contact_sheet import sheet_size as size_of
    from aniref.ui.export import ContactSheetDialog

    seq = ctx.project.sequences[0]
    dialog = ContactSheetDialog(ctx, sequence_id=seq.id)
    dialog.resize(1100, 720)
    dialog.show()
    QApplication.processEvents()
    dialog._refresh_preview()
    assert dialog.content.currentData() == ("seq", seq.id)
    assert len(dialog._cells) == 4 and dialog.title.text() == "질풍참"
    assert dialog.preview._image is not None and dialog.save_btn.isEnabled()
    assert "4" in dialog.info.text()
    # images are capped to the largest cell width
    assert dialog._cells[0].image.width() <= 1280

    expected = ctx.folder / "exports" / "질풍참.png"
    assert dialog.default_path() == expected
    dialog.layout_box.setCurrentIndex(dialog.layout_box.findData("strip"))
    saved = dialog.save()
    assert saved == expected and expected.exists()
    assert QImage(str(expected)).size() == size_of(dialog._cells, dialog.options())
    assert any("질풍참.png" in text for text in ctx.shown)
    assert dialog.folder_btn.isVisibleTo(dialog)

    dialog.copy_to_clipboard()
    assert QApplication.clipboard().image().size() == size_of(dialog._cells, dialog.options())
    dialog.close()

    again = ContactSheetDialog(ctx)
    assert again.layout_box.currentData() == "strip"  # options are remembered
    assert again.content.currentData() == ("seq", seq.id)  # the active sequence
    again.close()


def test_dialog_selection_and_empty_state(ctx, qapp):
    from aniref.core.model import Project
    from aniref.ui.context import AppContext
    from aniref.ui.export import ContactSheetDialog

    poses = ctx.project.key_poses
    picked = ContactSheetDialog(ctx, key_pose_ids=[poses[2].id, poses[0].id])
    assert picked.content.currentData() == ("selected", None)
    assert [c.source_frame for c in picked._cells] == ["F201", "F37"]
    assert picked.title.text() == ctx.project.name
    picked.title.setText("")
    assert picked.options().sheet_title == "" and picked.options().subtitle == ""
    picked.close()

    empty_ctx = AppContext()
    empty_ctx.set_project(Project("빈 프로젝트"), None)
    empty = ContactSheetDialog(empty_ctx)
    assert empty.stack.currentIndex() == 1
    assert not empty.save_btn.isEnabled() and not empty.copy_btn.isEnabled()
    assert empty.default_path() is None and empty.save() is None
    empty.close()
    empty_ctx.poses.shutdown()


def test_export_markers_from_the_ui(ctx, tmp_path, monkeypatch):
    from aniref.ui.export import dialogs, export_markers

    seq = ctx.project.sequences[0]
    written = export_markers(ctx, None, seq.id, path=tmp_path / "out.csv")
    assert written.suffix == ".csv" and written.read_text(encoding="utf-8-sig").startswith("frame,")
    assert any("4" in text and "out.csv" in text for text in ctx.shown)

    shown = []
    monkeypatch.setattr(dialogs.QMessageBox, "information", lambda *args: shown.append(args))
    ctx.project.sequences[0].items.clear()
    assert export_markers(ctx, None, path=tmp_path / "none.json") is None
    assert shown and not (tmp_path / "none.json").exists()
