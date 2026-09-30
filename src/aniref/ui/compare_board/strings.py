"""Comparison board text, icons, shortcut and guide page, registered at import."""

from __future__ import annotations

from .. import i18n, icons, shortcuts
from ..help.content import Block, Page, h, note, register_page, tip
from ..i18n import pick as t
from ..shortcuts import board_key_markup

i18n.register(
    {
        "act.compare_mode": ("비교 보드 열기 / 닫기", "Open / close comparison board"),
        "cmp.title": ("비교 보드", "Comparison Board"),
        "cmp.subtitle": (
            "영상 {sources}개  ·  키포즈 {poses}개  ·  Phase {phases}개",
            "{sources} videos  ·  {poses} key poses  ·  {phases} phases",
        ),
        "cmp.hidden_sources": ("  ·  키포즈 없는 영상 {n}개 숨김", "  ·  {n} videos without key poses hidden"),
        "cmp.back": ("플레이어로 돌아가기", "Back to player"),
        "cmp.corner": ("영상 ↓     Phase →", "Video ↓     Phase →"),
        "cmp.no_phase": ("Phase 없음", "No phase"),
        "cmp.unknown_source": ("(프로젝트에서 뺀 영상)", "(removed video)"),
        # -- controls --------------------------------------------------------------
        # KO: 고르다 for a FINAL pick, 선택 only for the grid's focused / selected card, so
        # "고른 포즈 없음" can sit next to a visibly selected card without contradicting it.
        # {keys} placeholders are filled from shortcuts.BOARD_KEYS["compare"].
        # The chips sit in the title row with no caption of their own, so the tooltip names them.
        "cmp.columns_tip": (
            "표시할 열\n클릭: 열 보이기 / 숨기기\n끌기: 순서 바꾸기  (보드에서 {keys} 키로도 옮길 수 있어요)",
            "Shown columns\nClick: show / hide a column\nDrag: reorder  (or {keys} on the board)",
        ),
        "cmp.columns_reset": ("기본 순서로", "Reset columns"),
        "cmp.all_origins": ("모든 출처", "All origins"),
        "cmp.no_origin": ("출처 없음", "No origin"),
        "cmp.all_tags": ("모든 태그", "All tags"),
        "cmp.origin_tip": ("출처(게임 이름 등)로 행 추리기", "Show only videos from one origin (game, etc.)"),
        "cmp.tag_tip": ("태그로 추리기 — 영상 태그나 키포즈 태그", "Filter by tag — video or key pose tags"),
        "cmp.notes": ("메모", "Notes"),
        "cmp.notes_tip": ("썸네일 아래에 키포즈 메모 보이기", "Show each pose's notes under its thumbnail"),
        # Ctrl + wheel stays words: it isn't a key the table can hold
        "cmp.size_tip": ("썸네일 크기  (Ctrl + 휠, {keys})", "Thumbnail size  (Ctrl + wheel, {keys})"),
        "cmp.clear": ("고른 것 모두 해제", "Clear picks"),
        "cmp.clear_tip": ("고른 포즈를 모두 해제", "Unpick every pose"),
        # -- grid ----------------------------------------------------------------------
        "cmp.final": ("FINAL", "FINAL"),
        "cmp.final_count": ("{n} / {total} 고름", "{n} / {total} picked"),
        # 'anim': next to a 60fps reference a bare '30fps' reads as the video's rate
        "cmp.final_timing": ("{frames}f  ·  {sec}s  ·  애니 {fps}fps", "{frames}f  ·  {sec}s  ·  anim {fps}fps"),
        "cmp.slot_empty": ("고른 포즈 없음", "Not picked"),
        # Rows below the fold, above the pinned FINAL row (the grid scrolls by whole rows).
        # Named: the same screen also counts key poses and picks.
        "cmp.more_rows": ("▼ 영상 {n}개 더", "▼ {n} more {videos}"),
        "cmp.video_one": ("영상", "video"),
        "cmp.video_many": ("영상", "videos"),
        "cmp.pick_tip": ("고르기 / 해제  ({keys})", "Pick / unpick  ({keys})"),
        "cmp.pose_tip": (
            "클릭: 크게 보기   ·   더블클릭: 플레이어에서 보기",
            "Click: preview   ·   Double-click: open in player",
        ),
        "cmp.menu_pick": ("이 포즈 고르기", "Pick this pose"),
        "cmp.menu_unpick": ("고르기 취소", "Unpick"),
        "cmp.no_match": ("조건에 맞는 키포즈가 없습니다", "No key poses match"),
        "cmp.no_match_body": ("위쪽 출처 · 태그 필터를 '모든 …'으로 바꿔 보세요.", "Set the origin and tag filters above back to 'All'."),
        "cmp.all_hidden": ("모든 열을 숨겼습니다", "Every column is hidden"),
        "cmp.all_hidden_body": ("위쪽 Phase 칩을 눌러 다시 보이게 하세요.", "Click a phase chip above to show it again."),
        # -- footer --------------------------------------------------------------------
        "cmp.make": ("시퀀스로 만들기", "Make sequence"),
        "cmp.make_tip": (
            "고른 포즈를 열 순서대로 새 시퀀스로 만듭니다 (포즈마다 6f)  ({keys})",
            "Make a new sequence from the picks in column order (6f each)  ({keys})",
        ),
        "cmp.append": ("현재 시퀀스에 추가", "Add to current sequence"),
        "cmp.append_to": ("'{name}' 뒤에 추가", "Add to '{name}'"),
        "cmp.append_tip": ("고른 포즈를 '{name}' 끝에 붙입니다", "Append the picks to the end of '{name}'"),
        "cmp.append_tip_new": ("열린 시퀀스가 없어서 새로 만듭니다", "No sequence is open, so this makes a new one"),
        "cmp.need_picks": ("먼저 포즈를 고르세요 — 썸네일의 체크 또는 {keys}", "Pick poses first — a thumbnail's check or {keys}"),
        "cmp.key_move": ("이동", "move"),
        "cmp.key_pick": ("고르기", "pick"),
        "cmp.key_open": ("플레이어에서 보기", "open in player"),
        "cmp.key_back": ("플레이어로", "back to player"),
        # -- sequences -----------------------------------------------------------------
        "cmp.seq_name": ("고른 포즈 {n}", "Picks {n}"),
        "cmp.cmd_make": ("비교 보드에서 시퀀스 만들기", "make sequence from picks"),
        "cmp.cmd_append": ("시퀀스에 포즈 추가", "add poses to sequence"),
        # -- feedback ------------------------------------------------------------------
        "cmp.osd_picked": ("✓  {phase}  ·  {source} {frame}", "✓  {phase}  ·  {source} {frame}"),
        "cmp.osd_replaced": ("✓  {phase} 고른 포즈를 바꿨습니다  ·  {source} {frame}", "✓  {phase} pick changed  ·  {source} {frame}"),
        "cmp.osd_unpicked": ("고르기 취소  ·  {phase}", "Unpicked  ·  {phase}"),
        "cmp.osd_cleared": ("고른 것을 모두 해제했습니다", "All picks cleared"),
        "cmp.osd_made": ("시퀀스 '{name}' 만들었습니다  ·  키포즈 {n}개", "Made sequence '{name}'  ·  {n} key poses"),
        "cmp.osd_appended": ("'{name}'에 키포즈 {n}개 추가", "Added {n} key poses to '{name}'"),
        "cmp.osd_hidden": ("{phase} 열 숨김", "{phase} column hidden"),
        "cmp.osd_shown": ("{phase} 열 보이기", "{phase} column shown"),
        "cmp.osd_moved": ("{phase} 열 이동", "Moved the {phase} column"),
        "cmp.osd_reset": ("열을 기본 순서로 되돌렸습니다", "Columns reset"),
        "cmp.osd_size": ("썸네일 {n}px", "Thumbnails {n}px"),
        # -- empty states / hints ------------------------------------------------------
        "cmp.empty.title": ("아직 비교할 키포즈가 없습니다", "No key poses to compare yet"),
        "cmp.empty.body": (
            "플레이어에서 좋은 프레임을 찾아 키포즈로 뽑으세요.\n"
            "Phase(Anticipation, Contact …)를 정해 두면 여기서 Phase별로 레퍼런스끼리 나란히 비교하고, 가장 좋은 것만 골라 시퀀스로 만들 수 있어요.",
            "Find good frames in the player and extract them as key poses.\n"
            "Give them a phase (Anticipation, Contact …) and this board lines them up by phase across references, "
            "so you can pick the best of each and turn them into a sequence.",
        ),
        "cmp.empty.add": ("키포즈 추가", "add key pose"),
        "cmp.empty.add_phase": ("Phase 골라서 추가", "add with a phase"),
        "cmp.hint.one_source": (
            "영상이 하나뿐이에요. 레퍼런스를 여러 개 넣고 키포즈를 뽑으면, 같은 Phase의 포즈를 영상끼리 나란히 비교할 수 있습니다.",
            "Only one video so far. Add more references and extract their key poses to compare the same phase side by side.",
        ),
        "cmp.hint.no_phase": (
            "아직 Phase를 정한 키포즈가 없어서 한 열로만 보입니다. 키포즈에 Phase를 정하면 Phase별 열로 나뉩니다 ({key}: Phase 골라서 추가).",
            "No key pose has a phase yet, so everything sits in one column. Give poses a phase to split them by phase ({key}: add with a phase).",
        ),
        # -- preview -------------------------------------------------------------------
        "cmp.preview": ("미리보기", "Preview"),
        "cmp.preview_empty": (
            "포즈를 클릭하면 여기서 크게 봅니다.\n더블클릭하면 플레이어의 그 프레임으로 갑니다.",
            "Click a pose to see it large here.\nDouble-click to open that frame in the player.",
        ),
        "cmp.info_source": ("영상", "Video"),
        "cmp.info_origin": ("출처", "Origin"),
        "cmp.info_frame": ("프레임", "Frame"),
        "cmp.info_tags": ("태그", "Tags"),
        "cmp.no_notes": ("메모 없음", "No notes"),
        "cmp.mirrored": ("Mirror 켜짐", "Mirrored"),
        "cmp.pick": ("이 포즈 고르기", "Pick this pose"),
        "cmp.unpick": ("고르기 취소", "Unpick"),
        "cmp.picked_badge": ("✓ 이 열에서 고름", "✓ Picked for this column"),
        "cmp.jump": ("플레이어에서 보기", "Open in player"),
        "cmp.jump_tip": ("이 프레임을 플레이어에서 엽니다  (더블클릭, {keys})", "Open this frame in the player  (double-click, {keys})"),
        "cmp.missing_image": ("이미지 없음", "No image"),
        # -- keys of the grid (shortcuts.BOARD_KEYS["compare"]) ------------------------------
        "grp.compare": ("비교 보드 (열려 있을 때)", "Comparison board (while it is open)"),
        "boardkey.cmp_move": ("포즈 사이 이동", "Move between poses"),
        "boardkey.cmp_pick": ("고르기 / 해제", "Pick / unpick"),
        "boardkey.cmp_open": ("플레이어에서 보기", "Open in the player"),
        "boardkey.cmp_make": ("시퀀스로 만들기", "Make a sequence"),
        "boardkey.cmp_column": ("선택한 열 옮기기", "Move the current column"),
        "boardkey.cmp_size": ("썸네일 작게 / 크게", "Smaller / larger thumbnails"),
        "boardkey.cmp_back": ("플레이어로 돌아가기", "Back to the player"),
    }
)

