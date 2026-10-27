"""The macOS visual language, drawn with Qt on Windows."""
import math

from PySide6.QtCore import QByteArray, QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QFrame, QLabel, QWidget

BASE, SIDEBAR, CARD, INPUT = "#121214", "#171719", "#1c1c21", "#242429"
CYAN, GREEN, YELLOW, PINK = "#00d9f2", "#4df266", "#ffd91a", "#ff4d99"
BRAND = (CYAN, GREEN, YELLOW, PINK)

STYLE = """
QWidget { color: #e8e8e9; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow, QWidget#page, QScrollArea, QStackedWidget { background: #121214; }
QFrame#sidebar { background: #171719; border: none; }
QFrame#card { background: #1c1c21; border: none; border-radius: 12px; }
QLabel { background: transparent; border: none; }
QLabel[role='title'] { font-size: 22px; font-weight: 700; color: white; }
QLabel[role='section'] { font-size: 13px; font-weight: 600; color: #e6e6e7; }
QLabel[role='row'] { font-size: 12px; font-weight: 500; color: #b3b3b6; }
QLabel[role='detail'] { font-size: 10px; color: #626268; }
QLabel[role='stat'] { font-size: 15px; font-weight: 600; color: #d9d9dc; }
QLabel[role='keycap'] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #303036,stop:1 #242429); border: 1px solid #3b3b42;
 border-bottom: 2px solid #101013; border-radius: 6px; color: #ccccd0;
 font-size: 11px; font-weight: 600; padding: 4px 9px; }
QPushButton { background: #303034; border: 1px solid #39393e; border-radius: 6px;
 padding: 4px 10px; font-size: 11px; color: #d5d5d8; min-height: 16px; }
QPushButton:hover { background: #3a3a40; border-color: #484850; }
QPushButton:pressed { background: #242429; }
QPushButton:disabled { color: #55555b; background: #232328; border-color: #2c2c32; }
QPushButton[role='text'] { background: transparent; border: none; color: #707078; padding: 0; }
QPushButton[role='text']:hover { color: #d5d5db; }
QPushButton[role='nav'] { background: transparent; border: none; border-radius: 7px;
 text-align: left; padding: 0; }
QPushButton[role='nav']:hover { background: #222225; }
QPushButton[role='nav']:checked { background: #2a2a2d; }
QLabel[role='badge'] { background: #36363b; color: #bfbfc4; border-radius: 7px;
 font-size: 10px; font-weight: 700; padding: 2px 6px; }
QLineEdit, QKeySequenceEdit { background: #242429; border: 1px solid transparent;
 border-radius: 8px; padding: 8px; color: #d0d0d5; selection-background-color: #32575d; }
QLineEdit:focus, QKeySequenceEdit:focus { border-color: #505059; }
QComboBox { background: #303034; border: 1px solid #39393e; border-radius: 6px;
 padding: 4px 24px 4px 10px; color: #d5d5d8; font-size: 11px; min-height: 18px; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow { image: none; }
QComboBox QAbstractItemView { background: #242429; border: 1px solid #414148;
 selection-background-color: #36363e; outline: none; padding: 4px; }
QScrollArea { border: none; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 4px 1px; }
QScrollBar::handle:vertical { background: #333338; min-height: 40px; border-radius: 3px; }
QScrollBar::handle:vertical:hover { background: #53535b; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QMenu { background: #242429; border: 1px solid #414148; border-radius: 6px; padding: 5px; }
QMenu::item { padding: 7px 20px; border-radius: 4px; }
QMenu::item:selected { background: #36363e; }
QDialog, QMessageBox { background: #171719; }
QToolTip { background: #242429; color: #dedee2; border: 1px solid #414148; padding: 8px; }
"""


