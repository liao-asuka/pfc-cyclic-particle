from __future__ import print_function

import csv
import math
import os
import random
import subprocess
import sys
import imp
import time

try:
    import itasca as it
except Exception:
    it = None


def get_itasca():
    module = globals().get("it", None)
    if module is not None:
        return module
    try:
        module = __import__("itasca")
    except Exception:
        module = None
    globals()["it"] = module
    return module

try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # PFC3D 6.x can execute program-called Python without defining __file__.
    SCRIPT_DIR = os.environ.get(
        "CYCLIC_PARTICLE_PLUGIN_SCRIPT_DIR",
        r"E:\codexfile\pfc cyclic particle\cyclic_particle_plugin\scripts",
    )
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from plugin_common import (
    AXES,
    AXIS_INDEX,
    ConfigError,
    case_paths,
    default_config_path,
    ensure_case_dirs,
    load_json,
    normalized_config,
    rve_bounds,
    rve_length,
    rve_volume,
    save_json,
    sphere_volume,
    validate_config,
)


VERSION_NAME = "cyclic_particle_plugin_v1"
RANDOM_SEED = 240530
LARGE_SCALE = {"x": 3.0, "y": 3.0, "z": 3.0}
MIN_CENTER_SPACING_FACTOR = 0.55
MAX_INSERT_ATTEMPTS = 3000000
BIN_BALANCE_RANDOMNESS = 0.15
BALL_DENSITY = 2160.0
BALL_DAMP = 0.8
SHIFT_RANGE = (-1, 0, 1)
INTERSECTION_TOL = 1.0e-8
POROSITY_TOLERANCE = 1.0e-3
CUT_FRAGMENT_FRACTION_MIN = 0.40
CUT_FRAGMENT_FRACTION_MAX = 0.60
TARGET_CUT_FRAGMENT_FRACTION = 0.45
CONTACT_GAP_TOLERANCE = 1.0e-4
MAX_CONNECTIVITY_CANDIDATES = 40
HEAVY_PACK_BALL_THRESHOLD = 50000
SPHERE_LAT_SEGMENTS = 12
SPHERE_LON_SEGMENTS = 24
CUT_CAP_SEGMENTS = 48


class RunLog(object):
    def __init__(self, path):
        self.path = path
        parent = os.path.dirname(os.path.abspath(path))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        self.handle = open(path, "w")

    def write(self, text=""):
        print(text)
        self.handle.write(text + "\n")
        self.handle.flush()

    def close(self):
        self.handle.close()


def bounds_for_axis(config, axis):
    return rve_bounds(config)[axis]


def large_half_length(config, axis):
    return 0.5 * LARGE_SCALE[axis] * rve_length(config, axis)


def large_min(config, axis):
    return -large_half_length(config, axis)


def large_max(config, axis):
    return large_half_length(config, axis)


def large_volume(config):
    return (
        (large_max(config, "x") - large_min(config, "x")) *
        (large_max(config, "y") - large_min(config, "y")) *
        (large_max(config, "z") - large_min(config, "z"))
    )


def pick_bin(rng, bins):
    value = rng.random()
    accum = 0.0
    for item in bins:
        accum += item["volume_fraction"]
        if value <= accum:
            return item
    return bins[-1]


def pick_bin_balanced(rng, bins, bin_volume, current_total, target_volume):
    if rng.random() < BIN_BALANCE_RANDOMNESS:
        return pick_bin(rng, bins)
    best = None
    best_deficit = None
    reference = max(current_total, 1.0e-12)
    for item in bins:
        target = item["volume_fraction"] * min(target_volume, reference)
        deficit = target - bin_volume.get(item["name"], 0.0)
        if best is None or deficit > best_deficit:
            best = item
            best_deficit = deficit
    return best


def adjusted_final_radius(config, remaining_volume):
    radius = (remaining_volume / (4.0 / 3.0 * math.pi)) ** (1.0 / 3.0)
    r_min = min(item["r_min"] for item in config["radius_bins"])
    r_max = max(item["r_max"] for item in config["radius_bins"])
    if r_min <= radius <= r_max:
        return radius
    return None


def grid_cell_size(config):
    return max(item["r_max"] for item in config["radius_bins"]) * 1.35


