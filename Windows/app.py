"""Windows client, reproducing the original macOS layout with Qt."""
import ctypes
import datetime
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import urllib.request
import winreg
import winsound

from PySide6.QtCore import (QAbstractNativeEventFilter, QEasingCurve, QEvent, QMimeData, QPoint,
    QSignalBlocker, Qt, QTimer, QUrl, QVariantAnimation)
from PySide6.QtGui import (QColor, QCursor, QDesktopServices, QFont, QIcon, QKeySequence,
    QPainter, QPen, QPixmap)
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
    QKeySequenceEdit, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
    QSizePolicy, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

import sounddevice as sd
import native
from speech import Session
from ui import (BRAND, CYAN, GREEN, MICA_STYLE, PINK, YELLOW, STYLE, AudioMeter, ComboBox, CompactPanel,
    LiveCaption, MotionButton, RecordingIndicator, SmoothScrollArea, StudioBackdrop, Switch,
    VoicePanel, divider, icon, label, motion_duration)

DATA_FILE = Path(os.environ["LOCALAPPDATA"]) / "Blablabla" / "windows.json"
HOLD_TO_TALK = 0.4  # seconds; a shorter press is a tap that toggles
APP_VERSION = "0.7.0"
UPDATE_REPO = "arturogj92/blablabla"


def version_tuple(tag):
    return tuple(int(part) for part in re.findall(r"\d+", tag)[:3])


def newer_windows_release(releases, current=APP_VERSION):
    """Newest release that ships a Windows build and is newer than current, as (tag, page url)."""
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        if any("windows" in asset.get("name", "").lower() for asset in release.get("assets", [])):
            if version_tuple(release["tag_name"]) > version_tuple(current):
                return release["tag_name"], release["html_url"]
            return None
    return None


