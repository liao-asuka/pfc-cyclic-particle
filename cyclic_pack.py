# PFC3D cyclic-face / random-interior particle generator.
# Opposite cut faces can be made identical along x, y, and/or z by creating
# paired particles with the same radius, same transverse coordinates, and the
# same inward distance from the two faces.

from __future__ import print_function

import math
import random

try:
    import itasca as it
except ImportError:
    it = None


# ----------------------- user parameters -----------------------

TARGET_POROSITY = 0.40
POROSITY_TOLERANCE = 1.0e-3
RANDOM_SEED = 10001

BOX_X_MIN, BOX_X_MAX = -1.5, 1.5
BOX_Y_MIN, BOX_Y_MAX = -1.5, 1.5
BOX_Z_MIN, BOX_Z_MAX = -3.0, 3.0

# Enable any subset of ("x", "y", "z"). For example:
#   ("z",)           -> inlet/outlet cyclic faces only
#   ("x", "y", "z") -> left/right, front/back, and outlet/inlet faces
PERIODIC_AXES = ("x", "y", "z")

# Paired particles are sampled so they cross the selected cyclic cut faces.
# Interior random particles are kept away from selected cyclic faces so the
# cut-face particle pattern is controlled only by the paired particles.
PERIODIC_BAND_THICKNESS = 0.55
PERIODIC_FACE_CLEARANCE = 0.03
RANDOM_PERIODIC_FACE_CLEARANCE = 0.03

# Center distance from a cyclic face, expressed as a fraction of radius. Values
# below 1.0 make the sphere cross the face and create a visible cut section.
PERIODIC_CUT_OFFSET_FRACTION_MIN = 0.25
PERIODIC_CUT_OFFSET_FRACTION_MAX = 0.75

# Fraction of total solid volume assigned to all periodic face pairs combined.
PERIODIC_SOLID_VOLUME_FRACTION = 0.40

# Radius bins in mm. volume_fraction values should sum to 1.0.
RADIUS_BINS = [
    {"name": "fine", "r_min": 0.2125, "r_max": 0.2400, "volume_fraction": 0.25},
    {"name": "medium", "r_min": 0.2400, "r_max": 0.2700, "volume_fraction": 0.45},
    {"name": "coarse", "r_min": 0.2700, "r_max": 0.3000, "volume_fraction": 0.30},
]

# 1.0 means no initial overlap. Values below 1.0 allow controlled initial
# overlap, which PFC can relax during cycling.
MIN_CENTER_SPACING_FACTOR = 0.55
MAX_INSERT_ATTEMPTS = 700000
BIN_BALANCE_RANDOMNESS = 0.15

BALL_DENSITY = 2160.0
BALL_DAMP = 0.8

# If the remaining target volume is smaller than a normal sampled ball/pair,
# this option allows one final adjusted-radius ball/pair.
ALLOW_FINAL_RADIUS_ADJUST = True


# ----------------------- geometry helpers -----------------------

AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
BOX_MIN = {"x": BOX_X_MIN, "y": BOX_Y_MIN, "z": BOX_Z_MIN}
BOX_MAX = {"x": BOX_X_MAX, "y": BOX_Y_MAX, "z": BOX_Z_MAX}


def box_volume():
    return ((BOX_X_MAX - BOX_X_MIN) *
            (BOX_Y_MAX - BOX_Y_MIN) *
            (BOX_Z_MAX - BOX_Z_MIN))


def axis_length(axis):
    return BOX_MAX[axis] - BOX_MIN[axis]


def periodic_band_volume(axis):
    return 2.0 * PERIODIC_BAND_THICKNESS * box_volume() / axis_length(axis)


def sphere_volume(radius):
    return 4.0 / 3.0 * math.pi * radius ** 3


def target_solid_volume():
    return (1.0 - TARGET_POROSITY) * box_volume()


def phase_targets():
    axes = list(PERIODIC_AXES)
    total = target_solid_volume()
    periodic_total = total * PERIODIC_SOLID_VOLUME_FRACTION if axes else 0.0
    per_axis = periodic_total / len(axes) if axes else 0.0
    periodic_targets = dict((axis, per_axis) for axis in axes)
    return total - periodic_total, periodic_targets


