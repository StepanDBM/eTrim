# ET_core/ET_uv_model.py

import re
from collections import defaultdict, deque

from maya import cmds
import maya.api.OpenMaya as om

from ET_core.ET_heatmap import EStretchHeatMapCalculator

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

        # face index in mesh_data.faces -> Maya mesh edge ids in face order
        self.face_edge_ids = []

        # Maya edge id -> set(Maya polygon ids)
        self.edge_polygon_ids = defaultdict(set)

        # Maya mesh edges that must become persistent UV borders on Apply.
        self.pending_uv_cut_edge_ids = set()

        # uv_id -> set(connected uv ids)
        self.adjacency = defaultdict(set)

        # [EUVShellData, ...]
        self.shells = []
        
        # face index in mesh_data.faces -> world/object-space polygon area
        self.face_world_areas = []


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

def build_mesh_edge_polygon_map(dag_path):
    """
    Return Maya mesh edge topology.

    Returns:
        edge_polygon_ids:
            edge_id -> set(connected Maya polygon ids)

        vertex_pair_to_edge_id:
            sorted(vertex_a, vertex_b) -> Maya edge id
    """

    edge_polygon_ids = defaultdict(set)
    vertex_pair_to_edge_id = {}

    edge_iterator = om.MItMeshEdge(dag_path)

    while not edge_iterator.isDone():
        edge_id = edge_iterator.index()

        vertex_a = edge_iterator.vertexId(0)
        vertex_b = edge_iterator.vertexId(1)

        vertex_key = tuple(
            sorted(
                (
                    int(vertex_a),
                    int(vertex_b)
                )
            )
        )

        vertex_pair_to_edge_id[vertex_key] = int(edge_id)

        connected_faces = edge_iterator.getConnectedFaces()

        for polygon_id in connected_faces:
            edge_polygon_ids[int(edge_id)].add(
                int(polygon_id)
            )

        edge_iterator.next()

    return edge_polygon_ids, vertex_pair_to_edge_id

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
    world_points = mesh_fn.getPoints(om.MSpace.kWorld)

    edge_polygon_ids, vertex_pair_to_edge_id = build_mesh_edge_polygon_map(
        dag_path
    )

    mesh_data.edge_polygon_ids = edge_polygon_ids

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

        polygon_vertex_ids = mesh_fn.getPolygonVertices(polygon_id)

        face_edge_ids = []

        for index, vertex_a in enumerate(polygon_vertex_ids):
            vertex_b = polygon_vertex_ids[
                (index + 1
                ) % len(polygon_vertex_ids)
            ]

            vertex_key = tuple(sorted((int(vertex_a), int(vertex_b))))

            edge_id = vertex_pair_to_edge_id.get(vertex_key)

            if edge_id is None:
                raise RuntimeError(
                    "[eTrim] Could not resolve Maya edge for polygon {} vertices {}."
                    .format(polygon_id, vertex_key)
                )

            face_edge_ids.append(int(edge_id))

        mesh_data.face_edge_ids.append(face_edge_ids)

        polygon_world_points = [
            world_points[vertex_id]
            for vertex_id in polygon_vertex_ids
        ]

        mesh_data.face_world_areas.append(
            EStretchHeatMapCalculator.polygon_area_3d(polygon_world_points)
            )

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

def get_complete_face_indices_from_uv_ids(mesh_data, selected_uv_ids):
    """
    Return face indices whose all preview UV ids are selected.

    This lets vertex selections behave like face-island edits when the selected
    vertices actually describe complete faces.
    """

    if not mesh_data:
        return []

    selected_uv_ids = set(selected_uv_ids)

    if not selected_uv_ids:
        return []

    face_indices = []

    for face_index, face_uv_ids in enumerate(mesh_data.faces):
        if not face_uv_ids:
            continue

        all_face_uvs_selected = True

        for uv_id in face_uv_ids:
            if uv_id not in selected_uv_ids:
                all_face_uvs_selected = False
                break

        if all_face_uvs_selected:
            face_indices.append(face_index)

    return face_indices


def get_uv_pairs_from_face_indices(mesh_data, face_indices):
    """
    Return unique UV pairs from given face indices.

    Returns:
        [(mesh_data, uv_id), ...]
    """

    if not mesh_data:
        return []

    uv_pairs = []
    seen = set()

    for face_index in face_indices:
        if face_index < 0:
            continue

        if face_index >= len(mesh_data.faces):
            continue

        for uv_id in mesh_data.faces[face_index]:
            key = (
                id(mesh_data),
                uv_id
            )

            if key in seen:
                continue

            seen.add(key)

            uv_pairs.append(
                (
                    mesh_data,
                    uv_id
                )
            )

    return uv_pairs