def grid_key(config, x, y, z):
    cell = grid_cell_size(config)
    return (int(math.floor(x / cell)), int(math.floor(y / cell)), int(math.floor(z / cell)))


def nearby_grid_keys(key):
    kx, ky, kz = key
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                yield (kx + dx, ky + dy, kz + dz)


def ball_distance_ok(candidate, existing):
    cx, cy, cz, cr = candidate
    for ex, ey, ez, er, _bin_name in existing:
        dx = cx - ex
        dy = cy - ey
        dz = cz - ez
        min_dist = MIN_CENTER_SPACING_FACTOR * (cr + er)
        if dx * dx + dy * dy + dz * dz < min_dist * min_dist:
            return False
    return True


def ball_distance_ok_grid(config, candidate, grid):
    cx, cy, cz, _cr = candidate
    for key in nearby_grid_keys(grid_key(config, cx, cy, cz)):
        if not ball_distance_ok(candidate, grid.get(key, [])):
            return False
    return True


def add_to_grid(config, ball, grid):
    x, y, z, _radius, _bin_name = ball
    key = grid_key(config, x, y, z)
    grid.setdefault(key, []).append(ball)


def sample_large_position(config, rng, radius):
    return (
        rng.uniform(large_min(config, "x") + radius, large_max(config, "x") - radius),
        rng.uniform(large_min(config, "y") + radius, large_max(config, "y") - radius),
        rng.uniform(large_min(config, "z") + radius, large_max(config, "z") - radius),
    )


def generate_large_pack(config, log=None):
    rng = random.Random(RANDOM_SEED)
    target_solid = (1.0 - config["target_porosity"]) * large_volume(config)
    tolerance_volume = POROSITY_TOLERANCE * large_volume(config) * 0.5
    balls = []
    grid = {}
    bin_volume = dict((item["name"], 0.0) for item in config["radius_bins"])
    attempts = 0
    current_solid = 0.0
    last_report = time.time()
    if log is not None:
        min_radius = min(item["r_min"] for item in config["radius_bins"])
        max_radius = max(item["r_max"] for item in config["radius_bins"])
        log.write("generating precursor pack")
        log.write("  target_solid_volume: {:.8f} mm3".format(target_solid))
        log.write("  radius_range: {:.8f} - {:.8f} mm".format(min_radius, max_radius))

    while attempts < MAX_INSERT_ATTEMPTS:
        attempts += 1
        remaining = target_solid - current_solid
        if remaining <= tolerance_volume:
            break
        now = time.time()
        if log is not None and (attempts == 1 or attempts % 100000 == 0 or now - last_report >= 10.0):
            progress = 100.0 * current_solid / target_solid if target_solid > 0.0 else 0.0
            log.write(
                "  pack progress: attempts={} balls={} solid={:.6f}/{:.6f} ({:.2f}%)"
                .format(attempts, len(balls), current_solid, target_solid, progress)
            )
            last_report = now
        bin_def = pick_bin_balanced(rng, config["radius_bins"], bin_volume, current_solid, target_solid)
        radius = rng.uniform(bin_def["r_min"], bin_def["r_max"])
        volume = sphere_volume(radius)
        if volume > remaining + tolerance_volume:
            adjusted = adjusted_final_radius(config, remaining)
            if adjusted is None:
                continue
            radius = adjusted
            volume = sphere_volume(radius)
            bin_def = {"name": "adjusted-final"}
        x, y, z = sample_large_position(config, rng, radius)
        candidate = (x, y, z, radius)
        if not ball_distance_ok_grid(config, candidate, grid):
            continue
        ball = (x, y, z, radius, bin_def["name"])
        balls.append(ball)
        add_to_grid(config, ball, grid)
        current_solid += volume
        bin_volume[bin_def["name"]] = bin_volume.get(bin_def["name"], 0.0) + volume

    actual_porosity = 1.0 - current_solid / large_volume(config)
    if abs(actual_porosity - config["target_porosity"]) > POROSITY_TOLERANCE:
        raise RuntimeError(
            "Could not reach precursor porosity. target={:.6f}, actual={:.6f}, balls={}, attempts={}"
            .format(config["target_porosity"], actual_porosity, len(balls), attempts)
        )
    return balls, bin_volume, attempts, actual_porosity


