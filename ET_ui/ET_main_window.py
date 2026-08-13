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

from ET_core import ET_uv_model


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

        self.setMinimumSize(700, 500)
        self.resize(700, 500)

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

        # Top toolbar
        toolbar_layout = QtWidgets.QHBoxLayout()
        toolbar_layout.setSpacing(6)

        self.load_selection_btn = QtWidgets.QPushButton("Load Selected UVs")
        self.apply_btn = QtWidgets.QPushButton("Apply")
        self.create_box_btn = QtWidgets.QPushButton("Create Box")
        self.delete_box_btn = QtWidgets.QPushButton("Delete Box")
        self.clear_boxes_btn = QtWidgets.QPushButton("Clear")
        self.frame_btn = QtWidgets.QPushButton("Frame 0-1")

        toolbar_layout.addWidget(self.load_selection_btn)
        toolbar_layout.addWidget(self.apply_btn)
        toolbar_layout.addWidget(self.create_box_btn)
        toolbar_layout.addWidget(self.delete_box_btn)
        toolbar_layout.addWidget(self.clear_boxes_btn)
        toolbar_layout.addSpacing(12)
        toolbar_layout.addWidget(self.frame_btn)
        toolbar_layout.addStretch()

        main_layout.addLayout(toolbar_layout)

        # Selection filter toolbar
        selection_toolbar_layout = QtWidgets.QHBoxLayout()
        selection_toolbar_layout.setSpacing(6)

        self.enable_uv_selection_btn = QtWidgets.QPushButton("UV Selection: ON")
        self.enable_uv_selection_btn.setCheckable(True)
        self.enable_uv_selection_btn.setChecked(True)

        self.enable_box_selection_btn = QtWidgets.QPushButton("Box Selection: ON")
        self.enable_box_selection_btn.setCheckable(True)
        self.enable_box_selection_btn.setChecked(True)

        self.uv_select_mode_btn = QtWidgets.QPushButton("Shells")
        self.uv_select_mode_btn.setCheckable(True)

        selection_toolbar_layout.addWidget(self.enable_uv_selection_btn)
        selection_toolbar_layout.addWidget(self.enable_box_selection_btn)
        selection_toolbar_layout.addWidget(self.uv_select_mode_btn)
        selection_toolbar_layout.addStretch()

        main_layout.addLayout(selection_toolbar_layout)

        # Info label
        self.info_label = QtWidgets.QLabel()
        self.info_label.setMinimumHeight(20)
        main_layout.addWidget(self.info_label)

        # Viewer
        self.viewer = ETrimViewer(self.model)
        main_layout.addWidget(self.viewer, 1)

    def create_connections(self):
        self.load_selection_btn.clicked.connect(self.load_selected_uvs)
        self.uv_select_mode_btn.clicked.connect(self.toggle_uv_select_mode)
        self.apply_btn.clicked.connect(self.apply_preview)
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
    def load_selected_uvs(self):
        uv_cache = ET_uv_model.build_cache_from_selection()

        self.viewer.set_uv_cache(uv_cache)

        self.refresh_info()

        print("[eTrim] UV selection loaded into viewer.")
    def toggle_uv_select_mode(self):
        """
        Toggle UV interaction between shell selection and face selection.
        """

        if self.uv_select_mode_btn.isChecked():
            self.uv_select_mode_btn.setText("Faces")
            self.viewer.uv_drawer.set_selection_mode("face")
        else:
            self.uv_select_mode_btn.setText("Shells")
            self.viewer.uv_drawer.set_selection_mode("shell")

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

    def create_box(self):
        box = self.model.create_box()

        print("[eTrim] Created box:")
        print("    id:", box.id)
        print("    name:", box.name)
        print("    uv:", box.u_min, box.v_min, box.u_max, box.v_max)
        print("    z:", box.z_index)

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
            self.enable_uv_selection_btn.setText("UV Selection: ON")
        else:
            self.enable_uv_selection_btn.setText("UV Selection: OFF")

        self.viewer.set_uv_selection_enabled(enabled)


    def toggle_box_selection_enabled(self):
        enabled = self.enable_box_selection_btn.isChecked()

        if enabled:
            self.enable_box_selection_btn.setText("Box Selection: ON")
        else:
            self.enable_box_selection_btn.setText("Box Selection: OFF")

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