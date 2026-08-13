# ET_ui/ET_uv_drawer.py

try:
    from PySide2 import QtCore, QtGui
except ImportError:
    from PySide6 import QtCore, QtGui

from ET_ui.ET_drawable_object import EDrawableObjectController

class EUVDrawer(EDrawableObjectController):
    """
    Draws and controls cached UV preview data.

    The drawer does not query Maya.
    It only draws/interacts with data already stored in EUVCache.

    First responsive behavior:
    - hover shell by edge proximity
    - drag shell in preview space
    - do not apply changes to Maya
    """

    def __init__(self, viewer):
        super(EUVDrawer, self).__init__(
            viewer, drawable_kind="uv")

        self.draw_faces_enabled = True
        self.draw_edges_enabled = True
        self.draw_vertices_enabled = True

        self.face_color = QtGui.QColor(60, 140, 255, 35)
        self.edge_color = QtGui.QColor(80, 190, 255, 230)
        self.vertex_color = QtGui.QColor(220, 245, 255, 255)

        self.hover_face_color = QtGui.QColor(255, 220, 80, 45)
        self.hover_edge_color = QtGui.QColor(255, 220, 80, 255)
        self.hover_vertex_color = QtGui.QColor(255, 245, 170, 255)

        self.active_face_color = QtGui.QColor(255, 170, 40, 50)
        self.active_edge_color = QtGui.QColor(255, 170, 40, 255)
        self.active_vertex_color = QtGui.QColor(255, 230, 120, 255)

        self.edge_width = 1.0
        self.hover_edge_width = 2.0
        self.active_edge_width = 2.5

        self.vertex_radius = 1.8
        self.hover_vertex_radius = 2.6
        self.active_vertex_radius = 3.0

        self.hover_shell = None
        self.active_shell = None

        self.is_dragging_shell = False
        self.drag_start_positions = None

        self.drag_start_shell_bounds = None

        self.shell_hit_pixel_distance = 8.0

    # -----------------------------------------------------
    # Cache
    # -----------------------------------------------------

    def get_cache(self):
        return self.viewer.uv_cache

    def has_cache(self):
        cache = self.get_cache()
        return bool(cache and cache.has_data())

    # -----------------------------------------------------
    # UV positions
    # -----------------------------------------------------

    def get_uv_position(self, mesh_data, uv_id):
        if (
            hasattr(mesh_data, "preview_uv_positions") and
            uv_id in mesh_data.preview_uv_positions
        ):
            return mesh_data.preview_uv_positions[uv_id]

        return mesh_data.uv_positions[uv_id]

    def uv_point_to_screen(self, mesh_data, uv_id):
        u, v = self.get_uv_position(mesh_data, uv_id)
        return self.viewer.uv_to_screen(u, v)

    # -----------------------------------------------------
    # Shell checks
    # -----------------------------------------------------

    def shell_key(self, mesh_data, shell_data):
        return (
            mesh_data.mesh_name,
            mesh_data.uv_set,
            shell_data.shell_id
        )

    def shell_matches(self, shell_ref, mesh_data, shell_data):
        if not shell_ref:
            return False

        ref_mesh_data, ref_shell_data = shell_ref

        return (
            ref_mesh_data is mesh_data and
            ref_shell_data is shell_data
        )

    # -----------------------------------------------------
    # Drawing
    # -----------------------------------------------------

    def draw_cache(self, painter, uv_cache):
        if not uv_cache:
            return

        if not uv_cache.has_data():
            return

        for mesh_data in uv_cache.meshes:
            for shell_data in mesh_data.shells:
                is_hovered = self.shell_matches(
                    self.hover_shell,
                    mesh_data,
                    shell_data
                )

                is_active = self.shell_matches(
                    self.active_shell,
                    mesh_data,
                    shell_data
                )

                if self.draw_faces_enabled:
                    self.draw_shell_faces(
                        painter,
                        mesh_data,
                        shell_data,
                        is_hovered,
                        is_active
                    )

                if self.draw_edges_enabled:
                    self.draw_shell_edges(
                        painter,
                        mesh_data,
                        shell_data,
                        is_hovered,
                        is_active
                    )

                if self.draw_vertices_enabled:
                    self.draw_shell_vertices(
                        painter,
                        mesh_data,
                        shell_data,
                        is_hovered,
                        is_active
                    )

    def draw_shell_faces(self, painter, mesh_data, shell_data, is_hovered, is_active):
        if is_active:
            color = self.active_face_color
        elif is_hovered:
            color = self.hover_face_color
        else:
            color = self.face_color

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QBrush(color))

        for face_uv_ids in shell_data.faces:
            polygon = QtGui.QPolygonF()

            for uv_id in face_uv_ids:
                polygon.append(
                    self.uv_point_to_screen(mesh_data, uv_id)
                )

            if not polygon.isEmpty():
                painter.drawPolygon(polygon)

    def draw_shell_edges(self, painter, mesh_data, shell_data, is_hovered, is_active):
        if is_active:
            color = self.active_edge_color
            width = self.active_edge_width
        elif is_hovered:
            color = self.hover_edge_color
            width = self.hover_edge_width
        else:
            color = self.edge_color
            width = self.edge_width

        pen = QtGui.QPen(
            color,
            width
        )

        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)

        for uv_a, uv_b in shell_data.edges:
            p_a = self.uv_point_to_screen(mesh_data, uv_a)
            p_b = self.uv_point_to_screen(mesh_data, uv_b)

            painter.drawLine(p_a, p_b)

    def draw_shell_vertices(self, painter, mesh_data, shell_data, is_hovered, is_active):
        if is_active:
            color = self.active_vertex_color
            radius = self.active_vertex_radius
        elif is_hovered:
            color = self.hover_vertex_color
            radius = self.hover_vertex_radius
        else:
            color = self.vertex_color
            radius = self.vertex_radius

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QBrush(color))

        for uv_id in shell_data.uv_ids:
            point = self.uv_point_to_screen(mesh_data, uv_id)

            rect = QtCore.QRectF(
                point.x() - radius,
                point.y() - radius,
                radius * 2.0,
                radius * 2.0
            )

            painter.drawEllipse(rect)

    # -----------------------------------------------------
    # Hit testing
    # -----------------------------------------------------

    def hit_test_shell(self, pos):
        """
        Return:
            (mesh_data, shell_data) or (None, None)

        First version hits shell edges only.
        This is stable and avoids weird face-fill ambiguity.
        """

        if not self.has_cache():
            return None, None

        threshold_sq = self.shell_hit_pixel_distance * self.shell_hit_pixel_distance

        cache = self.get_cache()

        for mesh_data in reversed(cache.meshes):
            for shell_data in reversed(mesh_data.shells):
                for uv_a, uv_b in shell_data.edges:
                    p_a = self.uv_point_to_screen(mesh_data, uv_a)
                    p_b = self.uv_point_to_screen(mesh_data, uv_b)

                    distance_sq = self.distance_sq_to_segment(
                        pos,
                        p_a,
                        p_b
                    )

                    if distance_sq <= threshold_sq:
                        return mesh_data, shell_data

        return None, None

    # -----------------------------------------------------
    # Drag shell
    # -----------------------------------------------------

    def begin_drag_shell(self, mesh_data, shell_data, pos):
        if not hasattr(mesh_data, "preview_uv_positions"):
            mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)

        shell_ref = (mesh_data, shell_data)

        self.is_dragging_shell = True
        self.active_shell = shell_ref
        self.hover_shell = shell_ref
        self.set_active_object(shell_ref)
        self.set_hover_object(shell_ref)

        self.begin_drag_object(
            shell_ref,
            pos
        )
        self.drag_start_positions = {}

        for uv_id in shell_data.uv_ids:
            self.drag_start_positions[uv_id] = mesh_data.preview_uv_positions[uv_id]

        self.drag_start_shell_bounds = self.get_uv_bounds_from_positions(self.drag_start_positions)

        self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
        self.viewer.update()

    def update_drag_shell(self, pos):
        if not self.is_dragging_shell:
            return

        if not self.active_shell:
            return

        mesh_data, shell_data = self.active_shell
        du, dv = self.get_drag_delta_uv(pos)

        if self.drag_start_shell_bounds:
            u_min, v_min, u_max, v_max = self.drag_start_shell_bounds

            du, dv = self.clamp_uv_delta_to_tile(
                u_min,
                v_min,
                u_max,
                v_max,
                du,
                dv
            )

        for uv_id, start_pos in self.drag_start_positions.items():
            original_u, original_v = start_pos

            mesh_data.preview_uv_positions[uv_id] = (
                original_u + du,
                original_v + dv
            )

        self.viewer.update()

    def end_drag_shell(self):
        if not self.is_dragging_shell:
            return

        self.is_dragging_shell = False
        self.drag_start_positions = None
        self.drag_start_shell_bounds = None

        self.end_drag_object()

        if self.hover_shell:
            self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
        else:
            self.viewer.setCursor(QtCore.Qt.ArrowCursor)

        self.viewer.update()

    # -----------------------------------------------------
    # Mouse events
    # -----------------------------------------------------
    def deselect(self):
        """
        Clear UV shell selection and hover state.
        """

        if self.is_dragging_shell:
            return

        self.hover_shell = None
        self.active_shell = None

        self.clear_hover_object()
        self.clear_active_object()

        self.viewer.setCursor(QtCore.Qt.ArrowCursor)
        self.viewer.update()
        
    def mouse_move_event(self, event):
        pos = event.pos()

        if self.is_dragging_shell:
            self.update_drag_shell(pos)
            return True

        mesh_data, shell_data = self.hit_test_shell(pos)

        if mesh_data and shell_data:
            new_hover = (mesh_data, shell_data)
        else:
            new_hover = None

        if new_hover != self.hover_shell:
            self.hover_shell = new_hover
            self.set_hover_object(new_hover)

            if self.hover_shell:
                self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
            else:
                self.viewer.setCursor(QtCore.Qt.ArrowCursor)

            self.viewer.update()

        # Return False for pure hover so other systems can still work if needed.
        return False

    def mouse_press_event(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return False

        pos = event.pos()

        mesh_data, shell_data = self.hit_test_shell(pos)

        if not mesh_data or not shell_data:
            return False

        self.begin_drag_shell(
            mesh_data,
            shell_data,
            pos
        )

        return True

    def mouse_release_event(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return False

        if self.is_dragging_shell:
            self.end_drag_shell()
            return True

        return False

    def leave_event(self, event):
        if self.is_dragging_shell:
            return

        self.hover_shell = None
        self.viewer.setCursor(QtCore.Qt.ArrowCursor)
        self.viewer.update()