"""Settings: preferences, the settings window, shortcut customization,
autosave/recovery and the update check.

Importing the package registers this feature's text, icons, the `Ctrl+,`
shortcut and its guide page.
"""

from . import strings as _strings  # noqa: F401  (registers text, icons, shortcut)
from . import guide as _guide  # noqa: F401  (registers the user guide page)
from .autosave import Autosaver, ask_recovery, discard, find_recovery, load_recovery, orphaned_untitled
from .dialog import SettingsDialog, open_settings
from .keymap import KeymapEditor, apply_to_actions
from .prefs import changes, load_shortcut_overrides
from .updates import UpdateChecker, show_update_notice

__all__ = [
    "Autosaver",
    "KeymapEditor",
    "SettingsDialog",
    "UpdateChecker",
    "apply_to_actions",
    "ask_recovery",
    "changes",
    "discard",
    "find_recovery",
    "load_recovery",
    "load_shortcut_overrides",
    "open_settings",
    "orphaned_untitled",
    "show_update_notice",
]
