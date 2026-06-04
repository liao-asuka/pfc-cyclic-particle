from __future__ import print_function

import argparse
import csv
import math
import os
import sys

import numpy as np
import vtk
from scipy.ndimage import binary_closing, binary_dilation, binary_opening, distance_transform_edt, gaussian_filter, label
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


def nearest_index(values, target):
    return int(np.argmin(np.abs(values - target)))


def synchronize_periodic_boundary_slices(config, solid_field, coords):
    bounds = rve_bounds(config)
    sigma = float(config["fluid_surface"].get("smooth_sigma_cells", 0.0))
    sync_band = max(2, int(math.ceil(3.0 * sigma)) + 1)
    # Run more than once so x and y periodic bands remain consistent at edges
    # and corners after both directions have been synchronized.
    for _pass in range(2):
        for axis in config.get("periodic_axes", []):
            lower = nearest_index(coords[axis], bounds[axis][0])
            upper = nearest_index(coords[axis], bounds[axis][1])
            for offset in range(-sync_band, sync_band + 1):
                lower_index = lower + offset
                upper_index = upper - offset
                if axis == "x":
                    if lower_index < 0 or upper_index >= solid_field.shape[2]:
                        continue
                    paired = 0.5 * (solid_field[:, :, lower_index] + solid_field[:, :, upper_index])
                    solid_field[:, :, lower_index] = paired
                    solid_field[:, :, upper_index] = paired
                elif axis == "y":
                    if lower_index < 0 or upper_index >= solid_field.shape[1]:
                        continue
                    paired = 0.5 * (solid_field[:, lower_index, :] + solid_field[:, upper_index, :])
                    solid_field[:, lower_index, :] = paired
                    solid_field[:, upper_index, :] = paired
                elif axis == "z":
                    if lower_index < 0 or upper_index >= solid_field.shape[0]:
                        continue
                    paired = 0.5 * (solid_field[lower_index, :, :] + solid_field[upper_index, :, :])
                    solid_field[lower_index, :, :] = paired
                    solid_field[upper_index, :, :] = paired
    return sync_band


def pad_for_periodic_axes(config, mask, pad_width):
    pad_spec = []
    mode_by_dim = []
    periodic_axes = set(config.get("periodic_axes", []))
    for axis in ("z", "y", "x"):
        pad_spec.append((pad_width, pad_width))
        mode_by_dim.append("wrap" if axis in periodic_axes else "constant")

    result = mask
    # np.pad only accepts one mode for all axes, so pad one axis at a time.
    for dim, mode in enumerate(mode_by_dim):
        spec = [(0, 0), (0, 0), (0, 0)]
        spec[dim] = pad_spec[dim]
        if mode == "wrap":
            result = np.pad(result, spec, mode="wrap")
        else:
            result = np.pad(result, spec, mode="constant", constant_values=False)
    return result


def crop_padding(mask, pad_width):
    if pad_width <= 0:
        return mask
    return mask[pad_width:-pad_width, pad_width:-pad_width, pad_width:-pad_width]


def binary_iterations(mask, operation, iterations, config=None):
    result = mask
    structure = np.ones((3, 3, 3), dtype=bool)
    for _index in range(max(0, int(iterations))):
        if config is not None:
            working = pad_for_periodic_axes(config, result, 1)
        else:
            working = result
        if operation == "open":
            working = binary_opening(working, structure=structure, border_value=0)
        elif operation == "close":
            working = binary_closing(working, structure=structure, border_value=0)
        if config is not None:
            result = crop_padding(working, 1)
        else:
            result = working
    return result


def synchronize_periodic_mask_slices(config, mask, coords, band_cells, rule="and"):
    bounds = rve_bounds(config)
    changed = 0
    band_cells = max(0, int(band_cells))
    for axis in config.get("periodic_axes", []):
        lower = nearest_index(coords[axis], bounds[axis][0])
        upper = nearest_index(coords[axis], bounds[axis][1])
        for offset in range(-band_cells, band_cells + 1):
            lower_index = lower + offset
            upper_index = upper - offset
            if axis == "x":
                if lower_index < 0 or upper_index >= mask.shape[2]:
                    continue
                left = mask[:, :, lower_index]
                right = mask[:, :, upper_index]
                paired = np.logical_or(left, right) if rule == "or" else np.logical_and(left, right)
                changed += int(np.count_nonzero(left != paired) + np.count_nonzero(right != paired))
                mask[:, :, lower_index] = paired
                mask[:, :, upper_index] = paired
            elif axis == "y":
                if lower_index < 0 or upper_index >= mask.shape[1]:
                    continue
                left = mask[:, lower_index, :]
                right = mask[:, upper_index, :]
                paired = np.logical_or(left, right) if rule == "or" else np.logical_and(left, right)
                changed += int(np.count_nonzero(left != paired) + np.count_nonzero(right != paired))
                mask[:, lower_index, :] = paired
                mask[:, upper_index, :] = paired
            elif axis == "z":
                if lower_index < 0 or upper_index >= mask.shape[0]:
                    continue
                left = mask[lower_index, :, :]
                right = mask[upper_index, :, :]
                paired = np.logical_or(left, right) if rule == "or" else np.logical_and(left, right)
                changed += int(np.count_nonzero(left != paired) + np.count_nonzero(right != paired))
                mask[lower_index, :, :] = paired
                mask[upper_index, :, :] = paired
    return changed