def prepare_vertex_uvs_for_preview_edit(mesh_data, selected_uv_ids):
    """
    Prepare selected UV vertices for a preview edit.

    Behavior:
        - If selected vertices form complete faces, split those complete faces
          into their own preview shell, then return the updated preview UV ids.
        - If selected vertices do not form complete faces, return the selected
          UV ids directly.

    This is the vertex equivalent of split_faces_to_preview_shell(), but it
    avoids inventing a fake shell from disconnected single vertices.
    """

    if not mesh_data:
        return []

    selected_uv_ids = set(selected_uv_ids)

    if not selected_uv_ids:
        return []

    ensure_preview_uv_storage(mesh_data)

    complete_face_indices = get_complete_face_indices_from_uv_ids(
        mesh_data,
        selected_uv_ids
    )

    if complete_face_indices:
        split_faces_to_preview_shell(
            mesh_data,
            complete_face_indices
        )

        return get_uv_pairs_from_face_indices(
            mesh_data,
            complete_face_indices
        )

    uv_pairs = []
    seen = set()

    for uv_id in selected_uv_ids:
        if uv_id not in mesh_data.preview_uv_positions:
            continue

        key = (
            id(mesh_data),
            uv_id
        )

        if key in seen:
            continue

        seen.add(key)

        uv_pairs.append(
            (
                mesh_data,
                uv_id
            )
        )

    return uv_pairs

def get_selected_region_boundary_edge_ids(mesh_data, face_indices):
    """
    Return real Maya mesh edges on the outer boundary of a selected face region.

    An edge is included when:
        - at least one selected polygon uses the edge
        - at least one connected polygon is outside the selected region

    Internal edges between selected faces are not cut.
    """

    if not mesh_data or not face_indices:
        return set()

    selected_face_indices = set(face_indices)
    selected_polygon_ids = set()

    for face_index in selected_face_indices:
        if face_index < 0:
            continue

        if face_index >= len(mesh_data.face_polygon_ids):
            continue

        selected_polygon_ids.add(
            int(mesh_data.face_polygon_ids[face_index])
        )

    boundary_edge_ids = set()

    for face_index in selected_face_indices:
        if face_index < 0:
            continue

        if face_index >= len(mesh_data.face_edge_ids):
            continue

        face_edge_ids = mesh_data.face_edge_ids[face_index]

        for edge_id in face_edge_ids:
            edge_id = int(edge_id)

            connected_polygon_ids = mesh_data.edge_polygon_ids.get(
                edge_id,
                set()
            )

            has_selected_polygon = False
            has_outside_polygon = False

            for polygon_id in connected_polygon_ids:
                polygon_id = int(polygon_id)

                if polygon_id in selected_polygon_ids:
                    has_selected_polygon = True
                else:
                    has_outside_polygon = True

            # Internal edges between selected faces are not cut.
            #
            # Mesh boundary edges only have one connected polygon and already
            # represent an open mesh boundary, so they do not need polyMapCut.
            if has_selected_polygon and has_outside_polygon:
                boundary_edge_ids.add(edge_id)

    return boundary_edge_ids

def split_faces_to_preview_shell(mesh_data, face_indices, duplicate_all=False):
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

    boundary_edge_ids = get_selected_region_boundary_edge_ids(
        mesh_data, selected_face_indices
    )

    mesh_data.pending_uv_cut_edge_ids.update(boundary_edge_ids)

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
            should_duplicate = (duplicate_all or old_uv_id in outside_uv_ids)

            if should_duplicate:
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

    return bool(did_split or boundary_edge_ids)

def apply_pending_uv_cuts_to_maya(mesh_data):
    """
    Apply queued eTrim detach boundaries as native Maya UV cuts.

    Returns:
        number of Maya mesh edges cut
    """

    edge_ids = sorted(
        set(getattr(
                mesh_data,
                "pending_uv_cut_edge_ids",
                set()
            )
        )
    )

    if not edge_ids:
        return 0

    try:
        cmds.polyUVSet(
            mesh_data.mesh_name,
            currentUVSet=True,
            uvSet=mesh_data.uv_set
        )
    except Exception:
        pass

    edge_components = [
        "{}.e[{}]".format(mesh_data.mesh_name, edge_id)
        for edge_id in edge_ids
    ]

    cmds.polyMapCut(edge_components, constructionHistory=True)
    cmds.dgdirty(mesh_data.mesh_name)
    cmds.refresh(force=True)

    print("[eTrim] Applied persistent Maya UV cuts:")
    print("        mesh:", mesh_data.mesh_name)
    print("        edges:", len(edge_ids))

    return len(edge_ids)

