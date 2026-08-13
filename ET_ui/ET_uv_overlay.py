# ET_ui/ET_uv_overlay.py

import __main__

try:
    from PySide2.QtCore import Qt, QRectF
    from PySide2.QtGui import QColor, QPainter, QPen, QBrush
    from PySide2.QtWidgets import QWidget
except ImportError:
    from PySide6.QtCore import Qt, QRectF
    from PySide6.QtGui import QColor, QPainter, QPen, QBrush
    from PySide6.QtWidgets import QWidget

from ET_core.ET_model import get_model
from ET_core import ET_uv_editor


class ETrimUVOverlay(QWidget):
    """
    Transparent overlay that sits above Maya's UV Editor.

    It does NOT own data.
    It draws from the ETrimModel source of truth.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.model = get_model()

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.setWindowFlags(Qt.Widget)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        self.draw_boxes(painter)

        painter.end()

    def uv_to_screen_rect(self, box):
        w = self.width()
        h = self.height()

        x = box.u_min * w
        y = (1.0 - box.v_max) * h

        rect_w = (box.u_max - box.u_min) * w
        rect_h = (box.v_max - box.v_min) * h

        return QRectF(
            x,
            y,
            rect_w,
            rect_h
        )

    def draw_boxes(self, painter):
        for box in self.model.iter_boxes():
            rect = self.uv_to_screen_rect(box)

            r, g, b, a = box.color

            fill = QColor(
                int(r * 255),
                int(g * 255),
                int(b * 255),
                50
            )

            outline = QColor(
                int(r * 255),
                int(g * 255),
                int(b * 255),
                220
            )

            if box.id == self.model.active_box_id:
                outline = QColor(255, 220, 80, 255)
                pen_width = 3
            else:
                pen_width = 2

            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(outline, pen_width))
            painter.drawRect(rect)

            painter.setPen(QPen(QColor(240, 240, 240, 230), 1))
            painter.drawText(
                rect.adjusted(5, 5, -5, -5),
                Qt.AlignTop | Qt.AlignLeft,
                box.name
            )


def get_overlay_store():
    overlay = getattr(
        __main__,
        "ETRIM_UV_OVERLAY",
        None
    )
    return overlay


def remove_overlay():
    overlay = get_overlay_store()

    if overlay:
        try:
            overlay.close()
            overlay.deleteLater()
        except Exception:
            pass

    __main__.ETRIM_UV_OVERLAY = None


def install_overlay():
    """
    Installs the transparent overlay over Maya's UV Editor.

    For now, this assumes UV coordinates map directly to the visible widget.
    Later we must account for pan/zoom inside the UV Editor.
    """

    ET_uv_editor.open_uv_editor()

    root = ET_uv_editor.get_uv_editor_widget()

    if not ET_uv_editor.is_qt_object_valid(root):
        print("[eTrim] Cannot install overlay. No valid UV editor root.")
        return None

    remove_overlay()

    overlay = ETrimUVOverlay(parent=root)

    overlay.setGeometry(root.rect())
    overlay.show()
    overlay.raise_()

    __main__.ETRIM_UV_OVERLAY = overlay

    print("[eTrim] Installed UV overlay:", overlay)

    return overlay


def refresh_overlay():
    overlay = get_overlay_store()

    if overlay:
        try:
            root = ET_uv_editor.get_uv_editor_widget()
            if ET_uv_editor.is_qt_object_valid(root):
                overlay.setGeometry(root.rect())

            overlay.update()
        except Exception:
            pass