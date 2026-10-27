"""Protocol regressions plus real Win32 checks; no cloud key required."""
import ctypes
import json
from pathlib import Path
import queue
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch
import urllib.error

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QKeySequenceEdit

import app
import native
import speech


class FakeSocket:
    def __init__(self, fail=False):
        self.messages = queue.Queue()
        self.messages.put(json.dumps({"type": "Begin"}))
        self.sent = []
        self.fail = fail
        self.closed = False

    def settimeout(self, value):
        pass

    def recv(self):
        try:
            return self.messages.get(timeout=0.05)
        except queue.Empty:
            raise speech.websocket.WebSocketTimeoutException()

    def send_binary(self, data):
        self.sent.append(data)
        self.messages.put(json.dumps({"type": "Turn", "turn_order": 0,
            "transcript": "hola", "end_of_turn": False}))
        if self.fail:
            self.messages.put(json.dumps({"type": "Error", "error": "Sin saldo"}))

    def send(self, data):
        event = json.loads(data)
        self.sent.append(event["type"])
        if event["type"] == "Terminate" and not self.fail:
            # A final only arriving AFTER Terminate must not be lost.
            for text in ("hola mundo", "¡Hola, mundo!"):
                self.messages.put(json.dumps({"type": "Turn", "turn_order": 0,
                    "transcript": text, "end_of_turn": True}))
            self.messages.put(json.dumps({"type": "Termination"}))

    def close(self, timeout=1):
        self.closed = True


class FakeStream:
    def __init__(self, **kwargs):
        self.callback = kwargs["callback"]
        self.active = False
        self.closed = False

    def start(self):
        self.active = True
        self.callback(bytes(4800), 2400, None, None)

    def stop(self):
        self.active = False

    def close(self):
        self.closed = True


class ProtocolTests(unittest.TestCase):
    def run_session(self, fail=False):
        events = queue.Queue()
        session = speech.Session("not-a-real-key", None, events)
        socket = FakeSocket(fail)
        streams = []
        def make_stream(**kwargs):
            stream = FakeStream(**kwargs)
            streams.append(stream)
            return stream
        with patch.object(speech.sd, "query_devices", return_value={"default_samplerate": 48000}), \
             patch.object(speech.sd, "RawInputStream", side_effect=make_stream), \
             patch.object(session, "token", return_value="temporary-token"), \
             patch.object(speech.websocket, "create_connection", return_value=socket) as connection:
            session.start()
            while True:
                kind, value = events.get(timeout=3)
                if kind == "transcript" and not fail:
                    session.stop()
                if kind == "finished":
                    break
            session.thread.join(timeout=3)
            self.assertFalse(session.thread.is_alive())
            self.assertIn("sample_rate=48000", connection.call_args.args[0])
        self.assertTrue(streams[0].closed)
        self.assertTrue(socket.closed)
        return value, socket

    def test_final_after_terminate_and_formatted_replacement(self):
        (text, error), socket = self.run_session()
        self.assertEqual(text, "¡Hola, mundo!")
        self.assertIsNone(error)
        self.assertLess(socket.sent.index("ForceEndpoint"), socket.sent.index("Terminate"))
        self.assertTrue(any(isinstance(item, bytes) for item in socket.sent))

    def test_connection_error_preserves_partial(self):
        (text, error), _ = self.run_session(fail=True)
        self.assertEqual(text, "hola")
        self.assertIn("Sin saldo", error)

    def test_audio_recorded_while_connecting_is_sent(self):
        events = queue.Queue()
        session = speech.Session("dummy", None, events)
        socket = FakeSocket()
        def token():
            self.assertEqual(events.get_nowait()[0], "level")
            self.assertEqual(events.get_nowait(), ("listening", None))
            session.stop()  # user stops before the connection is ready
            return "token"
        with patch.object(speech.sd, "query_devices", return_value={"default_samplerate": 48000}), \
             patch.object(speech.sd, "RawInputStream", side_effect=FakeStream), \
             patch.object(session, "token", side_effect=token), \
             patch.object(speech.websocket, "create_connection", return_value=socket):
            session.run()
        self.assertEqual(socket.sent[0], bytes(4800))
        self.assertEqual(events.queue[-1], ("finished", ("¡Hola, mundo!", None)))

    def test_stop_during_connect_does_not_start_capture(self):
        events = queue.Queue()
        session = speech.Session("dummy", None, events)
        session.stop()
        with patch.object(speech.sd, "query_devices", return_value={"default_samplerate": 48000}), \
             patch.object(speech.sd, "RawInputStream", side_effect=FakeStream), \
             patch.object(session, "token", return_value="token"), \
             patch.object(speech.websocket, "create_connection") as connection:
            session.run()
            connection.assert_not_called()
        self.assertEqual(events.get_nowait(), ("finished", ("", None)))

    def test_rejected_key_has_actionable_message_without_secret(self):
        session = speech.Session("secret-never-print", None, queue.Queue())
        with patch.object(speech.urllib.request, "urlopen", side_effect=
                urllib.error.HTTPError("url", 401, "Unauthorized", None, None)):
            with self.assertRaisesRegex(RuntimeError, "API key") as error:
                session.token()
        self.assertNotIn("secret-never-print", str(error.exception))

    def test_missing_microphone_does_not_open_billable_session(self):
        events = queue.Queue()
        session = speech.Session("dummy", None, events)
        with patch.object(speech.sd, "query_devices", side_effect=speech.sd.PortAudioError("No device")), \
             patch.object(session, "token") as token:
            session.run()
            token.assert_not_called()
        kind, (text, error) = events.get_nowait()
        self.assertEqual(kind, "finished")
        self.assertEqual(text, "")
        self.assertIn("Connect one", error)

    def test_disconnected_endpoint_does_not_open_billable_session(self):
        events = queue.Queue()
        session = speech.Session("dummy", None, events)
        stream = FakeStream(callback=lambda *args: None)
        stream.start = lambda: None
        with patch.object(speech.sd, "query_devices", return_value={"default_samplerate": 44100}), \
             patch.object(speech.sd, "RawInputStream", return_value=stream), \
             patch.object(session, "token") as token:
            session.run()
            token.assert_not_called()
        kind, (text, error) = events.get_nowait()
        self.assertEqual(kind, "finished")
        self.assertIn("delivers no audio", error)
        self.assertTrue(stream.closed)


