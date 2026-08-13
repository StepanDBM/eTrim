# ET_core/ET_uv_model.py

import re
from collections import defaultdict, deque

from maya import cmds
import maya.api.OpenMaya as om


_FACE_RE = re.compile(r"(.+)\.f\[(\d+)\]$")


class EUVShellData(object):
    def __init__(self, shell_id):
        self.shell_id = shell_id
        self.uv_ids = set()
        self.edges = []
        self.faces = []


class EUVMeshUVData(object):
    def __init__(self, mesh_name, uv_set):
        self.mesh_name = mesh_name
        self.uv_set = uv_set

        # uv_id -> (u, v)
        self.uv_positions = {}
        # uv_id -> (u, v)
        # Editable viewer-side preview positions.
        # Native UVs are not modified until an explicit Apply step exists.
        self.preview_uv_positions = {}
        self.preview_uv_original_ids = {}
        self.next_preview_uv_id = 0

        # [(uv_id_a, uv_id_b), ...]
        self.edges = []

        # [[uv_id_0, uv_id_1, uv_id_2, ...], ...]
        self.faces = []
        
        # face index in mesh_data.faces -> Maya polygon id
        self.face_polygon_ids = []

        # uv_id -> set(connected uv ids)
        self.adjacency = defaultdict(set)

        # [EUVShellData, ...]
        self.shells = []


class EUVCache(object):
    """
    Stores UV data imported from Maya.

    This is the future source for:
    - drawing selected UVs
    - finding shell neighbours
    - moving/scaling/rotating preview UVs
    - applying preview changes back to Maya
    """

    def __init__(self):
        self.meshes = []
        self.source_selection = []

    def clear(self):
        self.meshes = []
        self.source_selection = []

    def has_data(self):
        return bool(self.meshes)


# -----------------------------------------------------
# Selection helpers
# -----------------------------------------------------

def get_selected_face_components():
    """
    Convert current Maya selection to polygon faces.

    Supports:
    - selected faces
    - selected vertices
    - selected edges
    - selected transforms / shapes

    For now, if conversion fails or no UVs exist, we let it error loudly.
    """

    selection = cmds.ls(sl=True, fl=True) or []

    if not selection:
        cmds.warning("[eTrim] Nothing selected. Select mesh faces/components/object first.")
        raise RuntimeError("[eTrim] Nothing selected.")

    converted = cmds.polyListComponentConversion(
        selection,
        toFace=True
    )

    faces = cmds.ls(converted, fl=True) or []

    if not faces:
        cmds.warning("[eTrim] Selection could not be converted to polygon faces.")
        raise RuntimeError("[eTrim] No polygon faces found from selection.")

    return faces


def group_faces_by_object(face_components):
    grouped = defaultdict(list)

    for component in face_components:
        match = _FACE_RE.match(component)

        if not match:
            continue

        object_name = match.group(1)
        face_id = int(match.group(2))

        grouped[object_name].append(face_id)

    if not grouped:
        cmds.warning("[eTrim] Could not parse selected face components.")
        raise RuntimeError("[eTrim] Could not parse faces.")

    return grouped


def get_mesh_dag_path(object_name):
    """
    Resolve transform/shape name to a mesh MDagPath.
    """

    selection_list = om.MSelectionList()
    selection_list.add(object_name)

    dag_path = selection_list.getDagPath(0)

    if dag_path.node().hasFn(om.MFn.kTransform):
        dag_path.extendToShape()

    if not dag_path.node().hasFn(om.MFn.kMesh):
        cmds.warning("[eTrim] Object is not a mesh: {}".format(object_name))
        raise RuntimeError("[eTrim] Object is not a mesh: {}".format(object_name))

    return dag_path


# -----------------------------------------------------
# UV building
# -----------------------------------------------------

def get_polygon_uv_id(mesh_fn, polygon_id, local_vertex_id, uv_set):
    """
    Compatibility wrapper for getting polygon UV id.
    """

    try:
        return mesh_fn.getPolygonUVid(
            polygon_id,
            local_vertex_id,
            uv_set
        )
    except TypeError:
        return mesh_fn.getPolygonUVid(
            polygon_id,
            local_vertex_id
        )


