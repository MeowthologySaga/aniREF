"""Sequence board / flipbook text, shortcuts and icons (registered at import),
plus the small formatters for timing text shown on cards, the header and the flipbook."""

from __future__ import annotations

from .. import i18n, icons, shortcuts
from ..i18n import tr
from ..shortcuts import Shortcut

i18n.register(
    {
        "act.add_to_sequence": ("선택한 키포즈를 시퀀스에 추가", "Add selected key poses to the sequence"),
        "act.flipbook": ("Flipbook 미리보기", "Flipbook preview"),
        # -- board header ----------------------------------------------------------
        "seq.dock": ("시퀀스 보드", "Sequence Board"),
        "seq.title": ("시퀀스", "Sequence"),
        "seq.default_name": ("시퀀스 {n}", "Sequence {n}"),
        "seq.copy_name": ("{name} 사본", "{name} copy"),
        "seq.none": ("시퀀스 없음", "No sequence"),
        "seq.combo_tip": ("작업할 시퀀스 고르기", "Choose the sequence to work on"),
        "seq.new_tip": ("새 시퀀스", "New sequence"),
        "seq.rename_tip": ("시퀀스 이름 바꾸기", "Rename sequence"),
        "seq.duplicate_tip": ("시퀀스 복제", "Duplicate sequence"),
        "seq.delete_tip": ("시퀀스 삭제 (되돌리기 가능)", "Delete sequence (undoable)"),
        "seq.start": ("시작", "Start"),
        "seq.start_tip": (
            "첫 포즈가 놓일 애니 프레임 (Maya 타임라인)\n휠로 바꾸거나 숫자 입력 후 Enter",
            "Anim frame of the first pose (Maya timeline)\nScroll, or type a number and press Enter",
        ),
        # '@N' is only ever a Maya timeline position (card footers, the start field);
        # a rate is written '30fps'.
        # "애니" names the fps: next to the transport's source-fps badge a bare "30fps" read as the video's rate.
        "seq.total": ("총 <b>{frames}f</b> · {secs}s · 애니 {fps}fps", "Total <b>{frames}f</b> · {secs}s · anim {fps}fps"),
        "seq.total_tip": (
            "마지막 포즈의 Hold까지 더한 길이입니다. Hold는 애니 fps 기준 프레임입니다.",
            "Length including the last pose's hold. Holds count anim frames.",
        ),
        "seq.btn.flipbook": ("Flipbook", "Flipbook"),
        "seq.btn.contact": ("Contact Sheet", "Contact Sheet"),
        "seq.btn.markers": ("Maya 마커", "Maya markers"),
        "seq.contact_tip": ("이 시퀀스를 한 장의 PNG로 내보내기", "Export this sequence as one PNG"),
        "seq.markers_tip": ("Maya 타임라인 마커(JSON / CSV)로 내보내기", "Export as Maya timeline markers (JSON / CSV)"),
        "seq.dlg.rename.title": ("시퀀스 이름", "Sequence name"),
        "seq.dlg.rename.body": ("새 이름", "New name"),
        # -- cards and holds ---------------------------------------------------------
        "seq.frames": ("{n}f", "{n}f"),
        "seq.secs": ("{s}s", "{s}s"),
        "seq.card.missing_image": ("이미지 없음", "No image"),
        "seq.card.missing_pose": ("삭제된 키포즈", "Deleted key pose"),
        "seq.card.no_source": ("영상 없음", "No video"),
        "seq.card.span": ("애니 @{a} – @{b}  ({hold}f)", "Anim @{a} – @{b}  ({hold}f)"),
        "seq.card.at": ("Maya {n}프레임", "Maya frame {n}"),
        "seq.card.help": (
            "더블클릭: 이 프레임으로 이동  ·  끌기: 순서 변경  ·  {key}: 라벨",
            "Double-click: go to frame  ·  Drag: reorder  ·  {key}: label",
        ),
        "seq.card.mirrored": ("Mirror", "Mirrored"),
        "seq.hold.tip": ("다음 포즈까지 {hold}f  ({secs}s · {fps}fps)", "{hold}f until the next pose  ({secs}s · {fps}fps)"),
        "seq.hold.tip_last": ("마지막 포즈 유지 {hold}f  ({secs}s · {fps}fps)", "Last pose held {hold}f  ({secs}s · {fps}fps)"),
        "seq.hold.ref": ("원본 {f}f", "src {f}f"),
        # when the video's fps isn't the anim fps: both counts, so '3.5f' can't pass for
        # 3.5 source frames
        "seq.hold.ref_conv": ("원본 {src}f→{f}f", "src {src}f→{f}f"),
        "seq.hold.ref_tip": ("원본 {src}f ({sfps}fps) = {anim}f ({afps}fps)", "Source {src}f ({sfps}fps) = {anim}f ({afps}fps)"),
        "seq.hold.help": ("휠: ±1  ·  클릭: 숫자 입력  ·  우클릭: 프리셋", "Wheel: ±1  ·  Click: type  ·  Right-click: presets"),
        "seq.ghost": ("끌어다 놓기", "Drop here"),
        "seq.drop": ("놓아서 시퀀스에 추가", "Drop to add to the sequence"),
        # -- menus -----------------------------------------------------------------
        "seq.menu.label": ("라벨 편집…", "Edit label…"),
        "seq.menu.hold": ("Hold", "Hold"),
        "seq.menu.hold_type": ("직접 입력…", "Type a value…"),
        "seq.menu.ref_timing": ("원본 타이밍 적용  ({anim}f → {n}f)", "Use reference timing  ({anim}f → {n}f)"),
        "seq.menu.jump": ("이 프레임으로 이동", "Go to frame"),
        "seq.menu.remove": ("시퀀스에서 빼기", "Remove from sequence"),
        # -- empty state -----------------------------------------------------------
        "seq.empty.title": ("키포즈를 여기로 끌어다 놓으세요", "Drag key poses here"),
        "seq.empty.body": (
            "여러 영상에서 고른 포즈를 순서대로 놓아 새 모션을 만듭니다. 카드 사이 숫자(Hold)는 다음 포즈까지의 애니 프레임 수입니다.",
            "Line up poses from different videos to build a new motion. The number between cards (the hold) is how many anim frames until the next pose.",
        ),
        "seq.empty.key_hint": ("라이브러리에서 선택한 키포즈를 바로 추가", "adds the key poses selected in the library"),
        "seq.empty.no_project": ("영상을 열고 키포즈를 뽑으면 여기서 조합합니다", "Open a video and extract key poses to combine them here"),
        # a project with no key poses yet: the viewer's "drop a video" is the only call to action
        "seq.empty.no_poses": ("키포즈를 뽑으면 여기서 순서와 타이밍을 짭니다", "Once you capture key poses, order and time them here"),
        # -- feedback ----------------------------------------------------------------
        "seq.osd.added": ("'{name}'에 {n}개 추가  ·  @{frame}", "Added {n} to '{name}'  ·  @{frame}"),
        "seq.osd.created": ("새 시퀀스 '{name}'", "New sequence '{name}'"),
        "seq.osd.nothing_selected": ("추가할 키포즈를 먼저 라이브러리에서 선택하세요", "Select key poses in the library first"),
        "seq.osd.removed": ("시퀀스에서 {n}개 뺌  ·  {undo} 키로 되돌리기", "Removed {n} from the sequence  ·  {undo} to undo"),
        "seq.osd.deleted": ("시퀀스 '{name}' 삭제  ·  {undo} 키로 되돌리기", "Deleted '{name}'  ·  {undo} to undo"),
        "seq.osd.hold": ("Hold {hold}f  ·  {secs}s", "Hold {hold}f  ·  {secs}s"),
        "seq.osd.moved": ("순서 변경", "Reordered"),
        "seq.osd.keys_back": ("키가 플레이어로 돌아갑니다", "Keys back to the player"),
        "seq.osd.no_poses": ("시퀀스에 포즈가 없습니다  ·  {key} 키로 추가", "No poses in the sequence  ·  add some with {key}"),
        # -- undo texts --------------------------------------------------------------
        "seq.cmd.add_items": ("시퀀스에 추가", "add to sequence"),
        "seq.cmd.remove_items": ("시퀀스에서 빼기", "remove from sequence"),
        "seq.cmd.move_items": ("시퀀스 순서 변경", "reorder sequence"),
        "seq.cmd.hold": ("Hold 변경", "change hold"),
        "seq.cmd.label": ("카드 라벨 변경", "change card label"),
        "seq.cmd.add_seq": ("새 시퀀스", "new sequence"),
        "seq.cmd.duplicate": ("시퀀스 복제", "duplicate sequence"),
        "seq.cmd.remove_seq": ("시퀀스 삭제", "delete sequence"),
        "seq.cmd.rename_seq": ("시퀀스 이름 변경", "rename sequence"),
        "seq.cmd.start": ("시작 프레임 변경", "change start frame"),
        # -- flipbook ----------------------------------------------------------------
        "seq.fb.title": ("Flipbook — {name}", "Flipbook — {name}"),
        "seq.fb.prev": ("이전 포즈", "Previous pose"),
        "seq.fb.next": ("다음 포즈", "Next pose"),
        "seq.fb.first": ("처음으로", "To the first pose"),
        "seq.fb.loop": ("반복", "Loop"),
        "seq.fb.drawings": ("드로잉 보이기", "Show drawings"),
        "seq.fb.speed_tip": ("재생 속도", "Playback speed"),
        "seq.fb.close": ("닫기", "Close"),
        "seq.fb.loop_on": ("반복 켜짐", "Loop on"),
        "seq.fb.loop_off": ("반복 꺼짐 · 마지막 포즈에서 멈춤", "Loop off · stops on the last pose"),
        "seq.fb.drawings_on": ("드로잉 표시됨", "Drawings shown"),
        "seq.fb.drawings_off": ("드로잉 숨김", "Drawings hidden"),
        # frames against frames, seconds against seconds
        "seq.fb.readout": ("@{frame} / @{last}  ·  {secs}s / {total_secs}s", "@{frame} / @{last}  ·  {secs}s / {total_secs}s"),
        "seq.fb.empty": ("이 시퀀스에는 아직 포즈가 없습니다", "This sequence has no poses yet"),
        "seq.fb.bar_tip": ("클릭하거나 끌어서 이동", "Click or drag to scrub"),
        # -- keys of the card row (shortcuts.BOARD_KEYS) --------------------------------
        "grp.sequence": ("시퀀스 보드 (카드 줄을 클릭한 뒤)", "Sequence board (after clicking the cards)"),
        "boardkey.seq_select": ("카드 선택", "Select a card"),
        "boardkey.seq_extend": ("선택 넓히기", "Extend the selection"),
        "boardkey.seq_move": ("카드 옮기기", "Move cards"),
        "boardkey.seq_ends": ("처음 · 마지막 카드", "First / last card"),
        "boardkey.seq_select_all": ("모두 선택", "Select all"),
        "boardkey.seq_hold": ("Hold +1 / −1", "Hold +1 / −1"),
        "boardkey.seq_edit_hold": ("Hold 숫자 입력", "Type a hold"),
        "boardkey.seq_rename": ("카드 라벨 편집", "Edit the card label"),
        "boardkey.seq_remove": ("시퀀스에서 빼기", "Remove from the sequence"),
        "boardkey.seq_leave": ("플레이어로 돌아가기", "Back to the player"),
    }
)

