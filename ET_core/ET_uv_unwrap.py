# ET_core/ET_uv_unwrap.py

import maya.cmds as cmds
import maya.mel as mel
import maya.api.OpenMaya as om

from ET_core import ET_uv_model


TEMP_PREFIX = "ET_unwrap_TEMP_"


def safe_delete(node):
    if node and cmds.objExists(node):
        try:
            cmds.delete(node)
        except Exception:
            pass


def get_mesh_transform(mesh_name):
    """
    Return a transform for a mesh_data.mesh_name.

    mesh_name may already be a transform or may be a shape.
    """

    if not mesh_name:
        return None

    if not cmds.objExists(mesh_name):
        return None

    node_type = cmds.nodeType(mesh_name)

    if node_type == "transform":
        return mesh_name

    if node_type == "mesh":
        parents = cmds.listRelatives(
            mesh_name,
            parent=True,
            fullPath=True
        ) or []

        if parents:
            return parents[0]

    return None


def duplicate_mesh_for_unwrap(mesh_name):
    """
    Duplicate a mesh transform for temporary unwrap work.

    Returns:
        temp_transform or None
    """

    transform = get_mesh_transform(mesh_name)

    if not transform:
        print("[eTrim] Could not resolve mesh transform:", mesh_name)
        return None

    duplicates = cmds.duplicate(
        transform,
        name=TEMP_PREFIX + transform.split("|")[-1]
    ) or []

    if not duplicates:
        print("[eTrim] Could not duplicate mesh:", transform)
        return None

    temp_transform = duplicates[0]

    # Make sure temp object is visible/selectable enough for commands.
    try:
        cmds.setAttr(
            "{}.visibility".format(temp_transform),
            True
        )
    except Exception:
        pass

    return temp_transform

def get_temp_mesh_dag_path(temp_transform):
    """
    Resolve the temporary mesh transform to a mesh MDagPath.
    """

    temp_shape = get_temp_shape(
        temp_transform
    )

    if not temp_shape:
        return None

    selection_list = om.MSelectionList()
    selection_list.add(temp_shape)

    dag_path = selection_list.getDagPath(0)

    if not dag_path.node().hasFn(om.MFn.kMesh):
        return None

    return dag_path

def apply_preview_cuts_to_temp_mesh(temp_transform, mesh_data):
    """
    Recreate queued preview detach borders on the temporary unwrap mesh.

    The edge IDs remain valid because the temporary mesh is a duplicate of
    the source mesh and its polygon topology is unchanged.
    """

    if not temp_transform or not mesh_data:
        return False

    edge_ids = sorted(
        set(
            getattr(
                mesh_data,
                "pending_uv_cut_edge_ids",
                set()
            )
        )
    )

    if not edge_ids:
        return True

    try:
        cmds.polyUVSet(
            temp_transform,
            currentUVSet=True,
            uvSet=mesh_data.uv_set
        )
    except Exception:
        pass

    edge_components = [
        "{}.e[{}]".format(
            temp_transform,
            edge_id
        )
        for edge_id in edge_ids
    ]

    try:
        cmds.polyMapCut(
            edge_components,
            constructionHistory=False
        )

        cmds.refresh(
            force=True
        )

        print("[eTrim] Applied preview cuts to temp unwrap mesh:")
        print("        edges:", len(edge_ids))

        return True

    except Exception as exc:
        print("[eTrim] Failed to cut temp unwrap mesh:")
        print(exc)
        return False

def get_temp_shape(temp_transform):
    shapes = cmds.listRelatives(
        temp_transform,
        shapes=True,
        fullPath=True,
        noIntermediate=True
    ) or []

    for shape in shapes:
        if cmds.nodeType(shape) == "mesh":
            return shape

    return None


def get_temp_uv_component(temp_transform, uv_id):
    return "{}.map[{}]".format(
        temp_transform,
        int(uv_id)
    )


def get_temp_face_component(temp_transform, face_index):
    return "{}.f[{}]".format(
        temp_transform,
        int(face_index)
    )

