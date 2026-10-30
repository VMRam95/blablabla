"""The macOS visual language, drawn with Qt on Windows."""
import math

from PySide6.QtCore import QByteArray, QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient, QWheelEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from native import animations_enabled

BASE, SIDEBAR, CARD, INPUT = "#121214", "#171719", "#1c1c21", "#242429"
CYAN, GREEN, YELLOW, PINK = "#00d9f2", "#4df266", "#ffd91a", "#ff4d99"
BRAND = (CYAN, GREEN, YELLOW, PINK)

STYLE = """
QWidget { color: #e8e8e9; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow, QWidget#page, QScrollArea, QStackedWidget { background: #121214; }
QFrame#sidebar { background: #171719; border: none; }
QFrame#card { background: #1c1c21; border: 1px solid #303036; border-radius: 14px; }
QFrame#sessionPanel { background: #1c1c21; border: 1px solid #34343c; border-radius: 14px; }
QLabel { background: transparent; border: none; }
QLabel[role='title'] { font-size: 28px; font-weight: 700; color: #f6f6f8; }
QLabel[role='section'] { font-size: 15px; font-weight: 600; color: #ededf0; }
QLabel[role='row'] { font-size: 13px; font-weight: 500; color: #dedee3; }
QLabel[role='detail'] { font-size: 12px; color: #a3a3af; }
QLabel[role='stat'] { font-size: 24px; font-weight: 600; color: #ededf0; }
QLabel[role='keycap'] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #303036,stop:1 #242429); border: 1px solid #3b3b42;
 border-bottom: 2px solid #101013; border-radius: 6px; color: #ccccd0;
 font-size: 11px; font-weight: 600; padding: 4px 9px; }
QPushButton { background: #2b2b32; border: 1px solid #41414b; border-radius: 8px;
 padding: 7px 12px; font-size: 12px; font-weight: 500; color: #e2e2e8; min-height: 20px; }
QPushButton:hover { background: #3a3a40; border-color: #484850; }
QPushButton:pressed { background: #242429; }
QPushButton:disabled { color: #55555b; background: #232328; border-color: #2c2c32; }
QPushButton:focus, QComboBox:focus, QAbstractButton:focus { border: 1px solid #00d9f2; }
QPushButton[role='primary'] { background: #00d9f2; border-color: #00d9f2; color: #092328; font-weight: 700; min-height: 28px; }
QPushButton[role='primary']:hover { background: #58e8f7; border-color: #58e8f7; }
QPushButton[role='primary']:pressed { background: #00b8cf; }
QPushButton[role='primary']:disabled { background: #29363b; border-color: #39474d; color: #a3b7bc; }
QPushButton[role='stop'] { background: #ff4d99; border-color: #ff4d99; color: #260b18; font-weight: 700; min-height: 28px; }
QPushButton[role='stop']:hover { background: #ff81b7; }
QPushButton[role='copy'] { background: #17393f; border-color: #287783; color: #75eaf7; font-weight: 600; padding: 8px 14px; min-height: 24px; }
QPushButton[role='copy']:hover { background: #20515a; border-color: #00d9f2; color: #b0f6ff; }
QPushButton[role='copy']:pressed { background: #123038; }
QPushButton[role='copy'][copied='true'] { background: #1b3e28; border-color: #39804b; color: #85f497; }
QPushButton[role='copy']:disabled { background: #232328; border-color: #36363d; color: #85858f; }
QPushButton[role='text'] { background: transparent; border: 1px solid transparent; color: #a3a3af; padding: 3px; }
QPushButton[role='text']:hover { color: #d5d5db; }
QPushButton[role='nav'] { background: transparent; border: none; border-radius: 7px;
 text-align: left; padding: 0; min-height: 44px; }
QPushButton[role='nav']:hover { background: #222225; }
QPushButton[role='nav']:checked { background: #233238; border: 1px solid #31515b; }
QPushButton[role='nav']:focus, QPushButton[role='text']:focus { border: 1px solid #00d9f2; }
QLabel[role='badge'] { background: #36363b; color: #bfbfc4; border-radius: 7px;
 font-size: 10px; font-weight: 700; padding: 2px 6px; }
QLineEdit, QKeySequenceEdit { background: #242429; border: 1px solid #393942;
 border-radius: 9px; padding: 10px; color: #ededf2; selection-background-color: #32575d; }
QLineEdit:focus, QKeySequenceEdit:focus { border-color: #00d9f2; }
QComboBox { background: #303034; border: 1px solid #39393e; border-radius: 6px;
 padding: 7px 24px 7px 10px; color: #dedee5; font-size: 12px; min-height: 20px; }
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

# A quiet frame around the existing pages; their controls and layout stay intact.
STYLE += """
QMainWindow { background: #101014; }
QWidget#page, QScrollArea, QStackedWidget, QScrollArea > QWidget { background: transparent; }
QWidget#workspace { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #19191f,stop:1 #131317); border: 1px solid #2a2a33; border-radius: 18px; }
QFrame#sidebar { background: transparent; }
QFrame#card { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #202027,stop:1 #1b1b21); border: 1px solid #32323c; border-radius: 14px; }
QPushButton { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #33333c,stop:1 #282830); border-color: #41414c; border-radius: 9px; }
QPushButton[role='primary'] { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
 stop:0 #6ce9f6,stop:.45 #00d9f2,stop:1 #00b8d2); border-color: #7debf7; }
QPushButton[role='primary']:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
 stop:0 #6ce9f6,stop:.45 #00d9f2,stop:1 #00b8d2); border-color: #7debf7; }
QPushButton[role='stop'] { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
 stop:0 #ff91bf,stop:1 #ff4d99); border-color: #ff97c2; }
QPushButton[role='copy'] { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #20414a,stop:1 #172d34); border-color: #35616c; color: #97e9f3; }
QPushButton[role='copy']:hover { background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
 stop:0 #20414a,stop:1 #172d34); border-color: #35616c; color: #97e9f3; }
QPushButton[role='copy'][copied='true'] { background: #1b3e28; border-color: #39804b; color: #85f497; }
QPushButton[role='nav'] { background: transparent; border: 1px solid transparent; border-radius: 10px; }
QPushButton[role='nav']:hover { background: #212129; }
QPushButton[role='nav']:checked { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
 stop:0 #203239,stop:1 #1c262d); border-color: #33464e; border-left: 2px solid #00d9f2; }
QPushButton[role='nav']:focus, QPushButton[role='text']:focus { border: 1px solid #00d9f2; }
QLabel[role='badge'] { background: #2b2b34; color: #bdbdc9; }
QFrame#navigation { background: #1b1b23; border: 1px solid #30303b; border-radius: 12px; }
QPushButton[role='nav'] { min-height: 22px; padding: 7px 9px; border: 1px solid transparent; border-radius: 8px; }
QPushButton[role='nav']:checked { background: #32323f; border: 1px solid #4a4a59; border-bottom: 2px solid #00d9f2; }
QPushButton[role='preview'] { background: #353540; border: 1px solid #626273; color: #f2f2f7;
 min-height: 24px; padding: 8px 12px; border-radius: 9px; font-weight: 600; }
QPushButton[role='preview']:hover { background: #474754; border-color: #00d9f2; }
QPushButton#recordButton { border-radius: 22px; min-height: 28px; padding: 10px 16px; }
QScrollBar:vertical { width: 6px; margin: 12px 1px; }
QScrollBar::handle:vertical { background: #3b3b47; }
"""


# Windows 11 Mica: let the backdrop show through; cards become subtle layers.
MICA_STYLE = """
QMainWindow { background: transparent; }
"""


def motion_duration(milliseconds):
    return milliseconds if animations_enabled() else 0


class StudioBackdrop(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#101014"))
        light = QRadialGradient(QPointF(0, 80), 420)
        light.setColorAt(0, QColor(0, 217, 242, 12))
        light.setColorAt(1, QColor(0, 217, 242, 0))
        painter.fillRect(self.rect(), light)


class VoicePanel(QFrame):
    """The voice control has its own surface, with light tied to recording state."""
    def __init__(self):
        super().__init__()
        self.state = "idle"
        self.tint = 0.0
        self.transition = QVariantAnimation(self)
        self.transition.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.transition.valueChanged.connect(self.set_tint)

    def set_tint(self, value):
        self.tint = value
        self.update()

    def set_state(self, state):
        self.state = state
        self.transition.stop()
        target = float(state != "idle")
        duration = motion_duration(220)
        if not duration or not self.isVisible():
            self.set_tint(target)
            return
        self.transition.setDuration(duration)
        self.transition.setStartValue(self.tint)
        self.transition.setEndValue(target)
        self.transition.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(.5, .5, -.5, -.5)
        path = QPainterPath()
        path.addRoundedRect(bounds, 16, 16)
        painter.setClipPath(path)
        surface = QLinearGradient(0, 0, self.width(), self.height())
        surface.setColorAt(0, QColor("#252630"))
        surface.setColorAt(1, QColor("#1a1a21"))
        painter.fillPath(path, surface)
        glow = QRadialGradient(QPointF(25, 10), 290)
        tint = QColor(PINK if self.state == "listening" else CYAN)
        tint.setAlpha(int(10 + 14 * self.tint))
        glow.setColorAt(0, tint)
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        painter.fillPath(path, glow)
        edge = QLinearGradient(0, 0, self.width(), self.height())
        edge.setColorAt(0, QColor("#46616a"))
        edge.setColorAt(.4, QColor("#3a3a48"))
        edge.setColorAt(1, QColor("#30303b"))
        painter.setPen(QPen(edge, 1))
        painter.drawPath(path)


class MotionButton(QPushButton):
    """Native button semantics with an interruptible, short hover highlight."""
    def __init__(self, text=""):
        super().__init__(text)
        self.hover_amount = 0.0
        self.hover_animation = QVariantAnimation(self)
        self.hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hover_animation.valueChanged.connect(self.set_hover)

    def set_hover(self, value):
        self.hover_amount = value
        self.update()

    def animate_hover(self, target):
        self.hover_animation.stop()
        duration = motion_duration(140)
        if not duration:
            self.set_hover(target)
            return
        self.hover_animation.setDuration(duration)
        self.hover_animation.setStartValue(self.hover_amount)
        self.hover_animation.setEndValue(target)
        self.hover_animation.start()

    def enterEvent(self, event):
        self.animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.animate_hover(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.isEnabled() or not self.hover_amount:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(220, 244, 255, round(35 * self.hover_amount)), 1))
        painter.setBrush(QColor(220, 244, 255, round(5 * self.hover_amount)))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8, 8)


class SmoothScrollArea(QScrollArea):
    """Smooth discrete wheel steps, preserving direct touchpad scrolling."""
    def __init__(self):
        super().__init__()
        self.scroll_motion = QVariantAnimation(self)
        self.scroll_motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.scroll_motion.valueChanged.connect(lambda value: self.verticalScrollBar().setValue(round(value)))
        self.verticalScrollBar().sliderPressed.connect(self.scroll_motion.stop)
        self.verticalScrollBar().rangeChanged.connect(lambda *_: self.scroll_motion.stop())
        self.scroll_target = 0

    def wheelEvent(self, event):
        duration = motion_duration(180)
        if not duration or not event.pixelDelta().isNull() or not event.angleDelta().y():
            self.scroll_motion.stop()
            super().wheelEvent(event)
            return
        bar = self.verticalScrollBar()
        running = self.scroll_motion.state() == QVariantAnimation.State.Running
        step = event.angleDelta().y() / 120 * QApplication.wheelScrollLines() * 20
        # A reversal should turn immediately, rather than finish the old journey.
        continuing = running and (self.scroll_target - bar.value()) * -step > 0
        origin = self.scroll_target if continuing else bar.value()
        self.scroll_target = max(bar.minimum(), min(bar.maximum(), origin - step))
        self.scroll_motion.stop()
        self.scroll_motion.setDuration(duration)
        self.scroll_motion.setStartValue(float(bar.value()))
        self.scroll_motion.setEndValue(float(self.scroll_target))
        self.scroll_motion.start()
        event.accept()

    def keyPressEvent(self, event):
        self.scroll_motion.stop()
        super().keyPressEvent(event)

    def hideEvent(self, event):
        self.scroll_motion.stop()
        super().hideEvent(event)


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
        "check": '<path d="m5 12 4 4L19 6"/>',
        "stop": '<rect x="6" y="6" width="12" height="12" rx="2"/>',
        "play": '<path d="m8 5 11 7-11 7Z"/>',
        "compact": '<rect x="3" y="4" width="18" height="16" rx="2"/><rect x="12" y="11" width="6" height="6" rx="1"/>',
        "expand": '<path d="M8 3H3v5M16 3h5v5M21 16v5h-5M3 16v5h5"/>',
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
        self.setFixedSize(44, 32)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        if not self.isVisible() or not motion_duration(140):
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
        painter.translate(3, 5)
        painter.setPen(Qt.PenStyle.NoPen)
        off, on = QColor("#39393f"), QColor(GREEN)
        t = self.position
        painter.setBrush(QColor.fromRgbF(off.redF() + (on.redF()-off.redF())*t,
            off.greenF() + (on.greenF()-off.greenF())*t, off.blueF() + (on.blueF()-off.blueF())*t))
        painter.drawRoundedRect(QRectF(0, 0, 38, 22), 11, 11)
        painter.setBrush(QColor("#f4f4f6" if self.isEnabled() else "#66666c"))
        painter.drawEllipse(QRectF(3 + 16*t, 3, 16, 16))
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(CYAN), 1))
            painter.drawRoundedRect(QRectF(-2, -2, 42, 26), 13, 13)


class AudioMeter(QWidget):
    """Quiet when idle; a readable input meter while the microphone is active."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(56, 32)
        self.level = 0
        self.shown_level = 0
        self.smoothing = QVariantAnimation(self)
        self.smoothing.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.smoothing.valueChanged.connect(self.show_level)
        self.setAccessibleName("Microphone input level")

    def set_level(self, value):
        self.level = max(0, min(1, value))
        self.setAccessibleDescription(f"Input level {round(self.level * 100)} percent")
        self.smoothing.stop()
        duration = motion_duration(110)
        if not duration or not self.isVisible():
            self.show_level(self.level)
            return
        self.smoothing.setDuration(duration)
        self.smoothing.setStartValue(self.shown_level)
        self.smoothing.setEndValue(self.level)
        self.smoothing.start()

    def show_level(self, value):
        self.shown_level = value
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        glow = QRadialGradient(QPointF(28, 16), 29)
        glow.setColorAt(0, QColor(0, 217, 242, round(18 + 25 * self.shown_level)))
        glow.setColorAt(1, QColor(0, 217, 242, 0))
        painter.fillRect(self.rect(), glow)
        gradient = QLinearGradient(5, 0, 51, 0)
        for index, color in enumerate(BRAND):
            gradient.setColorAt(index/3, QColor(color))
        points = [(0,.5),(.12,.5),(.20,.3),(.28,.65),(.36,.15),(.44,.8),
                  (.52,.08),(.60,.88),(.68,.20),(.76,.62),(.84,.38),(.92,.5),(1,.5)]
        path = QPainterPath()
        amplitude = 19 + 13 * self.shown_level
        for index, (x, y) in enumerate(points):
            point = QPointF(5 + x*46, 16 + (y-.5)*amplitude)
            path.lineTo(point) if index else path.moveTo(point)
        painter.setPen(QPen(gradient, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)


class ComboBox(QComboBox):
    def wheelEvent(self, event):
        # Closed selectors never consume the page's wheel, even when focused.
        # The popup's own item view still scrolls normally when opened.
        if self.view().isVisible():
            super().wheelEvent(event)
            return
        parent = self.parentWidget()
        while parent is not None and not isinstance(parent, QScrollArea):
            parent = parent.parentWidget()
        if parent is None:
            event.ignore()
            return
        viewport = parent.viewport()
        position = viewport.mapFromGlobal(event.globalPosition().toPoint())
        forwarded = QWheelEvent(QPointF(position), event.globalPosition(), event.pixelDelta(),
            event.angleDelta(), event.buttons(), event.modifiers(), event.phase(), event.inverted())
        QApplication.sendEvent(viewport, forwarded)
        event.accept()

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


class CompactPanel(VoicePanel):
    toggle_requested = Signal()
    expand_requested = Signal()
    position_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("Blablabla compact")
        self.setStyleSheet(STYLE)
        self.setFixedSize(320, 112)
        self.drag_offset = None
        column = QVBoxLayout(self)
        column.setContentsMargins(12, 10, 12, 10)
        column.setSpacing(6)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.meter = AudioMeter()
        row.addWidget(self.meter)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("Blablabla", "section"))
        self.status = label("Ready", "detail")
        self.status.setMinimumWidth(0)
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        titles.addWidget(self.status)
        row.addLayout(titles, 1)
        self.record = MotionButton()
        self.record.setProperty("role", "primary")
        self.record.setFixedSize(42, 42)
        self.record.setStyleSheet("padding:0;min-height:40px;border-radius:20px;")
        self.record.setCursor(Qt.CursorShape.PointingHandCursor)
        self.record.clicked.connect(lambda checked=False: self.toggle_requested.emit())
        row.addWidget(self.record)
        self.expand = MotionButton()
        self.expand.setIcon(icon("expand", "#dedee8", 17))
        self.expand.setFixedSize(32, 36)
        self.expand.setStyleSheet("padding:0;min-height:30px;")
        self.expand.setToolTip("Expand Blablabla")
        self.expand.setAccessibleName("Expand Blablabla")
        self.expand.setCursor(Qt.CursorShape.PointingHandCursor)
        self.expand.clicked.connect(lambda checked=False: self.expand_requested.emit())
        row.addWidget(self.expand)
        column.addLayout(row)
        self.caption = label("", "detail")
        self.caption.setWordWrap(True)
        self.caption.setMinimumWidth(0)
        self.caption.setMaximumHeight(36)
        self.caption.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        column.addWidget(self.caption)

    def set_session(self, state, text, message, shortcut, elapsed, closing=False):
        if state != self.state:
            self.set_state(state)
        active = state in ("connecting", "listening")
        heading = {"idle": "Ready", "connecting": "Connecting…",
            "listening": "Listening", "stopping": "Finalizing…"}[state]
        if elapsed and state != "idle":
            heading += " · " + elapsed
        self.status.setText(heading)
        self.status.setToolTip(message)
        self.record.setProperty("role", "stop" if active else "primary")
        self.record.setIcon(icon("stop" if active else "mic", "#260b18" if active else "#092328", 17))
        self.record.setToolTip("Stop dictation" if active else "Start dictation")
        self.record.setAccessibleName(self.record.toolTip())
        self.record.setEnabled(state != "stopping" and not closing)
        self.record.style().unpolish(self.record)
        self.record.style().polish(self.record)
        tail = text if len(text) <= 100 else "…" + text[-100:].split(" ", 1)[-1]
        self.caption.setText(tail or (shortcut if message == "Ready to dictate" else message))
        self.caption.setToolTip(message + ("\n" + text if text else ""))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None:
            point = event.globalPosition().toPoint() - self.drag_offset
            screen = QApplication.screenAt(event.globalPosition().toPoint())
            if screen:
                bounds = screen.availableGeometry()
                point.setX(max(bounds.left(), min(point.x(), bounds.right() - self.width() + 1)))
                point.setY(max(bounds.top(), min(point.y(), bounds.bottom() - self.height() + 1)))
            self.move(point)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drag_offset is not None:
            self.drag_offset = None
            self.position_changed.emit()
        super().mouseReleaseEvent(event)


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
