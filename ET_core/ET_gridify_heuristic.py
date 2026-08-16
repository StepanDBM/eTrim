# ET_core/ET_gridify_heuristic.py

import math
from collections import defaultdict, deque

from ET_core.ET_heatmap import EStretchHeatMapCalculator


class EGridifyTopologyAnalyzer(object):
    """
    Computes face topology data used by heuristic gridify.

    Main output:
        face_depths:
            face_index -> boundary depth

        face_is_triangle:
            face_index -> bool

        face_is_quad:
            face_index -> bool
    """

    def __init__(self):
        self.face_depths_by_mesh = {}
        self.face_is_triangle_by_mesh = {}
        self.face_is_quad_by_mesh = {}

    def edge_key(self, uv_a, uv_b):
        return tuple(
            sorted(
                (
                    uv_a,
                    uv_b
                )
            )
        )

    def build_face_edge_map(self, mesh_data):
        edge_to_faces = defaultdict(list)

        for face_index, face_uv_ids in enumerate(mesh_data.faces):
            count = len(face_uv_ids)

            for index, uv_a in enumerate(face_uv_ids):
                uv_b = face_uv_ids[(index + 1) % count]

                key = self.edge_key(
                    uv_a,
                    uv_b
                )

                edge_to_faces[key].append(face_index)

        return edge_to_faces

    def build_face_neighbors(self, mesh_data):
        edge_to_faces = self.build_face_edge_map(
            mesh_data
        )

        neighbors = defaultdict(set)
        boundary_faces = set()

        for edge_key, face_indices in edge_to_faces.items():
            if len(face_indices) == 1:
                boundary_faces.add(
                    face_indices[0]
                )

            elif len(face_indices) == 2:
                face_a, face_b = face_indices

                neighbors[face_a].add(face_b)
                neighbors[face_b].add(face_a)

        return neighbors, boundary_faces

    def compute_face_depths(self, mesh_data):
        """
        Boundary depth by BFS.

        depth 0:
            face has at least one boundary edge

        depth 1:
            neighbor of boundary face

        depth N:
            N steps away from shell boundary
        """

        neighbors, boundary_faces = self.build_face_neighbors(
            mesh_data
        )

        depths = {}

        queue = deque()

        for face_index in boundary_faces:
            depths[face_index] = 0
            queue.append(face_index)

        while queue:
            face_index = queue.popleft()
            current_depth = depths[face_index]

            for neighbor_index in neighbors.get(face_index, []):
                if neighbor_index in depths:
                    continue

                depths[neighbor_index] = current_depth + 1
                queue.append(neighbor_index)

        # Disconnected or strange faces fallback.
        for face_index in range(len(mesh_data.faces)):
            if face_index not in depths:
                depths[face_index] = 0

        return depths

    def analyze_mesh(self, mesh_data):
        depths = self.compute_face_depths(
            mesh_data
        )

        triangles = {}
        quads = {}

        for face_index, face_uv_ids in enumerate(mesh_data.faces):
            count = len(face_uv_ids)

            triangles[face_index] = count == 3
            quads[face_index] = count == 4

        self.face_depths_by_mesh[id(mesh_data)] = depths
        self.face_is_triangle_by_mesh[id(mesh_data)] = triangles
        self.face_is_quad_by_mesh[id(mesh_data)] = quads

    def analyze_cache(self, uv_cache):
        self.face_depths_by_mesh = {}
        self.face_is_triangle_by_mesh = {}
        self.face_is_quad_by_mesh = {}

        if not uv_cache or not uv_cache.has_data():
            return

        for mesh_data in uv_cache.meshes:
            self.analyze_mesh(
                mesh_data
            )

    def get_depth(self, mesh_data, face_index):
        return self.face_depths_by_mesh.get(
            id(mesh_data),
            {}
        ).get(
            face_index,
            0
        )

    def is_triangle(self, mesh_data, face_index):
        return self.face_is_triangle_by_mesh.get(
            id(mesh_data),
            {}
        ).get(
            face_index,
            False
        )

    def is_quad(self, mesh_data, face_index):
        return self.face_is_quad_by_mesh.get(
            id(mesh_data),
            {}
        ).get(
            face_index,
            False
        )


class EGridifyGrade(object):
    """
    Lower is better.
    """

    def __init__(self):
        self.total = 999999.0

        self.average_stretch_error = 0.0
        self.max_stretch_error = 0.0
        self.triangle_penalty = 0.0
        self.boundary_penalty = 0.0
        self.movement_penalty = 0.0
        self.face_count = 0

    def __lt__(self, other):
        return self.total < other.total

    def __repr__(self):
        return (
            "EGridifyGrade(total={:.6f}, avgStretch={:.6f}, maxStretch={:.6f}, "
            "triPenalty={:.6f}, boundaryPenalty={:.6f}, movePenalty={:.6f}, faces={})"
        ).format(
            self.total,
            self.average_stretch_error,
            self.max_stretch_error,
            self.triangle_penalty,
            self.boundary_penalty,
            self.movement_penalty,
            self.face_count
        )

