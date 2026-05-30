from __future__ import print_function

import argparse
import csv
import math
import os
import sys

import numpy as np
import vtk
from scipy.ndimage import gaussian_filter
from vtk.util import numpy_support

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from plugin_common import AXES, AXIS_INDEX, case_paths, load_json, normalized_config, rve_bounds


PATCHES = ["particle_walls", "x_min", "x_max", "y_min", "y_max", "z_min", "z_max"]


def read_particles(config, csv_path):
    periodic_axes = set(config.get("periodic_axes", []))
    shrink = float(config["fluid_surface"].get("radius_shrink", 0.0))
    balls = []
    with open(csv_path, "r") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            skip = False
            for axis in AXES:
                shift_key = "shift_{}".format(axis)
                if axis not in periodic_axes and int(row.get(shift_key, 0)) != 0:
                    skip = True
                    break
            if skip:
                continue
            radius = float(row["radius"]) - shrink
            if radius <= 0.0:
                continue
            balls.append((
                float(row["x"]),
                float(row["y"]),
                float(row["z"]),
                radius,
                int(row.get("source_id", len(balls) + 1)),
            ))
    if not balls:
        raise RuntimeError("No usable particles found in {}".format(csv_path))
    return balls


def pair_gap_stats(balls):
    min_gap = None
    close_pairs = 0
    for i in range(len(balls)):
        xi, yi, zi, ri, si = balls[i]
        for j in range(i + 1, len(balls)):
            xj, yj, zj, rj, sj = balls[j]
            if si == sj:
                continue
            dx = xi - xj
            dy = yi - yj
            dz = zi - zj
            gap = math.sqrt(dx * dx + dy * dy + dz * dz) - ri - rj
            min_gap = gap if min_gap is None else min(min_gap, gap)
            if gap < 0.001:
                close_pairs += 1
    return min_gap, close_pairs


def signed_box_phi(x_grid, y_grid, z_value, rve_min, rve_max):
    center = 0.5 * (rve_min + rve_max)
    half = 0.5 * (rve_max - rve_min)
    qx = np.abs(x_grid - center[0]) - half[0]
    qy = np.abs(y_grid - center[1]) - half[1]
    qz = abs(z_value - center[2]) - half[2]
    outside = np.sqrt(
        np.maximum(qx, 0.0) ** 2 +
        np.maximum(qy, 0.0) ** 2 +
        max(qz, 0.0) ** 2
    )
    inside = np.minimum(np.maximum(np.maximum(qx, qy), qz), 0.0)
    return outside + inside


def build_scalar_field(config, balls):
    bounds = rve_bounds(config)
    rve_min = np.array([bounds[a][0] for a in AXES], dtype=np.float32)
    rve_max = np.array([bounds[a][1] for a in AXES], dtype=np.float32)
    spacing = float(config["fluid_surface"]["grid_spacing"])
    sigma = float(config["fluid_surface"]["smooth_sigma_cells"])
    clip_distance = float(config["fluid_surface"]["smooth_clip_distance"])
    level_offset = float(config["fluid_surface"]["level_offset"])
    periodic_axes = set(config.get("periodic_axes", []))

    margin = spacing
    origin = rve_min - margin
    upper = rve_max + margin
    dims = np.floor((upper - origin) / spacing + 0.5).astype(int) + 1

    xs = origin[0] + np.arange(dims[0], dtype=np.float32) * spacing
    ys = origin[1] + np.arange(dims[1], dtype=np.float32) * spacing
    zs = origin[2] + np.arange(dims[2], dtype=np.float32) * spacing
    x_grid, y_grid = np.meshgrid(xs, ys, indexing="xy")

    solid_field = np.empty((dims[2], dims[1], dims[0]), dtype=np.float32)
    box_field = np.empty((dims[2], dims[1], dims[0]), dtype=np.float32)
    sphere_count_by_z = []

    for k, z_value in enumerate(zs):
        solid_phi = np.full((dims[1], dims[0]), -1.0e6, dtype=np.float32)
        active = 0
        for cx, cy, cz, radius, _source_id in balls:
            dz = z_value - cz
            if abs(dz) > radius + spacing:
                continue
            active += 1
            local = radius - np.sqrt((x_grid - cx) ** 2 + (y_grid - cy) ** 2 + dz * dz)
            solid_phi = np.maximum(solid_phi, local.astype(np.float32))
        box_field[k, :, :] = signed_box_phi(x_grid, y_grid, float(z_value), rve_min, rve_max)
        solid_field[k, :, :] = solid_phi
        sphere_count_by_z.append(active)

    if sigma > 0.0:
        clipped = np.clip(solid_field, -clip_distance, clip_distance)
        mode = []
        for axis in ("z", "y", "x"):
            mode.append("wrap" if axis in periodic_axes else "nearest")
        smooth = gaussian_filter(clipped, sigma=(sigma, sigma, sigma), mode=tuple(mode)).astype(np.float32)
        solid_field = smooth + level_offset

    field = np.maximum(box_field, solid_field)
    return origin, dims, field, max(sphere_count_by_z), spacing


def contour_field(origin, dims, field, spacing):
    image = vtk.vtkImageData()
    image.SetOrigin(float(origin[0]), float(origin[1]), float(origin[2]))
    image.SetSpacing(spacing, spacing, spacing)
    image.SetDimensions(int(dims[0]), int(dims[1]), int(dims[2]))

    scalars = numpy_support.numpy_to_vtk(
        num_array=field.ravel(order="C"),
        deep=True,
        array_type=vtk.VTK_FLOAT,
    )
    scalars.SetName("fluid_levelset")
    image.GetPointData().SetScalars(scalars)

    contour = vtk.vtkFlyingEdges3D()
    contour.SetInputData(image)
    contour.SetValue(0, 0.0)
    contour.ComputeNormalsOff()
    contour.Update()

    cleaner = vtk.vtkCleanPolyData()
    cleaner.SetInputConnection(contour.GetOutputPort())
    cleaner.SetTolerance(1.0e-9)
    cleaner.Update()

    triangles = vtk.vtkTriangleFilter()
    triangles.SetInputConnection(cleaner.GetOutputPort())
    triangles.Update()
    return triangles.GetOutput()


