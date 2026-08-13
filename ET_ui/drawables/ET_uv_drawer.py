# ET_ui/ET_uv_drawer.py

try:
    from PySide2 import QtCore, QtGui
except ImportError:
    from PySide6 import QtCore, QtGui

from ET_ui.drawables.ET_drawable_object import EDrawableObjectController
from ET_core import ET_uv_model

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

        self.selection_mode = "shell"

        self.hover_shell = None
        self.active_shell = None

        self.hover_face = None
        self.active_face = None

        self.is_dragging_shell = False
        self.is_dragging_face = False

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

    def set_selection_mode(self, mode):
        """
        Set UV selection behavior.

        mode:
            "shell"
            "face"
        """

        if mode not in ("shell", "face"):
            return

        self.selection_mode = mode

        self.hover_shell = None
        self.active_shell = None
        self.hover_face = None
        self.active_face = None

        self.clear_hover_object()
        self.clear_active_object()

        self.viewer.setCursor(QtCore.Qt.ArrowCursor)
        self.viewer.update()

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

    def drawable_key_for_face(self, mesh_data, face_index):
        return (
            "uv_face",
            mesh_data.mesh_name,
            mesh_data.uv_set,
            face_index
        )


    def face_ref_matches(self, face_ref, mesh_data, face_index):
        if not face_ref:
            return False

        ref_mesh_data, ref_face_index, ref_face_uv_ids = face_ref

        return (
            ref_mesh_data is mesh_data and
            ref_face_index == face_index
        )


    def get_face_index(self, mesh_data, face_uv_ids):
        """
        Return index of a face list inside mesh_data.faces.
        """

        for index, test_face_uv_ids in enumerate(mesh_data.faces):
            if test_face_uv_ids is face_uv_ids:
                return index

            if test_face_uv_ids == face_uv_ids:
                return index

        return -1
    
    def get_shell_screen_bounds(self, mesh_data, shell_data):
        """
        Return screen-space bounding rect for a shell.
        """

        polygon = QtGui.QPolygonF()

        for uv_id in shell_data.uv_ids:
            polygon.append(
                self.uv_point_to_screen(
                    mesh_data,
                    uv_id
                )
            )

        if polygon.isEmpty():
            return QtCore.QRectF()

        return polygon.boundingRect()

    def uv_polygon_for_face(self, mesh_data, face_uv_ids):
        polygon = QtGui.QPolygonF()

        for uv_id in face_uv_ids:
            polygon.append(
                self.uv_point_to_screen(mesh_data, uv_id)
            )

        return polygon

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

                is_selected = self.viewer.is_drawable_selected(
                    self.drawable_key_for_shell(
                        mesh_data,
                        shell_data
                    )
                )

                is_active = (
                    self.shell_matches(
                        self.active_shell,
                        mesh_data,
                        shell_data
                    ) or
                    is_selected
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
        painter.setPen(QtCore.Qt.NoPen)

        for face_uv_ids in shell_data.faces:
            face_index = self.get_face_index(
                mesh_data,
                face_uv_ids
            )

            is_face_hovered = self.face_ref_matches(
                self.hover_face,
                mesh_data,
                face_index
            )

            is_face_active = self.face_ref_matches(
                self.active_face,
                mesh_data,
                face_index
            )

            is_face_selected = self.viewer.is_drawable_selected(
                self.drawable_key_for_face(
                    mesh_data,
                    face_index
                )
            )

            if self.selection_mode == "face" and (
                is_face_hovered or
                is_face_active or
                is_face_selected
            ):
                if is_face_active or is_face_selected:
                    color = self.active_face_color
                else:
                    color = self.hover_face_color
            else:
                if is_active:
                    color = self.active_face_color
                elif is_hovered:
                    color = self.hover_face_color
                else:
                    color = self.face_color

            painter.setBrush(QtGui.QBrush(color))

            polygon = self.uv_polygon_for_face(
                mesh_data,
                face_uv_ids
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
    # Preview fit / trim operations
    # -----------------------------------------------------

    def get_active_shell_ref(self):
        return self.active_shell


    def get_uv_pair_bounds(self, uv_pairs):
        """
        uv_pairs:
            [(mesh_data, uv_id), ...]

        Returns:
            u_min, v_min, u_max, v_max
        """

        positions = {}

        for index, pair in enumerate(uv_pairs):
            mesh_data, uv_id = pair
            positions[index] = self.get_uv_position(mesh_data, uv_id)

        return self.get_uv_bounds_from_positions(positions)


    def fit_uv_pairs_to_box(self, uv_pairs, box):
        """
        Fit a group of preview UVs into a trim box.

        Current behavior:
        - stretch fill into the box
        - viewer preview only
        - no Maya UVs are modified
        """

        if not uv_pairs:
            return False

        src_u_min, src_v_min, src_u_max, src_v_max = self.get_uv_pair_bounds(
            uv_pairs
        )

        src_width = src_u_max - src_u_min
        src_height = src_v_max - src_v_min

        if src_width <= 0.000001 or src_height <= 0.000001:
            print("[eTrim] Cannot trim UVs. Source UV bounds are too small.")
            return False

        dst_u_min = box.u_min
        dst_v_min = box.v_min
        dst_u_max = box.u_max
        dst_v_max = box.v_max

        dst_width = dst_u_max - dst_u_min
        dst_height = dst_v_max - dst_v_min

        if dst_width <= 0.000001 or dst_height <= 0.000001:
            print("[eTrim] Cannot trim UVs. Target box bounds are too small.")
            return False

        scale_u = dst_width / src_width
        scale_v = dst_height / src_height

        for mesh_data, uv_id in uv_pairs:
            u, v = self.get_uv_position(mesh_data, uv_id)

            normalized_u = (u - src_u_min) / src_width
            normalized_v = (v - src_v_min) / src_height

            new_u = dst_u_min + normalized_u * dst_width
            new_v = dst_v_min + normalized_v * dst_height

            mesh_data.preview_uv_positions[uv_id] = (
                new_u,
                new_v
            )

        self.viewer.update()
        return True


    def fit_shell_to_box(self, mesh_data, shell_data, box):
        """
        Fit one shell preview into one trim box.
        """

        if not mesh_data or not shell_data or not box:
            return False

        if not hasattr(mesh_data, "preview_uv_positions"):
            mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)

        uv_pairs = [
            (mesh_data, uv_id)
            for uv_id in shell_data.uv_ids
        ]

        result = self.fit_uv_pairs_to_box(
            uv_pairs,
            box
        )

        if result:
            shell_ref = (mesh_data, shell_data)
            self.active_shell = shell_ref
            self.hover_shell = shell_ref
            self.set_active_object(shell_ref)
            self.set_hover_object(shell_ref)

        return result


    def fit_active_shell_to_box(self, box):
        """
        Fit the currently active viewer shell into a trim box.
        """

        if not self.active_shell:
            return False

        mesh_data, shell_data = self.active_shell

        return self.fit_shell_to_box(
            mesh_data,
            shell_data,
            box
        )

    def fit_selected_faces_to_box(self, box):
        """
        Split selected UV faces into their own preview island,
        then fit only those selected faces into one trim box.

        Preview only.
        """

        if not box:
            return False

        selected_by_mesh = self.get_selected_face_indices_by_mesh()

        if not selected_by_mesh:
            return False

        # Split faces first, so trimming does not pull the whole shell.
        for mesh_data, face_indices in selected_by_mesh.items():
            ET_uv_model.split_faces_to_preview_shell(
                mesh_data,
                face_indices
            )

        # After splitting, selected face keys still use the same face indices,
        # but the face uv ids now point to duplicated preview uv ids.
        uv_pairs = self.get_uv_pairs_from_selected_faces()

        if not uv_pairs:
            return False

        result = self.fit_uv_pairs_to_box(
            uv_pairs,
            box
        )

        if result:
            print("[eTrim] Split and fit selected UV faces into box:", box.name)

        return result

    def fit_cache_to_box(self, uv_cache, box):
        """
        Fit all UVs in a loaded cache into one trim box.

        This is used when the user has Maya faces/components selected.
        The whole loaded selection is treated as one preview island group.
        """

        if not uv_cache or not uv_cache.has_data():
            return False

        if not box:
            return False

        uv_pairs = []

        for mesh_data in uv_cache.meshes:
            if not hasattr(mesh_data, "preview_uv_positions"):
                mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)

            for uv_id in mesh_data.preview_uv_positions.keys():
                uv_pairs.append(
                    (mesh_data, uv_id)
                )

        result = self.fit_uv_pairs_to_box(
            uv_pairs,
            box
        )

        if result:
            # Make first shell active for visual feedback, if available.
            for mesh_data in uv_cache.meshes:
                if mesh_data.shells:
                    shell_ref = (
                        mesh_data,
                        mesh_data.shells[0]
                    )

                    self.active_shell = shell_ref
                    self.hover_shell = shell_ref
                    self.set_active_object(shell_ref)
                    self.set_hover_object(shell_ref)
                    break

        return result

    # -----------------------------------------------------
    # Context menu
    # -----------------------------------------------------
    def drawable_key_for_shell(self, mesh_data, shell_data):
        return (
            "uv_shell",
            mesh_data.mesh_name,
            mesh_data.uv_set,
            shell_data.shell_id
        )
    def build_context_menu(self, shell_ref):
        menu = super(EUVDrawer, self).build_context_menu(shell_ref)

        menu.addSeparator()

        fit_inside_selected_box_action = menu.addAction("Fit Inside Selected Box")
        fit_inside_selected_box_action.triggered.connect(
            lambda: self.fit_shell_inside_selected_box(shell_ref)
        )

        return menu


    def delete_drawable(self, shell_ref):
        """
        For now, do not delete UV data from cache.

        This only clears the active shell selection.
        Real UV deletion/removal can be defined later.
        """

        print("[eTrim] Delete UV shell requested. Not wired yet:", shell_ref)

        if shell_ref == self.active_shell:
            self.active_shell = None

        if shell_ref == self.hover_shell:
            self.hover_shell = None

        self.clear_active_object()
        self.clear_hover_object()

        if shell_ref:
            mesh_data, shell_data = shell_ref
            self.viewer.deselect_drawable_key(
                self.drawable_key_for_shell(
                    mesh_data=mesh_data,
                    shell_data=shell_data
                    )
                )

        self.viewer.update()


    def fit_shell_inside_selected_box(self, shell_ref):
        if not shell_ref:
            return

        box = self.viewer.model.get_active_box()

        if not box:
            print("[eTrim] No active box selected.")
            return

        mesh_data, shell_data = shell_ref

        result = self.fit_shell_to_box(
            mesh_data,
            shell_data,
            box
        )

        if result:
            print("[eTrim] Fit shell inside selected box:", box.name)


    # -----------------------------------------------------
    # Selection
    # -----------------------------------------------------

    def select_faces_in_rect(self, rect, additive=False):
        """
        Select UV faces whose screen-space polygon bounds intersect the rectangle.

        Current behavior:
        - face selection mode only
        - selects faces by polygon bounding rect overlap
        - viewer selection list owns the selected keys
        """

        if not self.has_cache():
            return False

        if rect.isNull() or rect.width() < 2.0 or rect.height() < 2.0:
            if not additive:
                self.viewer.clear_drawable_selection()
                self.active_face = None
                self.hover_face = None
                self.viewer.update()

            return False

        if not additive:
            self.viewer.clear_drawable_selection()

        selected_count = 0
        last_face_ref = None

        cache = self.get_cache()

        for mesh_data in cache.meshes:
            for face_index, face_uv_ids in enumerate(mesh_data.faces):
                polygon = self.uv_polygon_for_face(
                    mesh_data,
                    face_uv_ids
                )

                if polygon.isEmpty():
                    continue

                if not polygon.boundingRect().intersects(rect):
                    continue

                drawable_key = self.drawable_key_for_face(
                    mesh_data,
                    face_index
                )

                self.viewer.select_drawable(
                    drawable_key,
                    clear_previous=False
                )

                last_face_ref = (
                    mesh_data,
                    face_index,
                    face_uv_ids
                )

                selected_count += 1

        if last_face_ref:
            self.active_face = last_face_ref
            self.hover_face = last_face_ref
            self.active_shell = None
            self.hover_shell = None

            self.set_active_object(last_face_ref)
            self.set_hover_object(last_face_ref)

        print("[eTrim] Rect-selected UV faces:", selected_count)

        self.viewer.update()
        return selected_count > 0

    def select_shells_in_rect(self, rect, additive=False):
        """
        Select UV shells whose screen-space bounds intersect the rectangle.

        Current behavior:
        - shell selection mode only
        - selects shells by bounding rect overlap
        - viewer selection list owns selected keys
        """

        if not self.has_cache():
            return False

        if rect.isNull() or rect.width() < 2.0 or rect.height() < 2.0:
            if not additive:
                self.viewer.clear_drawable_selection()
                self.active_shell = None
                self.hover_shell = None
                self.viewer.update()

            return False

        if not additive:
            self.viewer.clear_drawable_selection()

        selected_count = 0
        last_shell_ref = None

        cache = self.get_cache()

        for mesh_data in cache.meshes:
            for shell_data in mesh_data.shells:
                shell_rect = self.get_shell_screen_bounds(
                    mesh_data,
                    shell_data
                )

                if shell_rect.isNull():
                    continue

                if not shell_rect.intersects(rect):
                    continue

                drawable_key = self.drawable_key_for_shell(
                    mesh_data,
                    shell_data
                )

                self.viewer.select_drawable(
                    drawable_key,
                    clear_previous=False
                )

                last_shell_ref = (
                    mesh_data,
                    shell_data
                )

                selected_count += 1

        if last_shell_ref:
            self.active_shell = last_shell_ref
            self.hover_shell = last_shell_ref

            self.active_face = None
            self.hover_face = None

            self.set_active_object(last_shell_ref)
            self.set_hover_object(last_shell_ref)

        print("[eTrim] Rect-selected UV shells:", selected_count)

        self.viewer.update()
        return selected_count > 0

    def get_selected_face_indices_by_mesh(self):
        """
        Return:
            {
                mesh_data: set(face_index, ...)
            }
        """

        result = {}

        selected_keys = self.get_selected_face_keys()

        for key in selected_keys:
            mesh_data, face_index, face_uv_ids = self.get_face_from_drawable_key(key)

            if not mesh_data:
                continue

            if mesh_data not in result:
                result[mesh_data] = set()

            result[mesh_data].add(face_index)

        return result

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

    def hit_test_face(self, pos):
        """
        Return:
            (mesh_data, face_index, face_uv_ids) or (None, None, None)

        Face mode uses polygon hit testing.
        """

        if not self.has_cache():
            return None, None, None

        cache = self.get_cache()

        for mesh_data in reversed(cache.meshes):
            for face_index in reversed(range(len(mesh_data.faces))):
                face_uv_ids = mesh_data.faces[face_index]
                polygon = self.uv_polygon_for_face(
                    mesh_data,
                    face_uv_ids
                )

                if polygon.containsPoint(
                    QtCore.QPointF(pos),
                    QtCore.Qt.OddEvenFill
                ):
                    return mesh_data, face_index, face_uv_ids

        return None, None, None
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

    def get_selected_face_keys(self):
        """
        Return all selected drawable keys that represent UV faces.
        """

        selected = []

        for key in self.viewer.selected_drawables:
            if not key:
                continue

            if key[0] == "uv_face":
                selected.append(key)

        return selected

    def get_face_from_drawable_key(self, drawable_key):
        """
        Convert a viewer drawable key back into:
            mesh_data, face_index, face_uv_ids
        """

        if not drawable_key:
            return None, None, None

        if drawable_key[0] != "uv_face":
            return None, None, None

        _, mesh_name, uv_set, face_index = drawable_key

        if not self.has_cache():
            return None, None, None

        cache = self.get_cache()

        for mesh_data in cache.meshes:
            if mesh_data.mesh_name != mesh_name:
                continue

            if mesh_data.uv_set != uv_set:
                continue

            if face_index < 0:
                return None, None, None

            if face_index >= len(mesh_data.faces):
                return None, None, None

            return (
                mesh_data,
                face_index,
                mesh_data.faces[face_index]
            )

        return None, None, None


    def get_uv_pairs_from_selected_faces(self):
        """
        Return unique UV pairs from all selected UV faces.

        Returns:
            [(mesh_data, uv_id), ...]
        """

        selected_keys = self.get_selected_face_keys()

        uv_pairs = []
        seen = set()

        for key in selected_keys:
            mesh_data, face_index, face_uv_ids = self.get_face_from_drawable_key(key)

            if not mesh_data or not face_uv_ids:
                continue

            for uv_id in face_uv_ids:
                pair_key = (
                    id(mesh_data),
                    uv_id
                )

                if pair_key in seen:
                    continue

                seen.add(pair_key)
                uv_pairs.append(
                    (
                        mesh_data,
                        uv_id
                    )
                )

        return uv_pairs

    def begin_drag_face(self, mesh_data, face_index, face_uv_ids, pos):
        if not hasattr(mesh_data, "preview_uv_positions"):
            mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)

        face_key = self.drawable_key_for_face(
            mesh_data,
            face_index
        )

        face_ref = (
            mesh_data,
            face_index,
            face_uv_ids
        )

        self.is_dragging_face = True
        self.active_face = face_ref
        self.hover_face = face_ref

        self.set_active_object(face_ref)
        self.set_hover_object(face_ref)

        self.begin_drag_object(
            face_ref,
            pos
        )

        self.drag_start_positions = {}

        # If the clicked face is part of the current selection,
        # drag all selected UV faces together.
        if self.viewer.is_drawable_selected(face_key):
            uv_pairs = self.get_uv_pairs_from_selected_faces()
        else:
            uv_pairs = [
                (
                    mesh_data,
                    uv_id
                )
                for uv_id in face_uv_ids
            ]

        for pair_mesh_data, uv_id in uv_pairs:
            if not hasattr(pair_mesh_data, "preview_uv_positions"):
                pair_mesh_data.preview_uv_positions = dict(pair_mesh_data.uv_positions)

            pair_key = (
                id(pair_mesh_data),
                uv_id
            )

            self.drag_start_positions[pair_key] = (
                pair_mesh_data,
                uv_id,
                pair_mesh_data.preview_uv_positions[uv_id]
            )

        # Bounds need only the UV positions, so convert the drag data.
        bounds_positions = {}

        for index, drag_data in enumerate(self.drag_start_positions.values()):
            pair_mesh_data, uv_id, start_pos = drag_data
            bounds_positions[index] = start_pos

        self.drag_start_shell_bounds = self.get_uv_bounds_from_positions(
            bounds_positions
        )

        self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
        self.viewer.update()


    def update_drag_face(self, pos):
        if not self.is_dragging_face:
            return

        if not self.active_face:
            return

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

        for drag_data in self.drag_start_positions.values():
            mesh_data, uv_id, start_pos = drag_data
            original_u, original_v = start_pos

            mesh_data.preview_uv_positions[uv_id] = (
                original_u + du,
                original_v + dv
            )

        self.viewer.update()



    def end_drag_face(self):
        if not self.is_dragging_face:
            return

        self.is_dragging_face = False
        self.drag_start_positions = None
        self.drag_start_shell_bounds = None

        self.end_drag_object()

        if self.hover_face:
            self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
        else:
            self.viewer.setCursor(QtCore.Qt.ArrowCursor)

        self.viewer.update()

    # -----------------------------------------------------
    # Mouse events
    # -----------------------------------------------------
    def deselect(self):
        """
        Clear UV shell/face selection and hover state.
        """

        if self.is_dragging_shell or self.is_dragging_face:
            return

        self.hover_shell = None
        self.active_shell = None

        self.hover_face = None
        self.active_face = None

        self.clear_hover_object()
        self.clear_active_object()

        self.viewer.setCursor(QtCore.Qt.ArrowCursor)
        self.viewer.update()
        
    def mouse_move_event(self, event):
        pos = event.pos()

        if self.is_dragging_shell:
            self.update_drag_shell(pos)
            return True

        if self.is_dragging_face:
            self.update_drag_face(pos)
            return True

        if self.selection_mode == "face":
            mesh_data, face_index, face_uv_ids = self.hit_test_face(pos)

            if mesh_data and face_uv_ids:
                new_hover = (
                    mesh_data,
                    face_index,
                    face_uv_ids
                )
            else:
                new_hover = None

            if new_hover != self.hover_face:
                self.hover_face = new_hover
                self.set_hover_object(new_hover)

                if self.hover_face:
                    self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
                else:
                    self.viewer.setCursor(QtCore.Qt.ArrowCursor)

                self.viewer.update()

            return False

        # Shell mode.
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

        return False

    def mouse_press_event(self, event):
        if event.button() not in (
            QtCore.Qt.LeftButton,
            QtCore.Qt.RightButton
        ):
            return False

        pos = event.pos()

        if self.selection_mode == "face":
            mesh_data, face_index, face_uv_ids = self.hit_test_face(pos)

            if not mesh_data or not face_uv_ids:
                return False

            face_ref = (
                mesh_data,
                face_index,
                face_uv_ids
            )

            self.active_face = face_ref
            self.hover_face = face_ref

            self.active_shell = None
            self.hover_shell = None

            self.set_active_object(face_ref)
            self.set_hover_object(face_ref)

            additive = bool(
                event.modifiers() & QtCore.Qt.ShiftModifier
            )

            face_key = self.drawable_key_for_face(mesh_data, face_index)

            additive = bool(
                event.modifiers() & QtCore.Qt.ShiftModifier
            )

            already_selected = self.viewer.is_drawable_selected(face_key)

            # If already selected and not additive, preserve multi-selection for group drag.
            if already_selected and not additive:
                pass
            else:
                self.viewer.select_drawable(face_key, clear_previous=not additive)

            if additive and event.button() == QtCore.Qt.LeftButton:
                self.viewer.update()
                return True

            if event.button() == QtCore.Qt.RightButton:
                self.show_context_menu(
                    event,
                    face_ref
                )

                self.viewer.update()
                return True

            self.begin_drag_face(
                mesh_data,
                face_index,
                face_uv_ids,
                pos
            )

            return True

        # Shell mode.
        mesh_data, shell_data = self.hit_test_shell(pos)

        if not mesh_data or not shell_data:
            return False

        shell_ref = (mesh_data, shell_data)

        self.active_shell = shell_ref
        self.hover_shell = shell_ref

        self.active_face = None
        self.hover_face = None

        self.set_active_object(shell_ref)
        self.set_hover_object(shell_ref)

        self.viewer.select_drawable(
            self.drawable_key_for_shell(
                mesh_data,
                shell_data
            ),
            clear_previous=True
        )

        if event.button() == QtCore.Qt.RightButton:
            self.show_context_menu(
                event,
                shell_ref
            )

            self.viewer.update()
            return True

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

        if self.is_dragging_face:
            self.end_drag_face()
            return True

        return False

    def leave_event(self, event):
        if self.is_dragging_shell or self.is_dragging_face:
            return

        self.hover_shell = None
        self.hover_face = None

        self.viewer.setCursor(QtCore.Qt.ArrowCursor)
        self.viewer.update()