class EGridifyGradeCalculator(object):
    """
    Scores a candidate UV state.

    Grade components:
        - stretch error from heatmap density ratio
        - max stretch error
        - triangle penalty weighted by boundary depth
        - boundary sensitivity penalty
    """

    EPSILON = 0.000000001

    def __init__(self):
        self.heatmap = EStretchHeatMapCalculator()
        self.topology = EGridifyTopologyAnalyzer()

        self.reference_median_density = None
        self.reference_uv_positions = {}

        self.reference_uv_bounds_diagonal = 1.0
        self.weight_average_stretch = 1.0
        self.weight_max_stretch = 0.15
        self.weight_triangle = 0.30
        self.weight_boundary = 0.20
        self.weight_movement = 0.75


    def get_depth_weight(self, depth):
        """
        Boundary faces matter more for triangle/rim problems.

        depth 0:
            strongest penalty

        depth 1:
            still important

        depth 2+:
            gradually normal
        """

        if depth <= 0:
            return 1.0

        if depth == 1:
            return 0.65

        if depth == 2:
            return 0.35

        return 0.15

    def get_affected_faces_by_mesh_from_uv_pairs(self, uv_pairs):
        grouped_uv_ids = defaultdict(set)

        for mesh_data, uv_id in uv_pairs:
            grouped_uv_ids[mesh_data].add(uv_id)

        affected = {}

        for mesh_data, uv_ids in grouped_uv_ids.items():
            face_indices = []

            for face_index, face_uv_ids in enumerate(mesh_data.faces):
                for uv_id in face_uv_ids:
                    if uv_id in uv_ids:
                        face_indices.append(face_index)
                        break

            affected[mesh_data] = sorted(
                set(face_indices)
            )

        return affected

    def get_uv_position(self, mesh_data, uv_id):
        if (
            hasattr(mesh_data, "preview_uv_positions") and
            uv_id in mesh_data.preview_uv_positions
        ):
            return mesh_data.preview_uv_positions[uv_id]

        return mesh_data.uv_positions[uv_id]


    def set_reference_uv_positions(self, uv_pairs):
        """
        Store the baseline UV positions for movement/shape-preservation scoring.
        """

        self.reference_uv_positions = {}

        u_values = []
        v_values = []

        for mesh_data, uv_id in uv_pairs:
            position = self.get_uv_position(
                mesh_data,
                uv_id
            )

            key = (
                id(mesh_data),
                uv_id
            )

            self.reference_uv_positions[key] = position

            u_values.append(
                float(position[0])
            )

            v_values.append(
                float(position[1])
            )

        if not u_values or not v_values:
            self.reference_uv_bounds_diagonal = 1.0
            return

        width = max(u_values) - min(u_values)
        height = max(v_values) - min(v_values)

        diagonal = math.sqrt(
            width * width + height * height
        )

        self.reference_uv_bounds_diagonal = max(
            diagonal,
            self.EPSILON
        )


    def compute_movement_penalty(self, uv_pairs):
        """
        Penalize candidates that move the UV layout too far from the baseline.

        This prevents the heuristic from accepting visually destructive layouts
        only because max stretch got slightly better.
        """

        if not uv_pairs:
            return 0.0

        if not self.reference_uv_positions:
            return 0.0

        distances = []

        for mesh_data, uv_id in uv_pairs:
            key = (
                id(mesh_data),
                uv_id
            )

            if key not in self.reference_uv_positions:
                continue

            original_u, original_v = self.reference_uv_positions[key]
            current_u, current_v = self.get_uv_position(
                mesh_data,
                uv_id
            )

            du = float(current_u) - float(original_u)
            dv = float(current_v) - float(original_v)

            distance = math.sqrt(
                du * du + dv * dv
            )

            distances.append(
                distance / self.reference_uv_bounds_diagonal
            )

        if not distances:
            return 0.0

        return sum(distances) / float(len(distances))

    def compute_grade(self, uv_cache, uv_pairs=None, affected_faces_by_mesh=None):
        """
        Calculate candidate grade.

        Either uv_pairs or affected_faces_by_mesh can be passed.
        """

        grade = EGridifyGrade()

        if not uv_cache or not uv_cache.has_data():
            return grade

        self.heatmap.compute(uv_cache)

        if self.reference_median_density is None:
            self.reference_median_density = self.heatmap.median_density

        if self.reference_median_density <= self.EPSILON:
            return grade

        self.topology.analyze_cache(uv_cache)

        if affected_faces_by_mesh is None:
            affected_faces_by_mesh = self.get_affected_faces_by_mesh_from_uv_pairs(
                uv_pairs or []
            )

        errors = []
        triangle_penalty = 0.0
        boundary_penalty = 0.0
        face_count = 0

        for mesh_data, face_indices in affected_faces_by_mesh.items():
            for face_index in face_indices:
                if face_index < 0:
                    continue

                if face_index >= len(mesh_data.faces):
                    continue
                face_uv_ids = mesh_data.faces[face_index]
                uv_points = self.heatmap.get_face_uv_points(mesh_data, face_uv_ids)
                uv_area = self.heatmap.polygon_area_uv(uv_points)

                # Degenerate UV candidate handling.
                # Quads collapsing are catastrophic.
                # Triangles collapsing are bad, but common around pole/rim regions,
                # so they should penalize the candidate instead of killing it outright.
                if uv_area <= self.EPSILON:
                    depth = self.topology.get_depth(mesh_data, face_index)
                    depth_weight = self.get_depth_weight(depth)
                    is_quad = self.topology.is_quad(mesh_data, face_index)

                    # Only deep/internal quads are catastrophic.
                    # Boundary and near-boundary quads can behave like pole/rim triangles.
                    if is_quad and depth > 1:
                        grade.total = 999999.0
                        grade.average_stretch_error = 999999.0
                        grade.max_stretch_error = 999999.0
                        grade.face_count = face_count

                        print("[eTrim] Heuristic grade rejected collapsed interior quad:")
                        print("        mesh:", mesh_data.mesh_name)
                        print("        face:", face_index)
                        print("        depth:", depth)

                        return grade

                    # Boundary quads, triangles, and ngons get penalized, not nuked.
                    collapsed_error = 3.5 * depth_weight

                    errors.append(
                        collapsed_error
                    )

                    if is_quad:
                        boundary_penalty += collapsed_error
                    elif self.topology.is_triangle(mesh_data, face_index):
                        triangle_penalty += depth_weight * 2.0
                    else:
                        triangle_penalty += depth_weight

                    if depth == 0:
                        boundary_penalty += collapsed_error

                    face_count += 1

                    continue

                ratio = self.heatmap.get_face_density_ratio(
                    mesh_data,
                    face_index,
                    self.reference_median_density
                )
                ratio = max(self.EPSILON, float(ratio))
                stretch_error = abs(math.log(ratio))
                errors.append(stretch_error)
                depth = self.topology.get_depth(mesh_data, face_index)
                depth_weight = self.get_depth_weight(depth)

                if self.topology.is_triangle(mesh_data, face_index):
                    triangle_penalty += depth_weight

                if depth == 0:
                    boundary_penalty += stretch_error

                face_count += 1

        if not errors:
            return grade

        average_error = sum(errors) / float(len(errors))
        max_error = max(errors)

        movement_penalty = self.compute_movement_penalty(uv_pairs or [])

        if face_count > 0:
            triangle_penalty = triangle_penalty / float(face_count)
            boundary_penalty = boundary_penalty / float(face_count)

        grade.average_stretch_error = average_error
        grade.max_stretch_error = max_error
        grade.triangle_penalty = triangle_penalty
        grade.boundary_penalty = boundary_penalty
        grade.movement_penalty = movement_penalty
        grade.face_count = face_count

        grade.total = (
            average_error * self.weight_average_stretch +
            max_error * self.weight_max_stretch +
            triangle_penalty * self.weight_triangle +
            boundary_penalty * self.weight_boundary +
            movement_penalty * self.weight_movement
        )

        return grade

