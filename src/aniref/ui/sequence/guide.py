"""User guide page for the sequence board and the flipbook."""

from __future__ import annotations

from ..help.content import Block, Page, h, note, p, register_page, tip
from ..i18n import pick as t
from ..shortcuts import board_key_markup


def _page() -> Page:
    # The card row's keys, as the row dispatches them (shortcuts.BOARD_KEYS).
    k = {name: board_key_markup(f"seq_{name}") for name in (
        "select", "extend", "move", "hold", "edit_hold", "rename", "remove", "ends", "select_all", "leave")}
    return Page(
        "sequence",
        "seq_cards",
        t("시퀀스 조합하기", "Building a sequence"),
        t(
            "여러 영상에서 뽑은 키포즈를 한 줄로 세워 새 모션의 타이밍을 설계합니다.",
            "Line up key poses from different videos and design the timing of a new motion.",
        ),
        [
            Block(
                "steps",
                [
                    (
                        t("포즈 모으기", "Collect the poses"),
                        t(
                            "라이브러리에서 키포즈를 아래 보드로 끌어다 놓습니다. 놓는 위치가 순서를 정하고, 파란 세로선이 들어갈 자리를 알려줍니다. 여러 개를 골라 {a:add_to_sequence} 키를 누르면 맨 뒤에 붙습니다.",
                            "Drag key poses from the library onto the board below. Where you drop decides the order — the blue line shows the slot. Select several and press {a:add_to_sequence} to append them.",
                        ),
                    ),
                    (
                        t("순서 정하기", "Set the order"),
                        t(
                            f"카드를 끌어서 옮기거나, 카드 줄을 클릭한 뒤 {k['move']} 키로 한 칸씩 이동합니다. {k['rename']} 키로 카드 라벨을 바꾸고, {k['remove']} 키를 누르면 선택한 카드를 시퀀스에서 뺍니다 (포즈 자체는 라이브러리에 남습니다).",
                            f"Drag cards, or click the card row and move one slot at a time with {k['move']}. {k['rename']} renames a card's label; {k['remove']} takes the selected cards out of the sequence — the poses stay in the library.",
                        ),
                    ),
                    (
                        t("타이밍 잡기", "Time it"),
                        t(
                            f"카드 사이의 숫자(Hold)에 휠을 굴리면 ±1프레임, 클릭하면 직접 입력, 우클릭하면 2 · 3 · 4 · 6 · 8 · 12 프리셋이 나옵니다. 키보드로는 카드를 고르고 {k['hold']} 키로 ±1, {k['edit_hold']} 키로 숫자를 입력합니다.",
                            f"Scroll the number between cards (the hold) for ±1 frame, click it to type one, right-click for the 2 · 3 · 4 · 6 · 8 · 12 presets. From the keyboard, pick a card and press {k['hold']} for ±1 or {k['edit_hold']} to type a hold.",
                        ),
                    ),
                    (
                        t("넘겨 보기", "Flip through it"),
                        t(
                            "{a:flipbook} 키로 Flipbook을 열면 정한 타이밍 그대로 포즈가 넘어갑니다. 블로킹을 만들기 전에 리듬을 확인하세요.",
                            "{a:flipbook} opens the flipbook and plays the poses at exactly that timing — check the rhythm before you block anything.",
                        ),
                    ),
                    (
                        t("내보내기", "Export"),
                        t(
                            "Contact Sheet는 포즈와 타이밍을 한 장의 PNG로, Maya 마커는 타임라인에 꽂을 북마크로 내보냅니다.",
                            "Contact Sheet writes the poses and timing as one PNG; Maya markers become timeline bookmarks.",
                        ),
                    ),
                ],
            ),
            h(t("Hold — 다음 포즈까지 몇 프레임", "Hold — frames until the next pose")),
            p(
                t(
                    "카드 사이의 **6f**는 그 포즈를 애니 프레임 6개 동안 유지한다는 뜻입니다. 카드 아래 **@7**은 그 포즈가 놓이는 Maya 타임라인 프레임이고, 헤더의 **시작 @1** 값을 바꾸면 전부 같이 움직입니다. 마지막 카드의 Hold는 모션의 끝까지 유지할 길이입니다.",
                    "The **6f** between two cards means that pose is held for 6 anim frames. The **@7** under a card is the Maya timeline frame it lands on; change **Start @1** in the header and they all move together. The last card's hold is how long the motion holds at the end.",
                )
            ),
            note(
                t(
                    "보드의 Hold, Flipbook 재생, Contact Sheet의 길이, Maya 마커가 모두 같은 값에서 나옵니다. 한 곳만 고치면 전부 맞춰집니다.",
                    "The board's holds, flipbook playback, contact sheet durations and Maya markers all come from the same number — change it once and everything follows.",
                )
            ),
            h(t("원본 fps와 애니 fps", "Source fps vs. anim fps")),
            p(
                t(
                    "레퍼런스가 60fps이고 Maya 씬이 30fps면 원본 7프레임은 애니 3.5프레임입니다. 같은 영상에서 뽑은 포즈가 이웃해 있으면 Hold 아래에 **원본 7f→3.5f**처럼 환산값을 보여줍니다. 카드를 우클릭해 **원본 타이밍 적용**을 고르면 그 간격을 그대로 Hold에 넣습니다.",
                    "If the reference runs at 60 fps and the Maya scene at 30, 7 source frames are 3.5 anim frames. When two neighbouring cards come from the same video, the converted interval shows under the hold as **src 7f→3.5f**. Right-click a card and choose **Use reference timing** to copy it into the hold.",
                )
            ),
            tip(
                t(
                    "레퍼런스의 리듬을 먼저 그대로 복사한 다음, 게임에 맞게 앞뒤를 줄여 보세요. 애니 fps는 보기 → 애니 fps에서 바꿉니다. Hold는 애니 프레임 수 그대로 두고 초만 다시 계산합니다.",
                    "Copy the reference rhythm first, then tighten it for the game. Change the anim fps under View → Anim fps; holds keep their anim frame counts and only the seconds change.",
                )
            ),
            h(t("Flipbook", "Flipbook")),
            p(
                t(
                    "{a:play_pause} 재생 / 정지, {a:step_back} / {a:step_fwd} 이전 · 다음 포즈, {a:loop_toggle} 반복, {a:drawings_visible} 드로잉, {a:speed_down} / {a:speed_up} 속도(0.25 · 0.5 · 1x), {k:Esc} 닫기. 아래 색 막대는 포즈별 길이라서, 어디가 늘어지는지 한눈에 보입니다.",
                    "{a:play_pause} plays, {a:step_back} / {a:step_fwd} step poses, {a:loop_toggle} loops, {a:drawings_visible} toggles drawings, {a:speed_down} / {a:speed_up} change speed (0.25 · 0.5 · 1x), {k:Esc} closes. The colored bar shows each pose's length, so slack spots stand out.",
                )
            ),
            h(t("보드에서 쓰는 키", "Keys on the board")),
            p(
                t(
                    "카드 줄을 클릭하면 파란 테두리가 생기고, 그동안은 아래 키가 영상 대신 카드에 작동합니다.\n"
                    f"{k['select']} 카드 선택  ·  {k['extend']} 여러 개 선택  ·  {k['move']} 카드 옮기기  ·  {k['ends']} 처음 · 끝  ·  {k['select_all']} 모두 선택\n"
                    f"{k['hold']} Hold ±1  ·  {k['edit_hold']} Hold 입력  ·  {k['rename']} 라벨 편집  ·  {k['remove']} 시퀀스에서 빼기\n"
                    f"{k['leave']} 키를 누르면 키가 다시 영상(플레이어)에 작동합니다. 카드를 더블클릭하면 그 포즈의 원본 영상·프레임으로 이동합니다.",
                    "Click the card row and it gets a blue outline; while it has one, these keys work on the cards instead of the video.\n"
                    f"{k['select']} select cards  ·  {k['extend']} extend  ·  {k['move']} move cards  ·  {k['ends']} first / last  ·  {k['select_all']} select all\n"
                    f"{k['hold']} hold ±1  ·  {k['edit_hold']} type a hold  ·  {k['rename']} edit the label  ·  {k['remove']} remove from the sequence\n"
                    f"{k['leave']} hands the keys back to the player. Double-click a card to jump to its source video and frame.",
                )
            ),
            Block("keys", ["add_to_sequence", "flipbook"]),
            h(t("시퀀스 여러 개", "More than one sequence")),
            p(
                t(
                    "헤더의 목록에서 시퀀스를 고르고, **+** 로 새로 만들거나 복제 버튼으로 복사본을 만들어 다른 타이밍을 시험해 보세요. 삭제해도 {a:undo} 키로 되돌릴 수 있습니다.",
                    "Pick a sequence in the header list, add one with **+**, or duplicate it to try different timing. Deleting one is undoable with {a:undo}.",
                )
            ),
            Block("links", ["frames", "project"]),
        ],
    )


register_page(47, _page)