def fetch_releases():
    request = urllib.request.Request(f"https://api.github.com/repos/{UPDATE_REPO}/releases?per_page=10",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Blablabla-Windows"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)
RESOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "Resources"
SOUNDS = (("None", "None"), ("Soft tap", "tone:soft-tap"), ("Glass", "tone:glass"),
    ("Bloom", "tone:bloom"), ("Rise", "tone:rise"), ("Fall", "tone:fall"),
    ("Pulse", "tone:pulse"), ("Two notes", "tone:two-notes"), ("Air", "tone:air"),
    ("Windows chime", "SystemAsterisk"), ("Windows notification", "SystemExclamation"),
    ("Windows alert", "SystemHand"))


def load_data(path=DATA_FILE):
    if not path.exists():
        return {"api_key": "", "copy_only": False, "device": "", "history": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("history", []), list):
        raise ValueError("Invalid local data format")
    return data


def save_data(data, path=DATA_FILE):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def button(text, action, text_only=False):
    widget = MotionButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if text_only:
        widget.setProperty("role", "text")
    widget.clicked.connect(action)
    return widget


def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            event = native.w.MSG.from_address(int(message))
            if event.message == 0x0312 and event.wParam == 0x4242:
                QTimer.singleShot(0, self.callback)
                return True, 0
        return False, 0


class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.data = load_data()
        self.events = queue.Queue()
        self.session = None
        self.state = "idle"
        self.target = self.last_target = None
        self.held_since = None
        self.closing = self.disposed = False
        self.display_limit = 10
        self.current_text = ""
        self.compact_mode = bool(self.data.get("compact_mode", False))
        self.recorded_seconds = None
        self.cloud_connected = False
        self.started_at = None
        self.settings_controls = []
        self.status_message = "Ready to dictate"
        self.clipboard_revision = 0
        self.pending_clipboard = None
        self.clipboard_timer = QTimer(self)
        self.clipboard_timer.setSingleShot(True)
        self.clipboard_timer.timeout.connect(self.restore_clipboard)
        self.setWindowTitle("Blablabla")
        self.resize(840, 740)
        self.setMinimumSize(700, 600)
        self.setStyleSheet(STYLE)
        # Mica needs Windows 11 22H2+; must be set before the native window exists.
        self.mica = sys.getwindowsversion().build >= 22621
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, self.mica)
        self.app_icon = QIcon(str(RESOURCES / "icon_squircle.png"))
        self.setWindowIcon(self.app_icon)
        self.hotkey = native.Hotkey(self.data.get("shortcut_modifiers", 3), self.data.get("shortcut_key", 0x20))
        self.hotkey_filter = HotkeyFilter(self.shortcut_pressed)
        QApplication.instance().installNativeEventFilter(self.hotkey_filter)
        try:
            key = native.unprotect_key(self.data.get("api_key", ""))
        except Exception:
            key = ""
            self.status_message = "Re-enter your API key: it could not be decrypted for this user."
        self.key = QLineEdit(key)
        self.key.setPlaceholderText("Paste your AssemblyAI key")
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setAccessibleName("AssemblyAI API key")
        self.key.editingFinished.connect(self.commit_key)
        self.key.textEdited.connect(self.key_edited)
        self.key_mask = label("")
        self.key_mask.setStyleSheet("background:#242429;border-radius:8px;padding:8px;color:#85858d;font-family:Consolas;")

        central = StudioBackdrop()
        self.setCentralWidget(central)
        shell = QVBoxLayout(central)
        shell.setContentsMargins(16, 10, 16, 16)
        shell.setSpacing(12)
        self.build_navigation(shell)
        self.fading = None
        self.page_fade = QVariantAnimation(self)
        self.page_fade.setDuration(motion_duration(160))
        self.page_fade.setStartValue(0.0)
        self.page_fade.setEndValue(1.0)
        self.page_fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.page_fade.valueChanged.connect(self.fade_step)
        self.page_fade.finished.connect(self.end_fade)
        self.pages = QStackedWidget()
        workspace = QWidget()
        workspace.setObjectName("workspace")
        content = QVBoxLayout(workspace)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self.pages, 1)
        shell.addWidget(workspace, 1)
        self.build_session_panel(shell)
        self.settings_page, self.settings_layout = self.page("Settings")
        self.transcripts_page, self.transcripts_layout = self.page("Transcripts", clear=True)
        self.permissions_page, self.permissions_layout = self.page("Permissions", refresh=True)
        self.build_settings()
        self.build_transcripts()
        self.build_permissions()
        self.select_page(0)

        self.indicator = RecordingIndicator()
        self.caption = LiveCaption()
        self.compact = CompactPanel()
        self.compact.toggle_requested.connect(self.toggle)
        self.compact.expand_requested.connect(self.show_window)
        self.compact.position_changed.connect(self.save_compact_position)
        self.position_compact()
        self.indicator.clicked.connect(self.toggle)
        self.indicator.position_changed.connect(self.save_indicator_position)
        self.indicator.draggable = self.free_position.isChecked()
        self.position_indicator()
        self.tray = QSystemTrayIcon(self.app_icon, self)
        self.tray.setToolTip("Blablabla")
        recording, busy = self.badged_icon(PINK), self.badged_icon(CYAN)
        self.tray_icons = {"idle": self.app_icon, "listening": recording, "connecting": busy, "stopping": busy}
        self.notice_page = 1
        self.tray.messageClicked.connect(lambda: (self.select_page(self.notice_page), self.show_window()))
        menu = QMenu(self)
        menu.addAction("Show Blablabla", self.show_window)
        self.tray_record_action = menu.addAction("Start dictation", self.toggle)
        menu.addSeparator()
        menu.addAction("Quit Blablabla", self.request_shutdown)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_window()
            if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll)
        self.poll_timer.start(40)
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_session_clock)
        self.clock_timer.start(1000)
        self.refresh_devices()
        self.refresh_history()
        self.update_usage()
        self.update_key_display()
        if not self.hotkey.registered:
            self.status_message = "Shortcut is in use. Use the indicator or set another shortcut."
        self.set_status(self.status_message)
        self.update_indicator()
        self.dark_titlebar()

    def build_session_panel(self, content):
        container = QWidget()
        inset = QVBoxLayout(container)
        inset.setContentsMargins(0, 0, 0, 0)
        panel = self.voice_panel = VoicePanel()
        column = QVBoxLayout(panel)
        column.setContentsMargins(18, 16, 18, 16)
        column.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.audio_meter = AudioMeter()
        row.addWidget(self.audio_meter)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        self.session_heading = label("Ready to dictate", "section")
        self.session_hint = label(self.data.get("shortcut_label", "Ctrl + Alt + Space"), "detail")
        for text in (self.session_heading, self.session_hint):
            text.setMinimumWidth(0)
            text.setWordWrap(True)
            text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.session_hint.setWordWrap(False)
        titles.addWidget(self.session_heading)
        titles.addWidget(self.session_hint)
        row.addLayout(titles, 1)
        self.session_clock = label("", "detail")
        self.session_clock.setStyleSheet("font-family:Consolas;color:#bcbcc6;")
        self.session_clock.setFixedWidth(52)
        row.addWidget(self.session_clock)
        self.button = button("Start dictation", self.toggle)
        self.button.setObjectName("recordButton")
        self.button.setProperty("role", "primary")
        self.button.setIcon(icon("mic", "#092328", 17))
        self.button.setMinimumSize(155, 44)
        row.addWidget(self.button)
        self.compact_button = button("Compact mode", lambda: self.set_compact_mode(True))
        self.compact_button.setIcon(icon("compact", "#d5d5df", 16))
        self.compact_button.setMinimumHeight(44)
        row.addWidget(self.compact_button)
        column.addLayout(row)
        self.session_status = label(self.status_message, "detail")
        self.session_status.setWordWrap(True)
        self.session_status.setMinimumWidth(0)
        self.session_status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.session_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        column.addWidget(self.session_status)
        inset.addWidget(panel)
        content.addWidget(container)

    def update_session_clock(self):
        seconds = max(0, int(time.monotonic() - self.started_at)) if self.started_at is not None else 0
        self.session_clock.setText(f"{seconds//60:02}:{seconds%60:02}" if self.state != "idle" else "")
        self.update_compact()

    def update_compact(self):
        if hasattr(self, "compact"):
            self.compact.set_session(self.state, self.current_text if self.live_text.isChecked() else "", self.status_message,
                self.data.get("shortcut_label", "Ctrl + Alt + Space"), self.session_clock.text(), self.closing)

    def position_compact(self):
        position = self.data.get("compact_position")
        if isinstance(position, list) and len(position) == 2 and all(isinstance(value, int) for value in position):
            screen = QApplication.screenAt(QPoint(*position))
            if screen and screen.availableGeometry().contains(QPoint(position[0] + self.compact.width() - 1,
                    position[1] + self.compact.height() - 1)):
                self.compact.move(*position)
                return
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        bounds = screen.availableGeometry()
        self.compact.move(bounds.center().x() - self.compact.width()//2,
            bounds.bottom() - self.compact.height() - 16)

    def save_compact_preferences(self):
        try:
            save_data(self.data)
        except OSError:
            self.set_status("Could not save compact mode preferences. They will reset on restart.")

    def save_compact_position(self):
        self.data["compact_position"] = [self.compact.x(), self.compact.y()]
        self.save_compact_preferences()

    def set_compact_mode(self, enabled):
        self.compact_mode = enabled
        self.data["compact_mode"] = enabled
        self.save_compact_preferences()
        if enabled:
            self.position_compact()
            self.hide()
        self.update_indicator()

    def badged_icon(self, color):
        """App icon with a status dot, so the tray shows when it is recording."""
        pixmap = self.app_icon.pixmap(64, 64)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#101014"), 5))
        painter.setBrush(QColor(color))
        painter.drawEllipse(34, 34, 27, 27)
        painter.end()
        return QIcon(pixmap)

    def build_navigation(self, shell):
        row = QHBoxLayout()
        row.setContentsMargins(6, 0, 0, 0)
        row.setSpacing(10)
        logo = QLabel()
        logo.setPixmap(QPixmap(str(RESOURCES / "icon_squircle.png"))
            .scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo.setFixedSize(32, 36)
        row.addWidget(logo)
        wordmark = label("Blablabla")
        wordmark.setStyleSheet("font-size:17px;font-weight:700;color:#efeff4;")
        row.addWidget(wordmark)
        row.addStretch()
        navigation = QFrame()
        navigation.setObjectName("navigation")
        tabs = QHBoxLayout(navigation)
        tabs.setContentsMargins(4, 4, 4, 4)
        tabs.setSpacing(3)
        self.nav = []
        for index, (name, symbol) in enumerate((("Settings", "settings"), ("Transcripts", "transcripts"), ("Permissions", "permissions"))):
            item = button("", lambda checked=False, i=index: self.select_page(i))
            item.setProperty("role", "nav")
            item.setCheckable(True)
            item.setMinimumWidth((118, 145, 132)[index])
            item.setAccessibleName(name)
            item.setToolTip(name)
            contents = QHBoxLayout(item)
            contents.setContentsMargins(10, 0, 10, 0)
            contents.setSpacing(7)
            image = QLabel()
            image.setFixedSize(18, 18)
            image.setPixmap(icon(symbol, size=16).pixmap(18, 18))
            caption = label(name)
            contents.addWidget(image)
            contents.addWidget(caption)
            badge = label("", "badge")
            badge.hide()
            contents.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
            self.nav.append((item, image, caption, badge, symbol))
            tabs.addWidget(item)
        row.addWidget(navigation)
        self.status_dot = label("\u25cf")
        self.status_dot.setFixedWidth(10)
        self.status_dot.setToolTip("Dictation status")
        row.addWidget(self.status_dot)
        shell.addLayout(row)

    def page(self, title, clear=False, refresh=False):
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("page")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(24, 26, 24, 28)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        header = QHBoxLayout()
        header.addWidget(label(title, "title"))
        if clear:
            self.history_count = label("", "detail")
            self.history_count.setProperty("role", "badge")
            header.addWidget(self.history_count, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addStretch()
        if clear:
            self.clear_button = button("Clear history", self.clear_history, True)
            header.addWidget(self.clear_button)
        elif refresh:
            header.addWidget(button("Refresh", self.refresh_permissions))
        layout.addLayout(header)
        subtitle = label({"Settings": "Make dictation work the way you do.",
            "Transcripts": "Your words, ready to use. Copy any transcript in one click.",
            "Permissions": "Check what Blablabla needs to capture and deliver your words."}[title], "detail")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        scroll.setWidget(body)
        self.pages.addWidget(scroll)
        return scroll, layout

    def card(self, title, parent_layout=None):
        frame = QFrame()
        frame.setObjectName("card")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)
        if title:
            layout.addWidget(label(title, "section"))
        (parent_layout or self.settings_layout).addWidget(frame)
        return layout

    def switch_row(self, layout, title, detail, key, default=False):
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label(title, "row"))
        subtitle = label(detail, "detail")
        subtitle.setWordWrap(True)
        text.addWidget(subtitle)
        row.addLayout(text, 1)
        toggle = Switch(title, self.data.get(key, default))
        self.settings_controls.append(toggle)
        row.addWidget(toggle)
        layout.addLayout(row)
        toggle.toggled.connect(lambda: self.persist_settings())
        return toggle

    def build_settings(self):
        general = self.card("General")
        self.launch_login = self.switch_row(general, "Launch at login",
            "Start Blablabla automatically when you log in", "launch_login")
        self.launch_login.toggled.disconnect()
        self.launch_login.toggled.connect(self.set_launch_login)
        general.addWidget(divider())
        self.minimize_tray = self.switch_row(general, "Minimize to tray",
            "Keep Blablabla available in the system tray", "minimize_tray")
        general.addWidget(divider())
        self.copy_after = self.switch_row(general, "Also copy to clipboard",
            "Keep transcript in clipboard as fallback after pasting", "copy_after")

        api = self.card("AssemblyAI API Key")
        api_row = QHBoxLayout()
        api_row.setSpacing(10)
        api_row.addWidget(self.key, 1)
        api_row.addWidget(self.key_mask, 1)
        self.edit_key_button = button("Edit", self.edit_key)
        api_row.addWidget(self.edit_key_button)
        api.addLayout(api_row)
        api.addWidget(button("Get a free API key at assemblyai.com ↗",
            lambda: self.open_url("https://www.assemblyai.com/dashboard/signup"), True), 0, Qt.AlignmentFlag.AlignLeft)
        self.settings_controls.extend((self.key, self.edit_key_button))

        usage = self.card(None)
        usage_header = QHBoxLayout()
        usage_header.addWidget(label("Usage", "section"))
        usage_header.addStretch()
        usage_header.addWidget(button("View on AssemblyAI ↗",
            lambda: self.open_url("https://www.assemblyai.com/app/usage"), True))
        usage.addLayout(usage_header)
        stats = QHBoxLayout()
        stats.setSpacing(20)
        self.usage_sessions = label("0", "stat")
        self.usage_duration = label("0m", "stat")
        for value, name in ((self.usage_sessions, "Sessions"), (self.usage_duration, "Duration")):
            column = QVBoxLayout()
            column.setSpacing(3)
            column.addWidget(value)
            column.addWidget(label(name, "detail"))
            stats.addLayout(column)
        stats.addStretch()
        usage.addLayout(stats)
        footer = QHBoxLayout()
        footer.addWidget(label("Local tracking · check dashboard for exact usage", "detail"), 1)
        reset_usage = button("Reset", self.reset_usage)
        self.settings_controls.append(reset_usage)
        footer.addWidget(reset_usage)
        usage.addLayout(footer)

        shortcut = self.card("Shortcut")
        keys_row = QHBoxLayout()
        keys_row.setSpacing(6)
        self.keycaps = QHBoxLayout()
        self.keycaps.setSpacing(6)
        keys_row.addLayout(self.keycaps)
        keys_row.addStretch()
        record = button("Record", self.record_shortcut)
        reset = button("Reset", lambda: self.change_shortcut(3, 0x20, "Ctrl + Alt + Space"))
        self.settings_controls.extend((record, reset))
        keys_row.addWidget(record)
        keys_row.addWidget(reset)
        shortcut.addLayout(keys_row)
        self.refresh_keycaps()
        shortcut.addWidget(divider())
        shortcut.addWidget(label("Tap to start and tap again to finish, or hold it while you speak.", "detail"))

        microphone = self.card("Microphone")
        mic_row = QHBoxLayout()
        self.device_combo = ComboBox()
        self.device_combo.setSizeAdjustPolicy(ComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.device_combo.setMinimumContentsLength(16)
        self.device_combo.setMinimumWidth(0)
        self.device_combo.setAccessibleName("Microphone")
        mic_row.addWidget(self.device_combo, 1)
        self.refresh_mic_button = button("Refresh", self.refresh_devices)
        mic_row.addWidget(self.refresh_mic_button)
        microphone.addLayout(mic_row)
        self.settings_controls.extend((self.device_combo, self.refresh_mic_button))
        self.device_combo.currentIndexChanged.connect(lambda: self.persist_settings())

        sounds = self.card(None)
        sound_header = QHBoxLayout()
        sound_header.addWidget(label("Sound Effects", "section"), 1)
        self.sounds_enabled = Switch("Sound Effects", self.data.get("sounds_enabled", True))
        sound_header.addWidget(self.sounds_enabled)
        sounds.addLayout(sound_header)
        self.sound_options = QWidget()
        sound_rows = QVBoxLayout(self.sound_options)
        sound_rows.setContentsMargins(0, 0, 0, 0)
        sound_rows.setSpacing(10)
        sound_rows.addWidget(divider())
        self.sound_pickers = {}
        self.sound_previews = {}
        for title, key, default in (("Start recording", "start_sound", "SystemAsterisk"),
                                    ("Stop recording", "stop_sound", "SystemExclamation")):
            row = QHBoxLayout()
            row.addWidget(label(title, "row"), 1)
            picker = ComboBox()
            picker.setAccessibleName(f"{title} sound")
            for name, sound in SOUNDS:
                picker.addItem(name, sound)
            picker.setCurrentIndex(max(0, picker.findData(self.data.get(key, default))))
            picker.setFixedWidth(180)
            row.addWidget(picker)
            preview = button("Play", lambda checked=False, box=picker: self.play_sound(box.currentData()))
            preview.setProperty("role", "preview")
            preview.setIcon(icon("play", "#f2f2f7", 18))
            preview.setMinimumSize(92, 42)
            preview.setAccessibleName(f"Play {title.lower()} sound")
            preview.setToolTip(f"Preview {title.lower()} sound")
            self.sound_previews[key] = preview
            preview.setEnabled(picker.currentData() != "None")
            row.addWidget(preview)
            sound_rows.addLayout(row)
            self.sound_pickers[key] = picker
            picker.currentTextChanged.connect(lambda: self.persist_settings())
            picker.currentIndexChanged.connect(lambda _, box=picker, action=preview:
                action.setEnabled(box.currentData() != "None"))
            self.settings_controls.extend((picker, preview))
        sounds.addWidget(self.sound_options)
        self.sound_options.setVisible(self.sounds_enabled.isChecked())
        self.sounds_enabled.toggled.connect(self.sound_options.setVisible)
        self.sounds_enabled.toggled.connect(lambda: self.persist_settings())
        self.settings_controls.append(self.sounds_enabled)

        indicator = self.card("Recording Indicator")
        self.indicator_only_recording = self.switch_row(indicator, "Show only when recording",
            "Hide the indicator when idle, show it during recording", "indicator_only_recording")
        indicator.addWidget(divider())
        self.free_position = self.switch_row(indicator, "Allow free positioning",
            "Drag the indicator anywhere on screen", "free_position")
        indicator.addWidget(divider())
        self.live_text = self.switch_row(indicator, "Show live text",
            "Show the words as you speak next to the indicator", "live_text", True)
        self.indicator_only_recording.toggled.connect(lambda: self.update_indicator())
        self.free_position.toggled.connect(self.set_indicator_draggable)
        self.reset_position_button = button("Reset to default", self.reset_indicator_position)
        indicator.addWidget(self.reset_position_button, 0, Qt.AlignmentFlag.AlignRight)
        self.reset_position_button.setVisible(bool(self.data.get("indicator_position")))
        self.settings_controls.append(self.reset_position_button)

        output = self.card("Text Insertion")
        self.copy_only = self.switch_row(output, "Clipboard only",
            "Copy the transcript without typing into another app", "copy_only")

        updates = self.card("Updates")
        row = QHBoxLayout()
        descriptions = QVBoxLayout()
        descriptions.setSpacing(2)
        descriptions.addWidget(label(f"Blablabla {APP_VERSION} · Windows preview", "row"))
        self.update_detail = label("Checks GitHub for new Windows releases", "detail")
        descriptions.addWidget(self.update_detail)
        row.addLayout(descriptions, 1)
        self.update_url = None
        self.update_button = button("Check for updates", lambda: self.open_url(self.update_url)
            if self.update_url else self.check_updates(manual=True))
        row.addWidget(self.update_button)
        updates.addLayout(row)
        updates.addWidget(button("View project ↗", lambda: self.open_url(f"https://github.com/{UPDATE_REPO}"), True),
            0, Qt.AlignmentFlag.AlignLeft)
        # Put the controls that make dictation work before background preferences.
        for section in (api, microphone, shortcut, output, indicator, general, sounds, usage, updates):
            frame = section.parentWidget()
            self.settings_layout.removeWidget(frame)
            self.settings_layout.addWidget(frame)

    def build_transcripts(self):
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search your transcripts")
        self.search.setAccessibleName("Search transcripts")
        self.search.setMinimumHeight(44)
        self.search.addAction(icon("search", size=14), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.search_history)
        self.transcripts_layout.addWidget(self.search)
        self.live_card = QFrame()
        self.live_card.setObjectName("card")
        live = QVBoxLayout(self.live_card)
        live.setContentsMargins(20, 18, 20, 18)
        live_header = QHBoxLayout()
        live_header.addWidget(label("Live transcript", "section"), 1)
        self.live_copy = self.copy_button(lambda: self.current_text, "Copy live transcript")
        self.live_copy.setEnabled(False)
        live_header.addWidget(self.live_copy)
        live.addLayout(live_header)
        self.preview = label("Start speaking…")
        self.preview.setWordWrap(True)
        self.preview.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        live.addWidget(self.preview)
        self.transcripts_layout.addWidget(self.live_card)
        self.live_card.hide()
        self.history_container = QWidget()
        self.history_layout = QVBoxLayout(self.history_container)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(16)
        self.transcripts_layout.addWidget(self.history_container)
        self.empty_history = label("No transcripts yet")
        self.empty_history.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_history.setWordWrap(True)
        self.empty_history.setStyleSheet("color:#a3a3af;padding:48px 12px;font-size:14px;")
        self.transcripts_layout.addWidget(self.empty_history)
        self.more_button = button("Show more", self.show_more)
        self.transcripts_layout.addWidget(self.more_button)

    def copy_button(self, text, name):
        widget = button("Copy text", lambda: self.copy(text(), widget))
        widget.setProperty("role", "copy")
        widget.setIcon(icon("copy", "#75eaf7", 16))
        widget.setMinimumSize(118, 42)
        widget.setAccessibleName(name)
        widget.setToolTip(name)
        widget.reset_feedback = QTimer(widget)
        widget.reset_feedback.setSingleShot(True)
        widget.reset_feedback.timeout.connect(lambda: self.reset_copy_button(widget))
        return widget

    @staticmethod
    def reset_copy_button(widget):
        widget.setText("Copy text")
        widget.setProperty("copied", False)
        widget.setIcon(icon("copy", "#75eaf7", 16))
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def build_permissions(self):
        permissions = self.card(None, self.permissions_layout)
        self.microphone_permission = self.permission_row(permissions, "Microphone", YELLOW,
            "Check access in Windows privacy settings", button("Settings", lambda: self.open_url("ms-settings:privacy-microphone")))
        permissions.addWidget(divider())
        self.permission_row(permissions, "Text insertion", GREEN,
            "Available · apps must use the same privilege level")
        permissions.addWidget(divider())
        self.shortcut_permission = self.permission_row(permissions, "Global shortcut",
            GREEN if self.hotkey.registered else YELLOW,
            "Available" if self.hotkey.registered else "Shortcut is already used by another app")
        self.permissions_layout.addWidget(label("Audio is sent directly to AssemblyAI. Transcripts stay on this PC.", "detail"))

    def permission_row(self, layout, title, color, detail, action=None):
        row = QHBoxLayout()
        row.setSpacing(10)
        dot = label("●")
        dot.setStyleSheet(f"color:{color};font-size:12px;")
        row.addWidget(dot)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label(title, "section"))
        description = label(detail, "detail")
        description.setWordWrap(True)
        text.addWidget(description)
        row.addLayout(text, 1)
        if action:
            row.addWidget(action)
        row.setContentsMargins(0, 4, 0, 4)
        layout.addLayout(row)
        return dot, description

    def select_page(self, index):
        if index != self.pages.currentIndex() and self.isVisible():
            self.fade_in(self.pages.widget(index))
        self.pages.setCurrentIndex(index)
        for number, (item, image, caption, badge, symbol) in enumerate(self.nav):
            selected = number == index
            item.setChecked(selected)
            caption.setStyleSheet(f"font-size:13px;font-weight:600;color:{'#e8faff' if selected else '#a3a3af'};")
            image.setPixmap(icon(symbol, CYAN if selected else "#a3a3af", 16).pixmap(18, 18))

    def fade_in(self, widget):
        self.page_fade.stop()
        self.end_fade()
        duration = motion_duration(160)
        if not duration:
            return
        self.page_fade.setDuration(duration)
        self.fading = widget
        widget.setGraphicsEffect(QGraphicsOpacityEffect(widget, opacity=0.0))
        self.page_fade.start()

    def fade_step(self, value):
        if self.fading is not None:
            self.fading.graphicsEffect().setOpacity(value)

    def end_fade(self):
        # Drop the effect afterwards: it would slow down scrolling.
        if self.fading is not None:
            self.fading.setGraphicsEffect(None)
            self.fading = None

    def set_status(self, message):
        self.status_message = message
        self.status_dot.setToolTip(message)
        self.session_status.setText(message)
        self.update_compact()
        color = YELLOW if self.state == "listening" else BRAND[0] if self.state in ("connecting", "stopping") else GREEN
        self.status_dot.setStyleSheet(f"color:{color};font-size:10px;")
        if hasattr(self, "indicator"):
            self.indicator.setToolTip(message + ("\n" + self.current_text if self.current_text else ""))
        if hasattr(self, "tray"):
            self.tray.setToolTip(f"Blablabla · {message}"[:127])  # Windows tooltip limit

    def refresh_devices(self):
        if self.state != "idle":
            return
        with QSignalBlocker(self.device_combo):
            self.device_combo.clear()
            self.device_combo.addItem("System Default", None)
            try:
                for index, device in enumerate(sd.query_devices()):
                    if device["max_input_channels"]:
                        host = sd.query_hostapis(device["hostapi"])["name"]
                        self.device_combo.addItem(f"{device['name']} ({host})", index)
                saved = self.data.get("device", "")
                selected = self.device_combo.findText(saved)
                self.device_combo.setCurrentIndex(max(0, selected))
                if self.device_combo.count() == 1 or (selected <= 0 and sd.default.device[0] < 0):
                    self.set_status("No default microphone. Choose one in Settings → Microphone.")
            except Exception as error:
                self.set_status(f"Cannot list microphones: {error}")

    def persist_settings(self):
        if self.state != "idle" or not hasattr(self, "copy_only"):
            return False
        try:
            self.data.update(api_key=native.protect_key(self.key.text().strip()),
                device=self.device_combo.currentText(), copy_only=self.copy_only.isChecked(),
                copy_after=self.copy_after.isChecked(), launch_login=self.launch_login.isChecked(),
                minimize_tray=self.minimize_tray.isChecked(), sounds_enabled=self.sounds_enabled.isChecked(),
                indicator_only_recording=self.indicator_only_recording.isChecked(), free_position=self.free_position.isChecked(),
                live_text=self.live_text.isChecked())
            for key, picker in self.sound_pickers.items():
                self.data[key] = picker.currentData()
            save_data(self.data)
            self.key.setModified(False)
            return True
        except Exception as error:
            QMessageBox.critical(self, "Could not save settings", str(error))
            return False

    def commit_key(self, force=False):
        if force or self.key.isModified():
            if self.persist_settings():
                if force:
                    self.update_key_display()

    def key_edited(self, text):
        self.edit_key_button.setVisible(bool(text))
        self.edit_key_button.setText("Done")

    def edit_key(self):
        if self.key.isVisible() and self.key.text():
            self.commit_key(force=True)
        else:
            self.key_mask.hide()
            self.key.show()
            self.edit_key_button.setText("Done")
            self.key.setFocus()

    def update_key_display(self):
        key = self.key.text().strip()
        self.key.setVisible(not key)
        self.key_mask.setVisible(bool(key))
        self.key_mask.setText(key[:4] + "•" * max(0, min(20, len(key)-8)) + key[-4:] if len(key) > 8 else "•" * len(key))
        self.edit_key_button.setVisible(bool(key))
        self.edit_key_button.setText("Edit")

    def set_launch_login(self, enabled):
        previous = self.data.get("launch_login", False)
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as run:
                if enabled:
                    executable = sys.executable if getattr(sys, "frozen", False) else str(Path(sys.executable).with_name("pythonw.exe"))
                    arguments = [executable] if getattr(sys, "frozen", False) else [executable, str(Path(__file__).resolve())]
                    winreg.SetValueEx(run, "Blablabla", 0, winreg.REG_SZ, subprocess.list2cmdline(arguments))
                else:
                    try:
                        winreg.DeleteValue(run, "Blablabla")
                    except FileNotFoundError:
                        pass
            self.persist_settings()
        except OSError as error:
            with QSignalBlocker(self.launch_login):
                self.launch_login.setChecked(previous)
            QMessageBox.critical(self, "Could not change launch at login", str(error))

    def refresh_keycaps(self):
        clear_layout(self.keycaps)
        for name in self.data.get("shortcut_label", "Ctrl + Alt + Space").split(" + "):
            self.keycaps.addWidget(label(name, "keycap"))
        self.session_hint.setText(self.data.get("shortcut_label", "Ctrl + Alt + Space"))
        self.session_hint.setToolTip(self.session_hint.text())

    def change_shortcut(self, modifiers, key, description):
        old_modifiers = self.data.get("shortcut_modifiers", 3)
        old_key = self.data.get("shortcut_key", 0x20)
        self.hotkey.close()
        self.hotkey = native.Hotkey(modifiers, key)
        if not self.hotkey.registered:
            self.hotkey = native.Hotkey(old_modifiers, old_key)
            self.set_status("That shortcut is used by another app. Choose another one.")
            self.refresh_permissions()
            return False
        self.data.update(shortcut_modifiers=modifiers, shortcut_key=key, shortcut_label=description)
        self.refresh_keycaps()
        self.persist_settings()
        self.refresh_permissions()
        return True

    def record_shortcut(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Record Shortcut")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(label("Record a new shortcut", "section"))
        layout.addWidget(label("Press a key with Ctrl, Alt, Shift or Win.", "detail"))
        recorder = QKeySequenceEdit()
        recorder.setMaximumSequenceLength(1)
        recorder.setFixedHeight(40)
        layout.addWidget(recorder)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        layout.addWidget(actions)
        recorder.setFocus()
        self.hotkey.close()
        try:
            result = dialog.exec()
        finally:
            self.hotkey = native.Hotkey(self.data.get("shortcut_modifiers", 3), self.data.get("shortcut_key", 0x20))
            self.refresh_permissions()
        if result != QDialog.DialogCode.Accepted or recorder.keySequence().isEmpty():
            return
        combination = recorder.keySequence()[0]
        qt_modifiers = combination.keyboardModifiers()
        modifiers = (1 if qt_modifiers & Qt.KeyboardModifier.AltModifier else 0) | \
            (2 if qt_modifiers & Qt.KeyboardModifier.ControlModifier else 0) | \
            (4 if qt_modifiers & Qt.KeyboardModifier.ShiftModifier else 0) | \
            (8 if qt_modifiers & Qt.KeyboardModifier.MetaModifier else 0)
        qt_key = int(combination.key())
        special = {int(Qt.Key.Key_Space): 0x20, int(Qt.Key.Key_Return): 0x0D,
            int(Qt.Key.Key_Tab): 9, int(Qt.Key.Key_Escape): 0x1B,
            int(Qt.Key.Key_Backspace): 8, int(Qt.Key.Key_Delete): 0x2E}
        key = qt_key if 0x30 <= qt_key <= 0x5A else special.get(qt_key)
        if int(Qt.Key.Key_F1) <= qt_key <= int(Qt.Key.Key_F12):
            key = 0x70 + qt_key - int(Qt.Key.Key_F1)
        if not modifiers or key is None:
            self.set_status("Use Ctrl/Alt/Shift/Win with a letter, number, F1–F12 or Space.")
            return
        description = recorder.keySequence().toString(QKeySequence.SequenceFormat.NativeText).replace("+", " + ")
        self.change_shortcut(modifiers, key, description)

    def update_usage(self):
        self.usage_sessions.setText(str(self.data.get("session_count", len(self.data.get("history", [])))))
        minutes = int(self.data.get("duration_seconds", 0)) // 60
        self.usage_duration.setText(f"{minutes//60}h {minutes%60}m" if minutes >= 60 else f"{minutes}m")

    def reset_usage(self):
        self.data.update(session_count=0, duration_seconds=0)
        self.persist_settings()
        self.update_usage()

    def search_history(self):
        self.display_limit = 10
        self.refresh_history()

    def show_more(self):
        self.display_limit += 10
        self.refresh_history()

    def refresh_history(self):
        clear_layout(self.history_layout)
        history = self.data.get("history", [])
        query = self.search.text().casefold()
        filtered = [record for record in history if query in record["text"].casefold()]
        self.history_count.setText(str(len(filtered)))
        self.clear_button.setVisible(bool(history))
        self.empty_history.setVisible(not filtered)
        self.empty_history.setText("No matching transcripts. Try another word or clear the search." if query else
            "Your next idea starts here.\nStart dictation and your transcript will appear in this space.")
        self.more_button.setVisible(len(filtered) > self.display_limit)
        self.more_button.setText(f"Show more ({max(0, len(filtered)-self.display_limit)})")
        badge = self.nav[1][3]
        badge.setText(str(len(history)))
        badge.setVisible(bool(history))
        for record in filtered[:self.display_limit]:
            row = self.card(None, self.history_layout)
            header = QHBoxLayout()
            try:
                timestamp = datetime.datetime.fromisoformat(record["date"])
                day = timestamp.date()
                today = datetime.date.today()
                date_text = "Today" if day == today else "Yesterday" if day == today - datetime.timedelta(days=1) else day.strftime("%d %b %Y")
                date_text += timestamp.strftime(" · %H:%M")
            except (ValueError, TypeError):
                date_text = str(record.get("date", ""))
            date = label(date_text, "detail")
            header.addWidget(date)
            header.addStretch()
            header.addWidget(self.copy_button(lambda value=record["text"]: value, f"Copy transcript from {date_text}"))
            row.addLayout(header)
            text = label(record["text"])
            text.setWordWrap(True)
            text.setMinimumWidth(0)
            text.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            text.setStyleSheet("font-size:15px;color:#ededf2;padding:2px 0;")
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
            row.addWidget(text)
            footer = QHBoxLayout()
            partial = record.get("partial")
            tag = "Partial · review before using" if partial else "Pasted to app" if record.get("inserted") else "Saved on this PC"
            status = label(tag, "detail")
            status.setStyleSheet(f"font-size:11px;color:{YELLOW if partial else GREEN if record.get('inserted') else '#a3a3af'};")
            footer.addWidget(status)
            footer.addStretch()
            words = len(record["text"].split())
            footer.addWidget(label(f"{words} {'word' if words == 1 else 'words'}", "detail"))
            row.addLayout(footer)

    def clear_history(self):
        if self.state != "idle":
            return
        if QMessageBox.question(self, "Clear transcripts", "Delete all locally saved transcripts?") != QMessageBox.StandardButton.Yes:
            return
        previous = self.data.get("history", [])
        self.data["history"] = []
        try:
            save_data(self.data)
        except OSError as error:
            self.data["history"] = previous
            QMessageBox.critical(self, "Could not clear transcripts", str(error))
        self.refresh_history()

    def refresh_permissions(self):
        dot, description = self.shortcut_permission
        dot.setStyleSheet(f"color:{GREEN if self.hotkey.registered else YELLOW};font-size:12px;")
        description.setText("Available" if self.hotkey.registered else "Shortcut is already used by another app")
        self.refresh_devices()

    def toggle(self):
        if self.closing or QApplication.activeModalWidget() is not None:
            return
        if self.state in ("connecting", "listening"):
            self.state = "stopping"
            self.set_status("Finalizing transcript…")
            self.session.stop()
            self.update_recording_controls()
            return
        if self.state != "idle":
            return
        if not self.key.text().strip():
            self.set_status("Add your API key in Settings before dictating.")
            self.select_page(0)
            self.show_window()
            self.key.setFocus()
            return
        if not self.persist_settings():
            return
        current = native.foreground()
        self.target = self.last_target if native.is_our_window(current) else current
        self.session_copy_only = self.copy_only.isChecked()
        self.session_copy_after = self.copy_after.isChecked()
        self.state = "connecting"
        self.current_text = ""
        self.recorded_seconds = None
        self.cloud_connected = False
        self.live_copy.setEnabled(False)
        self.reset_copy_button(self.live_copy)
        self.preview.setText("Start speaking…")
        self.live_card.show()
        self.set_status("Starting…")
        self.position_indicator()
        self.update_recording_controls()
        self.session = Session(self.key.text().strip(), self.device_combo.currentData(), self.events)
        self.session.start()

    def shortcut_pressed(self):
        """Tap toggles; holding the shortcut records until it is released."""
        starting = self.state == "idle"
        self.toggle()
        self.held_since = time.monotonic() if starting and self.state != "idle" else None

    def poll(self):
        current = native.foreground()
        if current and not native.is_our_window(current):
            self.last_target = current
        if self.hotkey.poll():
            self.shortcut_pressed()
        if self.held_since is not None and not native.key_down(self.data.get("shortcut_key", 0x20)):
            held = time.monotonic() - self.held_since
            self.held_since = None
            if held >= HOLD_TO_TALK and self.state in ("connecting", "listening"):
                self.toggle()
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "listening" and self.state == "connecting":
                self.state = "listening"
                self.started_at = time.monotonic()
                dot, description = self.microphone_permission
                dot.setStyleSheet(f"color:{GREEN};font-size:12px;")
                description.setText("Granted · microphone is recording")
                self.set_status("Recording your voice while transcription connects…")
                self.feedback("start_sound")
                self.update_recording_controls()
            elif kind == "update":
                self.show_update(*value)
            elif kind == "connected":
                self.cloud_connected = True
                if self.state == "listening":
                    self.set_status("Listening… tap the shortcut or release it to finish.")
                    self.update_recording_controls()
            elif kind == "duration":
                self.recorded_seconds = value
            elif kind == "level":
                self.indicator.level = value
                self.audio_meter.set_level(value if self.state == "listening" else 0)
                self.compact.meter.set_level(value if self.state == "listening" else 0)
            elif kind == "transcript":
                self.current_text = value
                self.live_copy.setEnabled(bool(value))
                self.preview.setText(value)
                self.set_status(self.status_message)
                if value and self.live_text.isChecked() and self.indicator.isVisible():
                    self.caption.show_text(value, self.indicator.geometry())
            elif kind == "stopping":
                self.state = "stopping"
                self.set_status(value)
                self.update_recording_controls()
            elif kind == "finished":
                self.finish(*value)
        if self.closing and self.session is None:
            self.dispose()
            QApplication.instance().quit()

    def finish(self, text, error):
        self.state = "idle"
        self.session = None
        self.current_text = text
        self.live_copy.setEnabled(bool(text))
        self.live_card.hide()
        self.preview.setText(text)
        if self.started_at is not None:
            duration = self.recorded_seconds if self.recorded_seconds is not None else time.monotonic() - self.started_at
            self.data["duration_seconds"] = self.data.get("duration_seconds", 0) + duration
            self.data["session_count"] = self.data.get("session_count", len(self.data.get("history", []))) + 1
            self.started_at = None
            self.feedback("stop_sound")
        if text:
            record = {"text": text, "date": datetime.datetime.now().isoformat(timespec="seconds"),
                      "inserted": False, "partial": bool(error)}
            self.data.setdefault("history", []).insert(0, record)
        try:
            save_data(self.data)
        except Exception as save_error:
            error = f"Could not save history: {save_error}. Copy the text from the window."
            self.live_card.setVisible(bool(text))
        if text and not error and not self.closing:
            if self.session_copy_only:
                self.copy(text)
            else:
                record["inserted"] = self.paste(text)
                self.set_status("Text inserted." if record["inserted"] else
                    "Text saved. Copy it from Transcripts.")
                try:
                    save_data(self.data)
                except OSError:
                    self.set_status("Text saved; could not update its insertion state.")
        elif not text:
            self.set_status("No speech detected. Ready to dictate.")
        if error:
            self.set_status(error)
            self.status_dot.setStyleSheet(f"color:{PINK};font-size:10px;")
            if not self.closing and not self.isVisible():
                # A notification instead of popping the whole window up.
                self.notice_page = 1  # Transcripts keeps the partial text
                self.tray.showMessage("Blablabla", error, QSystemTrayIcon.MessageIcon.Warning, 8000)
        elif text and not self.closing and not self.session_copy_only and not record.get("inserted") and not self.isVisible():
            self.notice_page = 1
            self.tray.showMessage("Transcript ready", "Open Transcripts to copy your text.", QSystemTrayIcon.MessageIcon.Information, 5000)
        self.refresh_history()
        self.update_usage()
        self.update_recording_controls()

    def update_recording_controls(self):
        stopping = self.state == "stopping"
        active = self.state in ("connecting", "listening")
        text = "Finalizing…" if stopping else "Stop dictation" if active else "Start dictation"
        self.button.setText(text)
        self.button.setEnabled(not stopping and not self.closing)
        self.button.setProperty("role", "stop" if active else "primary")
        self.button.setIcon(icon("stop" if active else "mic", "#260b18" if active else "#092328", 17))
        self.button.style().unpolish(self.button)
        self.button.style().polish(self.button)
        self.voice_panel.set_state(self.state)
        self.session_heading.setText({"idle": "Ready to dictate", "connecting": "Opening microphone…",
            "listening": "Listening to you" if self.cloud_connected else "Recording · connecting…",
            "stopping": "Finishing your transcript…"}[self.state])
        if not active:
            self.audio_meter.set_level(0)
            self.compact.meter.set_level(0)
        self.update_session_clock()
        self.tray_record_action.setText(text)
        self.tray_record_action.setEnabled(not stopping and not self.closing)
        for control in self.settings_controls:
            control.setEnabled(self.state == "idle" and not self.closing)
        for key, picker in self.sound_pickers.items():
            self.sound_previews[key].setEnabled(self.state == "idle" and not self.closing and picker.currentData() != "None")
        self.update_indicator()

    def update_indicator(self):
        self.tray.setIcon(self.tray_icons[self.state])
        self.indicator.state = self.state
        self.indicator.update()
        visible = not self.compact_mode and not self.closing and (self.state != "idle" or not self.indicator_only_recording.isChecked())
        self.indicator.setVisible(visible)
        self.update_compact()
        self.compact.setVisible(self.compact_mode and not self.closing)
        if self.state == "idle" or self.closing or self.compact_mode:
            self.caption.hide()

    def position_indicator(self):
        position = self.data.get("indicator_position") if self.free_position.isChecked() else None
        if position and QApplication.screenAt(QPoint(*position)):
            self.indicator.move(*position)
        else:
            screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
            bounds = screen.availableGeometry()
            self.indicator.move(bounds.center().x() - self.indicator.width()//2, bounds.bottom() - self.indicator.height() - 12)

    def set_indicator_draggable(self, enabled):
        self.indicator.draggable = enabled
        self.position_indicator()

    def save_indicator_position(self):
        self.data["indicator_position"] = [self.indicator.x(), self.indicator.y()]
        self.persist_settings()
        self.reset_position_button.show()

    def reset_indicator_position(self):
        self.data.pop("indicator_position", None)
        self.persist_settings()
        self.position_indicator()
        self.reset_position_button.hide()

    def paste(self, text):
        """Paste in one go via the clipboard, then restore what the user had there."""
        clipboard = QApplication.clipboard()
        pending = self.pending_clipboard
        if pending and pending[1:] == (self.clipboard_revision, native.clipboard_sequence()):
            previous = pending[0]  # a rapid second paste still restores the original
        else:
            previous = QMimeData()
            source = clipboard.mimeData()
            for fmt in source.formats() if source else ():
                previous.setData(fmt, source.data(fmt))
        self.clipboard_timer.stop()
        clipboard.setText(text)
        self.pending_clipboard = (previous, self.clipboard_revision, native.clipboard_sequence())
        inserted = native.paste(self.target)
        if not self.session_copy_after:
            # The target reads the clipboard asynchronously; give it time first.
            self.clipboard_timer.start(1500)
        else:
            self.pending_clipboard = None
        return inserted

    def restore_clipboard(self):
        pending, self.pending_clipboard = self.pending_clipboard, None
        if pending and pending[1:] == (self.clipboard_revision, native.clipboard_sequence()):
            QApplication.clipboard().setMimeData(pending[0])

    def copy(self, text, source=None):
        if text:
            # An explicit copy must also cancel a pending restoration when the
            # user copies exactly the same text that was just pasted.
            self.clipboard_revision += 1
            self.clipboard_timer.stop()
            self.pending_clipboard = None
            QApplication.clipboard().setText(text)
            self.set_status("Copied to clipboard.")
            if source is not None:
                source.setText("Copied")
                source.setIcon(icon("check", "#85f497", 16))
                source.setProperty("copied", True)
                source.style().unpolish(source)
                source.style().polish(source)
                source.reset_feedback.start(1800)

    def feedback(self, key):
        if self.sounds_enabled.isChecked():
            self.play_sound(self.sound_pickers[key].currentData())

    @staticmethod
    def play_sound(name):
        if name != "None":
            try:
                if name.startswith("tone:"):
                    # Only known bundled tones can resolve a filename.
                    if name not in {value for _, value in SOUNDS}:
                        return
                    path = RESOURCES / "Sounds" / (name.removeprefix("tone:") + ".wav")
                    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                else:
                    winsound.PlaySound(name, winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            except RuntimeError:
                pass

    @staticmethod
    def open_url(url):
        QDesktopServices.openUrl(QUrl(url))

    def check_updates(self, manual=False):
        self.update_detail.setText("Checking for updates…")
        def work():
            try:
                result = newer_windows_release(fetch_releases())
            except Exception:
                result = "error"
            self.events.put(("update", (result, manual)))
        threading.Thread(target=work, daemon=True).start()

    def show_update(self, result, manual):
        if result == "error":
            self.update_detail.setText("Could not check for updates. Try again later.")
        elif result:
            tag, self.update_url = result
            self.update_detail.setText(f"{tag} is available")
            self.update_button.setText("Download ↗")
            if not manual and not self.isVisible():
                self.notice_page = 0
                self.tray.showMessage("Blablabla", f"{tag} is available. Open Settings → Updates to download it.")
        else:
            self.update_detail.setText("You're up to date")

    def show_window(self):
        if self.compact_mode:
            self.set_compact_mode(False)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def dark_titlebar(self):
        try:
            dwm = ctypes.WinDLL("dwmapi")
            dwm.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
            # Caption colour (BGR) matches the dark Mica tint, overriding the accent colour.
            for attribute, value in ((20, 1), (33, 2), (35, 0x00141010)):
                setting = ctypes.c_int(value)
                dwm.DwmSetWindowAttribute(int(self.winId()), attribute, ctypes.byref(setting), 4)
            if self.mica:
                margins = (ctypes.c_int * 4)(-1, -1, -1, -1)
                dwm.DwmExtendFrameIntoClientArea(ctypes.c_void_p(int(self.winId())), margins)
                backdrop = ctypes.c_int(2)  # DWMWA_SYSTEMBACKDROP_TYPE = Mica
                self.mica = dwm.DwmSetWindowAttribute(int(self.winId()), 38, ctypes.byref(backdrop), 4) == 0
            if self.mica:
                self.setStyleSheet(STYLE + MICA_STYLE)
        except OSError:
            pass

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized() and hasattr(self, "minimize_tray"):
            if self.minimize_tray.isChecked():
                QTimer.singleShot(0, self.hide)
        super().changeEvent(event)

    def closeEvent(self, event):
        if self.disposed:
            event.accept()
        elif self.minimize_tray.isChecked() and not self.closing:
            self.hide()
            event.ignore()
        else:
            event.ignore()
            self.request_shutdown()

    def request_shutdown(self):
        self.closing = True
        if self.session:
            self.session.stop()
            self.set_status("Closing the dictation session…")
            self.update_recording_controls()
        else:
            self.dispose()
            QApplication.instance().quit()

    def dispose(self):
        if self.disposed:
            return
        self.disposed = True
        self.closing = True
        self.poll_timer.stop()
        self.clock_timer.stop()
        self.clipboard_timer.stop()
        self.hotkey.close()
        QApplication.instance().removeNativeEventFilter(self.hotkey_filter)
        self.indicator.animation.stop()
        self.indicator.close()
        self.caption.close()
        self.compact.close()
        self.tray.hide()
        self.close()


def main():
    qt_app = QApplication(sys.argv)
    qt_app.setApplicationName("Blablabla")
    qt_app.setStyle("Fusion")
    qt_app.setFont(QFont("Segoe UI", 10))
    qt_app.setQuitOnLastWindowClosed(False)
    try:
        window = App()
    except Exception as error:
        QMessageBox.critical(None, "Blablabla could not start",
            f"{error}\n\nLocal data: {DATA_FILE}\nIf the file is damaged, keep a copy before moving it.")
        return 1
    if "--background" not in sys.argv and not window.compact_mode:
        window.show()
    QTimer.singleShot(3000, window.check_updates)
    return qt_app.exec()


if __name__ == "__main__":
    sys.exit(main())