def apply_preview_uvs_to_temp_mesh(temp_transform, mesh_data):
    """
    Apply preview coordinates to the temporary mesh by polygon corner.

    Preview-only UV IDs do not need to match temp Maya UV IDs. The mapping is
    resolved through each cached polygon corner after temp UV cuts are applied.
    """

    if not temp_transform or not mesh_data:
        return False

    dag_path = get_temp_mesh_dag_path(
        temp_transform
    )

    if not dag_path:
        return False

    mesh_fn = om.MFnMesh(
        dag_path
    )

    uv_set = mesh_data.uv_set

    try:
        mesh_fn.setCurrentUVSetName(
            uv_set
        )
    except Exception:
        pass

    u_array, v_array = mesh_fn.getUVs(
        uv_set
    )

    new_u_values = [
        float(value)
        for value in u_array
    ]

    new_v_values = [
        float(value)
        for value in v_array
    ]

    desired_by_temp_uv_id = {}
    conflicting_uv_ids = set()

    for local_face_index, polygon_id in enumerate(mesh_data.face_polygon_ids):
        if local_face_index >= len(mesh_data.faces):
            continue

        preview_face_uv_ids = mesh_data.faces[local_face_index]
        vertex_count = mesh_fn.polygonVertexCount(
            polygon_id
        )

        if vertex_count != len(preview_face_uv_ids):
            continue

        for local_vertex_id in range(vertex_count):
            preview_uv_id = preview_face_uv_ids[local_vertex_id]

            if preview_uv_id not in mesh_data.preview_uv_positions:
                continue

            temp_uv_id = ET_uv_model.get_polygon_uv_id(
                mesh_fn,
                polygon_id,
                local_vertex_id,
                uv_set
            )

            temp_uv_id = int(
                temp_uv_id
            )

            position = mesh_data.preview_uv_positions[
                preview_uv_id
            ]

            desired_position = (
                float(position[0]),
                float(position[1])
            )

            if temp_uv_id in desired_by_temp_uv_id:
                previous_position = desired_by_temp_uv_id[temp_uv_id]

                du = abs(
                    previous_position[0] - desired_position[0]
                )

                dv = abs(
                    previous_position[1] - desired_position[1]
                )

                if du > 0.000001 or dv > 0.000001:
                    conflicting_uv_ids.add(
                        temp_uv_id
                    )
            else:
                desired_by_temp_uv_id[temp_uv_id] = desired_position

    if conflicting_uv_ids:
        print("[eTrim] Temp UV isolation is incomplete.")
        print("        conflicting UV ids:", sorted(conflicting_uv_ids))
        return False

    for temp_uv_id, position in desired_by_temp_uv_id.items():
        if temp_uv_id < 0:
            continue

        if temp_uv_id >= len(new_u_values):
            continue

        new_u_values[temp_uv_id] = position[0]
        new_v_values[temp_uv_id] = position[1]

    mesh_fn.setUVs(
        om.MFloatArray(new_u_values),
        om.MFloatArray(new_v_values),
        uv_set
    )

    mesh_fn.updateSurface()

    print("[eTrim] Applied preview UVs to temp mesh:")
    print("        UVs:", len(desired_by_temp_uv_id))

    return bool(
        desired_by_temp_uv_id
    )

def get_selected_face_indices_from_keys(selected_keys, mesh_data):
    """
    Convert viewer selected drawable keys into face indices for one mesh_data.
    """

    face_indices = []

    for key in selected_keys:
        if not key:
            continue

        if key[0] != "uv_face":
            continue

        if len(key) < 4:
            continue

        _, mesh_name, uv_set, face_index = key

        if mesh_name != mesh_data.mesh_name:
            continue

        if uv_set != mesh_data.uv_set:
            continue

        face_indices.append(
            int(face_index)
        )

    return sorted(set(face_indices))


def get_selected_shell_face_indices_from_keys(selected_keys, mesh_data):
    """
    Convert selected shell keys into face indices for one mesh_data.
    """

    shell_ids = set()

    for key in selected_keys:
        if not key:
            continue

        if key[0] != "uv_shell":
            continue

        if len(key) < 4:
            continue

        _, mesh_name, uv_set, shell_id = key

        if mesh_name != mesh_data.mesh_name:
            continue

        if uv_set != mesh_data.uv_set:
            continue

        shell_ids.add(shell_id)

    if not shell_ids:
        return []

    face_indices = []

    for shell_data in mesh_data.shells:
        if shell_data.shell_id not in shell_ids:
            continue

        for face_uv_ids in shell_data.faces:
            try:
                face_index = mesh_data.faces.index(face_uv_ids)
            except ValueError:
                continue

            face_indices.append(face_index)

    return sorted(set(face_indices))

