# Post-generation checks for the cyclic-face / random-interior PFC packing.

from __future__ import print_function

try:
    import itasca as it
except ImportError:
    it = None

import importlib
import cyclic_pack as cp
cp = importlib.reload(cp)


PAIR_TOLERANCE = 1.0e-5
BOUND_TOLERANCE = 1.0e-2
RANDOM_FACE_TOLERANCE = 1.0e-2


def balls_from_pfc():
    result = []
    for b in it.ball.list():
        pos = b.pos()
        phase = None
        if b.in_group("random", "layer"):
            phase = "random"
        else:
            for axis in cp.PERIODIC_AXES:
                candidate = cp.phase_for_axis(axis)
                if b.in_group(candidate, "layer"):
                    phase = candidate
                    break
        if phase is None:
            raise RuntimeError("Ball {} has no known layer group".format(b.id()))
        result.append((float(pos[0]), float(pos[1]), float(pos[2]), float(b.radius()), phase))
    return result


def check_box_bounds(balls):
    for x, y, z, r, phase in balls:
        coords = {"x": x, "y": y, "z": z}
        crossing_axis = phase.replace("periodic_", "") if phase.startswith("periodic_") else None
        for axis in ("x", "y", "z"):
            center = coords[axis]
            if center < cp.BOX_MIN[axis] - BOUND_TOLERANCE or center > cp.BOX_MAX[axis] + BOUND_TOLERANCE:
                raise RuntimeError("Ball center out of {} bounds: {}".format(axis, (x, y, z, r, phase)))
            if axis == crossing_axis:
                continue
            if center - r < cp.BOX_MIN[axis] - BOUND_TOLERANCE:
                raise RuntimeError("Ball out of {} min bounds: {}".format(axis, (x, y, z, r, phase)))
            if center + r > cp.BOX_MAX[axis] + BOUND_TOLERANCE:
                raise RuntimeError("Ball out of {} max bounds: {}".format(axis, (x, y, z, r, phase)))


def check_random_face_clearance(balls):
    for x, y, z, r, phase in balls:
        if phase != "random":
            continue
        coords = {"x": x, "y": y, "z": z}
        for axis in cp.PERIODIC_AXES:
            limit = cp.RANDOM_PERIODIC_FACE_CLEARANCE - RANDOM_FACE_TOLERANCE
            min_gap = coords[axis] - r - cp.BOX_MIN[axis]
            max_gap = cp.BOX_MAX[axis] - coords[axis] - r
            if min_gap < limit or max_gap < limit:
                raise RuntimeError(
                    "Random ball is too close to cyclic {} face: {}".format(axis, (x, y, z, r))
                )


def check_periodic_pairs(balls):
    for axis in cp.PERIODIC_AXES:
        phase = cp.phase_for_axis(axis)
        axis_balls = [(x, y, z, r) for x, y, z, r, p in balls if p == phase]
        if len(axis_balls) % 2 != 0:
            raise RuntimeError("Periodic {} ball count is not divisible by 2".format(axis))
        for i in range(0, len(axis_balls), 2):
            first = axis_balls[i]
            second = axis_balls[i + 1]
            first_coords = {"x": first[0], "y": first[1], "z": first[2]}
            second_coords = {"x": second[0], "y": second[1], "z": second[2]}
            if abs(first[3] - second[3]) > PAIR_TOLERANCE:
                raise RuntimeError("Periodic {} pair radius mismatch: {} {}".format(axis, first, second))
            first_min_offset = first_coords[axis] - cp.BOX_MIN[axis]
            second_max_offset = cp.BOX_MAX[axis] - second_coords[axis]
            if abs(first_min_offset - second_max_offset) > PAIR_TOLERANCE:
                raise RuntimeError("Periodic {} pair face-offset mismatch: {} {}".format(axis, first, second))
            if first_min_offset >= first[3] or second_max_offset >= second[3]:
                raise RuntimeError("Periodic {} pair does not cross the cut face: {} {}".format(axis, first, second))
            for transverse in ("x", "y", "z"):
                if transverse == axis:
                    continue
                if abs(first_coords[transverse] - second_coords[transverse]) > PAIR_TOLERANCE:
                    raise RuntimeError(
                        "Periodic {} pair transverse mismatch on {}: {} {}"
                        .format(axis, transverse, first, second)
                    )


def check_porosity(balls):
    solid = sum(cp.sphere_volume(r) for _x, _y, _z, r, _phase in balls)
    porosity = 1.0 - solid / cp.box_volume()
    if abs(porosity - cp.TARGET_POROSITY) > cp.POROSITY_TOLERANCE:
        raise RuntimeError(
            "Porosity outside tolerance: target={:.8f}, actual={:.8f}"
            .format(cp.TARGET_POROSITY, porosity)
        )
    return porosity, solid


def main():
    if it is None:
        generated, _random_bins, _periodic_bins, _attempts = cp.generate_pack()
        balls = [(x, y, z, r, phase) for x, y, z, r, _name, phase in generated]
    else:
        balls = balls_from_pfc()

    if not balls:
        raise RuntimeError("No balls found for cyclic pack check")
    check_box_bounds(balls)
    check_random_face_clearance(balls)
    check_periodic_pairs(balls)
    porosity, solid = check_porosity(balls)
    random_count = len([b for b in balls if b[4] == "random"])
    print("")
    print("=== Cyclic-face pack check passed ===")
    print("ball count:      {}".format(len(balls)))
    print("random balls:    {}".format(random_count))
    for axis in cp.PERIODIC_AXES:
        count = len([b for b in balls if b[4] == cp.phase_for_axis(axis)])
        print("periodic {}:     {} balls ({} face pairs)".format(axis, count, count // 2))
    print("solid volume:    {:.8f} mm^3".format(solid))
    print("porosity:        {:.8f}".format(porosity))
    print("=====================================")


if __name__ == "__main__":
    main()
