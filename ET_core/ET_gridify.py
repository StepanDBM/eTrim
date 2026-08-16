# ET_core/ET_gridify.py

import math
from collections import defaultdict, deque

from ET_core import ET_uv_model


EPSILON = 0.000000001


# -----------------------------------------------------
# Basic UV selection helpers
# -----------------------------------------------------

def unique_uv_pairs(uv_pairs):
    """
    Return unique UV pairs while preserving order.

    uv_pairs:
        [(mesh_data, uv_id), ...]
    """

    result = []
    seen = set()

    for mesh_data, uv_id in uv_pairs:
        key = (
            id(mesh_data),
            uv_id
        )

        if key in seen:
            continue

        seen.add(key)

        result.append(
            (
                mesh_data,
                uv_id
            )
        )

    return result


def get_uv_position(mesh_data, uv_id):
    if (
        hasattr(mesh_data, "preview_uv_positions") and
        uv_id in mesh_data.preview_uv_positions
    ):
        return mesh_data.preview_uv_positions[uv_id]

    return mesh_data.uv_positions[uv_id]


def ensure_preview_positions(mesh_data):
    if not hasattr(mesh_data, "preview_uv_positions"):
        mesh_data.preview_uv_positions = dict(
            mesh_data.uv_positions
        )


def get_selected_face_indices_by_mesh(viewer):
    """
    Return selected UV face indices grouped by mesh_data.

    Returns:
        {
            mesh_data: set(face_index, ...)
        }
    """

    result = {}

    if not viewer or not viewer.uv_drawer:
        return result

    selected_face_keys = viewer.get_selected_drawables_by_type(
        "uv_face"
    )

    for key in selected_face_keys:
        mesh_data, face_index, face_uv_ids = viewer.uv_drawer.get_face_from_drawable_key(
            key
        )

        if not mesh_data:
            continue

        if mesh_data not in result:
            result[mesh_data] = set()

        result[mesh_data].add(
            int(face_index)
        )

    return result


def split_selected_faces_if_needed(viewer):
    """
    If the user selected faces, split those faces into preview UVs first.

    This prevents gridify from pulling unselected shell UVs.
    """

    selected_by_mesh = get_selected_face_indices_by_mesh(
        viewer
    )

    if not selected_by_mesh:
        return False

    for mesh_data, face_indices in selected_by_mesh.items():
        ET_uv_model.split_faces_to_preview_shell(
            mesh_data,
            face_indices
        )

    return True


def get_gridify_uv_pairs(viewer):
    """
    Resolve current viewer selection into UV pairs.

    Priority:
        1. selected vertices
        2. selected faces
        3. selected shells
        4. active vertex
        5. active face
        6. active shell
        7. full loaded cache fallback
    """

    if not viewer or not viewer.uv_drawer:
        return []

    uv_drawer = viewer.uv_drawer

    for drawable_type in (
        "uv_vertex",
        "uv_face",
        "uv_shell"
    ):
        uv_pairs = uv_drawer.get_uv_pairs_from_selected_drawables(
            drawable_type
        )

        if uv_pairs:
            return unique_uv_pairs(
                uv_pairs
            )

    active_vertex = getattr(
        uv_drawer,
        "active_vertex",
        None
    )

    if active_vertex:
        return unique_uv_pairs(
            uv_drawer.get_uv_pairs_from_ref(
                uv_drawer.MODE_VERTEX,
                active_vertex
            )
        )

    active_face = getattr(
        uv_drawer,
        "active_face",
        None
    )

    if active_face:
        return unique_uv_pairs(
            uv_drawer.get_uv_pairs_from_ref(
                uv_drawer.MODE_FACE,
                active_face
            )
        )

    active_shell = getattr(
        uv_drawer,
        "active_shell",
        None
    )

    if active_shell:
        return unique_uv_pairs(
            uv_drawer.get_uv_pairs_from_ref(
                uv_drawer.MODE_SHELL,
                active_shell
            )
        )

    uv_cache = getattr(
        viewer,
        "uv_cache",
        None
    )

    if not uv_cache or not uv_cache.has_data():
        return []

    uv_pairs = []

    for mesh_data in uv_cache.meshes:
        ensure_preview_positions(
            mesh_data
        )

        for uv_id in mesh_data.preview_uv_positions.keys():
            uv_pairs.append(
                (
                    mesh_data,
                    uv_id
                )
            )

    return unique_uv_pairs(
        uv_pairs
    )


