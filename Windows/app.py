"""Windows client, reproducing the original macOS layout with Qt."""
import ctypes
import datetime
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import time
import winreg
import winsound

from PySide6.QtCore import QAbstractNativeEventFilter, QEvent, QPoint, QSignalBlocker, Qt, QTimer, QUrl
from PySide6.QtGui import QCursor, QDesktopServices, QFont, QFontMetrics, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
    QKeySequenceEdit, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton,
    QScrollArea, QSizePolicy, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

import sounddevice as sd
import native
from speech import Session
from ui import BRAND, GREEN, PINK, YELLOW, STYLE, ComboBox, RecordingIndicator, Switch, divider, gradient_line, icon, label

DATA_FILE = Path(os.environ["LOCALAPPDATA"]) / "Blablabla" / "windows.json"
RESOURCES = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "Resources"


def load_data(path=DATA_FILE):
    if not path.exists():
        return {"api_key": "", "copy_only": False, "device": "", "history": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("history", []), list):
        raise ValueError("Formato de datos local inválido")
    return data


def save_data(data, path=DATA_FILE):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def button(text, action, text_only=False):
    widget = QPushButton(text)
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
        self.closing = self.disposed = self.collapsed = False
        self.display_limit = 10
        self.current_text = ""
        self.started_at = None
        self.settings_controls = []
        self.status_message = "Ready to dictate"
        self.setWindowTitle("Blablabla")
        self.resize(720, 760)
        self.setMinimumSize(700, 600)
        self.setStyleSheet(STYLE)
        self.app_icon = QIcon(str(RESOURCES / "icon_squircle.png"))
        self.setWindowIcon(self.app_icon)
        self.hotkey = native.Hotkey(self.data.get("shortcut_modifiers", 3), self.data.get("shortcut_key", 0x20))
        self.hotkey_filter = HotkeyFilter(self.toggle)
        QApplication.instance().installNativeEventFilter(self.hotkey_filter)
        try:
            key = native.unprotect_key(self.data.get("api_key", ""))
        except Exception:
            key = ""
            self.status_message = "Vuelve a introducir la clave API: no se pudo descifrar para este usuario."
        self.key = QLineEdit(key)
        self.key.setPlaceholderText("Paste your AssemblyAI key")
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setAccessibleName("AssemblyAI API key")
        self.key.editingFinished.connect(self.commit_key)
        self.key.textEdited.connect(self.key_edited)
        self.key_mask = label("")
        self.key_mask.setStyleSheet("background:#242429;border-radius:8px;padding:8px;color:#85858d;font-family:Consolas;")

        central = QWidget()
        self.setCentralWidget(central)
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(200)
        shell.addWidget(self.sidebar)
        self.build_sidebar()
        self.pages = QStackedWidget()
        shell.addWidget(self.pages, 1)
        self.settings_page, self.settings_layout = self.page("Settings")
        self.transcripts_page, self.transcripts_layout = self.page("Transcripts", clear=True)
        self.permissions_page, self.permissions_layout = self.page("Permissions", refresh=True)
        self.build_settings()
        self.build_transcripts()
        self.build_permissions()
        self.select_page(0)

        self.indicator = RecordingIndicator()
        self.indicator.clicked.connect(self.toggle)
        self.indicator.position_changed.connect(self.save_indicator_position)
        self.indicator.draggable = self.free_position.isChecked()
        self.position_indicator()
        self.tray = QSystemTrayIcon(self.app_icon, self)
        self.tray.setToolTip("Blablabla")
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
        self.refresh_devices()
        self.refresh_history()
        self.update_usage()
        self.update_key_display()
        if not self.hotkey.registered:
            self.status_message = "El atajo está ocupado. Usa el indicador o configura otro atajo."
        self.set_status(self.status_message)
        self.update_indicator()
        self.dark_titlebar()

    def build_sidebar(self):
        column = QVBoxLayout(self.sidebar)
        column.setContentsMargins(10, 10, 10, 0)
        column.setSpacing(0)
        top = QHBoxLayout()
        top.addStretch()
        self.collapse_button = button("", self.toggle_sidebar, True)
        self.collapse_button.setIcon(icon("sidebar", size=14))
        self.collapse_button.setFixedSize(26, 26)
        self.collapse_button.setToolTip("Collapse sidebar")
        top.addWidget(self.collapse_button)
        column.addLayout(top)
        self.brand = QWidget()
        branding = QVBoxLayout(self.brand)
        branding.setContentsMargins(0, 0, 0, 16)
        branding.setSpacing(5)
        logo = QLabel()
        logo.setPixmap(QPixmap(str(RESOURCES / "Assets.xcassets/LogoWave.imageset/logo_wave.png"))
            .scaled(90, 55, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setFixedHeight(55)
        branding.addWidget(logo)
        title = label("Blablabla")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:14px;font-weight:600;color:#e5e5e8;")
        branding.addWidget(title)
        version = label("Windows preview", "detail")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("font-size:10px;color:#54545b;")
        branding.addWidget(version)
        column.addWidget(self.brand)
        gradient_container = QWidget()
        gradient_layout = QHBoxLayout(gradient_container)
        gradient_layout.setContentsMargins(10, 0, 10, 0)
        gradient_layout.addWidget(gradient_line())
        column.addWidget(gradient_container)
        column.addSpacing(14)
        self.nav = []
        for index, (name, symbol) in enumerate((("Settings", "settings"), ("Transcripts", "transcripts"), ("Permissions", "permissions"))):
            item = button("", lambda checked=False, i=index: self.select_page(i))
            item.setProperty("role", "nav")
            item.setCheckable(True)
            item.setFixedHeight(34)
            item.setAccessibleName(name)
            item.setToolTip(name)
            row = QHBoxLayout(item)
            row.setContentsMargins(10, 0, 10, 0)
            row.setSpacing(9)
            image = QLabel()
            image.setFixedSize(18, 18)
            image.setPixmap(icon(symbol, size=14).pixmap(18, 18))
            caption = label(name)
            row.addWidget(image)
            row.addWidget(caption)
            row.addStretch()
            badge = label("", "badge")
            badge.hide()
            row.addWidget(badge)
            self.nav.append((item, image, caption, badge, symbol))
            column.addWidget(item)
            column.addSpacing(2)
        column.addStretch()
        column.addWidget(divider())
        status_row = QHBoxLayout()
        status_row.setContentsMargins(4, 10, 4, 10)
        status_row.setSpacing(6)
        self.status_dot = label("●")
        self.status_dot.setStyleSheet(f"color:{GREEN};font-size:10px;")
        self.status_dot.setFixedWidth(8)
        self.status_label = label("", "detail")
        self.status_label.setMinimumWidth(0)
        status_row.addWidget(self.status_dot)
        status_row.addWidget(self.status_label, 1)
        column.addLayout(status_row)

    def page(self, title, clear=False, refresh=False):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("page")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        header = QHBoxLayout()
        header.addWidget(label(title, "title"))
        if clear:
            self.history_count = label("", "detail")
            self.history_count.setStyleSheet("font-size:14px;font-weight:600;color:#66666d;")
            header.addWidget(self.history_count)
        header.addStretch()
        if clear:
            self.clear_button = button("Clear All", self.clear_history)
            header.addWidget(self.clear_button)
        elif refresh:
            header.addWidget(button("Refresh", self.refresh_permissions))
        else:
            self.button = button("Start dictation", self.toggle)
            self.button.setIcon(icon("mic", "#bdbdc5", 12))
            header.addWidget(self.button)
        layout.addLayout(header)
        scroll.setWidget(body)
        self.pages.addWidget(scroll)
        return scroll, layout

    def card(self, title, parent_layout=None):
        frame = QFrame()
        frame.setObjectName("card")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
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
        shortcut.addWidget(label("Press once to record. Press again to finish.", "detail"))

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
        for title, key, default in (("Start recording", "start_sound", "SystemAsterisk"),
                                    ("Stop recording", "stop_sound", "SystemExclamation")):
            row = QHBoxLayout()
            row.addWidget(label(title, "row"), 1)
            picker = ComboBox()
            for name, sound in (("None", "None"), ("Chime", "SystemAsterisk"),
                                ("Notification", "SystemExclamation"), ("Alert", "SystemHand")):
                picker.addItem(name, sound)
            picker.setCurrentIndex(max(0, picker.findData(self.data.get(key, default))))
            picker.setFixedWidth(140)
            row.addWidget(picker)
            preview = button("▶", lambda checked=False, box=picker: self.play_sound(box.currentData()))
            preview.setFixedWidth(28)
            row.addWidget(preview)
            sound_rows.addLayout(row)
            self.sound_pickers[key] = picker
            picker.currentTextChanged.connect(lambda: self.persist_settings())
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
        descriptions.addWidget(label("Windows preview", "row"))
        descriptions.addWidget(label("Follow the project for new Windows releases", "detail"))
        row.addLayout(descriptions, 1)
        row.addWidget(button("View project ↗", lambda: self.open_url("https://github.com/arturogj92/blablabla")))
        updates.addLayout(row)

    def build_transcripts(self):
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.addAction(icon("search", size=14), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.setStyleSheet("background:#1c1c21;")
        self.search.textChanged.connect(self.search_history)
        self.transcripts_layout.addWidget(self.search)
        self.live_card = QFrame()
        self.live_card.setObjectName("card")
        live = QVBoxLayout(self.live_card)
        live.setContentsMargins(16, 16, 16, 16)
        live.addWidget(label("Live transcript", "section"))
        self.preview = label("Start speaking…")
        self.preview.setWordWrap(True)
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        live.addWidget(self.preview)
        live.addWidget(button("Copy", lambda: self.copy(self.current_text), True), 0, Qt.AlignmentFlag.AlignRight)
        self.transcripts_layout.addWidget(self.live_card)
        self.live_card.hide()
        self.history_container = QWidget()
        self.history_layout = QVBoxLayout(self.history_container)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.setSpacing(8)
        self.transcripts_layout.addWidget(self.history_container)
        self.empty_history = label("No transcripts yet")
        self.empty_history.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_history.setStyleSheet("color:#48484f;padding:50px 0;font-size:13px;")
        self.transcripts_layout.addWidget(self.empty_history)
        self.more_button = button("Show more", self.show_more, True)
        self.transcripts_layout.addWidget(self.more_button)

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
        self.pages.setCurrentIndex(index)
        for number, (item, image, caption, badge, symbol) in enumerate(self.nav):
            selected = number == index
            item.setChecked(selected)
            caption.setStyleSheet(f"font-size:13px;font-weight:500;color:{'#ffffff' if selected else '#797980'};")
            image.setPixmap(icon(symbol, "#e5e5e9" if selected else "#797980", 14).pixmap(18, 18))

    def toggle_sidebar(self):
        self.collapsed = not self.collapsed
        self.sidebar.setFixedWidth(54 if self.collapsed else 200)
        self.brand.setVisible(not self.collapsed)
        self.status_label.setVisible(not self.collapsed)
        self.collapse_button.setToolTip("Expand sidebar" if self.collapsed else "Collapse sidebar")
        for index, (item, image, caption, badge, symbol) in enumerate(self.nav):
            caption.setVisible(not self.collapsed)
            badge.setVisible(not self.collapsed and index == 1 and bool(self.data.get("history")))
            item.layout().setContentsMargins(7 if self.collapsed else 10, 0, 7 if self.collapsed else 10, 0)
        self.set_status(self.status_message)

    def set_status(self, message):
        self.status_message = message
        self.status_label.setText(QFontMetrics(self.status_label.font()).elidedText(message,
            Qt.TextElideMode.ElideRight, 148))
        self.status_label.setToolTip(message)
        color = YELLOW if self.state == "listening" else BRAND[0] if self.state in ("connecting", "stopping") else GREEN
        self.status_dot.setStyleSheet(f"color:{color};font-size:10px;")
        if hasattr(self, "indicator"):
            self.indicator.setToolTip(message + ("\n" + self.current_text if self.current_text else ""))

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
                    self.set_status("No hay micrófono predeterminado. Selecciona uno en Settings → Microphone.")
            except Exception as error:
                self.set_status(f"No se pueden consultar los micrófonos: {error}")

    def persist_settings(self):
        if self.state != "idle" or not hasattr(self, "copy_only"):
            return False
        try:
            self.data.update(api_key=native.protect_key(self.key.text().strip()),
                device=self.device_combo.currentText(), copy_only=self.copy_only.isChecked(),
                copy_after=self.copy_after.isChecked(), launch_login=self.launch_login.isChecked(),
                minimize_tray=self.minimize_tray.isChecked(), sounds_enabled=self.sounds_enabled.isChecked(),
                indicator_only_recording=self.indicator_only_recording.isChecked(), free_position=self.free_position.isChecked())
            for key, picker in self.sound_pickers.items():
                self.data[key] = picker.currentData()
            save_data(self.data)
            self.key.setModified(False)
            return True
        except Exception as error:
            QMessageBox.critical(self, "No se pudieron guardar los ajustes", str(error))
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
            QMessageBox.critical(self, "No se pudo cambiar el inicio automático", str(error))

    def refresh_keycaps(self):
        clear_layout(self.keycaps)
        for name in self.data.get("shortcut_label", "Ctrl + Alt + Space").split(" + "):
            self.keycaps.addWidget(label(name, "keycap"))

    def change_shortcut(self, modifiers, key, description):
        old_modifiers = self.data.get("shortcut_modifiers", 3)
        old_key = self.data.get("shortcut_key", 0x20)
        self.hotkey.close()
        self.hotkey = native.Hotkey(modifiers, key)
        if not self.hotkey.registered:
            self.hotkey = native.Hotkey(old_modifiers, old_key)
            self.set_status("Ese atajo está ocupado por otra aplicación. Elige otra combinación.")
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
            self.set_status("Usa Ctrl/Alt/Shift/Win junto con una letra, número, F1–F12 o Espacio.")
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
        self.history_count.setText(str(len(filtered)) if filtered else "")
        self.clear_button.setVisible(bool(history))
        self.empty_history.setVisible(not filtered)
        self.empty_history.setText("No results" if query else "No transcripts yet")
        self.more_button.setVisible(len(filtered) > self.display_limit)
        self.more_button.setText(f"Show more ({max(0, len(filtered)-self.display_limit)})")
        badge = self.nav[1][3]
        badge.setText(str(len(history)))
        badge.setVisible(bool(history) and not self.collapsed)
        for record in filtered[:self.display_limit]:
            row = self.card(None, self.history_layout)
            row.setContentsMargins(14, 14, 14, 14)
            row.setSpacing(8)
            header = QHBoxLayout()
            tag = "PARTIAL" if record.get("partial") else "PASTED" if record.get("inserted") else "HISTORY"
            status = label(tag)
            status.setStyleSheet(f"font-size:10px;font-weight:700;letter-spacing:0.5px;color:{GREEN if tag == 'PASTED' else YELLOW};")
            header.addWidget(status)
            header.addStretch()
            date = label(record["date"].replace("T", "  "), "detail")
            date.setStyleSheet("font-size:10px;color:#505057;")
            header.addWidget(date)
            row.addLayout(header)
            text = label(record["text"])
            text.setWordWrap(True)
            text.setStyleSheet("font-size:13px;color:#d9d9dd;")
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            row.addWidget(text)
            row.addWidget(button("Copy", lambda checked=False, value=record["text"]: self.copy(value), True),
                0, Qt.AlignmentFlag.AlignRight)

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
            self.set_status("Finalizando transcripción…")
            self.session.stop()
            self.update_recording_controls()
            return
        if self.state != "idle":
            return
        if not self.key.text().strip():
            self.set_status("Añade tu clave API en Settings antes de dictar.")
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
        self.preview.setText("Start speaking when the indicator is ready…")
        self.live_card.show()
        self.set_status("Conectando… espera a «Escuchando» para hablar.")
        self.position_indicator()
        self.update_recording_controls()
        self.session = Session(self.key.text().strip(), self.device_combo.currentData(), self.events)
        self.session.start()

    def poll(self):
        current = native.foreground()
        if current and not native.is_our_window(current):
            self.last_target = current
        if self.hotkey.poll():
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
                self.set_status("Escuchando… pulsa el atajo para terminar.")
                self.feedback("start_sound")
                self.update_recording_controls()
            elif kind == "level":
                self.indicator.level = value
            elif kind == "transcript":
                self.current_text = value
                self.preview.setText(value)
                self.set_status(self.status_message)
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
        self.live_card.hide()
        self.preview.setText(text)
        if self.started_at is not None:
            self.data["duration_seconds"] = self.data.get("duration_seconds", 0) + time.monotonic() - self.started_at
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
            error = f"No se pudo guardar el historial: {save_error}. Copia el texto de la ventana."
            self.live_card.setVisible(bool(text))
        if text and not error and not self.closing:
            if self.session_copy_only:
                self.copy(text)
            else:
                record["inserted"] = native.insert_text(text, self.target)
                self.set_status("Texto escrito en la aplicación." if record["inserted"] else
                    "Texto guardado. Puedes copiarlo de Transcripts.")
                if self.session_copy_after:
                    self.copy(text)
                try:
                    save_data(self.data)
                except OSError:
                    self.set_status("Texto guardado; no se pudo actualizar el estado de inserción.")
        elif not text:
            self.set_status("No se detectó voz. Listo para dictar.")
        if error:
            self.set_status(error)
            self.status_dot.setStyleSheet(f"color:{PINK};font-size:10px;")
            if not self.closing:
                self.show_window()
        self.refresh_history()
        self.update_usage()
        self.update_recording_controls()

    def update_recording_controls(self):
        stopping = self.state == "stopping"
        active = self.state in ("connecting", "listening")
        text = "Finalizing…" if stopping else "Stop dictation" if active else "Start dictation"
        self.button.setText(text)
        self.button.setEnabled(not stopping and not self.closing)
        self.tray_record_action.setText(text)
        self.tray_record_action.setEnabled(not stopping and not self.closing)
        for control in self.settings_controls:
            control.setEnabled(self.state == "idle" and not self.closing)
        self.update_indicator()

    def update_indicator(self):
        self.indicator.state = self.state
        self.indicator.update()
        visible = not self.closing and (self.state != "idle" or not self.indicator_only_recording.isChecked())
        self.indicator.setVisible(visible)

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

    def copy(self, text):
        if text:
            QApplication.clipboard().setText(text)
            self.set_status("Texto copiado al portapapeles.")

    def feedback(self, key):
        if self.sounds_enabled.isChecked():
            self.play_sound(self.sound_pickers[key].currentData())

    @staticmethod
    def play_sound(name):
        if name != "None":
            try:
                winsound.PlaySound(name, winsound.SND_ALIAS | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            except RuntimeError:
                pass

    @staticmethod
    def open_url(url):
        QDesktopServices.openUrl(QUrl(url))

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def dark_titlebar(self):
        try:
            dwm = ctypes.WinDLL("dwmapi")
            dwm.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
            for attribute, value in ((20, 1), (33, 2), (35, 0x00141212)):
                setting = ctypes.c_int(value)
                dwm.DwmSetWindowAttribute(int(self.winId()), attribute, ctypes.byref(setting), 4)
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
            self.set_status("Cerrando la sesión de dictado…")
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
        self.hotkey.close()
        QApplication.instance().removeNativeEventFilter(self.hotkey_filter)
        self.indicator.animation.stop()
        self.indicator.close()
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
        QMessageBox.critical(None, "Blablabla no pudo arrancar",
            f"{error}\n\nDatos locales: {DATA_FILE}\nSi el archivo está dañado, conserva una copia antes de moverlo.")
        return 1
    window.show()
    return qt_app.exec()


if __name__ == "__main__":
    sys.exit(main())
