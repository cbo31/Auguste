"""Auguste chat dialog for Houdini. Stdlib + PySide only: the LLM, the MCP
clients and the policy all live in the sidecar (``auguste serve``), reached
over the local HTTP API. Network calls run off the main thread, because the
sidecar's tool calls are executed by Houdini's main thread."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.request

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ImportError:  # Houdini 20.x
    from PySide2 import QtCore, QtGui, QtWidgets

PORT = int(os.environ.get("AUGUSTE_PORT", "8765"))
BASE = f"http://127.0.0.1:{PORT}"
LOG_PATH = os.path.join(tempfile.gettempdir(), "auguste-sidecar.log")
STARTUP_TIMEOUT_S = 90

_dialog = None


def _request(method, path, body=None, timeout=5):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method, headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=timeout)


def _json(method, path, body=None):
    with _request(method, path, body) as response:
        return json.loads(response.read())


def _health():
    try:
        return _json("GET", "/health")
    except (urllib.error.URLError, OSError, ValueError):
        return None


def _start_sidecar():
    python = os.environ.get("AUGUSTE_PYTHON")
    if not python:
        raise RuntimeError("AUGUSTE_PYTHON is not set. Run 'auguste install-houdini <packages dir>'.")
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP")}
    log = open(LOG_PATH, "ab")
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    subprocess.Popen(
        [python, "-m", "auguste", "serve", "--port", str(PORT)],
        env=env, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        creationflags=flags, start_new_session=os.name != "nt",
    )


class _StreamWorker(QtCore.QThread):
    event = QtCore.Signal(object)

    def __init__(self, session_id, text, parent=None):
        super().__init__(parent)
        self.session_id = session_id
        self.text = text

    def run(self):
        try:
            with _request("POST", f"/sessions/{self.session_id}/messages", {"text": self.text}, timeout=None) as response:
                for line in response:
                    if line.strip():
                        self.event.emit(json.loads(line))
        except Exception as exc:
            self.event.emit({"type": "error", "message": str(exc)})
            self.event.emit({"type": "done", "reason": "error"})


class _PostWorker(QtCore.QThread):
    def __init__(self, path, body, parent=None):
        super().__init__(parent)
        self.path, self.body = path, body

    def run(self):
        try:
            _json("POST", self.path, self.body)
        except Exception:
            pass


# -- look ----------------------------------------------------------------

Qt = QtCore.Qt
C = {
    "bg": "#1b1b1d", "surface": "#242427", "surface2": "#2c2c30", "border": "#36363b",
    "text": "#e6e6e6", "muted": "#8d8d94", "accent": "#e8875b", "accent_hover": "#f09a72",
    "safe": "#5cb87a", "mutating": "#5a9cf0", "dangerous": "#e8875b", "error": "#ef6461",
}
TIER_LABEL = {"safe": "read", "mutating": "edit", "dangerous": "needs approval"}
SUGGESTIONS = ["Summarize my scene", "Create a geo node named terrain", "Find nodes with errors"]

STYLE = f"""
QDialog#Auguste {{ background: {C['bg']}; }}
QWidget {{ color: {C['text']}; font-size: 13px; }}
QLabel {{ background: transparent; }}
QScrollArea, QWidget#Feed {{ background: {C['bg']}; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {C['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
QFrame#Header {{ background: {C['bg']}; border-bottom: 1px solid {C['border']}; }}
QLabel#Title {{ font-size: 14px; font-weight: 600; }}
QLabel#Muted {{ color: {C['muted']}; font-size: 12px; }}
QToolButton#Icon {{ background: transparent; border: none; border-radius: 6px; padding: 4px 8px; color: {C['muted']}; font-size: 15px; }}
QToolButton#Icon:hover {{ background: {C['surface2']}; color: {C['text']}; }}
QToolButton#Icon::menu-indicator {{ image: none; }}
QMenu {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
QMenu::item:selected {{ background: {C['surface2']}; }}
QFrame#UserMsg {{ background: {C['surface2']}; border: 1px solid {C['border']}; border-radius: 10px; }}
QFrame#Card {{ background: {C['surface']}; border: 1px solid {C['accent']}; border-radius: 10px; }}
QFrame#ToolDetail {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 8px; }}
QLabel#Code {{ color: #c8c8cc; }}
QPushButton#Chip {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 14px; padding: 6px 14px; color: {C['text']}; }}
QPushButton#Chip:hover {{ border-color: {C['accent']}; }}
QPushButton#Primary {{ background: {C['accent']}; border: none; border-radius: 7px; padding: 6px 16px; color: #1b1b1d; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {C['accent_hover']}; }}
QPushButton#Secondary {{ background: transparent; border: 1px solid {C['border']}; border-radius: 7px; padding: 6px 16px; }}
QPushButton#Secondary:hover {{ background: {C['surface2']}; }}
QFrame#Composer {{ background: {C['surface']}; border: 1px solid {C['border']}; border-radius: 12px; }}
QFrame#Composer[focused="true"] {{ border-color: {C['accent']}; }}
QPlainTextEdit#Input {{ background: transparent; border: none; padding: 2px; selection-background-color: {C['accent']}; }}
QToolButton#Send {{ background: {C['accent']}; border: none; border-radius: 15px; color: #1b1b1d; font-size: 15px; font-weight: 700; }}
QToolButton#Send:hover {{ background: {C['accent_hover']}; }}
QToolButton#Send:disabled {{ background: {C['surface2']}; color: {C['muted']}; }}
QToolButton#Send[stop="true"] {{ background: {C['surface2']}; color: {C['text']}; border: 1px solid {C['border']}; }}
"""


def _mono():
    font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont)
    font.setPointSize(max(font.pointSize() - 2, 9))
    return font


def _label(text="", name=None, markdown=False, selectable=True):
    label = QtWidgets.QLabel()
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.MarkdownText if markdown else Qt.TextFormat.PlainText)
    label.setText(text)
    if name:
        label.setObjectName(name)
    if selectable:
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        label.setOpenExternalLinks(True)
    return label


def _dot(color, size=8):
    dot = QtWidgets.QLabel()
    dot.setFixedSize(size, size)
    dot.setStyleSheet(f"background: {color}; border-radius: {size // 2}px;")
    return dot


def _pretty(arguments):
    """key: value lines; multi-line strings (code) are shown as written."""
    lines = []
    for key, value in arguments.items():
        if isinstance(value, str) and "\n" in value:
            lines.append(f"{key}:")
            lines.extend("    " + line for line in value.splitlines())
        else:
            lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
    return "\n".join(lines) or "(no arguments)"


# -- feed items ----------------------------------------------------------


class _UserMessage(QtWidgets.QFrame):
    def __init__(self, text):
        super().__init__()
        self.setObjectName("UserMsg")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.addWidget(_label(text))


class _AssistantMessage(QtWidgets.QWidget):
    def __init__(self, text):
        super().__init__()
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(10)
        dot = _dot(C["text"], 7)
        column = QtWidgets.QVBoxLayout()
        column.setContentsMargins(0, 6, 0, 0)
        column.addWidget(dot)
        column.addStretch()
        layout.addLayout(column)
        layout.addWidget(_label(text, markdown=True), 1)


class _Notice(QtWidgets.QWidget):
    def __init__(self, text, color):
        super().__init__()
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        label = _label(text)
        label.setStyleSheet(f"color: {color}; font-size: 12px;")
        layout.addWidget(label, 1)


class _ToolRow(QtWidgets.QWidget):
    """One tool call: a compact line, click to expand arguments and result."""

    def __init__(self, event):
        super().__init__()
        self.tier = event.get("tier", "dangerous")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(4)

        self.head = QtWidgets.QPushButton()
        self.head.setFlat(True)
        self.head.setCursor(Qt.CursorShape.PointingHandCursor)
        self.head.setStyleSheet("QPushButton { background: transparent; border: none; text-align: left; padding: 0; }")
        row = QtWidgets.QHBoxLayout(self.head)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(_dot(C[self.tier]))
        name = _label(event["name"], selectable=False)
        name.setFont(_mono())
        row.addWidget(name)
        self.summary = _label(self._summary(event.get("arguments") or {}), "Muted", selectable=False)
        row.addWidget(self.summary, 1)
        self.state = _label("running…", "Muted", selectable=False)
        row.addWidget(self.state)
        self.head.setMinimumHeight(22)
        self.head.clicked.connect(self.toggle)
        layout.addWidget(self.head)

        self.detail = QtWidgets.QFrame()
        self.detail.setObjectName("ToolDetail")
        detail = QtWidgets.QVBoxLayout(self.detail)
        detail.setContentsMargins(10, 8, 10, 8)
        self.args = _label(_pretty(event.get("arguments") or {}), "Code")
        self.args.setFont(_mono())
        self.result = _label("", "Code")
        self.result.setFont(_mono())
        self.result.hide()
        detail.addWidget(self.args)
        detail.addWidget(self.result)
        self.detail.hide()
        layout.addWidget(self.detail)

    @staticmethod
    def _summary(arguments):
        for key in ("node_path", "parent_path", "name", "node_type", "query", "path"):
            if isinstance(arguments.get(key), str):
                return arguments[key]
        return ""

    def toggle(self):
        self.detail.setVisible(not self.detail.isVisible())

    def set_state(self, text, color):
        self.state.setText(text)
        self.state.setStyleSheet(f"color: {color}; font-size: 12px;")

    def finish(self, result):
        is_error = result.startswith("Error")
        self.set_state("failed" if is_error else "done", C["error"] if is_error else C["muted"])
        shown = result if len(result) < 4000 else result[:4000] + "\n…"
        self.result.setText("→ " + shown)
        self.result.show()


class _ApprovalCard(QtWidgets.QFrame):
    answered = QtCore.Signal(str, bool)

    def __init__(self, event):
        super().__init__()
        self.setObjectName("Card")
        self.call_id = event["id"]
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        title = _label(f"Allow Auguste to run **{event['name']}**?", markdown=True, selectable=False)
        badge = _label(TIER_LABEL.get(event.get("tier"), event.get("tier", "")), selectable=False)
        badge.setStyleSheet(f"color: {C['accent']}; font-size: 11px; border: 1px solid {C['accent']}; border-radius: 8px; padding: 1px 7px;")
        top = QtWidgets.QHBoxLayout()
        top.addWidget(title, 1)
        top.addWidget(badge)
        layout.addLayout(top)

        code = _label(_pretty(event.get("arguments") or {}), "Code")
        code.setFont(_mono())
        scroll = QtWidgets.QScrollArea()
        scroll.setWidget(code)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(180)
        scroll.setStyleSheet(f"QScrollArea {{ background: {C['bg']}; border-radius: 6px; }} QLabel {{ background: {C['bg']}; padding: 8px; }}")
        layout.addWidget(scroll)

        self.buttons = QtWidgets.QHBoxLayout()
        self.buttons.addStretch()
        deny = QtWidgets.QPushButton("Deny")
        deny.setObjectName("Secondary")
        allow = QtWidgets.QPushButton("Allow")
        allow.setObjectName("Primary")
        for button, approved in ((deny, False), (allow, True)):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _=False, a=approved: self._answer(a))
            self.buttons.addWidget(button)
        self.button_widgets = (deny, allow)
        layout.addLayout(self.buttons)

    def _answer(self, approved):
        for button in self.button_widgets:
            button.hide()
        self.close_as("Allowed" if approved else "Denied", C["safe"] if approved else C["muted"])
        self.answered.emit(self.call_id, approved)

    def close_as(self, text, color):
        for button in self.button_widgets:
            button.hide()
        note = _label(text, selectable=False)
        note.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.buttons.insertWidget(0, note)
        self.setStyleSheet(f"QFrame#Card {{ border-color: {C['border']}; }}")


class _Thinking(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(2, 0, 2, 0)
        self.label = _label("", "Muted", selectable=False)
        layout.addWidget(self.label)
        layout.addStretch()
        self._frames = ["·  ", "·· ", "···", " ··", "  ·", "   "]
        self._i = 0
        self._timer = QtCore.QTimer(self, interval=180, timeout=self._tick)

    def start(self):
        self._timer.start()
        self._tick()
        self.show()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _tick(self):
        self._i = (self._i + 1) % len(self._frames)
        self.label.setText(f"Auguste is working {self._frames[self._i]}")


class _Composer(QtWidgets.QFrame):
    submitted = QtCore.Signal(str)
    stop_requested = QtCore.Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("Composer")
        self.busy = False
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(8)
        self.input = QtWidgets.QPlainTextEdit()
        self.input.setObjectName("Input")
        self.input.setPlaceholderText("Ask Auguste to inspect or edit your scene…")
        self.input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.input.installEventFilter(self)
        self.input.textChanged.connect(self._fit)
        layout.addWidget(self.input, 1)
        self.send = QtWidgets.QToolButton()
        self.send.setObjectName("Send")
        self.send.setFixedSize(30, 30)
        self.send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send.clicked.connect(self._clicked)
        layout.addWidget(self.send, 0, Qt.AlignmentFlag.AlignBottom)
        self.set_busy(False)
        self._fit()

    def _fit(self):
        lines = max(1, min(8, int(self.input.document().size().height())))
        height = self.input.fontMetrics().lineSpacing() * lines + 10
        self.input.setFixedHeight(height)
        if not self.busy:
            self.send.setEnabled(bool(self.input.toPlainText().strip()))

    def eventFilter(self, obj, event):
        if obj is self.input:
            if event.type() == QtCore.QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._clicked()
                    return True
            elif event.type() in (QtCore.QEvent.Type.FocusIn, QtCore.QEvent.Type.FocusOut):
                self.setProperty("focused", event.type() == QtCore.QEvent.Type.FocusIn)
                self.style().unpolish(self)
                self.style().polish(self)
        return super().eventFilter(obj, event)

    def _clicked(self):
        if self.busy:
            self.stop_requested.emit()
            return
        text = self.input.toPlainText().strip()
        if text:
            self.input.clear()
            self.submitted.emit(text)

    def set_busy(self, busy):
        self.busy = busy
        self.send.setText("■" if busy else "↑")
        self.send.setToolTip("Stop" if busy else "Send (Enter)")
        self.send.setProperty("stop", busy)
        self.send.style().unpolish(self.send)
        self.send.style().polish(self.send)
        self.send.setEnabled(busy or bool(self.input.toPlainText().strip()))


# -- window --------------------------------------------------------------


class AugusteDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Auguste")
        self.setWindowTitle("Auguste")
        self.setStyleSheet(STYLE)
        self.resize(520, 720)
        self.session_id = None
        self.ready = False
        self._workers = set()
        self._waited = 0
        self._rows = {}
        self._cards = {}

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        self.scroll = QtWidgets.QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        feed = QtWidgets.QWidget()
        feed.setObjectName("Feed")
        self.feed = QtWidgets.QVBoxLayout(feed)
        self.feed.setContentsMargins(18, 16, 18, 16)
        self.feed.setSpacing(12)
        self.feed.addStretch()
        self.scroll.setWidget(feed)
        self.scroll.verticalScrollBar().rangeChanged.connect(
            lambda _min, maximum: self.scroll.verticalScrollBar().setValue(maximum)
        )
        root.addWidget(self.scroll, 1)

        self.thinking = _Thinking()
        self.thinking.hide()
        self.welcome = self._build_welcome()
        self._add(self.welcome)

        bottom = QtWidgets.QVBoxLayout()
        bottom.setContentsMargins(14, 6, 14, 12)
        bottom.setSpacing(6)
        self.composer = _Composer()
        self.composer.submitted.connect(self.send)
        self.composer.stop_requested.connect(self.stop)
        bottom.addWidget(self.composer)
        hint = _label("Enter to send · Shift+Enter for a new line", "Muted", selectable=False)
        hint.setAlignment(Qt.AlignmentFlag.AlignRight)
        bottom.addWidget(hint)
        root.addLayout(bottom)

        self._poll = QtCore.QTimer(self, interval=500, timeout=self._check_server)
        self.start_session()

    def _build_header(self):
        header = QtWidgets.QFrame()
        header.setObjectName("Header")
        layout = QtWidgets.QHBoxLayout(header)
        layout.setContentsMargins(16, 10, 10, 10)
        layout.setSpacing(8)
        title = _label("Auguste", "Title", selectable=False)
        layout.addWidget(title)
        self.status_dot = _dot(C["muted"])
        layout.addWidget(self.status_dot)
        self.status = _label("Starting…", "Muted", selectable=False)
        layout.addWidget(self.status, 1)

        new = QtWidgets.QToolButton()
        new.setObjectName("Icon")
        new.setText("＋")
        new.setToolTip("New session")
        new.clicked.connect(self.new_session)
        layout.addWidget(new)

        menu = QtWidgets.QMenu(self)
        menu.addAction("New session", self.new_session)
        menu.addSeparator()
        menu.addAction("Open sidecar log", lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(LOG_PATH)))
        more = QtWidgets.QToolButton()
        more.setObjectName("Icon")
        more.setText("⋯")
        more.setMenu(menu)
        more.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        layout.addWidget(more)
        return header

    def _build_welcome(self):
        box = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(box)
        layout.setContentsMargins(0, 40, 0, 0)
        layout.setSpacing(10)
        hello = _label("What should we build?", selectable=False)
        hello.setStyleSheet("font-size: 20px; font-weight: 600;")
        hello.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub = _label("Auguste reads and edits the live scene. Risky actions wait for your approval.", "Muted", selectable=False)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(hello)
        layout.addWidget(sub)
        chips = QtWidgets.QVBoxLayout()
        chips.setContentsMargins(0, 14, 0, 0)
        for text in SUGGESTIONS:
            chip = QtWidgets.QPushButton(text)
            chip.setObjectName("Chip")
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.clicked.connect(lambda _=False, t=text: self.send(t))
            chips.addWidget(chip, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addLayout(chips)
        return box

    # -- session ---------------------------------------------------------

    def start_session(self):
        self._set_status("Starting…", C["muted"])
        if _health() is None:
            try:
                _start_sidecar()
            except Exception as exc:
                self._fail(f"Could not start the Auguste sidecar: {exc}")
                return
            self._set_status("Starting the agent…", C["muted"])
        self._waited = 0
        self._poll.start()
        self._check_server()

    def _check_server(self):
        health = _health()
        if health is None:
            self._waited += 0.5
            if self._waited >= STARTUP_TIMEOUT_S:
                self._poll.stop()
                self._fail(f"The agent did not start. See {LOG_PATH}")
            return
        self._poll.stop()
        try:
            self.session_id = _json("POST", "/sessions")["session_id"]
        except Exception as exc:
            self._fail(f"Could not open a session: {exc}")
            return
        self.ready = True
        tools = f" · {health['tools']} tools" if "tools" in health else ""
        self._set_status(f"{health.get('backend', '?')} · {health.get('model', '?')}{tools}", C["safe"])
        self.composer.input.setFocus()
        if health.get("auth") is False:
            self._set_status("Not signed in", C["accent"])
            self._add(_Notice("Claude Code is not signed in. Run `claude auth login` in a terminal, then start a new session.", C["accent"]))

    def new_session(self):
        if self.composer.busy:
            self.stop()
        for i in reversed(range(self.feed.count() - 1)):
            widget = self.feed.itemAt(i).widget()
            if widget is not None and widget not in (self.thinking, self.welcome):
                widget.deleteLater()
        self._rows.clear()
        self._cards.clear()
        self.welcome.show()
        self.ready = False
        self.start_session()

    def _fail(self, message):
        self._set_status("Not connected", C["error"])
        self._add(_Notice(message, C["error"]))

    def _set_status(self, text, color):
        self.status.setText(text)
        self.status_dot.setStyleSheet(f"background: {color}; border-radius: 4px;")

    # -- chat ------------------------------------------------------------

    def send(self, text):
        if not self.ready or self.composer.busy:
            return
        self.welcome.hide()
        self._add(_UserMessage(text))
        self._set_busy(True)
        worker = _StreamWorker(self.session_id, text, self)
        worker.event.connect(self._on_event)
        self._run(worker)

    def stop(self):
        if self.session_id:
            self._run(_PostWorker(f"/sessions/{self.session_id}/stop", {}, self))

    def _on_event(self, event):
        kind = event.get("type")
        if kind == "text":
            self._add(_AssistantMessage(event["text"]))
        elif kind == "tool_call":
            row = self._rows[event["id"]] = _ToolRow(event)
            self._add(row)
        elif kind == "confirm":
            card = self._cards[event["id"]] = _ApprovalCard(event)
            card.answered.connect(self._answer)
            self._rows[event["id"]].set_state("waiting for you", C["accent"])
            self._add(card)
            self.thinking.stop()
            QtWidgets.QApplication.alert(self)
        elif kind == "tool_result":
            if event["id"] in self._rows:
                self._rows[event["id"]].finish(event.get("result", ""))
        elif kind == "tool_skipped":
            row = self._rows.get(event["id"]) or self._add(_ToolRow(event))
            row.set_state("denied" if event["reason"] == "declined" else "skipped", C["muted"])
            card = self._cards.pop(event["id"], None)
            if card is not None and event["reason"] == "stopped":
                card.close_as("Stopped", C["muted"])
        elif kind == "error":
            self._add(_Notice(event.get("message", ""), C["error"]))
        elif kind == "done":
            reason = event.get("reason")
            if reason not in ("finished", "error", None):
                labels = {"stopped": "Stopped.", "max_turns": "Stopped: turn limit reached.", "max_tokens": "Stopped: token limit reached."}
                self._add(_Notice(labels.get(reason, reason), C["muted"]))
            self._set_busy(False)

    def _answer(self, call_id, approved):
        self._cards.pop(call_id, None)
        if call_id in self._rows:
            self._rows[call_id].set_state("running…" if approved else "denied", C["muted"])
        self._run(_PostWorker(f"/sessions/{self.session_id}/confirm", {"id": call_id, "approved": approved}, self))
        if self.composer.busy:
            self.thinking.start()

    # -- helpers ---------------------------------------------------------

    def _add(self, widget):
        # keep the "working" indicator as the last item above the stretch
        index = self.feed.count() - 1
        if self.feed.indexOf(self.thinking) >= 0:
            index -= 1
        self.feed.insertWidget(index, widget)
        return widget

    def _run(self, worker):
        self._workers.add(worker)
        worker.finished.connect(lambda: self._workers.discard(worker))
        worker.start()

    def _set_busy(self, busy):
        self.composer.set_busy(busy)
        if busy:
            if self.feed.indexOf(self.thinking) < 0:
                self.feed.insertWidget(self.feed.count() - 1, self.thinking)
            self.thinking.start()
        else:
            self.thinking.stop()


def show():
    """Entry point for the 'Start Session' shelf tool."""
    global _dialog
    if _dialog is not None and _dialog.isVisible():
        _dialog.raise_()
        _dialog.activateWindow()
        return _dialog
    try:
        import hou

        parent = hou.qt.mainWindow()
    except Exception:
        parent = None
    _dialog = AugusteDialog(parent)
    _dialog.setWindowFlag(Qt.WindowType.Window, True)
    _dialog.show()
    return _dialog