def validate_parameters():
    total = sum(b["volume_fraction"] for b in RADIUS_BINS)
    if abs(total - 1.0) > 1.0e-8:
        raise ValueError("RADIUS_BINS volume_fraction values must sum to 1.0")
    for b in RADIUS_BINS:
        if b["r_min"] <= 0.0 or b["r_max"] < b["r_min"]:
            raise ValueError("Invalid radius bin: {}".format(b))
    for axis in PERIODIC_AXES:
        if axis not in AXIS_INDEX:
            raise ValueError("Invalid periodic axis: {}".format(axis))
    if len(set(PERIODIC_AXES)) != len(PERIODIC_AXES):
        raise ValueError("PERIODIC_AXES contains duplicate axes")
    if PERIODIC_BAND_THICKNESS <= 0.0:
        raise ValueError("PERIODIC_BAND_THICKNESS must be positive")
    if PERIODIC_CUT_OFFSET_FRACTION_MIN <= 0.0:
        raise ValueError("PERIODIC_CUT_OFFSET_FRACTION_MIN must be positive")
    if PERIODIC_CUT_OFFSET_FRACTION_MAX >= 1.0:
        raise ValueError("PERIODIC_CUT_OFFSET_FRACTION_MAX must be less than 1.0")
    if PERIODIC_CUT_OFFSET_FRACTION_MIN > PERIODIC_CUT_OFFSET_FRACTION_MAX:
        raise ValueError("Invalid periodic cut offset fraction range")
    for axis in PERIODIC_AXES:
        max_band = 0.5 * axis_length(axis)
        if PERIODIC_BAND_THICKNESS >= max_band:
            raise ValueError("PERIODIC_BAND_THICKNESS is too large for {} axis".format(axis))


def phase_for_axis(axis):
    return "periodic_{}".format(axis)


def pick_bin(rng):
    value = rng.random()
    accum = 0.0
    for b in RADIUS_BINS:
        accum += b["volume_fraction"]
        if value <= accum:
            return b
    return RADIUS_BINS[-1]


def pick_bin_balanced(rng, bin_volume, current_total, target_volume):
    if rng.random() < BIN_BALANCE_RANDOMNESS:
        return pick_bin(rng)
    best = None
    best_deficit = None
    reference = max(current_total, 1.0e-12)
    for b in RADIUS_BINS:
        target = b["volume_fraction"] * min(target_volume, reference)
        deficit = target - bin_volume.get(b["name"], 0.0)
        if best is None or deficit > best_deficit:
            best = b
            best_deficit = deficit
    return best


def pick_radius(rng, bin_def):
    return rng.uniform(bin_def["r_min"], bin_def["r_max"])


def ball_distance_ok(candidate, existing):
    cx, cy, cz, cr = candidate
    for ex, ey, ez, er, _bin_name, _phase in existing:
        dx = cx - ex
        dy = cy - ey
        dz = cz - ez
        min_dist = MIN_CENTER_SPACING_FACTOR * (cr + er)
        if dx * dx + dy * dy + dz * dz < min_dist * min_dist:
            return False
    return True


def group_self_ok(group):
    for i, candidate in enumerate(group):
        others = [(x, y, z, r, "", "") for j, (x, y, z, r) in enumerate(group) if j != i]
        if not ball_distance_ok(candidate, others):
            return False
    return True


def bounds_for_axis(axis, radius, clearance):
    return (BOX_MIN[axis] + radius + clearance, BOX_MAX[axis] - radius - clearance)


def random_bounds(radius):
    bounds = {}
    for axis in ("x", "y", "z"):
        clearance = RANDOM_PERIODIC_FACE_CLEARANCE if axis in PERIODIC_AXES else PERIODIC_FACE_CLEARANCE
        bounds[axis] = bounds_for_axis(axis, radius, clearance)
    return bounds


def sample_random_position(rng, radius):
    bounds = random_bounds(radius)
    for axis, (low, high) in bounds.items():
        if low > high:
            raise ValueError("Radius {} is too large for random placement on {}".format(radius, axis))
    return (
        rng.uniform(bounds["x"][0], bounds["x"][1]),
        rng.uniform(bounds["y"][0], bounds["y"][1]),
        rng.uniform(bounds["z"][0], bounds["z"][1]),
    )


