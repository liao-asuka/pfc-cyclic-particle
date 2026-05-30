from __future__ import print_function

import json
import math
import os
import re


AXES = ("x", "y", "z")
AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
OUTPUT_MODES = ("particles", "fluid", "both")


try:
    MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    MODULE_DIR = os.environ.get(
        "CYCLIC_PARTICLE_PLUGIN_SCRIPT_DIR",
        r"E:\codexfile\pfc cyclic particle\cyclic_particle_plugin\scripts",
    )


class ConfigError(ValueError):
    pass


def plugin_root():
    return os.path.abspath(os.path.join(MODULE_DIR, ".."))


def default_config_path():
    return os.path.join(plugin_root(), "config", "model_config.json")


def load_json(path):
    with open(path, "rb") as handle:
        content = handle.read()
    try:
        content = content.decode("utf-8-sig")
    except AttributeError:
        if content.startswith("\ufeff"):
            content = content[1:]
    return json.loads(content)


def save_json(path, data):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w") as handle:
        json.dump(data, handle, indent=2, sort_keys=False)
        handle.write("\n")


def require_number(value, name, min_value=None, max_value=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ConfigError("{} must be a number".format(name))
    if min_value is not None and number < min_value:
        raise ConfigError("{} must be >= {}".format(name, min_value))
    if max_value is not None and number > max_value:
        raise ConfigError("{} must be <= {}".format(name, max_value))
    return number


def validate_config(config, check_output_dir=True, check_pvpython=False):
    errors = []

    name = str(config.get("model_name", "")).strip()
    if not name:
        errors.append("model_name is required")
    elif not re.match(r"^[A-Za-z0-9_.-]+$", name):
        errors.append("model_name may only contain letters, numbers, dot, dash and underscore")

    if config.get("unit", "mm") != "mm":
        errors.append("unit must be mm in v1")

    domain = config.get("domain", {})
    for axis in AXES:
        try:
            require_number(domain.get(axis), "domain.{}".format(axis), min_value=1.0e-9)
        except ConfigError as exc:
            errors.append(str(exc))

    try:
        require_number(config.get("target_porosity"), "target_porosity", min_value=0.01, max_value=0.95)
    except ConfigError as exc:
        errors.append(str(exc))

    periodic_axes = config.get("periodic_axes", [])
    if not isinstance(periodic_axes, list):
        errors.append("periodic_axes must be a list")
    else:
        for axis in periodic_axes:
            if axis not in AXES:
                errors.append("periodic_axes contains unsupported axis {}".format(axis))

    if config.get("output_mode") not in OUTPUT_MODES:
        errors.append("output_mode must be one of {}".format(", ".join(OUTPUT_MODES)))

    output_dir = str(config.get("output_dir", "")).strip()
    if not output_dir:
        errors.append("output_dir is required")
    elif check_output_dir:
        try:
            if not os.path.isdir(output_dir):
                os.makedirs(output_dir)
        except OSError as exc:
            errors.append("output_dir is not writable: {}".format(exc))

    bins = config.get("radius_bins")
    if not isinstance(bins, list):
        errors.append("radius_bins must be a list")
    else:
        if len(bins) < 1 or len(bins) > 5:
            errors.append("radius_bins must contain 1 to 5 bins")
        total_fraction = 0.0
        for index, item in enumerate(bins):
            label = "radius_bins[{}]".format(index)
            if not isinstance(item, dict):
                errors.append("{} must be an object".format(label))
                continue
            if not str(item.get("name", "")).strip():
                errors.append("{}.name is required".format(label))
            try:
                r_min = require_number(item.get("r_min"), "{}.r_min".format(label), min_value=1.0e-12)
                r_max = require_number(item.get("r_max"), "{}.r_max".format(label), min_value=1.0e-12)
                if r_min >= r_max:
                    errors.append("{}.r_min must be smaller than r_max".format(label))
            except ConfigError as exc:
                errors.append(str(exc))
            try:
                vf = require_number(item.get("volume_fraction"), "{}.volume_fraction".format(label), min_value=0.0)
                total_fraction += vf
            except ConfigError as exc:
                errors.append(str(exc))
        if bins and abs(total_fraction - 1.0) > 1.0e-6:
            errors.append("radius_bins volume_fraction values must sum to 1.0, got {:.8f}".format(total_fraction))

    fluid = config.get("fluid_surface", {})
    if not isinstance(fluid, dict):
        errors.append("fluid_surface must be an object")
    else:
        for key in ("grid_spacing", "smooth_sigma_cells", "smooth_clip_distance"):
            try:
                require_number(fluid.get(key), "fluid_surface.{}".format(key), min_value=0.0)
            except ConfigError as exc:
                errors.append(str(exc))
        try:
            require_number(fluid.get("radius_shrink", 0.0), "fluid_surface.radius_shrink", min_value=0.0)
            require_number(fluid.get("level_offset", 0.0), "fluid_surface.level_offset")
        except ConfigError as exc:
            errors.append(str(exc))

    if config.get("output_mode") in ("fluid", "both") and check_pvpython:
        pvpython = str(config.get("paraview", {}).get("pvpython_path", "")).strip()
        if not pvpython or not os.path.isfile(pvpython):
            errors.append("paraview.pvpython_path is missing or invalid")

    if errors:
        raise ConfigError("\n".join(errors))
    return True


def normalized_config(config):
    validate_config(config, check_output_dir=False, check_pvpython=False)
    result = json.loads(json.dumps(config))
    result["unit"] = "mm"
    result["domain"] = dict((axis, float(result["domain"][axis])) for axis in AXES)
    result["target_porosity"] = float(result["target_porosity"])
    result["periodic_axes"] = [axis for axis in AXES if axis in result.get("periodic_axes", [])]
    result["output_mode"] = str(result["output_mode"])
    for item in result["radius_bins"]:
        item["r_min"] = float(item["r_min"])
        item["r_max"] = float(item["r_max"])
        item["volume_fraction"] = float(item["volume_fraction"])
    fluid = result["fluid_surface"]
    for key in ("radius_shrink", "grid_spacing", "smooth_sigma_cells", "smooth_clip_distance", "level_offset"):
        fluid[key] = float(fluid[key])
    return result


def case_dir(config):
    return os.path.abspath(os.path.join(config["output_dir"], config["model_name"]))


def case_paths(config):
    root = case_dir(config)
    return {
        "case": root,
        "config_used": os.path.join(root, "config_used.json"),
        "log": os.path.join(root, "run_log.txt"),
        "geometry": os.path.join(root, "geometry"),
        "particles_csv": os.path.join(root, "geometry", "particles.csv"),
        "particles": os.path.join(root, "particles"),
        "particles_stl": os.path.join(root, "particles", "particles.stl"),
        "fluid": os.path.join(root, "fluid"),
        "fluid_stl": os.path.join(root, "fluid", "fluid_fluent.stl"),
        "fluid_report": os.path.join(root, "fluid", "fluid_surface_report.txt"),
    }


def ensure_case_dirs(config):
    paths = case_paths(config)
    for key in ("case", "geometry", "particles", "fluid"):
        if not os.path.isdir(paths[key]):
            os.makedirs(paths[key])
    return paths


def rve_bounds(config):
    domain = config["domain"]
    return {
        "x": (-0.5 * domain["x"], 0.5 * domain["x"]),
        "y": (-0.5 * domain["y"], 0.5 * domain["y"]),
        "z": (-0.5 * domain["z"], 0.5 * domain["z"]),
    }


def rve_length(config, axis):
    bounds = rve_bounds(config)[axis]
    return bounds[1] - bounds[0]


def rve_volume(config):
    return config["domain"]["x"] * config["domain"]["y"] * config["domain"]["z"]


def sphere_volume(radius):
    return 4.0 / 3.0 * math.pi * radius ** 3