def group_uv_pairs_by_mesh(uv_pairs):
    grouped = {}

    for mesh_data, uv_id in uv_pairs:
        if mesh_data not in grouped:
            grouped[mesh_data] = []

        grouped[mesh_data].append(
            uv_id
        )

    return grouped


# -----------------------------------------------------
# Math helpers
# -----------------------------------------------------

def vector_add(a, b):
    return (
        float(a[0]) + float(b[0]),
        float(a[1]) + float(b[1])
    )


def vector_sub(a, b):
    return (
        float(a[0]) - float(b[0]),
        float(a[1]) - float(b[1])
    )


def vector_mul(a, value):
    return (
        float(a[0]) * float(value),
        float(a[1]) * float(value)
    )


def vector_length(a):
    return math.sqrt(
        float(a[0]) * float(a[0]) +
        float(a[1]) * float(a[1])
    )


def vector_distance(a, b):
    return vector_length(
        vector_sub(
            a,
            b
        )
    )


def vector_normalize(a):
    length = vector_length(
        a
    )

    if length <= EPSILON:
        return (
            0.0,
            0.0
        )

    return (
        float(a[0]) / length,
        float(a[1]) / length
    )


def vector_dot(a, b):
    return (
        float(a[0]) * float(b[0]) +
        float(a[1]) * float(b[1])
    )


def vector_perpendicular(a):
    return (
        -float(a[1]),
        float(a[0])
    )


def vector_cross_2d(a, b):
    return (
        float(a[0]) * float(b[1]) -
        float(a[1]) * float(b[0])
    )


def rotate_vector(vector, radians_value):
    cos_value = math.cos(
        radians_value
    )

    sin_value = math.sin(
        radians_value
    )

    x, y = vector

    return (
        x * cos_value - y * sin_value,
        x * sin_value + y * cos_value
    )


def compute_bounds(points):
    if not points:
        return 0.0, 0.0, 0.0, 0.0

    u_values = [
        point[0]
        for point in points
    ]

    v_values = [
        point[1]
        for point in points
    ]

    return (
        min(u_values),
        min(v_values),
        max(u_values),
        max(v_values)
    )


def get_polygon_area_from_positions(mesh_data, face_uv_ids):
    if len(face_uv_ids) < 3:
        return 0.0

    area = 0.0
    count = len(face_uv_ids)

    for index, uv_a in enumerate(face_uv_ids):
        uv_b = face_uv_ids[
            (
                index + 1
            ) % count
        ]

        pos_a = get_uv_position(
            mesh_data,
            uv_a
        )

        pos_b = get_uv_position(
            mesh_data,
            uv_b
        )

        area += (
            pos_a[0] * pos_b[1] -
            pos_b[0] * pos_a[1]
        )

    return abs(area) * 0.5


def signed_quad_area(points):
    """
    Signed area for four points in order.
    """

    if len(points) != 4:
        return 0.0

    area = 0.0

    for index, point_a in enumerate(points):
        point_b = points[
            (
                index + 1
            ) % 4
        ]

        area += (
            point_a[0] * point_b[1] -
            point_b[0] * point_a[1]
        )

    return area * 0.5


def nearest_axis_from_vector(vector):
    """
    Snap an orientation vector to the nearest UV editor axis.

    Returns one of:
        (1, 0), (-1, 0), (0, 1), (0, -1)
    """

    x, y = vector

    if abs(x) >= abs(y):
        if x >= 0.0:
            return (
                1.0,
                0.0
            )

        return (
            -1.0,
            0.0
        )

    if y >= 0.0:
        return (
            0.0,
            1.0
        )

    return (
        0.0,
        -1.0
    )


# -----------------------------------------------------
# Quad topology helpers
# -----------------------------------------------------