def get_selected_vertex_complete_face_indices_from_keys(selected_keys, mesh_data):
    """
    Convert selected vertex keys into complete face indices for one mesh_data.

    Only faces whose every preview UV id is selected are returned.

    This prevents vertex-mode unwrap from falling back to the entire shell.
    """

    selected_uv_ids = set()

    for key in selected_keys:
        if not key:
            continue

        if key[0] != "uv_vertex":
            continue

        if len(key) < 4:
            continue

        _, mesh_name, uv_set, uv_id = key

        if mesh_name != mesh_data.mesh_name:
            continue

        if uv_set != mesh_data.uv_set:
            continue

        selected_uv_ids.add(
            int(uv_id)
        )

    if not selected_uv_ids:
        return []

    return ET_uv_model.get_complete_face_indices_from_uv_ids(
        mesh_data,
        selected_uv_ids
    )

def get_face_indices_for_unwrap(viewer, mesh_data):
    """
    Resolve selected components into mesh face indices.

    Priority:
        1. selected UV vertices, if current mode is vertex
        2. selected UV faces
        3. selected UV shells
        4. fallback to all faces only if there is no explicit UV component selection

    Important:
        In vertex mode, selected vertices must never accidentally unwrap the
        whole shell. If the selected vertices do not form complete faces,
        unwrap returns no faces.
    """

    if not viewer or not mesh_data:
        return []

    uv_mode = viewer.get_uv_selection_mode()

    selected_vertex_keys = viewer.get_selected_drawables_by_type(
        "uv_vertex"
    )

    selected_face_keys = viewer.get_selected_drawables_by_type(
        "uv_face"
    )

    selected_shell_keys = viewer.get_selected_drawables_by_type(
        "uv_shell"
    )

    # -----------------------------------------------------
    # Vertex mode has priority over stale face/shell selection.
    # -----------------------------------------------------

    if uv_mode == "vertex":
        face_indices = get_selected_vertex_complete_face_indices_from_keys(
            selected_vertex_keys,
            mesh_data
        )

        if face_indices:
            return face_indices

        if selected_vertex_keys:
            print(
                "[eTrim] Vertex unwrap skipped. Selected vertices do not form complete faces:"
            )
            print("        mesh:", mesh_data.mesh_name)
            return []

    # -----------------------------------------------------
    # Face mode has priority over stale shell selection.
    # -----------------------------------------------------

    if uv_mode == "face":
        face_indices = get_selected_face_indices_from_keys(
            selected_face_keys,
            mesh_data
        )

        if face_indices:
            return face_indices

        if selected_face_keys:
            return []

    # -----------------------------------------------------
    # Shell mode / generic shell selection.
    # -----------------------------------------------------

    if uv_mode == "shell":
        face_indices = get_selected_shell_face_indices_from_keys(
            selected_shell_keys,
            mesh_data
        )

        if face_indices:
            return face_indices

        if selected_shell_keys:
            return []

    # -----------------------------------------------------
    # Fallbacks for non-mode-specific calls.
    # -----------------------------------------------------

    face_indices = get_selected_face_indices_from_keys(
        selected_face_keys,
        mesh_data
    )

    if face_indices:
        return face_indices

    face_indices = get_selected_shell_face_indices_from_keys(
        selected_shell_keys,
        mesh_data
    )

    if face_indices:
        return face_indices

    # If any explicit UV selection exists, do not unwrap all faces.
    if selected_vertex_keys or selected_face_keys or selected_shell_keys:
        return []

    return list(range(len(mesh_data.faces)))

def prepare_faces_for_unwrap(mesh_data, face_indices):
    """
    Detach a partial face selection in preview before temporary unwrap.

    The selected faces remain connected to each other, while UVs shared with
    surrounding unselected faces are duplicated.

    Returns:
        True if preparation succeeded.
    """

    if not mesh_data or not face_indices:
        return False

    result = ET_uv_model.split_faces_to_preview_shell(
        mesh_data,
        face_indices,
        duplicate_all=False
    )

    if result:
        print("[eTrim] Prepared selected faces for isolated unwrap:")
        print("        mesh:", mesh_data.mesh_name)
        print("        faces:", len(face_indices))

    return result