def build_mesh_uv_data(object_name, face_ids):
    dag_path = get_mesh_dag_path(object_name)
    mesh_fn = om.MFnMesh(dag_path)

    uv_sets = mesh_fn.getUVSetNames()

    if not uv_sets:
        cmds.warning("[eTrim] Mesh has no UV sets: {}".format(object_name))
        raise RuntimeError("[eTrim] Mesh has no UV sets: {}".format(object_name))

    uv_set = mesh_fn.currentUVSetName()

    if not uv_set:
        uv_set = uv_sets[0]

    try:
        u_array, v_array = mesh_fn.getUVs(uv_set)
    except Exception:
        cmds.warning("[eTrim] Could not read UVs from mesh: {}".format(object_name))
        raise

    mesh_data = EUVMeshUVData(
        mesh_name=object_name,
        uv_set=uv_set
    )

    unique_edges = set()
    face_id_set = set(face_ids)

    for polygon_id in sorted(face_id_set):
        vertex_count = mesh_fn.polygonVertexCount(polygon_id)

        face_uv_ids = []

        for local_vertex_id in range(vertex_count):
            uv_id = get_polygon_uv_id(
                mesh_fn,
                polygon_id,
                local_vertex_id,
                uv_set
            )

            face_uv_ids.append(uv_id)

            if uv_id not in mesh_data.uv_positions:
                mesh_data.uv_positions[uv_id] = (
                    float(u_array[uv_id]),
                    float(v_array[uv_id])
                )

        mesh_data.faces.append(face_uv_ids)
        mesh_data.face_polygon_ids.append(polygon_id)

        for i, uv_a in enumerate(face_uv_ids):
            uv_b = face_uv_ids[(i + 1) % len(face_uv_ids)]

            edge_key = tuple(sorted((uv_a, uv_b)))

            if edge_key not in unique_edges:
                unique_edges.add(edge_key)
                mesh_data.edges.append((uv_a, uv_b))

            mesh_data.adjacency[uv_a].add(uv_b)
            mesh_data.adjacency[uv_b].add(uv_a)

    mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)

    mesh_data.preview_uv_original_ids = {}

    for uv_id in mesh_data.uv_positions:
        mesh_data.preview_uv_original_ids[uv_id] = uv_id

    if mesh_data.preview_uv_positions:
        mesh_data.next_preview_uv_id = max(mesh_data.preview_uv_positions.keys()) + 1
    else:
        mesh_data.next_preview_uv_id = 0

    build_shells(mesh_data)

    return mesh_data


def build_shells(mesh_data):
    """
    Build UV shell islands from selected UV adjacency.
    """

    remaining = set()

    for face_uv_ids in mesh_data.faces:
        for uv_id in face_uv_ids:
            remaining.add(uv_id)
    shell_index = 0

    while remaining:
        start_uv = next(iter(remaining))

        shell = EUVShellData(shell_index)
        shell_index += 1

        queue = deque([start_uv])
        remaining.remove(start_uv)

        while queue:
            uv_id = queue.popleft()
            shell.uv_ids.add(uv_id)

            for neighbour in mesh_data.adjacency.get(uv_id, []):
                if neighbour in remaining:
                    remaining.remove(neighbour)
                    queue.append(neighbour)

        # Store shell faces.
        for face_uv_ids in mesh_data.faces:
            if any(uv_id in shell.uv_ids for uv_id in face_uv_ids):
                shell.faces.append(face_uv_ids)

        # Store shell edges.
        for uv_a, uv_b in mesh_data.edges:
            if uv_a in shell.uv_ids and uv_b in shell.uv_ids:
                shell.edges.append((uv_a, uv_b))

        mesh_data.shells.append(shell)

def ensure_preview_uv_storage(mesh_data):
    """
    Make sure preview UV dictionaries exist.

    preview_uv_positions:
        preview uv id -> (u, v)

    preview_uv_original_ids:
        preview uv id -> original Maya uv id

    next_preview_uv_id:
        fake preview ids allocated above original uv id range
    """

    if not hasattr(mesh_data, "preview_uv_positions"):
        mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)

    if not hasattr(mesh_data, "preview_uv_original_ids"):
        mesh_data.preview_uv_original_ids = {}

        for uv_id in mesh_data.uv_positions:
            mesh_data.preview_uv_original_ids[uv_id] = uv_id

    if not hasattr(mesh_data, "next_preview_uv_id"):
        if mesh_data.preview_uv_positions:
            mesh_data.next_preview_uv_id = max(mesh_data.preview_uv_positions.keys()) + 1
        else:
            mesh_data.next_preview_uv_id = 0


