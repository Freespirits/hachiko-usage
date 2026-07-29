"""Hojek 3D — desktop pet. Frameless always-on-top translucent window rendering
the user-made GLB devil (pet/desktop3d.html via QtWebEngine, transparent WebGL).
He walks along the taskbar, flies waypoints, can be dragged, clicked (wave),
double-clicked (jump). Right-click for states, form (cute/evil), size and Quit.
Usage thought-cloud (Session/Weekly) carried over from the sprite version."""

import json
import math
import os
import random
import sys
import threading
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer, QUrl, QCoreApplication
from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication, QMenu, QWidget

if getattr(sys, "frozen", False):
    BASE = Path(sys._MEIPASS)
else:
    BASE = Path(__file__).resolve().parent.parent
PAGE = BASE / "desktop3d.html"

WALK_SPEED = 130
FLY_SPEED = 170
GRAVITY = 1600
JUMP_VY = 520

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
USAGE_POLL_SECONDS = 90
CREDENTIALS = Path.home() / ".claude" / ".credentials.json"

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
            creds = json.loads(CREDENTIALS.read_text(encoding="utf-8"))
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
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
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


class Hojek3D(QWidget):
    def __init__(self, side=310):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
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
        self.form = "cute.glb"

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
        self._place()

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

    # ---------- interaction ----------
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
        for label, name in MENU_STATES:
            if label is None:
                menu.addSeparator()
                continue
            act = QAction(label, menu)
            act.triggered.connect(lambda _=False, n=name: self._menu_state(n))
            menu.addAction(act)
        menu.addSeparator()
        form = menu.addMenu("form")
        for label, f in [("cute 😈", "cute.glb"), ("evil 👿", "evil.glb")]:
            act = QAction(label + (" ✓" if self.form == f else ""), form)
            act.triggered.connect(lambda _=False, v=f: self._set_form(v))
            form.addAction(act)
        cloud_act = QAction(("hide" if self.cloud_visible else "show") + " usage cloud", menu)
        cloud_act.triggered.connect(self._toggle_cloud)
        menu.addAction(cloud_act)
        size = menu.addMenu("size")
        for label, px in [("small", 230), ("medium", 310), ("large", 400)]:
            act = QAction(label + (" ✓" if self.width() == px else ""), size)
            act.triggered.connect(lambda _=False, v=px: self.resize(v, v))
            size.addAction(act)
        quit_act = QAction("quit Hojek", menu)
        quit_act.triggered.connect(QApplication.quit)
        menu.addAction(quit_act)
        menu.exec(e.globalPos())

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
    app.setApplicationName("Hojek3D")
    pet = Hojek3D()
    pet.show()
    pet.cloud.show()
    if os.environ.get("HOJEK_TEST_FLY"):
        QTimer.singleShot(1500, pet._start_fly)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