def build_desired_polygon_corner_positions(mesh_data):
    """
    Capture desired preview coordinates by Maya polygon corner.

    Returns:
        polygon_id -> [(u, v), ...]
    """

    desired_positions = {}

    for local_face_index, polygon_id in enumerate(mesh_data.face_polygon_ids):
        if local_face_index >= len(mesh_data.faces):
            continue

        face_uv_ids = mesh_data.faces[local_face_index]
        face_positions = []

        for preview_uv_id in face_uv_ids:
            if preview_uv_id in mesh_data.preview_uv_positions:
                position = mesh_data.preview_uv_positions[preview_uv_id]
            else:
                position = mesh_data.uv_positions[preview_uv_id]

            face_positions.append(
                (
                    float(position[0]),
                    float(position[1])
                )
            )

        desired_positions[int(polygon_id)] = face_positions

    return desired_positions

def apply_maya_uv_positions(
    mesh_data,
    positions_by_maya_uv_id
):
    """
    Apply absolute UV positions through Maya commands.

    This creates persistent Maya UV edits after polyMapCut, rather than
    modifying only the currently evaluated mesh output.

    positions_by_maya_uv_id:
        {
            maya_uv_id: (u, v)
        }
    """

    if not mesh_data or not positions_by_maya_uv_id:
        return 0

    try:
        cmds.polyUVSet(
            mesh_data.mesh_name,
            currentUVSet=True,
            uvSet=mesh_data.uv_set
        )
    except Exception:
        pass

    applied_count = 0

    for maya_uv_id, position in positions_by_maya_uv_id.items():
        maya_uv_id = int(maya_uv_id)

        if maya_uv_id < 0:
            continue

        uv_component = "{}.map[{}]".format(
            mesh_data.mesh_name,
            maya_uv_id
        )

        try:
            cmds.polyEditUV(
                uv_component,
                relative=False,
                uValue=float(position[0]),
                vValue=float(position[1]),
                uvSetName=mesh_data.uv_set
            )

            applied_count += 1

        except TypeError:
            # Compatibility fallback for Maya versions that accept u/v
            # aliases but not the long uValue/vValue keyword names.
            cmds.polyEditUV(
                uv_component,
                relative=False,
                u=float(position[0]),
                v=float(position[1]),
                uvSetName=mesh_data.uv_set
            )

            applied_count += 1

        except Exception as exc:
            print("[eTrim] Could not apply Maya UV position:")
            print("        mesh:", mesh_data.mesh_name)
            print("        uv id:", maya_uv_id)
            print(exc)

    return applied_count