def get_complete_selected_face_indices(mesh_data, selected_uv_ids):
    """
    Return faces whose all UV ids are inside selected_uv_ids.
    """

    selected_uv_ids = set(
        selected_uv_ids
    )

    result = []

    for face_index, face_uv_ids in enumerate(mesh_data.faces):
        if not face_uv_ids:
            continue

        complete = True

        for uv_id in face_uv_ids:
            if uv_id not in selected_uv_ids:
                complete = False
                break

        if complete:
            result.append(
                face_index
            )

    return result


def get_complete_selected_quad_indices(mesh_data, selected_uv_ids):
    """
    Return selected faces that are complete quads.
    """

    result = []

    complete_faces = get_complete_selected_face_indices(
        mesh_data,
        selected_uv_ids
    )

    for face_index in complete_faces:
        face_uv_ids = mesh_data.faces[face_index]

        if len(face_uv_ids) == 4:
            result.append(
                face_index
            )

    return result


def edge_key(uv_a, uv_b):
    return tuple(
        sorted(
            (
                uv_a,
                uv_b
            )
        )
    )


def build_quad_adjacency(mesh_data, quad_face_indices):
    """
    Build adjacency between selected quad faces through shared UV edges.

    Returns:
        face_index -> [(neighbor_face_index, shared_uv_a, shared_uv_b), ...]
    """

    quad_face_set = set(
        quad_face_indices
    )

    edge_to_faces = defaultdict(list)

    for face_index in quad_face_indices:
        face_uv_ids = mesh_data.faces[face_index]

        if len(face_uv_ids) != 4:
            continue

        for index, uv_a in enumerate(face_uv_ids):
            uv_b = face_uv_ids[
                (
                    index + 1
                ) % 4
            ]

            key = edge_key(
                uv_a,
                uv_b
            )

            edge_to_faces[key].append(
                face_index
            )

    neighbors = defaultdict(list)

    for key, face_indices in edge_to_faces.items():
        if len(face_indices) != 2:
            continue

        face_a, face_b = face_indices
        uv_a, uv_b = key

        if face_a not in quad_face_set:
            continue

        if face_b not in quad_face_set:
            continue

        neighbors[face_a].append(
            (
                face_b,
                uv_a,
                uv_b
            )
        )

        neighbors[face_b].append(
            (
                face_a,
                uv_a,
                uv_b
            )
        )

    return neighbors


def split_face_components(face_indices, neighbors):
    """
    Split selected quad faces into connected components.
    """

    remaining = set(
        face_indices
    )

    components = []

    while remaining:
        start = next(
            iter(
                remaining
            )
        )

        remaining.remove(
            start
        )

        component = set(
            [
                start
            ]
        )

        queue = deque(
            [
                start
            ]
        )

        while queue:
            face_index = queue.popleft()

            for neighbor_face, uv_a, uv_b in neighbors.get(face_index, []):
                if neighbor_face not in remaining:
                    continue

                remaining.remove(
                    neighbor_face
                )

                component.add(
                    neighbor_face
                )

                queue.append(
                    neighbor_face
                )

        components.append(
            component
        )

    return components


def choose_root_quad(mesh_data, component_face_indices):
    """
    Pick a stable root quad.

    Current rule:
        largest UV area among quad faces.
    """

    best_face_index = None
    best_area = -1.0

    for face_index in component_face_indices:
        face_uv_ids = mesh_data.faces[face_index]

        area = get_polygon_area_from_positions(
            mesh_data,
            face_uv_ids
        )

        if area > best_area:
            best_area = area
            best_face_index = face_index

    return best_face_index


def find_consecutive_edge_in_quad(face_uv_ids, shared_a, shared_b):
    """
    Find a shared edge inside a quad.

    Returns:
        index_i, index_j
    """

    count = len(
        face_uv_ids
    )

    for index in range(count):
        next_index = (
            index + 1
        ) % count

        uv_a = face_uv_ids[index]
        uv_b = face_uv_ids[next_index]

        if (
            (
                uv_a == shared_a and
                uv_b == shared_b
            ) or
            (
                uv_a == shared_b and
                uv_b == shared_a
            )
        ):
            return index, next_index

    return None, None