def synchronize_periodic_field_slices(config, field, coords, band_cells):
    bounds = rve_bounds(config)
    changed = 0
    max_delta = 0.0
    band_cells = max(0, int(band_cells))
    for axis in config.get("periodic_axes", []):
        lower = nearest_index(coords[axis], bounds[axis][0])
        upper = nearest_index(coords[axis], bounds[axis][1])
        for offset in range(-band_cells, band_cells + 1):
            lower_index = lower + offset
            upper_index = upper - offset
            if axis == "x":
                if lower_index < 0 or upper_index >= field.shape[2]:
                    continue
                left = field[:, :, lower_index]
                right = field[:, :, upper_index]
                paired = 0.5 * (left + right)
                max_delta = max(max_delta, float(np.max(np.abs(left - paired))), float(np.max(np.abs(right - paired))))
                changed += int(np.count_nonzero(left != paired) + np.count_nonzero(right != paired))
                field[:, :, lower_index] = paired
                field[:, :, upper_index] = paired
            elif axis == "y":
                if lower_index < 0 or upper_index >= field.shape[1]:
                    continue
                left = field[:, lower_index, :]
                right = field[:, upper_index, :]
                paired = 0.5 * (left + right)
                max_delta = max(max_delta, float(np.max(np.abs(left - paired))), float(np.max(np.abs(right - paired))))
                changed += int(np.count_nonzero(left != paired) + np.count_nonzero(right != paired))
                field[:, lower_index, :] = paired
                field[:, upper_index, :] = paired
            elif axis == "z":
                if lower_index < 0 or upper_index >= field.shape[0]:
                    continue
                left = field[lower_index, :, :]
                right = field[upper_index, :, :]
                paired = 0.5 * (left + right)
                max_delta = max(max_delta, float(np.max(np.abs(left - paired))), float(np.max(np.abs(right - paired))))
                changed += int(np.count_nonzero(left != paired) + np.count_nonzero(right != paired))
                field[lower_index, :, :] = paired
                field[upper_index, :, :] = paired
    return changed, max_delta


class UnionFind(object):
    def __init__(self, labels):
        self.parent = dict((int(item), int(item)) for item in labels if int(item) > 0)

    def find(self, value):
        value = int(value)
        parent = self.parent.get(value, value)
        if parent != value:
            parent = self.find(parent)
            self.parent[value] = parent
        return parent

    def union(self, left, right):
        left = int(left)
        right = int(right)
        if left <= 0 or right <= 0:
            return
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left != root_right:
            self.parent[root_right] = root_left


def merge_periodic_labels(config, labels, coords):
    bounds = rve_bounds(config)
    unique_labels = np.unique(labels)
    uf = UnionFind(unique_labels)
    for axis in config.get("periodic_axes", []):
        lower = nearest_index(coords[axis], bounds[axis][0])
        upper = nearest_index(coords[axis], bounds[axis][1])
        if axis == "x":
            lower_slice = labels[:, :, lower]
            upper_slice = labels[:, :, upper]
        elif axis == "y":
            lower_slice = labels[:, lower, :]
            upper_slice = labels[:, upper, :]
        else:
            lower_slice = labels[lower, :, :]
            upper_slice = labels[upper, :, :]
        pairs = np.stack((lower_slice.ravel(), upper_slice.ravel()), axis=1)
        for left, right in pairs:
            uf.union(left, right)
    return uf