def create_large_in_pfc(balls):
    pfc = get_itasca()
    if pfc is None:
        raise RuntimeError("run_pipeline.py must be called from PFC for particle generation")
    pfc.command("ball delete")
    for idx, (x, y, z, radius, bin_name) in enumerate(balls, 1):
        ball = pfc.ball.create(radius, (x, y, z), idx)
        try:
            ball.set_group("particles")
            ball.set_group("large_source", "stage")
            ball.set_group(bin_name, "size_bin")
        except TypeError:
            pfc.command("ball group 'large_source' slot 'stage' range id {}".format(idx))
            pfc.command("ball group '{}' slot 'size_bin' range id {}".format(bin_name, idx))
    pfc.command("ball attribute density {} damp {}".format(BALL_DENSITY, BALL_DAMP))


def setup_pfc_model(config):
    pfc = get_itasca()
    if pfc is None:
        raise RuntimeError("run_pipeline.py must be called from PFC")
    max_radius = max(item["r_max"] for item in config["radius_bins"])
    xmin = large_min(config, "x") - 2.0 * max_radius
    xmax = large_max(config, "x") + 2.0 * max_radius
    ymin = large_min(config, "y") - 2.0 * max_radius
    ymax = large_max(config, "y") + 2.0 * max_radius
    zmin = large_min(config, "z") - 2.0 * max_radius
    zmax = large_max(config, "z") + 2.0 * max_radius
    pfc.command("model new")
    pfc.command("model largestrain on")
    pfc.command("model domain extent {} {} {} {} {} {}".format(xmin, xmax, ymin, ymax, zmin, zmax))
    pfc.command("contact cmat default model linear method deformability emod 1e8 kratio 1.5 property fric 0.5")


def relax_large_pack(log, ball_count):
    pfc = get_itasca()
    if pfc is None:
        return
    if ball_count > HEAVY_PACK_BALL_THRESHOLD:
        log.write("heavy precursor pack detected; using short relaxation")
        log.write("  ball_count: {}".format(ball_count))
        pfc.command("model cycle 500 calm 50")
        return
    log.write("relaxing precursor pack in PFC")
    pfc.command("model cycle 5000 calm 250")
    pfc.command("model solve ratio-average 1e-6 cycles-total 200000")


def balls_from_pfc(config):
    pfc = get_itasca()
    source = []
    for ball in sorted(list(pfc.ball.list()), key=lambda b: b.id()):
        pos = ball.pos()
        bin_name = "unknown"
        for item in config["radius_bins"]:
            try:
                if ball.in_group(item["name"], "size_bin"):
                    bin_name = item["name"]
                    break
            except Exception:
                pass
        source.append({
            "id": int(ball.id()),
            "center": (float(pos[0]), float(pos[1]), float(pos[2])),
            "radius": float(ball.radius()),
            "bin_name": bin_name,
        })
    return source


def sphere_intersects_rve(config, center, radius):
    bounds = rve_bounds(config)
    for axis in AXES:
        value = center[AXIS_INDEX[axis]]
        if value + radius < bounds[axis][0] - INTERSECTION_TOL:
            return False
        if value - radius > bounds[axis][1] + INTERSECTION_TOL:
            return False
    return True


def center_inside_rve(config, center):
    bounds = rve_bounds(config)
    for axis in AXES:
        value = center[AXIS_INDEX[axis]]
        if value < bounds[axis][0] - INTERSECTION_TOL:
            return False
        if value > bounds[axis][1] + INTERSECTION_TOL:
            return False
    return True


def spherical_cap_fraction(radius, cap_height):
    if cap_height <= 0.0:
        return 0.0
    if cap_height >= 2.0 * radius:
        return 1.0
    cap_volume = math.pi * cap_height * cap_height * (3.0 * radius - cap_height) / 3.0
    return cap_volume / sphere_volume(radius)


def distance_for_cap_fraction(radius, target_fraction):
    low = 0.0
    high = radius
    for _step in range(60):
        mid = 0.5 * (low + high)
        cap_fraction = spherical_cap_fraction(radius, radius - mid)
        if cap_fraction > target_fraction:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


def set_axis(center, axis, value):
    coords = [center[0], center[1], center[2]]
    coords[AXIS_INDEX[axis]] = value
    return tuple(coords)


