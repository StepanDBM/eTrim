# ET_ui/ET_main_window.py

from maya import OpenMayaUI
import maya.cmds as cmds
from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

try:
    from shiboken2 import wrapInstance
    from PySide2 import QtCore, QtWidgets
except ImportError:
    from shiboken6 import wrapInstance
    from PySide6 import QtCore, QtWidgets


from ET_core.ET_box_model import get_model
from ET_ui.ET_viewer import ETrimViewer
from ET_ui import ET_style

from ET_core import ET_uv_model

from ET_core import ET_texture_finder

from ET_core.ET_storage import ETrimStorage


ETRIM_UI = None
ETRIM_UI_OBJECT_NAME = "ET_eTrim_UI"
ETRIM_WORKSPACE_CONTROL = ETRIM_UI_OBJECT_NAME + "WorkspaceControl"


def maya_main_window():
    ptr = OpenMayaUI.MQtUtil.mainWindow()

    if ptr is None:
        return None

    return wrapInstance(int(ptr), QtWidgets.QWidget)

def delete_workspace_control():
    if cmds.workspaceControl(
        ETRIM_WORKSPACE_CONTROL,
        q=True,
        exists=True
    ):
        cmds.workspaceControl(
            ETRIM_WORKSPACE_CONTROL,
            e=True,
            close=True
        )

        cmds.deleteUI(
            ETRIM_WORKSPACE_CONTROL,
            control=True
        )

def workspace_control_exists(control_name):
    try:
        return cmds.workspaceControl(
            control_name,
            q=True,
            exists=True
        )
    except Exception:
        return False

def find_uv_dock_target():
    """
    Try common UV Toolkit workspace control names.

    Maya versions can differ, so this is intentionally conservative.
    If none are found, eTrim will simply show dockable/floating.
    """

    candidates = [
        "UVToolkitWorkspaceControl",
        "UVToolkit",
        "polyTexturePlacementPanel1WindowWorkspaceControl",
        "UVEditorWorkspaceControl"
    ]

    for candidate in candidates:
        if workspace_control_exists(candidate):
            return candidate

    return None
def open_uv_editor():
    """
    Open Maya's native UV Editor.

    Uses MEL because TextureViewWindow is the stable native command.
    """

    try:
        cmds.TextureViewWindow()
    except Exception as exc:
        print("[eTrim] Failed to open UV Editor:")
        print(exc)


