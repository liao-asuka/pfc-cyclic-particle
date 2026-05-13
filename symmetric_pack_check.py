# Post-generation checks for the wall-symmetric / random-interior PFC packing.

from __future__ import print_function

try:
    import itasca as it
except ImportError:
    it = None

import importlib
import symmetric_pack as sp
sp = importlib.reload(sp)

BOX_X_MIN = sp.BOX_X_MIN
BOX_X_MAX = sp.BOX_X_MAX
BOX_Y_MIN = sp.BOX_Y_MIN
BOX_Y_MAX = sp.BOX_Y_MAX
BOX_Z_MIN = sp.BOX_Z_MIN
BOX_Z_MAX = sp.BOX_Z_MAX
RANDOM_SIDE_WALL_CLEARANCE = sp.RANDOM_SIDE_WALL_CLEARANCE
TARGET_POROSITY = sp.TARGET_POROSITY
POROSITY_TOLERANCE = sp.POROSITY_TOLERANCE
box_volume = sp.box_volume
sphere_volume = sp.sphere_volume
generate_pack = sp.generate_pack


MIRROR_TOLERANCE = 1.0e-5
BOUND_TOLERANCE = 1.0e-2
RANDOM_SIDE_WALL_TOLERANCE = 1.0e-2


def normalized_key(x, y, z, r):
    return (round(x, 5), round(y, 5), round(z, 5), round(r, 5))


def balls_from_pfc():
    result = []
    for b in it.ball.list():
        pos = b.pos()
        if b.in_group("random", "layer"):
            phase = "random"
        elif b.in_group("wall", "layer"):
            phase = "wall"
        else:
            raise RuntimeError("Ball {} has no layer group".format(b.id()))
        result.append((float(pos[0]), float(pos[1]), float(pos[2]), float(b.radius()), phase))
    return result


def check_box_bounds(balls):
    for x, y, z, r, phase in balls:
        if x - r < BOX_X_MIN - BOUND_TOLERANCE or x + r > BOX_X_MAX + BOUND_TOLERANCE:
            raise RuntimeError("Ball out of x bounds: {}".format((x, y, z, r, phase)))
        if y - r < BOX_Y_MIN - BOUND_TOLERANCE or y + r > BOX_Y_MAX + BOUND_TOLERANCE:
            raise RuntimeError("Ball out of y bounds: {}".format((x, y, z, r, phase)))
        if z - r < BOX_Z_MIN - BOUND_TOLERANCE or z + r > BOX_Z_MAX + BOUND_TOLERANCE:
            raise RuntimeError("Ball out of z bounds: {}".format((x, y, z, r, phase)))


def check_random_side_wall_clearance(balls):
    limit_x = BOX_X_MAX - RANDOM_SIDE_WALL_CLEARANCE + RANDOM_SIDE_WALL_TOLERANCE
    limit_y = BOX_Y_MAX - RANDOM_SIDE_WALL_CLEARANCE + RANDOM_SIDE_WALL_TOLERANCE
    for x, y, _z, r, phase in balls:
        if phase != "random":
            continue
        if abs(x) + r > limit_x:
            raise RuntimeError("Random ball is contacting the x side wall: {}".format((x, y, r)))
        if abs(y) + r > limit_y:
            raise RuntimeError("Random ball is contacting the y side wall: {}".format((x, y, r)))


def check_wall_symmetry(balls):
    wall = [(x, y, z, r) for x, y, z, r, phase in balls if phase == "wall"]
    keys = set(normalized_key(x, y, z, r) for x, y, z, r in wall)
    for x, y, z, r in wall:
        mirrors = [
            normalized_key(-x, y, z, r),
            normalized_key(x, -y, z, r),
            normalized_key(-x, -y, z, r),
        ]
        for key in mirrors:
            if key not in keys:
                raise RuntimeError("Missing wall mirror ball for {}".format((x, y, z, r)))


def check_porosity(balls):
    solid = sum(sphere_volume(r) for _x, _y, _z, r, _phase in balls)
    porosity = 1.0 - solid / box_volume()
    if abs(porosity - TARGET_POROSITY) > POROSITY_TOLERANCE:
        raise RuntimeError(
            "Porosity outside tolerance: target={:.8f}, actual={:.8f}"
            .format(TARGET_POROSITY, porosity)
        )
    return porosity, solid


def main():
    if it is None:
        generated, _random_bins, _wall_bins, _attempts = generate_pack()
        balls = [(x, y, z, r, phase) for x, y, z, r, _name, phase in generated]
    else:
        balls = balls_from_pfc()

    if not balls:
        raise RuntimeError("No balls found for wall-symmetric pack check")
    check_box_bounds(balls)
    check_random_side_wall_clearance(balls)
    check_wall_symmetry(balls)
    porosity, solid = check_porosity(balls)
    random_count = len([b for b in balls if b[4] == "random"])
    wall_count = len([b for b in balls if b[4] == "wall"])
    print("")
    print("=== Wall-symmetric pack check passed ===")
    print("ball count:      {}".format(len(balls)))
    print("random balls:    {}".format(random_count))
    print("wall balls:      {} ({} mirror groups)".format(wall_count, wall_count // 4))
    print("solid volume:    {:.8f} mm^3".format(solid))
    print("porosity:        {:.8f}".format(porosity))
    print("========================================")


if __name__ == "__main__":
    main()
