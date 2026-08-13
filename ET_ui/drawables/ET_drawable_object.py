# ET_ui/ET_drawable_object.py

try:
    from PySide2 import QtCore, QtWidgets
except ImportError:
    from PySide6 import QtCore, QtWidgets

from ET_ui import ET_style


class EDrawableObjectController(object):
    """
    Shared base controller for drawable/interactable UV-space objects.

    Intended users:
    - EBoxDrawer
    - EUVDrawer

    Responsibilities:
    - shared hover / active object references
    - shared drag bookkeeping
    - shared cursor helpers
    - shared UV-space helper methods

    Subclasses are still responsible for:
    - drawing
    - hit testing specific geometry
    - resize behavior
    - object-specific movement rules
    """

    def __init__(self, viewer, drawable_kind="drawable"):
        self.viewer = viewer
        self.drawable_kind = drawable_kind

        self.hover_object = None
        self.active_object = None

        self.is_dragging = False
        self.drag_object = None
        self.drag_start_uv = None
        self.drag_start_data = None

    # -----------------------------------------------------
    # Viewer helpers
    # -----------------------------------------------------

    def screen_to_uv(self, pos):
        return self.viewer.screen_to_uv(pos)

    def uv_to_screen(self, u, v):
        return self.viewer.uv_to_screen(u, v)

    def request_update(self):
        self.viewer.update()

    def set_arrow_cursor(self):
        self.viewer.setCursor(QtCore.Qt.ArrowCursor)

    def set_move_cursor(self):
        self.viewer.setCursor(QtCore.Qt.SizeAllCursor)

    # -----------------------------------------------------
    # Hover / active
    # -----------------------------------------------------

    def set_hover_object(self, obj):
        changed = obj != self.hover_object
        self.hover_object = obj

        if changed:
            self.request_update()

        return changed

    def clear_hover_object(self):
        return self.set_hover_object(None)

    def set_active_object(self, obj):
        changed = obj != self.active_object
        self.active_object = obj

        if changed:
            self.request_update()

        return changed

    def clear_active_object(self):
        return self.set_active_object(None)

    # -----------------------------------------------------
    # Generic drag bookkeeping
    # -----------------------------------------------------

    def clamp_uv_delta_to_tile(self, u_min, v_min, u_max, v_max, du, dv):
        """
        Clamp a movement delta so a UV-space rectangle stays inside 0-1.

        This preserves the rectangle size and only limits movement.
        """

        width = u_max - u_min
        height = v_max - v_min

        # If the object is larger than the tile, it cannot meaningfully be clamped.
        # Keep the delta at zero for now.
        if width > 1.0 or height > 1.0:
            return 0.0, 0.0

        if u_min + du < 0.0:
            du = -u_min

        if u_max + du > 1.0:
            du = 1.0 - u_max

        if v_min + dv < 0.0:
            dv = -v_min

        if v_max + dv > 1.0:
            dv = 1.0 - v_max

        return du, dv

    def begin_drag_object(self, obj, pos, start_data=None):
        self.is_dragging = True
        self.drag_object = obj
        self.drag_start_uv = self.screen_to_uv(pos)
        self.drag_start_data = start_data
        self.set_active_object(obj)
        self.set_hover_object(obj)
        self.set_move_cursor()

    def get_drag_delta_uv(self, pos):
        if not self.is_dragging:
            return 0.0, 0.0

        if self.drag_start_uv is None:
            return 0.0, 0.0

        current_u, current_v = self.screen_to_uv(pos)
        start_u, start_v = self.drag_start_uv

        return current_u - start_u, current_v - start_v

    def end_drag_object(self):
        self.is_dragging = False
        self.drag_object = None
        self.drag_start_uv = None
        self.drag_start_data = None

    # -----------------------------------------------------
    # UV-space utility
    # -----------------------------------------------------

    def get_uv_bounds_from_positions(self, positions):
        """
        Return UV bounds from a dictionary:
            key -> (u, v)
        """

        if not positions:
            return 0.0, 0.0, 0.0, 0.0

        u_values = []
        v_values = []

        for u, v in positions.values():
            u_values.append(u)
            v_values.append(v)

        return (
            min(u_values),
            min(v_values),
            max(u_values),
            max(v_values)
        )

    def clamp_uv_rect_to_tile(self, u_min, v_min, u_max, v_max):
        u_min = max(0.0, min(1.0, u_min))
        u_max = max(0.0, min(1.0, u_max))
        v_min = max(0.0, min(1.0, v_min))
        v_max = max(0.0, min(1.0, v_max))

        if u_min > u_max:
            u_min, u_max = u_max, u_min

        if v_min > v_max:
            v_min, v_max = v_max, v_min

        return u_min, v_min, u_max, v_max

    def rects_overlap(self, a_u_min, a_v_min, a_u_max, a_v_max,
                      b_u_min, b_v_min, b_u_max, b_v_max):
        """
        True if two UV rectangles overlap with actual area.

        Touching edges is allowed.
        """

        if a_u_max <= b_u_min:
            return False

        if a_u_min >= b_u_max:
            return False

        if a_v_max <= b_v_min:
            return False

        if a_v_min >= b_v_max:
            return False

        return True

    def distance_sq_to_segment(self, p, a, b):
        """
        Screen-space distance squared from point p to segment a-b.
        Useful for UV shell edge hit testing.
        """

        px = float(p.x())
        py = float(p.y())

        ax = float(a.x())
        ay = float(a.y())

        bx = float(b.x())
        by = float(b.y())

        abx = bx - ax
        aby = by - ay

        apx = px - ax
        apy = py - ay

        denom = abx * abx + aby * aby

        if denom <= 0.000001:
            dx = px - ax
            dy = py - ay
            return dx * dx + dy * dy

        t = (apx * abx + apy * aby) / denom
        t = max(0.0, min(1.0, t))

        cx = ax + abx * t
        cy = ay + aby * t

        dx = px - cx
        dy = py - cy

        return dx * dx + dy * dy

    # -----------------------------------------------------
    # Context menu
    # -----------------------------------------------------

    def build_context_menu(self, drawable_object):
        """
        Shared base menu for all drawable objects.

        Subclasses can override this and call super().
        """

        menu = QtWidgets.QMenu(self.viewer)
        menu.setStyleSheet(ET_style.DIALOG_STYLE)

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(
            lambda: self.delete_drawable(drawable_object)
        )

        return menu


    def show_context_menu(self, event, drawable_object):
        menu = self.build_context_menu(drawable_object)

        if hasattr(menu, "exec_"):
            menu.exec_(event.globalPos())
        else:
            menu.exec(event.globalPos())


    def delete_drawable(self, drawable_object):
        """
        Base delete behavior.

        Subclasses should override when deletion has real meaning.
        """

        print(
            "[eTrim] Delete requested for {}: {}".format(
                self.drawable_kind,
                drawable_object
            )
        )

    # -----------------------------------------------------
    # Virtual-ish event API
    # -----------------------------------------------------

    def mouse_move_event(self, event):
        return False

    def mouse_press_event(self, event):
        return False

    def mouse_release_event(self, event):
        return False

    def leave_event(self, event):
        pass

    def draw(self, painter):
        pass

    def deselect(self):
        """
        Clear active/hover state for this drawable controller.

        Subclasses can override this to also clear their own local active state.
        """

        self.clear_active_object()
        self.clear_hover_object()
        self.set_arrow_cursor()
        self.request_update()