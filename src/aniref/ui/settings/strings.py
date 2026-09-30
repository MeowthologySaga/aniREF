"""Text, icons and the shortcut this feature brings with it.

Imported by the package `__init__`, so anything that touches the settings
modules gets the strings registered first.
"""

from __future__ import annotations

from .. import icons, shortcuts
from ..i18n import register as register_strings

_STROKE = 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'


def _gear() -> str:
    """Eight-toothed gear, built from points so the teeth stay even."""
    import math

    outer, inner, teeth = 10.2, 7.6, 8
    points: list[str] = []
    for i in range(teeth * 4):
        angle = math.pi * 2 * i / (teeth * 4) + math.pi / teeth / 2
        r = outer if (i % 4) in (1, 2) else inner
        points.append(f"{12 + r * math.cos(angle):.2f} {12 + r * math.sin(angle):.2f}")
    return f'<path d="M{" L".join(points)} Z" {_STROKE}/><circle cx="12" cy="12" r="3.2" {_STROKE}/>'


icons.register(
    {
        "gear": _gear(),
        "sliders": f'<g {_STROKE}><path d="M4 7h9M18.5 7H20M4 17h3.5M13 17h7"/>'
        '<circle cx="15.5" cy="7" r="2.4"/><circle cx="10" cy="17" r="2.4"/></g>',
        "restore": f'<g {_STROKE}><path d="M3.5 12a8.5 8.5 0 1 0 2.9-6.4L3.5 8"/>'
        '<path d="M3.5 3.5v5h5"/><path d="M12 8v4.3l3 1.8"/></g>',
        "update": f'<g {_STROKE}><circle cx="12" cy="12" r="9"/><path d="M12 7.2v8.2"/><path d="M8.4 11.8L12 15.4l3.6-3.6"/></g>',
        "info": f'<g {_STROKE}><circle cx="12" cy="12" r="9"/><path d="M12 11v5.2"/><path d="M12 7.6h.01"/></g>',
    }
)

shortcuts.register([shortcuts.Shortcut("settings", ("Ctrl+,",), "project")])

