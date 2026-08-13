# ET_ui/ET_box_drawer.py

try:
    from PySide2 import QtCore, QtGui
except ImportError:
    from PySide6 import QtCore, QtGui

from ET_ui.ET_drawable_object import EDrawableObjectController


class EBoxDrawer(EDrawableObjectController):
    """
    Draws and controls TrimBox interaction.

    Responsibilities:
    - draw boxes
    - draw resize handles
    - hover boxes
    - drag boxes
    - resize boxes
    - prevent overlapping boxes
    - update box cursor states

    The actual box data lives in ET_box_model.
    """

    HANDLE_NONE = None
    HANDLE_LEFT = "left"
    HANDLE_RIGHT = "right"
    HANDLE_TOP = "top"
    HANDLE_BOTTOM = "bottom"
    HANDLE_TOP_LEFT = "top_left"
    HANDLE_TOP_RIGHT = "top_right"
    HANDLE_BOTTOM_LEFT = "bottom_left"
    HANDLE_BOTTOM_RIGHT = "bottom_right"
    HANDLE_BODY = "body"

    def __init__(self, viewer):
        super(EBoxDrawer, self).__init__(
            viewer, drawable_kind="box")

        self.hover_box_id = None
        self.hover_handle = self.HANDLE_NONE

        self.is_resizing = False
        self.is_dragging_box = False

        self.resize_box_id = None
        self.resize_handle = self.HANDLE_NONE
        self.resize_start_uv = None
        self.resize_start_box_values = None

        self.drag_box_id = None
        self.drag_start_box_values = None

        self.handle_pixel_size = 8
        self.min_box_size_uv = 0.01

    # -----------------------------------------------------
    # Model access
    # -----------------------------------------------------

    def model(self):
        return self.viewer.model

    # -----------------------------------------------------
    # Box utility
    # -----------------------------------------------------

    def clamp_box(self, box):
        box.u_min, box.v_min, box.u_max, box.v_max = self.clamp_uv_rect_to_tile(
            box.u_min,
            box.v_min,
            box.u_max,
            box.v_max
        )
        if box.u_max - box.u_min < self.min_box_size_uv:
            box.u_max = min(1.0, box.u_min + self.min_box_size_uv)

        if box.v_max - box.v_min < self.min_box_size_uv:
            box.v_max = min(1.0, box.v_min + self.min_box_size_uv)

    def iter_other_boxes(self, box_id):
        for other_id in self.model().box_order:
            if other_id == box_id:
                continue

            other = self.model().get_box(other_id)

            if other:
                yield other

    def move_box_clamped(self, box, u_min, v_min, u_max, v_max):
        box_id = box.id

        start_u_min = box.u_min
        start_v_min = box.v_min
        start_u_max = box.u_max
        start_v_max = box.v_max

        width = start_u_max - start_u_min
        height = start_v_max - start_v_min

        desired_du = u_min - start_u_min
        desired_dv = v_min - start_v_min

        if start_u_min + desired_du < 0.0:
            desired_du = -start_u_min

        if start_u_max + desired_du > 1.0:
            desired_du = 1.0 - start_u_max

        if start_v_min + desired_dv < 0.0:
            desired_dv = -start_v_min

        if start_v_max + desired_dv > 1.0:
            desired_dv = 1.0 - start_v_max

        final_du = desired_du

        candidate_u_min = start_u_min + final_du
        candidate_u_max = start_u_max + final_du

        for other in self.iter_other_boxes(box_id):
            vertical_overlap = not (
                start_v_max <= other.v_min or
                start_v_min >= other.v_max
            )

            if not vertical_overlap:
                continue

            if final_du > 0.0:
                if start_u_max <= other.u_min and candidate_u_max > other.u_min:
                    final_du = min(final_du, other.u_min - start_u_max)

            elif final_du < 0.0:
                if start_u_min >= other.u_max and candidate_u_min < other.u_max:
                    final_du = max(final_du, other.u_max - start_u_min)

        moved_u_min = start_u_min + final_du
        moved_u_max = start_u_max + final_du

        final_dv = desired_dv

        candidate_v_min = start_v_min + final_dv
        candidate_v_max = start_v_max + final_dv

        for other in self.iter_other_boxes(box_id):
            horizontal_overlap = not (
                moved_u_max <= other.u_min or
                moved_u_min >= other.u_max
            )

            if not horizontal_overlap:
                continue

            if final_dv > 0.0:
                if start_v_max <= other.v_min and candidate_v_max > other.v_min:
                    final_dv = min(final_dv, other.v_min - start_v_max)

            elif final_dv < 0.0:
                if start_v_min >= other.v_max and candidate_v_min < other.v_max:
                    final_dv = max(final_dv, other.v_max - start_v_min)

        box.u_min = start_u_min + final_du
        box.u_max = box.u_min + width

        box.v_min = start_v_min + final_dv
        box.v_max = box.v_min + height

    def clamp_resize_against_other_boxes(self, box, u_min, v_min, u_max, v_max, handle):
        box_id = box.id

        u_min = max(0.0, min(1.0, u_min))
        u_max = max(0.0, min(1.0, u_max))
        v_min = max(0.0, min(1.0, v_min))
        v_max = max(0.0, min(1.0, v_max))

        if u_min > u_max:
            u_min, u_max = u_max, u_min

        if v_min > v_max:
            v_min, v_max = v_max, v_min

        for other in self.iter_other_boxes(box_id):
            vertical_overlap = not (
                v_max <= other.v_min or
                v_min >= other.v_max
            )

            if vertical_overlap:
                if handle in (
                    self.HANDLE_RIGHT,
                    self.HANDLE_TOP_RIGHT,
                    self.HANDLE_BOTTOM_RIGHT
                ):
                    if box.u_max <= other.u_min and u_max > other.u_min:
                        u_max = other.u_min

                if handle in (
                    self.HANDLE_LEFT,
                    self.HANDLE_TOP_LEFT,
                    self.HANDLE_BOTTOM_LEFT
                ):
                    if box.u_min >= other.u_max and u_min < other.u_max:
                        u_min = other.u_max

            horizontal_overlap = not (
                u_max <= other.u_min or
                u_min >= other.u_max
            )

            if horizontal_overlap:
                if handle in (
                    self.HANDLE_TOP,
                    self.HANDLE_TOP_LEFT,
                    self.HANDLE_TOP_RIGHT
                ):
                    if box.v_max <= other.v_min and v_max > other.v_min:
                        v_max = other.v_min

                if handle in (
                    self.HANDLE_BOTTOM,
                    self.HANDLE_BOTTOM_LEFT,
                    self.HANDLE_BOTTOM_RIGHT
                ):
                    if box.v_min >= other.v_max and v_min < other.v_max:
                        v_min = other.v_max

        if u_max - u_min < self.min_box_size_uv:
            if handle in (
                self.HANDLE_LEFT,
                self.HANDLE_TOP_LEFT,
                self.HANDLE_BOTTOM_LEFT
            ):
                u_min = u_max - self.min_box_size_uv
            else:
                u_max = u_min + self.min_box_size_uv

        if v_max - v_min < self.min_box_size_uv:
            if handle in (
                self.HANDLE_BOTTOM,
                self.HANDLE_BOTTOM_LEFT,
                self.HANDLE_BOTTOM_RIGHT
            ):
                v_min = v_max - self.min_box_size_uv
            else:
                v_max = v_min + self.min_box_size_uv

        u_min = max(0.0, min(1.0, u_min))
        u_max = max(0.0, min(1.0, u_max))
        v_min = max(0.0, min(1.0, v_min))
        v_max = max(0.0, min(1.0, v_max))

        return u_min, v_min, u_max, v_max

    # -----------------------------------------------------
    # Hit testing
    # -----------------------------------------------------
    def hit_test_box_handle(self, pos):
        px = pos.x()
        py = pos.y()
        threshold = self.handle_pixel_size

        for box_id in reversed(self.model().box_order):
            box = self.model().get_box(box_id)

            if not box:
                continue

            rect = self.viewer.box_to_screen_rect(box)

            expanded = rect.adjusted(
                -threshold,
                -threshold,
                threshold,
                threshold
            )

            if not expanded.contains(pos):
                continue

            left_dist = abs(px - rect.left())
            right_dist = abs(px - rect.right())
            top_dist = abs(py - rect.top())
            bottom_dist = abs(py - rect.bottom())

            near_left = left_dist <= threshold
            near_right = right_dist <= threshold
            near_top = top_dist <= threshold
            near_bottom = bottom_dist <= threshold

            if near_left and near_top:
                return box_id, self.HANDLE_TOP_LEFT

            if near_right and near_top:
                return box_id, self.HANDLE_TOP_RIGHT

            if near_left and near_bottom:
                return box_id, self.HANDLE_BOTTOM_LEFT

            if near_right and near_bottom:
                return box_id, self.HANDLE_BOTTOM_RIGHT

            if near_left:
                return box_id, self.HANDLE_LEFT

            if near_right:
                return box_id, self.HANDLE_RIGHT

            if near_top:
                return box_id, self.HANDLE_TOP

            if near_bottom:
                return box_id, self.HANDLE_BOTTOM

            if rect.contains(pos):
                return box_id, self.HANDLE_BODY

        return None, self.HANDLE_NONE

    # -----------------------------------------------------
    # Cursor
    # -----------------------------------------------------

    def deselect(self):
        """
        Clear box selection and hover state.
        """

        self.hover_box_id = None
        self.hover_handle = self.HANDLE_NONE

        self.clear_hover_object()
        self.clear_active_object()

        self.model().active_box_id = None

        self.update_cursor_for_handle(self.HANDLE_NONE)
        self.viewer.boxesChanged.emit()
        self.viewer.update()

    def update_cursor_for_handle(self, handle):
        if self.viewer.is_panning:
            self.viewer.setCursor(QtCore.Qt.ClosedHandCursor)
            return

        if self.is_dragging_box:
            self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
            return

        if self.is_resizing:
            return

        if handle in (self.HANDLE_LEFT, self.HANDLE_RIGHT):
            self.viewer.setCursor(QtCore.Qt.SizeHorCursor)
            return

        if handle in (self.HANDLE_TOP, self.HANDLE_BOTTOM):
            self.viewer.setCursor(QtCore.Qt.SizeVerCursor)
            return

        if handle in (self.HANDLE_TOP_LEFT, self.HANDLE_BOTTOM_RIGHT):
            self.viewer.setCursor(QtCore.Qt.SizeFDiagCursor)
            return

        if handle in (self.HANDLE_TOP_RIGHT, self.HANDLE_BOTTOM_LEFT):
            self.viewer.setCursor(QtCore.Qt.SizeBDiagCursor)
            return

        if handle == self.HANDLE_BODY:
            self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
            return

        self.viewer.setCursor(QtCore.Qt.ArrowCursor)

    # -----------------------------------------------------
    # Drag logic
    # -----------------------------------------------------

    def begin_drag_box(self, box_id, pos):
        box = self.model().get_box(box_id)

        if not box:
            return

        self.is_dragging_box = True
        self.drag_box_id = box_id

        self.begin_drag_object(box_id, pos)

        self.drag_start_box_values = {
            "u_min": box.u_min,
            "v_min": box.v_min,
            "u_max": box.u_max,
            "v_max": box.v_max
        }

        self.model().set_active_box(box_id)
        self.viewer.activeBoxChanged.emit(box_id)
        self.viewer.setCursor(QtCore.Qt.SizeAllCursor)

    def update_drag_box(self, pos):
        if not self.is_dragging_box:
            return

        box = self.model().get_box(self.drag_box_id)

        if not box:
            return

        du, dv = self.get_drag_delta_uv(pos)
        start = self.drag_start_box_values

        u_min = start["u_min"] + du
        v_min = start["v_min"] + dv
        u_max = start["u_max"] + du
        v_max = start["v_max"] + dv

        self.move_box_clamped(
            box,
            u_min,
            v_min,
            u_max,
            v_max
        )

        self.viewer.boxesChanged.emit()
        self.viewer.update()

    def end_drag_box(self):
        if not self.is_dragging_box:
            return

        self.is_dragging_box = False
        self.drag_box_id = None
        self.drag_start_box_values = None

        self.end_drag_object()

        self.update_cursor_for_handle(self.hover_handle)
        self.viewer.boxesChanged.emit()
        self.viewer.update()

    # -----------------------------------------------------
    # Resize logic
    # -----------------------------------------------------

    def begin_resize(self, box_id, handle, pos):
        box = self.model().get_box(box_id)

        if not box:
            return

        self.is_resizing = True
        self.resize_box_id = box_id
        self.resize_handle = handle
        self.resize_start_uv = self.viewer.screen_to_uv(pos)

        self.resize_start_box_values = {
            "u_min": box.u_min,
            "v_min": box.v_min,
            "u_max": box.u_max,
            "v_max": box.v_max
        }

        self.model().set_active_box(box_id)
        self.viewer.activeBoxChanged.emit(box_id)

    def update_resize(self, pos):
        if not self.is_resizing:
            return

        box = self.model().get_box(self.resize_box_id)

        if not box:
            return

        current_u, current_v = self.viewer.screen_to_uv(pos)
        start_u, start_v = self.resize_start_uv

        du = current_u - start_u
        dv = current_v - start_v

        start = self.resize_start_box_values

        u_min = start["u_min"]
        v_min = start["v_min"]
        u_max = start["u_max"]
        v_max = start["v_max"]

        handle = self.resize_handle

        if handle in (
            self.HANDLE_LEFT,
            self.HANDLE_TOP_LEFT,
            self.HANDLE_BOTTOM_LEFT
        ):
            u_min = start["u_min"] + du

        if handle in (
            self.HANDLE_RIGHT,
            self.HANDLE_TOP_RIGHT,
            self.HANDLE_BOTTOM_RIGHT
        ):
            u_max = start["u_max"] + du

        if handle in (
            self.HANDLE_TOP,
            self.HANDLE_TOP_LEFT,
            self.HANDLE_TOP_RIGHT
        ):
            v_max = start["v_max"] + dv

        if handle in (
            self.HANDLE_BOTTOM,
            self.HANDLE_BOTTOM_LEFT,
            self.HANDLE_BOTTOM_RIGHT
        ):
            v_min = start["v_min"] + dv

        u_min, v_min, u_max, v_max = self.clamp_resize_against_other_boxes(
            box,
            u_min,
            v_min,
            u_max,
            v_max,
            handle
        )

        box.u_min = u_min
        box.v_min = v_min
        box.u_max = u_max
        box.v_max = v_max

        self.clamp_box(box)

        self.viewer.boxesChanged.emit()
        self.viewer.update()

    def end_resize(self):
        if not self.is_resizing:
            return

        self.is_resizing = False
        self.resize_box_id = None
        self.resize_handle = self.HANDLE_NONE
        self.resize_start_uv = None
        self.resize_start_box_values = None

        self.update_cursor_for_handle(self.hover_handle)
        self.viewer.boxesChanged.emit()
        self.viewer.update()

    # -----------------------------------------------------
    # Event routing
    # -----------------------------------------------------

    def mouse_move_event(self, event):
        pos = event.pos()

        if self.is_dragging_box:
            self.update_drag_box(pos)
            return True

        if self.is_resizing:
            self.update_resize(pos)
            return True

        box_id, handle = self.hit_test_box_handle(pos)

        changed = (
            box_id != self.hover_box_id or
            handle != self.hover_handle
        )

        self.hover_box_id = box_id
        self.hover_handle = handle
        self.set_hover_object(box_id)

        self.update_cursor_for_handle(handle)

        if changed:
            self.viewer.update()

        return bool(box_id)

    def mouse_press_event(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return False

        pos = event.pos()
        box_id, handle = self.hit_test_box_handle(pos)

        if not box_id:
            return False

        self.model().set_active_box(box_id)
        self.set_active_object(box_id)
        self.viewer.activeBoxChanged.emit(box_id)

        if handle == self.HANDLE_BODY:
            self.begin_drag_box(box_id, pos)
        else:
            self.begin_resize(box_id, handle, pos)

        self.viewer.update()
        return True

    def mouse_release_event(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return False

        if self.is_dragging_box:
            self.end_drag_box()
            return True

        if self.is_resizing:
            self.end_resize()
            return True

        return False

    def leave_event(self, event):
        if not self.is_resizing and not self.is_dragging_box:
            self.hover_box_id = None
            self.hover_handle = self.HANDLE_NONE
            self.clear_hover_object()
            self.update_cursor_for_handle(self.HANDLE_NONE)
            self.viewer.update()
    # -----------------------------------------------------
    # Drawing
    # -----------------------------------------------------

    def draw(self, painter):
        for box in self.model().iter_boxes_by_z():
            rect = self.viewer.box_to_screen_rect(box)

            is_active = box.id == self.model().active_box_id
            is_hovered = box.id == self.hover_box_id

            fill = QtGui.QColor(255, 204, 20, 35)
            outline = QtGui.QColor(255, 204, 20, 230)
            pen_width = 2

            if is_hovered:
                outline = QtGui.QColor(255, 255, 255, 255)
                pen_width = 3

            if is_active:
                outline = QtGui.QColor(255, 220, 60, 255)
                pen_width = 4

            painter.setBrush(QtGui.QBrush(fill))
            painter.setPen(QtGui.QPen(outline, pen_width))
            painter.drawRect(rect)

            self.draw_resize_handles(
                painter,
                rect,
                is_active,
                is_hovered
            )

            painter.setPen(QtGui.QPen(QtGui.QColor(245, 245, 245, 230), 1))
            painter.drawText(
                rect.adjusted(6, 6, -6, -6),
                QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft,
                box.name
            )

    def draw_resize_handles(self, painter, rect, is_active, is_hovered):
        if not is_active and not is_hovered:
            return

        size = 6.0
        half = size * 0.5

        points = [
            rect.topLeft(),
            rect.topRight(),
            rect.bottomLeft(),
            rect.bottomRight(),
            QtCore.QPointF(rect.center().x(), rect.top()),
            QtCore.QPointF(rect.center().x(), rect.bottom()),
            QtCore.QPointF(rect.left(), rect.center().y()),
            QtCore.QPointF(rect.right(), rect.center().y())
        ]

        painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 240, 120, 255)))
        painter.setPen(QtGui.QPen(QtGui.QColor(30, 30, 30, 255), 1))

        for point in points:
            handle_rect = QtCore.QRectF(
                point.x() - half,
                point.y() - half,
                size,
                size
            )

            painter.drawRect(handle_rect)