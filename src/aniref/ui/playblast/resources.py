"""Strings, icons and the global shortcut of the playblast compare window,
registered at import so the feature stays self-contained."""

from __future__ import annotations

from .. import i18n, icons, shortcuts

_STROKE = 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'

icons.register(
    {
        "pb_side": f'<g {_STROKE}><rect x="2.5" y="5" width="8.5" height="14" rx="1.5"/><rect x="13" y="5" width="8.5" height="14" rx="1.5"/></g>',
        "pb_overlay": f'<g {_STROKE}><rect x="3" y="3" width="12.5" height="12.5" rx="2"/></g>'
        '<rect x="8.5" y="8.5" width="12.5" height="12.5" rx="2" fill="currentColor" fill-opacity=".45"/>',
        "pb_wipe": f'<g {_STROKE}><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M12 2v20"/></g>'
        '<path d="M12 5h7a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1h-7z" fill="currentColor" fill-opacity=".45"/>',
        "pb_diff": f'<g {_STROKE}><circle cx="9" cy="12" r="6"/><circle cx="15" cy="12" r="6"/></g>',
        "pb_minus": f'<g {_STROKE}><path d="M5 12h14"/></g>',
        "pb_reload":f'<g {_STROKE}><path d="M20 12a8 8 0 1 1-2.35-5.65"/><path d="M20 4v5h-5"/></g>',
    }
)

shortcuts.register([shortcuts.Shortcut("playblast_compare", ("Ctrl+Shift+P",), "view")])

