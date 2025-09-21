#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spotify Desktop Alarm (PySide6 + Spotipy OAuth, installer-provisioned config)

- Reads CLIENT_ID / CLIENT_SECRET / DEFAULT_SPOTIFY_URI from:
    Windows: %APPDATA%/SpotifyAlarm/config.json
    macOS:   ~/Library/Application Support/SpotifyAlarm/config.json
    Linux:   ~/.config/SpotifyAlarm/config.json

- Redirect URI is fixed to: http://127.0.0.1:8080/callback
  (Add this exact URI in the Spotify dev dashboard.)

- Default URI is OPTIONAL. If missing/blank, each alarm must have its own URI.

Prereqs (Python 3.10 x64):
    pip install PySide6==6.7.3 spotipy==2.25.1
"""

import json
import os
import sys
import time
import threading
import webbrowser
import urllib.parse
import http.server
import socketserver
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtWidgets
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox,
    QComboBox, QMessageBox, QCheckBox
)
from PySide6.QtCore import QTimer, Qt

import spotipy
from spotipy.oauth2 import SpotifyOAuth

REDIRECT_URI = "http://127.0.0.1:8080/callback"   # must match dashboard exactly
ALARM_FILE = "alarms.json"

# ---------------- paths ----------------
def user_config_dir(app_name: str) -> Path:
    if sys.platform.startswith("win"):
        base = os.getenv("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    p = Path(base) / app_name
    p.mkdir(parents=True, exist_ok=True)
    return p

CONFIG_DIR = user_config_dir("SpotifyAlarm")
CONFIG_PATH = CONFIG_DIR / "config.json"
TOKEN_PATH = CONFIG_DIR / "tokens.json"

# ---------------- config ----------------
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise RuntimeError(
            f"Missing config file at:\n{CONFIG_PATH}\n\n"
            "This should be created by the installer and must contain JSON like:\n"
            '{\n  "client_id": "...",\n  "client_secret": "...",\n'
            '  "default_uri": "spotify:playlist:..."   // optional, can be ""\n}\n'
        )
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not cfg.get("client_id") or not cfg.get("client_secret"):
            raise ValueError("client_id or client_secret missing")
        # default_uri is optional
        if "default_uri" not in cfg or cfg["default_uri"] is None:
            cfg["default_uri"] = ""
        return cfg
    except Exception as e:
        raise RuntimeError(f"Failed to read config.json: {e}")

# ---------------- local callback server ----------------
class _AuthCodeHandler(http.server.BaseHTTPRequestHandler):
    code_holder = {"code": None}
    done_event = threading.Event()
    def log_message(self, *args, **kwargs): pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != urllib.parse.urlparse(REDIRECT_URI).path:
            self.send_response(404); self.end_headers(); self.wfile.write(b"Not found"); return
        qs = urllib.parse.parse_qs(parsed.query)
        code = qs.get("code", [None])[0]
        if code:
            _AuthCodeHandler.code_holder["code"] = code
            self.send_response(200); self.end_headers()
            self.wfile.write(b"<html><body><h3>Auth complete. You can close this window.</h3></body></html>")
            _AuthCodeHandler.done_event.set()
        else:
            self.send_response(400); self.end_headers(); self.wfile.write(b"Missing code")

def _run_local_server_in_thread():
    parsed = urllib.parse.urlparse(REDIRECT_URI)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 8080
    httpd = socketserver.TCPServer((host, port), _AuthCodeHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd

# ---------------- auth / client ----------------
def make_auth(client_id: str, client_secret: str) -> SpotifyOAuth:
    scope = "user-read-playback-state user-modify-playback-state user-read-currently-playing"
    return SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
        scope=scope,
        cache_path=str(TOKEN_PATH),  # where refresh token lives
    )

def get_spotify_client(cfg: dict):
    auth = make_auth(cfg["client_id"], cfg["client_secret"])
    token_info = auth.get_cached_token()
    if not token_info:
        httpd = _run_local_server_in_thread()
        try:
            webbrowser.open(auth.get_authorize_url())
            if not _AuthCodeHandler.done_event.wait(timeout=120):
                raise RuntimeError("Authorization timeout. Please try again.")
            code = _AuthCodeHandler.code_holder["code"]
            if not code:
                raise RuntimeError("Authorization code not received.")
            token_info = auth.get_access_token(code, check_cache=False)
            if not token_info:
                raise RuntimeError("Failed to obtain token from Spotify.")
        finally:
            try: httpd.shutdown()
            except Exception: pass
    return spotipy.Spotify(auth_manager=auth, requests_timeout=15, retries=3)

# ---------------- spotify helpers ----------------
def try_launch_spotify_desktop():
    try:
        if sys.platform.startswith("win"):
            webbrowser.open("spotify:")
        elif sys.platform == "darwin":
            os.system("open -g -a Spotify || open -g spotify:")
        else:
            if os.system("spotify --version > /dev/null 2>&1") == 0:
                os.system("spotify >/dev/null 2>&1 &")
            else:
                webbrowser.open("spotify:")
    except Exception:
        pass

def list_devices(sp):
    try:
        return sp.devices().get("devices", [])
    except Exception as e:
        print("Error fetching devices:", e); return []

def ensure_device_active(sp, preferred_device_id=None):
    devices = list_devices(sp)
    if not devices:
        try_launch_spotify_desktop(); time.sleep(2)
        devices = list_devices(sp)
        if not devices: return None
    if preferred_device_id:
        for d in devices:
            if d["id"] == preferred_device_id:
                try: sp.transfer_playback(device_id=preferred_device_id, force_play=True); return preferred_device_id
                except Exception: pass
    desktop_candidates = [d for d in devices if d.get("type","").lower() in ("computer","desktop")]
    active_desktop = next((d for d in desktop_candidates if d.get("is_active")), None)
    if active_desktop: return active_desktop["id"]
    if desktop_candidates:
        try: sp.transfer_playback(device_id=desktop_candidates[0]["id"], force_play=True); return desktop_candidates[0]["id"]
        except Exception: pass
    active_any = next((d for d in devices if d.get("is_active")), None)
    if active_any: return active_any["id"]
    try: sp.transfer_playback(device_id=devices[0]["id"], force_play=True); return devices[0]["id"]
    except Exception: return devices[0]["id"]

def start_playback(sp, device_id, uri, volume_percent=None):
    if not uri:
        raise ValueError("No Spotify URI provided.")
    uri = uri.strip()
    if "open.spotify.com" in uri:
        try:
            path = uri.split("open.spotify.com/")[1]
            parts = path.split("?")[0].split("/")
            kind, spotify_id = parts[0], parts[1]
            uri = f"spotify:{kind}:{spotify_id}"
        except Exception: pass
    body = {}
    if uri.startswith("spotify:track:"):
        body["uris"] = [uri]
    elif uri.startswith(("spotify:album:", "spotify:playlist:", "spotify:artist:", "spotify:show:", "spotify:episode:")):
        body["context_uri"] = uri
    else:
        if len(uri) > 0 and ":" not in uri and "/" not in uri:
            body["uris"] = [f"spotify:track:{uri}"]
        else:
            raise ValueError("Unsupported or invalid URI.")
    if volume_percent is not None:
        v = max(0, min(100, int(volume_percent)))
        try: sp.volume(v, device_id=device_id)
        except Exception as e: print("Volume set error:", e)
    try:
        sp.start_playback(device_id=device_id, **body)
    except spotipy.exceptions.SpotifyException as e:
        if e.http_status == 404:
            sp.transfer_playback(device_id=device_id, force_play=True)
            sp.start_playback(device_id=device_id, **body)
        else:
            raise

# ---------------- alarm storage ----------------
def load_alarms():
    if os.path.exists(ALARM_FILE):
        with open(ALARM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def save_alarms(alarms):
    with open(ALARM_FILE, "w", encoding="utf-8") as f:
        json.dump(alarms, f, indent=2)

# ---------------- GUI ----------------
class AlarmApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spotify Alarm")
        self.resize(900, 520)
        try:
            self.cfg = load_config()
        except Exception as e:
            QMessageBox.critical(self, "Config Error", str(e)); sys.exit(1)

        self.sp = None
        self.current_device_id = None
        self.default_uri = (self.cfg.get("default_uri") or "").strip()
        self._build_ui()
        self._load_alarms()
        self._auth_spotify()
        self._populate_devices()

        self.timer = QTimer(self); self.timer.timeout.connect(self._tick); self.timer.start(1000)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.device_combo = QComboBox()
        self.refresh_devices_btn = QPushButton("Refresh Devices")
        self.test_btn = QPushButton("Test Alarm (Play Now)")
        self.auto_launch_cb = QCheckBox("Auto-launch Spotify if closed"); self.auto_launch_cb.setChecked(True)
        top.addWidget(QLabel("Output Device:")); top.addWidget(self.device_combo, 1)
        top.addWidget(self.refresh_devices_btn); top.addWidget(self.test_btn); top.addWidget(self.auto_launch_cb)
        layout.addLayout(top)

        form = QHBoxLayout()
        self.time_edit = QLineEdit(); self.time_edit.setPlaceholderText("HH:MM (24h)")
        self.label_edit = QLineEdit(); self.label_edit.setPlaceholderText("Label")
        self.uri_edit = QLineEdit(); self.uri_edit.setPlaceholderText("Spotify URI or link")
        self.vol_spin = QSpinBox(); self.vol_spin.setRange(0, 100); self.vol_spin.setValue(60)
        self.add_btn = QPushButton("Add / Update"); self.remove_btn = QPushButton("Remove Selected")
        for w in (QLabel("Time:"), self.time_edit, QLabel("Label:"), self.label_edit,
                  QLabel("URI:"), self.uri_edit, QLabel("Vol%:"), self.vol_spin, self.add_btn, self.remove_btn):
            form.addWidget(w)
        layout.addLayout(form)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Time", "Label", "URI", "Volume %"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

        bottom = QHBoxLayout()
        self.save_btn = QPushButton("Save Alarms"); bottom.addStretch(1)
        self.about_btn = QPushButton("About"); bottom.addWidget(self.about_btn); bottom.addWidget(self.save_btn)
        layout.addLayout(bottom)

        self.add_btn.clicked.connect(self.add_or_update_alarm)
        self.remove_btn.clicked.connect(self.remove_selected)
        self.save_btn.clicked.connect(self.save_current_alarms)
        self.refresh_devices_btn.clicked.connect(self._populate_devices)
        self.test_btn.clicked.connect(self.test_alarm)
        self.table.cellClicked.connect(self._fill_form_from_row)
        self.about_btn.clicked.connect(self._about)

    def _about(self):
        QMessageBox.information(
            self, "About",
            "Spotify Alarm — OAuth with local callback.\n"
            "Config lives in your user AppData.\n© Vasilis"
        )

    def _auth_spotify(self):
        try:
            self.sp = get_spotify_client(self.cfg)
        except Exception as e:
            QMessageBox.critical(self, "Spotify Auth Error", str(e)); sys.exit(1)

    def _populate_devices(self):
        self.device_combo.clear()
        if not self.sp: return
        if self.auto_launch_cb.isChecked(): try_launch_spotify_desktop(); time.sleep(1)
        devices = list_devices(self.sp)
        if not devices:
            self.device_combo.addItem("No devices found (open Spotify)", userData=None); return
        for d in devices:
            name = f"{'★ ' if d.get('is_active') else ''}{d.get('name','Unknown')}  [{d.get('type','?')}]"
            self.device_combo.addItem(name, userData=d["id"])
        if getattr(self, "current_device_id", None):
            idx = next((i for i in range(self.device_combo.count())
                        if self.device_combo.itemData(i) == self.current_device_id), -1)
            if idx >= 0: self.device_combo.setCurrentIndex(idx)

    def _current_device_id(self):
        idx = self.device_combo.currentIndex()
        return None if idx < 0 else self.device_combo.itemData(idx)

    def _tick(self):
        now = datetime.now().strftime("%H:%M")
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).text().strip() == now:
                key = ("_fired", row, now)
                if getattr(self, str(key), False): continue
                setattr(self, str(key), True); self._fire_row(row)
        if getattr(self, "_last_minute", None) != now:
            for attr in list(self.__dict__.keys()):
                if attr.startswith("('_fired'"): delattr(self, attr)
            self._last_minute = now

    def _fire_row(self, row):
        label = self.table.item(row, 1).text()
        uri = self.table.item(row, 2).text().strip() or self.default_uri
        vol = int(self.table.item(row, 3).text())
        if not uri:
            QMessageBox.warning(
                self, "Missing URI",
                "No URI set for this alarm and no default playlist configured "
                "(this is fine — just enter a URI for each alarm)."
            )
            return
        def run():
            try:
                if self.auto_launch_cb.isChecked(): try_launch_spotify_desktop(); time.sleep(1)
                device_id = ensure_device_active(self.sp, self._current_device_id())
                if not device_id:
                    QtCore.QMetaObject.invokeMethod(self, "_notify", Qt.QueuedConnection,
                        QtCore.Q_ARG(str, f"Alarm '{label}': No active Spotify device found.")); return
                start_playback(self.sp, device_id, uri, volume_percent=vol)
                QtCore.QMetaObject.invokeMethod(self, "_notify", Qt.QueuedConnection,
                    QtCore.Q_ARG(str, f"Alarm '{label}' is playing 🎵"))
            except Exception as e:
                QtCore.QMetaObject.invokeMethod(self, "_notify", Qt.QueuedConnection,
                    QtCore.Q_ARG(str, f"Playback error: {e}"))
        threading.Thread(target=run, daemon=True).start()

    @QtCore.Slot(str)
    def _notify(self, msg): QMessageBox.information(self, "Spotify Alarm", msg)

    def test_alarm(self):
        uri = self.uri_edit.text().strip() or self.default_uri
        vol = self.vol_spin.value()
        if not uri:
            QMessageBox.warning(
                self, "Missing URI",
                "Enter a Spotify URI for testing or set a default playlist in config.json."
            )
            return
        def run():
            try:
                if self.auto_launch_cb.isChecked(): try_launch_spotify_desktop(); time.sleep(1)
                device_id = ensure_device_active(self.sp, self._current_device_id())
                if not device_id:
                    QtCore.QMetaObject.invokeMethod(self, "_notify", Qt.QueuedConnection,
                        QtCore.Q_ARG(str, "No active device found. Open Spotify and try again.")); return
                start_playback(self.sp, device_id, uri, volume_percent=vol)
                QtCore.QMetaObject.invokeMethod(self, "_notify", Qt.QueuedConnection,
                    QtCore.Q_ARG(str, "Test playback started ✅"))
            except Exception as e:
                QtCore.QMetaObject.invokeMethod(self, "_notify", Qt.QueuedConnection,
                    QtCore.Q_ARG(str, f"Playback error: {e}"))
        threading.Thread(target=run, daemon=True).start()

    def _load_alarms(self):
        alarms = load_alarms()
        self.table.setRowCount(0)
        for a in alarms:
            self._append_row(a["time"], a.get("label",""), a.get("uri",""), int(a.get("volume",60)))

    def save_current_alarms(self):
        alarms = []
        for row in range(self.table.rowCount()):
            alarms.append({
                "time": self.table.item(row, 0).text().strip(),
                "label": self.table.item(row, 1).text().strip(),
                "uri": self.table.item(row, 2).text().strip(),
                "volume": int(self.table.item(row, 3).text().strip() or "60"),
            })
        save_alarms(alarms); QMessageBox.information(self, "Saved", "Alarms saved to alarms.json")

    def _append_row(self, time_str, label, uri, vol):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(time_str))
        self.table.setItem(r, 1, QTableWidgetItem(label))
        self.table.setItem(r, 2, QTableWidgetItem(uri))
        self.table.setItem(r, 3, QTableWidgetItem(str(vol)))

    def add_or_update_alarm(self):
        t = self.time_edit.text().strip()
        if not self._valid_time(t):
            QMessageBox.warning(self, "Invalid time", "Use HH:MM (24h)."); return
        lbl = self.label_edit.text().strip()
        uri = self.uri_edit.text().strip()
        vol = self.vol_spin.value()
        rows = self.table.selectionModel().selectedRows()
        if rows:
            r = rows[0].row()
            self.table.item(r, 0).setText(t); self.table.item(r, 1).setText(lbl)
            self.table.item(r, 2).setText(uri); self.table.item(r, 3).setText(str(vol))
        else:
            self._append_row(t, lbl, uri, vol)

    def remove_selected(self):
        rows = sorted([r.row() for r in self.table.selectionModel().selectedRows()], reverse=True)
        for r in rows: self.table.removeRow(r)

    def _fill_form_from_row(self, row, col):
        self.time_edit.setText(self.table.item(row, 0).text())
        self.label_edit.setText(self.table.item(row, 1).text())
        self.uri_edit.setText(self.table.item(row, 2).text())
        self.vol_spin.setValue(int(self.table.item(row, 3).text()))

    @staticmethod
    def _valid_time(s):
        try: datetime.strptime(s, "%H:%M"); return True
        except Exception: return False

def main():
    app = QApplication(sys.argv)
    win = AlarmApp(); win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