def filter_connected_fluid_components(config, fluid_mask, coords, keep_largest=None, min_voxels=None):
    fluid = config.get("fluid_surface", {})
    if keep_largest is None:
        keep_largest = bool(fluid.get("robust_keep_largest_component", True))
    if min_voxels is None:
        min_voxels = int(float(fluid.get("robust_min_component_voxels", 800)))

    structure = np.ones((3, 3, 3), dtype=bool)
    labels, count = label(fluid_mask, structure=structure)
    if count <= 0:
        return fluid_mask, {
            "component_count_before": 0,
            "component_count_after": 0,
            "removed_voxels": 0,
            "kept_voxels": int(np.count_nonzero(fluid_mask)),
        }

    uf = merge_periodic_labels(config, labels, coords)
    sizes = {}
    flat = labels.ravel()
    for value in flat:
        if value <= 0:
            continue
        root = uf.find(value)
        sizes[root] = sizes.get(root, 0) + 1

    if keep_largest:
        keep_roots = set()
        if sizes:
            keep_roots.add(max(sizes, key=sizes.get))
    else:
        keep_roots = set(root for root, size in sizes.items() if size >= min_voxels)
    if not keep_roots and sizes:
        keep_roots.add(max(sizes, key=sizes.get))

    keep_label = np.zeros(count + 1, dtype=bool)
    for value in range(1, count + 1):
        if uf.find(value) in keep_roots:
            keep_label[value] = True
    filtered = keep_label[labels]
    before = int(np.count_nonzero(fluid_mask))
    after = int(np.count_nonzero(filtered))
    return filtered, {
        "component_count_before": int(count),
        "component_count_after": int(len(keep_roots)),
        "removed_voxels": before - after,
        "kept_voxels": after,
    }


def rebuild_signed_distance_from_fluid_mask(config, fluid_mask, spacing):
    outside_distance = distance_transform_edt(~fluid_mask) * spacing
    inside_distance = distance_transform_edt(fluid_mask) * spacing
    field = outside_distance - inside_distance
    sigma = float(config.get("fluid_surface", {}).get("robust_sdf_smooth_sigma_cells", 0.65))
    if sigma > 0.0:
        periodic_axes = set(config.get("periodic_axes", []))
        mode = []
        for axis in ("z", "y", "x"):
            mode.append("wrap" if axis in periodic_axes else "nearest")
        field = gaussian_filter(field.astype(np.float32), sigma=(sigma, sigma, sigma), mode=tuple(mode))
    return field.astype(np.float32)


def robust_v2_field(config, field, spacing, coords):
    fluid = config.get("fluid_surface", {})
    open_cells = int(float(fluid.get("robust_open_cells", 1)))
    close_cells = int(float(fluid.get("robust_close_cells", 1)))
    fluid_mask = field < 0.0
    before_voxels = int(np.count_nonzero(fluid_mask))
    if open_cells > 0:
        fluid_mask = binary_iterations(fluid_mask, "open", open_cells, config)
    if close_cells > 0:
        fluid_mask = binary_iterations(fluid_mask, "close", close_cells, config)
    after_morphology_voxels = int(np.count_nonzero(fluid_mask))
    fluid_mask, component_stats = filter_connected_fluid_components(config, fluid_mask, coords)
    robust_field = rebuild_signed_distance_from_fluid_mask(config, fluid_mask, spacing)
    stats = {
        "method": "robust_v2",
        "open_cells": open_cells,
        "close_cells": close_cells,
        "fluid_voxels_before": before_voxels,
        "fluid_voxels_after_morphology": after_morphology_voxels,
    }
    stats.update(component_stats)
    return robust_field, stats