def projected_balanced_center(config, center, radius):
    bounds = rve_bounds(config)
    periodic_axes = set(config["periodic_axes"])
    crossings = []
    for axis in periodic_axes:
        value = center[AXIS_INDEX[axis]]
        low_distance = value - bounds[axis][0]
        high_distance = bounds[axis][1] - value
        if low_distance < radius - INTERSECTION_TOL:
            crossings.append((axis, "min", low_distance))
        if high_distance < radius - INTERSECTION_TOL:
            crossings.append((axis, "max", high_distance))
    if not crossings:
        return center

    keep_axis, keep_side, _distance = sorted(crossings, key=lambda item: item[2])[0]
    balanced_distance = distance_for_cap_fraction(radius, TARGET_CUT_FRAGMENT_FRACTION)
    adjusted = center
    for axis in AXES:
        low, high = bounds[axis]
        value = adjusted[AXIS_INDEX[axis]]
        if axis == keep_axis:
            value = low + balanced_distance if keep_side == "min" else high - balanced_distance
        elif axis in periodic_axes:
            low_limit = low + radius + 1.0e-5
            high_limit = high - radius - 1.0e-5
            if low_limit <= high_limit:
                value = max(low_limit, min(high_limit, value))
        adjusted = set_axis(adjusted, axis, value)
    return adjusted


def boundary_fragment_ratios(config, center, radius):
    bounds = rve_bounds(config)
    ratios = []
    for axis in config["periodic_axes"]:
        value = center[AXIS_INDEX[axis]]
        low_distance = value - bounds[axis][0]
        high_distance = bounds[axis][1] - value
        if low_distance < radius - INTERSECTION_TOL:
            outside = spherical_cap_fraction(radius, radius - low_distance)
            ratios.append((axis, "min", outside, 1.0 - outside))
        if high_distance < radius - INTERSECTION_TOL:
            outside = spherical_cap_fraction(radius, radius - high_distance)
            ratios.append((axis, "max", outside, 1.0 - outside))
    return ratios


def shifted_to_rve(center, offset):
    return (center[0] - offset[0], center[1] - offset[1], center[2] - offset[2])


def periodic_delta(config, value_a, value_b, axis):
    delta = abs(value_a - value_b)
    length = rve_length(config, axis)
    if axis in config["periodic_axes"]:
        return min(delta, length - delta)
    return delta


def contact_components(config, primary, offset):
    count = len(primary)
    adjacency = [[] for _i in range(count)]
    centers = [projected_balanced_center(config, shifted_to_rve(item["center"], offset), item["radius"]) for item in primary]
    max_radius = max([item["radius"] for item in primary] or [1.0])
    cell_size = 2.0 * max_radius + CONTACT_GAP_TOLERANCE
    grid = {}
    for index, center in enumerate(centers):
        key = (
            int(math.floor(center[0] / cell_size)),
            int(math.floor(center[1] / cell_size)),
            int(math.floor(center[2] / cell_size)),
        )
        grid.setdefault(key, []).append(index)
    for i in range(count):
        ci = centers[i]
        ri = primary[i]["radius"]
        key = (
            int(math.floor(ci[0] / cell_size)),
            int(math.floor(ci[1] / cell_size)),
            int(math.floor(ci[2] / cell_size)),
        )
        candidate_indices = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    candidate_indices.extend(grid.get((key[0] + dx, key[1] + dy, key[2] + dz), []))
        for j in candidate_indices:
            if j <= i:
                continue
            cj = centers[j]
            rj = primary[j]["radius"]
            dx = periodic_delta(config, ci[0], cj[0], "x")
            dy = periodic_delta(config, ci[1], cj[1], "y")
            dz = periodic_delta(config, ci[2], cj[2], "z")
            limit = ri + rj + CONTACT_GAP_TOLERANCE
            if dx * dx + dy * dy + dz * dz <= limit * limit:
                adjacency[i].append(j)
                adjacency[j].append(i)

    seen = set()
    components = []
    for start in range(count):
        if start in seen:
            continue
        stack = [start]
        seen.add(start)
        component = []
        while stack:
            index = stack.pop()
            component.append(index)
            for neighbor in adjacency[index]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(component)
    return components