register_strings(
    {
        "act.settings": ("설정…", "Settings…"),
        # -- dialog shell --------------------------------------------------------
        "set.title": ("설정", "Settings"),
        "set.apply": ("적용", "Apply"),
        "set.restart_language": ("언어는 다시 시작하면 적용됩니다", "Language applies after a restart"),
        "set.restart_cache": ("캐시 크기는 다시 시작하면 적용됩니다", "Cache size applies after a restart"),
        "set.restart_both": ("언어와 캐시 크기는 다시 시작하면 적용됩니다", "Language and cache size apply after a restart"),
        "set.osd.saved": ("설정을 저장했습니다", "Settings saved"),
        "set.on": ("켜짐", "On"),
        "set.off": ("꺼짐", "Off"),
        "set.page.general": ("일반", "General"),
        "set.page.playback": ("재생", "Playback"),
        "set.page.shortcuts": ("단축키", "Shortcuts"),
        "set.page.autosave": ("자동 저장", "Autosave"),
        "set.page.updates": ("업데이트", "Updates"),
        "set.page.about": ("정보", "About"),
        "set.general.desc": ("언어와 새 프로젝트의 기본값.", "Language and the defaults for new projects."),
        "set.playback.desc": ("프레임 이동과 메모리 사용.", "Frame stepping and memory use."),
        "set.shortcuts.desc": (
            "손에 맞게 키를 바꾸세요. 메뉴와 툴팁, 단축키 한눈에 보기 화면에도 바로 반영됩니다.",
            "Rebind keys to fit your hands — menus, tooltips and the Keyboard shortcuts panel follow.",
        ),
        "set.autosave.desc": ("갑자기 꺼져도 작업이 남도록.", "So a crash never costs you your work."),
        "set.updates.desc": ("새 버전이 나오면 알려 드립니다.", "Hear about a new version when it lands."),
        "set.about.desc": ("버전, 라이선스, 설정이 저장되는 곳.", "Version, license, and where settings live."),
        # -- general -------------------------------------------------------------
        "set.language": ("언어 / Language", "Language / 언어"),
        "set.language.hint": (
            "다시 시작하면 바뀐 언어로 열립니다. Phase 이름(Anticipation 등)은 애니 용어라 두 언어 모두 영어입니다.",
            "aniREF opens in the new language after a restart. Phase names (Anticipation…) stay English in both.",
        ),
        "set.new_project": ("새 프로젝트 기본값", "New project defaults"),
        "set.anim_fps": ("애니 fps", "Anim fps"),  # same name as the View menu
        "set.anim_fps.hint": (
            "만들고 있는 애니메이션(Maya 씬)의 fps로, 포즈 사이 타이밍과 Maya 마커의 기준입니다. 지금 열린 프로젝트는 보기 → 애니 fps에서 바꿉니다.",
            "The frame rate of the animation you are building (your Maya scene); pose timing and Maya markers use it. For the open project, use View → Anim fps.",
        ),
        "set.fps_n": ("{n}fps", "{n}fps"),
        "set.frame_base": ("프레임 번호 시작", "Frame numbering"),
        "set.frame_base.hint": (
            # Stored per project like anim fps ("new projects only" is said once, under the
            # section header: set.new_project.note), so it says where to change the open one
            # (menu names as in menu.view / menu.frame_base).
            "화면에 보이는 프레임 번호를 1부터 셀지 0부터 셀지 정합니다. Maya 타임라인은 1부터입니다. 지금 열린 프로젝트는 보기 → 프레임 번호 시작에서 바꿉니다.",
            "Whether frame numbers on screen start at 1 or 0; Maya's timeline starts at 1. For the open project, use View → Frame Numbering.",
        ),
        "set.frame_base.one": ("1부터", "From 1"),
        "set.frame_base.zero": ("0부터", "From 0"),
        "set.new_project.note": (
            "새로 만드는 프로젝트에만 적용됩니다. 이미 만든 프로젝트는 각자 저장된 값을 씁니다.",
            "Applies to new projects only; existing projects keep their own values.",
        ),
        # -- playback ------------------------------------------------------------
        "set.custom_step": ("이동 간격", "Custom step"),
        "set.custom_step.hint": (
            "{keys} 키로 한 번에 건너뛸 프레임 수. 2프레임씩 찍는 애니(투스)를 볼 때 편합니다.",
            "How many frames {keys} jumps at once. Handy when you work on twos.",
        ),
        "set.cache": ("프레임 캐시 메모리", "Frame cache memory"),
        "set.cache.hint": (
            "풀어 놓은 영상 프레임을 담아 두는 공간입니다. 크면 앞뒤 이동과 루프가 더 부드럽고, 작으면 Maya 같은 다른 프로그램에 메모리를 더 남깁니다.",
            "Room for decoded video frames. More makes stepping and loops smoother; less leaves memory for Maya and the rest.",
        ),
        "set.cache.auto": ("자동 (권장)", "Auto (recommended)"),
        "set.cache.manual": ("직접 지정", "Set myself"),
        "set.cache.detected": ("이 PC의 메모리 {ram}  ·  자동이면 {auto} 사용", "This PC has {ram} of memory  ·  auto uses {auto}"),
        "set.cache.restart": ("다음에 aniREF를 시작할 때 적용됩니다.", "Applies the next time aniREF starts."),
        # -- shortcuts -----------------------------------------------------------
        "set.keys.search": ("기능 이름이나 키로 검색  (예: 루프, Ctrl+S)", "Search by action or key  (e.g. loop, Ctrl+S)"),
        "set.keys.howto": (
            "줄을 고른 뒤 {enter} 키를 누르거나 더블클릭하고, 새 키 조합을 누르세요.  {remove} 키를 누르면 단축키가 없어집니다.",
            "Pick a row, press {enter} or double-click it, then press the new keys.  {remove} removes a shortcut.",
        ),
        "set.keys.change": ("바꾸기", "Change"),
        "set.keys.add": ("키 추가", "Add key"),
        "set.keys.clear": ("없애기", "Remove"),
        "set.keys.reset": ("기본값", "Default"),
        "set.keys.reset_all": ("모두 기본값으로", "Reset all"),
        "set.keys.none": ("없음", "None"),
        "set.keys.or": ("또는", "or"),
        "set.keys.recording": ("새 키 조합을 누르세요…  ·  Esc 취소", "Press the new key combination…  ·  Esc cancels"),
        "set.keys.recording_cell": ("새 키를 누르세요…", "Press a key…"),
        "set.keys.default_tip": ("기본값: {keys}", "Default: {keys}"),
        "set.keys.changed": ("‘{name}’ 단축키를 {key} 키로 바꿨습니다", "‘{name}’ is now {key}"),
        "set.keys.moved": ("‘{name}’ 단축키를 {key} 키로 바꿨습니다  ·  ‘{other}’에서 가져왔습니다", "‘{name}’ is now {key}  ·  taken from ‘{other}’"),
        "set.keys.added": ("‘{name}’에 {key} 키를 더했습니다", "Added {key} to ‘{name}’"),
        "set.keys.cleared": ("‘{name}’ 단축키를 없앴습니다", "‘{name}’ has no shortcut now"),
        "set.keys.reset_done": ("‘{name}’ 단축키를 기본값으로 되돌렸습니다", "‘{name}’ is back to its default"),
        "set.keys.reset_all_done": ("모든 단축키를 기본값으로 되돌렸습니다", "Every shortcut is back to its default"),
        "set.keys.cancelled": ("바꾸지 않았습니다", "Nothing changed"),
        "set.keys.reserved": ("{key} 키는 aniREF가 따로 쓰고 있어 지정할 수 없습니다", "{key} is reserved by aniREF and can't be assigned"),
        "set.keys.select_first": ("먼저 바꿀 기능을 고르세요", "Pick an action first"),
        "set.keys.no_match": ("검색 결과가 없습니다", "No matches"),
        "set.keys.pending": ("확인이나 적용을 누르면 저장됩니다", "Press OK or Apply to keep these"),
        "set.keys.conflict.title": ("단축키가 겹칩니다", "That key is taken"),
        "set.keys.conflict.body": (
            "{key} 키는 이미 ‘{other}’에 쓰이고 있습니다.\n‘{name}’(으)로 옮길까요? ‘{other}’에서는 이 키가 빠집니다.",
            "{key} already belongs to ‘{other}’.\nMove it to ‘{name}’? ‘{other}’ loses this key.",
        ),
        "set.keys.replace": ("옮기기", "Move it"),
        # -- autosave ------------------------------------------------------------
        "set.autosave.enable": ("자동 저장", "Autosave"),
        "set.autosave.enable.hint": (
            "저장하지 않은 변경이 있으면 정해진 간격으로 복구용 사본을 따로 남깁니다. 프로젝트 파일 자체는 직접 저장할 때만 바뀝니다.",
            "While there are unsaved changes, a recovery copy is written on a timer. Your project file itself only changes when you save.",
        ),
        "set.autosave.interval": ("저장 간격", "How often"),
        "set.autosave.interval.hint": ("짧을수록 잃는 작업이 적습니다.", "Shorter means less work to redo."),
        "set.autosave.every": ("{n}분마다", "Every {n} min"),
        "set.autosave.where": ("사본이 저장되는 곳", "Where copies go"),
        "set.autosave.where.body": (
            "저장한 프로젝트 — 프로젝트 폴더 안 project.aniref.autosave\n저장 전 프로젝트 — {path}",
            "Saved projects — project.aniref.autosave inside the project folder\nUnsaved projects — {path}",
        ),
        "set.autosave.note": (
            "aniREF가 갑자기 꺼졌다면 다음에 열 때 복구할지 물어봅니다. 정상적으로 저장하거나 닫으면 사본은 지워집니다.",
            "If aniREF closes unexpectedly you'll be asked whether to recover. Copies disappear when you save or close normally.",
        ),
        # -- updates -------------------------------------------------------------
        "set.updates.check": ("시작할 때 새 버전 확인", "Check for a new version on start"),
        "set.updates.check.hint": (
            "하루에 한 번 GitHub에서 최신 버전 번호만 가져옵니다. 프로젝트나 사용 기록은 아무것도 보내지 않습니다.",
            "Once a day aniREF asks GitHub for the latest version number. Nothing about you or your work is sent.",
        ),
        "set.updates.current": ("현재 버전 {version}", "You have version {version}"),
        "set.updates.last": ("마지막 확인 {when}", "Last checked {when}"),
        "set.updates.never": ("아직 확인한 적 없음", "Not checked yet"),
        "set.updates.now": ("지금 확인", "Check now"),
        "set.updates.checking": ("확인하는 중…", "Checking…"),
        "set.updates.latest": ("최신 버전을 쓰고 있습니다", "You're on the latest version"),
        "set.updates.available": ("새 버전 {version} 이(가) 나왔습니다", "Version {version} is out"),
        "set.updates.failed": ("확인하지 못했습니다  ·  {error}", "Couldn't check  ·  {error}"),
        "set.updates.no_repo": (
            "이 빌드에는 확인할 저장소 주소가 아직 없어서 업데이트 확인을 쓸 수 없습니다.",
            "This build has no repository address yet, so update checking is unavailable.",
        ),
        "set.updates.open_page": ("다운로드 페이지 열기", "Open the download page"),
        "set.updates.notice.title": ("새 버전이 있습니다", "A new version is out"),
        "set.updates.notice.body": (
            "aniREF {version} 이(가) 나왔습니다. 지금 쓰는 버전은 {current} 입니다.\n"
            "다운로드 페이지에서 받아서 덮어쓰면 됩니다. 프로젝트와 설정은 그대로 남습니다.",
            "aniREF {version} is available; you have {current}.\n"
            "Download it and install over this one — your projects and settings stay put.",
        ),
        # -- about ---------------------------------------------------------------
        "set.about.version": ("버전 {version}", "Version {version}"),
        "set.about.license": ("라이선스", "License"),
        "set.about.license.body": ("GPL-3.0 — 마음껏 쓰고, 고치고, 나눠 주세요.", "GPL-3.0 — use it, change it, pass it on."),
        "set.about.build": ("설치 형태", "This build"),
        "set.about.build.installed": ("설치판", "Installed"),
        "set.about.build.portable": ("포터블판 — 설정이 프로그램 폴더 안에 함께 있습니다", "Portable — settings travel inside the program folder"),
        "set.about.build.source": ("소스에서 실행 중 (개발)", "Running from source (development)"),
        "set.about.data": ("설정 · 로그 폴더", "Settings & log folder"),
        "set.about.open_folder": ("폴더 열기", "Open folder"),
        "set.about.built_with": ("구성 요소", "Built with"),
        # -- recovery prompt -----------------------------------------------------
        "set.recover.title": ("작업 복구", "Recover work"),
        "set.recover.project": (
            "‘{name}’에 저장하지 않은 작업이 남아 있습니다.\n자동 저장 시각: {when}",
            "‘{name}’ has unsaved work from an earlier session.\nAutosaved at {when}",
        ),
        "set.recover.untitled": (
            "저장하지 않은 프로젝트가 남아 있습니다.\n자동 저장 시각: {when}\n영상 {sources}개 · 키포즈 {poses}개",
            "An unsaved project was left behind.\nAutosaved at {when}\n{sources} videos · {poses} key poses",
        ),
        "set.recover.info": (
            "aniREF가 정상적으로 닫히지 않은 것 같습니다. 복구하면 자동 저장된 내용을 열어 줍니다. 내용을 확인한 뒤 저장하세요.",
            "aniREF didn't close normally. Recover opens the autosaved copy — look it over, then save it.",
        ),
        "set.recover.later.untitled": ("‘나중에’를 누르면 그대로 두고 다음 실행 때 다시 물어봅니다.", "‘Later’ keeps it and asks again next time you start aniREF."),
        "set.recover.later.project": ("‘나중에’를 누르면 지금은 열지 않고, 다음에 열 때 다시 물어봅니다.", "‘Later’ leaves the project closed and asks again next time you open it."),
        "set.recover.recover": ("복구", "Recover"),
        "set.recover.discard": ("버리기", "Discard"),
        "set.recover.later": ("나중에", "Later"),
        "set.recover.failed": ("복구 파일을 읽을 수 없습니다", "Can't read the recovery copy"),
        "set.autosaved_at": ("자동 저장 {when}", "Autosaved {when}"),
    }
)
