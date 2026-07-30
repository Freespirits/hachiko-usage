"""Devil-Usage &_& — a tiny 3D devil desktop pet that watches your Claude usage.

Frameless, always-on-top, translucent and (by default) fully click-through, so
he never steals a click. He walks along the taskbar, flies waypoints around the
screen, and carries a thought-cloud with your Session / Weekly usage.

Control him from the system-tray devil icon: states, form (cute/evil), ghost
mode, opacity, size, quit. Turn ghost mode OFF to drag him, click (wave),
double-click (jump) and right-click him directly.

The 3D body is a user-made GLB rendered by desktop3d.html (three.js inside
QtWebEngine, transparent WebGL). Python owns behavior and feeds the renderer."""

import json
import math
import os
import random
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer, QUrl, QCoreApplication
from PySide6.QtGui import (
    QAction, QColor, QDesktopServices, QFont, QGuiApplication, QIcon,
    QPainter, QPainterPath, QPen,
)
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

IS_MAC = sys.platform == "darwin"

if getattr(sys, "frozen", False):
    BASE = HERE = Path(sys._MEIPASS)   # frozen: everything is flattened to one dir
else:
    HERE = Path(__file__).resolve().parent   # desktop/ - script + .ico live here
    BASE = HERE.parent                       # repo root - renderer + models live here
PAGE = BASE / "desktop3d.html"
ICON = HERE / "hojek.ico"


def _tray_icon():
    """The .ico has crisp 16/24/32 px frames for the Windows notification area;
    the macOS menu bar wants a 22 pt PNG (with an @2x beside it for Retina)."""
    if IS_MAC:
        for p in (HERE / "tray.png", BASE / "assets" / "tray.png"):
            if p.exists():
                return p
    return ICON


def keep_visible_on_mac(w):
    """Qt::Tool maps to an NSPanel on macOS, and an NSPanel hides itself the
    moment another app takes focus — fatal for a pet that is supposed to just be
    around. This attribute pins it open regardless of which app is active."""
    if IS_MAC:
        w.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)

WALK_SPEED = 130
FLY_SPEED = 170
GRAVITY = 1600
JUMP_VY = 520

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
USAGE_POLL_SECONDS = 90
CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
KEYCHAIN_SERVICE = "Claude Code-credentials"


def read_credentials():
    """Claude Code keeps its OAuth token in ~/.claude/.credentials.json on
    Windows and Linux, but in the login Keychain on macOS. Try the file first
    either way — some macOS setups still have it — then fall back to `security`.

    The first Keychain read shows a one-time macOS prompt, because the item was
    created by Claude Code and this is a different binary asking for it."""
    if CREDENTIALS.exists():
        return json.loads(CREDENTIALS.read_text(encoding="utf-8"))
    if IS_MAC:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if out.returncode == 0 and out.stdout.strip():
            return json.loads(out.stdout.strip())
    raise FileNotFoundError("no Claude Code credentials found")

STAR_URL = "https://github.com/Freespirits/hachiko-usage"

MENU_STATES = [
    ("wave 👋", "waving"), ("jump ⬆", "jumping"), ("fly ☁", "fly"), (None, None),
    ("working 🔧", "running"), ("waiting ⏳", "waiting"),
    ("review 📋", "review"), ("failed 😞", "failed"), ("idle", "idle"),
]