def cp4a_cleanup_field(config, field, spacing, coords):
    fluid = config.get("fluid_surface", {})
    enabled = bool(fluid.get("cp4a_cleanup_enabled", True))
    stats = {
        "method": "cp4a_smooth",
        "cleanup_enabled": enabled,
        "cleanup_open_cells": int(float(fluid.get("cp4a_cleanup_open_cells", 1))),
        "cleanup_close_cells": int(float(fluid.get("cp4a_cleanup_close_cells", 0))),
        "cleanup_blend_cells": int(float(fluid.get("cp4a_cleanup_blend_cells", 2))),
        "cleanup_periodic_band_cells": int(float(fluid.get("cp4a_cleanup_periodic_band_cells", 1))),
        "cleanup_changed_voxels": 0,
        "cleanup_band_voxels": 0,
        "cleanup_cut_changed_voxels": 0,
        "cleanup_cut_band_voxels": 0,
        "cleanup_component_changed_voxels": 0,
        "cleanup_component_band_voxels": 0,
        "cleanup_cut_periodic_sync_voxels": 0,
        "cleanup_component_periodic_sync_voxels": 0,
        "component_count_before": 0,
        "component_count_after": 0,
        "removed_voxels": 0,
        "kept_voxels": int(np.count_nonzero(field < 0.0)),
    }
    if not enabled:
        return field, stats

    original_fluid = field < 0.0
    cut_fluid = original_fluid.copy()
    open_cells = stats["cleanup_open_cells"]
    close_cells = stats["cleanup_close_cells"]
    periodic_band_cells = stats["cleanup_periodic_band_cells"]
    if open_cells > 0:
        cut_fluid = binary_iterations(cut_fluid, "open", open_cells, config)
    if close_cells > 0:
        cut_fluid = binary_iterations(cut_fluid, "close", close_cells, config)
    stats["cleanup_cut_periodic_sync_voxels"] = synchronize_periodic_mask_slices(
        config,
        cut_fluid,
        coords,
        periodic_band_cells,
        rule="and",
    )

    result = field.copy()
    blend_cells = max(0, stats["cleanup_blend_cells"])
    cut_changed = original_fluid != cut_fluid
    cut_changed_voxels = int(np.count_nonzero(cut_changed))
    stats["cleanup_cut_changed_voxels"] = cut_changed_voxels
    if cut_changed_voxels > 0:
        if blend_cells > 0:
            cut_band = binary_dilation(cut_changed, structure=np.ones((3, 3, 3), dtype=bool), iterations=blend_cells)
        else:
            cut_band = cut_changed
        cut_rebuilt = rebuild_signed_distance_from_fluid_mask(config, cut_fluid, spacing)
        result[cut_band] = cut_rebuilt[cut_band]
        stats["cleanup_cut_band_voxels"] = int(np.count_nonzero(cut_band))

    final_fluid, component_stats = filter_connected_fluid_components(
        config,
        cut_fluid,
        coords,
        keep_largest=bool(fluid.get("cp4a_cleanup_keep_largest_component", True)),
        min_voxels=int(float(fluid.get("cp4a_cleanup_min_component_voxels", 800))),
    )
    stats.update(component_stats)
    stats["cleanup_component_periodic_sync_voxels"] = synchronize_periodic_mask_slices(
        config,
        final_fluid,
        coords,
        periodic_band_cells,
        rule="and",
    )
    component_changed = cut_fluid != final_fluid
    component_changed_voxels = int(np.count_nonzero(component_changed))
    stats["cleanup_component_changed_voxels"] = component_changed_voxels
    if component_changed_voxels > 0:
        if blend_cells > 0:
            component_band = binary_dilation(component_changed, structure=np.ones((3, 3, 3), dtype=bool), iterations=blend_cells)
        else:
            component_band = component_changed
        component_rebuilt = rebuild_signed_distance_from_fluid_mask(config, final_fluid, spacing)
        result[component_band] = component_rebuilt[component_band]
        stats["cleanup_component_band_voxels"] = int(np.count_nonzero(component_band))

    changed = original_fluid != final_fluid
    changed_voxels = int(np.count_nonzero(changed))
    stats["cleanup_changed_voxels"] = changed_voxels
    if changed_voxels <= 0:
        return field, stats
    stats["cleanup_band_voxels"] = int(np.count_nonzero((result != field)))
    return result.astype(np.float32), stats


def build_scalar_field(config, balls):
    bounds = rve_bounds(config)
    rve_min = np.array([bounds[a][0] for a in AXES], dtype=np.float32)
    rve_max = np.array([bounds[a][1] for a in AXES], dtype=np.float32)
    spacing = float(config["fluid_surface"]["grid_spacing"])
    sigma = float(config["fluid_surface"]["smooth_sigma_cells"])
    clip_distance = float(config["fluid_surface"]["smooth_clip_distance"])
    level_offset = float(config["fluid_surface"]["level_offset"])
    method = str(config.get("fluid_surface", {}).get("method", "cp4a_smooth")).lower()
    anti_spike_sigma = float(config["fluid_surface"].get("anti_spike_sigma_cells", 0.8))
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

    sync_band = 0
    if method != "cp4a_smooth":
        sync_band = synchronize_periodic_boundary_slices(config, solid_field, {"x": xs, "y": ys, "z": zs})
    if method != "cp4a_smooth" and anti_spike_sigma > 0.0:
        clipped = np.clip(solid_field, -clip_distance, clip_distance)
        mode = []
        for axis in ("z", "y", "x"):
            mode.append("wrap" if axis in periodic_axes else "nearest")
        solid_field = gaussian_filter(
            clipped,
            sigma=(anti_spike_sigma, anti_spike_sigma, anti_spike_sigma),
            mode=tuple(mode),
        ).astype(np.float32)
        sync_band = max(sync_band, synchronize_periodic_boundary_slices(config, solid_field, {"x": xs, "y": ys, "z": zs}))

    field = np.maximum(box_field, solid_field)
    robust_stats = {"method": method}
    coords = {"x": xs, "y": ys, "z": zs}
    if method == "cp4a_smooth":
        field, robust_stats = cp4a_cleanup_field(config, field, spacing, coords)
        field = np.maximum(box_field, field)
        boundary_band = int(float(config.get("fluid_surface", {}).get("cp4a_cleanup_periodic_band_cells", 1)))
        changed, max_delta = synchronize_periodic_field_slices(config, field, coords, boundary_band)
        robust_stats["cleanup_field_periodic_sync_cells"] = boundary_band
        robust_stats["cleanup_field_periodic_sync_values"] = changed
        robust_stats["cleanup_field_periodic_sync_max_delta"] = max_delta
        sync_band = max(sync_band, boundary_band)
        field = np.maximum(box_field, field)
    elif method == "robust_v2":
        field, robust_stats = robust_v2_field(config, field, spacing, coords)
        sync_band = max(sync_band, synchronize_periodic_boundary_slices(config, field, coords))
        field = np.maximum(box_field, field)
    return origin, dims, field, max(sphere_count_by_z), spacing, sync_band, robust_stats


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