def keep_largest_connected_component(config, primary, offset):
    if not primary:
        return [], []
    if len(primary) > MAX_CONNECTIVITY_CANDIDATES:
        # Connectivity is still computed for all particles; this constant is kept
        # as a named guard for future tuning of very large cases.
        pass
    components = contact_components(config, primary, offset)
    largest = max(components, key=len)
    keep = set(largest)
    kept = [ball for index, ball in enumerate(primary) if index in keep]
    removed = [ball for index, ball in enumerate(primary) if index not in keep]
    return kept, removed


def candidate_offsets(config, source_count=0):
    if source_count > HEAVY_PACK_BALL_THRESHOLD:
        yield (0.0, 0.0, 0.0)
        return
    step_x = max(0.25, 0.083333 * rve_length(config, "x"))
    step_y = max(0.25, 0.083333 * rve_length(config, "y"))
    step_z = max(0.50, 0.083333 * rve_length(config, "z"))
    for ix in range(-4, 5):
        for iy in range(-4, 5):
            for iz in range(-4, 5):
                yield (ix * step_x, iy * step_y, iz * step_z)


def choose_rve_offset(config, source):
    candidates = []
    for offset in candidate_offsets(config, len(source)):
        primary = []
        for ball in source:
            center = shifted_to_rve(ball["center"], offset)
            if center_inside_rve(config, center):
                primary.append(ball)
        if not primary:
            continue
        kept, removed = keep_largest_connected_component(config, primary, offset)
        solid = sum(sphere_volume(ball["radius"]) for ball in kept)
        porosity = 1.0 - solid / rve_volume(config)
        candidates.append({
            "offset": offset,
            "primary": kept,
            "connectivity_removed": removed,
            "solid": solid,
            "porosity": porosity,
            "error": abs(porosity - config["target_porosity"]),
        })
    if not candidates:
        raise RuntimeError("No valid RVE offset could be selected")
    return sorted(candidates, key=lambda item: (item["error"], len(item["connectivity_removed"])))[0]


def phase_from_shift(shift):
    return "rve_primary" if shift == (0, 0, 0) else "rve_periodic"


def extract_images(config, selected):
    images = []
    next_id = 1
    for ball in selected["primary"]:
        radius = ball["radius"]
        raw_center = shifted_to_rve(ball["center"], selected["offset"])
        center0 = projected_balanced_center(config, raw_center, radius)
        ranges = []
        for axis in AXES:
            ranges.append(SHIFT_RANGE if axis in config["periodic_axes"] else (0,))
        for sx in ranges[0]:
            for sy in ranges[1]:
                for sz in ranges[2]:
                    shift = (sx, sy, sz)
                    center = (
                        center0[0] + sx * rve_length(config, "x"),
                        center0[1] + sy * rve_length(config, "y"),
                        center0[2] + sz * rve_length(config, "z"),
                    )
                    if not sphere_intersects_rve(config, center, radius):
                        continue
                    images.append({
                        "id": next_id,
                        "source_id": ball["id"],
                        "shift": shift,
                        "center": center,
                        "radius": radius,
                        "bin_name": ball["bin_name"],
                        "phase": phase_from_shift(shift),
                    })
                    next_id += 1
    return images


def create_rve_in_pfc(images):
    pfc = get_itasca()
    pfc.command("ball delete")
    for image in images:
        x, y, z = image["center"]
        ball = pfc.ball.create(image["radius"], (x, y, z), image["id"])
        try:
            ball.set_group("particles")
            ball.set_group("cyclic_particle_plugin_rve", "stage")
            ball.set_group(image["phase"], "layer")
            ball.set_group(image["bin_name"], "size_bin")
            ball.set_extra(1, image["source_id"])
            ball.set_extra(2, image["shift"][0])
            ball.set_extra(3, image["shift"][1])
            ball.set_extra(4, image["shift"][2])
        except TypeError:
            pfc.command("ball group 'cyclic_particle_plugin_rve' slot 'stage' range id {}".format(image["id"]))
    pfc.command("ball attribute density {} damp {}".format(BALL_DENSITY, BALL_DAMP))


def write_particles_csv(path, images):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "source_id", "x", "y", "z", "radius", "shift_x", "shift_y", "shift_z", "phase", "bin_name"])
        for image in images:
            x, y, z = image["center"]
            sx, sy, sz = image["shift"]
            writer.writerow([
                image["id"],
                image["source_id"],
                "{:.10f}".format(x),
                "{:.10f}".format(y),
                "{:.10f}".format(z),
                "{:.10f}".format(image["radius"]),
                sx,
                sy,
                sz,
                image["phase"],
                image["bin_name"],
            ])