def get_neighbor_outside_vertices(face_uv_ids, shared_a, shared_b):
    """
    For a quad neighbor sharing edge shared_a/shared_b, return:

        shared_left, shared_right, outside_left, outside_right

    Meaning:
        outside_left is connected to shared_left
        outside_right is connected to shared_right
    """

    index_i, index_j = find_consecutive_edge_in_quad(
        face_uv_ids,
        shared_a,
        shared_b
    )

    if index_i is None:
        return None

    count = len(
        face_uv_ids
    )

    shared_left = face_uv_ids[index_i]
    shared_right = face_uv_ids[index_j]

    outside_left = face_uv_ids[
        (
            index_i - 1
        ) % count
    ]

    outside_right = face_uv_ids[
        (
            index_j + 1
        ) % count
    ]

    return (
        shared_left,
        shared_right,
        outside_left,
        outside_right
    )


def compute_face_centroid_from_grid_coords(face_uv_ids, grid_coords):
    values = []

    for uv_id in face_uv_ids:
        if uv_id not in grid_coords:
            continue

        values.append(
            grid_coords[uv_id]
        )

    if not values:
        return (
            0.0,
            0.0
        )

    sum_u = sum(
        value[0]
        for value in values
    )

    sum_v = sum(
        value[1]
        for value in values
    )

    return (
        sum_u / float(len(values)),
        sum_v / float(len(values))
    )


def compute_average_side_length(mesh_data, shared_left, shared_right, outside_left, outside_right):
    """
    Estimate how far the neighboring quad should extend from the shared edge.
    """

    pos_shared_left = get_uv_position(
        mesh_data,
        shared_left
    )

    pos_shared_right = get_uv_position(
        mesh_data,
        shared_right
    )

    pos_outside_left = get_uv_position(
        mesh_data,
        outside_left
    )

    pos_outside_right = get_uv_position(
        mesh_data,
        outside_right
    )

    length_a = vector_distance(
        pos_shared_left,
        pos_outside_left
    )

    length_b = vector_distance(
        pos_shared_right,
        pos_outside_right
    )

    length = (
        length_a + length_b
    ) * 0.5

    if length <= EPSILON:
        length = vector_distance(
            pos_shared_left,
            pos_shared_right
        )

    return max(
        length,
        EPSILON
    )


# -----------------------------------------------------
# Follow-active-quad style solver
# -----------------------------------------------------