class EUVStateSnapshot(object):
    """
    Captures preview UV positions for a UV pair set.
    """

    def __init__(self, uv_pairs):
        self.positions = {}

        for mesh_data, uv_id in uv_pairs:
            if not hasattr(mesh_data, "preview_uv_positions"):
                mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)

            key = (
                id(mesh_data),
                uv_id
            )

            self.positions[key] = (
                mesh_data,
                uv_id,
                mesh_data.preview_uv_positions[uv_id]
            )

    def restore(self):
        for mesh_data, uv_id, position in self.positions.values():
            mesh_data.preview_uv_positions[uv_id] = position

    def capture_from_current(self):
        for key, value in list(self.positions.items()):
            mesh_data, uv_id, old_position = value

            if uv_id in mesh_data.preview_uv_positions:
                self.positions[key] = (
                    mesh_data,
                    uv_id,
                    mesh_data.preview_uv_positions[uv_id]
                )

class EGridifyHeuristicSession(object):
    """
    Temporary heuristic mode:

        - no variants
        - no candidate grading
        - no accept/reject
        - no restore-best loop

    It simply applies the current gridify operation N times in sequence,
    refreshes the viewport after each pass, and updates the viewer overlay.
    """

    def __init__(
        self,
        viewer,
        uv_pairs,
        gridify_function,
        iterations=20,
        affected_faces_by_mesh=None,
        variants=None
    ):
        self.viewer = viewer
        self.uv_pairs = uv_pairs
        self.gridify_function = gridify_function
        self.affected_faces_by_mesh = affected_faces_by_mesh

        if iterations is None:
            self.iterations = 20
        else:
            self.iterations = max(
                1,
                int(iterations)
            )

        self.grade_calculator = EGridifyGradeCalculator()

        self.original_state = EUVStateSnapshot(
            uv_pairs
        )

        self.best_state = EUVStateSnapshot(
            uv_pairs
        )

        self.best_grade = None

    def call_gridify_once(self):
        variant = {
            "angle_offset_degrees": 0.0,
            "u_tolerance_multiplier": 1.0,
            "v_tolerance_multiplier": 1.0,
            "swap_axes": False,
            "blend_factor": 1.0
        }

        try:
            return self.gridify_function(
                variant
            )
        except TypeError:
            return self.gridify_function()

    def refresh_viewer(self):
        if self.viewer:
            self.viewer.update()

            if hasattr(self.viewer, "repaint"):
                self.viewer.repaint()

        try:
            from PySide2 import QtWidgets
            QtWidgets.QApplication.processEvents()
        except Exception:
            try:
                from PySide6 import QtWidgets
                QtWidgets.QApplication.processEvents()
            except Exception:
                pass

        try:
            import maya.cmds as cmds
            cmds.refresh(
                force=True
            )
        except Exception:
            pass

    def begin_overlay(self):
        if not self.viewer:
            return

        if hasattr(self.viewer, "begin_gridify_overlay"):
            self.viewer.begin_gridify_overlay(
                title="Iterative Gridify",
                total_iterations=self.iterations
            )

    def update_overlay(self, iteration, status, grade=None, message=None):
        if not self.viewer:
            return

        if hasattr(self.viewer, "update_gridify_overlay"):
            self.viewer.update_gridify_overlay(
                iteration=iteration,
                total_iterations=self.iterations,
                status=status,
                grade=grade,
                message=message
            )

    def finish_overlay(self, message="Complete"):
        if not self.viewer:
            return

        if hasattr(self.viewer, "finish_gridify_overlay"):
            self.viewer.finish_gridify_overlay(
                message=message
            )

    def compute_current_grade(self, uv_cache):
        grade = self.grade_calculator.compute_grade(
            uv_cache,
            uv_pairs=self.uv_pairs,
            affected_faces_by_mesh=self.affected_faces_by_mesh
        )

        return grade

    def run(self):
        if not self.viewer:
            return False

        if not self.uv_pairs:
            print("[eTrim] Iterative gridify skipped. No UV pairs.")
            return False

        uv_cache = getattr(
            self.viewer,
            "uv_cache",
            None
        )

        if not uv_cache or not uv_cache.has_data():
            print("[eTrim] Iterative gridify skipped. No UV cache.")
            return False

        self.grade_calculator.reference_median_density = None

        self.grade_calculator.set_reference_uv_positions(
            self.uv_pairs
        )

        baseline_grade = self.compute_current_grade(
            uv_cache
        )

        print("[eTrim] Iterative gridify started.")
        print("        iterations:", self.iterations)
        print("        uv pairs:", len(self.uv_pairs))
        print("        baseline:", baseline_grade)

        self.begin_overlay()

        if baseline_grade:
            self.update_overlay(
                iteration=0,
                status="info",
                grade=baseline_grade.total,
                message="baseline"
            )

        changed = False

        self.refresh_viewer()

        for iteration in range(self.iterations):
            pass_index = iteration + 1

            result = self.call_gridify_once()

            if result:
                changed = True

                grade = self.compute_current_grade(
                    uv_cache
                )

                self.update_overlay(
                    iteration=pass_index,
                    status="correct",
                    grade=grade.total,
                    message="applied"
                )

                self.refresh_viewer()

                print("[eTrim] Iterative gridify pass complete:")
                print("        iteration:", pass_index)
                print("        grade:", grade)

            else:
                self.update_overlay(
                    iteration=pass_index,
                    status="failed",
                    grade=None,
                    message="no change"
                )

                self.refresh_viewer()

                print("[eTrim] Iterative gridify pass produced no change:")
                print("        iteration:", pass_index)

                break

        if changed:
            self.refresh_viewer()

        if changed:
            self.finish_overlay(
                message="Complete"
            )
        else:
            self.finish_overlay(
                message="No changes"
            )

        print("[eTrim] Iterative gridify complete.")
        print("        changed:", changed)

        return changed
