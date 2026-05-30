from __future__ import print_function

import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from plugin_common import ConfigError, default_config_path, load_json, validate_config


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else default_config_path()
    try:
        config = load_json(path)
        validate_config(config, check_output_dir=True, check_pvpython=False)
    except (ConfigError, IOError, OSError, ValueError) as exc:
        print("CONFIG INVALID")
        print(exc)
        return 1
    print("CONFIG OK: {}".format(os.path.abspath(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