def vector_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vector_cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def unit_normal(p1, p2, p3):
    normal = vector_cross(vector_sub(p2, p1), vector_sub(p3, p1))
    length = math.sqrt(normal[0] ** 2 + normal[1] ** 2 + normal[2] ** 2)
    if length <= 0.0:
        return (0.0, 0.0, 0.0)
    return (normal[0] / length, normal[1] / length, normal[2] / length)


def write_triangle(handle, p1, p2, p3):
    normal = unit_normal(p1, p2, p3)
    handle.write("  facet normal {:.8e} {:.8e} {:.8e}\n".format(*normal))
    handle.write("    outer loop\n")
    for point in (p1, p2, p3):
        handle.write("      vertex {:.8e} {:.8e} {:.8e}\n".format(point[0], point[1], point[2]))
    handle.write("    endloop\n")
    handle.write("  endfacet\n")


def point_axis_value(point, axis):
    return point[AXIS_INDEX[axis]]


def set_axis_value(point, axis, value):
    values = [point[0], point[1], point[2]]
    values[AXIS_INDEX[axis]] = value
    return tuple(values)


def inside_plane(point, axis, limit, keep_greater):
    value = point_axis_value(point, axis)
    if keep_greater:
        return value >= limit - 1.0e-10
    return value <= limit + 1.0e-10


def intersect_plane(p1, p2, axis, limit):
    v1 = point_axis_value(p1, axis)
    v2 = point_axis_value(p2, axis)
    if abs(v2 - v1) <= 1.0e-15:
        return p1
    t = (limit - v1) / (v2 - v1)
    return (
        p1[0] + t * (p2[0] - p1[0]),
        p1[1] + t * (p2[1] - p1[1]),
        p1[2] + t * (p2[2] - p1[2]),
    )


def clip_polygon_to_plane(points, axis, limit, keep_greater):
    if not points:
        return []
    clipped = []
    previous = points[-1]
    previous_inside = inside_plane(previous, axis, limit, keep_greater)
    for current in points:
        current_inside = inside_plane(current, axis, limit, keep_greater)
        if current_inside:
            if not previous_inside:
                clipped.append(intersect_plane(previous, current, axis, limit))
            clipped.append(current)
        elif previous_inside:
            clipped.append(intersect_plane(previous, current, axis, limit))
        previous = current
        previous_inside = current_inside
    return clipped


def clip_polygon_to_box(config, points):
    bounds = rve_bounds(config)
    planes = [
        ("x", bounds["x"][0], True),
        ("x", bounds["x"][1], False),
        ("y", bounds["y"][0], True),
        ("y", bounds["y"][1], False),
        ("z", bounds["z"][0], True),
        ("z", bounds["z"][1], False),
    ]
    clipped = list(points)
    for axis, limit, keep_greater in planes:
        clipped = clip_polygon_to_plane(clipped, axis, limit, keep_greater)
        if not clipped:
            break
    return clipped


def write_clipped_polygon(config, handle, points):
    points = clip_polygon_to_box(config, points)
    if len(points) < 3:
        return 0
    for index in range(1, len(points) - 1):
        write_triangle(handle, points[0], points[index], points[index + 1])
    return len(points) - 2


def sphere_point(center, radius, theta, phi):
    sin_theta = math.sin(theta)
    return (
        center[0] + radius * sin_theta * math.cos(phi),
        center[1] + radius * sin_theta * math.sin(phi),
        center[2] + radius * math.cos(theta),
    )


def cut_cap_point(axis, plane_value, center, cap_radius, angle):
    dx = cap_radius * math.cos(angle)
    dy = cap_radius * math.sin(angle)
    if axis == "x":
        return (plane_value, center[1] + dx, center[2] + dy)
    if axis == "y":
        return (center[0] + dx, plane_value, center[2] + dy)
    return (center[0] + dx, center[1] + dy, plane_value)


