# Export the current PFC balls and six wall faces to one ASCII STL file.

from __future__ import print_function

import math
import os

try:
    import itasca as it
except ImportError:
    it = None

import importlib
import symmetric_pack as sp
sp = importlib.reload(sp)


EXPORT_DIR = r"E:\codexfile\pfc cyclic particle\STLfile"
EXPORT_BASENAME = "cyc-particles-1"
EXPORT_PATH = os.path.join(EXPORT_DIR, EXPORT_BASENAME + ".stl")

# Sphere mesh resolution. Increase these for smoother exported particles.
SPHERE_LAT_SEGMENTS = 12
SPHERE_LON_SEGMENTS = 24


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
    for p in (p1, p2, p3):
        handle.write("      vertex {:.8e} {:.8e} {:.8e}\n".format(p[0], p[1], p[2]))
    handle.write("    endloop\n")
    handle.write("  endfacet\n")


def sphere_point(center, radius, theta, phi):
    sin_theta = math.sin(theta)
    return (
        center[0] + radius * sin_theta * math.cos(phi),
        center[1] + radius * sin_theta * math.sin(phi),
        center[2] + radius * math.cos(theta),
    )


def write_sphere(handle, center, radius):
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
                write_triangle(handle, p1, p2, p3)
            elif i == SPHERE_LAT_SEGMENTS - 1:
                write_triangle(handle, p1, p2, p4)
            else:
                write_triangle(handle, p1, p2, p3)
                write_triangle(handle, p1, p3, p4)


def wall_faces():
    xmin, xmax = sp.BOX_X_MIN, sp.BOX_X_MAX
    ymin, ymax = sp.BOX_Y_MIN, sp.BOX_Y_MAX
    zmin, zmax = sp.BOX_Z_MIN, sp.BOX_Z_MAX
    return [
        ("inlet",  [(xmin, ymin, zmax), (xmax, ymin, zmax), (xmax, ymax, zmax), (xmin, ymax, zmax)]),
        ("outlet", [(xmin, ymin, zmin), (xmin, ymax, zmin), (xmax, ymax, zmin), (xmax, ymin, zmin)]),
        ("wall_left",  [(xmin, ymin, zmin), (xmin, ymin, zmax), (xmin, ymax, zmax), (xmin, ymax, zmin)]),
        ("wall_right", [(xmax, ymin, zmin), (xmax, ymax, zmin), (xmax, ymax, zmax), (xmax, ymin, zmax)]),
        ("wall_front", [(xmin, ymin, zmin), (xmax, ymin, zmin), (xmax, ymin, zmax), (xmin, ymin, zmax)]),
        ("wall_back",  [(xmin, ymax, zmin), (xmin, ymax, zmax), (xmax, ymax, zmax), (xmax, ymax, zmin)]),
    ]


def balls_from_pfc():
    balls = []
    for ball in it.ball.list():
        pos = ball.pos()
        balls.append(((float(pos[0]), float(pos[1]), float(pos[2])), float(ball.radius())))
    return balls


def balls_for_offline_export():
    generated, _random_bins, _wall_bins, _attempts = sp.generate_pack()
    return [((x, y, z), radius) for x, y, z, radius, _bin_name, _phase in generated]


def export_stl(balls):
    if not os.path.isdir(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)

    triangle_count = 0
    with open(EXPORT_PATH, "w") as handle:
        handle.write("solid {}\n".format(EXPORT_BASENAME))
        for center, radius in balls:
            write_sphere(handle, center, radius)
            triangle_count += SPHERE_LON_SEGMENTS * (2 * SPHERE_LAT_SEGMENTS - 2)
        for _name, corners in wall_faces():
            write_triangle(handle, corners[0], corners[1], corners[2])
            write_triangle(handle, corners[0], corners[2], corners[3])
            triangle_count += 2
        handle.write("endsolid {}\n".format(EXPORT_BASENAME))
    return triangle_count


def main():
    balls = balls_from_pfc() if it is not None else balls_for_offline_export()
    if not balls:
        raise RuntimeError("No balls available for STL export")
    triangle_count = export_stl(balls)
    print("")
    print("=== STL export complete ===")
    print("file:       {}".format(EXPORT_PATH))
    print("balls:      {}".format(len(balls)))
    print("walls:      6")
    print("triangles:  {}".format(triangle_count))
    print("===========================")


if __name__ == "__main__":
    main()