def select_temp_faces(temp_transform, mesh_data, face_indices):
    """
    Select temp mesh faces using Maya polygon IDs.

    face_indices contains local mesh_data.faces indices, not necessarily
    Maya polygon IDs.
    """

    components = []

    for face_index in face_indices:
        if face_index < 0:
            continue

        if face_index >= len(mesh_data.face_polygon_ids):
            continue

        polygon_id = mesh_data.face_polygon_ids[face_index]

        components.append(
            get_temp_face_component(
                temp_transform,
                polygon_id
            )
        )

    if not components:
        return False

    cmds.select(
        components,
        replace=True
    )

    return True

def ensure_unfold3d_plugin_loaded():
    """
    Try to load Maya's unfold plugin.

    Plugin names vary across Maya versions, so try common names.
    """

    candidates = [
        "Unfold3D",
        "Unfold3D.mll",
        "u3dUnfold",
        "u3dUnfold.mll"
    ]

    for plugin_name in candidates:
        try:
            if cmds.pluginInfo(
                plugin_name,
                query=True,
                loaded=True
            ):
                return True
        except Exception:
            pass

    for plugin_name in candidates:
        try:
            cmds.loadPlugin(
                plugin_name,
                quiet=True
            )
            return True
        except Exception:
            pass

    return False


def run_native_unwrap(iterations=1, pack=False):
    """
    Run Maya native unwrap on current selection.

    First tries u3dUnfold. Falls back to cmds.unfold.
    """

    used_u3d = False

    if ensure_unfold3d_plugin_loaded():
        try:
            mel.eval(
                'u3dUnfold -ite {0} -p {1};'.format(
                    int(iterations),
                    "on" if pack else "off"
                )
            )

            used_u3d = True

        except Exception as exc:
            print("[eTrim] u3dUnfold failed, trying fallback unfold.")
            print(exc)

    if used_u3d:
        return True

    try:
        cmds.unfold(
            iterations=int(iterations),
            applyToShell=True,
            pinUvBorder=False
        )

        return True

    except Exception as exc:
        print("[eTrim] Fallback cmds.unfold failed.")
        print(exc)

    return False

def get_uv_values_for_temp_face_vertices(
    temp_transform,
    polygon_id,
    uv_set
):
    """
    Return temporary UV coordinates in polygon-corner order.

    This avoids relying on polyListComponentConversion ordering, which may not
    match the order of UV ids stored in mesh_data.faces.
    """

    dag_path = get_temp_mesh_dag_path(
        temp_transform
    )

    if not dag_path:
        return []

    mesh_fn = om.MFnMesh(
        dag_path
    )

    try:
        u_array, v_array = mesh_fn.getUVs(
            uv_set
        )
    except Exception as exc:
        print("[eTrim] Could not read temp mesh UVs:")
        print(exc)
        return []

    try:
        vertex_count = mesh_fn.polygonVertexCount(
            int(polygon_id)
        )
    except Exception as exc:
        print("[eTrim] Could not read temp polygon:")
        print("        polygon:", polygon_id)
        print(exc)
        return []

    result = []

    for local_vertex_id in range(vertex_count):
        try:
            uv_id = ET_uv_model.get_polygon_uv_id(
                mesh_fn,
                int(polygon_id),
                local_vertex_id,
                uv_set
            )

            uv_id = int(
                uv_id
            )

        except Exception as exc:
            print("[eTrim] Could not resolve temp polygon UV:")
            print("        polygon:", polygon_id)
            print("        local vertex:", local_vertex_id)
            print(exc)
            return []

        if uv_id < 0:
            return []

        if uv_id >= len(u_array):
            print("[eTrim] Temp UV id is outside UV array:")
            print("        polygon:", polygon_id)
            print("        uv id:", uv_id)
            print("        UV count:", len(u_array))
            return []

        result.append(
            (
                float(u_array[uv_id]),
                float(v_array[uv_id])
            )
        )

    return result