def write_cut_cap(config, handle, axis, plane_value, center, radius, outward_negative):
    distance = abs(point_axis_value(center, axis) - plane_value)
    if distance >= radius:
        return 0
    cap_radius = math.sqrt(max(0.0, radius * radius - distance * distance))
    cap_center = set_axis_value(center, axis, plane_value)
    count = 0
    for index in range(CUT_CAP_SEGMENTS):
        a1 = 2.0 * math.pi * index / CUT_CAP_SEGMENTS
        a2 = 2.0 * math.pi * (index + 1) / CUT_CAP_SEGMENTS
        p1 = cut_cap_point(axis, plane_value, center, cap_radius, a1)
        p2 = cut_cap_point(axis, plane_value, center, cap_radius, a2)
        if outward_negative:
            count += write_clipped_polygon(config, handle, [cap_center, p2, p1])
        else:
            count += write_clipped_polygon(config, handle, [cap_center, p1, p2])
    return count


def write_cut_caps(config, handle, center, radius):
    bounds = rve_bounds(config)
    count = 0
    count += write_cut_cap(config, handle, "x", bounds["x"][0], center, radius, True)
    count += write_cut_cap(config, handle, "x", bounds["x"][1], center, radius, False)
    count += write_cut_cap(config, handle, "y", bounds["y"][0], center, radius, True)
    count += write_cut_cap(config, handle, "y", bounds["y"][1], center, radius, False)
    count += write_cut_cap(config, handle, "z", bounds["z"][0], center, radius, True)
    count += write_cut_cap(config, handle, "z", bounds["z"][1], center, radius, False)
    return count


def write_sphere(config, handle, center, radius):
    count = 0
    for i in range(SPHERE_LAT_SEGMENTS):
        theta1 = math.pi * i / SPHERE_LAT_SEGMENTS
        theta2 = math.pi * (i + 1) / SPHERE_LAT_SEGMENTS
        for j in range(SPHERE_LON_SEGMENTS):
            phi1 = 2.0 * math.pi * j / SPHERE_LON_SEGMENTS
            phi2 = 2.0 * math.pi * (j + 1) / SPHERE_LON_SEGMENTS
            p1 = sphere_point(center, radius, theta1, phi1)
            p2 = sphere_point(center, radius, theta2, phi1)
            p3 = sphere_point(center, radius, theta2, phi2)
            p4 = sphere_point(center, radius, theta1, phi2)
            if i == 0:
                count += write_clipped_polygon(config, handle, [p1, p2, p3])
            elif i == SPHERE_LAT_SEGMENTS - 1:
                count += write_clipped_polygon(config, handle, [p1, p2, p4])
            else:
                count += write_clipped_polygon(config, handle, [p1, p2, p3])
                count += write_clipped_polygon(config, handle, [p1, p3, p4])
    count += write_cut_caps(config, handle, center, radius)
    return count


