# ET_core/ET_uv_unwrap.py

import maya.cmds as cmds
import maya.mel as mel


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
    Apply current viewer preview UV positions to temp mesh.

    This only applies UV ids that exist as real UV ids on the temp mesh.
    Preview-only duplicated UV ids may not exist on temp. That is okay for
    first version because final readback is face-index based.
    """

    if not temp_transform or not mesh_data:
        return False

    positions = getattr(
        mesh_data,
        "preview_uv_positions",
        None
    )

    if not positions:
        positions = getattr(
            mesh_data,
            "uv_positions",
            {}
        )

    if not positions:
        return False

    applied_count = 0

    for uv_id, uv_pos in positions.items():
        if not isinstance(uv_id, int):
            continue

        u, v = uv_pos

        uv_component = get_temp_uv_component(
            temp_transform,
            uv_id
        )

        if not cmds.objExists(uv_component):
            continue

        try:
            cmds.polyEditUV(
                uv_component,
                u=float(u),
                v=float(v),
                relative=False
            )

            applied_count += 1

        except Exception:
            pass

    print("[eTrim] Applied preview UVs to temp mesh:", applied_count)

    return applied_count > 0


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


def get_face_indices_for_unwrap(viewer, mesh_data):
    """
    Resolve selected faces/shells into mesh face indices.

    Priority:
        selected UV faces
        selected UV shells
        all faces in mesh_data as fallback
    """

    selected_face_keys = viewer.get_selected_drawables_by_type(
        "uv_face"
    )

    face_indices = get_selected_face_indices_from_keys(
        selected_face_keys,
        mesh_data
    )

    if face_indices:
        return face_indices

    selected_shell_keys = viewer.get_selected_drawables_by_type(
        "uv_shell"
    )

    face_indices = get_selected_shell_face_indices_from_keys(
        selected_shell_keys,
        mesh_data
    )

    if face_indices:
        return face_indices

    return list(range(len(mesh_data.faces)))


def select_temp_faces(temp_transform, face_indices):
    components = [
        get_temp_face_component(
            temp_transform,
            face_index
        )
        for face_index in face_indices
    ]

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


def get_uv_values_for_temp_face_vertices(temp_transform, face_index):
    """
    Return UV coordinates for each face vertex of a temp mesh face.

    Returns:
        [(u, v), ...]
    """

    face_component = get_temp_face_component(
        temp_transform,
        face_index
    )

    uv_components = cmds.polyListComponentConversion(
        face_component,
        fromFace=True,
        toUV=True
    ) or []

    uv_components = cmds.filterExpand(
        uv_components,
        selectionMask=35,
        expand=True
    ) or []

    result = []

    for uv_component in uv_components:
        try:
            values = cmds.polyEditUV(
                uv_component,
                query=True
            )

            if values and len(values) >= 2:
                result.append(
                    (
                        float(values[0]),
                        float(values[1])
                    )
                )
        except Exception:
            pass

    return result


def write_temp_unwrap_result_to_preview(temp_transform, mesh_data, face_indices):
    """
    Read temp unwrapped UVs and write them into mesh_data.preview_uv_positions.

    This writes by face index and face UV order. That means it can write into
    preview UV ids even if those ids are preview-only split ids.
    """

    if not hasattr(mesh_data, "preview_uv_positions"):
        mesh_data.preview_uv_positions = dict(mesh_data.uv_positions)

    written_count = 0

    for face_index in face_indices:
        if face_index < 0:
            continue

        if face_index >= len(mesh_data.faces):
            continue

        preview_face_uv_ids = mesh_data.faces[face_index]

        temp_uv_values = get_uv_values_for_temp_face_vertices(
            temp_transform,
            face_index
        )

        if not temp_uv_values:
            continue

        count = min(
            len(preview_face_uv_ids),
            len(temp_uv_values)
        )

        for local_index in range(count):
            preview_uv_id = preview_face_uv_ids[local_index]
            mesh_data.preview_uv_positions[preview_uv_id] = temp_uv_values[local_index]
            written_count += 1

    print("[eTrim] Unwrap result written to preview UVs:", written_count)

    return written_count > 0


def unwrap_mesh_data_to_preview(viewer, mesh_data, iterations=1, pack=False):
    """
    Unwrap selected faces/shells for one mesh_data into preview cache.
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

    temp_transform = duplicate_mesh_for_unwrap(
        mesh_data.mesh_name
    )

    if not temp_transform:
        return False

    try:
        apply_preview_uvs_to_temp_mesh(
            temp_transform,
            mesh_data
        )

        if not select_temp_faces(
            temp_transform,
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
        safe_delete(temp_transform)


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