"""Korean / English UI text.

Every user-visible string goes through `tr(key)`. The language is chosen once
at startup (changing it asks for a restart). Phase names such as Anticipation
are animation vocabulary and stay English in both languages.
"""

from __future__ import annotations

from PySide6.QtCore import QLocale

LANGUAGES = ("ko", "en")
_lang = "ko"


def set_language(lang: str) -> None:
    global _lang
    _lang = lang if lang in LANGUAGES else "en"


def language() -> str:
    return _lang


def system_language() -> str:
    return "ko" if QLocale.system().language() == QLocale.Language.Korean else "en"


def tr(key: str, /, **fmt) -> str:
    ko, en = STRINGS.get(key, (key, key))
    text = ko if _lang == "ko" else en
    return text.format(**fmt) if fmt else text


def pick(ko: str, en: str) -> str:
    """Inline bilingual text (used by long-form help content)."""
    return ko if _lang == "ko" else en


def register(strings: dict[str, tuple[str, str]]) -> None:
    """Feature modules bring their own strings: call at import with {key: (ko, en)}."""
    clash = {k for k in strings if k in STRINGS and STRINGS[k] != strings[k]}
    if clash:
        raise KeyError(f"i18n keys already defined differently: {sorted(clash)}")
    STRINGS.update(strings)