shortcuts.register(
    [
        Shortcut("add_to_sequence", ("A",), "keypose"),
        Shortcut("flipbook", ("P",), "keypose"),
    ]
)

_S = 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
icons.register(
    {
        "seq_cards": f'<g {_S}><rect x="2.5" y="6.5" width="7.5" height="11" rx="1.6"/>'
        '<rect x="14" y="6.5" width="7.5" height="11" rx="1.6"/><path d="M10.8 12h2.4"/></g>',
        "seq_copy": f'<g {_S}><rect x="8.5" y="8.5" width="11.5" height="11.5" rx="2"/>'
        '<path d="M15.5 8.5V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7.5a2 2 0 0 0 2 2h2.5"/></g>',
        "seq_marker": f'<g {_S}><path d="M3 20.5h18"/><path d="M6.5 20.5V4h10l-2.2 3.6 2.2 3.6H6.5"/><path d="M17.5 20.5v-4"/></g>',
    }
)


def num(x: float) -> str:
    """3.0 -> '3', 3.5 -> '3.5', 2.333 -> '2.3'."""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def frames_text(n) -> str:
    return tr("seq.frames", n=n if isinstance(n, int) else num(n))


def secs_value(frames: float, fps: float) -> str:
    return f"{frames / fps:.2f}" if fps > 0 else "0.00"


def secs_text(frames: float, fps: float) -> str:
    return tr("seq.secs", s=secs_value(frames, fps))
