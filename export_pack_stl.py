# Export the current PFC balls to one ASCII STL file, clipped to the specimen box.

from __future__ import print_function

import math
import os

try:
    import itasca as it
except ImportError:
    it = None

import importlib
import cyclic_pack as cp
cp = importlib.reload(cp)


EXPORT_DIR = r"E:\codexfile\pfc cyclic particle\outputs\stl"
EXPORT_BASENAME = "cyclic-particles-1"
EXPORT_PATH = os.path.join(EXPORT_DIR, EXPORT_BASENAME + ".stl")

# Sphere mesh resolution. Increase these for smoother exported particles.
SPHERE_LAT_SEGMENTS = 12
SPHERE_LON_SEGMENTS = 24
CUT_CAP_SEGMENTS = 48

# For checking cyclic cut faces, export only the clipped particle body by
# default. Wall faces can hide the caps because they sit on the same planes.
EXPORT_WALLS = False


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


def point_axis_value(point, axis):
    return point[{"x": 0, "y": 1, "z": 2}[axis]]


def set_axis_value(point, axis, value):
    values = [point[0], point[1], point[2]]
    values[{"x": 0, "y": 1, "z": 2}[axis]] = value
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


def clip_polygon_to_box(points):
    planes = [
        ("x", cp.BOX_X_MIN, True),
        ("x", cp.BOX_X_MAX, False),
        ("y", cp.BOX_Y_MIN, True),
        ("y", cp.BOX_Y_MAX, False),
        ("z", cp.BOX_Z_MIN, True),
        ("z", cp.BOX_Z_MAX, False),
    ]
    clipped = list(points)
    for axis, limit, keep_greater in planes:
        clipped = clip_polygon_to_plane(clipped, axis, limit, keep_greater)
        if not clipped:
            break
    return clipped


def write_clipped_polygon(handle, points):
    if len(points) < 3:
        return 0
    for i in range(1, len(points) - 1):
        write_triangle(handle, points[0], points[i], points[i + 1])
    return len(points) - 2


def write_clipped_triangle(handle, p1, p2, p3):
    return write_clipped_polygon(handle, clip_polygon_to_box([p1, p2, p3]))


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


def write_cut_cap(handle, axis, plane_value, center, radius, outward_negative):
    distance = abs(point_axis_value(center, axis) - plane_value)
    if distance >= radius:
        return 0
    cap_radius = math.sqrt(max(0.0, radius * radius - distance * distance))
    cap_center = set_axis_value(center, axis, plane_value)
    count = 0
    for i in range(CUT_CAP_SEGMENTS):
        a1 = 2.0 * math.pi * i / CUT_CAP_SEGMENTS
        a2 = 2.0 * math.pi * (i + 1) / CUT_CAP_SEGMENTS
        p1 = cut_cap_point(axis, plane_value, center, cap_radius, a1)
        p2 = cut_cap_point(axis, plane_value, center, cap_radius, a2)
        if outward_negative:
            write_triangle(handle, cap_center, p2, p1)
        else:
            write_triangle(handle, cap_center, p1, p2)
        count += 1
    return count


def write_cut_caps(handle, center, radius):
    count = 0
    count += write_cut_cap(handle, "x", cp.BOX_X_MIN, center, radius, True)
    count += write_cut_cap(handle, "x", cp.BOX_X_MAX, center, radius, False)
    count += write_cut_cap(handle, "y", cp.BOX_Y_MIN, center, radius, True)
    count += write_cut_cap(handle, "y", cp.BOX_Y_MAX, center, radius, False)
    count += write_cut_cap(handle, "z", cp.BOX_Z_MIN, center, radius, True)
    count += write_cut_cap(handle, "z", cp.BOX_Z_MAX, center, radius, False)
    return count


def write_sphere(handle, center, radius):
    triangle_count = 0
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
                triangle_count += write_clipped_triangle(handle, p1, p2, p3)
            elif i == SPHERE_LAT_SEGMENTS - 1:
                triangle_count += write_clipped_triangle(handle, p1, p2, p4)
            else:
                triangle_count += write_clipped_triangle(handle, p1, p2, p3)
                triangle_count += write_clipped_triangle(handle, p1, p3, p4)
    triangle_count += write_cut_caps(handle, center, radius)
    return triangle_count


def wall_faces():
    xmin, xmax = cp.BOX_X_MIN, cp.BOX_X_MAX
    ymin, ymax = cp.BOX_Y_MIN, cp.BOX_Y_MAX
    zmin, zmax = cp.BOX_Z_MIN, cp.BOX_Z_MAX
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
    generated, _random_bins, _periodic_bins, _attempts = cp.generate_pack()
    return [((x, y, z), radius) for x, y, z, radius, _bin_name, _phase in generated]


def export_stl(balls):
    if not os.path.isdir(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)

    triangle_count = 0
    with open(EXPORT_PATH, "w") as handle:
        handle.write("solid {}\n".format(EXPORT_BASENAME))
        for center, radius in balls:
            triangle_count += write_sphere(handle, center, radius)
        if EXPORT_WALLS:
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
    print("walls:      {}".format(6 if EXPORT_WALLS else 0))
    print("triangles:  {}".format(triangle_count))
    print("===========================")


if __name__ == "__main__":
    main()