_STROKE = 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
icons.register(
    {
        "cmp_board": f'<g {_STROKE}><rect x="3" y="4" width="7.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="7.5" height="6.5" rx="1.5"/>'
        '<rect x="3" y="13.5" width="7.5" height="6.5" rx="1.5"/><path d="M14 17l2.5 2.5L21 14.5"/></g>',
        "cmp_check": f'<g {_STROKE} stroke-width="2.6"><path d="M5.5 12.5l4.2 4.2L18.5 7.5"/></g>',
        "cmp_back": f'<g {_STROKE}><path d="M14.5 6l-6 6 6 6"/></g>',
        "cmp_notes": f'<g {_STROKE}><path d="M5 6.5h14M5 12h14M5 17.5h9"/></g>',
        "cmp_sequence": f'<g {_STROKE}><rect x="2.5" y="7" width="5.5" height="10" rx="1.2"/><rect x="16" y="7" width="5.5" height="10" rx="1.2"/>'
        '<path d="M9.5 12h5"/><path d="M12.5 10l2 2-2 2"/></g>',
    }
)

shortcuts.register([shortcuts.Shortcut("compare_mode", ("C",), "view")])


def _guide_page() -> Page:
    # The grid's keys, as it dispatches them (shortcuts.BOARD_KEYS["compare"]).
    k = {name: board_key_markup(f"cmp_{name}", "compare") for name in (
        "move", "pick", "open", "make", "column", "size", "back")}
    return Page(
        "compare",
        "cmp_board",
        t("비교 보드", "Comparison board"),
        t(
            "같은 Phase의 포즈를 레퍼런스끼리 나란히 놓고, 열마다 가장 좋은 것 하나를 골라 시퀀스로 만듭니다.",
            "Line up poses with the same phase across references, pick the best one per column and turn the picks into a sequence.",
        ),
        [
            Block(
                "steps",
                [
                    (
                        t("키포즈에 Phase 정하기", "Give key poses a phase"),
                        t(
                            "플레이어에서 {a:add_key_pose} 키로 키포즈를 뽑고 Phase(Anticipation, Contact …)를 정합니다. "
                            "{a:add_key_pose_phase} 키를 쓰면 뽑으면서 바로 고를 수 있어요.",
                            "Extract key poses in the player with {a:add_key_pose} and give each a phase (Anticipation, Contact …). "
                            "{a:add_key_pose_phase} lets you choose the phase as you extract.",
                        ),
                    ),
                    (
                        t("비교 보드 열기", "Open the board"),
                        t(
                            "{a:compare_mode} 키를 누릅니다. **행은 영상, 열은 Phase** — 같은 Phase의 포즈가 한 열에 모여서 레퍼런스끼리 바로 비교됩니다.",
                            "Press {a:compare_mode}. **Rows are videos, columns are phases** — poses with the same phase share a column.",
                        ),
                    ),
                    (
                        t("열마다 하나씩 고르기", "Pick one per column"),
                        t(
                            f"썸네일의 체크를 누르거나 {k['pick']}. 열마다 하나만 고를 수 있어서 다른 포즈를 고르면 고른 포즈가 바뀝니다. "
                            "고른 포즈는 맨 아래 **FINAL** 줄에 열 순서대로 모입니다.",
                            f"Click a thumbnail's check or press {k['pick']}. Each column holds one pick, so picking another pose swaps it. "
                            "Picks line up in the **FINAL** row at the bottom, in column order.",
                        ),
                    ),
                    (
                        t("시퀀스로 만들기", "Make a sequence"),
                        t(
                            f"**시퀀스로 만들기**({k['make']})를 누르면 FINAL 순서 그대로 새 시퀀스가 생깁니다. "
                            "포즈마다 6프레임씩 잡혀 있으니 시퀀스 보드에서 타이밍을 다듬으세요. "
                            "**'<시퀀스 이름>' 뒤에 추가** 버튼은 지금 열린 시퀀스 끝에 붙입니다(열린 시퀀스가 없으면 새로 만듭니다).",
                            f"**Make sequence** ({k['make']}) creates a new sequence in FINAL order, 6 frames per pose — "
                            "refine the timing on the Sequence Board. **Add to '<sequence name>'** appends to the open sequence (or makes one if none is open).",
                        ),
                    ),
                ],
            ),
            Block("keys", ["compare_mode"]),
            h(t("보드 다루기", "Working the board")),
            Block(
                "legend",
                [
                    (
                        t("키보드", "Keyboard"),
                        t(
                            f"{k['move']} 키로 포즈를 옮겨 다니고 {k['pick']} 키로 고릅니다. "
                            f"{k['open']} 키나 더블클릭은 플레이어의 그 프레임으로 갑니다. "
                            f"{k['back']} 키는 플레이어로 돌아갑니다. 고른 것은 그대로 남아요.",
                            f"{k['move']} move between poses; {k['pick']} picks. "
                            f"{k['open']} or a double-click opens that frame in the player. "
                            f"{k['back']} returns to the player; your picks stay.",
                        ),
                    ),
                    (
                        t("열 보이기와 순서", "Showing and ordering columns"),
                        t(
                            "위쪽 Phase 칩을 누르면 그 열을 숨기거나 다시 보이고, 끌면 순서가 바뀝니다. "
                            f"보드에서 {k['column']} 키로 선택한 열을 좌우로 옮길 수도 있어요. FINAL과 시퀀스도 이 순서를 따릅니다.",
                            "Click a phase chip above the board to hide or show its column; drag chips to reorder. "
                            f"{k['column']} moves the current column. FINAL and the sequence follow this order.",
                        ),
                    ),
                    (
                        t("필터", "Filters"),
                        t(
                            "출처(게임 이름 등)나 태그로 보이는 포즈를 추립니다. 이미 고른 포즈는 필터와 상관없이 FINAL에 남아요.",
                            "Narrow the rows by origin (game, …) or tag. Picks stay in FINAL whatever the filter.",
                        ),
                    ),
                    (
                        t("크기와 메모", "Size and notes"),
                        t(
                            f"슬라이더나 {{k:Ctrl}} + 휠, {k['size']} 키로 썸네일 크기를 바꿉니다. **메모**를 켜면 포즈마다 적어 둔 메모가 썸네일 아래에 보입니다.",
                            f"Change thumbnail size with the slider, {{k:Ctrl}} + wheel or {k['size']}. Turn on **Notes** to show each pose's notes.",
                        ),
                    ),
                ],
            ),
            tip(
                t(
                    "고른 포즈는 보드를 닫았다 열어도 그대로입니다. 프로젝트 파일에는 저장되지 않으니, 마음에 들면 시퀀스로 만들어 두세요.",
                    "Picks survive closing and reopening the board, but they aren't saved in the project — make a sequence to keep them.",
                )
            ),
            note(
                t(
                    "영상이 하나여도 쓸 수 있지만, 여러 레퍼런스를 넣었을 때 진가가 나옵니다.",
                    "It works with a single video, but it shines with several references.",
                )
            ),
            Block("links", ["shortcuts"]),
        ],
    )


register_page(55, _guide_page)
