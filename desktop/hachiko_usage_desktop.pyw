"""Hachiko-Usage — desktop pet (formerly Hojek). Frameless always-on-top
translucent window; he walks along the top of the taskbar. Starts in ghost
mode: 50% transparent and click-through, so the mouse passes straight through
him. While click-through is on, control him from the system tray icon
(right-click it for states, sizes, and toggles).

Two pets share this app (tray menu -> pet): Hojek the plant-fox and Latch the
pangolin-fox guardian. Both atlases are 8x11 grids of 192x208 cells with
identical rows and frame counts, so switching is just an atlas swap. Cursor-gaze
is not implemented: Hojek's look rows 9-10 were never generated; Latch's exist
(see latch.json), so gaze is possible for him later."""

import json
import math
import os
import random
import sys
import threading
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction, QColor, QFont, QGuiApplication, QIcon, QPainter, QPainterPath, QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QWidget

APP_NAME = "Hachiko-Usage"

if getattr(sys, "frozen", False):
    BASE = Path(sys._MEIPASS)          # PyInstaller bundle
else:
    BASE = Path(__file__).resolve().parent.parent
CW, CH = 192, 208

# Two pets share one exe: identical 8x11 grids with identical frame counts, so
# switching is an atlas swap + frame reload. "ground" pushes a row down so its
# lowest foot lands on the shared y=202 floor line - Latch's gait rows were
# generated slightly airborne (a pounce), which reads as floating on a taskbar.
PETS = {
    "hojek": {"label": "hojek 🌱", "atlas": "hojek-atlas.png", "ground": {}},
    "latch": {"label": "latch 🛡", "atlas": "latch-atlas.png", "ground": {1: 9, 2: 17}},
}
DEFAULT_PET = "hojek"

STATES = {
    "idle":          dict(row=0, frames=6, fps=6,  loop=True),
    "running-right": dict(row=1, frames=8, fps=12, loop=True),
    "running-left":  dict(row=2, frames=8, fps=12, loop=True),
    "waving":        dict(row=3, frames=4, fps=7,  loop=True),
    "jumping":       dict(row=4, frames=5, fps=10, loop=False),
    "flying":        dict(row=4, frames=5, fps=9,  loop=True),   # hover flutter
    "failed":        dict(row=5, frames=8, fps=4,  loop=True),
    "waiting":       dict(row=6, frames=6, fps=6,  loop=True),
    "running":       dict(row=7, frames=6, fps=8,  loop=True),
    "review":        dict(row=8, frames=6, fps=7,  loop=True),
}

MENU_STATES = [
    ("wave 👋", "waving"), ("jump ⬆", "jumping"), ("fly ☁", "fly"), (None, None),
    ("working 🔧", "running"), ("waiting ⏳", "waiting"),
    ("review 📋", "review"), ("failed 😞", "failed"), ("idle", "idle"),
]

SIZES = [("tiny", 0.31), ("small", 0.45), ("medium", 0.62), ("large", 0.85)]

WALK_SPEED = 130          # px/s
FLY_SPEED = 170
GRAVITY = 1600
JUMP_VY = 520

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
USAGE_POLL_SECONDS = 90
CREDENTIALS = Path.home() / ".claude" / ".credentials.json"


def _fmt_pct(v):
    return "…" if v is None else f"{round(v)}%"