def allocate_preview_uv_id(mesh_data, source_uv_id):
    """
    Allocate a new preview UV id copied from an existing preview/original UV id.
    """

    ensure_preview_uv_storage(mesh_data)

    new_uv_id = mesh_data.next_preview_uv_id
    mesh_data.next_preview_uv_id += 1

    if source_uv_id in mesh_data.preview_uv_positions:
        source_pos = mesh_data.preview_uv_positions[source_uv_id]
    else:
        source_pos = mesh_data.uv_positions[source_uv_id]

    mesh_data.preview_uv_positions[new_uv_id] = source_pos

    if source_uv_id in mesh_data.preview_uv_original_ids:
        mesh_data.preview_uv_original_ids[new_uv_id] = mesh_data.preview_uv_original_ids[source_uv_id]
    else:
        mesh_data.preview_uv_original_ids[new_uv_id] = source_uv_id

    return new_uv_id


def rebuild_preview_topology(mesh_data):
    """
    Rebuild edges, adjacency, and shells from mesh_data.faces.

    This is needed after preview UV ids are split/remapped.
    """

    mesh_data.edges = []
    mesh_data.adjacency = defaultdict(set)
    mesh_data.shells = []

    unique_edges = set()

    for face_uv_ids in mesh_data.faces:
        for i, uv_a in enumerate(face_uv_ids):
            uv_b = face_uv_ids[(i + 1) % len(face_uv_ids)]

            edge_key = tuple(sorted((uv_a, uv_b)))

            if edge_key not in unique_edges:
                unique_edges.add(edge_key)
                mesh_data.edges.append((uv_a, uv_b))

            mesh_data.adjacency[uv_a].add(uv_b)
            mesh_data.adjacency[uv_b].add(uv_a)

    build_shells(mesh_data)


def split_faces_to_preview_shell(mesh_data, face_indices):
    """
    Split selected faces into their own preview UV island.

    This does NOT touch Maya.

    Only UV ids shared with unselected faces are duplicated.
    This prevents selected faces from pulling the original shell while keeping
    selected faces internally connected.
    """

    if not face_indices:
        return False

    ensure_preview_uv_storage(mesh_data)

    selected_face_indices = set(face_indices)

    # Find UV ids used by unselected faces.
    outside_uv_ids = set()

    for face_index, face_uv_ids in enumerate(mesh_data.faces):
        if face_index in selected_face_indices:
            continue

        for uv_id in face_uv_ids:
            outside_uv_ids.add(uv_id)

    # old preview uv id -> duplicated preview uv id
    duplicated_uv_ids = {}

    did_split = False

    for face_index in sorted(selected_face_indices):
        if face_index < 0:
            continue

        if face_index >= len(mesh_data.faces):
            continue

        face_uv_ids = mesh_data.faces[face_index]
        new_face_uv_ids = []

        for old_uv_id in face_uv_ids:
            # Only duplicate if this UV is shared with faces outside selection.
            if old_uv_id in outside_uv_ids:
                if old_uv_id not in duplicated_uv_ids:
                    duplicated_uv_ids[old_uv_id] = allocate_preview_uv_id(
                        mesh_data,
                        old_uv_id
                    )

                new_face_uv_ids.append(
                    duplicated_uv_ids[old_uv_id]
                )

                did_split = True

            else:
                # Keep internal selected-face UVs shared.
                new_face_uv_ids.append(old_uv_id)

        # Mutate in place so face_index based selection remains valid.
        face_uv_ids[:] = new_face_uv_ids

    if did_split:
        rebuild_preview_topology(mesh_data)

    return True