def polydata_triangles(polydata):
    points = polydata.GetPoints()
    triangles = []
    for cell_id in range(polydata.GetNumberOfCells()):
        cell = polydata.GetCell(cell_id)
        if cell.GetNumberOfPoints() != 3:
            continue
        ids = [cell.GetPointId(i) for i in range(3)]
        coords = [np.array(points.GetPoint(pid), dtype=np.float64) for pid in ids]
        triangles.append((ids, coords, triangle_normal(coords[0], coords[1], coords[2])))
    return triangles


def normal_angle_stats(polydata, threshold_degrees):
    triangles = polydata_triangles(polydata)
    edges = {}
    for tri_id, (ids, _coords, _normal) in enumerate(triangles):
        for edge in ((ids[0], ids[1]), (ids[1], ids[2]), (ids[2], ids[0])):
            key = tuple(sorted(edge))
            edges.setdefault(key, []).append(tri_id)

    max_angle = 0.0
    over_threshold = 0
    paired_edges = 0
    threshold = float(threshold_degrees)
    for tri_ids in edges.values():
        if len(tri_ids) != 2:
            continue
        paired_edges += 1
        n1 = triangles[tri_ids[0]][2]
        n2 = triangles[tri_ids[1]][2]
        length1 = np.linalg.norm(n1)
        length2 = np.linalg.norm(n2)
        if length1 <= 0.0 or length2 <= 0.0:
            continue
        dot = abs(max(-1.0, min(1.0, float(np.dot(n1, n2)))))
        angle = math.degrees(math.acos(dot))
        max_angle = max(max_angle, angle)
        if angle > threshold:
            over_threshold += 1
    return {
        "paired_edges": paired_edges,
        "max_angle": max_angle,
        "over_threshold": over_threshold,
        "threshold": threshold,
    }


def edge_integrity_stats(polydata):
    edges = {}
    for ids, _coords, _normal in polydata_triangles(polydata):
        for edge in ((ids[0], ids[1]), (ids[1], ids[2]), (ids[2], ids[0])):
            key = tuple(sorted(edge))
            edges[key] = edges.get(key, 0) + 1
    open_edges = 0
    nonmanifold_edges = 0
    for count in edges.values():
        if count == 1:
            open_edges += 1
        if count != 2:
            nonmanifold_edges += 1
    return {
        "edges": len(edges),
        "open_edges": open_edges,
        "nonmanifold_edges": nonmanifold_edges,
    }


def boundary_plane_constraints(config, polydata):
    bounds = rve_bounds(config)
    spacing = float(config["fluid_surface"]["grid_spacing"])
    tol = max(1.0e-6, 1.0e-3 * spacing)
    points = polydata.GetPoints()
    constraints = []
    for point_id in range(points.GetNumberOfPoints()):
        point = points.GetPoint(point_id)
        point_constraints = []
        for axis in AXES:
            axis_id = AXIS_INDEX[axis]
            if abs(point[axis_id] - bounds[axis][0]) <= tol:
                point_constraints.append((axis_id, bounds[axis][0]))
            elif abs(point[axis_id] - bounds[axis][1]) <= tol:
                point_constraints.append((axis_id, bounds[axis][1]))
        constraints.append(point_constraints)
    return constraints


def apply_boundary_plane_constraints(polydata, constraints):
    points = polydata.GetPoints()
    for point_id, point_constraints in enumerate(constraints):
        if not point_constraints:
            continue
        point = list(points.GetPoint(point_id))
        for axis_id, value in point_constraints:
            point[axis_id] = value
        points.SetPoint(point_id, point)
    points.Modified()
    polydata.Modified()


def snap_polydata_to_box_boundaries(config, polydata, tolerance):
    bounds = rve_bounds(config)
    points = polydata.GetPoints()
    snapped = 0
    for point_id in range(points.GetNumberOfPoints()):
        point = list(points.GetPoint(point_id))
        changed = False
        for axis in AXES:
            axis_id = AXIS_INDEX[axis]
            for value in bounds[axis]:
                if abs(point[axis_id] - value) <= tolerance:
                    if point[axis_id] != value:
                        point[axis_id] = value
                        changed = True
                    break
        if changed:
            points.SetPoint(point_id, point)
            snapped += 1
    if snapped:
        points.Modified()
        polydata.Modified()
    return snapped