def solve_quad_component_grid_coords(mesh_data, component_face_indices, neighbors):
    """
    Solve one connected quad component into local rectangular grid coordinates.

    It:
        - chooses a root quad
        - makes the root a rectangle in local coordinates
        - walks adjacent quads through shared edges
        - extends each neighboring quad perpendicular to the shared edge
    """

    if not component_face_indices:
        return {}, None, set()

    root_face_index = choose_root_quad(
        mesh_data,
        component_face_indices
    )

    if root_face_index is None:
        return {}, None, set()

    root_uv_ids = mesh_data.faces[root_face_index]

    if len(root_uv_ids) != 4:
        return {}, None, set()

    root_positions = [
        get_uv_position(
            mesh_data,
            uv_id
        )
        for uv_id in root_uv_ids
    ]

    root_width = vector_distance(
        root_positions[0],
        root_positions[1]
    )

    root_height = vector_distance(
        root_positions[1],
        root_positions[2]
    )

    if root_width <= EPSILON:
        root_width = vector_distance(
            root_positions[2],
            root_positions[3]
        )

    if root_height <= EPSILON:
        root_height = vector_distance(
            root_positions[3],
            root_positions[0]
        )

    root_width = max(
        root_width,
        EPSILON
    )

    root_height = max(
        root_height,
        EPSILON
    )

    grid_coords = {}

    grid_coords[root_uv_ids[0]] = (
        0.0,
        0.0
    )

    grid_coords[root_uv_ids[1]] = (
        root_width,
        0.0
    )

    grid_coords[root_uv_ids[2]] = (
        root_width,
        root_height
    )

    grid_coords[root_uv_ids[3]] = (
        0.0,
        root_height
    )

    solved_faces = set(
        [
            root_face_index
        ]
    )

    queue = deque(
        [
            root_face_index
        ]
    )

    while queue:
        current_face_index = queue.popleft()
        current_face_uv_ids = mesh_data.faces[current_face_index]

        current_centroid = compute_face_centroid_from_grid_coords(
            current_face_uv_ids,
            grid_coords
        )

        for neighbor_face_index, shared_a, shared_b in neighbors.get(current_face_index, []):
            if neighbor_face_index in solved_faces:
                continue

            neighbor_face_uv_ids = mesh_data.faces[neighbor_face_index]

            edge_data = get_neighbor_outside_vertices(
                neighbor_face_uv_ids,
                shared_a,
                shared_b
            )

            if not edge_data:
                continue

            shared_left, shared_right, outside_left, outside_right = edge_data

            if shared_left not in grid_coords:
                continue

            if shared_right not in grid_coords:
                continue

            coord_left = grid_coords[shared_left]
            coord_right = grid_coords[shared_right]

            edge_vector = vector_sub(
                coord_right,
                coord_left
            )

            edge_length = vector_length(
                edge_vector
            )

            if edge_length <= EPSILON:
                continue

            edge_direction = vector_normalize(
                edge_vector
            )

            perpendicular = vector_perpendicular(
                edge_direction
            )

            shared_midpoint = vector_mul(
                vector_add(
                    coord_left,
                    coord_right
                ),
                0.5
            )

            current_side = vector_dot(
                vector_sub(
                    current_centroid,
                    shared_midpoint
                ),
                perpendicular
            )

            if current_side > 0.0:
                side_sign = -1.0
            else:
                side_sign = 1.0

            side_length = compute_average_side_length(
                mesh_data,
                shared_left,
                shared_right,
                outside_left,
                outside_right
            )

            offset = vector_mul(
                perpendicular,
                side_length * side_sign
            )

            outside_left_coord = vector_add(
                coord_left,
                offset
            )

            outside_right_coord = vector_add(
                coord_right,
                offset
            )

            if outside_left not in grid_coords:
                grid_coords[outside_left] = outside_left_coord

            if outside_right not in grid_coords:
                grid_coords[outside_right] = outside_right_coord

            solved_faces.add(
                neighbor_face_index
            )

            queue.append(
                neighbor_face_index
            )

    return grid_coords, root_face_index, solved_faces


def map_grid_coords_to_uv_space(
    mesh_data,
    root_face_index,
    grid_coords,
    angle_offset_degrees=0.0,
    swap_axes=False
):
    """
    Map local grid coordinates back to UV space.

    This version snaps the output to the nearest UV editor axis.
    That is intentional for gridify.
    """

    if root_face_index is None:
        return {}

    root_uv_ids = mesh_data.faces[root_face_index]

    if len(root_uv_ids) != 4:
        return {}

    root_pos_0 = get_uv_position(
        mesh_data,
        root_uv_ids[0]
    )

    root_pos_1 = get_uv_position(
        mesh_data,
        root_uv_ids[1]
    )

    root_pos_3 = get_uv_position(
        mesh_data,
        root_uv_ids[3]
    )

    original_x = vector_normalize(
        vector_sub(
            root_pos_1,
            root_pos_0
        )
    )

    if vector_length(original_x) <= EPSILON:
        original_x = (
            1.0,
            0.0
        )

    axis_x = nearest_axis_from_vector(
        original_x
    )

    if swap_axes:
        axis_x = vector_perpendicular(
            axis_x
        )

    angle_offset = math.radians(
        float(angle_offset_degrees)
    )

    if abs(angle_offset) > EPSILON:
        axis_x = rotate_vector(
            axis_x,
            angle_offset
        )

    axis_x = vector_normalize(
        axis_x
    )

    axis_y = vector_perpendicular(
        axis_x
    )

    raw_y = vector_sub(
        root_pos_3,
        root_pos_0
    )

    if vector_dot(axis_y, raw_y) < 0.0:
        axis_y = vector_mul(
            axis_y,
            -1.0
        )

    mapped = {}

    for uv_id, coord in grid_coords.items():
        coord_x, coord_y = coord

        position = vector_add(
            root_pos_0,
            vector_add(
                vector_mul(
                    axis_x,
                    coord_x
                ),
                vector_mul(
                    axis_y,
                    coord_y
                )
            )
        )

        mapped[uv_id] = position

    return mapped


