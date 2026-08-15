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
from ET_core.ET_heatmap import EStretchHeatMapCalculator


class EUVDrawer(EDrawableObjectController):
    """
    Draws and controls cached UV preview data.

    Responsibilities:
    - draw cached UV shells / faces / vertices
    - central UV selection behavior
    - central UV hover behavior
    - central UV drag behavior
    - preview fitting / rotating / unwrap / gridify operations
    """

    MODE_SHELL = "shell"
    MODE_FACE = "face"
    MODE_VERTEX = "vertex"

    KIND_SHELL = "uv_shell"
    KIND_FACE = "uv_face"
    KIND_VERTEX = "uv_vertex"

    FIT_MODE_STRETCH_FILL = "stretch_fill"
    FIT_MODE_UNIFORM_INSIDE = "uniform_inside"
    FIT_MODE_UNIFORM_FILL = "uniform_fill"
    FIT_MODE_BEST_90_INSIDE = "best_90_inside"

    VALID_MODES = (
        MODE_SHELL,
        MODE_FACE,
        MODE_VERTEX
    )

    VALID_FIT_MODES = (
        FIT_MODE_STRETCH_FILL,
        FIT_MODE_UNIFORM_INSIDE,
        FIT_MODE_UNIFORM_FILL,
        FIT_MODE_BEST_90_INSIDE
    )

    # -----------------------------------------------------
    # Init
    # -----------------------------------------------------

    def __init__(self, viewer):
        super(EUVDrawer, self).__init__(
            viewer,
            drawable_kind="uv"
        )

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

        self.selection_mode = self.MODE_SHELL

        self.hover_shell = None
        self.active_shell = None

        self.hover_face = None
        self.active_face = None

        self.hover_vertex = None
        self.active_vertex = None

        self.is_dragging_shell = False
        self.is_dragging_face = False
        self.is_dragging_vertex = False

        self.drag_mode = None
        self.drag_start_positions = None
        self.drag_start_shell_bounds = None

        self.shell_hit_pixel_distance = 8.0
        self.vertex_hit_pixel_distance = 8.0

        self.stretch_heatmap_enabled = False
        self.stretch_heatmap_mode = "severity"
        self.stretch_heatmap_calculator = EStretchHeatMapCalculator()
    # -----------------------------------------------------
    # Cache
    # -----------------------------------------------------

    def get_cache(self):
        return self.viewer.uv_cache

    def has_cache(self):
        cache = self.get_cache()
        return bool(cache and cache.has_data())

    # -----------------------------------------------------
    # Mode / kind / state mapping
    # -----------------------------------------------------

    def kind_for_mode(self, mode):
        if mode == self.MODE_SHELL:
            return self.KIND_SHELL

        if mode == self.MODE_FACE:
            return self.KIND_FACE

        if mode == self.MODE_VERTEX:
            return self.KIND_VERTEX

        return None

    def mode_for_kind(self, kind):
        if kind == self.KIND_SHELL:
            return self.MODE_SHELL

        if kind == self.KIND_FACE:
            return self.MODE_FACE

        if kind == self.KIND_VERTEX:
            return self.MODE_VERTEX

        return None

    def set_selection_mode(self, mode):
        if mode not in self.VALID_MODES:
            return

        self.selection_mode = mode
        self.clear_uv_state()
        self.viewer.setCursor(QtCore.Qt.ArrowCursor)
        self.viewer.update()

    def clear_uv_state(self):
        self.hover_shell = None
        self.active_shell = None

        self.hover_face = None
        self.active_face = None

        self.hover_vertex = None
        self.active_vertex = None

        self.clear_hover_object()
        self.clear_active_object()

    def clear_other_mode_state(self, mode):
        if mode != self.MODE_SHELL:
            self.hover_shell = None
            self.active_shell = None

        if mode != self.MODE_FACE:
            self.hover_face = None
            self.active_face = None

        if mode != self.MODE_VERTEX:
            self.hover_vertex = None
            self.active_vertex = None

    def get_hover_ref(self, mode):
        if mode == self.MODE_SHELL:
            return self.hover_shell

        if mode == self.MODE_FACE:
            return self.hover_face

        if mode == self.MODE_VERTEX:
            return self.hover_vertex

        return None

    def get_active_ref(self, mode):
        if mode == self.MODE_SHELL:
            return self.active_shell

        if mode == self.MODE_FACE:
            return self.active_face

        if mode == self.MODE_VERTEX:
            return self.active_vertex

        return None

    def set_hover_ref(self, mode, ref):
        if mode == self.MODE_SHELL:
            self.hover_shell = ref

        elif mode == self.MODE_FACE:
            self.hover_face = ref

        elif mode == self.MODE_VERTEX:
            self.hover_vertex = ref

        self.set_hover_object(ref)

    def set_active_ref(self, mode, ref):
        if mode == self.MODE_SHELL:
            self.active_shell = ref

        elif mode == self.MODE_FACE:
            self.active_face = ref

        elif mode == self.MODE_VERTEX:
            self.active_vertex = ref

        self.set_active_object(ref)

    def set_active_and_hover_ref(self, mode, ref):
        self.clear_other_mode_state(mode)
        self.set_active_ref(mode, ref)
        self.set_hover_ref(mode, ref)

    def clear_ref_if_matches(self, mode, ref):
        if mode == self.MODE_SHELL:
            if self.active_shell == ref:
                self.active_shell = None

            if self.hover_shell == ref:
                self.hover_shell = None

        elif mode == self.MODE_FACE:
            if self.active_face == ref:
                self.active_face = None

            if self.hover_face == ref:
                self.hover_face = None

        elif mode == self.MODE_VERTEX:
            if self.active_vertex == ref:
                self.active_vertex = None

            if self.hover_vertex == ref:
                self.hover_vertex = None

        if self.active_object == ref:
            self.clear_active_object()

        if self.hover_object == ref:
            self.clear_hover_object()

    # -----------------------------------------------------
    # Key / ref conversion
    # -----------------------------------------------------

    def drawable_key_for_shell(self, mesh_data, shell_data):
        return (
            self.KIND_SHELL,
            mesh_data.mesh_name,
            mesh_data.uv_set,
            shell_data.shell_id
        )

    def drawable_key_for_face(self, mesh_data, face_index):
        return (
            self.KIND_FACE,
            mesh_data.mesh_name,
            mesh_data.uv_set,
            face_index
        )

    def drawable_key_for_vertex(self, mesh_data, uv_id):
        return (
            self.KIND_VERTEX,
            mesh_data.mesh_name,
            mesh_data.uv_set,
            uv_id
        )

    def drawable_key_for_ref(self, mode, ref):
        if not ref:
            return None

        if mode == self.MODE_SHELL:
            mesh_data, shell_data = ref
            return self.drawable_key_for_shell(
                mesh_data,
                shell_data
            )

        if mode == self.MODE_FACE:
            mesh_data, face_index, face_uv_ids = ref
            return self.drawable_key_for_face(
                mesh_data,
                face_index
            )

        if mode == self.MODE_VERTEX:
            mesh_data, uv_id = ref
            return self.drawable_key_for_vertex(
                mesh_data,
                uv_id
            )

        return None

    def ref_from_drawable_key(self, key):
        if not key:
            return None

        kind = key[0]

        if kind == self.KIND_SHELL:
            mesh_data, shell_data = self.get_shell_from_drawable_key(key)

            if mesh_data and shell_data:
                return mesh_data, shell_data

        elif kind == self.KIND_FACE:
            mesh_data, face_index, face_uv_ids = self.get_face_from_drawable_key(key)

            if mesh_data and face_uv_ids:
                return mesh_data, face_index, face_uv_ids

        elif kind == self.KIND_VERTEX:
            mesh_data, uv_id = self.get_vertex_from_drawable_key(key)

            if mesh_data is not None and uv_id is not None:
                return mesh_data, uv_id

        return None

    def is_shell_ref(self, ref):
        if not ref:
            return False

        if not isinstance(ref, tuple):
            return False

        if len(ref) != 2:
            return False

        mesh_data, shell_data = ref
        return hasattr(shell_data, "shell_id")

    def is_face_ref(self, ref):
        if not ref:
            return False

        if not isinstance(ref, tuple):
            return False

        return len(ref) == 3

    def is_vertex_ref(self, ref):
        if not ref:
            return False

        if not isinstance(ref, tuple):
            return False

        if len(ref) != 2:
            return False

        mesh_data, uv_id = ref
        return not hasattr(uv_id, "shell_id")

    def mode_for_ref(self, ref):
        if self.is_shell_ref(ref):
            return self.MODE_SHELL

        if self.is_face_ref(ref):
            return self.MODE_FACE

        if self.is_vertex_ref(ref):
            return self.MODE_VERTEX

        return None

    # -----------------------------------------------------
    # Lookup from keys
    # -----------------------------------------------------

    def get_selected_shell_keys(self):
        return self.viewer.get_selected_drawables_by_type(
            self.KIND_SHELL
        )

    def get_selected_face_keys(self):
        return self.viewer.get_selected_drawables_by_type(
            self.KIND_FACE
        )

    def get_selected_vertex_keys(self):
        return self.viewer.get_selected_drawables_by_type(
            self.KIND_VERTEX
        )

    def prepare_selected_vertices_for_preview_edit(self):
        """
        Prepare selected UV vertices for an edit operation.

        If selected vertices form complete faces, split those faces into a preview
        shell and return the updated UV pairs.

        Otherwise return the selected vertices directly.
        """

        selected_keys = self.get_selected_vertex_keys()

        if not selected_keys:
            return []

        selected_by_mesh = {}

        for key in selected_keys:
            mesh_data, uv_id = self.get_vertex_from_drawable_key(key)

            if not mesh_data:
                continue

            if mesh_data not in selected_by_mesh:
                selected_by_mesh[mesh_data] = set()

            selected_by_mesh[mesh_data].add(uv_id)

        uv_pairs = []

        for mesh_data, selected_uv_ids in selected_by_mesh.items():
            prepared_pairs = ET_uv_model.prepare_vertex_uvs_for_preview_edit(
                mesh_data,
                selected_uv_ids
            )

            uv_pairs.extend(prepared_pairs)

        return uv_pairs

    def get_shell_from_drawable_key(self, key):
        if not key or key[0] != self.KIND_SHELL:
            return None, None

        _, mesh_name, uv_set, shell_id = key

        if not self.has_cache():
            return None, None

        for mesh_data in self.get_cache().meshes:
            if mesh_data.mesh_name != mesh_name:
                continue

            if mesh_data.uv_set != uv_set:
                continue

            for shell_data in mesh_data.shells:
                if shell_data.shell_id == shell_id:
                    return mesh_data, shell_data

        return None, None

    def get_face_from_drawable_key(self, key):
        if not key or key[0] != self.KIND_FACE:
            return None, None, None

        _, mesh_name, uv_set, face_index = key

        if not self.has_cache():
            return None, None, None

        for mesh_data in self.get_cache().meshes:
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

    def get_vertex_from_drawable_key(self, key):
        if not key or key[0] != self.KIND_VERTEX:
            return None, None

        _, mesh_name, uv_set, uv_id = key

        if not self.has_cache():
            return None, None

        for mesh_data in self.get_cache().meshes:
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

    # -----------------------------------------------------
    # UV data helpers
    # -----------------------------------------------------

    def ensure_preview_positions(self, mesh_data):
        if not hasattr(mesh_data, "preview_uv_positions"):
            mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)

    def get_uv_position(self, mesh_data, uv_id):
        if (
            hasattr(mesh_data, "preview_uv_positions") and
            uv_id in mesh_data.preview_uv_positions
        ):
            return mesh_data.preview_uv_positions[uv_id]

        return mesh_data.uv_positions[uv_id]

    def uv_point_to_screen(self, mesh_data, uv_id):
        u, v = self.get_uv_position(
            mesh_data,
            uv_id
        )

        return self.viewer.uv_to_screen(
            u,
            v
        )

    def iter_mesh_uv_ids(self, mesh_data):
        if hasattr(mesh_data, "preview_uv_positions"):
            return list(mesh_data.preview_uv_positions.keys())

        return list(mesh_data.uv_positions.keys())

    def get_face_index(self, mesh_data, face_uv_ids):
        for index, test_face_uv_ids in enumerate(mesh_data.faces):
            if test_face_uv_ids is face_uv_ids:
                return index

            if test_face_uv_ids == face_uv_ids:
                return index

        return -1

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

    def edge_key(self, uv_a, uv_b):
        return tuple(
            sorted(
                (
                    uv_a,
                    uv_b
                )
            )
        )

    def get_shell_boundary_edges(self, shell_data):
        edge_counts = {}

        for face_uv_ids in shell_data.faces:
            for uv_a, uv_b in self.get_face_edges(face_uv_ids):
                key = self.edge_key(
                    uv_a,
                    uv_b
                )

                edge_counts[key] = edge_counts.get(key, 0) + 1

        boundary_edges = []

        for face_uv_ids in shell_data.faces:
            for uv_a, uv_b in self.get_face_edges(face_uv_ids):
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

    def get_shell_screen_bounds(self, mesh_data, shell_data):
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
                self.uv_point_to_screen(
                    mesh_data,
                    uv_id
                )
            )

        return polygon

    # -----------------------------------------------------
    # Ref matching
    # -----------------------------------------------------

    def shell_matches(self, ref, mesh_data, shell_data):
        if not ref:
            return False

        ref_mesh_data, ref_shell_data = ref

        return (
            ref_mesh_data is mesh_data and
            ref_shell_data is shell_data
        )

    def face_ref_matches(self, ref, mesh_data, face_index):
        if not ref:
            return False

        ref_mesh_data, ref_face_index, ref_face_uv_ids = ref

        return (
            ref_mesh_data is mesh_data and
            ref_face_index == face_index
        )

    def vertex_ref_matches(self, ref, mesh_data, uv_id):
        if not ref:
            return False

        ref_mesh_data, ref_uv_id = ref

        return (
            ref_mesh_data is mesh_data and
            ref_uv_id == uv_id
        )

    # -----------------------------------------------------
    # Drawing
    # -----------------------------------------------------

    def draw_cache(self, painter, uv_cache):
        if not uv_cache:
            return

        if not uv_cache.has_data():
            return

        if self.stretch_heatmap_enabled:
            self.stretch_heatmap_calculator.compute(uv_cache)

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

            if self.stretch_heatmap_enabled:
                if self.stretch_heatmap_mode == "signed":
                    ratio = self.stretch_heatmap_calculator.get_face_density_ratio(mesh_data, face_index)
                    color = self.color_for_signed_stretch_ratio(ratio)

                else:
                    stretch = self.stretch_heatmap_calculator.get_face_stretch(mesh_data, face_index)

                    color = self.color_for_stretch_value(stretch)

            else:
                color = self.face_color

                if self.selection_mode != self.MODE_SHELL:
                    if (
                        self.face_ref_matches(self.active_face, mesh_data, face_index) or
                        self.viewer.is_drawable_selected(self.drawable_key_for_face(mesh_data, face_index))
                    ):
                        color = self.active_face_color

                    elif self.face_ref_matches(self.hover_face, mesh_data, face_index):
                        color = self.hover_face_color

            painter.setBrush(QtGui.QBrush(color))

            polygon = self.uv_polygon_for_face(mesh_data, face_uv_ids)

            if not polygon.isEmpty():
                painter.drawPolygon(polygon)

    def draw_shell_edges(self, painter, mesh_data, shell_data, is_hovered, is_active):
        painter.setPen(QtGui.QPen(self.edge_color, self.edge_width))

        painter.setBrush(QtCore.Qt.NoBrush)

        for uv_a, uv_b in shell_data.edges:
            self.draw_uv_edge(
                painter,
                mesh_data,
                uv_a,
                uv_b
            )

        if self.selection_mode == self.MODE_SHELL:
            if not is_hovered and not is_active:
                return

            color = self.active_edge_color if is_active else self.hover_edge_color
            width = self.active_edge_width if is_active else self.hover_edge_width

            painter.setPen(
                QtGui.QPen(
                    color,
                    width
                )
            )

            for uv_a, uv_b in self.get_shell_boundary_edges(shell_data):
                self.draw_uv_edge(
                    painter,
                    mesh_data,
                    uv_a,
                    uv_b
                )

            return

        if self.selection_mode == self.MODE_FACE:
            self.draw_face_edge_overlays(
                painter,
                mesh_data,
                shell_data
            )

    def draw_face_edge_overlays(self, painter, mesh_data, shell_data):
        for face_uv_ids in shell_data.faces:
            face_index = self.get_face_index(
                mesh_data,
                face_uv_ids
            )

            is_hovered = self.face_ref_matches(
                self.hover_face,
                mesh_data,
                face_index
            )

            is_active = self.face_ref_matches(
                self.active_face,
                mesh_data,
                face_index
            )

            is_selected = self.viewer.is_drawable_selected(
                self.drawable_key_for_face(
                    mesh_data,
                    face_index
                )
            )

            if not is_hovered and not is_active and not is_selected:
                continue

            color = self.active_edge_color if is_active or is_selected else self.hover_edge_color
            width = self.active_edge_width if is_active or is_selected else self.hover_edge_width

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
        painter.setPen(QtCore.Qt.NoPen)
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

        if self.selection_mode == self.MODE_VERTEX:
            self.draw_vertex_mode_vertex_overlays(
                painter,
                mesh_data,
                shell_data
            )
            return

        if self.selection_mode == self.MODE_SHELL:
            self.draw_shell_mode_vertex_overlays(
                painter,
                mesh_data,
                shell_data,
                is_hovered,
                is_active
            )
            return

        if self.selection_mode == self.MODE_FACE:
            self.draw_face_mode_vertex_overlays(
                painter,
                mesh_data,
                shell_data
            )

    def draw_vertex_mode_vertex_overlays(self, painter, mesh_data, shell_data):
        for uv_id in shell_data.uv_ids:
            is_hovered = self.vertex_ref_matches(
                self.hover_vertex,
                mesh_data,
                uv_id
            )

            is_active = self.vertex_ref_matches(
                self.active_vertex,
                mesh_data,
                uv_id
            )

            is_selected = self.viewer.is_drawable_selected(
                self.drawable_key_for_vertex(
                    mesh_data,
                    uv_id
                )
            )

            if not is_hovered and not is_active and not is_selected:
                continue

            color = self.active_vertex_color if is_active or is_selected else self.hover_vertex_color
            radius = self.active_vertex_radius if is_active or is_selected else self.hover_vertex_radius

            painter.setBrush(
                QtGui.QBrush(color)
            )

            self.draw_uv_vertex(
                painter,
                mesh_data,
                uv_id,
                radius
            )

    def draw_shell_mode_vertex_overlays(self, painter, mesh_data, shell_data, is_hovered, is_active):
        if not is_hovered and not is_active:
            return

        color = self.active_vertex_color if is_active else self.hover_vertex_color
        radius = self.active_vertex_radius if is_active else self.hover_vertex_radius

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

    def draw_face_mode_vertex_overlays(self, painter, mesh_data, shell_data):
        highlighted = {}

        for face_uv_ids in shell_data.faces:
            face_index = self.get_face_index(
                mesh_data,
                face_uv_ids
            )

            is_hovered = self.face_ref_matches(
                self.hover_face,
                mesh_data,
                face_index
            )

            is_active = self.face_ref_matches(
                self.active_face,
                mesh_data,
                face_index
            )

            is_selected = self.viewer.is_drawable_selected(
                self.drawable_key_for_face(
                    mesh_data,
                    face_index
                )
            )

            if is_active or is_selected:
                for uv_id in face_uv_ids:
                    highlighted[uv_id] = "active"

            elif is_hovered:
                for uv_id in face_uv_ids:
                    highlighted.setdefault(
                        uv_id,
                        "hover"
                    )

        for uv_id, state in highlighted.items():
            color = self.active_vertex_color if state == "active" else self.hover_vertex_color
            radius = self.active_vertex_radius if state == "active" else self.hover_vertex_radius

            painter.setBrush(
                QtGui.QBrush(color)
            )

            self.draw_uv_vertex(
                painter,
                mesh_data,
                uv_id,
                radius
            )

    def draw_uv_edge(self, painter, mesh_data, uv_a, uv_b):
        painter.drawLine(
            self.uv_point_to_screen(mesh_data, uv_a),
            self.uv_point_to_screen(mesh_data, uv_b)
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


    def set_stretch_heatmap_enabled(self, enabled):
        self.stretch_heatmap_enabled = bool(enabled)
        self.viewer.update()

    def set_stretch_heatmap_mode(self, mode):
        if mode not in ("severity", "signed"):
            return

        self.stretch_heatmap_mode = mode
        self.stretch_heatmap_enabled = True
        self.viewer.update()


    def set_stretch_heatmap_enabled(self, enabled):
        self.stretch_heatmap_enabled = bool(enabled)
        self.viewer.update()


    def toggle_stretch_heatmap(self):
        self.stretch_heatmap_enabled = not self.stretch_heatmap_enabled
        self.viewer.update()

    def toggle_stretch_heatmap(self):
        self.stretch_heatmap_enabled = not self.stretch_heatmap_enabled
        self.viewer.update()


    def lerp_color(self, color_a, color_b, t):
        t = max(
            0.0,
            min(
                1.0,
                float(t)
            )
        )

        return QtGui.QColor(
            int(color_a.red() + (color_b.red() - color_a.red()) * t),
            int(color_a.green() + (color_b.green() - color_a.green()) * t),
            int(color_a.blue() + (color_b.blue() - color_a.blue()) * t),
            int(color_a.alpha() + (color_b.alpha() - color_a.alpha()) * t)
        )


    def color_for_stretch_value(self, stretch):
        """
        Convert stretch grade into a face fill color.
        """

        green = QtGui.QColor(80, 255, 120, 95)
        yellow = QtGui.QColor(255, 220, 60, 115)
        red = QtGui.QColor(255, 70, 40, 135)

        if stretch <= 1.0:
            return green

        if stretch <= 1.5:
            t = (stretch - 1.0) / 0.5

            return self.lerp_color(
                green,
                yellow,
                t
            )

        t = min(
            1.0,
            (stretch - 1.5) / 1.5
        )

        return self.lerp_color(
            yellow,
            red,
            t
        )

    def color_for_signed_stretch_ratio(self, ratio):
        """
        Signed stretch color.

        ratio == 1.0:
            white, neutral

        ratio > 1.0:
            red, UV density is larger than median

        ratio < 1.0:
            blue, UV density is smaller than median
        """

        white = QtGui.QColor(245, 245, 245, 115)
        red = QtGui.QColor(255, 55, 45, 150)
        blue = QtGui.QColor(45, 130, 255, 150)

        if ratio <= 0.000000001:
            return blue

        # Symmetric response:
        # ratio 2.0 and ratio 0.5 should have similar intensity.
        if ratio >= 1.0:
            t = min(
                1.0,
                (ratio - 1.0) / 2.0
            )

            return self.lerp_color(
                white,
                red,
                t
            )

        inverse_ratio = 1.0 / ratio

        t = min(
            1.0,
            (inverse_ratio - 1.0) / 2.0
        )

        return self.lerp_color(
            white,
            blue,
            t
        )

    # -----------------------------------------------------
    # Hit testing
    # -----------------------------------------------------

    def hit_test_current_mode(self, pos):
        return self.hit_test_mode(
            self.selection_mode,
            pos
        )

    def hit_test_mode(self, mode, pos):
        if mode == self.MODE_SHELL:
            mesh_data, shell_data = self.hit_test_shell(pos)

            if mesh_data and shell_data:
                return mesh_data, shell_data

            return None

        if mode == self.MODE_FACE:
            mesh_data, face_index, face_uv_ids = self.hit_test_face(pos)

            if mesh_data and face_uv_ids:
                return mesh_data, face_index, face_uv_ids

            return None

        if mode == self.MODE_VERTEX:
            mesh_data, uv_id = self.hit_test_vertex(pos)

            if mesh_data is not None and uv_id is not None:
                return mesh_data, uv_id

            return None

        return None

    def hit_test_shell(self, pos):
        if not self.has_cache():
            return None, None

        threshold_sq = self.shell_hit_pixel_distance * self.shell_hit_pixel_distance

        for mesh_data in reversed(self.get_cache().meshes):
            for shell_data in reversed(mesh_data.shells):
                for uv_a, uv_b in shell_data.edges:
                    distance_sq = self.distance_sq_to_segment(
                        pos,
                        self.uv_point_to_screen(mesh_data, uv_a),
                        self.uv_point_to_screen(mesh_data, uv_b)
                    )

                    if distance_sq <= threshold_sq:
                        return mesh_data, shell_data

        return None, None

    def hit_test_face(self, pos):
        if not self.has_cache():
            return None, None, None

        for mesh_data in reversed(self.get_cache().meshes):
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

    def hit_test_vertex(self, pos):
        if not self.has_cache():
            return None, None

        threshold_sq = self.vertex_hit_pixel_distance * self.vertex_hit_pixel_distance

        for mesh_data in reversed(self.get_cache().meshes):
            for uv_id in reversed(self.iter_mesh_uv_ids(mesh_data)):
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

    # -----------------------------------------------------
    # Selection helpers
    # -----------------------------------------------------

    def select_ref(self, mode, ref, additive=False, subtractive=False):
        key = self.drawable_key_for_ref(
            mode,
            ref
        )

        if not key:
            return False

        if subtractive:
            self.viewer.deselect_drawable_key(key)
            self.clear_ref_if_matches(
                mode,
                ref
            )
            self.viewer.update()
            return True

        already_selected = self.viewer.is_drawable_selected(key)

        if not already_selected or additive:
            self.viewer.select_drawable(
                key,
                clear_previous=not additive
            )

        self.set_active_and_hover_ref(
            mode,
            ref
        )

        return True

    def select_refs_in_rect(self, mode, rect, additive=False, subtractive=False):
        if not self.has_cache():
            return False

        if rect.isNull() or rect.width() < 2.0 or rect.height() < 2.0:
            return False

        if not additive and not subtractive:
            self.viewer.clear_drawable_selection()

        selected_count = 0
        last_ref = None

        for ref in self.iter_refs_intersecting_rect(mode, rect):
            key = self.drawable_key_for_ref(
                mode,
                ref
            )

            if not key:
                continue

            if subtractive:
                self.viewer.deselect_drawable_key(key)
                self.clear_ref_if_matches(
                    mode,
                    ref
                )
            else:
                self.viewer.select_drawable(
                    key,
                    clear_previous=False
                )
                last_ref = ref

            selected_count += 1

        if last_ref and not subtractive:
            self.set_active_and_hover_ref(
                mode,
                last_ref
            )

        print(
            "[eTrim] Rect-selected {}: {}".format(
                mode,
                selected_count
            )
        )

        self.viewer.update()
        return selected_count > 0

    def iter_refs_intersecting_rect(self, mode, rect):
        if mode == self.MODE_SHELL:
            for mesh_data in self.get_cache().meshes:
                for shell_data in mesh_data.shells:
                    shell_rect = self.get_shell_screen_bounds(
                        mesh_data,
                        shell_data
                    )

                    if shell_rect.isNull():
                        continue

                    if shell_rect.intersects(rect):
                        yield (
                            mesh_data,
                            shell_data
                        )

        elif mode == self.MODE_FACE:
            for mesh_data in self.get_cache().meshes:
                for face_index, face_uv_ids in enumerate(mesh_data.faces):
                    polygon = self.uv_polygon_for_face(
                        mesh_data,
                        face_uv_ids
                    )

                    if polygon.isEmpty():
                        continue

                    if polygon.boundingRect().intersects(rect):
                        yield (
                            mesh_data,
                            face_index,
                            face_uv_ids
                        )

        elif mode == self.MODE_VERTEX:
            for mesh_data in self.get_cache().meshes:
                for uv_id in self.iter_mesh_uv_ids(mesh_data):
                    point = self.uv_point_to_screen(
                        mesh_data,
                        uv_id
                    )

                    if rect.contains(point):
                        yield (
                            mesh_data,
                            uv_id
                        )

    def select_shells_in_rect(self, rect, additive=False, subtractive=False):
        return self.select_refs_in_rect(
            self.MODE_SHELL,
            rect,
            additive=additive,
            subtractive=subtractive
        )

    def select_faces_in_rect(self, rect, additive=False, subtractive=False):
        return self.select_refs_in_rect(
            self.MODE_FACE,
            rect,
            additive=additive,
            subtractive=subtractive
        )

    def select_vertices_in_rect(self, rect, additive=False, subtractive=False):
        return self.select_refs_in_rect(
            self.MODE_VERTEX,
            rect,
            additive=additive,
            subtractive=subtractive
        )

    def get_selected_face_indices_by_mesh(self):
        result = {}

        for key in self.get_selected_face_keys():
            mesh_data, face_index, face_uv_ids = self.get_face_from_drawable_key(key)

            if not mesh_data:
                continue

            result.setdefault(
                mesh_data,
                set()
            ).add(face_index)

        return result

    # -----------------------------------------------------
    # UV pair helpers
    # -----------------------------------------------------

    def get_uv_pairs_from_ref(self, mode, ref):
        if not ref:
            return []

        if mode == self.MODE_SHELL:
            mesh_data, shell_data = ref
            return self.get_uv_pairs_from_shell(
                mesh_data,
                shell_data
            )

        if mode == self.MODE_FACE:
            mesh_data, face_index, face_uv_ids = ref
            return [
                (
                    mesh_data,
                    uv_id
                )
                for uv_id in face_uv_ids
            ]

        if mode == self.MODE_VERTEX:
            mesh_data, uv_id = ref
            return [
                (
                    mesh_data,
                    uv_id
                )
            ]

        return []

    def get_uv_pairs_from_selected_drawables(self, drawable_type):
        uv_pairs = []
        seen = set()

        for key in self.viewer.get_selected_drawables_by_type(drawable_type):
            mode = self.mode_for_kind(key[0])
            ref = self.ref_from_drawable_key(key)

            if not ref:
                continue

            for mesh_data, uv_id in self.get_uv_pairs_from_ref(mode, ref):
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

    def get_uv_pairs_from_selected_shells(self):
        return self.get_uv_pairs_from_selected_drawables(
            self.KIND_SHELL
        )

    def get_uv_pairs_from_selected_faces(self):
        return self.get_uv_pairs_from_selected_drawables(
            self.KIND_FACE
        )

    def get_uv_pairs_from_selected_vertices(self):
        return self.get_uv_pairs_from_selected_drawables(
            self.KIND_VERTEX
        )

    def get_uv_pairs_for_shell_context(self, shell_ref):
        if not shell_ref:
            return []

        key = self.drawable_key_for_ref(
            self.MODE_SHELL,
            shell_ref
        )

        if self.viewer.is_drawable_selected(key):
            return self.get_uv_pairs_from_selected_shells()

        return self.get_uv_pairs_from_ref(
            self.MODE_SHELL,
            shell_ref
        )

    def get_uv_pair_bounds(self, uv_pairs):
        positions = {}

        for index, pair in enumerate(uv_pairs):
            mesh_data, uv_id = pair
            positions[index] = self.get_uv_position(
                mesh_data,
                uv_id
            )

        return self.get_uv_bounds_from_positions(positions)

    # -----------------------------------------------------
    # Drag
    # -----------------------------------------------------

    def any_dragging(self):
        return (
            self.is_dragging_shell or
            self.is_dragging_face or
            self.is_dragging_vertex
        )

    def set_drag_flag(self, mode, value):
        value = bool(value)

        if mode == self.MODE_SHELL:
            self.is_dragging_shell = value

        elif mode == self.MODE_FACE:
            self.is_dragging_face = value

        elif mode == self.MODE_VERTEX:
            self.is_dragging_vertex = value

        if value:
            self.drag_mode = mode
        elif self.drag_mode == mode:
            self.drag_mode = None

    def begin_drag_ref(self, mode, ref, pos):
        if not ref:
            return

        key = self.drawable_key_for_ref(
            mode,
            ref
        )

        uv_pairs = []

        if key and self.viewer.is_drawable_selected(key):
            uv_pairs = self.get_uv_pairs_from_selected_drawables(
                key[0]
            )
        else:
            uv_pairs = self.get_uv_pairs_from_ref(
                mode,
                ref
            )

        self.set_drag_flag(
            mode,
            True
        )

        self.set_active_and_hover_ref(
            mode,
            ref
        )

        self.begin_drag_object(
            ref,
            pos
        )

        self.build_drag_start_from_uv_pairs(
            uv_pairs
        )

        self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
        self.viewer.update()

    def build_drag_start_from_uv_pairs(self, uv_pairs):
        self.drag_start_positions = {}

        for mesh_data, uv_id in uv_pairs:
            self.ensure_preview_positions(mesh_data)

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

    def update_drag_ref(self, pos):
        if not self.drag_start_positions:
            return

        du, dv = self.get_drag_delta_uv(pos)

        for mesh_data, uv_id, start_pos in self.drag_start_positions.values():
            original_u, original_v = start_pos

            mesh_data.preview_uv_positions[uv_id] = (
                original_u + du,
                original_v + dv
            )

        self.viewer.update()

    def end_drag_ref(self):
        mode = self.drag_mode

        if not mode:
            return

        hover_ref = self.get_hover_ref(mode)

        self.set_drag_flag(
            mode,
            False
        )

        self.drag_start_positions = None
        self.drag_start_shell_bounds = None
        self.end_drag_object()

        if hover_ref:
            self.viewer.setCursor(QtCore.Qt.SizeAllCursor)
        else:
            self.viewer.setCursor(QtCore.Qt.ArrowCursor)

        self.viewer.update()

    def begin_drag_shell(self, mesh_data, shell_data, pos):
        self.begin_drag_ref(
            self.MODE_SHELL,
            (
                mesh_data,
                shell_data
            ),
            pos
        )

    def begin_drag_face(self, mesh_data, face_index, face_uv_ids, pos):
        self.begin_drag_ref(
            self.MODE_FACE,
            (
                mesh_data,
                face_index,
                face_uv_ids
            ),
            pos
        )

    def update_drag_shell(self, pos):
        self.update_drag_ref(pos)

    def update_drag_face(self, pos):
        self.update_drag_ref(pos)

    def update_drag_vertex(self, pos):
        self.update_drag_ref(pos)

    def end_drag_shell(self):
        self.end_drag_ref()

    def end_drag_face(self):
        self.end_drag_ref()

    def end_drag_vertex(self):
        self.end_drag_ref()

    # -----------------------------------------------------
    # Fit
    # -----------------------------------------------------

    def detach_selected_faces(self):
        """
        Explicitly detach currently selected faces into their own preview shell.

        This is only intended for Face mode.
        """

        selected_by_mesh = self.get_selected_face_indices_by_mesh()

        if not selected_by_mesh:
            print("[eTrim] No selected faces to detach.")
            return False

        detached_count = 0

        for mesh_data, face_indices in selected_by_mesh.items():
            if ET_uv_model.split_faces_to_preview_shell(
                mesh_data,
                face_indices,
                duplicate_all=True
            ):
                detached_count += len(face_indices)

        if detached_count:
            print("[eTrim] Detached selected faces:")
            print("        faces:", detached_count)

            self.viewer.update()
            return True

        print("[eTrim] Selected faces were already detached or could not be detached.")
        return False


    def get_complete_face_indices_from_selected_vertices_by_mesh(self):
        """
        Return complete face indices from the current vertex selection.

        A face is complete only if all of its preview UV ids are selected.
        """

        selected_by_mesh = {}

        for key in self.get_selected_vertex_keys():
            mesh_data, uv_id = self.get_vertex_from_drawable_key(key)

            if not mesh_data:
                continue

            if mesh_data not in selected_by_mesh:
                selected_by_mesh[mesh_data] = set()

            selected_by_mesh[mesh_data].add(uv_id)

        result = {}

        for mesh_data, selected_uv_ids in selected_by_mesh.items():
            face_indices = ET_uv_model.get_complete_face_indices_from_uv_ids(
                mesh_data,
                selected_uv_ids
            )

            if face_indices:
                result[mesh_data] = face_indices

        return result


    def detach_complete_faces_from_vertex_selection(self):
        """
        Explicitly detach complete faces described by selected vertices.

        This is only intended for Vertex mode.

        Example:
            If all four UV vertices of a quad face are selected,
            that face can be detached.

            If only two vertices of a face are selected,
            that face is not detached.
        """

        selected_by_mesh = self.get_complete_face_indices_from_selected_vertices_by_mesh()

        if not selected_by_mesh:
            print("[eTrim] No complete faces found from selected vertices.")
            return False

        detached_count = 0

        for mesh_data, face_indices in selected_by_mesh.items():
            if ET_uv_model.split_faces_to_preview_shell(
                mesh_data,
                face_indices,
                duplicate_all=True
            ):
                detached_count += len(face_indices)

        if detached_count:
            print("[eTrim] Detached complete faces from vertex selection:")
            print("        faces:", detached_count)

            self.viewer.update()
            return True

        print("[eTrim] Vertex-selected complete faces were already detached or could not be detached.")
        return False

    def normalize_fit_mode(self, fit_mode):
        if fit_mode in self.VALID_FIT_MODES:
            return fit_mode

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

    def fit_uv_pairs_to_box(self, uv_pairs, box):
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

        if fit_mode == self.FIT_MODE_STRETCH_FILL:
            return self.fit_uv_pairs_stretch(
                uv_pairs,
                src_u_min,
                src_v_min,
                src_width,
                src_height,
                dst_u_min,
                dst_v_min,
                dst_width,
                dst_height
            )

        return self.fit_uv_pairs_uniform(
            uv_pairs,
            fit_mode,
            src_u_min,
            src_v_min,
            src_u_max,
            src_v_max,
            src_width,
            src_height,
            dst_u_min,
            dst_v_min,
            dst_u_max,
            dst_v_max,
            dst_width,
            dst_height
        )

    def fit_uv_pairs_stretch(self, uv_pairs, src_u_min, src_v_min, src_width, src_height,
                             dst_u_min, dst_v_min, dst_width, dst_height):
        for mesh_data, uv_id in uv_pairs:
            self.ensure_preview_positions(mesh_data)

            u, v = self.get_uv_position(
                mesh_data,
                uv_id
            )

            normalized_u = (u - src_u_min) / src_width
            normalized_v = (v - src_v_min) / src_height

            mesh_data.preview_uv_positions[uv_id] = (
                dst_u_min + normalized_u * dst_width,
                dst_v_min + normalized_v * dst_height
            )

        self.viewer.update()
        return True

    def fit_uv_pairs_uniform(self, uv_pairs, fit_mode,
                             src_u_min, src_v_min, src_u_max, src_v_max,
                             src_width, src_height,
                             dst_u_min, dst_v_min, dst_u_max, dst_v_max,
                             dst_width, dst_height):
        src_center_u = (src_u_min + src_u_max) * 0.5
        src_center_v = (src_v_min + src_v_max) * 0.5
        dst_center_u = (dst_u_min + dst_u_max) * 0.5
        dst_center_v = (dst_v_min + dst_v_max) * 0.5

        rotate_90 = False

        if fit_mode == self.FIT_MODE_UNIFORM_FILL:
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

            rotate_90 = scale_90 > scale_0
            scale = scale_90 if rotate_90 else scale_0

        else:
            scale = min(
                dst_width / src_width,
                dst_height / src_height
            )

        for mesh_data, uv_id in uv_pairs:
            self.ensure_preview_positions(mesh_data)

            u, v = self.get_uv_position(
                mesh_data,
                uv_id
            )

            local_u = u - src_center_u
            local_v = v - src_center_v

            if rotate_90:
                local_u, local_v = -local_v, local_u

            mesh_data.preview_uv_positions[uv_id] = (
                dst_center_u + local_u * scale,
                dst_center_v + local_v * scale
            )

        self.viewer.update()
        return True

    def fit_shell_to_box(self, mesh_data, shell_data, box):
        if not mesh_data or not shell_data or not box:
            return False

        result = self.fit_uv_pairs_to_box(
            self.get_uv_pairs_from_shell(
                mesh_data,
                shell_data
            ),
            box
        )

        if result:
            self.set_active_and_hover_ref(
                self.MODE_SHELL,
                (
                    mesh_data,
                    shell_data
                )
            )

        return result

    def fit_active_shell_to_box(self, box):
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

        If the selected vertices form complete faces, those faces are first split
        into their own preview shell, matching face-edit behavior.
        """

        if not box:
            return False

        uv_pairs = self.prepare_selected_vertices_for_preview_edit()

        if not uv_pairs:
            return False

        result = self.fit_uv_pairs_to_box(
            uv_pairs,
            box
        )

        if result:
            print("[eTrim] Fit selected UV vertices into box:", box.name)

        return result

    def fit_selected_shells_to_box(self, box):
        return self.fit_selected_kind_to_box(
            self.KIND_SHELL,
            box,
            "shells"
        )

    def fit_selected_kind_to_box(self, kind, box, label):
        if not box:
            return False

        uv_pairs = self.get_uv_pairs_from_selected_drawables(kind)

        if not uv_pairs:
            return False

        result = self.fit_uv_pairs_to_box(
            uv_pairs,
            box
        )

        if result:
            print(
                "[eTrim] Fit selected UV {} into box: {}".format(
                    label,
                    box.name
                )
            )

        return result

    def fit_each_selected_shell_to_box(self, box):
        if not box:
            return False

        fitted_count = 0

        for key in self.get_selected_shell_keys():
            mesh_data, shell_data = self.get_shell_from_drawable_key(key)

            if not mesh_data or not shell_data:
                continue

            if self.fit_uv_pairs_to_box(
                self.get_uv_pairs_from_shell(
                    mesh_data,
                    shell_data
                ),
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

    def fit_selected_faces_to_box(self, box):
        if not box:
            return False

        selected_by_mesh = self.get_selected_face_indices_by_mesh()

        if not selected_by_mesh:
            return False

        for mesh_data, face_indices in selected_by_mesh.items():
            ET_uv_model.split_faces_to_preview_shell(
                mesh_data,
                face_indices
            )

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
        if not uv_cache or not uv_cache.has_data():
            return False

        if not box:
            return False

        uv_pairs = []

        for mesh_data in uv_cache.meshes:
            self.ensure_preview_positions(mesh_data)

            for uv_id in mesh_data.preview_uv_positions.keys():
                uv_pairs.append(
                    (
                        mesh_data,
                        uv_id
                    )
                )

        result = self.fit_uv_pairs_to_box(
            uv_pairs,
            box
        )

        if result:
            for mesh_data in uv_cache.meshes:
                if mesh_data.shells:
                    self.set_active_and_hover_ref(
                        self.MODE_SHELL,
                        (
                            mesh_data,
                            mesh_data.shells[0]
                        )
                    )
                    break

        return result

    # -----------------------------------------------------
    # Rotation
    # -----------------------------------------------------

    def rotate_uv_pairs(self, uv_pairs, degrees):
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
            self.ensure_preview_positions(mesh_data)

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
        if not self.is_shell_ref(shell_ref):
            return False

        uv_pairs = self.get_uv_pairs_for_shell_context(shell_ref)

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
        return self.rotate_shell_context(
            shell_ref,
            90.0
        )

    def rotate_shell_arbitrary(self, shell_ref):
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

    def build_context_menu(self, uv_ref):
        menu = super(EUVDrawer, self).build_context_menu(uv_ref)

        menu.addSeparator()

        unwrap_selected_action = menu.addAction("Native Unwrap Selected UVs")
        unwrap_selected_action.triggered.connect(self.native_unwrap_selected_uvs)

        gridify_selected_action = menu.addAction("Gridify Selected UVs")
        gridify_selected_action.triggered.connect(self.gridify_selected_uvs)

        unwrap_gridify_action = menu.addAction("Native Unwrap + Gridify")
        unwrap_gridify_action.triggered.connect(self.native_unwrap_and_gridify_selected_uvs)

        menu.addSeparator()

        heatmap_menu = menu.addMenu("Stretch Heatmap")

        heatmap_enabled_action = heatmap_menu.addAction("Enabled")
        heatmap_enabled_action.setCheckable(True)
        heatmap_enabled_action.setChecked(self.stretch_heatmap_enabled)
        heatmap_enabled_action.triggered.connect(self.toggle_stretch_heatmap)

        heatmap_menu.addSeparator()

        severity_action = heatmap_menu.addAction("Severity: Green / Yellow / Red")
        severity_action.setCheckable(True)
        severity_action.setChecked(self.stretch_heatmap_mode == "severity")
        severity_action.triggered.connect(lambda checked=False: self.set_stretch_heatmap_mode("severity"))

        signed_action = heatmap_menu.addAction("Signed: Blue / White / Red")
        signed_action.setCheckable(True)
        signed_action.setChecked(self.stretch_heatmap_mode == "signed")
        signed_action.triggered.connect(lambda checked=False: self.set_stretch_heatmap_mode("signed"))

        if self.selection_mode == self.MODE_FACE:
            menu.addSeparator()

            detach_faces_action = menu.addAction("Detach Selected Faces")
            detach_faces_action.triggered.connect(self.detach_selected_faces)

        elif self.selection_mode == self.MODE_VERTEX:
            menu.addSeparator()

            detach_vertex_faces_action = menu.addAction("Detach Complete Faces From Vertex Selection")
            detach_vertex_faces_action.triggered.connect(self.detach_complete_faces_from_vertex_selection)

        if self.is_shell_ref(uv_ref):
            menu.addSeparator()

            fit_inside_selected_box_action = menu.addAction("Fit Inside Selected Box")
            fit_inside_selected_box_action.triggered.connect(lambda: self.fit_shell_inside_selected_box(uv_ref))

            menu.addSeparator()

            rotate_90_action = menu.addAction("Rotate 90 Clockwise")
            rotate_90_action.triggered.connect(lambda: self.rotate_shell_clockwise_90(uv_ref))

            rotate_custom_action = menu.addAction("Rotate...")
            rotate_custom_action.triggered.connect(lambda: self.rotate_shell_arbitrary(uv_ref))

        return menu

    def delete_drawable(self, uv_ref):
        mode = self.mode_for_ref(uv_ref)

        if not mode:
            print("[eTrim] Delete UV drawable requested. Unknown ref:", uv_ref)
            return

        key = self.drawable_key_for_ref(
            mode,
            uv_ref
        )

        print("[eTrim] Delete UV drawable requested. Not wired to Maya deletion:", uv_ref)

        if key:
            self.viewer.deselect_drawable_key(key)

        self.clear_ref_if_matches(mode, uv_ref)

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
    # Native unwrap / gridify
    # -----------------------------------------------------

    def native_unwrap_selected_uvs(self):
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
    # Mouse events
    # -----------------------------------------------------

    def mouse_move_event(self, event):
        pos = event.pos()

        if self.any_dragging():
            self.update_drag_ref(pos)
            return True

        ref = self.hit_test_current_mode(pos)
        old_hover = self.get_hover_ref(
            self.selection_mode
        )

        if ref != old_hover:
            self.set_hover_ref(
                self.selection_mode,
                ref
            )

            if ref:
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

        mode = self.selection_mode
        pos = event.pos()
        ref = self.hit_test_current_mode(pos)

        if not ref:
            return False

        key = self.drawable_key_for_ref(
            mode,
            ref
        )

        if not key:
            return False

        additive = bool(
            event.modifiers() & QtCore.Qt.ShiftModifier
        )

        subtractive = bool(
            event.modifiers() & QtCore.Qt.ControlModifier
        )

        already_selected = self.viewer.is_drawable_selected(key)

        self.set_active_and_hover_ref(
            mode,
            ref
        )

        if subtractive:
            self.viewer.deselect_drawable_key(key)
            self.clear_ref_if_matches(
                mode,
                ref
            )
            self.viewer.update()
            return True

        if not already_selected or additive:
            self.viewer.select_drawable(
                key,
                clear_previous=not additive
            )

        if additive and event.button() == QtCore.Qt.LeftButton:
            self.viewer.update()
            return True

        if event.button() == QtCore.Qt.RightButton:
            self.show_context_menu(
                event,
                ref
            )
            self.viewer.update()
            return True

        self.begin_drag_ref(
            mode,
            ref,
            pos
        )

        return True

    def mouse_release_event(self, event):
        if event.button() != QtCore.Qt.LeftButton:
            return False

        if self.any_dragging():
            self.end_drag_ref()
            return True

        return False

    def leave_event(self, event):
        if self.any_dragging():
            return

        self.clear_uv_state()
        self.viewer.setCursor(QtCore.Qt.ArrowCursor)
        self.viewer.update()

    def deselect(self):
        if self.any_dragging():
            return

        self.clear_uv_state()
        self.viewer.setCursor(QtCore.Qt.ArrowCursor)
        self.viewer.update()