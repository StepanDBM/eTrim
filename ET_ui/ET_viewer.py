# ET_ui/ET_viewer.py

try:
    from PySide2 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide6 import QtCore, QtGui, QtWidgets

from ET_ui.drawables.ET_uv_drawer import EUVDrawer
from ET_ui.drawables.ET_box_drawer import EBoxDrawer


class ETrimViewer(QtWidgets.QWidget):
    """
    Custom UV-style viewer.

    Responsibilities:
    - QWidget canvas
    - UV/screen coordinate conversion
    - pan / zoom
    - draw grid and 0-1 tile
    - route mouse events to box/UV drawers
    """

    activeBoxChanged = QtCore.Signal(object)
    boxesChanged = QtCore.Signal()

    def __init__(self, model, parent=None):
        super(ETrimViewer, self).__init__(parent)

        self.model = model

        self.setMinimumSize(300, 300)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        self.zoom = 420.0
        self.pan = QtCore.QPointF(80.0, 430.0)

        self.is_panning = False
        self.last_mouse_pos = QtCore.QPoint()

        # Outside 0-1 tile.
        self.background_color = QtGui.QColor(82, 82, 86)

        # Inside 0-1 tile.
        self.tile_color = QtGui.QColor(35, 35, 38)

        # Grid only inside 0-1 tile.
        self.grid_color = QtGui.QColor(65, 65, 70)
        self.major_grid_color = QtGui.QColor(110, 110, 118)
        self.tile_border_color = QtGui.QColor(180, 180, 185)

        self.uv_cache = None

        self.uv_drawer = EUVDrawer(self)
        self.box_drawer = EBoxDrawer(self)

    # -----------------------------------------------------
    # Data
    # -----------------------------------------------------

    def set_uv_cache(self, uv_cache):
        self.uv_cache = uv_cache
        self.update()
    def get_active_drawer(self):
        """
        Return the drawer that currently owns active selection.

        Priority:
        - active box
        - active UV shell

        Only one drawer should receive hover/press/drag behavior
        while something is selected.
        """

        if self.box_drawer:
            if self.model.active_box_id:
                return self.box_drawer

        if self.uv_drawer:
            active_shell = getattr(
                self.uv_drawer,
                "active_shell",
                None
            )

            if active_shell:
                return self.uv_drawer

        return None


    def has_active_drawable(self):
        return self.get_active_drawer() is not None
    # -----------------------------------------------------
    # Coordinate conversion
    # -----------------------------------------------------

    def uv_to_screen(self, u, v):
        x = self.pan.x() + (u * self.zoom)
        y = self.pan.y() - (v * self.zoom)

        return QtCore.QPointF(x, y)

    def screen_to_uv(self, point):
        u = (point.x() - self.pan.x()) / self.zoom
        v = -((point.y() - self.pan.y()) / self.zoom)

        return u, v

    def box_to_screen_rect(self, box):
        p_min = self.uv_to_screen(box.u_min, box.v_min)
        p_max = self.uv_to_screen(box.u_max, box.v_max)

        left = min(p_min.x(), p_max.x())
        right = max(p_min.x(), p_max.x())
        top = min(p_min.y(), p_max.y())
        bottom = max(p_min.y(), p_max.y())

        return QtCore.QRectF(
            left,
            top,
            right - left,
            bottom - top
        )
    
    def get_tile_rect(self):
        p0 = self.uv_to_screen(0.0, 0.0)
        p1 = self.uv_to_screen(1.0, 1.0)

        return QtCore.QRectF(
            min(p0.x(), p1.x()),
            min(p0.y(), p1.y()),
            abs(p1.x() - p0.x()),
            abs(p1.y() - p0.y())
        )
    
    # -----------------------------------------------------
    # View controls
    # -----------------------------------------------------

    def frame_01(self):
        margin = 50.0

        available_w = max(float(self.width()) - margin * 2.0, 100.0)
        available_h = max(float(self.height()) - margin * 2.0, 100.0)

        self.zoom = min(available_w, available_h)

        x = (float(self.width()) - self.zoom) * 0.5
        y = (float(self.height()) + self.zoom) * 0.5

        self.pan = QtCore.QPointF(x, y)

        self.update()

    def deselect_drawables(self):
        """
        Called when clicking empty space.

        Clears active/hover state from all drawable systems.
        """

        if self.box_drawer:
            self.box_drawer.deselect()

        if self.uv_drawer and hasattr(self.uv_drawer, "deselect"):
            self.uv_drawer.deselect()

        self.setCursor(QtCore.Qt.ArrowCursor)
        self.update()

    # -----------------------------------------------------
    # Events
    # -----------------------------------------------------

    def resizeEvent(self, event):
        super(ETrimViewer, self).resizeEvent(event)

        if self.zoom == 420.0 and self.pan == QtCore.QPointF(80.0, 430.0):
            self.frame_01()

    def mouseMoveEvent(self, event):
        pos = event.pos()

        if self.is_panning:
            delta = pos - self.last_mouse_pos
            self.pan += QtCore.QPointF(delta.x(), delta.y())
            self.last_mouse_pos = pos
            self.update()
            return

        active_drawer = self.get_active_drawer()

        if active_drawer:
            if active_drawer.mouse_move_event(event):
                return

            # Important:
            # If something is selected, do not allow other drawers to hover.
            return

        if self.box_drawer.mouse_move_event(event):
            return

        if hasattr(self.uv_drawer, "mouse_move_event"):
            if self.uv_drawer.mouse_move_event(event):
                return

        super(ETrimViewer, self).mouseMoveEvent(event)

    def mousePressEvent(self, event):
        pos = event.pos()

        if event.button() == QtCore.Qt.MiddleButton:
            self.is_panning = True
            self.last_mouse_pos = pos
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            return

        # Press is allowed to change selection no matter what was selected before.
        if self.box_drawer.mouse_press_event(event):
            # Box won this press, so UV selection must stop being active.
            if self.uv_drawer and hasattr(self.uv_drawer, "deselect"):
                self.uv_drawer.deselect()
            return

        if hasattr(self.uv_drawer, "mouse_press_event"):
            if self.uv_drawer.mouse_press_event(event):
                # UV won this press, so box selection must stop being active.
                if self.box_drawer and hasattr(self.box_drawer, "deselect"):
                    self.box_drawer.deselect()

                # Restore UV drag cursor because box deselect may set ArrowCursor.
                self.setCursor(QtCore.Qt.SizeAllCursor)

                return

        if event.button() == QtCore.Qt.LeftButton:
            self.deselect_drawables()
            return

        super(ETrimViewer, self).mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MiddleButton:
            self.is_panning = False
            self.setCursor(QtCore.Qt.ArrowCursor)
            return

        active_drawer = self.get_active_drawer()

        if active_drawer:
            if active_drawer.mouse_release_event(event):
                return

            # Do not route release to other drawers while something is active.
            return

        if self.box_drawer.mouse_release_event(event):
            return

        if hasattr(self.uv_drawer, "mouse_release_event"):
            if self.uv_drawer.mouse_release_event(event):
                return

        super(ETrimViewer, self).mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self.box_drawer.leave_event(event)

        if hasattr(self.uv_drawer, "leave_event"):
            self.uv_drawer.leave_event(event)

        super(ETrimViewer, self).leaveEvent(event)

    def wheelEvent(self, event):
        old_pos = event.pos()
        old_u, old_v = self.screen_to_uv(old_pos)

        delta = event.angleDelta().y()

        if delta > 0:
            factor = 1.12
        else:
            factor = 1.0 / 1.12

        self.zoom *= factor
        self.zoom = max(50.0, min(self.zoom, 8000.0))

        new_screen = self.uv_to_screen(old_u, old_v)
        offset = old_pos - new_screen.toPoint()

        self.pan += QtCore.QPointF(offset.x(), offset.y())

        self.update()

    # -----------------------------------------------------
    # Paint
    # -----------------------------------------------------

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        painter.fillRect(self.rect(), self.background_color)

        self.draw_tile(painter)
        self.draw_grid(painter)
        self.draw_tile_border(painter)

        if self.box_drawer:
            self.box_drawer.draw(painter)

        if self.uv_drawer:
            self.uv_drawer.draw_cache(
                painter,
                self.uv_cache
            )

        self.draw_hud(painter)

        painter.end()

    def draw_tile(self, painter):
        rect = self.get_tile_rect()

        painter.setBrush(QtGui.QBrush(self.tile_color))
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRect(rect)

    def draw_tile_border(self, painter):
        rect = self.get_tile_rect()

        painter.setBrush(QtCore.Qt.NoBrush)
        painter.setPen(QtGui.QPen(self.tile_border_color, 2))
        painter.drawRect(rect)

    def draw_grid(self, painter):
        """
        Draw grid only inside the 0-1 UV tile.
        """

        rect = self.get_tile_rect()

        painter.save()
        painter.setClipRect(rect)

        step = 0.1
        min_uv = 0.0
        max_uv = 1.0

        i = int(min_uv / step)

        while i <= int(max_uv / step):
            value = round(i * step, 5)

            if abs(value - round(value)) < 0.0001:
                painter.setPen(QtGui.QPen(self.major_grid_color, 1))
            else:
                painter.setPen(QtGui.QPen(self.grid_color, 1))

            p_a = self.uv_to_screen(value, min_uv)
            p_b = self.uv_to_screen(value, max_uv)
            painter.drawLine(p_a, p_b)

            p_c = self.uv_to_screen(min_uv, value)
            p_d = self.uv_to_screen(max_uv, value)
            painter.drawLine(p_c, p_d)

            i += 1

        painter.restore()

    def draw_hud(self, painter):
        painter.setPen(QtGui.QPen(QtGui.QColor(180, 180, 185), 1))

        text = "MMB pan | Wheel zoom | Box drawer handles box edit | UV drawer handles UV display"

        painter.drawText(
            12,
            self.height() - 12,
            text
        )