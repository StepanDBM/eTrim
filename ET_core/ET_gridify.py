# ET_core/ET_gridify.py

import math

from ET_core import ET_uv_model


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
        mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)


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

    This prevents gridify from pulling the whole original shell when the user
    only selected a few faces.
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
        1. selected faces
        2. selected shells
        3. active face
        4. active shell
        5. full loaded cache fallback
    """

    if not viewer or not viewer.uv_drawer:
        return []

    uv_drawer = viewer.uv_drawer
    selected_vertex_pairs = uv_drawer.get_uv_pairs_from_selected_drawables(
        "uv_vertex"
    )

    if selected_vertex_pairs:
        if hasattr(uv_drawer, "prepare_selected_vertices_for_preview_edit"):
            prepared_pairs = uv_drawer.prepare_selected_vertices_for_preview_edit()

            if prepared_pairs:
                return unique_uv_pairs(
                    prepared_pairs
                )

        return unique_uv_pairs(
            selected_vertex_pairs
        )

    # Face selection first.
    selected_face_pairs = uv_drawer.get_uv_pairs_from_selected_drawables(
        "uv_face"
    )

    if selected_face_pairs:
        return unique_uv_pairs(
            selected_face_pairs
        )

    # Shell selection second.
    selected_shell_pairs = uv_drawer.get_uv_pairs_from_selected_drawables(
        "uv_shell"
    )

    if selected_shell_pairs:
        return unique_uv_pairs(
            selected_shell_pairs
        )

    # Active face fallback.
    active_face = getattr(
        uv_drawer,
        "active_face",
        None
    )

    if active_face:
        mesh_data, face_index, face_uv_ids = active_face

        return unique_uv_pairs(
            [
                (
                    mesh_data,
                    uv_id
                )
                for uv_id in face_uv_ids
            ]
        )

    # Active shell fallback.
    active_shell = getattr(
        uv_drawer,
        "active_shell",
        None
    )

    if active_shell:
        mesh_data, shell_data = active_shell

        return unique_uv_pairs(
            uv_drawer.get_uv_pairs_from_shell(
                mesh_data,
                shell_data
            )
        )

    # Whole cache fallback.
    uv_cache = getattr(
        viewer,
        "uv_cache",
        None
    )

    if not uv_cache or not uv_cache.has_data():
        return []

    uv_pairs = []

    for mesh_data in uv_cache.meshes:
        ensure_preview_positions(mesh_data)

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


def compute_bounds(points):
    """
    points:
        [(u, v), ...]

    Returns:
        u_min, v_min, u_max, v_max
    """

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


def compute_pca_angle(points):
    """
    Compute principal direction angle from UV points.

    This helps gridify islands that are somewhat rotated.
    The output grid itself is still axis-aligned afterward.
    """

    if len(points) < 2:
        return 0.0

    center_u = sum(
        point[0]
        for point in points
    ) / float(len(points))

    center_v = sum(
        point[1]
        for point in points
    ) / float(len(points))

    xx = 0.0
    xy = 0.0
    yy = 0.0

    for u, v in points:
        du = u - center_u
        dv = v - center_v

        xx += du * du
        xy += du * dv
        yy += dv * dv

    if abs(xx - yy) < 0.0000001 and abs(xy) < 0.0000001:
        return 0.0

    return 0.5 * math.atan2(
        2.0 * xy,
        xx - yy
    )


def rotate_point(u, v, center_u, center_v, radians):
    cos_value = math.cos(radians)
    sin_value = math.sin(radians)

    local_u = u - center_u
    local_v = v - center_v

    return (
        center_u + local_u * cos_value - local_v * sin_value,
        center_v + local_u * sin_value + local_v * cos_value
    )


def cluster_values(values, tolerance):
    """
    Cluster sorted scalar values into row/column groups.

    Returns:
        centers, value_to_cluster_index
    """

    if not values:
        return [], {}

    sorted_values = sorted(values)

    clusters = []
    current_cluster = [
        sorted_values[0]
    ]

    for value in sorted_values[1:]:
        previous = current_cluster[-1]

        if abs(value - previous) <= tolerance:
            current_cluster.append(value)
        else:
            clusters.append(current_cluster)
            current_cluster = [
                value
            ]

    clusters.append(current_cluster)

    centers = [
        sum(cluster) / float(len(cluster))
        for cluster in clusters
    ]

    value_to_cluster_index = {}

    for value in values:
        best_index = 0
        best_distance = None

        for index, center in enumerate(centers):
            distance = abs(value - center)

            if best_distance is None or distance < best_distance:
                best_distance = distance
                best_index = index

        value_to_cluster_index[value] = best_index

    return centers, value_to_cluster_index


def get_adaptive_tolerance(values, span):
    """
    Estimate a clustering tolerance.

    This keeps the first implementation simple:
        - small enough to not merge all columns
        - large enough to absorb wavy native unwrap rows
    """

    if not values:
        return 0.001

    if span <= 0.000001:
        return 0.001

    sorted_values = sorted(values)

    diffs = []

    for index in range(len(sorted_values) - 1):
        diff = abs(
            sorted_values[index + 1] - sorted_values[index]
        )

        if diff > 0.000001:
            diffs.append(diff)

    if not diffs:
        return span * 0.02

    diffs.sort()

    median_diff = diffs[len(diffs) // 2]

    # If many UVs are already almost aligned, median diff can be tiny.
    # Clamp using span-based tolerance.
    return max(
        span * 0.015,
        min(
            span * 0.08,
            median_diff * 0.45
        )
    )


def compute_gridified_positions_for_mesh(mesh_data, uv_ids):
    """
    Compute clean grid positions for selected UV ids on one mesh.

    This is UV-space gridify:
        - reads current preview positions
        - estimates principal axes
        - clusters UVs into rows and columns
        - writes them into an evenly spaced axis-aligned grid
    """

    if not mesh_data or not uv_ids:
        return {}

    ensure_preview_positions(mesh_data)

    source_positions = {}

    for uv_id in uv_ids:
        if uv_id not in mesh_data.preview_uv_positions:
            continue

        source_positions[uv_id] = get_uv_position(
            mesh_data,
            uv_id
        )

    if len(source_positions) < 2:
        return {}

    points = list(source_positions.values())

    u_min, v_min, u_max, v_max = compute_bounds(
        points
    )

    width = u_max - u_min
    height = v_max - v_min

    if width <= 0.000001 or height <= 0.000001:
        return {}

    center_u = (u_min + u_max) * 0.5
    center_v = (v_min + v_max) * 0.5

    angle = compute_pca_angle(
        points
    )

    # Rotate into local PCA space for better clustering.
    local_positions = {}

    for uv_id, position in source_positions.items():
        u, v = position

        local_u, local_v = rotate_point(
            u,
            v,
            center_u,
            center_v,
            -angle
        )

        local_positions[uv_id] = (
            local_u,
            local_v
        )

    local_points = list(local_positions.values())

    local_u_min, local_v_min, local_u_max, local_v_max = compute_bounds(
        local_points
    )

    local_width = local_u_max - local_u_min
    local_height = local_v_max - local_v_min

    if local_width <= 0.000001 or local_height <= 0.000001:
        return {}

    local_u_values = [
        position[0]
        for position in local_positions.values()
    ]

    local_v_values = [
        position[1]
        for position in local_positions.values()
    ]

    u_tolerance = get_adaptive_tolerance(
        local_u_values,
        local_width
    )

    v_tolerance = get_adaptive_tolerance(
        local_v_values,
        local_height
    )

    column_centers, value_to_column = cluster_values(
        local_u_values,
        u_tolerance
    )

    row_centers, value_to_row = cluster_values(
        local_v_values,
        v_tolerance
    )

    column_count = len(column_centers)
    row_count = len(row_centers)

    if column_count < 2 and row_count < 2:
        return {}

    result = {}

    for uv_id, local_position in local_positions.items():
        local_u, local_v = local_position

        column_index = value_to_column.get(
            local_u,
            0
        )

        row_index = value_to_row.get(
            local_v,
            0
        )

        if column_count <= 1:
            normalized_u = 0.5
        else:
            normalized_u = float(column_index) / float(column_count - 1)

        if row_count <= 1:
            normalized_v = 0.5
        else:
            normalized_v = float(row_index) / float(row_count - 1)

        new_u = u_min + normalized_u * width
        new_v = v_min + normalized_v * height

        result[uv_id] = (
            new_u,
            new_v
        )

    print("[eTrim] Gridify mesh:")
    print("    mesh:", mesh_data.mesh_name)
    print("    uv count:", len(result))
    print("    columns:", column_count)
    print("    rows:", row_count)

    return result


def apply_gridified_positions(mesh_data, positions):
    """
    Apply gridified UV positions to preview positions.
    """

    if not positions:
        return False

    ensure_preview_positions(mesh_data)

    for uv_id, uv_position in positions.items():
        mesh_data.preview_uv_positions[uv_id] = uv_position

    return True


def gridify_viewer_selection_to_preview(viewer):
    """
    Gridify current viewer UV selection into preview UV positions.

    First version:
        - UV-space row/column clustering
        - good after native unwrap
        - does not yet perform topology-aware grid solving
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

    # If faces are selected, isolate them first.
    # This prevents selected-face gridify from pulling the whole original shell.
    split_selected_faces_if_needed(
        viewer
    )

    uv_pairs = get_gridify_uv_pairs(
        viewer
    )

    if not uv_pairs:
        print("[eTrim] No selected UVs found for gridify.")
        return False

    grouped = group_uv_pairs_by_mesh(
        uv_pairs
    )

    changed = False

    for mesh_data, uv_ids in grouped.items():
        uv_ids = sorted(
            set(uv_ids)
        )

        positions = compute_gridified_positions_for_mesh(
            mesh_data,
            uv_ids
        )

        if apply_gridified_positions(
            mesh_data,
            positions
        ):
            changed = True

    if changed:
        viewer.update()
        print("[eTrim] Gridify preview complete.")
    else:
        print("[eTrim] Gridify produced no changes.")

    return changed