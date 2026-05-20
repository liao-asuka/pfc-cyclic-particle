# Project relaxed balls back to the intended cyclic-face constraints.

from __future__ import print_function

try:
    import itasca as it
except ImportError:
    it = None

import importlib
import cyclic_pack as cp
cp = importlib.reload(cp)


BOUND_EPS = 1.0e-6


def clamp(value, low, high):
    return max(low, min(high, value))


def ball_phase(ball):
    if ball.in_group("random", "layer"):
        return "random"
    for axis in cp.PERIODIC_AXES:
        phase = cp.phase_for_axis(axis)
        if ball.in_group(phase, "layer"):
            return phase
    raise RuntimeError("Ball {} has no known layer group".format(ball.id()))


def set_ball_pos(ball, coords):
    ball.set_pos((coords["x"], coords["y"], coords["z"]))


def project_random(ball):
    radius = float(ball.radius())
    pos = ball.pos()
    coords = {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])}
    for axis in ("x", "y", "z"):
        clearance = cp.RANDOM_PERIODIC_FACE_CLEARANCE if axis in cp.PERIODIC_AXES else cp.PERIODIC_FACE_CLEARANCE
        low = cp.BOX_MIN[axis] + radius + clearance + BOUND_EPS
        high = cp.BOX_MAX[axis] - radius - clearance - BOUND_EPS
        coords[axis] = clamp(coords[axis], low, high)
    set_ball_pos(ball, coords)


def project_periodic_pair(axis, pair):
    radii = [float(b.radius()) for b in pair]
    radius = sum(radii) / 2.0
    if max(abs(r - radius) for r in radii) > 1.0e-8:
        raise RuntimeError("Periodic pair has inconsistent radii near ball id {}".format(pair[0].id()))

    positions = []
    for ball in pair:
        pos = ball.pos()
        positions.append({"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])})

    offset_min = cp.PERIODIC_CUT_OFFSET_FRACTION_MIN * radius + BOUND_EPS
    offset_max = min(
        cp.PERIODIC_CUT_OFFSET_FRACTION_MAX * radius,
        cp.PERIODIC_BAND_THICKNESS,
        0.5 * cp.axis_length(axis) - radius - cp.PERIODIC_FACE_CLEARANCE,
    ) - BOUND_EPS

    inward_offsets = []
    for pos in positions:
        inward_offsets.append(min(pos[axis] - cp.BOX_MIN[axis], cp.BOX_MAX[axis] - pos[axis]))
    offset = clamp(sum(inward_offsets) / 2.0, offset_min, offset_max)

    transverse = {}
    for other_axis in ("x", "y", "z"):
        if other_axis == axis:
            continue
        low = cp.BOX_MIN[other_axis] + radius + cp.PERIODIC_FACE_CLEARANCE + BOUND_EPS
        high = cp.BOX_MAX[other_axis] - radius - cp.PERIODIC_FACE_CLEARANCE - BOUND_EPS
        transverse[other_axis] = clamp(
            sum(pos[other_axis] for pos in positions) / 2.0,
            low,
            high,
        )

    min_coords = dict(transverse)
    max_coords = dict(transverse)
    min_coords[axis] = cp.BOX_MIN[axis] + offset
    max_coords[axis] = cp.BOX_MAX[axis] - offset

    set_ball_pos(pair[0], min_coords)
    set_ball_pos(pair[1], max_coords)


def main():
    if it is None:
        print("cyclic_pack_project.py only changes positions inside PFC.")
        return

    random_balls = []
    periodic_balls = dict((axis, []) for axis in cp.PERIODIC_AXES)
    for ball in sorted(list(it.ball.list()), key=lambda b: b.id()):
        phase = ball_phase(ball)
        if phase == "random":
            random_balls.append(ball)
        else:
            periodic_balls[phase.replace("periodic_", "")].append(ball)

    for ball in random_balls:
        project_random(ball)
    for axis in cp.PERIODIC_AXES:
        balls = periodic_balls[axis]
        if len(balls) % 2 != 0:
            raise RuntimeError("Periodic {} ball count is not divisible by 2: {}".format(axis, len(balls)))
        for i in range(0, len(balls), 2):
            project_periodic_pair(axis, balls[i:i + 2])

    periodic_count = sum(len(v) for v in periodic_balls.values())
    print("Projected {} random balls and {} periodic balls to final constraints.".format(
        len(random_balls), periodic_count))


if __name__ == "__main__":
    main()