# Windows 11 Mica: let the backdrop show through; cards become subtle layers.
MICA_STYLE = """
QMainWindow, QWidget#page, QScrollArea, QScrollArea > QWidget, QStackedWidget { background: transparent; }
QFrame#sidebar { background: rgba(0, 0, 0, 0.18); }
QFrame#card { background: rgba(255, 255, 255, 0.055); }
"""


def label(text, role=None, parent=None):
    widget = QLabel(text, parent)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        widget.setProperty("role", role)
    return widget


def divider():
    widget = QFrame()
    widget.setFixedHeight(1)
    widget.setStyleSheet("background: #2b2b30; border: none;")
    return widget


def gradient_line():
    widget = QFrame()
    widget.setFixedHeight(1)
    widget.setStyleSheet("background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
        "stop:0 #155963,stop:.33 #24612d,stop:.66 #665716,stop:1 #662644); border:none;")
    return widget


def icon(name, color="#77777d", size=18):
    shapes = {
        "settings": '<path d="m9 3 .7-1h4.6l.7 1 .5 2 2 .9 1.8-.6 1.2 1.6-.8 1.8.2 2.2 1.6 1v2.2l-1.6 1-.2 2.2.8 1.8-1.2 1.6-1.8-.6-2 .9-.5 2-.7 1H9l-.7-1-.5-2-2-.9-1.8.6-1.2-1.6.8-1.8-.2-2.2-1.6-1v-2.2l1.6-1 .2-2.2-.8-1.8L4 5.3l1.8.6 2-.9Z"/><circle cx="12" cy="12" r="3.3"/>',
        "transcripts": '<path d="M5 4h14a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H9l-5 3v-3H3a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/><path d="M6 9h12M6 13h8"/>',
        "permissions": '<path d="m12 2 8 3v6c0 6-8 11-8 11S4 17 4 11V5Z"/><rect x="9" y="10" width="6" height="6" rx="1"/><path d="M10 10V8a2 2 0 0 1 4 0v2"/>',
        "sidebar": '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M5 8h2M5 11h2"/>',
        "mic": '<rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8"/>',
        "copy": '<rect x="8" y="8" width="13" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
        "search": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
        "refresh": '<path d="M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5M4 16a8 8 0 0 0 14 3l3-3m0 5v-5h-5"/>',
    }
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{shapes[name]}</g></svg>'
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


