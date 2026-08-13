# ET_core/ET_storage.py

import json
import os

from maya import cmds


ETRIM_STORAGE_NODE = "ET_eTrim_Layout_DATA"
ETRIM_STORAGE_ATTR = "layoutJson"
ETRIM_STORAGE_VERSION = 1


class ETrimStorage(object):
    """
    Handles saving and loading eTrim layout data.

    Storage targets:
        - external .etrim JSON file
        - Maya scene network node

    This class does not directly know about UI buttons.
    It only serializes and deserializes viewer/model state.
    """

    FILE_EXTENSION = ".etrim"

    def __init__(self, model, viewer):
        self.model = model
        self.viewer = viewer

    # -----------------------------------------------------
    # Collect / Apply
    # -----------------------------------------------------

    def collect_data(self):
        """
        Collect eTrim layout data into a JSON-serializable dictionary.

        Stores:
            - trim boxes
            - tool settings
            - viewer pan/zoom
        """

        boxes = []

        for box_id in self.model.box_order:
            box = self.model.get_box(box_id)

            if not box:
                continue

            boxes.append(
                {
                    "name": box.name,
                    "u_min": float(box.u_min),
                    "v_min": float(box.v_min),
                    "u_max": float(box.u_max),
                    "v_max": float(box.v_max),
                    "color": list(box.color),
                    "z_index": int(box.z_index)
                }
            )

        data = {
            "version": ETRIM_STORAGE_VERSION,
            "boxes": boxes,
            "settings": {
                "uv_selection_enabled": bool(
                    getattr(
                        self.viewer,
                        "uv_selection_enabled",
                        True
                    )
                ),
                "box_selection_enabled": bool(
                    getattr(
                        self.viewer,
                        "box_selection_enabled",
                        True
                    )
                ),
                "uv_selection_mode": self.viewer.get_uv_selection_mode(),
                "viewer_zoom": float(self.viewer.zoom),
                "viewer_pan": [
                    float(self.viewer.pan.x()),
                    float(self.viewer.pan.y())
                ]
            }
        }

        return data

    def apply_data(self, data):
        """
        Apply previously saved eTrim layout data.

        Existing boxes are replaced.
        UV cache is not touched.
        """

        if not data:
            print("[eTrim] No layout data to apply.")
            return False

        boxes = data.get("boxes", [])
        settings = data.get("settings", {})

        self.model.clear_boxes()

        for box_data in boxes:
            box = self.model.create_box()

            box.name = str(
                box_data.get(
                    "name",
                    box.name
                )
            )

            box.u_min = float(
                box_data.get(
                    "u_min",
                    box.u_min
                )
            )

            box.v_min = float(
                box_data.get(
                    "v_min",
                    box.v_min
                )
            )

            box.u_max = float(
                box_data.get(
                    "u_max",
                    box.u_max
                )
            )

            box.v_max = float(
                box_data.get(
                    "v_max",
                    box.v_max
                )
            )

            color = box_data.get(
                "color",
                box.color
            )

            if color and len(color) == 4:
                box.color = (
                    float(color[0]),
                    float(color[1]),
                    float(color[2]),
                    float(color[3])
                )

            box.z_index = int(
                box_data.get(
                    "z_index",
                    box.z_index
                )
            )

        self.apply_settings(settings)

        self.viewer.boxesChanged.emit()
        self.viewer.update()

        print("[eTrim] Layout applied.")
        print("        boxes:", len(boxes))

        return True

    def apply_settings(self, settings):
        """
        Apply saved viewer/tool settings.

        This does not update UI button texts.
        The UI should sync its button visual state after this call.
        """

        uv_enabled = bool(
            settings.get(
                "uv_selection_enabled",
                True
            )
        )

        box_enabled = bool(
            settings.get(
                "box_selection_enabled",
                True
            )
        )

        if hasattr(self.viewer, "set_uv_selection_enabled"):
            self.viewer.set_uv_selection_enabled(uv_enabled)

        if hasattr(self.viewer, "set_box_selection_enabled"):
            self.viewer.set_box_selection_enabled(box_enabled)

        uv_mode = settings.get(
            "uv_selection_mode",
            "shell"
        )

        if self.viewer.uv_drawer:
            if uv_mode == "face":
                self.viewer.uv_drawer.set_selection_mode("face")
            else:
                self.viewer.uv_drawer.set_selection_mode("shell")

        viewer_zoom = settings.get(
            "viewer_zoom",
            None
        )

        viewer_pan = settings.get(
            "viewer_pan",
            None
        )

        if viewer_zoom is not None:
            self.viewer.zoom = float(viewer_zoom)

        if viewer_pan and len(viewer_pan) == 2:
            from PySide2 import QtCore

            try:
                self.viewer.pan = QtCore.QPointF(
                    float(viewer_pan[0]),
                    float(viewer_pan[1])
                )
            except Exception:
                try:
                    from PySide6 import QtCore as QtCore6

                    self.viewer.pan = QtCore6.QPointF(
                        float(viewer_pan[0]),
                        float(viewer_pan[1])
                    )
                except Exception:
                    pass

    # -----------------------------------------------------
    # File storage
    # -----------------------------------------------------

    def save_to_file(self, file_path):
        """
        Save layout to a .etrim file.
        """

        if not file_path:
            return False

        if not file_path.lower().endswith(self.FILE_EXTENSION):
            file_path += self.FILE_EXTENSION

        data = self.collect_data()

        try:
            with open(file_path, "w") as file_obj:
                json.dump(
                    data,
                    file_obj,
                    indent=4,
                    sort_keys=True
                )

            print("[eTrim] Saved layout file:")
            print("        path:", file_path)

            return True

        except Exception as exc:
            cmds.warning("[eTrim] Failed to save layout file.")
            print("[eTrim] Failed to save layout file:")
            print(exc)

            return False

    def load_from_file(self, file_path):
        """
        Load layout from a .etrim file.
        """

        if not file_path:
            return False

        if not os.path.exists(file_path):
            cmds.warning("[eTrim] Layout file does not exist.")
            print("[eTrim] Layout file does not exist:", file_path)
            return False

        try:
            with open(file_path, "r") as file_obj:
                data = json.load(file_obj)

            result = self.apply_data(data)

            if result:
                print("[eTrim] Loaded layout file:")
                print("        path:", file_path)

            return result

        except Exception as exc:
            cmds.warning("[eTrim] Failed to load layout file.")
            print("[eTrim] Failed to load layout file:")
            print(exc)

            return False

    # -----------------------------------------------------
    # Scene node storage
    # -----------------------------------------------------

    def get_or_create_scene_node(self):
        """
        Return the Maya scene node used to store eTrim layout data.
        """

        if cmds.objExists(ETRIM_STORAGE_NODE):
            node = ETRIM_STORAGE_NODE
        else:
            node = cmds.createNode(
                "network",
                name=ETRIM_STORAGE_NODE
            )

        if not cmds.attributeQuery(
            ETRIM_STORAGE_ATTR,
            node=node,
            exists=True
        ):
            cmds.addAttr(
                node,
                longName=ETRIM_STORAGE_ATTR,
                dataType="string"
            )

        return node

    def save_to_scene(self):
        """
        Save layout into the current Maya scene.
        """

        node = self.get_or_create_scene_node()
        data = self.collect_data()

        json_text = json.dumps(
            data,
            indent=4,
            sort_keys=True
        )

        try:
            cmds.setAttr(
                "{}.{}".format(
                    node,
                    ETRIM_STORAGE_ATTR
                ),
                json_text,
                type="string"
            )

            print("[eTrim] Saved layout to Maya scene node:")
            print("        node:", node)

            return True

        except Exception as exc:
            cmds.warning("[eTrim] Failed to save layout to scene.")
            print("[eTrim] Failed to save layout to scene:")
            print(exc)

            return False

    def load_from_scene(self):
        """
        Load layout from the current Maya scene.
        """

        if not cmds.objExists(ETRIM_STORAGE_NODE):
            cmds.warning("[eTrim] No eTrim layout node found in scene.")
            print("[eTrim] No eTrim layout node found in scene.")
            return False

        if not cmds.attributeQuery(
            ETRIM_STORAGE_ATTR,
            node=ETRIM_STORAGE_NODE,
            exists=True
        ):
            cmds.warning("[eTrim] eTrim layout node has no layout attribute.")
            print("[eTrim] eTrim layout node has no layout attribute.")
            return False

        try:
            json_text = cmds.getAttr(
                "{}.{}".format(
                    ETRIM_STORAGE_NODE,
                    ETRIM_STORAGE_ATTR
                )
            )

            if not json_text:
                cmds.warning("[eTrim] eTrim layout data is empty.")
                print("[eTrim] eTrim layout data is empty.")
                return False

            data = json.loads(json_text)
            result = self.apply_data(data)

            if result:
                print("[eTrim] Loaded layout from Maya scene node:")
                print("        node:", ETRIM_STORAGE_NODE)

            return result

        except Exception as exc:
            cmds.warning("[eTrim] Failed to load layout from scene.")
            print("[eTrim] Failed to load layout from scene:")
            print(exc)

            return False