# ET_bootstrap.py

import sys
import importlib


MODULES_TO_RELOAD = [
    "ET_core.ET_box_model",
    "ET_core.ET_uv_model",
    "ET_core.ET_storage",
    "ET_core.ET_texture_finder",
    "ET_core.ET_uv_unwrap",
    "ET_core.ET_gridify",
    "ET_core.ET_heatmap",
    "ET_core.ET_gridify_heuristic",

    "ET_ui.ET_style",
    "ET_ui.drawables.ET_drawable_object",
    "ET_ui.drawables.ET_uv_drawer",
    "ET_ui.drawables.ET_box_drawer",
    "ET_ui.ET_viewer",
    "ET_ui.ET_main_window",

    "ET_launcher",
]


def reload_module(module_name):
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])

    return importlib.import_module(module_name)


def reload_all(verbose=True):
    reloaded = []

    for module_name in MODULES_TO_RELOAD:
        try:
            reload_module(module_name)
            reloaded.append(module_name)

            if verbose:
                print("[eTrim bootstrap] Reloaded:", module_name)

        except Exception as exc:
            print("[eTrim bootstrap] FAILED:", module_name)
            print(exc)

    return reloaded


def run(verbose=True):
    reload_all(verbose=verbose)

    import ET_launcher
    return ET_launcher.show()


def show():
    import ET_launcher
    return ET_launcher.show()