from __future__ import print_function

import os
import sys
import importlib


SCRIPT_DIR = r"E:\\codexfile\\pfc cyclic particle\\cyclic_particle_plugin\\scripts"
CONFIG_PATH = r"E:\\codexfile\\pfc cyclic particle\\cyclic_particle_plugin\\config\\model_config.json"

os.environ["CYCLIC_PARTICLE_PLUGIN_SCRIPT_DIR"] = SCRIPT_DIR

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

for module_name in ("run_pipeline", "plugin_common"):
    if module_name in sys.modules:
        del sys.modules[module_name]

run_pipeline = importlib.import_module("run_pipeline")


run_pipeline.main(CONFIG_PATH)