def smooth_polydata_if_needed(config, polydata):
    fluid = config.get("fluid_surface", {})
    method = str(fluid.get("method", "cp4a_smooth")).lower()
    threshold = float(fluid.get("max_normal_angle_degrees", 80.0))
    iterations = int(float(fluid.get("mesh_smooth_iterations", 18)))
    pass_band = float(fluid.get("mesh_smooth_pass_band", 0.08))
    stats_before = normal_angle_stats(polydata, threshold)
    integrity_before = edge_integrity_stats(polydata)

    if method == "cp4a_smooth" or iterations <= 0 or stats_before["over_threshold"] <= 0:
        return polydata, stats_before, stats_before, integrity_before, integrity_before, False, "not_needed"

    constraints = boundary_plane_constraints(config, polydata)
    smoother = vtk.vtkWindowedSincPolyDataFilter()
    smoother.SetInputData(polydata)
    smoother.SetNumberOfIterations(iterations)
    smoother.SetPassBand(pass_band)
    smoother.BoundarySmoothingOff()
    smoother.FeatureEdgeSmoothingOn()
    smoother.NonManifoldSmoothingOn()
    smoother.NormalizeCoordinatesOn()
    smoother.Update()

    smoothed = vtk.vtkPolyData()
    smoothed.DeepCopy(smoother.GetOutput())
    if smoothed.GetNumberOfPoints() == len(constraints):
        apply_boundary_plane_constraints(smoothed, constraints)

    triangles = vtk.vtkTriangleFilter()
    triangles.SetInputData(smoothed)
    triangles.Update()
    triangulated = triangles.GetOutput()
    stats_after = normal_angle_stats(triangulated, threshold)
    integrity_after = edge_integrity_stats(triangulated)
    acceptable = (
        integrity_after["open_edges"] == 0 and
        integrity_after["nonmanifold_edges"] == 0 and
        stats_after["over_threshold"] <= stats_before["over_threshold"]
    )
    if not acceptable:
        return polydata, stats_before, stats_after, integrity_before, integrity_after, False, "rejected"
    return triangulated, stats_before, stats_after, integrity_before, integrity_after, True, "accepted"


def periodic_field_pair_stats(config, origin, dims, field, spacing, sync_band):
    bounds = rve_bounds(config)
    coords = {
        axis: origin[index] + np.arange(dims[index], dtype=np.float32) * spacing
        for index, axis in enumerate(AXES)
    }
    stats = {}
    for axis in config.get("periodic_axes", []):
        lower = nearest_index(coords[axis], bounds[axis][0])
        upper = nearest_index(coords[axis], bounds[axis][1])
        max_diff = 0.0
        for offset in range(-sync_band, sync_band + 1):
            lower_index = lower + offset
            upper_index = upper - offset
            if axis == "x":
                if lower_index < 0 or upper_index >= field.shape[2]:
                    continue
                diff = float(np.max(np.abs(field[:, :, lower_index] - field[:, :, upper_index])))
            elif axis == "y":
                if lower_index < 0 or upper_index >= field.shape[1]:
                    continue
                diff = float(np.max(np.abs(field[:, lower_index, :] - field[:, upper_index, :])))
            else:
                if lower_index < 0 or upper_index >= field.shape[0]:
                    continue
                diff = float(np.max(np.abs(field[lower_index, :, :] - field[upper_index, :, :])))
            max_diff = max(max_diff, diff)
        stats[axis] = max_diff
    return stats


def classify_patch(config, coords):
    bounds = rve_bounds(config)
    tol = max(1.0e-6, 1.0e-3 * float(config["fluid_surface"]["grid_spacing"]))

    def all_on_plane(axis, value):
        axis_id = AXIS_INDEX[axis]
        return all(abs(point[axis_id] - value) <= tol for point in coords)

    if all_on_plane("x", bounds["x"][0]):
        return "x_min"
    if all_on_plane("x", bounds["x"][1]):
        return "x_max"
    if all_on_plane("y", bounds["y"][0]):
        return "y_min"
    if all_on_plane("y", bounds["y"][1]):
        return "y_max"
    if all_on_plane("z", bounds["z"][0]):
        return "z_min"
    if all_on_plane("z", bounds["z"][1]):
        return "z_max"
    return "particle_walls"


def triangle_normal(p1, p2, p3):
    n = np.cross(p2 - p1, p3 - p1)
    length = np.linalg.norm(n)
    if length <= 0.0:
        return np.array([0.0, 0.0, 0.0])
    return n / length


def triangle_area(p1, p2, p3):
    return 0.5 * float(np.linalg.norm(np.cross(p2 - p1, p3 - p1)))


