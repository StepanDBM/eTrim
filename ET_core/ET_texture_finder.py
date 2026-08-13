# ET_core/ET_texture_finder.py

import os

import maya.cmds as cmds


BASE_COLOR_ATTR_CANDIDATES = [
    "baseColor",      # standardSurface / aiStandardSurface
    "color",          # lambert / blinn / phong / surfaceShader
    "diffuseColor",   # some shader nodes
    "albedo",         # possible custom/native-ish naming
]


TEXTURE_FILE_ATTR_CANDIDATES = [
    "fileTextureName",    # Maya file node
    "filename",           # some image-style nodes
]


def get_mesh_shape(mesh_name):
    """
    Resolve a transform or shape name to a mesh shape.
    """

    if not mesh_name:
        return None

    if cmds.objExists(mesh_name):
        node_type = cmds.nodeType(mesh_name)

        if node_type == "mesh":
            return mesh_name

        shapes = cmds.listRelatives(
            mesh_name,
            shapes=True,
            fullPath=True,
            noIntermediate=True
        ) or []

        for shape in shapes:
            if cmds.nodeType(shape) == "mesh":
                return shape

    return None


def get_shading_engines_from_mesh(mesh_name):
    """
    Return shadingEngine nodes connected to a mesh.
    """

    shape = get_mesh_shape(mesh_name)

    if not shape:
        return []

    shading_engines = cmds.listConnections(
        shape,
        type="shadingEngine"
    ) or []

    # Stable unique list.
    result = []

    for shading_engine in shading_engines:
        if shading_engine not in result:
            result.append(shading_engine)

    return result


def get_surface_shader_from_shading_engine(shading_engine):
    """
    Return the shader connected to shadingEngine.surfaceShader.
    """

    if not shading_engine:
        return None

    plug = "{}.surfaceShader".format(shading_engine)

    connections = cmds.listConnections(
        plug,
        source=True,
        destination=False
    ) or []

    if not connections:
        return None

    return connections[0]


def get_existing_attr_plug(node, attr_names):
    """
    Return first existing plug from attr_names.
    """

    if not node:
        return None

    for attr_name in attr_names:
        if cmds.attributeQuery(
            attr_name,
            node=node,
            exists=True
        ):
            return "{}.{}".format(
                node,
                attr_name
            )

    return None


def get_texture_path_from_node(node):
    """
    Return texture file path if node is a recognized texture node.
    """

    if not node:
        return None

    node_type = cmds.nodeType(node)

    # Main target for native Maya texture files.
    if node_type == "file":
        plug = "{}.fileTextureName".format(node)

        if cmds.objExists(plug):
            path = cmds.getAttr(plug)

            if path:
                return path

    # Generic fallback for image-like nodes.
    for attr_name in TEXTURE_FILE_ATTR_CANDIDATES:
        if cmds.attributeQuery(
            attr_name,
            node=node,
            exists=True
        ):
            plug = "{}.{}".format(
                node,
                attr_name
            )

            path = cmds.getAttr(plug)

            if path:
                return path

    return None


def get_upstream_source_plugs(plug_or_node):
    """
    Return incoming source plugs for a plug or node.

    If a plug is given:
        look for source plugs connected into that plug.

    If a node is given:
        look for all source plugs feeding the node.
    """

    if not plug_or_node:
        return []

    if "." in plug_or_node:
        plugs = cmds.listConnections(
            plug_or_node,
            source=True,
            destination=False,
            plugs=True
        ) or []

        return plugs

    plugs = cmds.listConnections(
        plug_or_node,
        source=True,
        destination=False,
        plugs=True
    ) or []

    return plugs


def node_from_plug(plug):
    if not plug:
        return None

    return plug.split(".", 1)[0]


def find_texture_upstream_from_plug(start_plug, max_depth=64):
    """
    Walk upstream from a shader input plug until a texture file is found.

    Returns:
        texture path or None
    """

    if not start_plug:
        return None

    queue = [start_plug]
    visited = set()

    depth = 0

    while queue and depth < max_depth:
        current = queue.pop(0)

        if current in visited:
            depth += 1
            continue

        visited.add(current)

        current_node = node_from_plug(current)

        if current_node:
            texture_path = get_texture_path_from_node(current_node)

            if texture_path:
                return texture_path

        upstream_plugs = get_upstream_source_plugs(current)

        if not upstream_plugs and current_node:
            upstream_plugs = get_upstream_source_plugs(current_node)

        for upstream_plug in upstream_plugs:
            if upstream_plug not in visited:
                queue.append(upstream_plug)

        depth += 1

    return None


def find_base_color_texture_from_shader(shader):
    """
    Try to find the texture feeding the shader's base color / color input.
    """

    if not shader:
        return None

    start_plug = get_existing_attr_plug(
        shader,
        BASE_COLOR_ATTR_CANDIDATES
    )

    if not start_plug:
        return None

    return find_texture_upstream_from_plug(start_plug)


def find_base_color_texture_from_mesh(mesh_name):
    """
    Find first base-color texture connected to a mesh material.

    If the mesh has multiple shading engines, the first base-color texture found
    is returned.
    """

    shading_engines = get_shading_engines_from_mesh(mesh_name)

    for shading_engine in shading_engines:
        shader = get_surface_shader_from_shading_engine(shading_engine)

        if not shader:
            continue

        texture_path = find_base_color_texture_from_shader(shader)

        if texture_path:
            return texture_path

    return None


def find_base_color_texture_from_uv_cache(uv_cache):
    """
    Find a base-color texture from the first mesh in a UV cache.
    """

    if not uv_cache or not uv_cache.has_data():
        return None

    for mesh_data in uv_cache.meshes:
        texture_path = find_base_color_texture_from_mesh(
            mesh_data.mesh_name
        )

        if texture_path:
            return texture_path

    return None