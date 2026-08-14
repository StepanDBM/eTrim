# ET_ui/ET_uv_drawer.py

import math

try:
    from PySide2 import QtCore, QtGui, QtWidgets
except ImportError:
    from PySide6 import QtCore, QtGui, QtWidgets

from ET_ui.drawables.ET_drawable_object import EDrawableObjectController
from ET_core import ET_uv_model
from ET_core import ET_uv_unwrap
from ET_core import ET_gridify

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

        self.hover_vertex = None
        self.active_vertex = None

        self.is_dragging_shell = False
        self.is_dragging_face = False
        self.is_dragging_vertex = False

        self.drag_start_positions = None
        self.drag_start_shell_bounds = None

        self.shell_hit_pixel_distance = 8.0
        self.vertex_hit_pixel_distance = 8.0

    FIT_MODE_STRETCH_FILL = "stretch_fill"
    FIT_MODE_UNIFORM_INSIDE = "uniform_inside"
    FIT_MODE_UNIFORM_FILL = "uniform_fill"
    FIT_MODE_BEST_90_INSIDE = "best_90_inside"


    def normalize_fit_mode(self, fit_mode):
        """
        Normalize old/unknown fit mode names.
        """

        if fit_mode in (
            self.FIT_MODE_STRETCH_FILL,
            self.FIT_MODE_UNIFORM_INSIDE,
            self.FIT_MODE_UNIFORM_FILL,
            self.FIT_MODE_BEST_90_INSIDE
        ):
            return fit_mode

        # Backward compatibility with old default.
        if fit_mode == "fit_height":
            return self.FIT_MODE_STRETCH_FILL

        return self.FIT_MODE_STRETCH_FILL


    def get_box_fit_mode(self, box):
        if not box:
            return self.FIT_MODE_STRETCH_FILL

        return self.normalize_fit_mode(
            getattr(
                box,
                "fit_mode",
                self.FIT_MODE_STRETCH_FILL
            )
        )

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

        if mode not in ("shell", "face", "vertex"):
            return

        self.selection_mode = mode

        self.hover_shell = None
        self.active_shell = None
        self.hover_face = None
        self.active_face = None
        self.hover_vertex = None
        self.active_vertex = None

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

    def drawable_key_for_vertex(self, mesh_data, uv_id):
        return (
            "uv_vertex",
            mesh_data.mesh_name,
            mesh_data.uv_set,
            uv_id
        )


    def vertex_ref_matches(self, vertex_ref, mesh_data, uv_id):
        if not vertex_ref:
            return False

        ref_mesh_data, ref_uv_id = vertex_ref

        return (
            ref_mesh_data is mesh_data and
            ref_uv_id == uv_id
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

            # Shell mode:
            # keep face fill normal. Shell selection is shown by outer boundary only.
            if self.selection_mode == "shell":
                color = self.face_color

            # Face mode:
            # individual face fill state.
            else:
                if is_face_active or is_face_selected:
                    color = self.active_face_color
                elif is_face_hovered:
                    color = self.hover_face_color
                else:
                    color = self.face_color

            painter.setBrush(
                QtGui.QBrush(color)
            )

            polygon = self.uv_polygon_for_face(
                mesh_data,
                face_uv_ids
            )

            if not polygon.isEmpty():
                painter.drawPolygon(polygon)

    def draw_shell_edges(self, painter, mesh_data, shell_data, is_hovered, is_active):
        """
        Draw shell/face edge states.

        Shell mode:
            - all shell edges draw normally
            - only shell boundary edges highlight on shell hover/selection

        Face mode:
            - all shell edges draw normally
            - selected/hovered/active face edges highlight individually
        """

        # -----------------------------------------------------
        # Base edges
        # -----------------------------------------------------

        painter.setPen(
            QtGui.QPen(
                self.edge_color,
                self.edge_width
            )
        )

        painter.setBrush(
            QtCore.Qt.NoBrush
        )

        for uv_a, uv_b in shell_data.edges:
            self.draw_uv_edge(
                painter,
                mesh_data,
                uv_a,
                uv_b
            )

        # -----------------------------------------------------
        # Shell mode overlay: boundary only
        # -----------------------------------------------------

        if self.selection_mode == "shell":
            if not is_hovered and not is_active:
                return

            if is_active:
                color = self.active_edge_color
                width = self.active_edge_width
            else:
                color = self.hover_edge_color
                width = self.hover_edge_width

            painter.setPen(
                QtGui.QPen(
                    color,
                    width
                )
            )

            boundary_edges = self.get_shell_boundary_edges(
                shell_data
            )

            for uv_a, uv_b in boundary_edges:
                self.draw_uv_edge(
                    painter,
                    mesh_data,
                    uv_a,
                    uv_b
                )

            return

        # -----------------------------------------------------
        # Face mode overlay: per-face edges
        # -----------------------------------------------------

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

            if not is_face_hovered and not is_face_active and not is_face_selected:
                continue

            if is_face_active or is_face_selected:
                color = self.active_edge_color
                width = self.active_edge_width
            else:
                color = self.hover_edge_color
                width = self.hover_edge_width

            painter.setPen(
                QtGui.QPen(
                    color,
                    width
                )
            )

            for uv_a, uv_b in self.get_face_edges(face_uv_ids):
                self.draw_uv_edge(
                    painter,
                    mesh_data,
                    uv_a,
                    uv_b
                )

    def draw_shell_vertices(self, painter, mesh_data, shell_data, is_hovered, is_active):
        """
        Draw vertex states.

        Shell mode:
            - all vertices normal
            - only boundary vertices highlight on shell hover/selection

        Face mode:
            - all vertices normal
            - selected/hovered/active face vertices highlight individually
        """

        # -----------------------------------------------------
        # Base vertices
        # -----------------------------------------------------

        painter.setPen(
            QtCore.Qt.NoPen
        )

        painter.setBrush(
            QtGui.QBrush(self.vertex_color)
        )

        for uv_id in shell_data.uv_ids:
            self.draw_uv_vertex(
                painter,
                mesh_data,
                uv_id,
                self.vertex_radius
            )

        # -----------------------------------------------------
        # Vertex mode overlay: selected/hovered/active vertices
        # -----------------------------------------------------

        if self.selection_mode == "vertex":
            highlighted_uv_ids = {}

            for uv_id in shell_data.uv_ids:
                is_vertex_hovered = self.vertex_ref_matches(
                    self.hover_vertex,
                    mesh_data,
                    uv_id
                )

                is_vertex_active = self.vertex_ref_matches(
                    self.active_vertex,
                    mesh_data,
                    uv_id
                )

                is_vertex_selected = self.viewer.is_drawable_selected(
                    self.drawable_key_for_vertex(
                        mesh_data,
                        uv_id
                    )
                )

                if is_vertex_active or is_vertex_selected:
                    highlighted_uv_ids[uv_id] = "active"

                elif is_vertex_hovered:
                    highlighted_uv_ids[uv_id] = "hover"

            for uv_id, state in highlighted_uv_ids.items():
                if state == "active":
                    color = self.active_vertex_color
                    radius = self.active_vertex_radius
                else:
                    color = self.hover_vertex_color
                    radius = self.hover_vertex_radius

                painter.setBrush(
                    QtGui.QBrush(color)
                )

                self.draw_uv_vertex(
                    painter,
                    mesh_data,
                    uv_id,
                    radius
                )

            return

        # -----------------------------------------------------
        # Shell mode overlay: boundary vertices only
        # -----------------------------------------------------

        if self.selection_mode == "shell":
            if not is_hovered and not is_active:
                return

            if is_active:
                color = self.active_vertex_color
                radius = self.active_vertex_radius
            else:
                color = self.hover_vertex_color
                radius = self.hover_vertex_radius

            painter.setBrush(
                QtGui.QBrush(color)
            )

            boundary_uv_ids = set()

            for uv_a, uv_b in self.get_shell_boundary_edges(shell_data):
                boundary_uv_ids.add(uv_a)
                boundary_uv_ids.add(uv_b)

            for uv_id in boundary_uv_ids:
                self.draw_uv_vertex(
                    painter,
                    mesh_data,
                    uv_id,
                    radius
                )

            return

        # -----------------------------------------------------
        # Face mode overlay: per-face vertices
        # -----------------------------------------------------

        highlighted_uv_ids = {}

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

            if is_face_active or is_face_selected:
                for uv_id in face_uv_ids:
                    highlighted_uv_ids[uv_id] = "active"

            elif is_face_hovered:
                for uv_id in face_uv_ids:
                    if uv_id not in highlighted_uv_ids:
                        highlighted_uv_ids[uv_id] = "hover"

        for uv_id, state in highlighted_uv_ids.items():
            if state == "active":
                color = self.active_vertex_color
                radius = self.active_vertex_radius
            else:
                color = self.hover_vertex_color
                radius = self.hover_vertex_radius

            painter.setBrush(
                QtGui.QBrush(color)
            )

            self.draw_uv_vertex(
                painter,
                mesh_data,
                uv_id,
                radius
            )

    def edge_key(self, uv_a, uv_b):
        return tuple(sorted((uv_a, uv_b)))


    def get_shell_boundary_edges(self, shell_data):
        """
        Return only outer boundary edges for a shell.

        Internal shared face edges are ignored.
        """

        edge_counts = {}

        for face_uv_ids in shell_data.faces:
            count = len(face_uv_ids)

            for index, uv_a in enumerate(face_uv_ids):
                uv_b = face_uv_ids[(index + 1) % count]

                key = self.edge_key(
                    uv_a,
                    uv_b
                )

                edge_counts[key] = edge_counts.get(key, 0) + 1

        boundary_edges = []

        for face_uv_ids in shell_data.faces:
            count = len(face_uv_ids)

            for index, uv_a in enumerate(face_uv_ids):
                uv_b = face_uv_ids[(index + 1) % count]

                key = self.edge_key(
                    uv_a,
                    uv_b
                )

                if edge_counts.get(key, 0) == 1:
                    boundary_edges.append(
                        (
                            uv_a,
                            uv_b
                        )
                    )

        return boundary_edges


    def get_face_edges(self, face_uv_ids):
        edges = []

        count = len(face_uv_ids)

        for index, uv_a in enumerate(face_uv_ids):
            uv_b = face_uv_ids[(index + 1) % count]

            edges.append(
                (
                    uv_a,
                    uv_b
                )
            )

        return edges


    def draw_uv_edge(self, painter, mesh_data, uv_a, uv_b):
        p_a = self.uv_point_to_screen(
            mesh_data,
            uv_a
        )

        p_b = self.uv_point_to_screen(
            mesh_data,
            uv_b
        )

        painter.drawLine(
            p_a,
            p_b
        )


    def draw_uv_vertex(self, painter, mesh_data, uv_id, radius):
        point = self.uv_point_to_screen(
            mesh_data,
            uv_id
        )

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

        Fit modes:
            stretch_fill:
                Non-uniform scale to fill the box exactly.

            uniform_inside:
                Uniform scale, preserve proportions, fit fully inside box.

            uniform_fill:
                Uniform scale, preserve proportions, fill box, may exceed one axis.

            best_90_inside:
                Try 0 and 90 degrees, preserve proportions, fit fully inside box.
        """

        if not uv_pairs:
            return False

        if not box:
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

        fit_mode = self.get_box_fit_mode(box)

        src_center_u = (src_u_min + src_u_max) * 0.5
        src_center_v = (src_v_min + src_v_max) * 0.5

        dst_center_u = (dst_u_min + dst_u_max) * 0.5
        dst_center_v = (dst_v_min + dst_v_max) * 0.5

        rotate_90 = False

        if fit_mode == self.FIT_MODE_STRETCH_FILL:
            for mesh_data, uv_id in uv_pairs:
                u, v = self.get_uv_position(
                    mesh_data,
                    uv_id
                )

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

        if fit_mode == self.FIT_MODE_UNIFORM_INSIDE:
            scale = min(
                dst_width / src_width,
                dst_height / src_height
            )

        elif fit_mode == self.FIT_MODE_UNIFORM_FILL:
            scale = max(
                dst_width / src_width,
                dst_height / src_height
            )

        elif fit_mode == self.FIT_MODE_BEST_90_INSIDE:
            scale_0 = min(
                dst_width / src_width,
                dst_height / src_height
            )

            scale_90 = min(
                dst_width / src_height,
                dst_height / src_width
            )

            if scale_90 > scale_0:
                rotate_90 = True
                scale = scale_90
            else:
                scale = scale_0

        else:
            scale = min(
                dst_width / src_width,
                dst_height / src_height
            )

        for mesh_data, uv_id in uv_pairs:
            if not hasattr(mesh_data, "preview_uv_positions"):
                mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)

            u, v = self.get_uv_position(
                mesh_data,
                uv_id
            )

            local_u = u - src_center_u
            local_v = v - src_center_v

            if rotate_90:
                rotated_u = -local_v
                rotated_v = local_u
            else:
                rotated_u = local_u
                rotated_v = local_v

            new_u = dst_center_u + rotated_u * scale
            new_v = dst_center_v + rotated_v * scale

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

    def fit_selected_vertices_to_box(self, box):
        """
        Fit currently selected UV vertices into one trim box.
        """

        if not box:
            return False

        uv_pairs = self.get_uv_pairs_from_selected_drawables(
            "uv_vertex"
        )

        if not uv_pairs:
            return False

        result = self.fit_uv_pairs_to_box(
            uv_pairs,
            box
        )

        if result:
            print("[eTrim] Fit selected UV vertices into box:", box.name)

        return result

    def fit_each_selected_shell_to_box(self, box):
        """
        Fit each selected UV shell individually into one trim box.

        Unlike fit_selected_shells_to_box(), this does not preserve relative
        layout between selected shells. Each shell fills the target box by itself.
        """

        if not box:
            return False

        selected_shell_keys = self.get_selected_shell_keys()

        if not selected_shell_keys:
            return False

        fitted_count = 0

        for shell_key in selected_shell_keys:
            mesh_data, shell_data = self.get_shell_from_drawable_key(shell_key)

            if not mesh_data or not shell_data:
                continue

            uv_pairs = self.get_uv_pairs_from_shell(
                mesh_data,
                shell_data
            )

            if not uv_pairs:
                continue

            if self.fit_uv_pairs_to_box(
                uv_pairs,
                box
            ):
                fitted_count += 1

        if fitted_count:
            print(
                "[eTrim] Fit each selected UV shell into box: {} | shells: {}".format(
                    box.name,
                    fitted_count
                )
            )

        return fitted_count > 0

    def fit_selected_shells_to_box(self, box):
        """
        Fit currently selected UV shells into one trim box.

        Uses viewer.selected_drawables.
        Preview only.

        Multiple selected shells are fitted together as one group,
        preserving their relative layout.
        """

        if not box:
            return False

        uv_pairs = self.get_uv_pairs_from_selected_drawables(
            "uv_shell"
        )

        if not uv_pairs:
            return False

        result = self.fit_uv_pairs_to_box(
            uv_pairs,
            box
        )

        if result:
            print("[eTrim] Fit selected UV shells into box:", box.name)

        return result

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
    # Rotation methods
    # -----------------------------------------------------

    def rotate_uv_pairs(self, uv_pairs, degrees):
        """
        Rotate preview UV pairs around their collective bounds center.

        Positive degrees rotate counter-clockwise in UV space.
        Negative degrees rotate clockwise.
        """

        if not uv_pairs:
            return False

        src_u_min, src_v_min, src_u_max, src_v_max = self.get_uv_pair_bounds(
            uv_pairs
        )

        center_u = (src_u_min + src_u_max) * 0.5
        center_v = (src_v_min + src_v_max) * 0.5

        radians = math.radians(-degrees)
        cos_value = math.cos(radians)
        sin_value = math.sin(radians)

        for mesh_data, uv_id in uv_pairs:
            if not hasattr(mesh_data, "preview_uv_positions"):
                mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)

            u, v = self.get_uv_position(
                mesh_data,
                uv_id
            )

            local_u = u - center_u
            local_v = v - center_v

            rotated_u = (local_u * cos_value) - (local_v * sin_value)
            rotated_v = (local_u * sin_value) + (local_v * cos_value)

            mesh_data.preview_uv_positions[uv_id] = (
                center_u + rotated_u,
                center_v + rotated_v
            )

        self.viewer.update()
        return True


    def rotate_shell_context(self, shell_ref, degrees):
        """
        Rotate clicked shell, or all selected shells if clicked shell is selected.
        """

        if not self.is_shell_ref(shell_ref):
            return False

        uv_pairs = self.get_uv_pairs_for_shell_context(
            shell_ref
        )

        if not uv_pairs:
            return False

        result = self.rotate_uv_pairs(
            uv_pairs,
            degrees
        )

        if result:
            print("[eTrim] Rotated shell UVs by {} degrees.".format(degrees))

        return result


    def rotate_shell_clockwise_90(self, shell_ref):
        """
        Rotate shell clockwise by 90 degrees.
        """

        return self.rotate_shell_context(
            shell_ref,
            90.0
        )


    def rotate_shell_arbitrary(self, shell_ref):
        """
        Ask user for degrees, then rotate shell.
        """

        if not self.is_shell_ref(shell_ref):
            return False

        value, accepted = QtWidgets.QInputDialog.getDouble(
            self.viewer,
            "Rotate Shell",
            "Degrees:",
            0.0,
            -3600.0,
            3600.0,
            2
        )

        if not accepted:
            return False

        return self.rotate_shell_context(
            shell_ref,
            float(value)
        )

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
    
    def build_context_menu(self, uv_ref):
        menu = super(EUVDrawer, self).build_context_menu(uv_ref)

        menu.addSeparator()

        unwrap_selected_action = menu.addAction("Native Unwrap Selected UVs")
        unwrap_selected_action.triggered.connect(
            self.native_unwrap_selected_uvs
        )

        gridify_selected_action = menu.addAction("Gridify Selected UVs")
        gridify_selected_action.triggered.connect(
            self.gridify_selected_uvs
        )

        unwrap_gridify_action = menu.addAction("Native Unwrap + Gridify")
        unwrap_gridify_action.triggered.connect(
            self.native_unwrap_and_gridify_selected_uvs
        )

        # Shell-only actions.
        if self.is_shell_ref(uv_ref):
            menu.addSeparator()

            fit_inside_selected_box_action = menu.addAction("Fit Inside Selected Box")
            fit_inside_selected_box_action.triggered.connect(
                lambda: self.fit_shell_inside_selected_box(uv_ref)
            )

            menu.addSeparator()

            rotate_90_action = menu.addAction("Rotate 90 Clockwise")
            rotate_90_action.triggered.connect(
                lambda: self.rotate_shell_clockwise_90(uv_ref)
            )

            rotate_custom_action = menu.addAction("Rotate...")
            rotate_custom_action.triggered.connect(
                lambda: self.rotate_shell_arbitrary(uv_ref)
            )

        return menu

    def is_shell_ref(self, shell_ref):
        if not shell_ref:
            return False

        if not isinstance(shell_ref, tuple):
            return False

        if len(shell_ref) != 2:
            return False

        mesh_data, shell_data = shell_ref

        return hasattr(shell_data, "shell_id")

    def get_selected_vertex_keys(self):
        """
        Return all selected drawable keys that represent UV vertices.
        """

        return self.viewer.get_selected_drawables_by_type("uv_vertex")


    def get_vertex_from_drawable_key(self, drawable_key):
        """
        Convert a viewer drawable key back into:
            mesh_data, uv_id
        """

        if not drawable_key:
            return None, None

        if drawable_key[0] != "uv_vertex":
            return None, None

        _, mesh_name, uv_set, uv_id = drawable_key

        if not self.has_cache():
            return None, None

        cache = self.get_cache()

        for mesh_data in cache.meshes:
            if mesh_data.mesh_name != mesh_name:
                continue

            if mesh_data.uv_set != uv_set:
                continue

            if uv_id in mesh_data.uv_positions:
                return mesh_data, uv_id

            if (
                hasattr(mesh_data, "preview_uv_positions") and
                uv_id in mesh_data.preview_uv_positions
            ):
                return mesh_data, uv_id

        return None, None


    def get_uv_pairs_from_selected_vertices(self):
        """
        Return unique UV pairs from all selected UV vertices.
        """

        uv_pairs = []
        seen = set()

        for key in self.get_selected_vertex_keys():
            mesh_data, uv_id = self.get_vertex_from_drawable_key(key)

            if not mesh_data:
                continue

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

    def get_shell_from_drawable_key(self, drawable_key):
        """
        Convert a viewer drawable key back into:
            mesh_data, shell_data
        """

        if not drawable_key:
            return None, None

        if drawable_key[0] != "uv_shell":
            return None, None

        _, mesh_name, uv_set, shell_id = drawable_key

        if not self.has_cache():
            return None, None

        cache = self.get_cache()

        for mesh_data in cache.meshes:
            if mesh_data.mesh_name != mesh_name:
                continue

            if mesh_data.uv_set != uv_set:
                continue

            for shell_data in mesh_data.shells:
                if shell_data.shell_id == shell_id:
                    return mesh_data, shell_data

        return None, None

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

    def native_unwrap_selected_uvs(self):
        """
        Run Maya native unwrap on selected viewer UVs and write result to preview.
        """

        if not self.viewer:
            return

        result = ET_uv_unwrap.unwrap_viewer_selection_to_preview(
            self.viewer,
            iterations=1,
            pack=False
        )

        if result:
            print("[eTrim] Native unwrap selected UVs complete.")
        else:
            print("[eTrim] Native unwrap selected UVs failed or did nothing.")

        self.viewer.update()


    def gridify_selected_uvs(self):
        """
        Gridify selected viewer UVs into preview UV positions.
        """

        if not self.viewer:
            return

        result = ET_gridify.gridify_viewer_selection_to_preview(
            self.viewer
        )

        if result:
            print("[eTrim] Gridify selected UVs complete.")
        else:
            print("[eTrim] Gridify selected UVs failed or did nothing.")

        self.viewer.update()


    def native_unwrap_and_gridify_selected_uvs(self):
        """
        Native unwrap selected viewer UVs, then gridify the result.
        """

        if not self.viewer:
            return

        unwrap_result = ET_uv_unwrap.unwrap_viewer_selection_to_preview(
            self.viewer,
            iterations=1,
            pack=False
        )

        if not unwrap_result:
            print("[eTrim] Native unwrap failed. Gridify skipped.")
            return

        gridify_result = ET_gridify.gridify_viewer_selection_to_preview(
            self.viewer
        )

        if gridify_result:
            print("[eTrim] Native unwrap + gridify complete.")
        else:
            print("[eTrim] Native unwrap complete, but gridify did nothing.")

        self.viewer.update()

    # -----------------------------------------------------
    # Selection
    # -----------------------------------------------------

    def select_vertices_in_rect(self, rect, additive=False, subtractive=False):
        """
        Select or deselect UV vertices whose screen-space point is inside rect.
        """

        if not self.has_cache():
            return False

        if rect.isNull() or rect.width() < 2.0 or rect.height() < 2.0:
            return False

        selected_count = 0
        last_vertex_ref = None

        cache = self.get_cache()

        for mesh_data in cache.meshes:
            uv_ids = []

            if hasattr(mesh_data, "preview_uv_positions"):
                uv_ids = list(mesh_data.preview_uv_positions.keys())
            else:
                uv_ids = list(mesh_data.uv_positions.keys())

            for uv_id in uv_ids:
                point = self.uv_point_to_screen(
                    mesh_data,
                    uv_id
                )

                if not rect.contains(point):
                    continue

                drawable_key = self.drawable_key_for_vertex(
                    mesh_data,
                    uv_id
                )

                if subtractive:
                    self.viewer.deselect_drawable_key(drawable_key)

                    if self.vertex_ref_matches(
                        self.active_vertex,
                        mesh_data,
                        uv_id
                    ):
                        self.active_vertex = None

                    if self.vertex_ref_matches(
                        self.hover_vertex,
                        mesh_data,
                        uv_id
                    ):
                        self.hover_vertex = None

                else:
                    self.viewer.select_drawable(
                        drawable_key,
                        clear_previous=False
                    )

                    last_vertex_ref = (
                        mesh_data,
                        uv_id
                    )

                selected_count += 1

        if last_vertex_ref and not subtractive:
            self.active_vertex = last_vertex_ref
            self.hover_vertex = last_vertex_ref

            self.active_shell = None
            self.hover_shell = None
            self.active_face = None
            self.hover_face = None

            self.set_active_object(last_vertex_ref)
            self.set_hover_object(last_vertex_ref)

        print("[eTrim] Rect-selected UV vertices:", selected_count)

        self.viewer.update()
        return selected_count > 0

    def select_faces_in_rect(self, rect, additive=False, subtractive=False):
        """
        Select or deselect UV faces whose screen-space polygon bounds intersect rect.
        """

        if not self.has_cache():
            return False

        if rect.isNull() or rect.width() < 2.0 or rect.height() < 2.0:
            return False

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

                if subtractive:
                    self.viewer.deselect_drawable_key(drawable_key)
                else:
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

        if last_face_ref and not subtractive:
            self.active_face = last_face_ref
            self.hover_face = last_face_ref
            self.active_shell = None
            self.hover_shell = None

            self.set_active_object(last_face_ref)
            self.set_hover_object(last_face_ref)

        print("[eTrim] Rect-selected UV faces:", selected_count)

        self.viewer.update()
        return selected_count > 0

    def select_shells_in_rect(self, rect, additive=False, subtractive=False):
        """
        Select or deselect UV shells whose screen-space bounds intersect rect.
        """

        if not self.has_cache():
            return False

        if rect.isNull() or rect.width() < 2.0 or rect.height() < 2.0:
            return False

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

                if subtractive:
                    self.viewer.deselect_drawable_key(drawable_key)
                else:
                    self.viewer.select_drawable(
                        drawable_key,
                        clear_previous=False
                    )

                    last_shell_ref = (
                        mesh_data,
                        shell_data
                    )

                selected_count += 1

        if last_shell_ref and not subtractive:
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

    def get_uv_pairs_from_selected_drawables(self, drawable_type):
        """
        Convert viewer selected drawable keys into unique UV pairs.

        drawable_type:
            "uv_shell"
            "uv_face"
        """

        uv_pairs = []
        seen = set()

        selected_keys = self.viewer.get_selected_drawables_by_type(
            drawable_type
        )

        for key in selected_keys:
            if drawable_type == "uv_shell":
                mesh_data, shell_data = self.get_shell_from_drawable_key(key)

                if not mesh_data or not shell_data:
                    continue

                source_uv_ids = shell_data.uv_ids

            elif drawable_type == "uv_face":
                mesh_data, face_index, face_uv_ids = self.get_face_from_drawable_key(key)

                if not mesh_data or not face_uv_ids:
                    continue

                source_uv_ids = face_uv_ids

            elif drawable_type == "uv_vertex":
                mesh_data, uv_id = self.get_vertex_from_drawable_key(key)

                if not mesh_data:
                    continue

                source_uv_ids = [uv_id]

            else:
                continue

            for uv_id in source_uv_ids:
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

    def hit_test_vertex(self, pos):
        """
        Return:
            (mesh_data, uv_id) or (None, None)

        Vertex mode uses screen-space point distance.
        """

        if not self.has_cache():
            return None, None

        threshold_sq = self.vertex_hit_pixel_distance * self.vertex_hit_pixel_distance

        cache = self.get_cache()

        for mesh_data in reversed(cache.meshes):
            uv_ids = []

            if hasattr(mesh_data, "preview_uv_positions"):
                uv_ids = list(mesh_data.preview_uv_positions.keys())
            else:
                uv_ids = list(mesh_data.uv_positions.keys())

            for uv_id in reversed(uv_ids):
                point = self.uv_point_to_screen(
                    mesh_data,
                    uv_id
                )

                dx = float(pos.x()) - float(point.x())
                dy = float(pos.y()) - float(point.y())

                distance_sq = dx * dx + dy * dy

                if distance_sq <= threshold_sq:
                    return mesh_data, uv_id

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

    def build_drag_start_from_uv_pairs(self, uv_pairs):
        """
        Store drag start positions from unique UV pairs.
        """

        self.drag_start_positions = {}

        for mesh_data, uv_id in uv_pairs:
            if not hasattr(mesh_data, "preview_uv_positions"):
                mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)

            pair_key = (
                id(mesh_data),
                uv_id
            )

            self.drag_start_positions[pair_key] = (
                mesh_data,
                uv_id,
                mesh_data.preview_uv_positions[uv_id]
            )

        bounds_positions = {}

        for index, drag_data in enumerate(self.drag_start_positions.values()):
            mesh_data, uv_id, start_pos = drag_data
            bounds_positions[index] = start_pos

        self.drag_start_shell_bounds = self.get_uv_bounds_from_positions(
            bounds_positions
        )

    def begin_drag_shell(self, mesh_data, shell_data, pos):
        if not hasattr(mesh_data, "preview_uv_positions"):
            mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)

        shell_key = self.drawable_key_for_shell(
            mesh_data,
            shell_data
        )

        shell_ref = (
            mesh_data,
            shell_data
        )

        self.is_dragging_shell = True
        self.active_shell = shell_ref
        self.hover_shell = shell_ref

        self.set_active_object(shell_ref)
        self.set_hover_object(shell_ref)

        self.begin_drag_object(
            shell_ref,
            pos
        )

        if self.viewer.is_drawable_selected(shell_key):
            uv_pairs = self.get_uv_pairs_from_selected_drawables(
                "uv_shell"
            )
        else:
            uv_pairs = self.get_uv_pairs_from_shell(
                mesh_data,
                shell_data
            )

        self.build_drag_start_from_uv_pairs(
            uv_pairs
        )

        self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
        self.viewer.update()

    def update_drag_shell(self, pos):
        if not self.is_dragging_shell:
            return

        if not self.active_shell:
            return

        du, dv = self.get_drag_delta_uv(pos)

        for drag_data in self.drag_start_positions.values():
            mesh_data, uv_id, start_pos = drag_data
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

    def get_selected_shell_keys(self):
        """
        Return all selected drawable keys that represent UV shells.
        """

        return self.viewer.get_selected_drawables_by_type("uv_shell")

    def get_shell_from_drawable_key(self, drawable_key):
        """
        Convert a viewer drawable key back into:
            mesh_data, shell_data
        """

        if not drawable_key:
            return None, None

        if drawable_key[0] != "uv_shell":
            return None, None

        _, mesh_name, uv_set, shell_id = drawable_key

        if not self.has_cache():
            return None, None

        cache = self.get_cache()

        for mesh_data in cache.meshes:
            if mesh_data.mesh_name != mesh_name:
                continue

            if mesh_data.uv_set != uv_set:
                continue

            for shell_data in mesh_data.shells:
                if shell_data.shell_id == shell_id:
                    return mesh_data, shell_data

        return None, None

    def get_uv_pairs_from_selected_shells(self):
        """
        Return unique UV pairs from all selected UV shells.

        Returns:
            [(mesh_data, uv_id), ...]
        """

        selected_keys = self.get_selected_shell_keys()

        uv_pairs = []
        seen = set()

        for key in selected_keys:
            mesh_data, shell_data = self.get_shell_from_drawable_key(key)

            if not mesh_data or not shell_data:
                continue

            for uv_id in shell_data.uv_ids:
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

    def get_uv_pairs_from_shell(self, mesh_data, shell_data):
        """
        Return unique UV pairs from one shell.
        """

        uv_pairs = []
        seen = set()

        for uv_id in shell_data.uv_ids:
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


    def get_uv_pairs_for_shell_context(self, shell_ref):
        """
        If the clicked shell is selected, rotate all selected shells.
        Otherwise rotate only the clicked shell.
        """

        if not shell_ref:
            return []

        mesh_data, shell_data = shell_ref

        clicked_key = self.drawable_key_for_shell(
            mesh_data,
            shell_data
        )

        if self.viewer.is_drawable_selected(clicked_key):
            selected_shell_keys = self.get_selected_shell_keys()

            uv_pairs = []
            seen = set()

            for key in selected_shell_keys:
                selected_mesh_data, selected_shell_data = self.get_shell_from_drawable_key(key)

                if not selected_mesh_data or not selected_shell_data:
                    continue

                for uv_id in selected_shell_data.uv_ids:
                    pair_key = (
                        id(selected_mesh_data),
                        uv_id
                    )

                    if pair_key in seen:
                        continue

                    seen.add(pair_key)
                    uv_pairs.append(
                        (
                            selected_mesh_data,
                            uv_id
                        )
                    )

            return uv_pairs

        return self.get_uv_pairs_from_shell(
            mesh_data,
            shell_data
        )

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

    def begin_drag_vertex(self, mesh_data, uv_id, pos):
        if not hasattr(mesh_data, "preview_uv_positions"):
            mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)

        vertex_key = self.drawable_key_for_vertex(
            mesh_data,
            uv_id
        )

        vertex_ref = (
            mesh_data,
            uv_id
        )

        self.is_dragging_vertex = True
        self.active_vertex = vertex_ref
        self.hover_vertex = vertex_ref

        self.active_shell = None
        self.hover_shell = None
        self.active_face = None
        self.hover_face = None

        self.set_active_object(vertex_ref)
        self.set_hover_object(vertex_ref)

        self.begin_drag_object(
            vertex_ref,
            pos
        )

        if self.viewer.is_drawable_selected(vertex_key):
            uv_pairs = self.get_uv_pairs_from_selected_drawables(
                "uv_vertex"
            )
        else:
            uv_pairs = [
                (
                    mesh_data,
                    uv_id
                )
            ]

        self.build_drag_start_from_uv_pairs(
            uv_pairs
        )

        self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
        self.viewer.update()


    def update_drag_vertex(self, pos):
        if not self.is_dragging_vertex:
            return

        if not self.active_vertex:
            return

        du, dv = self.get_drag_delta_uv(pos)

        for drag_data in self.drag_start_positions.values():
            mesh_data, uv_id, start_pos = drag_data
            original_u, original_v = start_pos

            mesh_data.preview_uv_positions[uv_id] = (
                original_u + du,
                original_v + dv
            )

        self.viewer.update()


    def end_drag_vertex(self):
        if not self.is_dragging_vertex:
            return

        self.is_dragging_vertex = False
        self.drag_start_positions = None
        self.drag_start_shell_bounds = None

        self.end_drag_object()

        if self.hover_vertex:
            self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
        else:
            self.viewer.setCursor(QtCore.Qt.ArrowCursor)

        self.viewer.update()

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

        if self.viewer.is_drawable_selected(face_key):
            uv_pairs = self.get_uv_pairs_from_selected_drawables(
                "uv_face"
            )
        else:
            uv_pairs = [
                (
                    mesh_data,
                    uv_id
                )
                for uv_id in face_uv_ids
            ]

        self.build_drag_start_from_uv_pairs(
            uv_pairs
        )

        self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
        self.viewer.update()

    def update_drag_face(self, pos):
        if not self.is_dragging_face:
            return

        if not self.active_face:
            return

        du, dv = self.get_drag_delta_uv(pos)

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

        if self.is_dragging_vertex:
            self.update_drag_vertex(pos)
            return True

        if self.selection_mode == "vertex":
            mesh_data, uv_id = self.hit_test_vertex(pos)

            if mesh_data is not None and uv_id is not None:
                new_hover = (
                    mesh_data,
                    uv_id
                )
            else:
                new_hover = None

            if new_hover != self.hover_vertex:
                self.hover_vertex = new_hover
                self.set_hover_object(new_hover)

                if self.hover_vertex:
                    self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
                else:
                    self.viewer.setCursor(QtCore.Qt.ArrowCursor)

                self.viewer.update()

            return False

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

        if self.selection_mode == "vertex":
            mesh_data, uv_id = self.hit_test_vertex(pos)

            if mesh_data is None or uv_id is None:
                return False

            vertex_ref = (
                mesh_data,
                uv_id
            )

            self.active_vertex = vertex_ref
            self.hover_vertex = vertex_ref

            self.active_shell = None
            self.hover_shell = None
            self.active_face = None
            self.hover_face = None

            self.set_active_object(vertex_ref)
            self.set_hover_object(vertex_ref)

            additive = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
            subtractive = bool(event.modifiers() & QtCore.Qt.ControlModifier)

            vertex_key = self.drawable_key_for_vertex(
                mesh_data,
                uv_id
            )

            already_selected = self.viewer.is_drawable_selected(vertex_key)

            if subtractive:
                self.viewer.deselect_drawable_key(vertex_key)

                if self.active_vertex == vertex_ref:
                    self.active_vertex = None

                if self.hover_vertex == vertex_ref:
                    self.hover_vertex = None

                self.viewer.update()
                return True

            if already_selected and not additive:
                pass
            else:
                self.viewer.select_drawable(
                    vertex_key,
                    clear_previous=not additive
                )

            # Shift-click selects/adds but does not immediately drag.
            if additive and event.button() == QtCore.Qt.LeftButton:
                self.viewer.update()
                return True

            if event.button() == QtCore.Qt.RightButton:
                self.show_context_menu(
                    event,
                    vertex_ref
                )

                self.viewer.update()
                return True

            self.begin_drag_vertex(
                mesh_data,
                uv_id,
                pos
            )

            return True

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

            additive = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
            subtractive = bool(event.modifiers() & QtCore.Qt.ControlModifier)

            face_key = self.drawable_key_for_face(
                mesh_data,
                face_index
            )

            already_selected = self.viewer.is_drawable_selected(face_key)

            if subtractive:
                self.viewer.deselect_drawable_key(face_key)

                if self.active_face == face_ref:
                    self.active_face = None

                if self.hover_face == face_ref:
                    self.hover_face = None

                self.viewer.update()
                return True

            # If already selected and not additive, preserve multi-selection for group drag.
            if already_selected and not additive:
                pass
            else:
                self.viewer.select_drawable(
                    face_key,
                    clear_previous=not additive
                )

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

        shell_ref = (
            mesh_data,
            shell_data
        )

        self.active_shell = shell_ref
        self.hover_shell = shell_ref

        self.active_face = None
        self.hover_face = None

        self.set_active_object(shell_ref)
        self.set_hover_object(shell_ref)

        shell_key = self.drawable_key_for_shell(
            mesh_data,
            shell_data
        )

        additive = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
        subtractive = bool(event.modifiers() & QtCore.Qt.ControlModifier)

        already_selected = self.viewer.is_drawable_selected(shell_key)

        if subtractive:
            self.viewer.deselect_drawable_key(shell_key)

            if self.active_shell == shell_ref:
                self.active_shell = None

            if self.hover_shell == shell_ref:
                self.hover_shell = None

            self.viewer.update()
            return True

        # If clicked shell is already selected and not additive,
        # preserve multi-selection for group drag.
        if already_selected and not additive:
            pass
        else:
            self.viewer.select_drawable(
                shell_key,
                clear_previous=not additive
            )

        # Shift-click selects/adds but does not immediately drag.
        if additive and event.button() == QtCore.Qt.LeftButton:
            self.viewer.update()
            return True
        
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

        if self.is_dragging_vertex:
            self.end_drag_vertex()
            return True

        return False

    def leave_event(self, event):
        if self.is_dragging_shell or self.is_dragging_face or self.is_dragging_vertex:
            return

        self.hover_shell = None
        self.active_shell = None

        self.hover_face = None
        self.active_face = None

        self.hover_vertex = None
        self.active_vertex = None

        self.viewer.setCursor(QtCore.Qt.ArrowCursor)
        self.viewer.update()