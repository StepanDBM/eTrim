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
        self.trim_uvs_btn = QtWidgets.QPushButton("Trim UVs")
        self.create_box_btn = QtWidgets.QPushButton("Create Box")
        self.delete_box_btn = QtWidgets.QPushButton("Delete Box")
        self.clear_boxes_btn = QtWidgets.QPushButton("Clear")
        self.frame_btn = QtWidgets.QPushButton("Frame 0-1")

        toolbar_layout.addWidget(self.load_selection_btn)
        toolbar_layout.addWidget(self.trim_uvs_btn)
        toolbar_layout.addWidget(self.create_box_btn)
        toolbar_layout.addWidget(self.delete_box_btn)
        toolbar_layout.addWidget(self.clear_boxes_btn)
        toolbar_layout.addSpacing(12)
        toolbar_layout.addWidget(self.frame_btn)
        toolbar_layout.addStretch()

        main_layout.addLayout(toolbar_layout)

        # Info label
        self.info_label = QtWidgets.QLabel()
        self.info_label.setMinimumHeight(20)
        main_layout.addWidget(self.info_label)

        # Viewer
        self.viewer = ETrimViewer(self.model)
        main_layout.addWidget(self.viewer, 1)

    def create_connections(self):
        self.load_selection_btn.clicked.connect(self.load_selected_uvs)
        self.trim_uvs_btn.clicked.connect(self.trim_uvs)
        self.create_box_btn.clicked.connect(self.create_box)
        self.delete_box_btn.clicked.connect(self.delete_box)
        self.clear_boxes_btn.clicked.connect(self.clear_boxes)
        self.frame_btn.clicked.connect(self.frame_view)
        self.viewer.boxesChanged.connect(self.refresh_info)

        self.viewer.activeBoxChanged.connect(self.on_active_box_changed)

    # -----------------------------------------------------
    # Actions
    # -----------------------------------------------------
    def load_selected_uvs(self):
        uv_cache = ET_uv_model.build_cache_from_selection()

        self.viewer.set_uv_cache(uv_cache)

        self.refresh_info()

        print("[eTrim] UV selection loaded into viewer.")

    def trim_uvs(self):
        """
        Preview-fit either selected Maya faces/components or the active viewer UV shell
        into the active trim box.

        Priority:
        1. Maya selected faces/components
        2. Active UV shell in viewer

        This does not apply changes back to Maya yet.
        It only updates the viewer preview UV positions.
        """

        active_box = self.model.get_active_box()

        # -----------------------------------------------------
        # First priority: Maya face/component selection
        # -----------------------------------------------------

        uv_cache = None
        has_maya_selection = bool(cmds.ls(sl=True, fl=True) or [])

        if has_maya_selection:
            try:
                uv_cache = ET_uv_model.build_cache_from_selection()
            except Exception as exc:
                uv_cache = None
                print("[eTrim] Could not build UV cache from Maya selection:")
                print(exc)

        if uv_cache and uv_cache.has_data():
            if not active_box:
                print("No boxes or faces selected")
                return

            self.viewer.set_uv_cache(uv_cache)

            if self.viewer.uv_drawer.fit_cache_to_box(
                uv_cache,
                active_box
            ):
                print("[eTrim] Trimmed selected Maya UVs into box:")
                print("        box:", active_box.name, active_box.id)
                self.refresh_info()
                self.viewer.update()
                return

        # -----------------------------------------------------
        # Second priority: active viewer shell
        # -----------------------------------------------------

        active_shell = None

        if self.viewer.uv_drawer:
            active_shell = getattr(
                self.viewer.uv_drawer,
                "active_shell",
                None
            )

        if active_box and active_shell:
            if self.viewer.uv_drawer.fit_active_shell_to_box(active_box):
                print("[eTrim] Trimmed active viewer UV shell into box:")
                print("        box:", active_box.name, active_box.id)
                self.refresh_info()
                self.viewer.update()
                return

        print("No boxes or faces selected")

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