def translate_positions_to_match_source_center(mesh_data, uv_ids, positions):
    """
    Keep solved component spatially near its original UV location.
    """

    if not positions:
        return positions

    source_points = []
    target_points = []

    for uv_id in uv_ids:
        if uv_id not in positions:
            continue

        source_points.append(
            get_uv_position(
                mesh_data,
                uv_id
            )
        )

        target_points.append(
            positions[uv_id]
        )

    if not source_points or not target_points:
        return positions

    source_center_u = sum(
        point[0]
        for point in source_points
    ) / float(len(source_points))

    source_center_v = sum(
        point[1]
        for point in source_points
    ) / float(len(source_points))

    target_center_u = sum(
        point[0]
        for point in target_points
    ) / float(len(target_points))

    target_center_v = sum(
        point[1]
        for point in target_points
    ) / float(len(target_points))

    offset = (
        source_center_u - target_center_u,
        source_center_v - target_center_v
    )

    result = {}

    for uv_id, position in positions.items():
        result[uv_id] = vector_add(
            position,
            offset
        )

    return result


def attach_unsolved_selected_vertices(mesh_data, selected_uv_ids, final_positions):
    """
    Move selected non-quad / triangle-only UVs only when they are connected to
    solved UVs.

    This avoids forcing triangles to define the grid, while still allowing rim
    vertices to follow nearby solved quad structure a little.
    """

    if not final_positions:
        return final_positions

    selected_uv_ids = set(
        selected_uv_ids
    )

    solved_uv_ids = set(
        final_positions.keys()
    )

    result = dict(
        final_positions
    )

    adjacency = getattr(
        mesh_data,
        "adjacency",
        {}
    )

    for uv_id in selected_uv_ids:
        if uv_id in result:
            continue

        neighbors = adjacency.get(
            uv_id,
            []
        )

        source_position = get_uv_position(
            mesh_data,
            uv_id
        )

        offsets = []

        for neighbor_uv_id in neighbors:
            if neighbor_uv_id not in solved_uv_ids:
                continue

            old_neighbor_position = get_uv_position(
                mesh_data,
                neighbor_uv_id
            )

            new_neighbor_position = final_positions[neighbor_uv_id]

            offsets.append(
                vector_sub(
                    new_neighbor_position,
                    old_neighbor_position
                )
            )

        if not offsets:
            continue

        average_offset = (
            sum(
                offset[0]
                for offset in offsets
            ) / float(len(offsets)),
            sum(
                offset[1]
                for offset in offsets
            ) / float(len(offsets))
        )

        result[uv_id] = vector_add(
            source_position,
            average_offset
        )

    return result


