"""User guide page for exporting (contact sheet, Maya markers)."""

from __future__ import annotations

from ..help.content import Block, Page, h, note, p, register_page, tip
from ..i18n import pick as t

_SAMPLE = """{ "format": "aniref.markers", "anim_fps": 30, "start_frame": 1,
  "markers": [
    { "frame": 1,  "end_frame": 6,  "name": "Anticipation",
      "source": "MH_SnS_01", "source_frame": 37 },
    { "frame": 7,  "end_frame": 10, "name": "Dash",
      "source": "Souls_02",  "source_frame": 112 } ] }"""


def _page() -> Page:
    return Page(
        "export",
        "export",
        t("내보내기 · Maya 마커", "Export · Maya markers"),
        t(
            "시퀀스를 그림 한 장으로 뽑고, 타이밍을 Maya 타임라인에 그대로 올립니다.",
            "Turn a sequence into one image, and put its timing straight onto the Maya timeline.",
        ),
        [
            h("Contact Sheet"),
            p(
                t(
                    "키포즈를 순서대로 PNG 한 장에 담습니다. PureRef에 띄워 두거나 인쇄해서 옆에 놓고 블로킹하세요.",
                    "Puts the key poses in order on one PNG — keep it in PureRef or print it and block next to it.",
                )
            ),
            Block(
                "steps",
                [
                    (
                        t("무엇을 담을지 고르기", "Choose what goes on it"),
                        t(
                            "{a:export_contact_sheet} 키를 누르면 지금 작업 중인 시퀀스로 시작합니다. 라이브러리에서 선택한 키포즈나 모든 키포즈로 만들려면 창 안의 **내용**에서 바꾸세요.",
                            "{a:export_contact_sheet} starts with the sequence you are working on. To use the poses selected in the library, or every key pose, switch **Content** in the window.",
                        ),
                    ),
                    (
                        t("옵션 맞추기", "Set it up"),
                        t(
                            "왼쪽에서 바꾸면 오른쪽 미리보기가 바로 따라옵니다. 미리보기는 저장될 PNG를 그대로 줄인 그림이라, 보이는 그대로 저장됩니다.",
                            "Change anything on the left and the preview follows. The preview is the exported PNG, only smaller — what you see is what you get.",
                        ),
                    ),
                    (
                        t("저장 또는 복사", "Save or copy"),
                        t(
                            "**PNG 저장**은 프로젝트 폴더의 exports/ 에 시퀀스 이름으로 저장합니다. **클립보드에 복사**는 PureRef·Photoshop에 바로 붙여넣을 때 씁니다.",
                            "**Save PNG** writes it into the project's exports/ folder under the sequence name. **Copy to clipboard** is for pasting straight into PureRef or Photoshop.",
                        ),
                    ),
                ],
            ),
            Block("keys", ["export_contact_sheet", "export_markers"]),
            h(t("옵션", "The options")),
            p(
                t(
                    "**레이아웃** — 자동은 포즈 개수에 맞춰 가로·세로 비율이 보기 좋게 정해집니다. 2 × 3처럼 칸 수가 정해진 배치는 남는 칸을 점선으로 남겨 두고(인쇄해서 직접 그려 넣기 좋습니다), 포즈가 더 많으면 줄을 늘립니다. **가로 한 줄**은 타임라인처럼 쭉 늘어놓습니다.",
                    "**Layout** — Auto picks a pleasant width-to-height for the number of poses. A fixed grid like 2 × 3 keeps its empty slots as dotted outlines (handy to sketch into on paper) and adds rows when there are more poses. **One row** lays them out like a timeline.",
                )
            ),
            p(
                t(
                    "**칸 너비** — 한 칸의 가로 픽셀 수(240~1280). 완성될 크기는 미리보기 아래에 나옵니다.",
                    "**Cell width** — how many pixels wide one pose is (240–1280). The finished size is shown under the preview.",
                )
            ),
            p(
                t(
                    "**표시할 정보** — 번호, 카드 라벨·Phase 배지, 소스와 소스 프레임(F37), 타이밍(6f · 0.20s)과 애니 프레임(@7), 메모. **드로잉 포함**을 켜면 그 프레임에 그린 선과 가이드가 같이 합성됩니다.",
                    "**What to show** — number, card label/phase badge, source and source frame (F37), timing (6f · 0.20s) and anim frame (@7), notes. **Include drawings** composites that frame's strokes and guides onto the pose.",
                )
            ),
            p(
                t(
                    "**배경** — 밝게는 인쇄용입니다. 잉크를 덜 쓰고 종이에서 글씨가 또렷합니다.",
                    "**Background** — Light is for printing: less ink, crisper text on paper.",
                )
            ),
            tip(
                t(
                    "제목 칸을 비우면 머리글 없이 포즈 카드만 나옵니다. 그림만 필요할 때 쓰세요.",
                    "Clear the title box to drop the header and keep only the pose cards.",
                )
            ),
            h(t("Maya 마커", "Maya markers")),
            p(
                t(
                    "{a:export_markers} 키는 시퀀스의 타이밍을 파일로 저장합니다. 포즈마다 시작 프레임(시퀀스 시작 프레임 + 앞 포즈들의 Hold 합), 끝 프레임, 이름, Phase, 소스와 소스 프레임, 메모가 들어갑니다. JSON은 Maya용, CSV는 엑셀이나 다른 툴용입니다.",
                    "{a:export_markers} writes the sequence's timing to a file: each pose's start frame (the sequence start plus the holds before it), end frame, name, phase, source and source frame, and notes. JSON is for Maya, CSV for spreadsheets and other tools.",
                )
            ),
            Block("pre", _SAMPLE),
            h(t("Maya에 설치 (한 번만)", "Install in Maya (once)")),
            Block(
                "steps",
                [
                    (
                        t("install_aniref.mel 끌어다 놓기", "Drag install_aniref.mel in"),
                        t(
                            "aniREF 폴더 안 **maya** 폴더의 install_aniref.mel 을 Maya 뷰포트로 끌어다 놓습니다.",
                            "Drag install_aniref.mel from aniREF's **maya** folder into the Maya viewport.",
                        ),
                    ),
                    (
                        t("셸프 버튼 확인", "Check the shelf"),
                        t(
                            "지금 보고 있는 셸프에 **aniREF** 버튼이 생깁니다. 스크립트는 Maya 사용자 스크립트 폴더로 복사됩니다.",
                            "An **aniREF** button appears on the shelf you are on; the script is copied into your Maya scripts folder.",
                        ),
                    ),
                    (
                        t("마커 불러오기", "Import the markers"),
                        t(
                            "버튼을 누르고 내보낸 .json 을 고르면 포즈마다 Time Slider Bookmark가 Phase 색으로 생기고, 재생 범위가 시퀀스 길이에 맞춰집니다.",
                            "Press the button, pick the exported .json, and each pose becomes a Time Slider Bookmark in its phase color, with the playback range set to the sequence.",
                        ),
                    ),
                ],
            ),
            note(
                t(
                    "Maya 2020 이상이 필요합니다. 씬 fps가 프로젝트의 애니 fps와 다르면 먼저 물어봅니다. 같은 시퀀스를 다시 불러오면 이전 마커를 지우고 새로 만들고, 방금 만든 마커는 Maya에서 {k:Ctrl}+{k:Z} 키로 되돌릴 수 있습니다. 셸프 버튼을 오른쪽 클릭하면 aniREF 북마크 전체 지우기가 있습니다.",
                    "Maya 2020 or newer. If the scene fps differs from the project's anim fps it asks first. Re-importing the same sequence replaces its old markers, and {k:Ctrl}+{k:Z} in Maya undoes an import. Right-click the shelf button to remove all aniREF bookmarks.",
                )
            ),
            Block("links", ["project", "frames"]),
        ],
    )


register_page(48, _page)
