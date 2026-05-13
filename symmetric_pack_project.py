# Project relaxed balls back to the intended wall-symmetric constraints.
# Random balls are kept inside the full specimen and away from side-wall contact.
# Wall balls are projected to exact x/y mirror symmetry and kept in the wall band.

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
WALL_BAND_THICKNESS = sp.WALL_BAND_THICKNESS


BOUND_EPS = 1.0e-6


def clamp(value, low, high):
    return max(low, min(high, value))


def ball_phase(ball):
    if ball.in_group("random", "layer"):
        return "random"
    if ball.in_group("wall", "layer"):
        return "wall"
    raise RuntimeError("Ball {} has no layer group".format(ball.id()))


def project_random(ball):
    radius = float(ball.radius())
    pos = ball.pos()
    x = clamp(
        float(pos[0]),
        BOX_X_MIN + radius + RANDOM_SIDE_WALL_CLEARANCE + BOUND_EPS,
        BOX_X_MAX - radius - RANDOM_SIDE_WALL_CLEARANCE - BOUND_EPS,
    )
    y = clamp(
        float(pos[1]),
        BOX_Y_MIN + radius + RANDOM_SIDE_WALL_CLEARANCE + BOUND_EPS,
        BOX_Y_MAX - radius - RANDOM_SIDE_WALL_CLEARANCE - BOUND_EPS,
    )
    z = clamp(float(pos[2]), BOX_Z_MIN + radius + BOUND_EPS, BOX_Z_MAX - radius - BOUND_EPS)
    ball.set_pos((x, y, z))


def project_wall_group(group):
    radii = [float(b.radius()) for b in group]
    radius = sum(radii) / 4.0
    if max(abs(r - radius) for r in radii) > 1.0e-8:
        raise RuntimeError("Mirror group has inconsistent radii near ball id {}".format(group[0].id()))

    positions = [b.pos() for b in group]
    x_abs = sum(abs(float(p[0])) for p in positions) / 4.0
    y_abs = sum(abs(float(p[1])) for p in positions) / 4.0
    z = sum(float(p[2]) for p in positions) / 4.0

    min_wall_band = BOX_X_MAX - WALL_BAND_THICKNESS
    if x_abs < min_wall_band and y_abs < min_wall_band:
        if x_abs >= y_abs:
            x_abs = min_wall_band
        else:
            y_abs = min_wall_band

    x_abs = clamp(x_abs, radius + BOUND_EPS, BOX_X_MAX - radius - BOUND_EPS)
    y_abs = clamp(y_abs, radius + BOUND_EPS, BOX_Y_MAX - radius - BOUND_EPS)
    z = clamp(z, BOX_Z_MIN + radius + BOUND_EPS, BOX_Z_MAX - radius - BOUND_EPS)

    target_positions = (
        (x_abs, y_abs, z),
        (-x_abs, y_abs, z),
        (x_abs, -y_abs, z),
        (-x_abs, -y_abs, z),
    )
    for ball, pos in zip(group, target_positions):
        ball.set_pos(pos)


def main():
    if it is None:
        print("symmetric_pack_project.py only changes positions inside PFC.")
        return

    random_balls = []
    wall_balls = []
    for ball in sorted(list(it.ball.list()), key=lambda b: b.id()):
        if ball_phase(ball) == "random":
            random_balls.append(ball)
        else:
            wall_balls.append(ball)

    if len(wall_balls) % 4 != 0:
        raise RuntimeError("Wall ball count is not divisible by 4: {}".format(len(wall_balls)))

    for ball in random_balls:
        project_random(ball)
    for i in range(0, len(wall_balls), 4):
        project_wall_group(wall_balls[i:i + 4])

    print("Projected {} random balls and {} wall balls to final constraints.".format(
        len(random_balls), len(wall_balls)))


if __name__ == "__main__":
    main()