def classify_patch(config, center):
    bounds = rve_bounds(config)
    tol = 1.75 * float(config["fluid_surface"]["grid_spacing"])
    if abs(center[0] - bounds["x"][0]) <= tol:
        return "x_min"
    if abs(center[0] - bounds["x"][1]) <= tol:
        return "x_max"
    if abs(center[1] - bounds["y"][0]) <= tol:
        return "y_min"
    if abs(center[1] - bounds["y"][1]) <= tol:
        return "y_max"
    if abs(center[2] - bounds["z"][0]) <= tol:
        return "z_min"
    if abs(center[2] - bounds["z"][1]) <= tol:
        return "z_max"
    return "particle_walls"


def triangle_normal(p1, p2, p3):
    n = np.cross(p2 - p1, p3 - p1)
    length = np.linalg.norm(n)
    if length <= 0.0:
        return np.array([0.0, 0.0, 0.0])
    return n / length


def write_ascii_stl(config, polydata, output_path):
    parent = os.path.dirname(os.path.abspath(output_path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)

    tris = dict((name, []) for name in PATCHES)
    points = polydata.GetPoints()

    for cell_id in range(polydata.GetNumberOfCells()):
        cell = polydata.GetCell(cell_id)
        if cell.GetNumberOfPoints() != 3:
            continue
        ids = [cell.GetPointId(i) for i in range(3)]
        coords = [np.array(points.GetPoint(pid), dtype=np.float64) for pid in ids]
        center = (coords[0] + coords[1] + coords[2]) / 3.0
        patch = classify_patch(config, center)
        tris[patch].append(coords)

    with open(output_path, "w") as handle:
        for patch in PATCHES:
            handle.write("solid {}\n".format(patch))
            for p1, p2, p3 in tris[patch]:
                n = triangle_normal(p1, p2, p3)
                handle.write("  facet normal {:.8e} {:.8e} {:.8e}\n".format(n[0], n[1], n[2]))
                handle.write("    outer loop\n")
                for p in (p1, p2, p3):
                    handle.write("      vertex {:.8e} {:.8e} {:.8e}\n".format(p[0], p[1], p[2]))
                handle.write("    endloop\n")
                handle.write("  endfacet\n")
            handle.write("endsolid {}\n".format(patch))
    return dict((patch, len(tris[patch])) for patch in PATCHES)


def write_report(path, lines):
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "w") as handle:
        for line in lines:
            handle.write(line.rstrip() + "\n")


def run(config_path, case_dir=None, csv_path=None, output_path=None, report_path=None):
    config = normalized_config(load_json(config_path))
    paths = case_paths(config)
    csv_path = csv_path or paths["particles_csv"]
    output_path = output_path or paths["fluid_stl"]
    report_path = report_path or paths["fluid_report"]

    balls = read_particles(config, csv_path)
    min_gap, close_pairs = pair_gap_stats(balls)
    origin, dims, field, max_active, spacing = build_scalar_field(config, balls)
    polydata = contour_field(origin, dims, field, spacing)
    patch_counts = write_ascii_stl(config, polydata, output_path)

    lines = [
        "fluid STL export complete",
        "output: {}".format(output_path),
        "input_csv: {}".format(csv_path),
        "balls/images: {}".format(len(balls)),
        "periodic_axes: {}".format(",".join(config.get("periodic_axes", []))),
        "radius_shrink: {:.8f} mm".format(config["fluid_surface"]["radius_shrink"]),
        "grid_spacing: {:.8f} mm".format(config["fluid_surface"]["grid_spacing"]),
        "smooth_sigma_cells: {:.4f}".format(config["fluid_surface"]["smooth_sigma_cells"]),
        "smooth_clip_distance: {:.8f} mm".format(config["fluid_surface"]["smooth_clip_distance"]),
        "level_offset: {:.8f} mm".format(config["fluid_surface"]["level_offset"]),
        "grid_dimensions: {} x {} x {}".format(int(dims[0]), int(dims[1]), int(dims[2])),
        "min_raw_pair_gap: {}".format("n/a" if min_gap is None else "{:.8f} mm".format(min_gap)),
        "raw_pairs_below_0p001: {}".format(close_pairs),
        "max_active_balls_per_z: {}".format(max_active),
        "vtk_points: {}".format(polydata.GetNumberOfPoints()),
        "vtk_triangles: {}".format(polydata.GetNumberOfCells()),
    ]
    for patch in PATCHES:
        lines.append("{}: {}".format(patch, patch_counts[patch]))
    write_report(report_path, lines)
    for line in lines:
        print(line)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Export smooth Fluent-ready fluid STL from particle CSV.")
    parser.add_argument("--config", required=True, help="Path to model_config.json or config_used.json")
    parser.add_argument("--case-dir", default=None, help="Case directory. Defaults to output_dir/model_name.")
    parser.add_argument("--csv", default=None, help="Particle CSV path. Defaults to case geometry/particles.csv.")
    parser.add_argument("--output", default=None, help="Fluid STL path. Defaults to case fluid/fluid_fluent.stl.")
    parser.add_argument("--report", default=None, help="Report path. Defaults to case fluid/fluid_surface_report.txt.")
    args = parser.parse_args()
    run(args.config, args.case_dir, args.csv, args.output, args.report)


if __name__ == "__main__":
    main()
