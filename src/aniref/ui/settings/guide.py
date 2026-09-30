"""User guide page for settings, shortcut customization, autosave and updates."""

from __future__ import annotations

from ...appdata import data_dir
from ..help.content import Block, Page, h, note, p, register_page, tip
from ..i18n import pick as t


def _page() -> Page:
    return Page(
        "settings",
        "gear",
        t("설정 · 단축키", "Settings & shortcuts"),
        t(
            "{a:settings} 키로 설정 창을 엽니다. 언어, 캐시, 자동 저장, 단축키가 모두 여기에 있습니다.",
            "{a:settings} opens settings: language, cache, autosave and every shortcut.",
        ),
        [
            h(t("설정이 저장되는 곳", "Where settings are kept")),
            p(
                t(
                    "설치판은 **%APPDATA%\\aniREF** 폴더에, 포터블판은 aniREF.exe 옆 **data** 폴더에 저장합니다. "
                    "포터블판을 USB나 공유 폴더에 넣어 두면 설정과 단축키가 그대로 따라갑니다. "
                    "지금 쓰는 위치는 설정 → 정보에서 확인하고 폴더를 열어 볼 수 있습니다.",
                    "An installed aniREF keeps them in **%APPDATA%\\aniREF**; a portable one in the **data** folder next "
                    "to aniREF.exe, so a portable copy on a USB stick carries your settings and keys with it. "
                    "Settings → About shows the folder in use and opens it.",
                )
            ),
            h(t("단축키 바꾸기", "Rebinding keys")),
            Block(
                "steps",
                [
                    (
                        t("설정 → 단축키", "Settings → Shortcuts"),
                        t(
                            "{a:settings} 키를 누르고 왼쪽에서 **단축키**를 고릅니다. 검색칸에 기능 이름이나 키를 그대로 쳐도 됩니다.",
                            "Press {a:settings} and pick **Shortcuts**. The search box takes an action name or a key.",
                        ),
                    ),
                    (
                        t("새 키 누르기", "Press the new key"),
                        t(
                            "바꿀 줄을 고르고 {k:Enter} (또는 더블클릭) 후 원하는 키 조합을 누릅니다. {k:Esc} 키로 취소합니다.",
                            "Select the row, press {k:Enter} (or double-click), then press the combination you want. {k:Esc} cancels.",
                        ),
                    ),
                    (
                        t("겹치면 물어봅니다", "Clashes are never silent"),
                        t(
                            "이미 다른 기능이 쓰는 키라면 누가 쓰고 있는지 알려 주고, 옮길지 물어봅니다. 옮기면 원래 기능은 그 키를 잃습니다.",
                            "If another action already has the key, aniREF says who and asks whether to move it. The old owner loses it.",
                        ),
                    ),
                    (
                        t("없애기 · 되돌리기", "Remove or reset"),
                        t(
                            "{k:Del} 키를 누르면 그 기능의 단축키가 없어집니다. **기본값**은 한 줄만, **모두 기본값으로**는 전체를 처음 상태로 되돌립니다.",
                            "{k:Del} leaves an action without a shortcut. **Default** resets one row, **Reset all** puts every key back.",
                        ),
                    ),
                ],
            ),
            tip(
                t(
                    "바꾼 키는 메뉴, 툴팁, {a:shortcut_sheet} 화면, 이 설명서에 바로 반영됩니다. 확인이나 적용을 눌러야 저장됩니다.",
                    "New keys show up in menus, tooltips, the {a:shortcut_sheet} sheet and this guide right away — press OK or Apply to keep them.",
                )
            ),
            h(t("자동 저장과 복구", "Autosave and recovery")),
            p(
                t(
                    "저장하지 않은 변경이 있으면 기본 3분마다 **복구용 사본**을 남깁니다. 저장한 프로젝트는 폴더 안 "
                    "**project.aniref.autosave** 에, 아직 저장 전인 프로젝트는 **{path}** 에 저장됩니다.",
                    "While there are unsaved changes a **recovery copy** is written every 3 minutes by default: into "
                    "**project.aniref.autosave** inside the project folder, or into **{path}** for a project you haven't saved yet.",
                ).format(path=data_dir() / "autosave")
            ),
            note(
                t(
                    "자동 저장은 프로젝트 파일 자체를 건드리지 않습니다. **project.aniref** 는 {a:save_project} 키로 직접 저장할 때만 바뀝니다.",
                    "Autosave never touches the project file itself: **project.aniref** only changes when you save with {a:save_project}.",
                )
            ),
            p(
                t(
                    "aniREF가 갑자기 꺼졌다면 다음에 그 프로젝트를 열 때(저장 전 프로젝트라면 시작할 때) **복구할까요?** 하고 물어봅니다. "
                    "복구하면 자동 저장된 내용이 열리고, 확인한 뒤 {a:save_project} 키로 저장하면 됩니다. 정상적으로 저장하거나 닫으면 사본은 지워집니다.",
                    "If aniREF closed unexpectedly you'll be asked whether to **recover** the next time you open that project "
                    "(or at startup, for a project that was never saved). Recover opens the copy; look it over and {a:save_project} it. "
                    "Saving or closing normally removes the copy.",
                )
            ),
            h(t("업데이트 확인", "Update check")),
            p(
                t(
                    "켜 두면 하루에 한 번 GitHub에서 최신 버전 번호만 확인하고, 새 버전이 있으면 알려 줍니다. "
                    "프로젝트 내용이나 사용 기록은 아무것도 보내지 않습니다. 설정 → 업데이트에서 끌 수 있고, **지금 확인** 으로 직접 확인할 수도 있습니다.",
                    "Left on, aniREF asks GitHub once a day for the latest version number and tells you when a new one is out. "
                    "Nothing about your projects or your usage is sent. Turn it off in Settings → Updates, or press **Check now** yourself.",
                )
            ),
            Block("links", ["shortcuts", "project"]),
        ],
    )


register_page(80, _page)