def apply_preview_to_maya(uv_cache):
    """
    Apply viewer preview UVs back to Maya.

    Supports:
    - moved original UVs
    - fitted UVs
    - rotated UVs
    - preview-split UV ids created by split_faces_to_preview_shell()

    This function writes:
    - new UV positions
    - new UV ids for split face corners
    - updated UV assignments for affected mesh faces
    """

    if not uv_cache or not uv_cache.has_data():
        cmds.warning("[eTrim] No UV cache to apply.")
        print("[eTrim] No UV cache to apply.")
        return False

    cmds.undoInfo(openChunk=True)

    try:
        applied_mesh_count = 0

        for mesh_data in uv_cache.meshes:
            if not mesh_data.preview_uv_positions:
                continue

            dag_path = get_mesh_dag_path(mesh_data.mesh_name)
            mesh_fn = om.MFnMesh(dag_path)

            uv_set = mesh_data.uv_set

            # -------------------------------------------------
            # Read current Maya UV arrays.
            # -------------------------------------------------

            current_u_array, current_v_array = mesh_fn.getUVs(uv_set)

            new_u_values = [
                float(value)
                for value in current_u_array
            ]

            new_v_values = [
                float(value)
                for value in current_v_array
            ]

            preview_to_maya_uv_id = {}

            # -------------------------------------------------
            # Build preview UV id -> actual Maya UV id mapping.
            # Existing preview ids keep their original Maya id.
            # New preview ids are appended as real Maya UVs.
            # -------------------------------------------------

            preview_uv_ids = sorted(mesh_data.preview_uv_positions.keys())

            for preview_uv_id in preview_uv_ids:
                u, v = mesh_data.preview_uv_positions[preview_uv_id]

                original_uv_id = mesh_data.preview_uv_original_ids.get(
                    preview_uv_id,
                    preview_uv_id
                )

                if preview_uv_id < len(new_u_values):
                    maya_uv_id = preview_uv_id

                    new_u_values[maya_uv_id] = float(u)
                    new_v_values[maya_uv_id] = float(v)

                elif original_uv_id < len(new_u_values):
                    maya_uv_id = len(new_u_values)

                    new_u_values.append(float(u))
                    new_v_values.append(float(v))

                else:
                    maya_uv_id = len(new_u_values)

                    new_u_values.append(float(u))
                    new_v_values.append(float(v))

                preview_to_maya_uv_id[preview_uv_id] = maya_uv_id

            # -------------------------------------------------
            # Push UV position array.
            # -------------------------------------------------

            mesh_fn.setUVs(
                om.MFloatArray(new_u_values),
                om.MFloatArray(new_v_values),
                uv_set
            )

            # -------------------------------------------------
            # Rebuild UV assignment for the whole mesh.
            # We preserve existing assignments for untouched faces,
            # then override cached faces with preview topology.
            # -------------------------------------------------

            cached_face_map = {}

            for local_face_index, polygon_id in enumerate(mesh_data.face_polygon_ids):
                if local_face_index >= len(mesh_data.faces):
                    continue

                cached_face_map[polygon_id] = mesh_data.faces[local_face_index]

            polygon_count = mesh_fn.numPolygons

            uv_counts = []
            uv_ids = []

            for polygon_id in range(polygon_count):
                vertex_count = mesh_fn.polygonVertexCount(polygon_id)
                uv_counts.append(vertex_count)

                if polygon_id in cached_face_map:
                    preview_face_uv_ids = cached_face_map[polygon_id]

                    for preview_uv_id in preview_face_uv_ids:
                        maya_uv_id = preview_to_maya_uv_id.get(
                            preview_uv_id,
                            preview_uv_id
                        )

                        uv_ids.append(int(maya_uv_id))

                else:
                    for local_vertex_id in range(vertex_count):
                        maya_uv_id = get_polygon_uv_id(
                            mesh_fn,
                            polygon_id,
                            local_vertex_id,
                            uv_set
                        )

                        uv_ids.append(int(maya_uv_id))

            mesh_fn.assignUVs(
                om.MIntArray(uv_counts),
                om.MIntArray(uv_ids),
                uv_set
            )

            mesh_fn.updateSurface()

            applied_mesh_count += 1

        print("[eTrim] Applied preview UVs to Maya.")
        print("        meshes:", applied_mesh_count)

        cmds.refresh()
        return applied_mesh_count > 0

    except Exception as exc:
        cmds.warning("[eTrim] Failed to apply preview UVs to Maya.")
        print("[eTrim] Failed to apply preview UVs to Maya:")
        print(exc)
        raise

    finally:
        cmds.undoInfo(closeChunk=True)

def build_cache_from_selection():
    """
    Main public function.

    Reads selected Maya components in bulk and returns an EUVCache.
    """

    face_components = get_selected_face_components()
    grouped = group_faces_by_object(face_components)

    cache = EUVCache()
    cache.source_selection = cmds.ls(sl=True, fl=True) or []

    for object_name, face_ids in grouped.items():
        mesh_data = build_mesh_uv_data(
            object_name,
            face_ids
        )

        cache.meshes.append(mesh_data)

    print("[eTrim] Loaded UV cache:")
    print("        meshes:", len(cache.meshes))

    for mesh_data in cache.meshes:
        print(
            "        {} | uv_set={} | uvs={} | edges={} | faces={} | shells={}".format(
                mesh_data.mesh_name,
                mesh_data.uv_set,
                len(mesh_data.uv_positions),
                len(mesh_data.edges),
                len(mesh_data.faces),
                len(mesh_data.shells)
            )
        )

    return cache