class WindowsTests(unittest.TestCase):
    def test_dpapi_roundtrip_and_no_plaintext(self):
        encrypted = native.protect_key("test-secret-é")
        self.assertNotIn("test-secret", encrypted)
        self.assertEqual(native.unprotect_key(encrypted), "test-secret-é")
        self.assertEqual(native.unprotect_key(native.protect_key("")), "")

    def test_hotkey_registers_and_unregisters(self):
        hotkey = native.Hotkey()
        try:
            self.assertTrue(hotkey.registered)
            self.assertFalse(hotkey.poll())
        finally:
            hotkey.close()

    def test_unicode_input_into_real_edit_control(self):
        root = tk.Tk()
        try:
            root.title("Blablabla input smoke test")
            text = tk.Text(root)
            text.pack()
            root.update()
            root.focus_force()
            text.focus_set()
            root.update()
            self.assertEqual(ctypes.sizeof(native.Input), 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
            target = native.foreground()
            self.assertTrue(native.is_our_window(target))
            root.clipboard_clear()
            root.clipboard_append("España, café 😀")
            root.update()
            self.assertTrue(native.paste(target))
            root.update()
            self.assertEqual(text.get("1.0", "end-1c"), "España, café 😀")
            self.assertFalse(native.paste(None))
        finally:
            root.destroy()

    def test_history_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "windows.json"
            data = {"history": [{"text": "¡Hola!", "date": "2026-10-10"}]}
            app.save_data(data, path)
            self.assertEqual(app.load_data(path), data)

    def test_app_launch_and_missing_key(self):
        qt_app = QApplication.instance() or QApplication([])
        qt_app.setStyle("Fusion")
        client = None
        try:
            with patch.object(app, "load_data", return_value={"history": []}):
                client = app.App()
            client.show()
            qt_app.processEvents()
            client.toggle()
            self.assertEqual(client.state, "idle")
            self.assertIn("API key", client.status_message)
        finally:
            if client:
                client.dispose()

    def test_partial_transcript_is_saved_without_automatic_insertion(self):
        qt_app = QApplication.instance() or QApplication([])
        client = None
        try:
            with patch.object(app, "load_data", return_value={"history": []}):
                client = app.App()
            client.state = "listening"
            client.update_indicator()
            self.assertEqual(client.tray.icon().cacheKey(), client.tray_icons["listening"].cacheKey())
            with patch.object(app, "save_data") as save, \
                 patch.object(native, "paste") as insert, \
                 patch.object(client.tray, "showMessage") as notify:
                client.finish("Texto parcial", "Se perdió la conexión")
                self.assertTrue(client.data["history"][0]["partial"])
                self.assertEqual(client.data["history"][0]["text"], "Texto parcial")
                save.assert_called_once()
                insert.assert_not_called()
                # Hidden window: notify instead of popping it up.
                notify.assert_called_once()
                self.assertFalse(client.isVisible())
                self.assertEqual(client.tray.icon().cacheKey(), client.tray_icons["idle"].cacheKey())
        finally:
            if client:
                client.dispose()


class QtInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qt_app = QApplication.instance() or QApplication([])
        cls.qt_app.setStyle("Fusion")

    def setUp(self):
        self.storage = patch.object(app, "save_data")
        self.saved = self.storage.start()
        history = [{"date": "2026-10-10T19:30:00", "text": "España y café", "inserted": True},
                   {"date": "2026-10-10T19:31:00", "text": "Another transcript", "inserted": False}]
        with patch.object(app, "load_data", return_value={"history": history, "sounds_enabled": False}):
            self.client = app.App()
        self.client.show()
        self.qt_app.processEvents()

    def tearDown(self):
        self.client.dispose()
        self.qt_app.processEvents()
        self.storage.stop()

    def test_sidebar_navigation_collapse_and_card_fit(self):
        self.assertEqual(self.client.sidebar.width(), 200)
        QTest.mouseClick(self.client.nav[1][0], Qt.MouseButton.LeftButton)
        self.assertEqual(self.client.pages.currentIndex(), 1)
        QTest.mouseClick(self.client.collapse_button, Qt.MouseButton.LeftButton)
        QTest.qWait(300)  # animated
        self.assertEqual(self.client.sidebar.width(), 54)
        QTest.mouseClick(self.client.collapse_button, Qt.MouseButton.LeftButton)
        QTest.qWait(300)
        self.assertEqual(self.client.sidebar.width(), 200)
        self.assertIsNone(self.client.pages.currentWidget().graphicsEffect())  # fade cleaned up
        self.client.select_page(0)
        for width in (700, 720, 980):
            self.client.resize(width, 760)
            self.qt_app.processEvents()
            scroll = self.client.settings_page
            self.assertLessEqual(scroll.widget().width(), scroll.viewport().width())

    def test_transcript_search_and_copy(self):
        self.client.select_page(1)
        self.client.search.setText("CAFÉ")
        self.qt_app.processEvents()
        self.assertEqual(self.client.history_count.text(), "1")
        self.assertEqual(self.client.history_layout.count(), 1)
        self.client.copy("España y café")
        self.assertEqual(QApplication.clipboard().text(), "España y café")

    def test_hold_shortcut_records_until_release_and_tap_toggles(self):
        client = self.client
        def fake_toggle():
            client.state = "listening" if client.state == "idle" else "idle"
        with patch.object(client, "toggle", side_effect=fake_toggle), \
             patch.object(client.hotkey, "poll", return_value=False), \
             patch.object(native, "key_down", return_value=False):
            client.shortcut_pressed()  # tap: released right away, keeps recording
            client.poll()
            self.assertEqual(client.state, "listening")
            client.shortcut_pressed()  # second tap stops
            self.assertEqual(client.state, "idle")
            client.shortcut_pressed()  # hold: released after the threshold, stops
            client.held_since -= app.HOLD_TO_TALK + 0.1
            client.poll()
            self.assertEqual(client.state, "idle")
            self.assertIsNone(client.held_since)

    def test_live_text_follows_the_indicator(self):
        client = self.client
        client.state = "listening"
        client.update_indicator()
        client.events.put(("transcript", "hola mundo"))
        client.poll()
        self.assertTrue(client.caption.isVisible())
        self.assertEqual(client.caption.text(), "hola mundo")
        self.assertLess(client.caption.geometry().bottom(), client.indicator.geometry().top())
        client.state = "idle"
        client.update_indicator()
        self.assertFalse(client.caption.isVisible())

    def test_update_check_only_offers_newer_windows_builds(self):
        mac = {"tag_name": "v0.9.0", "html_url": "mac", "assets": [{"name": "Blablabla-v0.9.0-macOS.zip"}]}
        win = {"tag_name": "v0.5.0", "html_url": "page", "assets": [{"name": "Blablabla-v0.5.0-Windows.zip"}]}
        old = {"tag_name": "v0.4.4", "html_url": "old", "assets": [{"name": "Blablabla-v0.4.4-Windows.zip"}]}
        self.assertEqual(app.newer_windows_release([mac, win, old], "0.4.4"), ("v0.5.0", "page"))
        self.assertIsNone(app.newer_windows_release([mac, old], "0.4.4"))
        self.assertIsNone(app.newer_windows_release([mac], "0.4.4"))
        self.client.show_update(("v0.5.0", "page"), True)
        self.assertEqual(self.client.update_button.text(), "Download ↗")
        self.assertEqual(self.client.update_url, "page")

    def test_paste_restores_previous_clipboard(self):
        QApplication.clipboard().setText("anterior")
        self.client.session_copy_after = False
        with patch.object(native, "paste", return_value=True) as paste:
            self.assertTrue(self.client.paste("dictado"))
            self.assertEqual(QApplication.clipboard().text(), "dictado")
        paste.assert_called_once()
        QTest.qWait(1700)
        self.assertEqual(QApplication.clipboard().text(), "anterior")

    def test_api_key_done_masks_and_preserves_saved_key(self):
        self.client.key.setText("new-test-key-never-real")
        self.client.key.setModified(True)
        self.client.key_edited(self.client.key.text())
        self.client.key.setFocus()
        QTest.mouseClick(self.client.edit_key_button, Qt.MouseButton.LeftButton)
        self.qt_app.processEvents()
        self.assertFalse(self.client.key.isVisible())
        self.assertTrue(self.client.key_mask.isVisible())
        self.assertEqual(native.unprotect_key(self.client.data["api_key"]), "new-test-key-never-real")

    def test_real_windows_hotkey_reaches_qt_once(self):
        hits = []
        self.client.hotkey_filter.callback = lambda: hits.append("hotkey")
        with patch.object(self.client, "toggle", side_effect=lambda: hits.append("hotkey")):
            keys = [(0x11, 0), (0x12, 0), (0x20, 0), (0x20, 2), (0x12, 2), (0x11, 2)]
            inputs = (native.Input * len(keys))(*(native.Input(1, native.InputUnion(
                keyboard=native.KeyboardInput(key, 0, flags, 0, 0))) for key, flags in keys))
            self.assertEqual(native.user32.SendInput(len(keys), inputs, ctypes.sizeof(native.Input)), len(keys))
            QTest.qWait(120)
        self.assertEqual(hits, ["hotkey"])

    def test_indicator_visibility_and_recording_state(self):
        self.client.indicator_only_recording.setChecked(True)
        self.assertFalse(self.client.indicator.isVisible())
        self.client.state = "listening"
        self.client.indicator.level = 0.25
        self.client.update_recording_controls()
        self.assertTrue(self.client.indicator.isVisible())
        self.assertEqual(self.client.indicator.state, "listening")
        self.assertFalse(self.client.key.isEnabled())
        self.assertEqual(self.client.button.text(), "Stop dictation")

    def test_shortcut_change_and_restore(self):
        self.assertTrue(self.client.change_shortcut(6, 0x78, "Ctrl + Shift + F9"))
        self.assertEqual(self.client.data["shortcut_key"], 0x78)
        self.assertTrue(self.client.change_shortcut(3, 0x20, "Ctrl + Alt + Space"))

    def test_record_shortcut_temporarily_releases_hotkey(self):
        observations = []
        def finish_dialog():
            dialog = QApplication.activeModalWidget()
            observations.append(self.client.hotkey.registered)
            recorder = dialog.findChild(QKeySequenceEdit)
            recorder.setKeySequence(QKeySequence("Ctrl+Alt+Space"))
            dialog.accept()
        QTimer.singleShot(40, finish_dialog)
        self.client.record_shortcut()
        self.assertEqual(observations, [False])
        self.assertTrue(self.client.hotkey.registered)
        self.assertEqual(self.client.data["shortcut_key"], 0x20)

    def test_minimize_to_tray_preserves_shortcut_and_can_reopen(self):
        self.client.minimize_tray.setChecked(True)
        self.client.close()
        self.assertFalse(self.client.isVisible())
        self.assertFalse(self.client.disposed)
        self.assertTrue(self.client.hotkey.registered)
        self.client.show_window()
        self.assertTrue(self.client.isVisible())

    def test_launch_at_login_writes_only_our_run_value(self):
        with patch.object(app.winreg, "CreateKey") as key, \
             patch.object(app.winreg, "SetValueEx") as set_value, \
             patch.object(app.winreg, "DeleteValue") as delete_value:
            self.client.launch_login.setChecked(True)
            self.assertEqual(set_value.call_args.args[1], "Blablabla")
            command = set_value.call_args.args[4]
            self.assertIn("pythonw.exe", command)
            self.assertIn("app.py", command)
            self.client.launch_login.setChecked(False)
            self.assertEqual(delete_value.call_args.args[1], "Blablabla")


if __name__ == "__main__":
    unittest.main()