class ETrimMainWindow(MayaQWidgetDockableMixin, QtWidgets.QDialog):

    WINDOW_TITLE = "eTrim SDBM"

    def __init__(self, parent=None):
        super(ETrimMainWindow, self).__init__(parent or maya_main_window())

        self.setObjectName(ETRIM_UI_OBJECT_NAME)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)

        self.model = get_model()
        self.setWindowTitle(self.WINDOW_TITLE)

        self.resize(700, 500)
        self.gen_spacing = 10

        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.WindowMinimizeButtonHint |
            QtCore.Qt.WindowMaximizeButtonHint |
            QtCore.Qt.WindowCloseButtonHint
        )

        self.setSizeGripEnabled(True)

        self.build_ui()
        self.create_connections()
        self.refresh_info()

    # -----------------------------------------------------
    # UI
    # -----------------------------------------------------

    def build_ui(self):
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # -----------------------------------------------------
        # Top toolbar
        # -----------------------------------------------------
        toolbar_layout = ET_style.create_compact_toolbar_layout()

        self.load_selection_btn = ET_style.create_primary_button("Load Sel",
            tooltip="Load current Maya UV selection into eTrim."
        )

        self.apply_btn = ET_style.create_primary_button("Apply",
            tooltip="Apply preview UV edits back to Maya."
        )

        self.create_box_btn = ET_style.create_action_button("Create Box",
            tooltip="Create a new trim box."
        )

        self.delete_box_btn = ET_style.create_danger_button("Delete Box",
            tooltip="Delete the active trim box."
        )

        self.clear_boxes_btn = ET_style.create_danger_button("Clear",
            tooltip="Clear all trim boxes."
        )

        self.frame_btn = ET_style.create_action_button("Frame 0-1",
            tooltip="Frame the 0-1 UV tile."
        )

        self.backdrop_image_btn = ET_style.create_toggle_button("BG Image",
            tooltip="Show or hide base color texture behind the UVs."
        )

        self.backdrop_source_mode_btn = ET_style.create_toggle_button("Shader",
            checked=False, tooltip="Switch backdrop source between shader texture and chosen image file."
        )

        self.choose_backdrop_image_btn = ET_style.create_action_button("Choose Img",
            tooltip="Choose an image file to use as the UV backdrop. This overrides the shader texture."
        )

        self.backdrop_opacity_spin = QtWidgets.QSpinBox()
        self.backdrop_opacity_spin.setRange(0, 100)
        self.backdrop_opacity_spin.setValue(15)
        self.backdrop_opacity_spin.setSuffix(" %")
        self.backdrop_opacity_spin.setMinimumWidth(72)
        self.backdrop_opacity_spin.setMinimumHeight(24)
        self.backdrop_opacity_spin.setStyleSheet(ET_style.DIALOG_STYLE)
        self.backdrop_opacity_spin.setToolTip("Backdrop image opacity.")

        toolbar_layout.addWidget(self.load_selection_btn)
        toolbar_layout.addWidget(self.apply_btn)


        toolbar_layout.addWidget(self.create_box_btn)
        toolbar_layout.addWidget(self.delete_box_btn)
        toolbar_layout.addWidget(self.clear_boxes_btn)

        toolbar_layout.addWidget(self.frame_btn)

        # Push backdrop controls to the right side of the top toolbar.
        toolbar_layout.addStretch()

        toolbar_layout.addWidget(self.backdrop_image_btn)
        toolbar_layout.addWidget(self.backdrop_source_mode_btn)
        toolbar_layout.addWidget(self.choose_backdrop_image_btn)
        toolbar_layout.addWidget(self.backdrop_opacity_spin)

        main_layout.addLayout(toolbar_layout)

        # -----------------------------------------------------
        # Tool / storage toolbar
        # -----------------------------------------------------
        selection_toolbar_layout = ET_style.create_compact_toolbar_layout()

        # Left side: interaction toggles
        self.enable_uv_selection_btn = ET_style.create_toggle_button("UV Sel: ON",
            checked=True, tooltip="Enable or disable UV picking and UV interaction.")

        self.enable_box_selection_btn = ET_style.create_toggle_button("Box Sel: ON",
            checked=True, tooltip="Enable or disable box picking and box interaction.")

        self.uv_mode_shell_btn = ET_style.create_small_toggle_button("S",
            checked=True, tooltip="Shell selection mode.")

        self.uv_mode_face_btn = ET_style.create_small_toggle_button("F",
            tooltip="Face selection mode.")

        self.uv_mode_vertex_btn = ET_style.create_small_toggle_button("V",
            tooltip="Vertex selection mode.")

        self.uv_mode_group = QtWidgets.QButtonGroup(self)
        self.uv_mode_group.setExclusive(True)

        self.uv_mode_group.addButton(self.uv_mode_shell_btn)
        self.uv_mode_group.addButton(self.uv_mode_face_btn)
        self.uv_mode_group.addButton(self.uv_mode_vertex_btn)

        uv_mode_layout = QtWidgets.QHBoxLayout()
        uv_mode_layout.setContentsMargins(0, 0, 0, 0)
        uv_mode_layout.setSpacing(2)

        uv_mode_layout.addWidget(self.uv_mode_shell_btn)
        uv_mode_layout.addWidget(self.uv_mode_face_btn)
        uv_mode_layout.addWidget(self.uv_mode_vertex_btn)

        selection_toolbar_layout.addWidget(self.enable_uv_selection_btn)
        selection_toolbar_layout.addWidget(self.enable_box_selection_btn)
        selection_toolbar_layout.addLayout(uv_mode_layout)

        # Spacer pushes save/load buttons to the right side.
        selection_toolbar_layout.addStretch()

        # Right side: storage buttons
        self.save_layout_btn = ET_style.create_action_button("Save .etrim",
            tooltip="Save current eTrim layout to a .etrim file.")

        self.load_layout_btn = ET_style.create_action_button("Load .etrim",
            tooltip="Load an eTrim layout from a .etrim file.")

        self.save_scene_layout_btn = ET_style.create_action_button("Save To Scene",
            tooltip="Save current eTrim layout into the Maya scene.")

        self.load_scene_layout_btn = ET_style.create_action_button("Load From Scene",
            tooltip="Load eTrim layout from the Maya scene.")

        selection_toolbar_layout.addWidget(self.save_layout_btn)
        selection_toolbar_layout.addWidget(self.load_layout_btn)
        selection_toolbar_layout.addWidget(self.save_scene_layout_btn)
        selection_toolbar_layout.addWidget(self.load_scene_layout_btn)

        main_layout.addLayout(selection_toolbar_layout)

        # -----------------------------------------------------
        # Info label
        # -----------------------------------------------------
        self.info_label = QtWidgets.QLabel()
        self.info_label.setMinimumHeight(20)
        main_layout.addWidget(self.info_label)

        # -----------------------------------------------------
        # Viewer
        # -----------------------------------------------------
        self.viewer = ETrimViewer(self.model)
        main_layout.addWidget(self.viewer, 1)

        self.storage = ETrimStorage(self.model, self.viewer)

    def create_connections(self):
        self.load_selection_btn.clicked.connect(self.load_selected_uvs)

        self.uv_mode_shell_btn.clicked.connect(lambda: self.set_uv_select_mode("shell"))
        self.uv_mode_face_btn.clicked.connect(lambda: self.set_uv_select_mode("face"))
        self.uv_mode_vertex_btn.clicked.connect(lambda: self.set_uv_select_mode("vertex"))
        
        self.backdrop_image_btn.clicked.connect(self.toggle_backdrop_image)
        self.backdrop_source_mode_btn.clicked.connect(self.toggle_backdrop_source_mode)
        self.choose_backdrop_image_btn.clicked.connect(self.choose_backdrop_image_file)
        self.backdrop_opacity_spin.valueChanged.connect(self.set_backdrop_opacity)

        self.apply_btn.clicked.connect(self.apply_preview)

        self.save_layout_btn.clicked.connect(self.save_layout_file)
        self.load_layout_btn.clicked.connect(self.load_layout_file)
        self.save_scene_layout_btn.clicked.connect(self.save_layout_to_scene)
        self.load_scene_layout_btn.clicked.connect(self.load_layout_from_scene)

        self.create_box_btn.clicked.connect(self.create_box)
        self.delete_box_btn.clicked.connect(self.delete_box)
        self.clear_boxes_btn.clicked.connect(self.clear_boxes)
        self.frame_btn.clicked.connect(self.frame_view)
        self.viewer.boxesChanged.connect(self.refresh_info)

        self.viewer.activeBoxChanged.connect(self.on_active_box_changed)

        self.enable_uv_selection_btn.clicked.connect(self.toggle_uv_selection_enabled)
        self.enable_box_selection_btn.clicked.connect(self.toggle_box_selection_enabled)

    # -----------------------------------------------------
    # Actions
    # -----------------------------------------------------
    def try_load_backdrop_image_from_cache(self, uv_cache):
        """
        Try to find and load base color texture from the loaded UV cache.
        """

        texture_path = ET_texture_finder.find_base_color_texture_from_uv_cache(
            uv_cache
        )

        if not texture_path:
            print("[eTrim] No base color texture found for backdrop.")
            self.backdrop_image_btn.setChecked(False)
            self.viewer.set_backdrop_enabled(False)
            return False

        result = self.viewer.set_backdrop_image_path(
            texture_path
        )

        if result:
            self.backdrop_image_btn.setChecked(True)
            self.backdrop_image_btn.setText("Backdrop Image")
            self.viewer.set_backdrop_opacity_percent(100)

        return result


    def toggle_backdrop_image(self):
        """
        Toggle backdrop image display.

        The active source can be:
            - shader
            - file
        """

        enabled = self.backdrop_image_btn.isChecked()

        if not enabled:
            self.viewer.set_backdrop_enabled(False)
            return

        source_mode = self.viewer.get_backdrop_source_mode()

        if source_mode == "shader":
            if not self.viewer.backdrop_shader_image_path:
                result = self.try_load_backdrop_image_from_cache(
                    self.viewer.uv_cache
                )

                if not result:
                    self.backdrop_image_btn.setChecked(False)
                    self.viewer.set_backdrop_enabled(False)
                    return

            self.viewer.set_backdrop_source_mode(
                "shader"
            )

            self.viewer.set_backdrop_enabled(True)
            return

        if source_mode == "file":
            if not self.viewer.backdrop_file_image_path:
                result = self.choose_backdrop_image_file()

                if not result:
                    self.backdrop_image_btn.setChecked(False)
                    self.viewer.set_backdrop_enabled(False)
                    return

            self.viewer.set_backdrop_source_mode(
                "file"
            )

            self.viewer.set_backdrop_enabled(True)
            return

    def choose_backdrop_image_file(self):
        """
        Choose a manual image file for the backdrop.

        Choosing a file immediately switches source mode to file and overrides
        shader display.
        """

        file_path, selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose Backdrop Image",
            "",
            "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp);;All Files (*.*)"
        )

        if not file_path:
            return False

        result = self.viewer.set_file_backdrop_image_path(
            file_path
        )

        if not result:
            return False

        self.backdrop_source_mode_btn.setChecked(True)
        self.backdrop_source_mode_btn.setText("File")

        self.backdrop_image_btn.setChecked(True)
        self.viewer.set_backdrop_enabled(True)

        print("[eTrim] Manual backdrop image chosen:")
        print("    path:", file_path)

        return True

    def toggle_backdrop_source_mode(self):
        """
        Toggle backdrop source mode.

        Button unchecked:
            Shader

        Button checked:
            File
        """

        use_file = self.backdrop_source_mode_btn.isChecked()

        if use_file:
            self.backdrop_source_mode_btn.setText("File")

            if not self.viewer.backdrop_file_image_path:
                result = self.choose_backdrop_image_file()

                if not result:
                    self.backdrop_source_mode_btn.setChecked(False)
                    self.backdrop_source_mode_btn.setText("Shader")
                    self.viewer.set_backdrop_source_mode(
                        "shader"
                    )
                    return

                return

            result = self.viewer.set_backdrop_source_mode(
                "file"
            )

            if result:
                self.backdrop_image_btn.setChecked(True)
                self.viewer.set_backdrop_enabled(True)

            return

        self.backdrop_source_mode_btn.setText("Shader")

        if not self.viewer.backdrop_shader_image_path:
            self.try_load_backdrop_image_from_cache(
                self.viewer.uv_cache
            )

        result = self.viewer.set_backdrop_source_mode(
            "shader"
        )

        if result:
            self.backdrop_image_btn.setChecked(True)
            self.viewer.set_backdrop_enabled(True)
        else:
            self.backdrop_image_btn.setChecked(False)
            self.viewer.set_backdrop_enabled(False)

    def try_load_backdrop_image_from_cache(self, uv_cache):
        """
        Try to find and store base color texture from the loaded UV cache.

        Important:
            This updates shader backdrop source only.
            If the user selected file mode, this does not override the file.
        """

        texture_path = ET_texture_finder.find_base_color_texture_from_uv_cache(
            uv_cache
        )

        if not texture_path:
            print("[eTrim] No base color texture found for backdrop.")

            if self.viewer.get_backdrop_source_mode() == "shader":
                self.backdrop_image_btn.setChecked(False)
                self.viewer.set_backdrop_enabled(False)

            return False

        result = self.viewer.set_shader_backdrop_image_path(
            texture_path
        )

        if result and self.viewer.get_backdrop_source_mode() == "shader":
            self.backdrop_image_btn.setChecked(True)
            self.viewer.set_backdrop_enabled(True)
            self.viewer.set_backdrop_opacity_percent(100)

        return result

    def set_backdrop_opacity(self, value):
        self.viewer.set_backdrop_opacity_percent(value)

    def load_selected_uvs(self):
        uv_cache = ET_uv_model.build_cache_from_selection()
        self.viewer.set_uv_cache(uv_cache)
        self.try_load_backdrop_image_from_cache(uv_cache)
        self.refresh_info()
        print("[eTrim] UV selection loaded into viewer.")

    def set_uv_select_mode(self, mode):
        """
        Set UV interaction mode from the S/F/V button group.
        """

        if mode not in (
            "shell",
            "face",
            "vertex"
        ):
            return

        if not self.viewer:
            return

        if not self.viewer.uv_drawer:
            return

        self.viewer.uv_drawer.set_selection_mode(
            mode
        )

        self.sync_uv_mode_buttons()

        self.viewer.update()

    def apply_preview(self):
        """
        Apply viewer preview UVs back to Maya.
        """

        if not self.viewer.uv_cache:
            print("[eTrim] No loaded UV cache to apply.")
            return

        result = ET_uv_model.apply_preview_to_maya(
            self.viewer.uv_cache
        )

        if result:
            print("[eTrim] Apply complete.")
        else:
            print("[eTrim] Nothing was applied.")

    def sync_uv_mode_buttons(self):
        """
        Sync S/F/V button checked states from viewer UV selection mode.
        """

        uv_mode = self.viewer.get_uv_selection_mode()

        self.uv_mode_shell_btn.setChecked(
            uv_mode == "shell"
        )

        self.uv_mode_face_btn.setChecked(
            uv_mode == "face"
        )

        self.uv_mode_vertex_btn.setChecked(
            uv_mode == "vertex"
        )

    def sync_ui_from_viewer_state(self):
        """
        Sync UI button labels/check states from viewer state.

        Storage applies data to model/viewer.
        UI owns buttons, so button state sync stays here.
        """

        uv_enabled = bool(
            getattr(
                self.viewer,
                "uv_selection_enabled",
                True
            )
        )
        self.uv_mode_shell_btn.setEnabled(uv_enabled)
        self.uv_mode_face_btn.setEnabled(uv_enabled)
        self.uv_mode_vertex_btn.setEnabled(uv_enabled)
        self.enable_uv_selection_btn.setChecked(uv_enabled)

        if uv_enabled:
            self.enable_uv_selection_btn.setText("UV Selection: ON")
        else:
            self.enable_uv_selection_btn.setText("UV Selection: OFF")

        box_enabled = bool(
            getattr(
                self.viewer,
                "box_selection_enabled",
                True
            )
        )

        self.enable_box_selection_btn.setChecked(box_enabled)

        if box_enabled:
            self.enable_box_selection_btn.setText("Box Sel: ON")
        else:
            self.enable_box_selection_btn.setText("Box Sel: OFF")

        self.sync_uv_mode_buttons()
        
        backdrop_source_mode = self.viewer.get_backdrop_source_mode()

        if backdrop_source_mode == "file":
            self.backdrop_source_mode_btn.setChecked(True)
            self.backdrop_source_mode_btn.setText("File")
        else:
            self.backdrop_source_mode_btn.setChecked(False)
            self.backdrop_source_mode_btn.setText("Shader")

    def save_layout_file(self):
        file_path, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save eTrim Layout",
            "",
            "eTrim Layout (*.etrim)"
        )

        if not file_path:
            return

        result = self.storage.save_to_file(file_path)

        if result:
            print("[eTrim] Save .etrim complete.")
        else:
            print("[eTrim] Save .etrim failed.")

    def load_layout_file(self):
        file_path, selected_filter = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Load eTrim Layout",
            "",
            "eTrim Layout (*.etrim)"
        )

        if not file_path:
            return

        result = self.storage.load_from_file(file_path)

        if result:
            self.sync_ui_from_viewer_state()
            self.refresh_info()
            print("[eTrim] Load .etrim complete.")
        else:
            print("[eTrim] Load .etrim failed.")

    def save_layout_to_scene(self):
        result = self.storage.save_to_scene()

        if result:
            print("[eTrim] Save layout to scene complete.")
        else:
            print("[eTrim] Save layout to scene failed.")

    def load_layout_from_scene(self):
        result = self.storage.load_from_scene()

        if result:
            self.sync_ui_from_viewer_state()
            self.refresh_info()
            print("[eTrim] Load layout from scene complete.")
        else:
            print("[eTrim] Load layout from scene failed.")



    def create_box(self):
        width = self.viewer.create_box_width_percent / 100.0
        height = self.viewer.create_box_height_percent / 100.0

        box = self.model.create_box(
            width=width,
            height=height,
            preferred_u=0.0,
            preferred_v=0.0,
            centered=False
        )

        if not box:
            print("[eTrim] Could not create box.")
            return

        print("[eTrim] Created box:")
        print("    id:", box.id)
        print("    name:", box.name)
        print("    uv:", box.u_min, box.v_min, box.u_max, box.v_max)
        print("    z:", box.z_index)

        self.viewer.select_drawable(
            self.viewer.box_drawer.drawable_key_for_box(box.id),
            clear_previous=True
        )

        self.viewer.activeBoxChanged.emit(box.id)
        self.viewer.boxesChanged.emit()

        self.refresh_info()
        self.viewer.update()

    def delete_box(self):
        active_box = self.model.get_active_box()

        if not active_box:
            print("[eTrim] No active box to delete.")
            return

        print("[eTrim] Deleted box:", active_box.id)

        self.model.delete_active_box()

        self.refresh_info()
        self.viewer.update()

    def clear_boxes(self):
        self.model.clear_boxes()

        print("[eTrim] Cleared boxes.")

        self.refresh_info()
        self.viewer.update()

    def frame_view(self):
        self.viewer.frame_01()

    def on_active_box_changed(self, box_id):
        self.refresh_info()

    def refresh_info(self):
        active_box = self.model.get_active_box()
        count = len(self.model.box_order)

        if active_box:
            text = "Boxes: {} | Active: {} | {}".format(
                count,
                active_box.name,
                active_box.id
            )
        else:
            text = "Boxes: {} | Active: None".format(count)

        self.info_label.setText(text)

    def toggle_uv_selection_enabled(self):
        enabled = self.enable_uv_selection_btn.isChecked()

        if enabled:
            self.enable_uv_selection_btn.setText("UV Sel: ON")
        else:
            self.enable_uv_selection_btn.setText("UV Sel: OFF")

        self.viewer.set_uv_selection_enabled(enabled)
        self.sync_ui_from_viewer_state()


    def toggle_box_selection_enabled(self):
        enabled = self.enable_box_selection_btn.isChecked()

        if enabled:
            self.enable_box_selection_btn.setText("Box Sel: ON")
        else:
            self.enable_box_selection_btn.setText("Box Sel: OFF")

        self.viewer.set_box_selection_enabled(enabled)
    # -----------------------------------------------------
    # Close
    # -----------------------------------------------------

    def closeEvent(self, event):
        global ETRIM_UI
        ETRIM_UI = None
        super(ETrimMainWindow, self).closeEvent(event)