def sample_periodic_pair(rng, axis, radius):
    offset_min = PERIODIC_CUT_OFFSET_FRACTION_MIN * radius
    offset_max = min(
        PERIODIC_CUT_OFFSET_FRACTION_MAX * radius,
        PERIODIC_BAND_THICKNESS,
        0.5 * axis_length(axis) - radius - PERIODIC_FACE_CLEARANCE,
    )
    if offset_min > offset_max:
        raise ValueError("Radius {} is too large for periodic placement on {}".format(radius, axis))

    coords = {
        "x": None,
        "y": None,
        "z": None,
    }
    offset = rng.uniform(offset_min, offset_max)
    coords[axis] = (BOX_MIN[axis] + offset, BOX_MAX[axis] - offset)

    for transverse in ("x", "y", "z"):
        if transverse == axis:
            continue
        low, high = bounds_for_axis(transverse, radius, PERIODIC_FACE_CLEARANCE)
        if low > high:
            raise ValueError("Radius {} is too large for transverse placement".format(radius))
        coords[transverse] = rng.uniform(low, high)

    first = (coords["x"][0] if axis == "x" else coords["x"],
             coords["y"][0] if axis == "y" else coords["y"],
             coords["z"][0] if axis == "z" else coords["z"],
             radius)
    second = (coords["x"][1] if axis == "x" else coords["x"],
              coords["y"][1] if axis == "y" else coords["y"],
              coords["z"][1] if axis == "z" else coords["z"],
              radius)
    return [first, second]


def adjusted_final_radius(remaining_volume, group_size):
    radius = (remaining_volume / (group_size * (4.0 / 3.0) * math.pi)) ** (1.0 / 3.0)
    r_min = min(b["r_min"] for b in RADIUS_BINS)
    r_max = max(b["r_max"] for b in RADIUS_BINS)
    if radius < r_min or radius > r_max:
        return None
    return radius


def append_random_ball(rng, balls, target_volume, bin_volume, tolerance_volume):
    current = sum(sphere_volume(b[3]) for b in balls if b[5] == "random")
    remaining = target_volume - current
    if remaining <= tolerance_volume:
        return False, True
    bin_def = pick_bin_balanced(rng, bin_volume, current, target_volume)
    radius = pick_radius(rng, bin_def)
    volume = sphere_volume(radius)
    if volume > remaining + tolerance_volume:
        adjusted = adjusted_final_radius(remaining, 1) if ALLOW_FINAL_RADIUS_ADJUST else None
        if adjusted is None:
            return False, False
        radius = adjusted
        volume = sphere_volume(radius)
        bin_def = {"name": "adjusted-final"}
    x, y, z = sample_random_position(rng, radius)
    candidate = (x, y, z, radius)
    if not ball_distance_ok(candidate, balls):
        return False, False
    balls.append((x, y, z, radius, bin_def["name"], "random"))
    bin_volume[bin_def["name"]] = bin_volume.get(bin_def["name"], 0.0) + volume
    return True, False


def append_periodic_pair(rng, balls, axis, target_volume, bin_volume, tolerance_volume):
    phase = phase_for_axis(axis)
    current = sum(sphere_volume(b[3]) for b in balls if b[5] == phase)
    remaining = target_volume - current
    if remaining <= tolerance_volume:
        return False, True
    bin_def = pick_bin_balanced(rng, bin_volume, current, target_volume)
    radius = pick_radius(rng, bin_def)
    pair_volume = 2.0 * sphere_volume(radius)
    if pair_volume > remaining + tolerance_volume:
        adjusted = adjusted_final_radius(remaining, 2) if ALLOW_FINAL_RADIUS_ADJUST else None
        if adjusted is None:
            return False, False
        radius = adjusted
        pair_volume = 2.0 * sphere_volume(radius)
        bin_def = {"name": "adjusted-final"}
    pair = sample_periodic_pair(rng, axis, radius)
    if not group_self_ok(pair):
        return False, False
    for candidate in pair:
        if not ball_distance_ok(candidate, balls):
            return False, False
    for x, y, z, r in pair:
        balls.append((x, y, z, r, bin_def["name"], phase))
    bin_volume[bin_def["name"]] = bin_volume.get(bin_def["name"], 0.0) + pair_volume
    return True, False