def write_temp_unwrap_result_to_preview(
    temp_transform,
    mesh_data,
    face_indices
):
    """
    Read temp unwrapped UVs and write them into preview UV positions.

    Readback is performed in polygon-corner order and maps directly onto the
    preview UV IDs stored in mesh_data.faces.
    """

    if not hasattr(mesh_data, "preview_uv_positions"):
        mesh_data.preview_uv_positions = dict(
            mesh_data.uv_positions
        )

    written_count = 0

    for face_index in face_indices:
        if face_index < 0:
            continue

        if face_index >= len(mesh_data.faces):
            continue

        if face_index >= len(mesh_data.face_polygon_ids):
            continue

        preview_face_uv_ids = mesh_data.faces[face_index]
        polygon_id = mesh_data.face_polygon_ids[face_index]

        temp_uv_values = get_uv_values_for_temp_face_vertices(
            temp_transform,
            polygon_id,
            mesh_data.uv_set
        )

        if not temp_uv_values:
            continue

        if len(preview_face_uv_ids) != len(temp_uv_values):
            print("[eTrim] Temp unwrap corner-count mismatch:")
            print("        face index:", face_index)
            print("        polygon id:", polygon_id)
            continue

        for local_index, preview_uv_id in enumerate(preview_face_uv_ids):
            mesh_data.preview_uv_positions[preview_uv_id] = (
                temp_uv_values[local_index]
            )

            written_count += 1

    print("[eTrim] Unwrap result written to preview UVs:", written_count)

    return written_count > 0

def unwrap_mesh_data_to_preview(viewer, mesh_data, iterations=1, pack=False):
    """
    Unwrap selected faces or shells into preview UVs.

    Partial face regions are detached in preview and recreated as UV cuts on
    the temporary mesh before Maya Unfold runs.
    """

    if not viewer or not mesh_data:
        return False

    face_indices = get_face_indices_for_unwrap(
        viewer,
        mesh_data
    )

    if not face_indices:
        print("[eTrim] No faces found for unwrap:", mesh_data.mesh_name)
        return False

    uv_mode = viewer.get_uv_selection_mode()

    if uv_mode in (
        "face",
        "vertex"
    ):
        prepare_faces_for_unwrap(
            mesh_data,
            face_indices
        )

    temp_transform = duplicate_mesh_for_unwrap(
        mesh_data.mesh_name
    )

    if not temp_transform:
        return False

    try:
        # The temp mesh must have the same shell boundaries as the preview
        # before preview positions are mapped onto temp Maya UV IDs.
        if not apply_preview_cuts_to_temp_mesh(
            temp_transform,
            mesh_data
        ):
            print("[eTrim] Could not isolate temp faces for unwrap.")
            return False

        if not apply_preview_uvs_to_temp_mesh(
            temp_transform,
            mesh_data
        ):
            print("[eTrim] Could not apply preview UVs to temp mesh.")
            return False

        if not select_temp_faces(
            temp_transform,
            mesh_data,
            face_indices
        ):
            print("[eTrim] Could not select temp faces for unwrap.")
            return False

        if not run_native_unwrap(
            iterations=iterations,
            pack=pack
        ):
            return False

        return write_temp_unwrap_result_to_preview(
            temp_transform,
            mesh_data,
            face_indices
        )

    finally:
        safe_delete(
            temp_transform
        )

def unwrap_viewer_selection_to_preview(viewer, iterations=1, pack=False):
    """
    Unwrap current viewer selection into preview UV cache.

    Returns:
        True if anything was unwrapped.
    """

    if not viewer:
        return False

    uv_cache = getattr(
        viewer,
        "uv_cache",
        None
    )

    if not uv_cache or not uv_cache.has_data():
        print("[eTrim] No UV cache loaded for unwrap.")
        return False

    result = False

    for mesh_data in uv_cache.meshes:
        mesh_result = unwrap_mesh_data_to_preview(
            viewer,
            mesh_data,
            iterations=iterations,
            pack=pack
        )

        if mesh_result:
            result = True

    viewer.update()

    if result:
        print("[eTrim] Native unwrap preview complete.")
    else:
        print("[eTrim] Native unwrap preview produced no result.")

    return result