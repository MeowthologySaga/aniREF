"""Export feature: contact sheet PNG and Maya markers.

Importing this package registers its strings, shortcuts and guide page, so
the main window only needs to import it before building actions.
"""

from .. import icons
from ..shortcuts import Shortcut, register as register_shortcuts
from . import strings as _strings  # noqa: F401  (registers i18n text)

icons.register(
    {
        "export_done": '<g fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
        'stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 12.3l2.7 2.7L16.2 9.5"/></g>',
    }
)

register_shortcuts(
    [
        Shortcut("export_contact_sheet", ("Ctrl+E",), "project"),
        Shortcut("export_markers", ("Ctrl+Shift+E",), "project"),
    ]
)

from . import help as _help  # noqa: E402,F401  (registers the guide page)
from .dialogs import ContactSheetDialog, export_markers, open_contact_sheet_dialog  # noqa: E402

__all__ = ["ContactSheetDialog", "export_markers", "open_contact_sheet_dialog"]
