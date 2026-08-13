# ET_ui/ET_viewer.py

try:
    from PySide2 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide6 import QtCore, QtGui, QtWidgets

from ET_ui.drawables.ET_uv_drawer import EUVDrawer
from ET_ui.drawables.ET_box_drawer import EBoxDrawer
from ET_ui import ET_style


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

        self.selected_drawables = []

        self.uv_selection_enabled = True
        self.box_selection_enabled = True

        self.create_box_width_percent = 20.0
        self.create_box_height_percent = 20.0

        self.backdrop_image_enabled = False
        self.backdrop_image_path = None
        self.backdrop_image = QtGui.QImage()
        self.backdrop_opacity = 1.0

        self.is_rect_selecting = False
        self.rect_select_start = None
        self.rect_select_current = None
        self.rect_select_additive = False

        self.is_pending_rect_select = False
        self.pending_rect_select_start = None
        self.pending_rect_select_additive = False
        self.rect_select_start_threshold = 4.0

        self.rect_select_fill = QtGui.QColor(255, 220, 80, 35)
        self.rect_select_outline = QtGui.QColor(255, 220, 80, 220)

    # -----------------------------------------------------
    # Data
    # -----------------------------------------------------

    def set_uv_selection_enabled(self, enabled):
        self.uv_selection_enabled = bool(enabled)

        if not self.uv_selection_enabled:
            if self.uv_drawer and hasattr(self.uv_drawer, "deselect"):
                self.uv_drawer.deselect()

            self.selected_drawables = [
                key for key in self.selected_drawables
                if not key or key[0] not in ("uv_shell", "uv_face")
            ]

        self.update()


    def set_box_selection_enabled(self, enabled):
        self.box_selection_enabled = bool(enabled)

        if not self.box_selection_enabled:
            if self.box_drawer and hasattr(self.box_drawer, "deselect"):
                self.box_drawer.deselect()

            self.selected_drawables = [
                key for key in self.selected_drawables
                if not key or key[0] != "box"
            ]

        self.update()

    def set_uv_cache(self, uv_cache):
        self.uv_cache = uv_cache
        self.update()

    def select_drawable(self, drawable_key, clear_previous=True, toggle=False):
        """
        Viewer-owned selection list.

        drawable_key examples:
            ("box", box_id)
            ("uv_shell", mesh_name, uv_set, shell_id)
            ("uv_face", mesh_name, uv_set, face_index)
        """

        if clear_previous:
            self.selected_drawables = []

        if toggle:
            if drawable_key in self.selected_drawables:
                self.selected_drawables.remove(drawable_key)
            else:
                self.selected_drawables.append(drawable_key)

            self.update()
            return

        if drawable_key not in self.selected_drawables:
            self.selected_drawables.append(drawable_key)

        self.update()

    def set_backdrop_image_path(self, image_path):
        """
        Set viewer backdrop image from file path.
        """

        if not image_path:
            self.backdrop_image_path = None
            self.backdrop_image = QtGui.QImage()
            self.backdrop_image_enabled = False
            self.update()
            return False

        image = QtGui.QImage(image_path)

        if image.isNull():
            print("[eTrim] Could not load backdrop image:", image_path)
            self.backdrop_image_path = None
            self.backdrop_image = QtGui.QImage()
            self.backdrop_image_enabled = False
            self.update()
            return False

        self.backdrop_image_path = image_path
        self.backdrop_image = image
        self.backdrop_image_enabled = True
        self.update()

        print("[eTrim] Backdrop image loaded:")
        print("    path:", image_path)

        return True


    def set_backdrop_enabled(self, enabled):
        self.backdrop_image_enabled = bool(enabled)
        self.update()


    def set_backdrop_opacity_percent(self, value):
        value = max(
            0.0,
            min(
                100.0,
                float(value)
            )
        )

        self.backdrop_opacity = value / 100.0
        self.update()
    # -----------------------------------------------------
    # Selection
    # -----------------------------------------------------
    def deselect_drawable_key(self, drawable_key):
        if drawable_key in self.selected_drawables:
            self.selected_drawables.remove(drawable_key)
            self.update()


    def is_drawable_selected(self, drawable_key):
        return drawable_key in self.selected_drawables


    def clear_drawable_selection(self):
        self.selected_drawables = []
        self.update()

    def is_shift_modifier(self, event):
        return bool(
            event.modifiers() & QtCore.Qt.ShiftModifier
        )

    def get_uv_selection_mode(self):
        if not self.uv_drawer:
            return "shell"

        return getattr(
            self.uv_drawer,
            "selection_mode",
            "shell"
        )


    def is_uv_selection_mode(self):
        if not self.uv_selection_enabled:
            return False

        return self.get_uv_selection_mode() in (
            "shell",
            "face"
        )

    def is_uv_face_selection_mode(self):
        if not self.uv_drawer:
            return False

        return getattr(
            self.uv_drawer,
            "selection_mode",
            "shell"
        ) == "face"


    def get_rect_select_rect(self):
        if not self.rect_select_start or not self.rect_select_current:
            return QtCore.QRectF()

        return QtCore.QRectF(
            self.rect_select_start,
            self.rect_select_current
        ).normalized()


    def begin_rect_selection(self, pos, additive=False):
        self.is_rect_selecting = True
        self.rect_select_start = QtCore.QPointF(pos)
        self.rect_select_current = QtCore.QPointF(pos)
        self.rect_select_additive = additive
        self.setCursor(QtCore.Qt.CrossCursor)
        self.update()


    def update_rect_selection(self, pos):
        if not self.is_rect_selecting:
            return

        self.rect_select_current = QtCore.QPointF(pos)
        self.update()


    def end_rect_selection(self):
        if not self.is_rect_selecting:
            return

        rect = self.get_rect_select_rect()

        self.is_rect_selecting = False
        self.rect_select_start = None
        self.rect_select_current = None

        if self.uv_drawer:
            mode = self.get_uv_selection_mode()

            if mode == "face" and hasattr(self.uv_drawer, "select_faces_in_rect"):
                self.uv_drawer.select_faces_in_rect(
                    rect,
                    additive=self.rect_select_additive
                )

            elif mode == "shell" and hasattr(self.uv_drawer, "select_shells_in_rect"):
                self.uv_drawer.select_shells_in_rect(
                    rect,
                    additive=self.rect_select_additive
                )

        self.rect_select_additive = False
        self.setCursor(QtCore.Qt.ArrowCursor)
        self.update()
    #pending rectselection andthreshold
    def begin_pending_rect_selection(self, pos, additive=False):
        """
        Store a possible rectangle selection.

        Actual rectangle selection only starts after the mouse moves
        more than rect_select_start_threshold pixels.
        """

        self.is_pending_rect_select = True
        self.pending_rect_select_start = QtCore.QPointF(pos)
        self.pending_rect_select_additive = additive


    def cancel_pending_rect_selection(self):
        self.is_pending_rect_select = False
        self.pending_rect_select_start = None
        self.pending_rect_select_additive = False


    def pending_rect_selection_distance_sq(self, pos):
        if not self.pending_rect_select_start:
            return 0.0

        dx = float(pos.x()) - float(self.pending_rect_select_start.x())
        dy = float(pos.y()) - float(self.pending_rect_select_start.y())

        return dx * dx + dy * dy


    def should_start_rect_selection(self, pos):
        threshold = float(self.rect_select_start_threshold)
        return self.pending_rect_selection_distance_sq(pos) >= threshold * threshold

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

            active_face = getattr(
                self.uv_drawer,
                "active_face",
                None
            )

            if active_shell or active_face:
                return self.uv_drawer

        return None


    def has_active_drawable(self):
        return self.get_active_drawer() is not None

    def get_selected_drawables_by_type(self, drawable_type):
        """
        Return selected drawable keys matching a type.

        drawable_type examples:
            "uv_shell"
            "uv_face"
            "box"
        """

        result = []

        for key in self.selected_drawables:
            if not key:
                continue

            if key[0] == drawable_type:
                result.append(key)

        return result
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
        self.clear_drawable_selection()
        if self.box_drawer:
            self.box_drawer.deselect()

        if self.uv_drawer and hasattr(self.uv_drawer, "deselect"):
            self.uv_drawer.deselect()

        self.setCursor(QtCore.Qt.ArrowCursor)
        self.update()

    def create_box_at_screen_pos(self, pos):
        """
        Ask the model to create a box centered on a viewer click.

        Viewer only converts screen position to UV coordinates.
        Model owns creation, collision, shrinking, and placement.
        """

        center_u, center_v = self.screen_to_uv(pos)

        width = self.create_box_width_percent / 100.0
        height = self.create_box_height_percent / 100.0

        box = self.model.create_box(
            width=width,
            height=height,
            preferred_u=center_u,
            preferred_v=center_v,
            centered=True
        )

        if not box:
            print("[eTrim] Could not create box from context menu.")
            return None

        self.model.set_active_box(box.id)

        self.select_drawable(
            self.box_drawer.drawable_key_for_box(box.id),
            clear_previous=True
        )

        self.activeBoxChanged.emit(box.id)
        self.boxesChanged.emit()
        self.update()

        print("[eTrim] Created box from empty context menu:")
        print("    id:", box.id)
        print("    name:", box.name)
        print("    uv:", box.u_min, box.v_min, box.u_max, box.v_max)

        return box

    def edit_create_box_settings(self):
        """
        Edit default create-box size as percentage of the 0-1 UV tile.
        """

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Create Box Settings")
        dialog.setStyleSheet(ET_style.DIALOG_STYLE)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        width_label = QtWidgets.QLabel("Width (% of 0-1 tile):")
        width_spin = QtWidgets.QDoubleSpinBox()
        width_spin.setRange(0.1, 100.0)
        width_spin.setDecimals(2)
        width_spin.setSingleStep(1.0)
        width_spin.setSuffix(" %")
        width_spin.setValue(self.create_box_width_percent)

        height_label = QtWidgets.QLabel("Height (% of 0-1 tile):")
        height_spin = QtWidgets.QDoubleSpinBox()
        height_spin.setRange(0.1, 100.0)
        height_spin.setDecimals(2)
        height_spin.setSingleStep(1.0)
        height_spin.setSuffix(" %")
        height_spin.setValue(self.create_box_height_percent)

        layout.addWidget(width_label)
        layout.addWidget(width_spin)
        layout.addWidget(height_label)
        layout.addWidget(height_spin)

        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()

        ok_btn = ET_style.create_primary_button("OK",
            minimum_width=72
        )

        cancel_btn = ET_style.create_action_button("Cancel",
            minimum_width=72
        )

        button_layout.addWidget(ok_btn)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec_() if hasattr(dialog, "exec_") else dialog.exec():
            self.create_box_width_percent = float(width_spin.value())
            self.create_box_height_percent = float(height_spin.value())

            print("[eTrim] Create box settings changed:")
            print("    width %:", self.create_box_width_percent)
            print("    height %:", self.create_box_height_percent)

    def build_empty_context_menu(self, pos):
        """
        Context menu for empty viewer space.
        """

        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(ET_style.DIALOG_STYLE)

        create_box_action = menu.addAction("Create Box")
        create_box_action.triggered.connect(
            lambda: self.create_box_at_screen_pos(pos)
        )

        settings_action = menu.addAction("Create Box Settings")
        settings_action.triggered.connect(
            self.edit_create_box_settings
        )

        return menu


    def show_empty_context_menu(self, event):
        menu = self.build_empty_context_menu(
            event.pos()
        )

        if hasattr(menu, "exec_"):
            menu.exec_(event.globalPos())
        else:
            menu.exec(event.globalPos())
    # -----------------------------------------------------
    # Events
    # -----------------------------------------------------

    def resizeEvent(self, event):
        super(ETrimViewer, self).resizeEvent(event)

        if self.zoom == 420.0 and self.pan == QtCore.QPointF(80.0, 430.0):
            self.frame_01()

    def is_box_handle_under_mouse(self, pos):
        """
        Return True only if the mouse is over a box resize handle/edge.

        Box handles should have priority over UVs.
        Box bodies should NOT have priority over UVs.
        """

        if not self.box_selection_enabled:
            return False

        if not self.box_drawer:
            return False

        box_id, handle = self.box_drawer.hit_test_box_handle(pos)

        if not box_id:
            return False

        return handle != self.box_drawer.HANDLE_BODY

    def mouseMoveEvent(self, event):
        pos = event.pos()

        if self.is_pending_rect_select:
            if self.should_start_rect_selection(pos):
                start_pos = self.pending_rect_select_start
                additive = self.pending_rect_select_additive

                self.cancel_pending_rect_selection()

                self.begin_rect_selection(
                    start_pos,
                    additive=additive
                )

                self.update_rect_selection(pos)
                return

            return

        if self.is_rect_selecting:
            self.update_rect_selection(pos)
            return

        if self.is_panning:
            delta = pos - self.last_mouse_pos
            self.pan += QtCore.QPointF(delta.x(), delta.y())
            self.last_mouse_pos = pos
            self.update()
            return

        # Ongoing box interaction always wins if boxes are enabled.
        if self.box_selection_enabled and self.box_drawer:
            if (
                getattr(self.box_drawer, "is_dragging_box", False) or
                getattr(self.box_drawer, "is_resizing", False)
            ):
                if self.box_drawer.mouse_move_event(event):
                    return

        # Ongoing UV interaction always wins if UVs are enabled.
        if self.uv_selection_enabled and self.uv_drawer:
            if (
                getattr(self.uv_drawer, "is_dragging_shell", False) or
                getattr(self.uv_drawer, "is_dragging_face", False)
            ):
                if self.uv_drawer.mouse_move_event(event):
                    return

        # Box handles get priority so boxes remain resizable.
        if self.box_selection_enabled:
            if self.is_box_handle_under_mouse(pos):
                if self.box_drawer.mouse_move_event(event):
                    return

        # UVs are the main event.
        if self.uv_selection_enabled:
            if hasattr(self.uv_drawer, "mouse_move_event"):
                if self.uv_drawer.mouse_move_event(event):
                    return

        # Box body hover only if no UV took the hover.
        if self.box_selection_enabled:
            if self.box_drawer.mouse_move_event(event):
                return

        super(ETrimViewer, self).mouseMoveEvent(event)

    def mousePressEvent(self, event):
        pos = event.pos()

        if event.button() == QtCore.Qt.MiddleButton:
            self.is_panning = True
            self.last_mouse_pos = pos
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            return

        # Box handles first, so resizing boxes is still possible.
        if self.box_selection_enabled:
            if self.is_box_handle_under_mouse(pos):
                if self.box_drawer.mouse_press_event(event):
                    if event.button() == QtCore.Qt.LeftButton:
                        if self.uv_drawer and hasattr(self.uv_drawer, "deselect"):
                            self.uv_drawer.deselect()
                    return

        # UVs / shells / faces are the main interaction target.
        if self.uv_selection_enabled:
            if hasattr(self.uv_drawer, "mouse_press_event"):
                if self.uv_drawer.mouse_press_event(event):
                    if event.button() == QtCore.Qt.LeftButton:
                        if self.box_drawer and hasattr(self.box_drawer, "deselect"):
                            self.box_drawer.deselect()

                    self.setCursor(QtCore.Qt.SizeAllCursor)
                    return

        # Box body only after UVs fail.
        if self.box_selection_enabled:
            if self.box_drawer.mouse_press_event(event):
                if event.button() == QtCore.Qt.LeftButton:
                    if self.uv_drawer and hasattr(self.uv_drawer, "deselect"):
                        self.uv_drawer.deselect()
                return

        # Empty click may clear selection.
        # Empty click-drag starts rectangle selection only after a small movement threshold.
        if event.button() == QtCore.Qt.LeftButton:
            if self.uv_selection_enabled and self.is_uv_selection_mode():
                self.begin_pending_rect_selection(
                    pos,
                    additive=self.is_shift_modifier(event)
                )
                return

            self.deselect_drawables()
            return
        
        if event.button() == QtCore.Qt.RightButton:
            self.show_empty_context_menu(event)
            return
        super(ETrimViewer, self).mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            if self.is_pending_rect_select:
                self.cancel_pending_rect_selection()
                self.deselect_drawables()
                return

        if event.button() == QtCore.Qt.LeftButton:
            if self.is_rect_selecting:
                self.end_rect_selection()
                return

        if event.button() == QtCore.Qt.MiddleButton:
            self.is_panning = False
            self.setCursor(QtCore.Qt.ArrowCursor)
            return

        # Finish box interactions first if one is active.
        if self.box_selection_enabled and self.box_drawer:
            if (
                getattr(self.box_drawer, "is_dragging_box", False) or
                getattr(self.box_drawer, "is_resizing", False)
            ):
                if self.box_drawer.mouse_release_event(event):
                    return

        # Finish UV interactions if one is active.
        if self.uv_selection_enabled and self.uv_drawer:
            if (
                getattr(self.uv_drawer, "is_dragging_shell", False) or
                getattr(self.uv_drawer, "is_dragging_face", False)
            ):
                if self.uv_drawer.mouse_release_event(event):
                    return

        if self.box_selection_enabled:
            if self.box_drawer.mouse_release_event(event):
                return

        if self.uv_selection_enabled:
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
        self.draw_backdrop_image(painter)
        self.draw_grid(painter)
        self.draw_tile_border(painter)

        if self.box_drawer:
            self.box_drawer.draw(painter)

        if self.uv_drawer:
            self.uv_drawer.draw_cache(
                painter,
                self.uv_cache
            )

        self.draw_rect_selection(painter)
        self.draw_hud(painter)

        painter.end()

    def draw_backdrop_image(self, painter):
        """
        Draw backdrop image inside the 0-1 UV tile.
        """

        if not self.backdrop_image_enabled:
            return

        if self.backdrop_image.isNull():
            return

        rect = self.get_tile_rect()

        if rect.isNull():
            return

        painter.save()
        painter.setClipRect(rect)
        painter.setOpacity(self.backdrop_opacity)

        painter.drawImage(
            rect,
            self.backdrop_image
        )

        painter.restore()


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

    def draw_rect_selection(self, painter):
        if not self.is_rect_selecting:
            return

        rect = self.get_rect_select_rect()

        if rect.isNull():
            return

        painter.setBrush(QtGui.QBrush(self.rect_select_fill))
        painter.setPen(QtGui.QPen(self.rect_select_outline, 1))
        painter.drawRect(rect)

    def draw_hud(self, painter):
        painter.setPen(QtGui.QPen(QtGui.QColor(180, 180, 185), 1))

        text = "MMB pan | Wheel zoom | Box drawer handles box edit | UV drawer handles UV display"

        painter.drawText(
            12,
            self.height() - 12,
            text
        )