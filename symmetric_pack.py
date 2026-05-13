# PFC3D wall-symmetric / interior-random particle generator.
# Only the particles placed near the four side walls are mirrored about x=0 and
# y=0. Interior particles are random across the full specimen so no artificial
# inner/outer interface channel is introduced.

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

# Historical central zone size used only for printed diagnostics. Random balls
# are not confined to this zone.
DIAGNOSTIC_CORE_HALF_WIDTH = 0.75

# Side-wall contact fabric. Mirror-symmetric balls are sampled in a band near
# the four vertical walls. Random balls can occupy the rest of the specimen and
# contact these wall balls naturally, but they are kept just away from the side
# walls so side-wall-contacting balls remain mirror-symmetric.
WALL_BAND_THICKNESS = 0.55
RANDOM_SIDE_WALL_CLEARANCE = 0.03
WALL_RELAXATION_CLEARANCE = 0.03

# Fraction of total solid volume assigned to mirror-symmetric wall balls. Keep
# this lower than the geometric wall-band volume fraction because random balls
# are allowed to naturally penetrate and contact the wall fabric.
WALL_SOLID_VOLUME_FRACTION = 0.40

# Radius bins in mm. volume_fraction values should sum to 1.0.
RADIUS_BINS = [
    {"name": "fine", "r_min": 0.2125, "r_max": 0.2400, "volume_fraction": 0.25},
    {"name": "medium", "r_min": 0.2400, "r_max": 0.2700, "volume_fraction": 0.45},
    {"name": "coarse", "r_min": 0.2700, "r_max": 0.3000, "volume_fraction": 0.30},
]

# 1.0 means no initial overlap. Values below 1.0 allow controlled initial
# overlap, which PFC can relax during cycling.
MIN_CENTER_SPACING_FACTOR = 0.55
CENTERLINE_CLEARANCE_FACTOR = MIN_CENTER_SPACING_FACTOR
MAX_INSERT_ATTEMPTS = 700000
BIN_BALANCE_RANDOMNESS = 0.15

BALL_DENSITY = 2160.0
BALL_DAMP = 0.8

# If the remaining target volume is smaller than a normal sampled ball/group,
# this option allows one final adjusted-radius ball/group.
ALLOW_FINAL_RADIUS_ADJUST = True


# ----------------------- geometry helpers -----------------------

def box_volume():
    return ((BOX_X_MAX - BOX_X_MIN) *
            (BOX_Y_MAX - BOX_Y_MIN) *
            (BOX_Z_MAX - BOX_Z_MIN))


def diagnostic_core_volume():
    return ((2.0 * DIAGNOSTIC_CORE_HALF_WIDTH) *
            (2.0 * DIAGNOSTIC_CORE_HALF_WIDTH) *
            (BOX_Z_MAX - BOX_Z_MIN))


def wall_band_volume():
    inner_width = max(0.0, (BOX_X_MAX - BOX_X_MIN) - 2.0 * WALL_BAND_THICKNESS)
    inner_depth = max(0.0, (BOX_Y_MAX - BOX_Y_MIN) - 2.0 * WALL_BAND_THICKNESS)
    inner_volume = inner_width * inner_depth * (BOX_Z_MAX - BOX_Z_MIN)
    return box_volume() - inner_volume


def sphere_volume(radius):
    return 4.0 / 3.0 * math.pi * radius ** 3


def mirror_positions(x, y, z):
    return ((x, y, z), (-x, y, z), (x, -y, z), (-x, -y, z))


def target_solid_volume():
    return (1.0 - TARGET_POROSITY) * box_volume()


def phase_targets():
    total = target_solid_volume()
    if WALL_SOLID_VOLUME_FRACTION is None:
        wall_target = total * wall_band_volume() / box_volume()
    else:
        wall_target = total * WALL_SOLID_VOLUME_FRACTION
    return total - wall_target, wall_target