def compute_follow_active_quad_gridified_positions_for_mesh(
    mesh_data,
    uv_ids,
    angle_offset_degrees=0.0,
    u_tolerance_multiplier=1.0,
    v_tolerance_multiplier=1.0,
    swap_axes=False
):
    """
    Clean-room follow-active-quad style gridify.

    Behavior:
        - complete selected quad faces drive the grid
        - triangles and n-gons do not drive the grid
        - triangle/rim vertices can follow nearby solved quads
        - no global PCA bounding-box remapping
    """

    if not mesh_data or not uv_ids:
        return {}

    ensure_preview_positions(
        mesh_data
    )

    uv_ids = sorted(
        set(
            uv_ids
        )
    )

    selected_uv_ids = set(
        uv_ids
    )

    quad_face_indices = get_complete_selected_quad_indices(
        mesh_data,
        selected_uv_ids
    )

    if not quad_face_indices:
        print("[eTrim] Gridify skipped. No complete selected quad faces.")
        return {}

    neighbors = build_quad_adjacency(
        mesh_data,
        quad_face_indices
    )

    components = split_face_components(
        quad_face_indices,
        neighbors
    )

    final_positions = {}

    solved_face_count = 0

    for component in components:
        grid_coords, root_face_index, solved_faces = solve_quad_component_grid_coords(
            mesh_data,
            component,
            neighbors
        )

        if not grid_coords:
            continue

        if root_face_index is None:
            continue

        mapped_positions = map_grid_coords_to_uv_space(
            mesh_data,
            root_face_index,
            grid_coords,
            angle_offset_degrees=angle_offset_degrees,
            swap_axes=swap_axes
        )

        component_uv_ids = sorted(
            grid_coords.keys()
        )

        mapped_positions = translate_positions_to_match_source_center(
            mesh_data,
            component_uv_ids,
            mapped_positions
        )

        for uv_id, position in mapped_positions.items():
            if uv_id not in selected_uv_ids:
                continue

            final_positions[uv_id] = position

        solved_face_count += len(
            solved_faces
        )

    final_positions = attach_unsolved_selected_vertices(
        mesh_data,
        selected_uv_ids,
        final_positions
    )

    if not final_positions:
        print("[eTrim] Gridify produced no topology-aware positions.")
        return {}
    """
    print("[eTrim] Gridify mesh:")
    print("    mesh:", mesh_data.mesh_name)
    print("    uv count:", len(final_positions))
    print("    quad faces:", len(quad_face_indices))
    print("    solved quad faces:", solved_face_count)
    print("    components:", len(components))
    """

    return final_positions


# -----------------------------------------------------
# Public solver entry points
# -----------------------------------------------------

def compute_gridified_positions_for_mesh(
    mesh_data,
    uv_ids,
    angle_offset_degrees=0.0,
    u_tolerance_multiplier=1.0,
    v_tolerance_multiplier=1.0,
    swap_axes=False
):
    """
    Public gridify solver.

    The tolerance arguments are kept for heuristic compatibility.
    This topology-aware implementation does not do global U/V clustering.
    """

    return compute_follow_active_quad_gridified_positions_for_mesh(
        mesh_data,
        uv_ids,
        angle_offset_degrees=angle_offset_degrees,
        u_tolerance_multiplier=u_tolerance_multiplier,
        v_tolerance_multiplier=v_tolerance_multiplier,
        swap_axes=swap_axes
    )


def apply_gridified_positions(mesh_data, positions):
    """
    Apply gridified UV positions to preview positions.
    """

    if not positions:
        return False

    ensure_preview_positions(
        mesh_data
    )

    for uv_id, uv_position in positions.items():
        mesh_data.preview_uv_positions[uv_id] = uv_position

    return True


def gridify_viewer_selection_to_preview(viewer):
    """
    Gridify current viewer UV selection into preview UV positions.

    New version:
        - topology-aware
        - quad propagation based
        - does not force whole selection into a rectangular PCA grid
    """

    if not viewer:
        return False

    uv_cache = getattr(
        viewer,
        "uv_cache",
        None
    )

    if not uv_cache:
        print("[eTrim] No UV cache loaded for gridify.")
        return False

    if not uv_cache.has_data():
        print("[eTrim] Empty UV cache. Gridify skipped.")
        return False

    split_selected_faces_if_needed(viewer)

    uv_pairs = get_gridify_uv_pairs(viewer)

    if not uv_pairs:
        print("[eTrim] No selected UVs found for gridify.")
        return False

    grouped = group_uv_pairs_by_mesh(uv_pairs)

    changed = False

    for mesh_data, uv_ids in grouped.items():
        uv_ids = sorted(set(uv_ids))

        positions = compute_gridified_positions_for_mesh(mesh_data, uv_ids)

        if apply_gridified_positions(mesh_data, positions):
            changed = True

    if changed:
        viewer.update()
        print("[eTrim] Gridify preview complete.")
    else:
        print("[eTrim] Gridify produced no changes.")

    return changed