"""Focused checks or --all without desktop windows, global key input or audio."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

import app
import test_windows


CHECKS = (
    "QtInterfaceTests.test_top_navigation_and_compact_card_fit",
    "QtInterfaceTests.test_closed_selectors_forward_wheel_without_changing_or_saving_selection",
    "QtInterfaceTests.test_sound_preview_is_visible_and_uses_the_selected_bundled_file",
    "QtInterfaceTests.test_voice_dock_does_not_overlap_in_any_state_or_with_a_long_shortcut",
    "WindowsTests.test_all_bundled_sound_choices_resolve_to_short_pcm_audio",
)


class NoDesktopHotkey:
    registered = True

    def __init__(self, *args):
        pass

    def poll(self):
        return False

    def close(self):
        self.registered = False


def main():
    all_tests = sys.argv[1:] == ["--all"]
    chosen = sys.argv[1:] or CHECKS
    if not all_tests and any(name not in CHECKS for name in chosen):
        raise SystemExit("Choose an explicit safe check from CHECKS; native desktop tests are excluded.")
    qt = QApplication.instance() or QApplication([])
    qt.setStyle("Fusion")
    for name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "consola.ttf"):
        QFontDatabase.addApplicationFont(str(Path(os.environ["WINDIR"]) / "Fonts" / name))
    qt.setFont(QFont("Segoe UI", 10))
    suite = (unittest.defaultTestLoader.loadTestsFromModule(test_windows) if all_tests else
        unittest.defaultTestLoader.loadTestsFromNames(chosen, module=test_windows))
    sequence = [0]
    def clipboard_changed():
        sequence[0] += 1
    qt.clipboard().dataChanged.connect(clipboard_changed)
    with patch.object(app.native, "Hotkey", NoDesktopHotkey), \
         patch.object(app.native, "foreground", return_value=0), \
         patch.object(app.native, "clipboard_sequence", side_effect=lambda: sequence[0]), \
         patch.object(app.App, "dark_titlebar"), \
         patch.object(app.winsound, "PlaySound"), \
         patch.object(QSystemTrayIcon, "show"), \
         patch.object(QSystemTrayIcon, "showMessage"):
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    qt.clipboard().dataChanged.disconnect(clipboard_changed)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
