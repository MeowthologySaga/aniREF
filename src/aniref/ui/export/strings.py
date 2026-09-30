"""Korean / English text for the export feature (registered at import)."""

from __future__ import annotations

from ..i18n import register

register(
    {
        # -- actions -------------------------------------------------------------
        "act.export_contact_sheet": ("Contact Sheet 내보내기…", "Export contact sheet…"),
        "act.export_markers": ("Maya 마커 내보내기…", "Export Maya markers…"),
        # -- contact sheet dialog ------------------------------------------------
        "export.sheet.window": ("Contact Sheet 내보내기", "Export contact sheet"),
        "export.sheet.content": ("내용", "Content"),
        "export.sheet.content_seq": ("{name}  ·  키포즈 {n}개", "{name}  ·  {n} key poses"),
        "export.sheet.content_selected": ("선택한 키포즈  ·  {n}개", "Selected key poses  ·  {n}"),
        "export.sheet.content_all": ("모든 키포즈  ·  {n}개", "All key poses  ·  {n}"),
        "export.sheet.title_label": ("제목", "Title"),
        "export.sheet.title_hint": ("비우면 머리글 없음", "Empty: no header"),
        "export.sheet.layout": ("레이아웃", "Layout"),
        "export.sheet.columns_suffix": ("열", " columns"),
        "export.sheet.cell_width": ("칸 너비", "Cell width"),
        "export.sheet.px": ("{n} px", "{n} px"),
        "export.sheet.show": ("표시할 정보", "What to show"),
        "export.sheet.background": ("배경", "Background"),
        "export.sheet.open_after": ("저장하면 폴더 열기", "Open the folder after saving"),
        "export.layout.auto": ("자동", "Auto"),
        # columns first, as the info line under the preview reads (GRIDS keys are rows x cols)
        "export.layout.2x3": ("3열 × 2줄  —  6칸", "3 cols × 2 rows  —  6 slots"),
        "export.layout.2x4": ("4열 × 2줄  —  8칸", "4 cols × 2 rows  —  8 slots"),
        "export.layout.3x3": ("3열 × 3줄  —  9칸", "3 cols × 3 rows  —  9 slots"),
        "export.layout.strip": ("가로 한 줄", "One row"),
        "export.layout.columns": ("열 수 지정", "Set columns"),
        "export.opt.number": ("번호", "Number"),
        "export.opt.title": ("카드 라벨 · Phase", "Card label · phase"),
        "export.opt.source": ("영상 · 프레임", "Video · frame"),
        "export.opt.timing": ("타이밍 · 애니 프레임", "Timing · anim frame"),
        "export.opt.notes": ("메모", "Notes"),
        "export.opt.drawings": ("드로잉 포함", "Include drawings"),
        "export.opt.arrows": ("순서 화살표", "Order arrows"),
        "export.bg.dark": ("어둡게", "Dark"),
        "export.bg.light": ("밝게 · 인쇄용", "Light · print"),
        # -- buttons and feedback -------------------------------------------------
        "export.sheet.save": ("PNG 저장", "Save PNG"),
        "export.sheet.save_as": ("다른 이름으로 저장…", "Save as…"),
        "export.sheet.copy": ("클립보드에 복사", "Copy to clipboard"),
        "export.sheet.copy_tip": ("PureRef · Photoshop에 바로 붙여넣기  ({keys})", "Paste straight into PureRef or Photoshop  ({keys})"),
        "export.sheet.save_tip": ("{path} 에 저장  (Enter)", "Saves to {path}  (Enter)"),
        "export.sheet.save_tip_ask": ("저장할 위치를 물어봅니다  (Enter)", "Asks where to save  (Enter)"),
        "export.sheet.info": ("{w} × {h} px  ·  {cols}열 × {rows}줄  ·  키포즈 {n}개", "{w} × {h} px  ·  {cols} cols × {rows} rows  ·  {n} key poses"),
        "export.sheet.overflow": ("{cap}칸보다 많아서 줄을 늘렸습니다", "More poses than slots — rows added"),
        "export.sheet.target": ("저장 위치  {path}", "Saves to  {path}"),
        "export.sheet.target_ask": (
            "프로젝트를 아직 저장하지 않아서, 저장할 위치를 물어봅니다",
            "The project isn't saved yet, so you'll be asked where to put the PNG",
        ),
        "export.sheet.saved": ("저장했습니다  ·  {path}", "Saved  ·  {path}"),
        "export.sheet.copied": ("클립보드에 복사했습니다 — PureRef에 붙여넣어 보세요", "Copied — paste it into PureRef"),
        "export.sheet.open_folder": ("폴더 열기", "Open folder"),
        "export.sheet.file_dialog": ("Contact Sheet 저장", "Save contact sheet"),
        "export.sheet.png_filter": ("PNG 이미지 (*.png)", "PNG image (*.png)"),
        "export.sheet.save_failed": ("PNG를 저장하지 못했습니다", "Couldn't save the PNG"),
        "export.sheet.missing": ("이미지 없음", "No image"),
        "export.sheet.empty_title": ("내보낼 키포즈가 없습니다", "Nothing to put on the sheet"),
        "export.sheet.empty_body": (
            "시퀀스 보드에 포즈를 넣거나 라이브러리에서 키포즈를 선택한 뒤 다시 열어 주세요.",
            "Put poses on the Sequence Board or select some in the library, then open this again.",
        ),
        # a rate is written "30fps"; "@N" is kept for Maya timeline positions (sequence cards).
        # "anim": the PNG goes to people who never see the app, and next to a 60fps reference
        # a bare "30fps" reads as the video's rate.
        "export.sheet.subtitle_seq": (
            "{project}  ·  {total} · 애니 {fps}fps  ·  {date}",
            "{project}  ·  {total} · anim {fps}fps  ·  {date}",
        ),
        "export.sheet.subtitle_poses": ("{project}  ·  키포즈 {n}개  ·  {date}", "{project}  ·  {n} key poses  ·  {date}"),
        # never-saved project: its placeholder name ("제목 없음") read as "title missing" on the sheet
        "export.sheet.subtitle_seq_noproj": ("{total} · 애니 {fps}fps  ·  {date}", "{total} · anim {fps}fps  ·  {date}"),
        "export.sheet.subtitle_poses_noproj": ("키포즈 {n}개  ·  {date}", "{n} key poses  ·  {date}"),
        "export.sheet.poses_title": ("키포즈", "Key poses"),
        # -- markers ---------------------------------------------------------------
        "export.markers.dialog": ("Maya 마커 저장", "Save Maya markers"),
        "export.markers.json_filter": ("Maya 마커 JSON (*.json)", "Maya markers JSON (*.json)"),
        "export.markers.csv_filter": ("CSV 표 (*.csv)", "CSV table (*.csv)"),
        "export.markers.none_title": ("내보낼 시퀀스가 없습니다", "No sequence to export"),
        "export.markers.none_body": (
            "마커는 시퀀스의 포즈 위치(애니 프레임)로 만들어집니다. "
            "시퀀스 보드에 포즈를 넣고 타이밍을 정한 뒤 다시 내보내세요.",
            "Markers come from each pose's anim frame in a sequence. "
            "Put poses on the Sequence Board, set their timing, then export again.",
        ),
        "export.markers.failed": ("마커 파일을 저장하지 못했습니다", "Couldn't save the marker file"),
        # -- OSD --------------------------------------------------------------------
        "export.osd.sheet_saved": ("Contact Sheet 저장  {name}", "Contact sheet saved  {name}"),
        "export.osd.sheet_copied": ("Contact Sheet를 클립보드에 복사했습니다", "Contact sheet copied to the clipboard"),
        "export.osd.markers_saved": ("Maya 마커 {n}개 저장  {name}", "{n} Maya markers saved  {name}"),
    }
)