def validate_bins():
    total = sum(b["volume_fraction"] for b in RADIUS_BINS)
    if abs(total - 1.0) > 1.0e-8:
        raise ValueError("RADIUS_BINS volume_fraction values must sum to 1.0")
    for b in RADIUS_BINS:
        if b["r_min"] <= 0.0 or b["r_max"] < b["r_min"]:
            raise ValueError("Invalid radius bin: {}".format(b))
    if WALL_BAND_THICKNESS <= 0.0:
        raise ValueError("WALL_BAND_THICKNESS must be positive")


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


def random_bounds(radius):
    return (
        BOX_X_MIN + radius + RANDOM_SIDE_WALL_CLEARANCE,
        BOX_X_MAX - radius - RANDOM_SIDE_WALL_CLEARANCE,
        BOX_Y_MIN + radius + RANDOM_SIDE_WALL_CLEARANCE,
        BOX_Y_MAX - radius - RANDOM_SIDE_WALL_CLEARANCE,
        BOX_Z_MIN + radius + WALL_RELAXATION_CLEARANCE,
        BOX_Z_MAX - radius - WALL_RELAXATION_CLEARANCE,
    )


def wall_positive_bounds(radius):
    return (
        max(radius + WALL_RELAXATION_CLEARANCE, CENTERLINE_CLEARANCE_FACTOR * radius),
        BOX_X_MAX - radius - WALL_RELAXATION_CLEARANCE,
        max(radius + WALL_RELAXATION_CLEARANCE, CENTERLINE_CLEARANCE_FACTOR * radius),
        BOX_Y_MAX - radius - WALL_RELAXATION_CLEARANCE,
        BOX_Z_MIN + radius + WALL_RELAXATION_CLEARANCE,
        BOX_Z_MAX - radius - WALL_RELAXATION_CLEARANCE,
    )


def sample_random_position(rng, radius):
    xmin, xmax, ymin, ymax, zmin, zmax = random_bounds(radius)
    if xmin > xmax or ymin > ymax or zmin > zmax:
        raise ValueError("Radius {} is too large for random placement".format(radius))
    return (rng.uniform(xmin, xmax), rng.uniform(ymin, ymax), rng.uniform(zmin, zmax))


def sample_wall_group_position(rng, radius):
    xmin, xmax, ymin, ymax, zmin, zmax = wall_positive_bounds(radius)
    if xmin > xmax or ymin > ymax or zmin > zmax:
        raise ValueError("Radius {} is too large for wall placement".format(radius))

    threshold = BOX_X_MAX - WALL_BAND_THICKNESS
    for _ in range(1000):
        x = rng.uniform(xmin, xmax)
        y = rng.uniform(ymin, ymax)
        z = rng.uniform(zmin, zmax)
        if x >= threshold or y >= threshold:
            return x, y, z
    raise RuntimeError("Could not sample a wall-band position for radius {}".format(radius))


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


def append_wall_group(rng, balls, target_volume, bin_volume, tolerance_volume):
    current = sum(sphere_volume(b[3]) for b in balls if b[5] == "wall")
    remaining = target_volume - current
    if remaining <= tolerance_volume:
        return False, True
    bin_def = pick_bin_balanced(rng, bin_volume, current, target_volume)
    radius = pick_radius(rng, bin_def)
    group_volume = 4.0 * sphere_volume(radius)
    if group_volume > remaining + tolerance_volume:
        adjusted = adjusted_final_radius(remaining, 4) if ALLOW_FINAL_RADIUS_ADJUST else None
        if adjusted is None:
            return False, False
        radius = adjusted
        group_volume = 4.0 * sphere_volume(radius)
        bin_def = {"name": "adjusted-final"}
    x, y, z = sample_wall_group_position(rng, radius)
    group = [(px, py, pz, radius) for px, py, pz in mirror_positions(x, y, z)]
    if not group_self_ok(group):
        return False, False
    for candidate in group:
        if not ball_distance_ok(candidate, balls):
            return False, False
    for px, py, pz, r in group:
        balls.append((px, py, pz, r, bin_def["name"], "wall"))
    bin_volume[bin_def["name"]] = bin_volume.get(bin_def["name"], 0.0) + group_volume
    return True, False


