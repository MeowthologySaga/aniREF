"""User guide pages (Korean / English).

Pages are data; `help/window.py` renders them. Inline markup in text:
    {a:loop_in}          key cap of that action's current shortcut
    {k:Alt}              a literal key cap
    [[page_id|text]]     link to another page
    **bold**
Shortcuts are never typed out by hand, so the guide can't drift from the
real key bindings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from ..i18n import pick as t


@dataclass
class Block:
    kind: str  # h | p | steps | legend | keys | callout | figure | pre | links | roadmap | all_shortcuts
    data: object = None
    style: str = ""  # callout: tip | note | warn


@dataclass
class Page:
    id: str
    icon: str
    title: str
    summary: str
    blocks: list[Block] = field(default_factory=list)

    def plain_text(self) -> str:
        parts = [self.title, self.summary]
        for b in self.blocks:
            parts.append(_flatten(b.data))
        return strip_markup(" ".join(parts)).lower()


def _flatten(data) -> str:
    if isinstance(data, str):
        return data
    if isinstance(data, (list, tuple)):
        return " ".join(_flatten(x) for x in data)
    return ""


def strip_markup(text: str) -> str:
    text = re.sub(r"\[\[[^|\]]+\|([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"\{[ak]:([^}]+)\}", r"\1", text)
    return text.replace("**", "")


def h(text):
    return Block("h", text)


def p(text):
    return Block("p", text)


def tip(text):
    return Block("callout", text, "tip")


def note(text):
    return Block("callout", text, "note")


def warn(text):
    return Block("callout", text, "warn")


_BASE_ORDER = {
    "quickstart": 10,
    "layout": 20,
    "playback": 30,
    "loop": 40,
    "drawing": 44,
    "keyposes": 45,
    "ghosts": 46,
    "trails": 46.5,
    "frames": 50,
    "view": 60,
    "project": 70,
    "shortcuts": 90,
    "troubleshoot": 95,
    "roadmap": 99,
}
_EXTRA: list[tuple[float, Callable[[], Page]]] = []


def register_page(order: float, builder: Callable[[], Page]) -> None:
    """Feature modules add guide pages at import. `builder` runs at render time (current
    language). Base page orders: quickstart 10, layout 20, playback 30, loop 40, frames 50,
    view 60, project 70, shortcuts 90, troubleshoot 95, roadmap 99."""
    _EXTRA.append((order, builder))


def build_pages() -> list[Page]:
    ordered = [(_BASE_ORDER[p.id], p) for p in _base_pages()] + [(order, fn()) for order, fn in _EXTRA]
    return [p for _, p in sorted(ordered, key=lambda x: x[0])]


def _base_pages() -> list[Page]:
    return [
        Page(
            "quickstart",
            "sparkle",
            t("3분 시작 가이드", "3-minute quick start"),
            t(
                "영상 하나를 불러와 공격 모션을 프레임 단위로 뜯어보고 키포즈를 뽑기까지.",
                "From importing one video to studying an attack frame by frame and pulling its key poses.",
            ),
            [
                Block(
                    "steps",
                    [
                        (
                            t("영상 불러오기", "Import a video"),
                            t(
                                "레퍼런스 영상을 창에 끌어다 놓거나 {a:import_video} 키를 누릅니다. 여러 개를 한 번에 넣으면 위쪽에 탭으로 나란히 열립니다.",
                                "Drag a reference video into the window or press {a:import_video}. Drop several at once and each opens as a tab along the top.",
                            ),
                        ),
                        (
                            t("재생하고 멈추기", "Play and stop"),
                            t(
                                "{a:play_pause} 키로 재생하고 멈춥니다. 좋은 동작이 보이면 바로 멈추세요.",
                                "{a:play_pause} plays and stops. Stop as soon as you see a good moment.",
                            ),
                        ),
                        (
                            t("한 프레임씩 보기", "Step frame by frame"),
                            t(
                                "{a:step_back} / {a:step_fwd} 키로 1프레임씩 움직입니다. {a:step_back_5} / {a:step_fwd_5} 키는 5프레임, {a:step_back_10} / {a:step_fwd_10} 키는 10프레임. 타임라인을 클릭하거나 끌어도 됩니다.",
                                "{a:step_back} / {a:step_fwd} move one frame, {a:step_back_5} / {a:step_fwd_5} five and {a:step_back_10} / {a:step_fwd_10} ten. Clicking or dragging the timeline works too.",
                            ),
                        ),
                        (
                            t("공격 구간만 반복", "Loop just the attack"),
                            t(
                                "공격이 시작되는 프레임에서 {a:loop_in}, 끝나는 프레임에서 {a:loop_out} 키를 누르면 그 구간만 반복 재생됩니다.",
                                "Press {a:loop_in} where the attack starts and {a:loop_out} where it ends; playback now repeats just that range.",
                            ),
                        ),
                        (
                            t("느리게 보기", "Slow it down"),
                            t(
                                "{a:speed_down} / {a:speed_up} 키로 속도를 0.1x ~ 2x 사이에서 바꿉니다. 빠른 공격은 0.25x 루프로 보면 궤적이 잘 보여요.",
                                "{a:speed_down} / {a:speed_up} change speed between 0.1x and 2x. Fast attacks read best as a 0.25x loop.",
                            ),
                        ),
                        (
                            t("키포즈 뽑기", "Pull a key pose"),
                            t(
                                "좋은 프레임에서 {a:add_key_pose} 키를 누르면 오른쪽 라이브러리에 모입니다. 선택한 키포즈는 {a:add_to_sequence} 키로 아래 시퀀스 보드에 붙이세요.",
                                "On a frame you like press {a:add_key_pose}; it lands in the library on the right. Press {a:add_to_sequence} to put the selected poses on the sequence board below.",
                            ),
                        ),
                        (
                            t("저장", "Save"),
                            t(
                                "{a:save_project} 키로 프로젝트 폴더를 만들어 저장합니다. 다시 열면 보던 프레임과 루프 구간이 그대로 돌아옵니다.",
                                "{a:save_project} saves the project as a folder. Reopen it and each video returns to the frame and loop you left.",
                            ),
                        ),
                    ],
                ),
                tip(
                    t(
                        "단축키는 언제든 {a:shortcut_sheet} 한 번으로 볼 수 있어요.",
                        "See every shortcut any time with {a:shortcut_sheet}.",
                    )
                ),
                Block("links", ["layout", "playback", "loop", "keyposes"]),
            ],
        ),
        Page(
            "layout",
            "focus",
            t("화면 구성", "The main window"),
            t("각 영역이 하는 일.", "What each part of the window does."),
            [
                Block("figure", "layout"),
                Block(
                    "legend",
                    [
                        (
                            t("영상 탭", "Video tabs"),
                            t(
                                "프로젝트에 넣은 영상들. 클릭하거나 {a:next_source} 키로 전환합니다. 탭의 × 는 프로젝트에서 빼기만 하고 원본 파일은 그대로 둡니다.",
                                "The videos in this project. Click or use {a:next_source} to switch. A tab's × removes it from the project; the file stays.",
                            ),
                        ),
                        (
                            t("도구 막대", "Tool rail"),
                            t(
                                "위에서부터: 도구 — 포인터 {a:tool_pointer}, 펜 {a:tool_pen}, 직선 {a:tool_line}, 화살표 {a:tool_arrow}, 원 {a:tool_circle}, 지우개 {a:tool_eraser}, 궤적 {a:tool_trail}. 그 아래 색과 두께. 그다음 매 프레임 {a:guide_layer}, 보이기 {a:drawings_visible}, 프레임 지움 {a:clear_drawings}, Onion {a:onion_skin}, 실루엣 {a:silhouette}.\n"
                                "포인터와 마지막 그리기 도구를 오가는 키는 {a:draw_toggle}.",
                                "Top to bottom: the tools — pointer {a:tool_pointer}, pen {a:tool_pen}, line {a:tool_line}, arrow {a:tool_arrow}, circle {a:tool_circle}, eraser {a:tool_eraser}, trail {a:tool_trail}; then color and width; then All frames {a:guide_layer}, Show {a:drawings_visible}, Clear frame {a:clear_drawings}, Onion {a:onion_skin} and Silhouette {a:silhouette}.\n"
                                "Switch between the pointer and your last draw tool with {a:draw_toggle}.",
                            ),
                        ),
                        (
                            t("뷰어", "Viewer"),
                            t(
                                "현재 프레임과 그 위의 드로잉. 휠로 확대, 가운데 버튼(또는 {k:Alt} + 드래그)으로 이동, 더블클릭이나 {a:fit_view} 키로 화면 맞춤. 기본값이 아닌 보기(Mirror, Onion, 실루엣, 드로잉 숨김, 1x가 아닌 속도)는 왼쪽 위에 작은 표시로 계속 남습니다.",
                                "The current frame with its drawings. Wheel to zoom, middle-drag (or {k:Alt} + drag) to pan, double-click or {a:fit_view} to fit. Any view setting off its default (mirror, onion, silhouette, hidden drawings, a speed other than 1x) stays as a small tag at the top left.",
                            ),
                        ),
                        (
                            t("타임라인", "Timeline"),
                            t(
                                "눈금의 숫자는 프레임 번호입니다. 파란 표시가 현재 프레임, 회색 괄호 구간이 루프, ◆ 가 키포즈(Phase 색), ◆ 사이 숫자가 키포즈 간격, 그 아래 색 띠가 타이밍 구간({a:add_section}), 작은 점이 드로잉이 있는 프레임입니다.",
                                "Numbers are frame numbers: blue is the current frame, the grey bracket is the loop range, ◆ is a key pose (in its phase colour), the number between ◆ marks is the gap between key poses, the coloured band below is a timing section ({a:add_section}) and a small dot is a frame with drawings.",
                            ),
                        ),
                        (
                            t("재생 컨트롤", "Transport"),
                            t(
                                "재생, 1프레임 이동, 속도, 루프 시작·켜기·끝, Mirror, 화면 맞춤. 버튼 위에 마우스를 올리면 단축키가 보입니다.",
                                "Play, step, speed, loop in/on/out, mirror, fit. Hover any button to see its shortcut.",
                            ),
                        ),
                        (
                            t("시간 · 프레임", "Time · frame"),
                            t(
                                "현재 시간 / 전체 길이, 현재 프레임 번호(클릭해서 입력 가능), 원본 fps.",
                                "Current time / length, current frame (click to type one), source fps.",
                            ),
                        ),
                        (
                            t("키포즈 라이브러리", "Key pose library"),
                            t(
                                "{a:add_key_pose} 키로 뽑은 포즈가 모두 여기 모입니다. Phase 칩 · 영상 · 검색으로 거르고, 더블클릭하면 그 프레임으로 갑니다. "
                                "오른쪽 위 비교 보드 버튼({a:compare_mode})으로 Phase별로 나란히 봅니다.",
                                "Every pose you take with {a:add_key_pose} collects here. Filter by phase chip, video or search; double-click to jump to its frame. "
                                "The board button at its top right ({a:compare_mode}) lines poses up by phase.",
                            ),
                        ),
                        (
                            t("편집 칸", "Inspector"),
                            t(
                                "라이브러리에서 선택한 키포즈의 이름 · Phase · 태그 · 메모 · 앞발과 체중을 고칩니다. 이전 키포즈와의 간격도 여기 나옵니다. 키포즈가 생기면 나타납니다.",
                                "Edits the selected pose's name, phase, tags, notes, lead foot and weight, and shows the gap to the previous pose. It appears once there is a key pose.",
                            ),
                        ),
                        (
                            t("시퀀스 보드", "Sequence board"),
                            t(
                                "창 아래. 라이브러리의 포즈를 끌어다 놓거나 {a:add_to_sequence} 키로 붙여 순서와 타이밍(카드 사이 Hold)을 정하고, {a:flipbook} 키로 넘겨 봅니다. [[sequence|시퀀스 조합하기]]",
                                "Along the bottom. Drag poses in from the library or press {a:add_to_sequence}, set their order and timing (the hold between cards), and flip through them with {a:flipbook}. [[sequence|Building a sequence]]",
                            ),
                        ),
                    ],
                ),
                tip(
                    t(
                        "키를 누르면 뷰어 위쪽에 무엇이 바뀌었는지 잠깐 표시됩니다. 예: 루프 시작 F12",
                        "Each key press briefly shows what changed at the top of the viewer, e.g. Loop in F12.",
                    )
                ),
            ],
        ),
        Page(
            "playback",
            "play_outline",
            t("재생과 프레임 이동", "Playback and stepping"),
            t(
                "aniREF는 시간이 아니라 프레임 번호로 영상을 다룹니다.",
                "aniREF addresses video by frame number, not by time.",
            ),
            [
                p(
                    t(
                        "어느 프레임으로 가든 **항상 정확히 그 프레임**이 나옵니다. 일반 동영상 플레이어처럼 근처 프레임으로 튀지 않아요.",
                        "Whatever frame you go to, you get **exactly that frame** — never a nearby one like typical video players.",
                    )
                ),
                Block(
                    "keys",
                    [
                        "play_pause",
                        "step_back",
                        "step_fwd",
                        "step_back_5",
                        "step_fwd_5",
                        "step_back_10",
                        "step_fwd_10",
                        "step_back_custom",
                        "step_fwd_custom",
                        "first_frame",
                        "last_frame",
                        "go_to_frame",
                    ],
                ),
                h(t("프레임 번호로 바로 가기", "Jump to a frame number")),
                p(
                    t(
                        "재생 컨트롤 오른쪽의 프레임 칸을 클릭하거나 {a:go_to_frame} 키를 누르고, 번호를 입력한 뒤 {k:Enter}.",
                        "Click the frame box at the right of the transport or press {a:go_to_frame}, type a number, then {k:Enter}.",
                    )
                ),
                h(t("이동 간격", "Custom step")),
                p(
                    t(
                        "{a:step_fwd_custom} 키는 정해둔 프레임 수만큼 움직입니다. 2프레임 간격으로 포즈를 훑어볼 때 편해요. 재생 메뉴 → 이동 간격에서 2 · 3 · 4프레임 중에 고릅니다.",
                        "{a:step_fwd_custom} moves by a step you choose — handy for scanning poses on twos. Pick 2, 3 or 4 frames in Playback → Custom Step.",
                    )
                ),
                note(
                    t(
                        "재생 중에 프레임 이동 키를 누르면 재생이 멈추고 그 프레임에 섭니다.",
                        "Stepping while playing stops playback on that frame.",
                    )
                ),
                Block("links", ["loop", "frames"]),
            ],
        ),
        Page(
            "loop",
            "loop",
            t("루프와 재생 속도", "Loop and speed"),
            t(
                "동작 하나를 분석할 땐 그 구간만 반복해서 보는 게 가장 빠릅니다.",
                "To study one action, repeating just that range is fastest.",
            ),
            [
                Block(
                    "steps",
                    [
                        (t("시작 프레임에서", "At the first frame"), t("{a:loop_in} 키를 누릅니다.", "press {a:loop_in}.")),
                        (t("끝 프레임에서", "At the last frame"), t("{a:loop_out} 키를 누릅니다.", "press {a:loop_out}.")),
                        (
                            t("재생", "Play"),
                            t("{a:play_pause} — 구간 안에서만 반복됩니다.", "{a:play_pause} — it repeats inside the range."),
                        ),
                    ],
                ),
                Block("keys", ["loop_in", "loop_out", "loop_toggle", "loop_clear", "speed_down", "speed_up"]),
                p(
                    t(
                        "루프가 켜져 있으면 {a:first_frame} / {a:last_frame} 키는 영상의 처음·끝이 아니라 **루프의 시작·끝**으로 갑니다. 루프를 정하지 않으면 영상 전체가 반복됩니다.",
                        "With the loop on, {a:first_frame} / {a:last_frame} go to the **loop's** start and end. With no loop set, the whole video repeats.",
                    )
                ),
                tip(
                    t(
                        "빠른 공격은 0.25x 로 루프를 걸고, 궤적이 보이는 순간 멈춰서 1프레임씩 확인하세요.",
                        "Loop fast attacks at 0.25x, stop when the arc shows, then step frame by frame.",
                    )
                ),
                note(
                    t(
                        "루프 구간과 속도는 영상마다 따로 기억됩니다.",
                        "Loop range and speed are remembered per video.",
                    )
                ),
            ],
        ),
        Page(
            "drawing",
            "pen",
            t("영상 위에 그리기", "Drawing over frames"),
            t(
                "척추선, 무게중심, 검 궤적을 직접 그어 보면서 분석합니다.",
                "Draw the spine line, the balance point and the sword arc right on the frame.",
            ),
            [
                Block("keys", ["draw_toggle", "tool_pen", "tool_line", "tool_arrow", "tool_circle", "tool_eraser", "undo"]),
                p(
                    t(
                        "{a:draw_toggle} 키로 포인터와 그리기 도구를 오갑니다. 왼쪽 도구 막대에서 색과 두께를 고르세요. 그린 선은 **그 프레임에만** 남습니다.",
                        "{a:draw_toggle} switches between the pointer and your draw tool; pick color and width in the tool rail. A stroke belongs to **the frame you drew it on**.",
                    )
                ),
                h(t("모든 프레임에 남기는 가이드", "Guides on every frame")),
                p(
                    t(
                        "{a:guide_layer} 키로 켜고 그리면 그 영상의 **모든 프레임**에 보이는 선이 됩니다. 지면 높이, 기준선처럼 계속 봐야 하는 선에 쓰세요.",
                        "With {a:guide_layer} on, what you draw shows on **every frame** of that video — ground level, a height reference, anything you keep checking.",
                    )
                ),
                h(t("지우기", "Erasing")),
                p(
                    t(
                        "{a:tool_eraser} 키로 선 위를 지나가면 그 선이 통째로 지워집니다. {a:clear_drawings} 키는 현재 프레임의 선을 모두 지웁니다. 둘 다 {a:undo} 키로 되돌릴 수 있어요.",
                        "{a:tool_eraser} removes a whole stroke when you swipe over it; {a:clear_drawings} clears the frame. Both undo with {a:undo}.",
                    )
                ),
                tip(
                    t(
                        "직선({a:tool_line})이나 화살표({a:tool_arrow})를 그릴 때 {k:Shift} 키를 누르면 수평·수직·45°로 딱 맞춰집니다. 어깨축과 골반축을 비교할 때 좋습니다.",
                        "Hold {k:Shift} with {a:tool_line} / {a:tool_arrow} to snap to horizontal, vertical or 45° — handy for comparing shoulder and hip lines.",
                    )
                ),
                note(
                    t(
                        "Mirror를 켜면 그림도 같이 뒤집힙니다. 원본 영상 파일은 절대 바뀌지 않고, 그림은 프로젝트에 저장됩니다. {a:drawings_visible} 키로 잠시 숨길 수 있어요.",
                        "Mirroring flips the drawings with the image. The video file is never touched; strokes live in the project. Hide them for a moment with {a:drawings_visible}.",
                    )
                ),
                Block("links", ["keyposes"]),
            ],
        ),
        Page(
            "keyposes",
            "diamond",
            t("키포즈 뽑기", "Extracting key poses"),
            t(
                "마음에 드는 프레임을 출처와 함께 모아 둡니다.",
                "Collect the frames you like, with where they came from.",
            ),
            [
                Block(
                    "steps",
                    [
                        (
                            t("좋은 포즈에서 멈추기", "Stop on a good pose"),
                            t("루프와 슬로우로 찾은 그 프레임에서 멈춥니다.", "Loop and slow motion get you there; stop on the frame."),
                        ),
                        (
                            t("{a:add_key_pose} 누르기", "Press {a:add_key_pose}"),
                            t(
                                "현재 프레임이 원본 해상도 그대로 저장되고 오른쪽 라이브러리에 들어갑니다. {a:add_key_pose_phase} 키를 누르면 Phase를 고르면서 추가합니다.",
                                "The frame is saved at full resolution and lands in the library on the right. {a:add_key_pose_phase} lets you pick a phase while adding.",
                            ),
                        ),
                        (
                            t("Phase와 메모 붙이기", "Set a phase and a note"),
                            t(
                                "아래 편집 칸에서 Phase(Anticipation, Contact …), 태그, 메모를 씁니다. 나중에 \"왜 이 포즈를 골랐는지\"가 기억납니다.",
                                "In the inspector below set the phase (Anticipation, Contact …), tags and notes — later you'll remember why you picked it.",
                            ),
                        ),
                        (
                            t("다시 찾아보기", "Find it again"),
                            t(
                                "라이브러리에서 Phase 칩이나 검색으로 거르고, 포즈를 더블클릭하면 그 영상 그 프레임으로 바로 이동합니다.",
                                "Filter with the phase chips or search, and double-click a pose to jump back to that video and frame.",
                            ),
                        ),
                    ],
                ),
                Block("keys", ["add_key_pose", "add_key_pose_phase", "prev_key_pose", "next_key_pose", "delete_key_pose"]),
                h(t("Phase가 왜 중요한가", "Why the phase matters")),
                p(
                    t(
                        "Phase는 그 포즈가 모션에서 맡은 **역할**입니다. 같은 역할끼리 모아서 여러 영상을 비교하고, 제일 좋은 걸 골라 새 모션을 만들 때 기준이 됩니다. 색도 Phase마다 고정이라 타임라인·라이브러리·시퀀스에서 같은 의미로 보입니다.",
                        "A phase is the **role** a pose plays. Grouping by role is how you compare references and pick the best one for a new motion. Each phase keeps its color across the timeline, library and sequence.",
                    )
                ),
                tip(
                    t(
                        "타임라인의 ◆ 표시가 키포즈 위치입니다. {a:prev_key_pose} / {a:next_key_pose} 키로 키포즈 사이만 건너뛸 수 있어요.",
                        "The ◆ marks on the timeline are key poses; {a:prev_key_pose} / {a:next_key_pose} hop between them.",
                    )
                ),
                note(
                    t(
                        "키포즈 이미지는 프로젝트 폴더의 poses 안에 PNG로 저장됩니다. 드로잉은 이미지에 굽지 않고 따로 저장해서, 나중에 켜고 끌 수 있습니다.",
                        "Key pose images are PNGs in the project's poses folder. Drawings stay separate from the image, so you can turn them off later.",
                    )
                ),
                Block("links", ["drawing", "project"]),
            ],
        ),
        Page(
            "ghosts",
            "onion",
            t("Onion Skin · 실루엣", "Onion skin · silhouette"),
            t(
                "동작이 흘러가는 길과 포즈가 한눈에 읽히는지 확인하는 보기입니다.",
                "Views for seeing the path of a motion and whether a pose reads at a glance.",
            ),
            [
                Block("keys", ["onion_skin", "silhouette"]),
                h("Onion Skin"),
                p(
                    t(
                        "{a:onion_skin} 키로 켜면 현재 프레임 위에 앞뒤 프레임이 반투명하게 겹칩니다. **따뜻한 색이 이전 프레임, 차가운 색이 다음 프레임**입니다. 검끝 궤적, 팔이 지나가는 길, 골반 이동을 한 화면에서 볼 수 있어요.",
                        "{a:onion_skin} overlays the neighbouring frames on the current one. **Warm is earlier, cool is later.** Sword-tip arcs, the path of an arm and hip travel show up in one view.",
                    )
                ),
                p(
                    t(
                        "보기 → Onion Skin 설정에서 겹칠 프레임 수(앞뒤 1~3, 앞만, 뒤만)와 진하기를 고릅니다.",
                        "View → Onion Skin Settings picks how many frames to ghost (1–3 each side, before only, after only) and how strong.",
                    )
                ),
                note(
                    t(
                        "Onion Skin은 멈춰 있을 때 보입니다. 재생 중에는 부드러운 재생을 위해 잠시 빠집니다.",
                        "Ghosts show while paused; during playback they step aside to keep playback smooth.",
                    )
                ),
                h(t("실루엣 보기", "Silhouette view")),
                p(
                    t(
                        "{a:silhouette} 키를 누를 때마다 원본 → 고대비 → 실루엣 → 실루엣 반전 순서로 바뀝니다. 포즈를 흑백 덩어리로 보면 형태가 명확하게 읽히는지, 액션 라인이 살아 있는지 바로 보입니다.",
                        "{a:silhouette} cycles original → high contrast → silhouette → inverted silhouette. As a flat shape you see at once whether the pose reads and the line of action holds.",
                    )
                ),
                tip(
                    t(
                        "배경이 복잡하면 실루엣이 지저분할 수 있어요. 그럴 땐 반전이나 고대비를 써 보세요. 키포즈 이미지는 어떤 보기에서 뽑아도 원본으로 저장됩니다.",
                        "Busy backgrounds make messy silhouettes — try inverted or high contrast. Key pose images are always saved from the original frame.",
                    )
                ),
                Block("links", ["keyposes", "drawing"]),
            ],
        ),
        Page(
            "trails",
            "trail",
            t("궤적 · 타이밍 구간", "Motion trails · timing sections"),
            t(
                "검끝이 그리는 호, 골반이 전진한 거리, 동작의 구간별 프레임 수를 숫자로 봅니다.",
                "See the arc of a sword tip, how far the hips travel, and how many frames each part of a move takes.",
            ),
            [
                h(t("궤적 (Motion Trail)", "Motion trail")),
                Block(
                    "steps",
                    [
                        (
                            t("궤적 도구 켜기", "Pick the trail tool"),
                            t(
                                "{a:tool_trail} 키를 누르면 '검끝' 궤적이 만들어집니다. 다른 부위는 드로잉 메뉴 → 궤적 → 새 궤적에서 고르세요(골반, 발, 머리 …).",
                                "{a:tool_trail} starts a 'Sword tip' trail. Other body parts are in Draw → Motion Trail → New trail (pelvis, feet, head …).",
                            ),
                        ),
                        (
                            t("프레임마다 한 번 클릭", "One click per frame"),
                            t(
                                "따라갈 지점을 클릭하면 점이 찍히고 자동으로 다음 프레임으로 넘어갑니다. 계속 클릭만 하면 궤적이 그려집니다. {k:Shift} + 클릭은 그 프레임의 점을 지웁니다.",
                                "Click the point you're following; it's placed and the next frame comes up. Keep clicking and the trail draws itself. {k:Shift} + click removes that frame's point.",
                            ),
                        ),
                        (
                            t("숫자 읽기", "Read the numbers"),
                            t(
                                "뷰어 왼쪽 아래에 이동(영상 높이의 %), 가로·세로 이동, 최고 속도와 그 프레임, 시작점에서 최대 거리가 나옵니다. 골반 궤적이면 **Root Motion** 전진 거리, 검끝이면 **공격 범위와 가장 빠른 순간**입니다.",
                                "Bottom-left of the viewer: travel, horizontal / vertical movement (% of frame height), peak speed and its frame, and the farthest reach. On the pelvis that's your **root motion**; on the sword tip, **reach and the fastest moment**.",
                            ),
                        ),
                    ],
                ),
                tip(
                    t(
                        "캐릭터 크기가 영상마다 달라도 '영상 높이의 %'로 비교하면 전진 거리를 대략 맞춰 볼 수 있어요.",
                        "Characters are framed differently in each video; comparing '% of frame height' still lines up travel distances roughly.",
                    )
                ),
                h(t("타이밍 구간", "Timing sections")),
                p(
                    t(
                        "{a:loop_in} / {a:loop_out} 키로 범위를 잡고 {a:add_section} 키를 누르면 그 범위에 Phase(Anticipation, Attack …)를 붙인 구간이 타임라인 아래에 생깁니다. 루프가 없으면 앞 구간이 끝난 다음 프레임(앞 구간이 없으면 직전 키포즈)부터 현재 프레임까지가 구간이 되어, 구간들이 겹치지 않고 이어집니다. 구간 위에 마우스를 올리면 프레임 수, 초, 애니 fps 기준 길이가 보이고, 우클릭으로 Phase를 바꾸거나 지웁니다.",
                        "Set a range with {a:loop_in} / {a:loop_out} and press {a:add_section} to label it (Anticipation, Attack …) in a band under the timeline. Without a loop, it runs from the frame after the previous section (or from the previous key pose if there is none) to the current frame, so sections line up without overlapping. Hover a section for frames, seconds and anim-fps length; right-click to relabel or delete.",
                    )
                ),
                h(t("키포즈 사이 간격", "Gaps between key poses")),
                p(
                    t(
                        "타임라인의 ◆ 사이에 프레임 수가 표시됩니다. 편집 칸 미리보기 아래 줄에 이전 키포즈와의 간격(이전 +Nf)이 나옵니다. 영상 fps와 애니 fps가 다르면 애니 프레임으로 바꾼 값도 함께 보여 줍니다(마우스를 올리면 초). 60fps 레퍼런스의 7프레임은 30fps 씬에서 3.5프레임입니다.",
                        "The timeline shows frame counts between ◆ marks. The line under the inspector preview shows the gap to the previous key pose (prev +Nf); when the video and anim fps differ it adds the anim-frame value too (hover for seconds). 7 frames of a 60 fps reference are 3.5 in a 30 fps scene.",
                    )
                ),
                h(t("포즈 연결 검토", "Pose continuity")),
                p(
                    t(
                        "편집 칸의 **앞발 · 체중발** 표시로 포즈마다 어느 발이 앞인지, 체중이 어디 실렸는지 적어 두세요. 서로 다른 영상에서 포즈를 이어 붙일 때 발이 갑자기 바뀌는 곳을 찾기 쉬워집니다.",
                        "Mark **lead foot and weight** per pose in the inspector. When you stitch poses from different videos, a sudden foot switch is easy to spot.",
                    )
                ),
                Block("links", ["keyposes", "ghosts"]),
            ],
        ),
        Page(
            "frames",
            "clock",
            t("프레임 번호와 시간", "Frame numbers and time"),
            t("화면의 숫자를 읽는 법.", "How to read the numbers on screen."),
            [
                h(t("프레임 번호", "Frame numbers")),
                p(
                    t(
                        "기본적으로 **1부터** 셉니다. Maya 타임라인과 같아요. 0부터가 편하면 보기 → 프레임 번호 시작에서 바꿉니다. 이 설정은 프로젝트마다 저장됩니다.",
                        "Counting starts at **1** by default, like Maya's timeline. Switch to 0 in View → Frame Numbering; it's saved per project.",
                    )
                ),
                h(t("시간", "Time")),
                p(
                    t(
                        "00:01.233 은 첫 프레임부터 1.233초라는 뜻입니다. 각 프레임의 실제 시각을 그대로 씁니다.",
                        "00:01.233 means 1.233 s after the first frame, using each frame's real timestamp.",
                    )
                ),
                h(t("VFR 배지", "The VFR badge")),
                p(
                    t(
                        "게임 녹화 영상은 프레임 간격이 일정하지 않은 경우(가변 프레임레이트)가 많습니다. 그런 영상에는 **VFR** 배지가 붙습니다. 프레임 번호는 정확하니 그대로 쓰면 되고, 프레임 사이 시간이 조금씩 다를 수 있다는 점만 알아두세요.",
                        "Game captures often have uneven frame spacing (variable frame rate) and get a **VFR** badge. Frame numbers are still exact; only the time between frames may vary.",
                    )
                ),
                h(t("원본 fps와 애니 fps", "Source fps vs. animation fps")),
                p(
                    t(
                        "레퍼런스는 60fps, Maya 씬은 30fps인 경우가 많습니다. 60fps 레퍼런스의 7프레임은 30fps 기준 3.5프레임입니다. 키포즈 간격과 타이밍 구간은 두 값을 함께 보여줍니다([[trails|궤적 · 타이밍 구간]]). 지금 프로젝트의 애니 fps는 보기 → 애니 fps에서 바꿉니다(설정의 값은 새 프로젝트 기본값).",
                        "References are often 60 fps while the Maya scene is 30 fps: 7 frames at 60 are 3.5 at 30. Key pose gaps and timing sections show both ([[trails|Motion trails · timing sections]]). Change the open project's anim fps under View → Anim fps (Settings holds the default for new projects).",
                    )
                ),
            ],
        ),
        Page(
            "view",
            "pin",
            t("보기 · Maya 옆에서 쓰기", "View · working next to Maya"),
            t("확대, Mirror, 작은 창으로 띄워두기.", "Zoom, mirror, and a small always-on-top window."),
            [
                Block("keys", ["fit_view", "mirror", "focus_mode", "always_on_top", "next_source", "prev_source"]),
                h(t("확대와 이동", "Zoom and pan")),
                p(
                    t(
                        "마우스 휠로 커서 위치를 기준으로 확대합니다. 가운데 버튼 드래그나 {k:Alt} + 왼쪽 드래그로 화면을 옮기고, 더블클릭이나 {a:fit_view} 키로 되돌립니다.",
                        "The wheel zooms around the cursor. Middle-drag or {k:Alt} + left-drag pans; double-click or {a:fit_view} resets.",
                    )
                ),
                h("Mirror"),
                p(
                    t(
                        "오른쪽 공격 레퍼런스를 왼쪽 공격에 쓸 때 켭니다. 보기만 뒤집을 뿐 원본 파일은 바뀌지 않습니다.",
                        "Flip a right-handed reference for a left-handed attack. Only the view flips; the file is untouched.",
                    )
                ),
                h(t("Maya 옆에 띄워두기", "Keep it next to Maya")),
                p(
                    t(
                        "{a:focus_mode} 키로 뷰어와 재생 컨트롤만 남기고, {a:always_on_top} 키로 Maya 위에 떠 있게 하세요. 창을 작게 줄여 뷰포트 옆에 두면 됩니다.",
                        "{a:focus_mode} leaves only the viewer and transport; {a:always_on_top} keeps the window above Maya. Shrink it next to the viewport.",
                    )
                ),
            ],
        ),
        Page(
            "project",
            "folder",
            t("프로젝트와 파일", "Projects and files"),
            t("저장 방식과 동료와 공유하는 법.", "How saving works and how to share with teammates."),
            [
                p(t("프로젝트는 폴더 하나입니다.", "A project is a folder:")),
                Block(
                    "pre",
                    t(
                        "질풍참/\n  project.aniref    ← 프로젝트 파일 (더블클릭으로 열기)\n  poses/            ← 추출한 키포즈 이미지\n  exports/          ← 내보낸 Contact Sheet 등",
                        "DashSlash/\n  project.aniref    ← the project file (double-click to open)\n  poses/            ← extracted key pose images\n  exports/          ← contact sheets and other exports",
                    ),
                ),
                p(
                    t(
                        "**영상은 복사하지 않습니다.** 프로젝트에는 영상 위치만 적어 둡니다. 그래서 프로젝트는 가볍지만, 영상을 옮기면 다시 연결해야 할 수 있어요.",
                        "**Videos are never copied** — the project only records where they are. Projects stay small, but moved videos may need relinking.",
                    )
                ),
                h(t("저장 없이 바로 시작", "Start without saving")),
                p(
                    t(
                        "영상을 바로 열면 '제목 없음' 프로젝트로 시작합니다. {a:save_project} 키를 처음 누를 때 저장할 폴더를 정합니다.",
                        "Opening a video directly starts an Untitled project. The first {a:save_project} asks where to put the folder.",
                    )
                ),
                h(t("동료와 공유하기", "Sharing with teammates")),
                p(
                    t(
                        "프로젝트 폴더와 영상 폴더를 같은 상위 폴더에 두고 통째로 넘기면, 받는 사람 PC에서 경로가 달라도 자동으로 연결됩니다. 연결이 안 된 영상은 탭에 경고 표시와 **다시 연결** 버튼이 나타납니다.",
                        "Keep the project folder and the video folder under one parent and share that; links resolve automatically on another PC. Anything unresolved shows a warning with a **Relink** button.",
                    )
                ),
                tip(
                    t(
                        "저장할 때마다 직전 버전이 project.aniref.bak 으로 남습니다.",
                        "Every save keeps the previous version as project.aniref.bak.",
                    )
                ),
            ],
        ),
        Page(
            "shortcuts",
            "keyboard",
            t("단축키 전체", "All shortcuts"),
            t(
                "키보드만으로 분석할 수 있게 만들었습니다. {a:shortcut_sheet} 키로 언제든 한눈에 볼 수 있어요.",
                "Built for keyboard-first work. Press {a:shortcut_sheet} any time to see them all.",
            ),
            [Block("all_shortcuts")],
        ),
        Page(
            "troubleshoot",
            "help",
            t("문제 해결", "Troubleshooting"),
            t("자주 생기는 상황과 해결 방법.", "Common situations and what to do."),
            [
                h(t("영상이 열리지 않아요", "A video won't open")),
                p(
                    t(
                        "mp4, mov, mkv, avi, webm 등 대부분의 형식을 지원합니다. 다른 플레이어에서도 안 열리면 파일이 손상됐을 수 있어요. 다른 플레이어에서는 열린다면 문제 신고로 알려주세요.",
                        "Most formats work (mp4, mov, mkv, avi, webm…). If other players can't open it either, the file may be damaged; if they can, please report it.",
                    )
                ),
                h(t("크게 건너뛸 때 잠깐 멈칫해요", "Big jumps pause for a moment")),
                p(
                    t(
                        "유튜브 다운로드나 OBS 녹화처럼 키프레임 간격이 긴 영상은 타임라인을 멀리 건너뛸 때 0.1~0.3초 걸릴 수 있습니다. 1프레임 이동과 루프 재생은 캐시 덕분에 빠릅니다.",
                        "Videos with sparse keyframes (YouTube downloads, OBS captures) can take 0.1–0.3 s for long jumps. Stepping and loop playback stay fast thanks to caching.",
                    )
                ),
                h(t("처음 실행할 때 'Windows의 PC 보호' 창이 떠요", "\"Windows protected your PC\" on first launch")),
                p(
                    t(
                        "코드 서명이 없는 프로그램이라 나오는 경고입니다. **추가 정보 → 실행**을 누르면 됩니다.",
                        "The app isn't code-signed yet. Click **More info → Run anyway**.",
                    )
                ),
                h(t("단축키가 안 먹어요", "A shortcut does nothing")),
                p(
                    t(
                        "프레임 번호 칸 같은 입력칸에 커서가 있으면 입력이 우선합니다. 뷰어를 한 번 클릭하고 다시 눌러 보세요. 그래도 I, O, L 같은 글자 키가 안 되면 한/영 키로 영문 입력으로 바꿔 보세요.",
                        "If a text box has the cursor, typing wins — click the viewer and try again. If letter keys like I, O, L still fail, switch your keyboard input to English.",
                    )
                ),
                h(t("문제 신고", "Reporting a problem")),
                p(
                    t(
                        "도움말 → 로그 폴더 열기에서 aniref.log 를 찾아, 어떤 영상에서 무엇을 했는지와 함께 보내 주세요.",
                        "Open Help → Open log folder and send aniref.log along with what you did and which video.",
                    )
                ),
            ],
        ),
        Page(
            "roadmap",
            "layers",
            t("기능 현황", "Features"),
            t("지금 버전에서 되는 것과 앞으로 할 것.", "What works now and what's next."),
            [
                Block(
                    "roadmap",
                    [
                        (t("플레이어", "Player"), t("프레임 정확 재생, 루프, 슬로우, Mirror, 여러 영상 탭", "Frame-accurate playback, loop, slow motion, mirror, video tabs"), True),
                        (t("드로잉", "Drawing"), t("펜 · 직선 · 화살표 · 원, 프레임별 저장, 모든 프레임에 그리기", "Pen, line, arrow, circle; per-frame, draw on every frame"), True),
                        (t("키포즈 라이브러리", "Key pose library"), t("키 하나로 추출, Phase · 태그 · 메모 · 앞발/체중발, 필터와 검색", "Extract with one key; phase, tags, notes, lead foot / weight on; filter and search"), True),
                        (t("분석 보기", "Analysis views"), t("Onion Skin, 실루엣, Motion Trail(검끝 궤적 · 이동 거리 · 속도), 타이밍 구간", "Onion skin, silhouette, motion trails (arc, travel, speed), timing sections"), True),
                        (t("시퀀스 보드", "Sequence board"), t("드래그로 포즈 조합, 포즈 사이 타이밍, Flipbook 미리보기, 카드 줄 키보드 조작", "Drag poses into order, timing between poses, flipbook preview, keyboard on the card row"), True),
                        (t("비교 보드", "Comparison board"), t("행 = 영상, 열 = Phase, 열마다 골라 시퀀스로", "Rows = videos, columns = phases, pick one per column into a sequence"), True),
                        (t("내보내기", "Export"), t("Contact Sheet PNG, Maya 타임라인 마커", "Contact sheet PNG, Maya timeline markers"), True),
                        (t("내 애니메이션과 비교", "Compare with my animation"), t("레퍼런스와 내 애니메이션을 나란히 · 겹쳐 · 차이로 비교", "Reference vs your animation: side by side, overlay, difference"), True),
                        (t("설정", "Settings"), t("단축키 바꾸기, 자동 저장과 복구, 업데이트 알림", "Custom shortcuts, autosave & recovery, update notice"), True),
                        (t("그다음", "After that"), t("자동 포즈 인식, 자동 트래킹, 키포즈 후보 추천", "Automatic pose estimation, automatic tracking, key pose suggestions"), False),
                    ],
                ),
            ],
        ),
    ]