class UsageFetcher:
    """Polls Claude usage limits in a daemon thread using the local Claude Code
    OAuth token. Only percentages are kept; the token never leaves the request."""

    def __init__(self):
        self.session = None
        self.weekly = None
        self.ok = False
        self.dirty = False
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            self._fetch()
            time.sleep(USAGE_POLL_SECONDS)

    def _fetch(self):
        try:
            creds = read_credentials()
            token = creds["claudeAiOauth"]["accessToken"]
            req = urllib.request.Request(
                USAGE_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "anthropic-beta": "oauth-2025-04-20",
                    "Content-Type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode())
            session = weekly = None
            for lim in data.get("limits") or []:
                if lim.get("group") == "session":
                    session = lim.get("percent")
                elif lim.get("kind") == "weekly_all":
                    weekly = lim.get("percent")
            if session is None and data.get("five_hour"):
                session = data["five_hour"].get("utilization")
            if weekly is None and data.get("seven_day"):
                weekly = data["seven_day"].get("utilization")
            self.session, self.weekly, self.ok = session, weekly, True
        except Exception:
            self.ok = False
        self.dirty = True


def _pct_color(pct):
    if pct is None:
        return QColor(120, 130, 142)
    if pct >= 85:
        return QColor(186, 51, 43)
    if pct >= 60:
        return QColor(173, 94, 6)
    return QColor(18, 121, 63)


class CloudBubble(QWidget):
    """Little thought-cloud above the pet showing usage percentages."""

    W, H = 150, 106

    def __init__(self, fetcher):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        keep_visible_on_mac(self)
        self.fetcher = fetcher
        self.resize(self.W, self.H)

    def _cloud_path(self):
        p = QPainterPath()
        p.setFillRule(Qt.FillRule.WindingFill)
        p.addRoundedRect(QRectF(8, 24, 134, 60), 21, 21)
        p.addEllipse(QRectF(24, 8, 40, 40))
        p.addEllipse(QRectF(56, 2, 48, 48))
        p.addEllipse(QRectF(94, 10, 38, 38))
        p.addEllipse(QRectF(68, 86, 10, 10))
        p.addEllipse(QRectF(61, 98, 6, 6))
        return p.simplified()

    def paintEvent(self, _event):
        f = self.fetcher
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 90), 1.5))
        p.setBrush(QColor(255, 255, 255, 165))
        p.drawPath(self._cloud_path())

        def fmt(v):
            return "…" if v is None else f"{round(v)}%"

        label_font = QFont("Segoe UI", 9, QFont.Weight.DemiBold)
        value_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        bar_track = QColor(140, 150, 162, 110)
        rows = [("Session", f.session, 30), ("Weekly", f.weekly, 55)]
        for label, value, y in rows:
            p.setFont(label_font)
            p.setPen(QColor(28, 36, 47))
            p.drawText(QRectF(22, y, 70, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            p.setFont(value_font)
            p.setPen(_pct_color(value))
            p.drawText(QRectF(70, y, 58, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, fmt(value))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bar_track)
            p.drawRoundedRect(QRectF(22, y + 17, 106, 5), 2.5, 2.5)
            if value:
                p.setBrush(_pct_color(value))
                p.drawRoundedRect(QRectF(22, y + 17, 106 * min(100, value) / 100, 5), 2.5, 2.5)
        if not f.ok and f.session is not None:
            p.setPen(QColor(90, 96, 104))
            p.setFont(QFont("Segoe UI", 7))
            p.drawText(QRectF(8, 78, 134, 10), Qt.AlignmentFlag.AlignHCenter, "offline")


class Devil(QWidget):
    def __init__(self, side=310):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        keep_visible_on_mac(self)
        self.resize(side, side)

        self.view = QWebEngineView(self)
        self.view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.view.setStyleSheet("background: transparent;")
        self.view.page().setBackgroundColor(Qt.GlobalColor.transparent)
        s = self.view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)
        self.view.setGeometry(0, 0, side, side)
        self.view.load(QUrl.fromLocalFile(str(PAGE)))

        self.area = QGuiApplication.primaryScreen().availableGeometry()
        self.x = self.area.left() + self.area.width() * 0.65
        self.h = 0.0
        self.vy = 0.0
        self.facing = 1
        self.mode = "idle"          # idle | walk | act | pose | held | fall | fly
        self.state = "idle"
        self.walk_target = 0.0
        self.fly_target = (0.0, 0.0)
        self.fly_waypoints = 0
        self.act_until = 0.0
        self.next_thought = time.monotonic() + 2.0
        self.pinned = None
        self.form = "cute-hd.glb"
        self.ghost = True           # click-through: he never steals input
        self.opacity_val = 0.85

        self._press_pos = None
        self._drag_moved = 0.0
        self._last_cursor_x = 0
        self._click_timer = QTimer(self, singleShot=True, interval=260)
        self._click_timer.timeout.connect(self._single_click)

        self.usage = UsageFetcher()
        self.cloud = CloudBubble(self.usage)
        self.cloud_visible = True
        self.head_gap = 70
        QTimer.singleShot(4000, self._sync_headroom)

        self._prev = (self.x, self.h)
        self._js_at = 0.0
        self._last_tick = time.monotonic()
        self._timer = QTimer(self, interval=16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._apply_ghost()
        self._apply_opacity()
        self._place()

    # ---------- ghost / opacity ----------
    def _apply_ghost(self):
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, self.ghost)
        self.show()
        if IS_MAC:
            # toggling a window flag rebuilds the NSWindow, which can leave it
            # sitting below other windows despite WindowStaysOnTopHint
            self.raise_()

    def _apply_opacity(self):
        self.setWindowOpacity(self.opacity_val)

    def toggle_ghost(self):
        self.ghost = not self.ghost
        self._apply_ghost()

    def set_opacity(self, v):
        self.opacity_val = v
        self._apply_opacity()

    # ---------- js bridge ----------
    def _js(self, code):
        self.view.page().runJavaScript("window.H&&(" + code + ")")

    def set_state(self, name):
        if name != self.state:
            self.state = name

    def _sync_headroom(self):
        def got(v):
            try:
                self.head_gap = max(0, int(v))
            except (TypeError, ValueError):
                pass
        self.view.page().runJavaScript("window.H?H.headroom():70", got)

    def resizeEvent(self, _e):
        self.view.setGeometry(0, 0, self.width(), self.height())
        QTimer.singleShot(600, self._sync_headroom)

    # ---------- placement ----------
    def _floor(self):
        return self.area.bottom() + 1

    def _place(self):
        half = self.width() / 2
        self.x = min(self.area.right() - half, max(self.area.left() + half, self.x))
        top = round(self._floor() - self.height() - self.h)
        self.move(round(self.x - half), top)
        if self.cloud_visible:
            bob = math.sin(time.monotonic() * 1.7) * 3
            cx = round(self.x - self.cloud.width() / 2 + 2)
            cx = min(self.area.right() - self.cloud.width(), max(self.area.left(), cx))
            cy = max(self.area.top(), round(top + self.head_gap - self.cloud.height() + 10 + bob))
            self.cloud.move(cx, cy)

    # ---------- behavior ----------
    def _back_to_idle(self):
        self.mode = "idle"
        self.set_state("idle")
        self._schedule_thought()

    def _schedule_thought(self, s=None):
        self.next_thought = time.monotonic() + (s if s is not None else random.uniform(2.5, 7.0))

    def _start_walk(self):
        half = self.width() / 2
        self.walk_target = random.uniform(self.area.left() + half, self.area.right() - half)
        if abs(self.walk_target - self.x) < 60:
            self._schedule_thought(1.5)
            return
        self.facing = 1 if self.walk_target > self.x else -1
        self.mode = "walk"
        self.set_state("walk")

    def _start_act(self, name, seconds):
        self.mode = "act"
        self.act_until = time.monotonic() + seconds
        self.set_state(name)

    def _jump(self):
        self.mode = "fall"
        self.vy = JUMP_VY
        self.set_state("jumping")
        self._js("H.event('jump')")

    def _random_air_point(self):
        half = self.width() / 2
        max_alt = max(160.0, self.area.height() * 0.6)
        return (
            random.uniform(self.area.left() + half, self.area.right() - half),
            random.uniform(120.0, max_alt),
        )

    def _start_fly(self):
        if self.mode == "held":
            return
        self.pinned = None
        self.mode = "fly"
        self.fly_waypoints = random.randint(1, 3)
        self.fly_target = self._random_air_point()
        self.set_state("fly")

    def _think(self):
        if self.mode != "idle" or self.pinned:
            return
        roll = random.random()
        if roll < 0.34:
            self._start_walk()
        elif roll < 0.46:
            self._start_fly()
        elif roll < 0.58:
            self._start_act("waving", 1.3)
        elif roll < 0.66:
            self._jump()
        elif roll < 0.76:
            self._start_act("waiting", 3.2)
        elif roll < 0.86:
            self._start_act("review", 3.0)
        elif roll < 0.92:
            self._start_act("failed", 5.2)
        else:
            self._schedule_thought(2.0)

    # ---------- main loop ----------
    def _tick(self):
        nowt = time.monotonic()
        dt = min(0.05, nowt - self._last_tick)
        self._last_tick = nowt

        if self.mode == "walk":
            self.x += self.facing * WALK_SPEED * dt
            if (self.facing > 0 and self.x >= self.walk_target) or (
                self.facing < 0 and self.x <= self.walk_target
            ):
                self._back_to_idle()
        elif self.mode == "fall":
            self.vy -= GRAVITY * dt
            self.h += self.vy * dt
            if self.h <= 0:
                self.h = 0.0
                self.vy = 0.0
                self._js("H.event('land')")
                self._back_to_idle()
        elif self.mode == "fly":
            tx, th = self.fly_target
            dx, dh = tx - self.x, th - self.h
            dist = math.hypot(dx, dh)
            step = FLY_SPEED * dt
            if dist <= step:
                self.x, self.h = tx, th
                if th <= 0:
                    self.h = 0.0
                    self._js("H.event('land')")
                    self._back_to_idle()
                elif self.fly_waypoints > 0:
                    self.fly_waypoints -= 1
                    self.fly_target = self._random_air_point()
                else:
                    self.fly_target = (self.x, 0.0)
            else:
                self.x += dx / dist * step
                self.h += dh / dist * step
                if abs(dx) > 2:
                    self.facing = 1 if dx > 0 else -1
        elif self.mode == "act":
            if nowt >= self.act_until:
                self._back_to_idle()
        elif self.mode == "idle":
            if nowt >= self.next_thought:
                self._think()

        if self.usage.dirty:
            self.usage.dirty = False
            self.cloud.update()
        self._place()

        # feed the renderer ~20 Hz
        if nowt - self._js_at > 0.05:
            px, ph = self._prev
            vx = (self.x - px) / max(dt, 1e-3)
            vyv = (self.h - ph) / max(dt, 1e-3)
            self._prev = (self.x, self.h)
            self._js_at = nowt
            air = 1 if (self.h > 2 or self.mode in ("fly", "fall")) else 0
            held = "held" if self.mode == "held" else self.state
            self._js(f"H.set('{held}',{self.facing},{vx:.0f},{vyv:.0f},{air})")

    # ---------- interaction (active only when ghost mode is off) ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_pos = e.globalPosition()
            self._drag_moved = 0.0
            self._last_cursor_x = e.globalPosition().x()

    def mouseMoveEvent(self, e):
        if self._press_pos is None:
            return
        pos = e.globalPosition()
        self._drag_moved += abs(pos.x() - self._last_cursor_x) + abs(pos.y() - self._press_pos.y()) * 0.05
        if self._drag_moved > 6:
            self.mode = "held"
            self.pinned = None
            dx = pos.x() - self._last_cursor_x
            if abs(dx) > 1.5:
                self.facing = 1 if dx > 0 else -1
            self.set_state("held")
            self.x = pos.x()
            self.h = max(0.0, self._floor() - pos.y() - self.height() * 0.55)
            self._place()
        self._last_cursor_x = pos.x()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._press_pos is None:
            return
        was_drag = self._drag_moved > 6
        self._press_pos = None
        if was_drag:
            self.mode = "fall"
            self.vy = 0.0
            self.set_state("jumping")
        elif not self._click_timer.isActive():
            self._click_timer.start()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._click_timer.stop()
            self.pinned = None
            if self.mode != "held":
                self._jump()

    def _single_click(self):
        if self.mode in ("idle", "act", "pose"):
            self.pinned = None
            self._start_act("waving", 1.3)

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        self.build_menu(menu)
        menu.exec(e.globalPos())

    # ---------- menu (shared by tray + right-click) ----------
    def build_menu(self, menu):
        star = QAction("⭐ star this pet on GitHub", menu)
        star.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(STAR_URL)))
        menu.addAction(star)
        menu.addSeparator()
        for label, name in MENU_STATES:
            if label is None:
                menu.addSeparator()
                continue
            act = QAction(label, menu)
            act.triggered.connect(lambda _=False, n=name: self._menu_state(n))
            menu.addAction(act)
        menu.addSeparator()
        form = menu.addMenu("form")
        for label, f in [("cute 😈", "cute-hd.glb"), ("evil 👿", "evil-hd.glb")]:
            act = QAction(label + (" ✓" if self.form == f else ""), form)
            act.triggered.connect(lambda _=False, v=f: self._set_form(v))
            form.addAction(act)
        ghost = QAction(("✓ " if self.ghost else "") + "ghost mode (click-through)", menu)
        ghost.triggered.connect(self.toggle_ghost)
        menu.addAction(ghost)
        opac = menu.addMenu("opacity")
        for label, v in [("50%", 0.5), ("70%", 0.7), ("85%", 0.85), ("100%", 1.0)]:
            act = QAction(label + (" ✓" if abs(self.opacity_val - v) < 0.01 else ""), opac)
            act.triggered.connect(lambda _=False, val=v: self.set_opacity(val))
            opac.addAction(act)
        cloud_act = QAction(("hide" if self.cloud_visible else "show") + " usage cloud", menu)
        cloud_act.triggered.connect(self._toggle_cloud)
        menu.addAction(cloud_act)
        size = menu.addMenu("size")
        for label, px in [("small", 230), ("medium", 310), ("large", 400)]:
            act = QAction(label + (" ✓" if self.width() == px else ""), size)
            act.triggered.connect(lambda _=False, v=px: self.resize(v, v))
            size.addAction(act)
        quit_act = QAction("quit devil", menu)
        quit_act.triggered.connect(QApplication.quit)
        menu.addAction(quit_act)

    def _menu_state(self, name):
        if name == "fly":
            self._start_fly()
        elif name == "jumping":
            self.pinned = None
            if self.mode != "held":
                self._jump()
        elif name == "waving":
            self.pinned = None
            self._start_act("waving", 1.3)
        elif name == "idle":
            self.pinned = None
            self._back_to_idle()
        else:
            self.pinned = name
            self.mode = "pose"
            self.set_state(name)

    def _set_form(self, f):
        self.form = f
        self._js(f"H.form('{f}')")
        QTimer.singleShot(2500, self._sync_headroom)

    def _toggle_cloud(self):
        self.cloud_visible = not self.cloud_visible
        self.cloud.setVisible(self.cloud_visible)


def main():
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    app.setApplicationName("Devil-Usage")
    app.setQuitOnLastWindowClosed(False)
    pet = Devil()
    pet.show()
    pet.cloud.show()

    tray = QSystemTrayIcon(QIcon(str(_tray_icon())), app)
    tray.setToolTip("Devil-Usage &_& — right-click me")
    tray_menu = QMenu()
    pet.build_menu(tray_menu)
    # rebuild the menu each time so checkmarks stay fresh
    def refresh_menu():
        tray_menu.clear()
        pet.build_menu(tray_menu)
    tray_menu.aboutToShow.connect(refresh_menu)
    tray.setContextMenu(tray_menu)
    tray.show()
    app._tray, app._tray_menu = tray, tray_menu   # keep refs alive

    if os.environ.get("DEVIL_TEST_FLY"):
        QTimer.singleShot(1500, pet._start_fly)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