def generate_pack():
    validate_bins()
    rng = random.Random(RANDOM_SEED)
    tolerance_volume = POROSITY_TOLERANCE * box_volume() * 0.5
    random_target, wall_target = phase_targets()
    balls = []
    random_bin_volume = dict((b["name"], 0.0) for b in RADIUS_BINS)
    wall_bin_volume = dict((b["name"], 0.0) for b in RADIUS_BINS)
    attempts = {"random": 0, "wall": 0}
    done_random = False
    done_wall = False

    while attempts["random"] + attempts["wall"] < MAX_INSERT_ATTEMPTS:
        if not done_wall:
            attempts["wall"] += 1
            _added, done_wall = append_wall_group(rng, balls, wall_target, wall_bin_volume, tolerance_volume)
        if not done_random:
            attempts["random"] += 1
            _added, done_random = append_random_ball(rng, balls, random_target, random_bin_volume, tolerance_volume)
        if done_random and done_wall:
            break

    actual_solid = sum(sphere_volume(b[3]) for b in balls)
    actual_porosity = 1.0 - actual_solid / box_volume()
    if abs(actual_porosity - TARGET_POROSITY) > POROSITY_TOLERANCE:
        raise RuntimeError(
            "Could not reach target porosity. target={:.6f}, actual={:.6f}, balls={}, attempts={}. "
            "Try lowering MIN_CENTER_SPACING_FACTOR, increasing MAX_INSERT_ATTEMPTS, or changing radius bins."
            .format(TARGET_POROSITY, actual_porosity, len(balls), attempts)
        )
    return balls, random_bin_volume, wall_bin_volume, attempts


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


def print_summary(balls, random_bin_volume, wall_bin_volume, attempts):
    actual_solid = sum(sphere_volume(b[3]) for b in balls)
    actual_porosity = 1.0 - actual_solid / box_volume()
    random_solid = sum(sphere_volume(b[3]) for b in balls if b[5] == "random")
    wall_solid = sum(sphere_volume(b[3]) for b in balls if b[5] == "wall")
    random_count = len([b for b in balls if b[5] == "random"])
    wall_count = len([b for b in balls if b[5] == "wall"])
    print("")
    print("=== Wall-symmetric / random-interior pack generated ===")
    print("box volume:        {:.8f} mm^3".format(box_volume()))
    print("diagnostic core:   {:.8f} mm^3 (not a hard boundary)".format(diagnostic_core_volume()))
    print("wall band volume:  {:.8f} mm^3".format(wall_band_volume()))
    print("target porosity:   {:.8f}".format(TARGET_POROSITY))
    print("actual porosity:   {:.8f}".format(actual_porosity))
    print("solid volume:      {:.8f} mm^3".format(actual_solid))
    print("random balls:      {}".format(random_count))
    print("wall balls:        {} mirror-symmetric ({} groups)".format(wall_count, wall_count // 4))
    print("attempts:          random={} wall={}".format(attempts["random"], attempts["wall"]))
    print("radius min/max:    {:.8f} / {:.8f} mm".format(
        min(b[3] for b in balls), max(b[3] for b in balls)))
    print_bin_summary("random bins:", random_bin_volume, random_solid)
    print_bin_summary("wall bins:", wall_bin_volume, wall_solid)
    print("======================================================")


def main():
    balls, random_bin_volume, wall_bin_volume, attempts = generate_pack()
    create_in_pfc(balls)
    print_summary(balls, random_bin_volume, wall_bin_volume, attempts)


if __name__ == "__main__":
    main()
