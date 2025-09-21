#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spotify Desktop Alarm (PySide6 + Spotipy OAuth, installer-provisioned config)
"""

import json, os, sys, time, threading, webbrowser, urllib.parse, http.server, socketserver
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QSpinBox, QComboBox, QMessageBox,
    QCheckBox, QTimeEdit
)
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPalette, QColor

import spotipy
from spotipy.oauth2 import SpotifyOAuth

# ---------------- constants ----------------
REDIRECT_URI = "http://127.0.0.1:8080/callback"
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
TOKEN_PATH  = CONFIG_DIR / "tokens.json"

# ---------------- config ----------------
def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise RuntimeError(
            f"Missing config file at:\n{CONFIG_PATH}\n\n"
            "This should be created by the installer and must contain:\n"
            '{\n  "client_id": "...",\n  "client_secret": "...",\n'
            '  "default_uri": ""\n}\n'
        )
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("client_id") or not cfg.get("client_secret"):
        raise RuntimeError("Config must contain client_id and client_secret.")
    cfg.setdefault("default_uri", "")
    cfg.setdefault("theme", "Dark")
    return cfg

def save_config(cfg: dict):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

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
    host, port = "127.0.0.1", 8080
    httpd = socketserver.TCPServer((host, port), _AuthCodeHandler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd

# ---------------- auth / client ----------------
def make_auth(client_id: str, client_secret: str) -> SpotifyOAuth:
    scope = "user-read-playback-state user-modify-playback-state user-read-currently-playing"
    return SpotifyOAuth(client_id=client_id, client_secret=client_secret,
                        redirect_uri=REDIRECT_URI, scope=scope, cache_path=str(TOKEN_PATH))

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
    if not uri: raise ValueError("No Spotify URI provided.")
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

# ---------------- themes (QSS + Palette) ----------------
DARK_QSS = """
QWidget { background:#0f1115; color:#e6e6e6; font-size:13px; }
QLabel[title="true"] { font-size:16px; font-weight:600; color:#fff; }
QLineEdit,QTimeEdit,QComboBox,QSpinBox {
  background:#141925; color:#e8eaf0; border:1px solid #1d2230; border-radius:8px; padding:6px 8px;
}
QLineEdit:focus,QTimeEdit:focus,QComboBox:focus,QSpinBox:focus { border:1px solid #2b89ff; }
QPushButton { background:#1b2030; border:1px solid #242a3a; border-radius:8px; padding:6px 12px; }
QPushButton:hover { background:#20263a; }
QPushButton[accent="true"] { background:#2b89ff; color:white; border:1px solid #2b89ff; }
QTableWidget { background:#0f1115; gridline-color:#1b2230; border:1px solid #171b26; border-radius:8px; }
QHeaderView::section { background:#10141d; color:#cfd6e6; border:0; padding:8px; }
"""

LIGHT_QSS = """
QWidget { background:#ffffff; color:#1e1e1e; font-size:13px; }
QLabel[title="true"] { font-size:16px; font-weight:600; color:#0a0a0a; }
QLineEdit,QTimeEdit,QComboBox,QSpinBox {
  background:#ffffff; color:#1e1e1e; border:1px solid #cfcfcf; border-radius:6px; padding:6px 8px;
}
QLineEdit:focus,QTimeEdit:focus,QComboBox:focus,QSpinBox:focus { border:1px solid #2b89ff; }
QPushButton { background:#f7f7f7; border:1px solid #cfcfcf; border-radius:6px; padding:6px 12px; }
QPushButton:hover { background:#f0f0f0; }
QPushButton[accent="true"] { background:#2b89ff; color:white; border:1px solid #2b89ff; }
QTableWidget { background:#ffffff; gridline-color:#e6e6e6; border:1px solid #d9d9d9; border-radius:6px; }
QHeaderView::section { background:#f5f5f5; color:#333; border:0; padding:8px; }
"""

NORD_QSS = """
QWidget { background:#2E3440; color:#D8DEE9; font-size:13px; }
QLabel[title="true"] { font-size:16px; font-weight:600; color:#ECEFF4; }
QLineEdit,QTimeEdit,QComboBox,QSpinBox {
  background:#3B4252; color:#ECEFF4; border:1px solid #4C566A; border-radius:8px; padding:6px 8px;
}
QLineEdit:focus,QTimeEdit:focus,QComboBox:focus,QSpinBox:focus { border:1px solid #88C0D0; }
QPushButton { background:#3B4252; border:1px solid #4C566A; border-radius:8px; padding:6px 12px; }
QPushButton:hover { background:#434C5E; }
QPushButton[accent="true"] { background:#5E81AC; color:white; border:1px solid #5E81AC; }
QTableWidget { background:#2E3440; gridline-color:#434C5E; border:1px solid #3B4252; border-radius:8px; }
QHeaderView::section { background:#2B303B; color:#E5E9F0; border:0; padding:8px; }
"""

THEMES = {"Dark": DARK_QSS, "Light": LIGHT_QSS, "Nord": NORD_QSS}

def set_fusion_palette(app: QApplication, theme: str):
    """Force a Fusion palette that matches the theme (so changes are obvious on Windows)."""
    app.setStyle("Fusion")
    pal = QPalette()

    if theme == "Light":
        pal.setColor(QPalette.Window, QColor("#ffffff"))
        pal.setColor(QPalette.WindowText, QColor("#1e1e1e"))
        pal.setColor(QPalette.Base, QColor("#ffffff"))
        pal.setColor(QPalette.AlternateBase, QColor("#f5f5f5"))
        pal.setColor(QPalette.Text, QColor("#1e1e1e"))
        pal.setColor(QPalette.Button, QColor("#f7f7f7"))
        pal.setColor(QPalette.ButtonText, QColor("#1e1e1e"))
        pal.setColor(QPalette.Highlight, QColor("#2b89ff"))
        pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    elif theme == "Nord":
        pal.setColor(QPalette.Window, QColor("#2E3440"))
        pal.setColor(QPalette.WindowText, QColor("#D8DEE9"))
        pal.setColor(QPalette.Base, QColor("#3B4252"))
        pal.setColor(QPalette.AlternateBase, QColor("#2E3440"))
        pal.setColor(QPalette.Text, QColor("#ECEFF4"))
        pal.setColor(QPalette.Button, QColor("#3B4252"))
        pal.setColor(QPalette.ButtonText, QColor("#ECEFF4"))
        pal.setColor(QPalette.Highlight, QColor("#5E81AC"))
        pal.setColor(QPalette.HighlightedText, QColor("#ECEFF4"))
    else:  # Dark default
        pal.setColor(QPalette.Window, QColor("#0f1115"))
        pal.setColor(QPalette.WindowText, QColor("#e6e6e6"))
        pal.setColor(QPalette.Base, QColor("#141925"))
        pal.setColor(QPalette.AlternateBase, QColor("#0f1115"))
        pal.setColor(QPalette.Text, QColor("#e8eaf0"))
        pal.setColor(QPalette.Button, QColor("#1b2030"))
        pal.setColor(QPalette.ButtonText, QColor("#e6e6e6"))
        pal.setColor(QPalette.Highlight, QColor("#2b89ff"))
        pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))

    app.setPalette(pal)
    # Also set stylesheet to style details like borders, headers, etc.
    app.setStyleSheet(THEMES.get(theme, DARK_QSS))

# ---------------- GUI ----------------
class AlarmApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spotify Alarm")
        self.resize(1000, 560)

        try:
            self.cfg = load_config()
        except Exception as e:
            QMessageBox.critical(self, "Config Error", str(e)); sys.exit(1)

        self.sp = None
        self.default_uri = self.cfg.get("default_uri", "")
        self._build_ui()
        self._apply_theme(self.cfg.get("theme", "Dark"))  # ensure palette + QSS now
        self._load_alarms()
        self._auth_spotify()
        self._populate_devices()

        self.timer = QTimer(self); self.timer.timeout.connect(self._tick); self.timer.start(1000)

    # ----- UI -----
    def _build_ui(self):
        root = QVBoxLayout(self)

        # Top bar: device + actions + theme
        bar = QHBoxLayout()
        self.device_combo = QComboBox()
        btn_refresh = QPushButton("Refresh Devices"); btn_refresh.clicked.connect(self._populate_devices)
        btn_test = QPushButton("Test Alarm (Play Now)"); btn_test.clicked.connect(self.test_alarm)
        self.auto_launch_cb = QCheckBox("Auto-launch Spotify if closed"); self.auto_launch_cb.setChecked(True)

        bar.addWidget(QLabel("Output Device:")); bar.addWidget(self.device_combo, 1)
        bar.addWidget(btn_refresh); bar.addWidget(btn_test); bar.addWidget(self.auto_launch_cb)

        bar.addSpacing(12)
        bar.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEMES.keys())
        self.theme_combo.currentTextChanged.connect(self._apply_theme)
        bar.addWidget(self.theme_combo)

        root.addLayout(bar)

        # Form row
        form = QHBoxLayout()
        self.time_edit = QTimeEdit(QtCore.QTime.currentTime()); self.time_edit.setDisplayFormat("HH:mm")
        self.label_edit = QLineEdit(); self.label_edit.setPlaceholderText("Label")
        self.uri_edit = QLineEdit(); self.uri_edit.setPlaceholderText("Spotify URI or link")
        self.vol_spin = QSpinBox(); self.vol_spin.setRange(0, 100); self.vol_spin.setValue(60)
        btn_add = QPushButton("Add / Update"); btn_add.clicked.connect(self.add_or_update_alarm)
        btn_del_sel = QPushButton("Delete Selected"); btn_del_sel.clicked.connect(self.remove_selected)

        for w in (QLabel("Time:"), self.time_edit, QLabel("Label:"), self.label_edit,
                  QLabel("URI:"), self.uri_edit, QLabel("Vol%:"), self.vol_spin, btn_add, btn_del_sel):
            form.addWidget(w)
        root.addLayout(form)

        # Table with checkbox column
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["✓", "Time", "Label", "URI", "Volume %"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.cellClicked.connect(self._fill_form_from_row)
        self.table.itemChanged.connect(lambda _=None: self._update_select_all_state())
        root.addWidget(self.table)

        # Bottom row
        bottom = QHBoxLayout()
        self.check_all_cb = QCheckBox("Select all"); self.check_all_cb.stateChanged.connect(self._toggle_check_all)
        btn_del_checked = QPushButton("Delete Checked"); btn_del_checked.clicked.connect(self.remove_checked)
        btn_save = QPushButton("Save Alarms"); btn_save.clicked.connect(self.save_current_alarms)
        bottom.addWidget(btn_del_checked); bottom.addStretch(1); bottom.addWidget(self.check_all_cb); bottom.addWidget(btn_save)
        root.addLayout(bottom)

    # ----- Theme -----
    def _apply_theme(self, name: str):
        # Set Fusion palette + stylesheet, persist in config
        set_fusion_palette(QApplication.instance(), name)
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentText(name)
        self.theme_combo.blockSignals(False)
        if self.cfg.get("theme") != name:
            self.cfg["theme"] = name
            save_config(self.cfg)

    # ----- auth -----
    def _auth_spotify(self):
        try:
            self.sp = get_spotify_client(self.cfg)
        except Exception as e:
            QMessageBox.critical(self, "Spotify Auth Error", str(e)); sys.exit(1)

    # ----- devices -----
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

    def _current_device_id(self):
        idx = self.device_combo.currentIndex()
        return None if idx < 0 else self.device_combo.itemData(idx)

    # ----- checkbox helpers -----
    def _make_check_item(self, checked=False):
        it = QTableWidgetItem("")
        it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
        it.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        return it

    def _is_row_checked(self, r: int) -> bool:
        it = self.table.item(r, 0)
        return bool(it and it.checkState() == Qt.Checked)

    def _set_row_checked(self, r: int, checked: bool):
        it = self.table.item(r, 0)
        if it:
            it.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def _checked_rows(self):
        return [r for r in range(self.table.rowCount()) if self._is_row_checked(r)]

    def _toggle_check_all(self, state: int):
        self.table.blockSignals(True)
        try:
            all_checked = (state == Qt.Checked)
            for r in range(self.table.rowCount()):
                self._set_row_checked(r, all_checked)
        finally:
            self.table.blockSignals(False)
        self._update_select_all_state()

    def _update_select_all_state(self):
        if self.table.rowCount() == 0:
            self.check_all_cb.setCheckState(Qt.Unchecked); return
        checks = [self._is_row_checked(r) for r in range(self.table.rowCount())]
        self.check_all_cb.blockSignals(True)
        if all(checks): self.check_all_cb.setCheckState(Qt.Checked)
        elif any(checks): self.check_all_cb.setCheckState(Qt.PartiallyChecked)
        else: self.check_all_cb.setCheckState(Qt.Unchecked)
        self.check_all_cb.blockSignals(False)

    # ----- alarms -----
    def _tick(self):
        now = datetime.now().strftime("%H:%M")
        if getattr(self, "_last_minute", None) != now:
            self._fired = set(); self._last_minute = now
        for row in range(self.table.rowCount()):
            t_item = self.table.item(row, 1)
            if t_item and t_item.text().strip() == now and row not in self._fired:
                self._fired.add(row)
                self._fire_row(row)

    def _fire_row(self, row):
        label = self.table.item(row, 2).text()
        uri   = self.table.item(row, 3).text().strip() or self.default_uri
        vol   = int(self.table.item(row, 4).text())
        if not uri:
            QMessageBox.warning(self, "Missing URI", "No URI set and no default_uri in config.json."); return

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
            QMessageBox.warning(self, "Missing URI", "Enter a Spotify URI or set default_uri in config.json."); return
        def run():
            try:
                if self.auto_launch_cb.isChecked(): try_launch_spotify_desktop(); time.sleep(1)
                device_id = ensure_device_active(self.sp, self._current_device_id())
                if not device_id:
                    QtCore.QMetaObject.invokeMethod(self, "_notify", Qt.QueuedConnection,
                        QtCore.Q_ARG(str, "No active device. Open Spotify and try again.")); return
                start_playback(self.sp, device_id, uri, volume_percent=vol)
                QtCore.QMetaObject.invokeMethod(self, "_notify", Qt.QueuedConnection,
                    QtCore.Q_ARG(str, "Test playback started ✅"))
            except Exception as e:
                QtCore.QMetaObject.invokeMethod(self, "_notify", Qt.QueuedConnection,
                    QtCore.Q_ARG(str, f"Playback error: {e}"))
        threading.Thread(target=run, daemon=True).start()

    def _load_alarms(self):
        try:
            alarms = json.load(open(ALARM_FILE, "r", encoding="utf-8")) if os.path.exists(ALARM_FILE) else []
        except Exception:
            alarms = []
        self.table.setRowCount(0)
        for a in alarms:
            self._append_row(a["time"], a.get("label",""), a.get("uri",""), int(a.get("volume",60)))

    def save_current_alarms(self):
        alarms = []
        for row in range(self.table.rowCount()):
            alarms.append({
                "time": self.table.item(row, 1).text().strip(),
                "label": self.table.item(row, 2).text().strip(),
                "uri": self.table.item(row, 3).text().strip(),
                "volume": int(self.table.item(row, 4).text().strip() or "60"),
            })
        with open(ALARM_FILE, "w", encoding="utf-8") as f:
            json.dump(alarms, f, indent=2)
        QMessageBox.information(self, "Saved", "Alarms saved to alarms.json")

    def _append_row(self, time_str, label, uri, vol, checked=False):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, self._make_check_item(checked))
        self.table.setItem(r, 1, QTableWidgetItem(time_str))
        self.table.setItem(r, 2, QTableWidgetItem(label))
        self.table.setItem(r, 3, QTableWidgetItem(uri))
        self.table.setItem(r, 4, QTableWidgetItem(str(vol)))
        self._update_select_all_state()

    def add_or_update_alarm(self):
        t = self.time_edit.time().toString("HH:mm")
        lbl = self.label_edit.text().strip()
        uri = self.uri_edit.text().strip()
        vol = self.vol_spin.value()
        rows = self.table.selectionModel().selectedRows()
        if rows:
            r = rows[0].row()
            self.table.item(r, 1).setText(t)
            self.table.item(r, 2).setText(lbl)
            self.table.item(r, 3).setText(uri)
            self.table.item(r, 4).setText(str(vol))
        else:
            self._append_row(t, lbl, uri, vol)

    def remove_selected(self):
        rows = sorted([r.row() for r in self.table.selectionModel().selectedRows()], reverse=True)
        for r in rows:
            self.table.removeRow(r)
        if rows:
            self._update_select_all_state()

    def remove_checked(self):
        rows = sorted(self._checked_rows(), reverse=True)
        for r in rows:
            self.table.removeRow(r)
        if rows:
            self._update_select_all_state()

    def _fill_form_from_row(self, row, col):
        if col == 0:  # ignore checkbox clicks for editing
            return
        t_item = self.table.item(row, 1)
        l_item = self.table.item(row, 2)
        u_item = self.table.item(row, 3)
        v_item = self.table.item(row, 4)
        if t_item:
            qtime = QtCore.QTime.fromString(t_item.text().strip(), "HH:mm")
            if qtime.isValid(): self.time_edit.setTime(qtime)
        if l_item: self.label_edit.setText(l_item.text())
        if u_item: self.uri_edit.setText(u_item.text())
        if v_item and v_item.text().strip().isdigit():
            self.vol_spin.setValue(int(v_item.text().strip()))

# ---------------- app entry ----------------
def main():
    cfg = load_config()
    app = QApplication(sys.argv)

    # Force Fusion + themed palette + QSS BEFORE creating the window
    set_fusion_palette(app, cfg.get("theme", "Dark"))

    icon_path = Path("icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QtGui.QIcon(str(icon_path)))

    win = AlarmApp()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