def patch_projection_stats(config, tris):
    stats = {}
    for patch, triangles in tris.items():
        if not triangles:
            stats[patch] = {"area": 0.0, "bounds": None}
            continue
        axis = patch[0] if patch in PATCHES and patch != "particle_walls" else None
        if axis not in AXES:
            continue
        other_axes = [AXIS_INDEX[item] for item in AXES if item != axis]
        projected = []
        area = 0.0
        for p1, p2, p3 in triangles:
            area += triangle_area(p1, p2, p3)
            projected.extend([
                (p1[other_axes[0]], p1[other_axes[1]]),
                (p2[other_axes[0]], p2[other_axes[1]]),
                (p3[other_axes[0]], p3[other_axes[1]]),
            ])
        values = np.array(projected, dtype=np.float64)
        stats[patch] = {
            "area": area,
            "bounds": (
                float(values[:, 0].min()),
                float(values[:, 0].max()),
                float(values[:, 1].min()),
                float(values[:, 1].max()),
            ),
        }
    return stats


def periodic_patch_pair_diagnostics(config, tris):
    stats = patch_projection_stats(config, tris)
    diagnostics = {}
    for axis in config.get("periodic_axes", []):
        left = "{}_min".format(axis)
        right = "{}_max".format(axis)
        left_stats = stats.get(left, {"area": 0.0, "bounds": None})
        right_stats = stats.get(right, {"area": 0.0, "bounds": None})
        area_diff = abs(left_stats["area"] - right_stats["area"])
        bounds_diff = None
        if left_stats["bounds"] is not None and right_stats["bounds"] is not None:
            bounds_diff = max(abs(a - b) for a, b in zip(left_stats["bounds"], right_stats["bounds"]))
        diagnostics[axis] = {
            "area_min": left_stats["area"],
            "area_max": right_stats["area"],
            "area_difference": area_diff,
            "projected_bounds_max_difference": bounds_diff,
        }
    return diagnostics


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
        patch = classify_patch(config, coords)
        tris[patch].append(coords)

    periodic_diagnostics = periodic_patch_pair_diagnostics(config, tris)

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
    counts = dict((patch, len(tris[patch])) for patch in PATCHES)
    counts["_periodic_patch_diagnostics"] = periodic_diagnostics
    return counts


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
    origin, dims, field, max_active, spacing, sync_band, robust_stats = build_scalar_field(config, balls)
    periodic_field_stats = periodic_field_pair_stats(config, origin, dims, field, spacing, sync_band)
    polydata = contour_field(origin, dims, field, spacing)
    (
        polydata,
        angle_stats_before,
        angle_stats_after,
        edge_stats_before,
        edge_stats_after,
        mesh_smoothed,
        mesh_smooth_status,
    ) = smooth_polydata_if_needed(config, polydata)
    snap_tolerance = 0.55 * spacing if robust_stats.get("method") == "robust_v2" else max(1.0e-6, 1.0e-3 * spacing)
    snapped_boundary_points = snap_polydata_to_box_boundaries(config, polydata, snap_tolerance)
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
        "anti_spike_sigma_cells: {:.4f}".format(config["fluid_surface"].get("anti_spike_sigma_cells", 0.8)),
        "fluid_surface_method: {}".format(robust_stats.get("method", "legacy")),
        "periodic_sync_band_cells: {}".format(sync_band),
        "grid_dimensions: {} x {} x {}".format(int(dims[0]), int(dims[1]), int(dims[2])),
        "min_raw_pair_gap: {}".format("n/a" if min_gap is None else "{:.8f} mm".format(min_gap)),
        "raw_pairs_below_0p001: {}".format(close_pairs),
        "max_active_balls_per_z: {}".format(max_active),
        "mesh_max_normal_angle_limit_degrees: {:.4f}".format(angle_stats_before["threshold"]),
        "mesh_smoothing_applied: {}".format(str(mesh_smoothed).lower()),
        "mesh_smoothing_status: {}".format(mesh_smooth_status),
        "mesh_normal_angle_max_before: {:.4f}".format(angle_stats_before["max_angle"]),
        "mesh_normal_angle_edges_over_limit_before: {}".format(angle_stats_before["over_threshold"]),
        "mesh_normal_angle_max_after: {:.4f}".format(angle_stats_after["max_angle"]),
        "mesh_normal_angle_edges_over_limit_after: {}".format(angle_stats_after["over_threshold"]),
        "mesh_open_edges_before: {}".format(edge_stats_before["open_edges"]),
        "mesh_nonmanifold_edges_before: {}".format(edge_stats_before["nonmanifold_edges"]),
        "mesh_open_edges_after_attempt: {}".format(edge_stats_after["open_edges"]),
        "mesh_nonmanifold_edges_after_attempt: {}".format(edge_stats_after["nonmanifold_edges"]),
        "boundary_snap_tolerance: {:.8e} mm".format(snap_tolerance),
        "boundary_snapped_points: {}".format(snapped_boundary_points),
        "vtk_points: {}".format(polydata.GetNumberOfPoints()),
        "vtk_triangles: {}".format(polydata.GetNumberOfCells()),
    ]
    for patch in PATCHES:
        lines.append("{}: {}".format(patch, patch_counts[patch]))
    if robust_stats.get("method") == "robust_v2":
        lines.append("robust_v2_open_cells: {}".format(robust_stats["open_cells"]))
        lines.append("robust_v2_close_cells: {}".format(robust_stats["close_cells"]))
        lines.append("robust_v2_fluid_voxels_before: {}".format(robust_stats["fluid_voxels_before"]))
        lines.append("robust_v2_fluid_voxels_after_morphology: {}".format(robust_stats["fluid_voxels_after_morphology"]))
        lines.append("robust_v2_component_count_before: {}".format(robust_stats["component_count_before"]))
        lines.append("robust_v2_component_count_after: {}".format(robust_stats["component_count_after"]))
        lines.append("robust_v2_removed_voxels: {}".format(robust_stats["removed_voxels"]))
        lines.append("robust_v2_kept_voxels: {}".format(robust_stats["kept_voxels"]))
    if robust_stats.get("method") == "cp4a_smooth":
        lines.append("cp4a_cleanup_enabled: {}".format(str(robust_stats["cleanup_enabled"]).lower()))
        lines.append("cp4a_cleanup_open_cells: {}".format(robust_stats["cleanup_open_cells"]))
        lines.append("cp4a_cleanup_close_cells: {}".format(robust_stats["cleanup_close_cells"]))
        lines.append("cp4a_cleanup_blend_cells: {}".format(robust_stats["cleanup_blend_cells"]))
        lines.append("cp4a_cleanup_periodic_band_cells: {}".format(robust_stats.get("cleanup_periodic_band_cells", 0)))
        lines.append("cp4a_cleanup_cut_periodic_sync_voxels: {}".format(robust_stats.get("cleanup_cut_periodic_sync_voxels", 0)))
        lines.append("cp4a_cleanup_component_periodic_sync_voxels: {}".format(robust_stats.get("cleanup_component_periodic_sync_voxels", 0)))
        lines.append("cp4a_cleanup_field_periodic_sync_cells: {}".format(robust_stats.get("cleanup_field_periodic_sync_cells", 0)))
        lines.append("cp4a_cleanup_field_periodic_sync_values: {}".format(robust_stats.get("cleanup_field_periodic_sync_values", 0)))
        lines.append("cp4a_cleanup_field_periodic_sync_max_delta: {:.8e}".format(robust_stats.get("cleanup_field_periodic_sync_max_delta", 0.0)))
        lines.append("cp4a_cleanup_component_count_before: {}".format(robust_stats["component_count_before"]))
        lines.append("cp4a_cleanup_component_count_after: {}".format(robust_stats["component_count_after"]))
        lines.append("cp4a_cleanup_removed_voxels: {}".format(robust_stats["removed_voxels"]))
        lines.append("cp4a_cleanup_kept_voxels: {}".format(robust_stats["kept_voxels"]))
        lines.append("cp4a_cleanup_cut_changed_voxels: {}".format(robust_stats["cleanup_cut_changed_voxels"]))
        lines.append("cp4a_cleanup_cut_band_voxels: {}".format(robust_stats["cleanup_cut_band_voxels"]))
        lines.append("cp4a_cleanup_component_changed_voxels: {}".format(robust_stats["cleanup_component_changed_voxels"]))
        lines.append("cp4a_cleanup_component_band_voxels: {}".format(robust_stats["cleanup_component_band_voxels"]))
        lines.append("cp4a_cleanup_changed_voxels: {}".format(robust_stats["cleanup_changed_voxels"]))
        lines.append("cp4a_cleanup_band_voxels: {}".format(robust_stats["cleanup_band_voxels"]))
    for axis, stats in sorted(patch_counts.get("_periodic_patch_diagnostics", {}).items()):
        lines.append("periodic_patch_{}_area_min: {:.8e}".format(axis, stats["area_min"]))
        lines.append("periodic_patch_{}_area_max: {:.8e}".format(axis, stats["area_max"]))
        lines.append("periodic_patch_{}_area_difference: {:.8e}".format(axis, stats["area_difference"]))
        bounds_diff = stats["projected_bounds_max_difference"]
        lines.append(
            "periodic_patch_{}_projected_bounds_max_difference: {}".format(
                axis,
                "n/a" if bounds_diff is None else "{:.8e}".format(bounds_diff),
            )
        )
    for axis in sorted(periodic_field_stats):
        lines.append(
            "periodic_field_{}_max_synced_band_difference: {:.8e}".format(
                axis, periodic_field_stats[axis]
            )
        )
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