def generate_pack():
    validate_parameters()
    rng = random.Random(RANDOM_SEED)
    tolerance_volume = POROSITY_TOLERANCE * box_volume() * 0.5
    random_target, periodic_targets = phase_targets()
    balls = []
    random_bin_volume = dict((b["name"], 0.0) for b in RADIUS_BINS)
    periodic_bin_volume = dict((axis, dict((b["name"], 0.0) for b in RADIUS_BINS))
                               for axis in PERIODIC_AXES)
    attempts = {"random": 0}
    attempts.update(dict((axis, 0) for axis in PERIODIC_AXES))
    done_random = False
    done_periodic = dict((axis, False) for axis in PERIODIC_AXES)

    while sum(attempts.values()) < MAX_INSERT_ATTEMPTS:
        for axis in PERIODIC_AXES:
            if not done_periodic[axis]:
                attempts[axis] += 1
                _added, done_periodic[axis] = append_periodic_pair(
                    rng, balls, axis, periodic_targets[axis],
                    periodic_bin_volume[axis], tolerance_volume)
        if not done_random:
            attempts["random"] += 1
            _added, done_random = append_random_ball(
                rng, balls, random_target, random_bin_volume, tolerance_volume)
        if done_random and all(done_periodic.values()):
            break

    actual_solid = sum(sphere_volume(b[3]) for b in balls)
    actual_porosity = 1.0 - actual_solid / box_volume()
    if abs(actual_porosity - TARGET_POROSITY) > POROSITY_TOLERANCE:
        raise RuntimeError(
            "Could not reach target porosity. target={:.6f}, actual={:.6f}, balls={}, attempts={}. "
            "Try lowering MIN_CENTER_SPACING_FACTOR, increasing MAX_INSERT_ATTEMPTS, or changing radius bins."
            .format(TARGET_POROSITY, actual_porosity, len(balls), attempts)
        )
    return balls, random_bin_volume, periodic_bin_volume, attempts


def create_in_pfc(balls):
    if it is None:
        return
    it.command("ball delete")
    for idx, (x, y, z, radius, bin_name, phase) in enumerate(balls, 1):
        ball = it.ball.create(radius, (x, y, z), idx)
        try:
            ball.set_group("particles")
            ball.set_group(bin_name, "size_bin")
            ball.set_group(phase, "layer")
        except TypeError:
            it.command("ball group '{}' slot 'layer' range id {}".format(phase, idx))
            it.command("ball group '{}' slot 'size_bin' range id {}".format(bin_name, idx))
    it.command("ball attribute density {} damp {}".format(BALL_DENSITY, BALL_DAMP))


def print_bin_summary(title, bin_volume, solid):
    print(title)
    for name in sorted(bin_volume):
        if bin_volume[name] > 0.0 and solid > 0.0:
            print("  bin {:>14s}: volume_fraction={:.6f}".format(name, bin_volume[name] / solid))


def print_summary(balls, random_bin_volume, periodic_bin_volume, attempts):
    actual_solid = sum(sphere_volume(b[3]) for b in balls)
    actual_porosity = 1.0 - actual_solid / box_volume()
    random_solid = sum(sphere_volume(b[3]) for b in balls if b[5] == "random")
    random_count = len([b for b in balls if b[5] == "random"])
    print("")
    print("=== Cyclic-face / random-interior pack generated ===")
    print("box volume:        {:.8f} mm^3".format(box_volume()))
    print("periodic axes:     {}".format(", ".join(PERIODIC_AXES) if PERIODIC_AXES else "none"))
    print("periodic band:     {:.8f} mm".format(PERIODIC_BAND_THICKNESS))
    print("target porosity:   {:.8f}".format(TARGET_POROSITY))
    print("actual porosity:   {:.8f}".format(actual_porosity))
    print("solid volume:      {:.8f} mm^3".format(actual_solid))
    print("random balls:      {}".format(random_count))
    for axis in PERIODIC_AXES:
        phase = phase_for_axis(axis)
        count = len([b for b in balls if b[5] == phase])
        solid = sum(sphere_volume(b[3]) for b in balls if b[5] == phase)
        print("periodic {} balls: {} ({} face pairs)".format(axis, count, count // 2))
        print_bin_summary("periodic {} bins:".format(axis), periodic_bin_volume[axis], solid)
    print("attempts:          {}".format(attempts))
    print("radius min/max:    {:.8f} / {:.8f} mm".format(
        min(b[3] for b in balls), max(b[3] for b in balls)))
    print_bin_summary("random bins:", random_bin_volume, random_solid)
    print("===================================================")


def main():
    balls, random_bin_volume, periodic_bin_volume, attempts = generate_pack()
    create_in_pfc(balls)
    print_summary(balls, random_bin_volume, periodic_bin_volume, attempts)


if __name__ == "__main__":
    main()
