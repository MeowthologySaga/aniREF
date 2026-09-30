"""The user guide page for the compare window.

Key caps come from `keys.py`, so the page always shows the keys that work.
"""

from __future__ import annotations

from ..help.content import Block, Page, h, note, p, register_page, tip
from ..i18n import pick as t
from . import keys

PAGE_ID = "playblast"

_GROUPS = (
    ("재생", "Playing", ["play_pause", "step_back", "step_fwd", "speed_down", "speed_up", "first_frame", "last_frame"]),
    ("맞추기", "Lining up", ["offset_back", "offset_fwd", "sync_toggle"]),
    (
        "보기",
        "Looking",
        ["toggle_mode", "mode_side", "mode_overlay", "mode_wipe", "difference", "opacity_up", "opacity_down",
         "mirror", "mirror_b", "fit_view"],
    ),
    ("루프", "Loop", ["loop_in", "loop_out", "loop_toggle"]),
    ("파일", "Files", ["open_b", "reload_b"]),
)


def _key_list(action_ids: list[str]) -> Block:
    return p("\n".join(f"{keys.markup(i)}  ·  {keys.label(i)}" for i in action_ids))


def _page() -> Page:
    return Page(
        PAGE_ID,
        "pb_side",
        t("내 애니메이션과 비교", "Compare with my animation"),
        t(
            "Maya에서 뽑은 플레이블라스트를 레퍼런스 옆에 놓거나 위에 겹쳐서, 타이밍과 포즈가 어디서 어긋나는지 봅니다.",
            "Put the playblast from Maya next to — or on top of — the reference and see where timing and poses drift.",
        ),
        [
            Block(
                "steps",
                [
                    (
                        t("비교 창 열기", "Open the compare window"),
                        t(
                            "{a:playblast_compare} 키를 누르면 지금 보던 레퍼런스가 **A**(왼쪽)로 들어갑니다.",
                            "{a:playblast_compare} opens it with the reference you were watching as **A** (left).",
                        ),
                    ),
                    (
                        t("Maya에서 플레이블라스트 뽑기", "Playblast from Maya"),
                        t(
                            "씬과 같은 fps로, 프레임 번호가 보이게 뽑으세요. 설정은 아래에 정리해 두었습니다.",
                            "Render it at the scene's fps with the frame number visible — settings are listed below.",
                        ),
                    ),
                    (
                        t("B에 끌어다 놓기", "Drop it into B"),
                        t(
                            f"영상 파일을 오른쪽에 끌어다 놓거나 {keys.markup('open_b')} 키로 엽니다. 최근에 쓴 파일은 목록에서 바로 고를 수 있어요.",
                            f"Drop the file on the right side or press {keys.markup('open_b')}. Files you used lately are one click away in the list.",
                        ),
                    ),
                    (
                        t("시작점 맞추기", "Line the two up"),
                        t(
                            f"두 영상에서 같은 순간(예: 발이 땅에 닿는 프레임)을 찾습니다. A를 그 프레임에 두고 "
                            f"{keys.markup('offset_back')} {keys.markup('offset_fwd')} 키로 B를 밀어서 같은 포즈가 나오게 합니다.",
                            f"Find the same instant in both (the frame a foot lands, say). Park A on it and nudge B with "
                            f"{keys.markup('offset_back')} {keys.markup('offset_fwd')} until the pose matches.",
                        ),
                    ),
                    (
                        t("겹쳐 보고 반복 재생", "Overlay and loop it"),
                        t(
                            f"{keys.markup('toggle_mode')} 키로 겹쳐보기, {{a:loop_in}} {{a:loop_out}} 키로 구간을 정하고 "
                            "{a:play_pause} 키로 반복 재생하며 비교합니다.",
                            f"{keys.markup('toggle_mode')} lays them over each other; set a range with {{a:loop_in}} {{a:loop_out}} "
                            "and compare while it repeats with {a:play_pause}.",
                        ),
                    ),
                ],
            ),
            h(t("Maya에서 플레이블라스트 뽑을 때", "Playblasting out of Maya")),
            Block(
                "legend",
                [
                    (
                        t("씬과 같은 fps로", "Same fps as the scene"),
                        t(
                            "30fps 씬이면 30fps 영상으로 뽑으세요. fps가 달라도 시간 기준으로 맞춰 주긴 하지만, 같은 fps여야 프레임 번호까지 그대로 비교됩니다.",
                            "A 30 fps scene should give a 30 fps file. Different rates still line up by time, but matching rates keep the frame numbers comparable too.",
                        ),
                    ),
                    (
                        t("프레임 번호가 보이게", "Show the frame number"),
                        t(
                            "Display → Heads Up Display → Current Frame 을 켜두면, 영상 안의 번호와 이 창의 번호를 눈으로 대조할 수 있습니다.",
                            "Display → Heads Up Display → Current Frame lets you check the number burned into the picture against the one this window shows.",
                        ),
                    ),
                    (
                        t("같은 파일에 덮어쓰기", "Overwrite the same file"),
                        t(
                            f"다시 뽑을 때 같은 경로에 덮어쓰면, 이 창으로 돌아올 때 새 영상을 알아서 다시 불러옵니다. 직접 불러오려면 {keys.markup('reload_b')}.",
                            f"Playblast over the same path and this window reloads it when you come back. To do it by hand: {keys.markup('reload_b')}.",
                        ),
                    ),
                    (
                        t("카메라와 화면 비율 고정", "Keep camera and framing"),
                        t(
                            "레퍼런스와 비슷한 각도·거리로 잡고, 매번 같은 카메라로 뽑으세요. 겹쳐보기와 차이 보기가 훨씬 잘 맞습니다.",
                            "Frame it like the reference and use the same camera every take — overlay and difference then actually line up.",
                        ),
                    ),
                ],
            ),
            h(t("맞춤 기준: 시간 vs 프레임", "Sync: by time or by frame")),
            p(
                t(
                    "**시간 기준**(기본)은 같은 순간끼리 붙입니다. 60fps 레퍼런스의 F60과 30fps 플레이블라스트의 F30은 둘 다 1초 지점이라 같이 보입니다. "
                    "**프레임 기준**은 번호가 같은 프레임끼리 붙입니다. 두 영상이 같은 fps일 때 편해요.",
                    "**By time** (the default) pairs the same instant: F60 of a 60 fps reference and F30 of a 30 fps playblast are both one second in. "
                    "**By frame** pairs equal frame numbers — handy when both run at the same rate.",
                )
            ),
            p(
                t(
                    "레퍼런스에는 준비 동작이 더 길게 들어 있는 경우가 많습니다. 기준이 되는 순간 하나만 오프셋으로 맞춰 두면 그 뒤 구간이 전부 맞습니다. "
                    "B가 자기 영상 밖으로 나가면 B 태그에 **시작 전 / 끝남** 이라고 표시되고 그림이 흐려집니다.",
                    "References usually carry a longer wind-up. Match one instant with the offset and everything after it lines up. "
                    "When A runs past either end of B, B's tag says **not started / ended** and the picture dims.",
                )
            ),
            h(t("네 가지 보기", "Four ways to look")),
            Block(
                "legend",
                [
                    (
                        t("나란히", "Side by side"),
                        t(
                            "전체 타이밍과 실루엣을 비교합니다. 크게 다른 곳을 먼저 찾을 때 좋아요.",
                            "Compare overall timing and silhouette — the fastest way to spot what is badly off.",
                        ),
                    ),
                    (
                        t("겹쳐보기", "Overlay"),
                        t(
                            f"B를 50% 정도로 겹쳐 놓고 포즈가 얼마나 어긋났는지 봅니다. {keys.markup('opacity_up')} {keys.markup('opacity_down')} 키로 진하기를 바꿉니다.",
                            f"Lay B over A at about 50% and see how far the pose drifts. {keys.markup('opacity_up')} {keys.markup('opacity_down')} change how strongly it shows.",
                        ),
                    ),
                    (
                        t("차이", "Difference"),
                        t(
                            "똑같은 곳은 검게, 어긋난 곳만 밝게 보입니다. 발 위치나 무게중심이 얼마나 밀렸는지 찾을 때 확실합니다. 배경과 카메라가 다르면 전체가 밝게 보입니다.",
                            "Matching areas go black and only the offsets light up — the surest way to see a foot or a weight shift sliding. A different background or camera lights up everything.",
                        ),
                    ),
                    (
                        t("와이프", "Wipe"),
                        t(
                            "가운데 경계를 드래그해서 왼쪽은 레퍼런스, 오른쪽은 내 애니메이션으로 봅니다. 실루엣 라인을 이어서 볼 때 좋아요.",
                            "Drag the split: reference on the left, your animation on the right. Good for reading one silhouette across the seam.",
                        ),
                    ),
                ],
            ),
            tip(
                t(
                    "타이밍이 궁금하면 0.25x 루프 + 나란히, 포즈를 다듬을 땐 겹쳐보기나 차이로 보세요. Mirror는 슬롯마다 따로 켤 수 있어서, 반대 방향 레퍼런스도 쓸 수 있습니다.",
                    "Timing question? Loop at 0.25x side by side. Polishing a pose? Overlay or difference. Mirror is per slot, so a reference facing the other way still works.",
                )
            ),
            h(t("단축키", "Keys")),
            *[block for ko, en, ids in _GROUPS for block in (h(t(ko, en)), _key_list(ids))],
            note(
                t(
                    "이 창은 프로젝트를 바꾸지 않습니다. 여기서 건드린 루프·속도·Mirror는 메인 창의 영상 설정에 저장되지 않아요.",
                    "This window never edits the project: the loop, speed and mirror you set here are not saved back to the video's settings.",
                )
            ),
            Block("links", ["loop", "playback", "frames"]),
        ],
    )


register_page(65, _page)
