from typing import Any, Callable, Dict, List, Optional

from PyQt5.QtCore import (
    QEasingCurve,
    QObject,
    QParallelAnimationGroup,
    QPoint,
    QPropertyAnimation,
    QSequentialAnimationGroup,
    Qt,
    QTimer,
)
from PyQt5.QtWidgets import QWidget


_EASING_MAP: Dict[str, QEasingCurve.Type] = {
    "linear": QEasingCurve.Linear,
    "out": QEasingCurve.OutCubic,
    "in_out": QEasingCurve.InOutCubic,
    "spring": QEasingCurve.OutBack,
    "bounce": QEasingCurve.OutBounce,
    "smooth": QEasingCurve.InOutSine,
    "decelerate": QEasingCurve.OutQuad,
    "accelerate": QEasingCurve.InQuad,
    "elastic": QEasingCurve.OutElastic,
    "in_quad": QEasingCurve.InQuad,
    "out_quad": QEasingCurve.OutQuad,
    "in_out_quad": QEasingCurve.InOutQuad,
    "in_cubic": QEasingCurve.InCubic,
    "out_cubic": QEasingCurve.OutCubic,
    "in_out_cubic": QEasingCurve.InOutCubic,
    "in_quart": QEasingCurve.InQuart,
    "out_quart": QEasingCurve.OutQuart,
    "in_out_quart": QEasingCurve.InOutQuart,
    "in_quint": QEasingCurve.InQuint,
    "out_quint": QEasingCurve.OutQuint,
    "in_out_quint": QEasingCurve.InOutQuint,
    "in_sine": QEasingCurve.InSine,
    "out_sine": QEasingCurve.OutSine,
    "in_out_sine": QEasingCurve.InOutSine,
    "in_expo": QEasingCurve.InExpo,
    "out_expo": QEasingCurve.OutExpo,
    "in_out_expo": QEasingCurve.InOutExpo,
    "in_circ": QEasingCurve.InCirc,
    "out_circ": QEasingCurve.OutCirc,
    "in_out_circ": QEasingCurve.InOutCirc,
    "in_elastic": QEasingCurve.InElastic,
    "out_elastic": QEasingCurve.OutElastic,
    "in_out_elastic": QEasingCurve.InOutElastic,
    "in_back": QEasingCurve.InBack,
    "out_back": QEasingCurve.OutBack,
    "in_out_back": QEasingCurve.InOutBack,
    "in_bounce": QEasingCurve.InBounce,
    "out_bounce": QEasingCurve.OutBounce,
    "in_out_bounce": QEasingCurve.InOutBounce,
}

EASING_NAMES: List[str] = sorted(_EASING_MAP.keys())


def _easing(name: str) -> QEasingCurve:
    curve_type = _EASING_MAP.get(name, QEasingCurve.OutCubic)
    return QEasingCurve(curve_type)


def easing_names() -> List[str]:
    return EASING_NAMES


def fade_in(
    widget: QWidget, duration: int = 200, on_finish: Optional[Callable] = None
) -> QPropertyAnimation:
    widget.setGraphicsEffect(None)
    anim = QPropertyAnimation(widget, b"windowOpacity")
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(_easing("out"))
    if on_finish:
        anim.finished.connect(on_finish)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


def fade_out(
    widget: QWidget, duration: int = 200, on_finish: Optional[Callable] = None
) -> QPropertyAnimation:
    anim = QPropertyAnimation(widget, b"windowOpacity")
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setEndValue(0.0)
    anim.setEasingCurve(_easing("in_out"))
    if on_finish:
        anim.finished.connect(on_finish)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


def scale_in(
    widget: QWidget, duration: int = 250, on_finish: Optional[Callable] = None
) -> QParallelAnimationGroup:
    group = QParallelAnimationGroup()
    for prop, s, e in [("windowOpacity", 0.0, 1.0)]:
        anim = QPropertyAnimation(widget, prop.encode())
        anim.setDuration(duration)
        anim.setStartValue(s)
        anim.setEndValue(e)
        anim.setEasingCurve(_easing("spring"))
        group.addAnimation(anim)
    if on_finish:
        group.finished.connect(on_finish)
    group.start(QPropertyAnimation.DeleteWhenStopped)
    return group


def slide_in(
    widget: QWidget,
    direction: str = "up",
    distance: int = 20,
    duration: int = 300,
    on_finish: Optional[Callable] = None,
) -> QPropertyAnimation:
    start_pos = widget.pos()
    offset = {
        "up": QPoint(0, distance),
        "down": QPoint(0, -distance),
        "left": QPoint(distance, 0),
        "right": QPoint(-distance, 0),
    }
    delta = offset.get(direction, QPoint(0, distance))
    anim = QPropertyAnimation(widget, b"pos")
    anim.setDuration(duration)
    anim.setStartValue(start_pos + delta)
    anim.setEndValue(start_pos)
    anim.setEasingCurve(_easing("spring"))
    if on_finish:
        anim.finished.connect(on_finish)
    anim.start(QPropertyAnimation.DeleteWhenStopped)
    return anim


def pulse(
    widget: QWidget, property_name: bytes = b"windowOpacity", duration: int = 1500
) -> QPropertyAnimation:
    anim = QPropertyAnimation(widget, property_name)
    anim.setDuration(duration)
    anim.setStartValue(1.0)
    anim.setKeyValueAt(0.5, 0.4)
    anim.setEndValue(1.0)
    anim.setLoopCount(-1)
    anim.setEasingCurve(_easing("in_out"))
    anim.start()
    return anim


def shake(widget: QWidget, duration: int = 300) -> QSequentialAnimationGroup:
    group = QSequentialAnimationGroup()
    orig = widget.pos()
    for _ in range(3):
        a = QPropertyAnimation(widget, b"pos")
        a.setDuration(50)
        a.setStartValue(orig + QPoint(8, 0))
        a.setEndValue(orig)
        a.setEasingCurve(_easing("linear"))
        group.addAnimation(a)
        a2 = QPropertyAnimation(widget, b"pos")
        a2.setDuration(50)
        a2.setStartValue(orig + QPoint(-8, 0))
        a2.setEndValue(orig)
        a2.setEasingCurve(_easing("linear"))
        group.addAnimation(a2)
    group.start(QPropertyAnimation.DeleteWhenStopped)
    return group


def delayed(delay_ms: int, callback: Callable) -> QTimer:
    t = QTimer()
    t.setSingleShot(True)
    t.timeout.connect(callback)
    t.start(delay_ms)
    return t