class UsageFetcher:
    """Polls Claude usage limits in a daemon thread using the local Claude Code
    OAuth token. Only percentages are kept; the token never leaves the request."""

    def __init__(self):
        self.session = None      # 0-100 or None
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
            self.ok = False    # keep last known values, just flag staleness
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
    """Little thought-cloud above the pet showing usage percentages.
    Transparent for input so it never steals clicks."""

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
        self.opacity = 1.0       # ghost mode dims the cloud with the pet
        self.resize(self.W, self.H)

    def _cloud_path(self):
        p = QPainterPath()
        p.setFillRule(Qt.FillRule.WindingFill)
        p.addRoundedRect(QRectF(8, 24, 134, 60), 21, 21)
        p.addEllipse(QRectF(24, 8, 40, 40))
        p.addEllipse(QRectF(56, 2, 48, 48))
        p.addEllipse(QRectF(94, 10, 38, 38))
        # thought-bubble tail
        p.addEllipse(QRectF(68, 86, 10, 10))
        p.addEllipse(QRectF(61, 98, 6, 6))
        return p.simplified()

    def paintEvent(self, _event):
        f = self.fetcher
        p = QPainter(self)
        p.setOpacity(self.opacity)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 120), 1.5))
        p.setBrush(QColor(255, 255, 255, 220))
        p.drawPath(self._cloud_path())
        p.setOpacity(1.0)   # ghost mode dims only the cloud; text stays readable

        label_font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        value_font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        bar_track = QColor(140, 150, 162, 110)
        rows = [("Session", f.session, 30), ("Weekly", f.weekly, 55)]
        for label, value, y in rows:
            p.setFont(label_font)
            p.setPen(QColor(28, 36, 47))
            p.drawText(QRectF(22, y, 70, 16), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            p.setFont(value_font)
            p.setPen(_pct_color(value))
            p.drawText(QRectF(70, y, 58, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, _fmt_pct(value))
            # mini progress bar
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


class HachikoUsage(QWidget):
    def __init__(self, scale=0.31, ghost=True, click_through=True):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.ghost = ghost
        self.opacity = 0.5 if ghost else 1.0
        self.click_through = click_through
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, click_through)
        self.scale = scale
        self.pet = DEFAULT_PET
        self.frames = {}
        self._load_frames()
        w = round(CW * scale)
        h = round(CH * scale)
        self.resize(w, h)

        self.area = QGuiApplication.primaryScreen().availableGeometry()
        self.x = self.area.left() + self.area.width() * 0.65   # pet center
        self.h = 0.0                                            # height above floor
        self.vy = 0.0
        self.facing = 1
        self.mode = "idle"      # idle | walk | act | pose | held | fall
        self.state = "idle"
        self.frame = 0
        self.frame_clock = 0.0
        self.walk_target = 0.0
        self.fly_target = (0.0, 0.0)
        self.fly_waypoints = 0
        self.act_until = 0.0
        self.next_thought = time.monotonic() + 2.0
        self.pinned = None

        self._press_pos = None
        self._drag_moved = 0.0
        self._last_cursor_x = 0
        self._click_timer = QTimer(self, singleShot=True, interval=260)
        self._click_timer.timeout.connect(self._single_click)

        self.usage = UsageFetcher()
        self.cloud = CloudBubble(self.usage)
        self.cloud.opacity = self.opacity
        self.cloud_visible = True
        self._make_tray()

        self._last_tick = time.monotonic()
        self._timer = QTimer(self, interval=16)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._place()

    # ---------- sprites ----------
    def _load_frames(self):
        pet = PETS[self.pet]
        path = BASE / pet["atlas"]
        atlas = QPixmap(str(path))
        if atlas.isNull():
            raise SystemExit(f"cannot load atlas: {path}")
        w = round(CW * self.scale)
        h = round(CH * self.scale)
        self.frames = {}
        for name, s in STATES.items():
            off = pet["ground"].get(s["row"], 0)
            cells = []
            for i in range(s["frames"]):
                cell = atlas.copy(QRect(i * CW, s["row"] * CH, CW, CH))
                if off:
                    shifted = QPixmap(CW, CH)
                    shifted.fill(Qt.GlobalColor.transparent)
                    painter = QPainter(shifted)
                    painter.drawPixmap(0, off, cell)
                    painter.end()
                    cell = shifted
                cells.append(cell.scaled(
                    w, h,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                ))
            self.frames[name] = cells

    def set_state(self, name):
        if name != self.state:
            self.state = name
            self.frame = 0
            self.frame_clock = 0.0
            self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setOpacity(self.opacity)
        p.drawPixmap(0, 0, self.frames[self.state][self.frame])

    # ---------- tray ----------
    def _make_tray(self):
        icon = QIcon()
        for cand in (BASE / "hojek.ico", BASE / "desktop" / "hojek.ico"):
            if cand.exists():
                icon = QIcon(str(cand))
                break
        if icon.isNull():
            icon = QIcon(self.frames["idle"][0])
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(APP_NAME)
        self._tray_menu = QMenu()
        self._tray_menu.aboutToShow.connect(lambda: self._populate_menu(self._tray_menu))
        self.tray.setContextMenu(self._tray_menu)
        self.tray.show()

    def _populate_menu(self, menu):
        for sub in menu.findChildren(QMenu):
            sub.deleteLater()
        menu.clear()
        for label, name in MENU_STATES:
            if label is None:
                menu.addSeparator()
                continue
            act = QAction(label, menu)
            act.triggered.connect(lambda _=False, n=name: self._menu_state(n))
            menu.addAction(act)
        menu.addSeparator()
        pet_menu = menu.addMenu("pet")
        for key, p in PETS.items():
            act = QAction(p["label"] + (" ✓" if self.pet == key else ""), pet_menu)
            act.triggered.connect(lambda _=False, k=key: self._set_pet(k))
            pet_menu.addAction(act)
        cloud_act = QAction(("hide" if self.cloud_visible else "show") + " usage cloud", menu)
        cloud_act.triggered.connect(self._toggle_cloud)
        menu.addAction(cloud_act)
        ghost_act = QAction("ghost 50%" + (" ✓" if self.ghost else ""), menu)
        ghost_act.triggered.connect(self._toggle_ghost)
        menu.addAction(ghost_act)
        ct_act = QAction("click-through" + (" ✓" if self.click_through else ""), menu)
        ct_act.triggered.connect(self._toggle_click_through)
        menu.addAction(ct_act)
        size = menu.addMenu("size")
        for label, sc in SIZES:
            act = QAction(label + (" ✓" if abs(self.scale - sc) < 0.01 else ""), size)
            act.triggered.connect(lambda _=False, v=sc: self._set_scale(v))
            size.addAction(act)
        menu.addSeparator()
        quit_act = QAction(f"quit {APP_NAME}", menu)
        quit_act.triggered.connect(QApplication.quit)
        menu.addAction(quit_act)

    # ---------- placement ----------
    def _floor(self):
        return self.area.bottom() + 1

    def _place(self):
        half = self.width() / 2
        self.x = min(self.area.right() - half, max(self.area.left() + half, self.x))
        hover = math.sin(time.monotonic() * 3.1) * 4 if self.mode == "fly" else 0
        top = round(self._floor() - self.height() - self.h - hover)
        self.move(round(self.x - half), top)
        if self.cloud_visible:
            bob = math.sin(time.monotonic() * 1.7) * 3
            cx = round(self.x - self.cloud.width() / 2 + 2)
            cx = min(self.area.right() - self.cloud.width(), max(self.area.left(), cx))
            cy = max(self.area.top(), round(top - self.cloud.height() + 8 + bob))
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
        self.set_state("running-right" if self.facing > 0 else "running-left")

    def _start_act(self, name, seconds):
        self.mode = "act"
        self.act_until = time.monotonic() + seconds
        self.set_state(name)

    def _jump(self):
        self.mode = "fall"
        self.vy = JUMP_VY
        self.set_state("jumping")

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
        self.set_state("flying")

    def _think(self):
        if self.mode != "idle" or self.pinned:
            return
        roll = random.random()
        if roll < 0.38:
            self._start_walk()
        elif roll < 0.50:
            self._start_act("waving", 1.15)
        elif roll < 0.58:
            self._jump()
        elif roll < 0.66:
            self._start_fly()
        elif roll < 0.76:
            self._start_act("waiting", 3.2)
        elif roll < 0.86:
            self._start_act("review", 3.0)
        elif roll < 0.92:
            self._start_act("failed", 5.2)     # nap
        else:
            self._schedule_thought(2.0)

    # ---------- main loop ----------
    def _tick(self):
        now = time.monotonic()
        dt = min(0.05, now - self._last_tick)
        self._last_tick = now

        s = STATES[self.state]
        self.frame_clock += dt
        if self.frame_clock >= 1.0 / s["fps"]:
            self.frame_clock = 0.0
            if self.frame + 1 >= s["frames"]:
                if s["loop"]:
                    self.frame = 0
            else:
                self.frame += 1
            self.update()

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
                    self._back_to_idle()
                elif self.fly_waypoints > 0:
                    self.fly_waypoints -= 1
                    self.fly_target = self._random_air_point()
                else:
                    self.fly_target = (self.x, 0.0)   # glide home
            else:
                self.x += dx / dist * step
                self.h += dh / dist * step
                if abs(dx) > 2:
                    self.facing = 1 if dx > 0 else -1
        elif self.mode == "act":
            if now >= self.act_until:
                self._back_to_idle()
        elif self.mode == "idle":
            if now >= self.next_thought:
                self._think()

        if self.usage.dirty:
            self.usage.dirty = False
            self.cloud.update()
            self.tray.setToolTip(
                f"{APP_NAME} — session {_fmt_pct(self.usage.session)}"
                f" · weekly {_fmt_pct(self.usage.weekly)}"
            )
        self._place()

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
            self.set_state("running-right" if self.facing > 0 else "running-left")
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
            self.frame = 2
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
            self._start_act("waving", 1.15)

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        self._populate_menu(menu)
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
            self._start_act("waving", 1.15)
        elif name == "idle":
            self.pinned = None
            self._back_to_idle()
        else:
            self.pinned = name
            self.mode = "pose"
            self.set_state(name)

    def _toggle_cloud(self):
        self.cloud_visible = not self.cloud_visible
        self.cloud.setVisible(self.cloud_visible)

    def _toggle_ghost(self):
        self.ghost = not self.ghost
        self.opacity = 0.5 if self.ghost else 1.0
        self.cloud.opacity = self.opacity
        self.update()
        self.cloud.update()

    def _toggle_click_through(self):
        self.click_through = not self.click_through
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, self.click_through)
        self.show()    # changing window flags hides the window; bring him back

    def _set_scale(self, scale):
        self.scale = scale
        self._load_frames()
        self.resize(round(CW * scale), round(CH * scale))
        self.update()
        self._place()

    def _set_pet(self, key):
        if key == self.pet or key not in PETS:
            return
        self.pet = key
        self._load_frames()
        if self.frame >= len(self.frames[self.state]):
            self.frame = 0
        self.update()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)   # tray keeps him alive across flag flips
    pet = HachikoUsage()
    pet.show()
    pet.cloud.show()
    if os.environ.get("HOJEK_TEST_FLY"):      # debug hook: take off right away
        QTimer.singleShot(1500, pet._start_fly)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