def show_ui():
    global ETRIM_UI

    open_uv_editor()

    if ETRIM_UI is not None:
        try:
            ETRIM_UI.close()
            ETRIM_UI.deleteLater()
        except Exception:
            pass

    delete_workspace_control()

    ETRIM_UI = ETrimMainWindow(parent=maya_main_window())

    dock_target = find_uv_dock_target()

    if dock_target:
        print("[eTrim] Dock target found:", dock_target)

        ETRIM_UI.show(
            dockable=True,
            floating=False,
            area="right"
        )

        try:
            cmds.workspaceControl(
                ETRIM_WORKSPACE_CONTROL,
                e=True,
                dockToControl=[
                    dock_target,
                    "right"
                ]
            )
        except Exception as exc:
            print("[eTrim] Could not dock to UV target. Falling back.")
            print(exc)

    else:
        print("[eTrim] No UV dock target found. Showing floating dockable UI.")

        ETRIM_UI.show(
            dockable=True,
            floating=True,
            area="right"
        )

    try:
        cmds.workspaceControl(
            ETRIM_WORKSPACE_CONTROL,
            e=True,
            label=ETrimMainWindow.WINDOW_TITLE,
            widthProperty="preferred",
            initialWidth=700,
            minimumWidth=450
        )
    except Exception:
        pass

    ETRIM_UI.raise_()
    ETRIM_UI.activateWindow()

    return ETRIM_UI