class Switch(QAbstractButton):
    def __init__(self, name, checked=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(30, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(name)
        self.setToolTip(name)
        self.position = float(checked)
        self.slide = QVariantAnimation(self)
        self.slide.setDuration(140)
        self.slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.slide.valueChanged.connect(self.set_position)
        self.toggled.connect(self.animate)

    def animate(self, checked):
        self.slide.stop()
        if not self.isVisible():
            self.set_position(float(checked))
            return
        self.slide.setStartValue(self.position)
        self.slide.setEndValue(float(checked))
        self.slide.start()

    def set_position(self, value):
        self.position = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        off, on = QColor("#39393f"), QColor(GREEN)
        t = self.position
        painter.setBrush(QColor.fromRgbF(off.redF() + (on.redF()-off.redF())*t,
            off.greenF() + (on.greenF()-off.greenF())*t, off.blueF() + (on.blueF()-off.blueF())*t))
        painter.drawRoundedRect(QRectF(0, 0, 30, 18), 9, 9)
        painter.setBrush(QColor("#f4f4f6" if self.isEnabled() else "#66666c"))
        painter.drawEllipse(QRectF(2 + 12*t, 2, 14, 14))


class ComboBox(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#aaaab2"), 1.3))
        x, y = self.width() - 12, self.height() / 2
        painter.drawLine(QPointF(x-3, y-1), QPointF(x, y+2))
        painter.drawLine(QPointF(x, y+2), QPointF(x+3, y-1))


class LiveCaption(QLabel):
    """Floating pill next to the indicator with the latest dictated words."""
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setWordWrap(True)
        self.setFixedWidth(440)
        self.setContentsMargins(14, 9, 14, 9)
        self.setStyleSheet("color: #e8e8e9; font-size: 13px;")

    def paintEvent(self, event):
        # Translucent top-level windows ignore stylesheet backgrounds: draw the pill.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#32323b"), 1))
        painter.setBrush(QColor(16, 16, 20, 235))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 10, 10)
        painter.end()
        super().paintEvent(event)

    def show_text(self, text, anchor):
        if len(text) > 110:  # keep the tail: two lines at most
            text = "…" + text[-110:].split(" ", 1)[-1]
        self.setText(text)
        self.adjustSize()
        x = anchor.center().x() - self.width() // 2
        y = anchor.top() - self.height() - 8
        screen = QApplication.screenAt(anchor.center())
        if screen and y < screen.availableGeometry().top():
            y = anchor.bottom() + 8  # indicator near the top: show below it
        self.move(x, y)
        self.show()


class RecordingIndicator(QWidget):
    clicked = Signal()
    position_changed = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(76, 38)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Dictation indicator")
        self._state = "idle"
        self.level = 0
        self.shown_level = 0
        self.frame = 0
        self.draggable = False
        self.drag_start = None
        self.moved = False
        self.animation = QTimer(self)
        self.animation.setTimerType(Qt.TimerType.PreciseTimer)
        self.animation.timeout.connect(self.animate)

    @property
    def state(self):
        return self._state

    @state.setter
    def state(self, value):
        self._state = value
        # ~60 fps only while active; idle draws a static wave.
        if value == "idle":
            self.animation.stop()
        elif not self.animation.isActive():
            self.animation.start(16)

    def animate(self):
        self.frame += 1
        self.shown_level += (self.level - self.shown_level) * 0.2
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(3, 3, 70, 28)
        painter.setPen(QPen(QColor("#32323b"), 0.7))
        painter.setBrush(QColor("#101014"))
        painter.drawRoundedRect(bounds, 8, 8)
        gradient = QLinearGradient(16, 0, 60, 0)
        for index, color in enumerate(BRAND):
            gradient.setColorAt(index / 3, QColor(color))
        if self.state in ("connecting", "stopping"):
            painter.setPen(Qt.PenStyle.NoPen)
            for index in range(3):
                color = QColor(CYAN)
                color.setAlphaF(0.3 + 0.7 * (0.5 + 0.5 * math.sin(self.frame / 12 - index)))
                painter.setBrush(color)
                painter.drawEllipse(QRectF(27 + index*9, 14, 4, 4))
            return
        path = QPainterPath()
        if self.state == "idle":
            points = [(0,.5),(.12,.5),(.20,.3),(.28,.65),(.36,.15),(.44,.8),
                      (.52,.08),(.60,.88),(.68,.20),(.76,.62),(.84,.38),(.92,.5),(1,.5)]
            points = [(x, (y-.5)*16) for x, y in points]
        else:
            # A travelling wave, tapered at both ends, that follows the voice level.
            amplitude = 8 * max(0.15, min(1.2, self.shown_level*4))
            phase = self.frame * 0.18
            points = [(x, amplitude * math.sin(math.pi*x)**1.5 *
                       (0.6*math.sin(13.8*x - phase) + 0.4*math.sin(23.2*x + phase*1.3)))
                      for x in (i/40 for i in range(41))]
        for index, (x, y) in enumerate(points):
            point = QPointF(16 + x*44, 17 + y)
            path.moveTo(point) if index == 0 else path.lineTo(point)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(gradient, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = event.globalPosition().toPoint() - self.pos()
            self.moved = False

    def mouseMoveEvent(self, event):
        if self.draggable and self.drag_start is not None:
            point = event.globalPosition().toPoint() - self.drag_start
            if (point - self.pos()).manhattanLength() > 2:
                self.moved = True
                self.move(point)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag_start is not None:
            self.position_changed.emit() if self.moved else self.clicked.emit()
            self.drag_start = None