def export_particles_stl(config, images, output_path):
    parent = os.path.dirname(os.path.abspath(output_path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    count = 0
    with open(output_path, "w") as handle:
        handle.write("solid particles\n")
        for image in images:
            count += write_sphere(config, handle, image["center"], image["radius"])
        handle.write("endsolid particles\n")
    return count


def run_fluid_export(config, paths, log):
    pvpython = str(config.get("paraview", {}).get("pvpython_path", "")).strip()
    if not pvpython or not os.path.isfile(pvpython):
        message = (
            "ParaView pvpython is missing. Install it with:\n"
            "  powershell -ExecutionPolicy Bypass -File \"{}\"\n"
            "Then set paraview.pvpython_path in config/model_config.json."
        ).format(os.path.join(os.path.dirname(SCRIPT_DIR), "tools", "install_paraview.ps1"))
        raise RuntimeError(message)
    cmd = [
        pvpython,
        os.path.join(SCRIPT_DIR, "export_fluid_levelset.py"),
        "--config",
        paths["config_used"],
        "--csv",
        paths["particles_csv"],
        "--output",
        paths["fluid_stl"],
        "--report",
        paths["fluid_report"],
    ]
    log.write("running fluid exporter:")
    log.write("  " + " ".join('"{}"'.format(item) if " " in item else item for item in cmd))
    completed = subprocess.call(cmd)
    if completed != 0:
        raise RuntimeError("fluid exporter failed with exit code {}".format(completed))


def main(config_path=None):
    if "generate_large_pack" not in globals():
        fresh = imp.load_source(
            "cyclic_particle_plugin_run_pipeline_fresh",
            os.path.join(SCRIPT_DIR, "run_pipeline.py"),
        )
        return fresh.main(config_path)
    if config_path is None:
        config_path = sys.argv[1] if len(sys.argv) > 1 else default_config_path()
    raw_config = load_json(config_path)
    validate_config(raw_config, check_output_dir=True, check_pvpython=False)
    config = normalized_config(raw_config)
    if config["output_mode"] in ("fluid", "both"):
        validate_config(config, check_output_dir=True, check_pvpython=True)
    paths = ensure_case_dirs(config)
    save_json(paths["config_used"], config)
    log = RunLog(paths["log"])

    try:
        log.write("=== {} ===".format(VERSION_NAME))
        log.write("config: {}".format(os.path.abspath(config_path)))
        log.write("case_dir: {}".format(paths["case"]))
        log.write("unit: {}".format(config["unit"]))
        log.write("domain: x={x:.6f} y={y:.6f} z={z:.6f} mm".format(**config["domain"]))
        log.write("target_porosity: {:.6f}".format(config["target_porosity"]))
        log.write("periodic_axes: {}".format(",".join(config["periodic_axes"])))
        log.write("output_mode: {}".format(config["output_mode"]))

        setup_pfc_model(config)
        balls, bin_volume, attempts, actual_large_porosity = generate_large_pack(config, log)
        create_large_in_pfc(balls)
        log.write("precursor_balls: {}".format(len(balls)))
        log.write("precursor_attempts: {}".format(attempts))
        log.write("precursor_porosity: {:.8f}".format(actual_large_porosity))
        for name in sorted(bin_volume):
            log.write("bin_volume_{}: {:.8f}".format(name, bin_volume[name]))

        relax_large_pack(log, len(balls))
        source = balls_from_pfc(config)
        selected = choose_rve_offset(config, source)
        images = extract_images(config, selected)
        if not images:
            raise RuntimeError("No particles/images were extracted")
        create_rve_in_pfc(images)
        write_particles_csv(paths["particles_csv"], images)

        boundary_fragments = []
        for ball in selected["primary"]:
            center = projected_balanced_center(config, shifted_to_rve(ball["center"], selected["offset"]), ball["radius"])
            boundary_fragments.extend(boundary_fragment_ratios(config, center, ball["radius"]))
        min_fragment = None
        max_fragment = None
        for _axis, _side, outside, inside in boundary_fragments:
            local_min = min(outside, inside)
            local_max = max(outside, inside)
            min_fragment = local_min if min_fragment is None else min(min_fragment, local_min)
            max_fragment = local_max if max_fragment is None else max(max_fragment, local_max)

        primary_count = len([item for item in images if item["phase"] == "rve_primary"])
        log.write("rve_offset: ({:.6f}, {:.6f}, {:.6f})".format(*selected["offset"]))
        log.write("rve_particles_csv: {}".format(paths["particles_csv"]))
        log.write("primary_images: {}".format(primary_count))
        log.write("periodic_images: {}".format(len(images) - primary_count))
        log.write("floating_removed: {}".format(len(selected["connectivity_removed"])))
        log.write("final_porosity: {:.8f}".format(selected["porosity"]))
        log.write("final_particle_count: {}".format(len(images)))
        if min_fragment is not None:
            log.write("boundary_cut_fragment_range: {:.6f} - {:.6f}".format(min_fragment, max_fragment))

        if config["output_mode"] in ("particles", "both"):
            triangles = export_particles_stl(config, images, paths["particles_stl"])
            log.write("particle_stl: {}".format(paths["particles_stl"]))
            log.write("particle_stl_triangles: {}".format(triangles))

        if config["output_mode"] in ("fluid", "both"):
            run_fluid_export(config, paths, log)
            log.write("fluid_stl: {}".format(paths["fluid_stl"]))
            log.write("fluid_report: {}".format(paths["fluid_report"]))

        pfc = get_itasca()
        if pfc is not None:
            save_path = os.path.join(paths["case"], config["model_name"] + ".sav").replace("\\", "/")
            pfc.command("model save '{}'".format(save_path))
            log.write("pfc_save: {}".format(save_path))
        log.write("pipeline complete")
    except Exception as exc:
        log.write("ERROR: {}".format(exc))
        raise
    finally:
        log.close()


if __name__ == "__main__":
    main()