i18n.register(
    {
        # one name for the window everywhere: menu, title bar, guide page
        "act.playblast_compare": ("내 애니메이션과 비교", "Compare with my animation"),
        "pb.title": ("내 애니메이션과 비교", "Compare with my animation"),
        "pb.slot.a": ("레퍼런스", "Reference"),
        "pb.slot.b": ("내 애니메이션", "My animation"),
        "pb.pick_a": ("레퍼런스 고르기", "Choose a reference"),
        "pb.pick_b": ("플레이블라스트 없음", "No playblast yet"),
        "pb.open_file": ("다른 파일 열기…", "Open another file…"),
        "pb.open_b": ("플레이블라스트 열기…", "Open playblast…"),
        "pb.mode.side": ("나란히", "Side by side"),
        "pb.mode.overlay": ("겹쳐보기", "Overlay"),
        "pb.mode.wipe": ("와이프", "Wipe"),
        "pb.opacity": ("B 불투명도", "B opacity"),
        "pb.difference": ("차이", "Difference"),
        "pb.sync": ("맞춤 기준", "Sync"),  # not 맞춤 alone: that is fit-to-view (화면 맞춤) elsewhere
        "pb.sync.time": ("시간", "Time"),
        "pb.sync.frame": ("프레임", "Frame"),
        "pb.offset": ("B 오프셋", "B offset"),
        "pb.tip.sync_time": (
            "시간 기준: fps가 달라도 같은 순간끼리 맞춥니다\n(60fps 레퍼런스 ↔ 30fps 플레이블라스트)",
            "By time: pairs what shows at the same moment, even at different fps\n(60 fps reference ↔ 30 fps playblast)",
        ),
        "pb.tip.sync_frame": ("프레임 기준: 같은 프레임 번호끼리 맞춥니다", "By frame: pairs equal frame numbers"),
        "pb.tip.offset": (
            "B를 몇 프레임 밀어서 맞출지 (B의 프레임 단위)  ·  {keys}",
            "How many of its own frames B is shifted  ·  {keys}",
        ),
        "pb.tip.opacity": ("겹쳐보기에서 B가 보이는 정도  ·  {keys}", "How strongly B shows in overlay  ·  {keys}"),
        "pb.tip.difference": (
            "겹치는 부분은 검게, 어긋난 부분만 밝게 보입니다",
            "Matching areas turn black; only what is off lights up",
        ),
        "pb.tip.readout": ("A의 현재 프레임과, 거기에 맞춰진 B의 프레임", "A's current frame and the B frame matched to it"),
        "pb.tip.diff_disables": ("차이 보기에서는 B를 100%로 겹칩니다", "Difference always blends B at 100%"),
        # Only ever shown right after B's pink "B" label (tag and readout), so no "B" of their own.
        "pb.before": ("시작 전", "not started"),
        "pb.after": ("끝남", "ended"),
        "pb.osd.mode.side": ("나란히 보기", "Side by side"),
        "pb.osd.mode.overlay": ("겹쳐보기  ·  B {pct}%", "Overlay  ·  B {pct}%"),
        "pb.osd.mode.wipe": ("와이프  ·  드래그해서 경계 이동", "Wipe  ·  drag to move the split"),
        "pb.osd.diff_on": ("차이 보기  ·  어긋난 곳만 밝게", "Difference  ·  only offsets light up"),
        "pb.osd.diff_off": ("차이 보기 꺼짐", "Difference off"),
        "pb.osd.opacity": ("B 불투명도  {pct}%", "B opacity  {pct}%"),
        "pb.osd.offset": ("B 오프셋  {offset}f", "B offset  {offset}f"),
        "pb.osd.sync_time": ("시간 기준으로 맞춤", "Synced by time"),
        "pb.osd.sync_frame": ("프레임 번호 기준으로 맞춤", "Synced by frame number"),
        "pb.osd.mirror_a_on": ("A Mirror 켜짐", "A mirror on"),
        "pb.osd.mirror_a_off": ("A Mirror 꺼짐", "A mirror off"),
        "pb.osd.mirror_b_on": ("B Mirror 켜짐", "B mirror on"),
        "pb.osd.mirror_b_off": ("B Mirror 꺼짐", "B mirror off"),
        "pb.osd.need_a": ("먼저 레퍼런스(A)를 여세요", "Open a reference (A) first"),
        "pb.osd.need_b": ("먼저 내 애니메이션(B)을 여세요", "Open your playblast (B) first"),
        "pb.osd.opened_b": ("B  {name}", "B  {name}"),
        "pb.osd.reloaded": ("새 플레이블라스트를 불러왔습니다", "Loaded the new playblast"),
        "pb.drop.a": ("놓아서 A (레퍼런스)로 열기", "Drop to open as A (reference)"),
        "pb.drop.b": ("놓아서 B (내 애니메이션)로 열기", "Drop to open as B (my animation)"),
        "pb.empty_a.title": ("레퍼런스 영상을 끌어다 놓으세요", "Drop a reference video here"),
        "pb.empty_a.body": (
            "위쪽 목록에서 프로젝트의 영상을 고르거나, 영상 파일을 이쪽에 끌어다 놓으세요.",
            "Pick one of the project's videos in the list above, or drop a video file on this side.",
        ),
        "pb.empty_a.open": ("레퍼런스 열기", "Open reference"),
        "pb.empty_b.title": ("플레이블라스트 영상을 끌어다 놓으세요", "Drop your playblast here"),
        "pb.empty_b.body": (
            "Maya에서 뽑은 영상을 이쪽에 놓으면 레퍼런스와 시간을 맞춰 함께 재생됩니다.",
            "Drop the video you playblasted from Maya on this side; it plays in step with the reference.",
        ),
        "pb.empty_b.open": ("플레이블라스트 열기", "Open playblast"),
        "pb.empty_b.howto": ("Maya에서 뽑는 법", "Playblast tips"),
        "pb.recent": ("최근 플레이블라스트", "Recent playblasts"),
        "pb.dlg.open_a": ("레퍼런스 영상 열기", "Open reference video"),
        "pb.dlg.open_b": ("플레이블라스트 영상 열기", "Open playblast video"),
        "pb.key.mirror_a": ("A Mirror (좌우 반전)", "Mirror A"),
        "pb.key.mirror_b": ("B Mirror (좌우 반전)", "Mirror B"),
        "pb.key.offset_back": ("B 오프셋 -1프레임", "B offset -1 frame"),
        "pb.key.offset_fwd": ("B 오프셋 +1프레임", "B offset +1 frame"),
        "pb.key.toggle_mode": ("나란히 ↔ 겹쳐보기", "Side by side ↔ overlay"),
        "pb.key.mode_side": ("나란히 보기", "Side by side"),
        "pb.key.mode_overlay": ("겹쳐보기", "Overlay"),
        "pb.key.mode_wipe": ("와이프 (경계를 드래그)", "Wipe (drag the split)"),
        "pb.key.difference": ("차이 보기 켜기 / 끄기", "Difference on / off"),
        "pb.key.opacity_down": ("B 불투명도 -10%", "B opacity -10%"),
        "pb.key.opacity_up": ("B 불투명도 +10%", "B opacity +10%"),
        "pb.key.sync_toggle": ("맞춤 기준 바꾸기 (시간 ↔ 프레임)", "Switch sync (time ↔ frame)"),
        "pb.key.open_b": ("플레이블라스트 열기", "Open playblast"),
        "pb.key.reload_b": ("플레이블라스트 다시 불러오기", "Reload playblast"),
        "pb.key.help": ("이 창 사용법", "How this window works"),
    }
)