def apply_preview_to_maya(uv_cache):
    """
    Apply preview UV topology and positions to Maya.

    Topology changes:
        Queued detach edges are applied with native polyMapCut.

    Position changes:
        Preview positions are written to the real post-cut Maya UV ids.

    The UV cache is then rebuilt from Maya.
    """

    if not uv_cache or not uv_cache.has_data():
        cmds.warning("[eTrim] No UV cache to apply.")
        print("[eTrim] No UV cache to apply.")
        return False

    cmds.undoInfo(
        openChunk=True,
        chunkName="eTrim Apply Preview UVs"
    )

    try:
        applied_mesh_count = 0

        for mesh_data in uv_cache.meshes:
            if not mesh_data.preview_uv_positions:
                continue

            # Preserve desired coordinates by polygon corner before Maya
            # generates new UV ids for detached borders.
            desired_polygon_positions = build_desired_polygon_corner_positions(
                mesh_data
            )

            cut_count = apply_pending_uv_cuts_to_maya(
                mesh_data
            )

            # Re-query the evaluated output after polyMapCut.
            dag_path = get_mesh_dag_path(mesh_data.mesh_name)
            mesh_fn = om.MFnMesh(dag_path)
            uv_set = mesh_data.uv_set

            try:
                mesh_fn.setCurrentUVSetName(uv_set)
            except Exception:
                pass

            current_u_array, current_v_array = mesh_fn.getUVs(uv_set)

            new_u_values = [
                float(value)
                for value in current_u_array
            ]

            new_v_values = [
                float(value)
                for value in current_v_array
            ]

            desired_position_by_maya_uv_id = {}
            conflicting_uv_ids = set()

            # Maya now owns the split topology. Query every cached polygon
            # corner to find the real UV ids created by polyMapCut.
            for polygon_id, desired_positions in desired_polygon_positions.items():
                vertex_count = mesh_fn.polygonVertexCount(polygon_id)

                if vertex_count != len(desired_positions):
                    raise RuntimeError(
                        "[eTrim] Polygon corner count changed for polygon {}."
                        .format(
                            polygon_id
                        )
                    )

                for local_vertex_id in range(vertex_count):
                    maya_uv_id = get_polygon_uv_id(
                        mesh_fn,
                        polygon_id,
                        local_vertex_id,
                        uv_set
                    )

                    maya_uv_id = int(maya_uv_id)
                    desired_position = desired_positions[local_vertex_id]

                    if maya_uv_id in desired_position_by_maya_uv_id:
                        previous_position = desired_position_by_maya_uv_id[
                            maya_uv_id
                        ]

                        du = abs(
                            previous_position[0] - desired_position[0]
                        )

                        dv = abs(
                            previous_position[1] - desired_position[1]
                        )

                        if du > 0.000001 or dv > 0.000001:
                            conflicting_uv_ids.add(maya_uv_id)

                    else:
                        desired_position_by_maya_uv_id[maya_uv_id] = (
                            float(desired_position[0]),
                            float(desired_position[1])
                        )

            if conflicting_uv_ids:
                raise RuntimeError(
                    "[eTrim] Maya UV cuts did not separate all required "
                    "corners. Conflicting Maya UV ids: {}"
                    .format(
                        sorted(conflicting_uv_ids)
                    )
                )

            # -------------------------------------------------
            # Apply preview positions as persistent Maya UV edits.
            #
            # Do not use MFnMesh.setUVs() here. After polyMapCut creates a
            # construction-history node, direct output-mesh UV writes can be
            # replaced the next time Maya evaluates the history chain.
            # -------------------------------------------------

            for maya_uv_id in desired_position_by_maya_uv_id.keys():
                if maya_uv_id < 0:
                    raise RuntimeError(
                        "[eTrim] Invalid negative Maya UV id after cut: {}"
                        .format(
                            maya_uv_id
                        )
                    )

                if maya_uv_id >= len(new_u_values):
                    raise RuntimeError(
                        "[eTrim] Invalid Maya UV id after cut: {}"
                        .format(
                            maya_uv_id
                        )
                    )

            positioned_uv_count = apply_maya_uv_positions(
                mesh_data,
                desired_position_by_maya_uv_id
            )

            if positioned_uv_count <= 0:
                raise RuntimeError(
                    "[eTrim] Maya accepted no UV position updates for mesh: {}"
                    .format(
                        mesh_data.mesh_name
                    )
                )

            try:
                cmds.dgdirty(mesh_data.mesh_name)
            except Exception:
                pass

            cmds.refresh(force=True)

            try:
                shell_count = cmds.polyEvaluate(
                    mesh_data.mesh_name,
                    uvShell=True
                )
            except Exception:
                shell_count = None

            print("[eTrim] Applied preview UVs to mesh:")
            print("        mesh:", mesh_data.mesh_name)
            print("        persistent cut edges:", cut_count)
            print("        requested Maya UVs:", len(desired_position_by_maya_uv_id))
            print("        positioned Maya UVs:", positioned_uv_count)
            print("        Maya UV shells:", shell_count)

            # Rebuild from Maya's real post-cut UV topology.
            replace_mesh_data_from_maya(mesh_data)

            applied_mesh_count += 1

        print("[eTrim] Applied preview UVs to Maya.")
        print("        meshes:", applied_mesh_count)

        cmds.refresh(force=True)

        return applied_mesh_count > 0

    except Exception as exc:
        cmds.warning("[eTrim] Failed to apply preview UVs to Maya.")
        print("[eTrim] Failed to apply preview UVs to Maya:")
        print(exc)
        raise

    finally:
        cmds.undoInfo(closeChunk=True)

def replace_mesh_data_from_maya(mesh_data):
    """
    Re-read the cached polygon set from Maya while preserving mesh_data identity.

    Preserving object identity avoids invalidating viewer references.
    """

    refreshed_data = build_mesh_uv_data(
        mesh_data.mesh_name,
        mesh_data.face_polygon_ids
    )

    mesh_data.uv_set = refreshed_data.uv_set
    mesh_data.uv_positions = refreshed_data.uv_positions
    mesh_data.preview_uv_positions = refreshed_data.preview_uv_positions
    mesh_data.preview_uv_original_ids = refreshed_data.preview_uv_original_ids
    mesh_data.next_preview_uv_id = refreshed_data.next_preview_uv_id

    mesh_data.edges = refreshed_data.edges
    mesh_data.faces = refreshed_data.faces
    mesh_data.face_polygon_ids = refreshed_data.face_polygon_ids
    mesh_data.face_edge_ids = refreshed_data.face_edge_ids
    mesh_data.edge_polygon_ids = refreshed_data.edge_polygon_ids
    mesh_data.adjacency = refreshed_data.adjacency
    mesh_data.shells = refreshed_data.shells
    mesh_data.face_world_areas = refreshed_data.face_world_areas

    mesh_data.pending_uv_cut_edge_ids = set()

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