# key: (한국어, English)
STRINGS: dict[str, tuple[str, str]] = {
    # -- general -------------------------------------------------------------
    "app.tagline": ("레퍼런스에서 키포즈를 뽑아 새 모션을 설계하세요", "Pull key poses from references and design new motion"),
    "project.untitled": ("제목 없음", "Untitled"),
    "lang.ko": ("한국어", "한국어"),
    "lang.en": ("English", "English"),
    # -- menus ---------------------------------------------------------------
    "menu.file": ("파일", "File"),
    "menu.playback": ("재생", "Playback"),
    "menu.view": ("보기", "View"),
    "menu.help": ("도움말", "Help"),
    "menu.recent": ("최근 프로젝트", "Recent Projects"),
    "menu.recent_empty": ("(없음)", "(none)"),
    "menu.speed": ("재생 속도", "Playback Speed"),
    "menu.custom_step": ("이동 간격", "Custom Step"),
    "menu.language": ("언어 / Language", "Language / 언어"),
    "menu.frame_base": ("프레임 번호 시작", "Frame Numbering"),
    "menu.anim_fps": ("애니 fps", "Anim fps"),
    "anim_fps.n": ("{fps:g}fps", "{fps:g}fps"),
    "frame_base.one": ("1부터 (Maya 타임라인과 같게)", "Start at 1 (like Maya)"),
    "frame_base.zero": ("0부터", "Start at 0"),
    "step.n": ("{n}프레임", "{n} frames"),
    # -- shortcut groups -----------------------------------------------------
    "grp.playback": ("재생", "Playback"),
    "grp.navigate": ("프레임 이동", "Frame Navigation"),
    "grp.loop": ("루프", "Loop"),
    "grp.view": ("보기", "View"),
    "grp.project": ("프로젝트", "Project"),
    "grp.help": ("도움말", "Help"),
    "grp.keypose": ("키포즈", "Key Poses"),
    "grp.draw": ("드로잉", "Drawing"),
    "grp.edit": ("편집", "Edit"),
    "menu.edit": ("편집", "Edit"),
    "menu.draw": ("드로잉", "Draw"),
    "menu.keypose": ("키포즈", "Key Pose"),
    # -- actions -------------------------------------------------------------
    "act.play_pause": ("재생 / 정지", "Play / Pause"),
    # 이전 / 다음, not 뒤로 / 앞으로: Onion Skin and its OSD use 앞 for "before",
    # so 앞으로 for → would give 앞 two opposite meanings on the same screen.
    "act.step_back": ("이전 프레임", "Back 1 frame"),
    "act.step_fwd": ("다음 프레임", "Forward 1 frame"),
    "act.step_back_5": ("5프레임 이전", "Back 5 frames"),
    "act.step_fwd_5": ("5프레임 다음", "Forward 5 frames"),
    "act.step_back_10": ("10프레임 이전", "Back 10 frames"),
    "act.step_fwd_10": ("10프레임 다음", "Forward 10 frames"),
    "act.step_back_custom": ("이동 간격만큼 이전", "Back by custom step"),
    "act.step_fwd_custom": ("이동 간격만큼 다음", "Forward by custom step"),
    "act.first_frame": ("처음으로 (루프 켜짐: 루프 시작)", "To start (loop on: loop in)"),
    "act.last_frame": ("끝으로 (루프 켜짐: 루프 끝)", "To end (loop on: loop out)"),
    "act.go_to_frame": ("프레임 번호 입력해서 이동", "Go to frame number"),
    "act.speed_down": ("느리게", "Slower"),
    "act.speed_up": ("빠르게", "Faster"),
    "act.loop_in": ("루프 시작 지정", "Set loop in"),
    "act.loop_out": ("루프 끝 지정", "Set loop out"),
    "act.loop_toggle": ("루프 켜기 / 끄기", "Loop on / off"),
    "act.loop_clear": ("루프 구간 지우기", "Clear loop range"),
    "act.mirror": ("Mirror (좌우 반전)", "Mirror"),
    "act.fit_view": ("화면 맞춤", "Fit to view"),
    "act.focus_mode": ("Focus 모드 (뷰어만 보기)", "Focus mode (viewer only)"),
    "act.always_on_top": ("항상 위", "Always on top"),
    "act.next_source": ("다음 영상 탭", "Next video tab"),
    "act.prev_source": ("이전 영상 탭", "Previous video tab"),
    "act.close_source": ("영상 탭 닫기", "Close video tab"),
    "act.new_project": ("새 프로젝트", "New project"),
    "act.open_project": ("프로젝트 열기…", "Open project…"),
    "act.save_project": ("저장", "Save"),
    "act.save_as": ("다른 이름으로 저장…", "Save as…"),
    "act.import_video": ("영상 불러오기…", "Import video…"),
    "act.relink": ("영상 다시 연결…", "Relink video…"),
    "act.quit": ("종료", "Quit"),
    "act.shortcut_sheet": ("단축키 한눈에 보기", "Keyboard shortcuts"),
    "act.help": ("사용 설명서", "User guide"),
    "act.guide": ("3분 시작 가이드", "3-minute quick start"),
    "act.open_log_folder": ("로그 폴더 열기", "Open log folder"),
    "act.report": ("문제 신고 (GitHub)", "Report a problem (GitHub)"),
    "act.about": ("aniREF 정보", "About aniREF"),
    "act.add_key_pose": ("키포즈 추가", "Add key pose"),
    "act.add_key_pose_phase": ("Phase 골라서 키포즈 추가", "Add key pose with a phase"),
    "act.prev_key_pose": ("이전 키포즈로", "Previous key pose"),
    "act.next_key_pose": ("다음 키포즈로", "Next key pose"),
    "act.delete_key_pose": ("선택한 키포즈 삭제", "Delete selected key pose"),
    "act.draw_toggle": ("그리기 도구 ↔ 포인터", "Draw tool ↔ pointer"),
    "act.tool_pointer": ("포인터 (그리기 끔)", "Pointer (no drawing)"),
    "act.tool_pen": ("펜", "Pen"),
    "act.tool_line": ("직선", "Line"),
    "act.tool_arrow": ("화살표", "Arrow"),
    "act.tool_circle": ("원", "Circle"),
    "act.tool_eraser": ("지우개", "Eraser"),
    "act.guide_layer": ("모든 프레임에 그리기", "Draw on every frame"),
    "act.drawings_visible": ("드로잉 보이기 / 숨기기", "Show / hide drawings"),
    "act.clear_drawings": ("이 프레임 드로잉 모두 지우기", "Clear this frame's drawings"),
    "act.undo": ("되돌리기", "Undo"),
    "act.redo": ("다시 실행", "Redo"),
    "act.tool_trail": ("궤적 찍기 (Motion Trail)", "Motion trail"),
    "act.add_section": ("타이밍 구간 만들기", "Add timing section"),
    "tool.trail": ("궤적", "Trail"),
    "menu.trail": ("궤적 (Motion Trail)", "Motion Trail"),
    "trail.new": ("새 궤적", "New trail"),
    "trail.custom": ("직접 이름 입력…", "Custom name…"),
    "trail.custom_title": ("새 궤적", "New trail"),
    "trail.custom_body": ("무엇을 따라갈까요?  (예: 창끝, 왼손)", "What are you following?  (e.g. spear tip, left hand)"),
    "trail.toggle_visible": ("현재 궤적 보이기", "Show current trail"),
    "trail.clear_point": ("이 프레임의 점 지우기", "Remove this frame's point"),
    "trail.delete": ("현재 궤적 삭제", "Delete current trail"),
    "trail.advance": ("점을 찍으면 다음 프레임으로", "Advance a frame after each point"),
    "trail.preset.sword_tip": ("검끝", "Sword tip"),
    "trail.preset.sword_hand": ("검 쥔 손", "Sword hand"),
    "trail.preset.shield": ("방패 중심", "Shield center"),
    "trail.preset.head": ("머리", "Head"),
    "trail.preset.pelvis": ("골반", "Pelvis"),
    "trail.preset.left_foot": ("왼발", "Left foot"),
    "trail.preset.right_foot": ("오른발", "Right foot"),
    "trail.info.head": ("● {name}  ·  점 {n}개  ({first} – {last})", "● {name}  ·  {n} points  ({first} – {last})"),
    "trail.info.empty": ("● {name}  ·  클릭해서 이 프레임에 점을 찍으세요  ·  Shift+클릭 지우기", "● {name}  ·  click to place this frame's point  ·  Shift+click removes"),
    "trail.info.move": (
        # dx / dy arrive as "오른쪽 62%" / "위 25%": direction words, not a signed number (+y is
        # down) and not an arrow glyph, which glued to the digits read "↑25%" as "125%".
        # Every % is of the source video's height (not the window's). The unit is named right
        # after the first % so that bare number has a label; a trailing "(영상 높이 대비)" read as
        # if it covered only the vertical value.
        "이동 {path:.0f}px (영상 높이의 {path_rel:.0%})  ·  가로 {dx}  ·  세로 {dy}",
        "Travel {path:.0f}px ({path_rel:.0%} of frame height)  ·  horizontal {dx}  ·  vertical {dy}",
    ),
    "trail.dir.up": ("위", "up"),
    "trail.dir.down": ("아래", "down"),
    "trail.dir.left": ("왼쪽", "left"),
    "trail.dir.right": ("오른쪽", "right"),
    "trail.info.speed": (
        "최고 속도 {speed:.0f}px/f ({frame})  ·  시작점에서 최대 거리 {reach:.0%}",
        "Peak speed {speed:.0f}px/f ({frame})  ·  max reach {reach:.0%} from start",
    ),
    "osd.trail_point": ("● {name}  {frame}", "● {name}  {frame}"),
    "osd.trail_new": ("새 궤적: {name}", "New trail: {name}"),
    "osd.section_added": ("구간 {label}  {a} – {b}  ({n}f)", "Section {label}  {a} – {b}  ({n}f)"),
    "section.menu_title": ("이 구간의 Phase", "Phase of this range"),
    "section.delete": ("구간 삭제", "Delete section"),
    # '@N' is reserved for a Maya timeline position (sequence cards); a rate is written '30fps'.
    "section.tip": ("{label}  {a} – {b}  ·  {n}f · {sec:.3f}s  ·  애니 {anim:.1f}f ({anim_fps:g}fps)", "{label}  {a} – {b}  ·  {n}f · {sec:.3f}s  ·  anim {anim:.1f}f ({anim_fps:g}fps)"),
    "cmd.track_point": ("궤적 점", "trail point"),
    "cmd.add_track": ("궤적 추가", "add trail"),
    "cmd.delete_track": ("궤적 삭제", "delete trail"),
    "cmd.add_section": ("구간 추가", "add section"),
    "cmd.edit_section": ("구간 편집", "edit section"),
    "cmd.delete_section": ("구간 삭제", "delete section"),
    "inspector.lead_foot": ("앞발", "Lead foot"),
    "inspector.weight": ("체중발", "Weight on"),
    "inspector.left": ("왼발", "L"),
    "inspector.right": ("오른발", "R"),
    "inspector.both": ("양발", "Both"),
    # Shown on the meta line, so short: source frames first, then what they become on the
    # Maya timeline (DESIGN §1). Rates are written '60fps'; '@N' means a timeline position.
    "inspector.interval": ("이전 +{n}f ({src_fps:g}fps) = 애니 {anim}f ({anim_fps:g}fps)", "prev +{n}f ({src_fps:g}fps) = anim {anim}f ({anim_fps:g}fps)"),
    # Same fps on both sides: the conversion would only repeat the number.
    "inspector.interval_same": ("이전 +{n}f", "prev +{n}f"),
    "inspector.interval_tip": ("이전 키포즈에서 {n}프레임 · {sec:.3f}초", "{n} frames after the previous key pose · {sec:.3f}s"),
    "act.onion_skin": ("Onion Skin (앞뒤 프레임 겹쳐 보기)", "Onion skin (ghost nearby frames)"),
    "act.silhouette": ("실루엣 보기 (원본 → 고대비 → 실루엣 → 반전)", "Silhouette view (original → contrast → silhouette → inverted)"),
    "tool.onion": ("Onion", "Onion"),
    "tool.silhouette": ("실루엣", "Silhouette"),
    "menu.onion": ("Onion Skin 설정", "Onion Skin Settings"),
    "onion.both": ("앞뒤 {n}프레임", "{n} before & after"),
    "onion.before": ("앞 {n}프레임만", "{n} before only"),
    "onion.after": ("뒤 {n}프레임만", "{n} after only"),
    "onion.opacity": ("진하기 {pct}%", "Opacity {pct}%"),
    "osd.onion_on": ("Onion Skin  ·  앞 {b} (따뜻한 색) · 뒤 {a} (차가운 색)", "Onion skin  ·  {b} before (warm) · {a} after (cool)"),
    "osd.onion_off": ("Onion Skin 꺼짐", "Onion skin off"),
    "osd.filter.none": ("원본 보기", "Original"),
    "osd.filter.contrast": ("고대비 보기  ·  {key} 키로 다음", "High contrast  ·  {key} for next"),
    "osd.filter.silhouette": ("실루엣 보기  ·  {key} 키로 다음", "Silhouette  ·  {key} for next"),
    "osd.filter.silhouette_inv": ("실루엣 (반전)  ·  {key} 키로 원본", "Silhouette (inverted)  ·  {key} for original"),
    # the rail button's label follows the active view filter (short: the rail button is 56px)
    "tool.filter.contrast": ("고대비", "Contrast"),
    "tool.filter.silhouette": ("실루엣", "Silhouette"),
    "tool.filter.silhouette_inv": ("반전", "Inverted"),
    # pills in the viewer's corner: view state that stays on after the OSD fades
    "badge.mirror": ("Mirror", "Mirror"),
    "badge.onion": ("Onion", "Onion"),
    "badge.drawings_off": ("드로잉 숨김", "Drawings hidden"),
    "badge.speed": ("속도 {speed}", "Speed {speed}"),
    "badge.filter.contrast": ("고대비", "High contrast"),
    "badge.filter.silhouette": ("실루엣", "Silhouette"),
    "badge.filter.silhouette_inv": ("실루엣 반전", "Inverted silhouette"),
    # -- drawing -------------------------------------------------------------
    "tool.pointer": ("포인터", "Pointer"),
    "tool.pen": ("펜", "Pen"),
    "tool.line": ("직선", "Line"),
    "tool.arrow": ("화살표", "Arrow"),
    "tool.circle": ("원", "Circle"),
    "tool.eraser": ("지우개", "Eraser"),
    "tool.guide": ("매 프레임", "All frames"),
    "tool.visible": ("보이기", "Show"),
    "tool.clear": ("프레임 지움", "Clear frame"),
    "draw.color_tip": ("선 색", "Stroke color"),
    "draw.width_tip": ("선 두께: {name}", "Stroke width: {name}"),
    "width.thin": ("얇게", "Thin"),
    "width.medium": ("보통", "Medium"),
    "width.thick": ("굵게", "Thick"),
    "osd.tool": ("도구: {tool}", "Tool: {tool}"),
    "osd.layer_frame": ("그리기 대상: 이 프레임만", "Drawing on: this frame only"),
    "osd.layer_guide": ("그리기 대상: 모든 프레임", "Drawing on: every frame"),
    "osd.drawings_on": ("드로잉 표시됨", "Drawings shown"),
    "osd.drawings_off": ("드로잉 숨김  ·  {key}", "Drawings hidden  ·  {key}"),
    "osd.cleared": ("이 프레임의 드로잉을 지웠습니다", "Frame drawings cleared"),
    "osd.undo_hint": ("{key} 키로 되돌리기", "{key} to undo"),
    "osd.undo": ("되돌리기: {what}", "Undo: {what}"),
    "osd.redo": ("다시 실행: {what}", "Redo: {what}"),
    "cmd.stroke": ("드로잉", "drawing"),
    "cmd.erase": ("지우기", "erase"),
    "cmd.clear": ("프레임 드로잉 지우기", "clear frame drawings"),
    "cmd.add_pose": ("키포즈 추가", "add key pose"),
    "cmd.delete_pose": ("키포즈 삭제", "delete key pose"),
    "cmd.remove_source": ("영상 빼기", "remove video"),
    "cmd.edit_pose": ("키포즈 편집", "edit key pose"),
    "cmd.add_phase": ("Phase 추가", "add phase"),
    # -- key poses -----------------------------------------------------------
    "osd.pose_added": ("◆  키포즈 추가  {frame}", "◆  Key pose added  {frame}"),
    "osd.pose_exists": ("이미 키포즈가 있는 프레임입니다", "This frame already has a key pose"),
    "osd.pose_deleted": ("키포즈 삭제", "Key pose deleted"),
    "osd.pose_cancelled": (
        "키포즈를 추가하지 않았습니다 — 그 프레임이 뜨기 전에 이동했어요",
        "Key pose not added — moved on before that frame showed",
    ),
    "osd.no_pose_before": ("이 앞에는 키포즈가 없습니다", "No key pose before this frame"),
    "osd.no_pose_after": ("이 뒤에는 키포즈가 없습니다", "No key pose after this frame"),
    "dock.library": ("키포즈 라이브러리", "Key Pose Library"),
    "library.search": ("이름 · 태그 · 메모 검색", "Search name, tags, notes"),
    "library.all": ("전체", "All"),
    "library.all_sources": ("모든 영상", "All videos"),
    "library.no_phase": ("Phase 없음", "No phase"),
    "library.empty.title": ("아직 키포즈가 없습니다", "No key poses yet"),
    "library.empty.body": ("마음에 드는 프레임에서\n{key} 키를 누르면 여기에 모입니다.", "Press {key} on a frame you like\nand it lands here."),
    "library.no_match": ("조건에 맞는 키포즈가 없습니다", "No key poses match"),
    "library.count": ("{n}개", "{n}"),
    "library.count_filtered": ("{shown} / {total}개", "{shown} / {total}"),
    "inspector.title": ("편집 칸", "Inspector"),  # the name the guide uses (help/content.py)
    "inspector.empty": (
        "키포즈를 선택하면 여기서 이름, Phase, 태그, 메모를 편집합니다.\n더블클릭하면 그 프레임으로 이동합니다.",
        "Select a key pose to edit its name, phase, tags and notes.\nDouble-click one to jump to its frame.",
    ),
    "inspector.name": ("이름", "Name"),
    "inspector.phase": ("Phase", "Phase"),
    "inspector.tags": ("태그", "Tags"),
    "inspector.tags_hint": ("쉼표로 구분  예) 질풍참, 방패", "Comma separated, e.g. dash slash, shield"),
    "inspector.notes": ("메모", "Notes"),
    "inspector.notes_hint": ("이 포즈를 고른 이유, 참고할 부분…", "Why this pose, what to take from it…"),
    "inspector.source": ("영상", "Video"),
    "inspector.frame": ("프레임", "Frame"),
    "inspector.time": ("시간", "Time"),
    "inspector.jump": ("이 프레임으로 이동", "Go to frame"),
    "inspector.delete": ("삭제", "Delete"),
    "inspector.new_phase": ("새 Phase 추가…", "Add a phase…"),
    "inspector.missing_image": ("이미지 파일 없음", "Image file missing"),
    "dlg.new_phase.title": ("새 Phase", "New phase"),
    "dlg.new_phase.body": ("Phase 이름  (예: Dash, 질풍참_타격)", "Phase name  (e.g. Dash, Shield Bash)"),
    "phase_menu.title": ("어떤 Phase로 추가할까요?", "Add as which phase?"),
    # -- on-screen feedback --------------------------------------------------
    "osd.playing": ("▶  재생  {speed}", "▶  Play  {speed}"),
    "osd.paused": ("❚❚  정지", "❚❚  Paused"),
    "osd.speed": ("속도  {speed}", "Speed  {speed}"),
    "osd.loop_in": ("루프 시작  {frame}", "Loop in  {frame}"),
    # {n}: frames in the range, both ends included — animators loop an attack to count it
    "osd.loop_out": ("루프 끝  {frame}  ·  {n}f", "Loop out  {frame}  ·  {n}f"),
    "osd.loop_out_only": ("루프 끝  {frame}", "Loop out  {frame}"),
    "osd.loop_on": ("루프 켜짐  {a} – {b}  ·  {n}f", "Loop on  {a} – {b}  ·  {n}f"),
    "osd.loop_off": ("루프 꺼짐", "Loop off"),
    # {keys}: the loop_in / loop_out keys, filled from the keymap (both can be rebound)
    "osd.loop_none": ("먼저 {keys} 키로 루프 구간을 지정하세요", "Set a loop range first with {keys}"),
    "osd.loop_cleared": ("루프 구간을 지웠습니다", "Loop range cleared"),
    "osd.mirror_on": ("Mirror 켜짐", "Mirror on"),
    "osd.mirror_off": ("Mirror 꺼짐", "Mirror off"),
    "osd.fit": ("화면 맞춤", "Fit to view"),
    "osd.top_on": ("항상 위 켜짐", "Always on top: on"),
    "osd.top_off": ("항상 위 꺼짐", "Always on top: off"),
    "osd.focus_on": ("Focus 모드  ·  {key} 키로 돌아가기", "Focus mode  ·  {key} to exit"),
    "osd.saved": ("저장했습니다", "Saved"),
    "osd.already_added": ("이미 프로젝트에 있는 영상입니다", "Already in this project"),
    "osd.step_set": ("이동 간격  {n}프레임", "Custom step  {n} frames"),
    # Hold counts are anim frames already, so they stay put; only their seconds change.
    "osd.anim_fps": ("애니 fps {fps:g}  ·  Hold는 애니 프레임 그대로", "Anim fps {fps:g}  ·  holds keep their anim frames"),
    # -- transport -----------------------------------------------------------
    "transport.frame_tip": ("현재 프레임 — 클릭해서 번호를 입력하고 Enter", "Current frame — click, type a number, Enter"),
    "transport.time_tip": ("현재 시간 / 전체 길이", "Current time / duration"),
    "transport.fps_tip": ("원본 영상의 fps", "Frame rate of the source video"),
    # the fps badge drops out on a narrow window; the count keeps the rate in its tooltip
    "transport.count_tip": ("마지막 프레임 번호  ·  원본 영상 {fps}", "Last frame number  ·  source video {fps}"),
    "transport.vfr_tip": (
        "가변 프레임레이트(VFR) 영상입니다. 게임 녹화에서 흔합니다.\n프레임 번호는 정확하고, 시간은 각 프레임의 실제 시각을 씁니다.",
        "Variable frame rate (VFR) video, common in game captures.\nFrame numbers are exact; times use each frame's real timestamp.",
    ),
    "transport.speed_tip": ("재생 속도", "Playback speed"),
    # -- empty states --------------------------------------------------------
    "empty.no_video.title": ("영상을 끌어다 놓으세요", "Drop a video here"),
    "empty.no_video.body": (
        "레퍼런스 영상 파일을 이 창에 끌어다 놓거나 아래 버튼을 누르세요.\n여러 개를 한 번에 넣어도 됩니다. 원본 파일은 복사하지 않습니다.",
        "Drag reference videos into this window or use the button below.\nSeveral at once is fine. Files are referenced, never copied.",
    ),
    "empty.import_btn": ("영상 불러오기", "Import video"),
    "empty.guide_btn": ("3분 시작 가이드", "3-minute quick start"),  # same name as act.guide
    "empty.loading": ("영상 여는 중…", "Opening video…"),
    "empty.missing.title": ("영상 파일을 찾을 수 없습니다", "Video file not found"),
    "empty.missing.body": (
        "파일이 옮겨졌거나 이름이 바뀌었을 수 있어요.\n새 위치를 알려주면 이 영상의 작업 내용이 그대로 다시 연결됩니다.",
        "It may have been moved or renamed.\nPoint to its new location and everything made from it reconnects.",
    ),
    "empty.relink_btn": ("다시 연결…", "Relink…"),
    "empty.close_tab_btn": ("탭 닫기", "Close tab"),
    "empty.error.title": ("이 영상을 열 수 없습니다", "Can't open this video"),
    "empty.error.body": (
        "파일이 손상됐거나 지원하지 않는 형식일 수 있어요.\n다른 프로그램에서는 열린다면 문제 신고에 이 파일 정보를 알려주세요.",
        "The file may be damaged or in an unsupported format.\nIf other players open it, please report it with the file details.",
    ),
    "viewer.drop": ("놓아서 영상 추가", "Drop to add videos"),
    # -- welcome -------------------------------------------------------------
    "welcome.start_video": ("영상 불러와서 시작", "Import a video"),
    "welcome.drop_hint": ("영상 파일을 이 창 아무 곳에나 끌어다 놓아도 됩니다", "…or drop video files anywhere in this window"),
    "welcome.recent": ("최근 프로젝트", "Recent projects"),
    "welcome.recent_empty": ("저장한 프로젝트가 여기에 표시됩니다.", "Projects you save will show up here."),
    "welcome.first_time": ("처음이세요?", "New here?"),
    "welcome.first_time_body": (
        "3분이면 영상 불러오기부터 루프·슬로우로 동작을 뜯어보고 키포즈를 뽑는 법까지 익힐 수 있어요.",
        "In three minutes you'll go from importing a video to studying it with loops and slow motion, then pulling key poses.",
    ),
    "welcome.guide_btn": ("3분 시작 가이드", "3-minute quick start"),
    "welcome.shortcuts_btn": ("단축키 한눈에 보기", "Keyboard shortcuts"),  # same name as act.shortcut_sheet
    "welcome.manual_btn": ("사용 설명서", "User guide"),
    "welcome.workflow": ("작업 흐름", "Workflow"),
    "welcome.available": ("사용 가능", "Available"),
    "welcome.coming": ("준비 중", "Coming soon"),
    # Flow bodies are comma lists: with "·" separators the break fell after the dot and left
    # it dangling at a line end ("Step · loop ·"). U+00A0 stays only inside multi-word items
    # ('Contact Sheet', 'slow motion') so each item wraps as a whole.
    "flow.1.title": ("영상 불러오기", "Import video"),
    "flow.1.body": ("여러 레퍼런스를 한\u00a0프로젝트에", "Many references, one project"),
    "flow.2.title": ("프레임 분석", "Frame by frame"),
    "flow.2.body": ("프레임\u00a0이동, 루프, 슬로우", "Step, loop, slow\u00a0motion"),
    "flow.3.title": ("드로잉", "Draw over"),
    "flow.3.body": ("척추선, 무게중심, 검\u00a0궤적", "Spine, balance, sword\u00a0arc"),
    "flow.4.title": ("키포즈 추출", "Key poses"),
    "flow.4.body": ("{key} 한 번으로 출처와 함께 저장", "{key} saves it with video & frame"),
    "flow.5.title": ("비교 · 조합", "Compare · combine"),
    "flow.5.body": ("Phase별 비교, 순서와 타이밍", "Compare by phase, set order & timing"),
    "flow.6.title": ("내보내기", "Export"),  # the export step; blocking itself happens in Maya
    "flow.6.body": ("Contact\u00a0Sheet, Maya\u00a0마커", "Contact\u00a0sheet, Maya\u00a0markers"),
    # -- tabs / status -------------------------------------------------------
    "tabs.add_tip": ("영상 추가", "Add video"),
    "tabs.missing_tip": ("파일을 찾을 수 없음: {path}", "File not found: {path}"),
    "status.unsaved": ("저장 안 됨", "Not saved"),
    "status.untitled_tip": ("아직 저장하지 않은 프로젝트입니다.", "This project hasn't been saved yet."),
    "status.save_hint": ("{key} 키로 저장하세요.", "Press {key} to save."),
    "hint.play": ("재생", "play"),
    "hint.frame": ("1프레임 이동", "step 1 frame"),
    "hint.loop": ("루프 구간", "loop range"),
    # what D does: the group name "드로잉" read as the draw tool or as showing drawings (H)
    "hint.draw": ("그리기 도구", "draw tool"),
    "hint.all": ("단축키 한눈에", "shortcuts"),  # the ? overlay; "단축키 전체" is a help page
    # welcome page: only the keys that work before a video is open
    "hint.import": ("영상 불러오기", "import video"),
    "hint.open": ("프로젝트 열기", "open project"),
    "hint.help": ("사용 설명서", "user guide"),
    # -- dialogs -------------------------------------------------------------
    "btn.save": ("저장", "Save"),
    "btn.discard": ("저장 안 함", "Don't Save"),
    "btn.cancel": ("취소", "Cancel"),
    "btn.ok": ("확인", "OK"),
    "btn.close": ("닫기", "Close"),
    "btn.remove": ("빼기", "Remove"),
    "btn.replace": ("덮어쓰기", "Replace"),
    "btn.restart": ("지금 다시 시작", "Restart now"),
    "btn.later": ("나중에", "Later"),
    "dlg.open_project": ("프로젝트 열기", "Open project"),
    "dlg.project_filter": ("aniREF 프로젝트 (*.aniref)", "aniREF project (*.aniref)"),
    "dlg.import": ("영상 불러오기", "Import video"),
    "dlg.video_filter": ("영상 파일 ({exts})", "Video files ({exts})"),
    "dlg.all_files": ("모든 파일 (*)", "All files (*)"),
    "dlg.save_as": ("프로젝트 저장 — 프로젝트 폴더 이름을 입력하세요", "Save project — name the project folder"),
    "dlg.save_as_filter": ("aniREF 프로젝트 폴더", "aniREF project folder"),
    "dlg.unsaved.title": ("저장하지 않은 변경 사항", "Unsaved changes"),
    "dlg.unsaved.body": ("'{name}'의 변경 사항을 저장할까요?", "Save changes to '{name}'?"),
    "dlg.close_source.title": ("영상 탭 닫기", "Close video"),
    "dlg.close_source.body": (
        "'{name}'을(를) 프로젝트에서 뺄까요?\n원본 영상 파일은 지워지지 않습니다.",
        "Remove '{name}' from the project?\nThe video file itself is not deleted.",
    ),
    "dlg.close_source.loses": (
        "이 영상에서 뽑은 키포즈 {poses}개(시퀀스 카드 포함)와 드로잉 · 궤적 · 타이밍 구간도 함께 빠집니다.",
        "Its {poses} key poses (and their sequence cards), drawings, trails and timing sections go with it.",
    ),
    "dlg.close_source.undo": ("{key} 키로 되돌릴 수 있습니다.", "{key} brings it back."),
    "dlg.save_as_exists.title": ("이미 있는 프로젝트", "Project already exists"),
    "dlg.save_as_exists.body": (
        "'{folder}' 폴더에는 이미 aniREF 프로젝트가 있습니다.\n지금 프로젝트로 덮어쓸까요? 원래 프로젝트는 되살릴 수 없습니다.",
        "'{folder}' already holds an aniREF project.\nReplace it with this one? The other project can't be brought back.",
    ),
    "dlg.open_failed": ("프로젝트를 열 수 없습니다", "Can't open project"),
    "dlg.save_failed": ("저장하지 못했습니다", "Couldn't save"),
    "dlg.relink": ("'{name}' 영상 위치 찾기", "Locate '{name}'"),
    "dlg.media_changed.title": ("영상 파일이 바뀌었습니다", "Video file changed"),
    "dlg.media_changed.body": (
        "'{name}'의 프레임 수가 {old} → {new}(으)로 달라졌습니다.\n이 영상에서 뽑은 키포즈의 프레임 번호가 맞지 않을 수 있어요.",
        "'{name}' now has {new} frames instead of {old}.\nKey poses taken from it may point at different frames.",
    ),
    "dlg.language.title": ("언어 변경", "Language"),
    "dlg.language.body": ("다시 시작하면 적용됩니다. 지금 다시 시작할까요?", "The new language applies after a restart. Restart now?"),
    "dlg.about.title": ("aniREF 정보", "About aniREF"),
    "dlg.about.body": (
        "<h3>aniREF {version}</h3><p>게임 애니메이션 레퍼런스 분석 / 키포즈 조합 툴</p>"
        "<p style='color:#9aa2b3'>GPL-3.0 라이선스<br>Qt for Python(PySide6), FFmpeg(PyAV) 사용</p>",
        "<h3>aniREF {version}</h3><p>Game animation reference analysis &amp; key pose composition</p>"
        "<p style='color:#9aa2b3'>Licensed under GPL-3.0<br>Built with Qt for Python (PySide6) and FFmpeg (PyAV)</p>",
    ),
    # -- shortcut overlay ----------------------------------------------------
    "overlay.title": ("단축키", "Keyboard Shortcuts"),
    "overlay.close_hint": ("{keys} 키로 닫기", "{keys} to close"),
    "overlay.or": (" 또는 ", " or "),
    "overlay.help_hint": ("{key} 전체 설명서", "{key} full guide"),
    "overlay.note": (
        # {key}: the play_pause key from the keymap
        "글자 입력칸에 커서가 있을 때는 입력이 우선합니다. 메모를 쓰다가 {key} 키를 눌러도 재생되지 않아요.",
        "While a text field has the cursor, typing wins — {key} in a note won't start playback.",
    ),
    # -- help window ---------------------------------------------------------
    "help.title": ("aniREF 사용 설명서", "aniREF User Guide"),
    "help.search": ("설명서 검색", "Search the guide"),
    "help.no_results": ("검색 결과가 없습니다", "No results"),
    "help.related": ("함께 보기", "See also"),
    "help.coming": ("준비 중", "Coming soon"),
    "help.tip": ("팁", "Tip"),
    "help.note": ("참고", "Note"),
    "help.warn": ("주의", "Caution"),
}
