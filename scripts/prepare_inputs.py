#!/usr/bin/env python3
"""Prepare raster hydraulic inputs for the Local-Inertial solver.

Expected input NPZ files
------------------------
dem_1m.npz:
    z : (N,N) float DEM [m]
    x : (N,) local x coordinates [m], increasing east
    y : (N,) local y coordinates [m], increasing north

buildings.npz:
    buildings : object array of Nx2 polygon vertex arrays in local x/y [m]

basemap_vectors.npz:
    roads : object array of Nx2 road line arrays in local x/y [m]

Outputs are raw row-major binary files consumed by solver.cpp.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from rasterio.features import rasterize
from rasterio.transform import from_origin
from scipy.ndimage import label
from shapely.geometry import LineString, Polygon, mapping


def polygons_to_mask(polygons, shape, transform):
    shapes = []
    for vertices in polygons:
        a = np.asarray(vertices, dtype=float)
        if len(a) < 3:
            continue
        p = Polygon(a)
        if p.is_valid and not p.is_empty:
            shapes.append((mapping(p), 1))
    # rasterio row 0 is north; solver array row 0 is south -> flip vertically.
    top_down = rasterize(
        shapes,
        out_shape=shape,
        transform=transform,
        fill=0,
        dtype=np.uint8,
        all_touched=True,
    )
    return np.flipud(top_down).astype(bool)


def roads_to_mask(lines, shape, transform, half_width_m):
    shapes = []
    for vertices in lines:
        a = np.asarray(vertices, dtype=float)
        if len(a) < 2:
            continue
        g = LineString(a).buffer(half_width_m, cap_style=2, join_style=2)
        if not g.is_empty:
            shapes.append((mapping(g), 1))
    top_down = rasterize(
        shapes,
        out_shape=shape,
        transform=transform,
        fill=0,
        dtype=np.uint8,
        all_touched=True,
    )
    return np.flipud(top_down).astype(bool)


def roof_rain_weights(building_mask: np.ndarray) -> np.ndarray:
    """Return rainfall weights conserving rain that falls on roofs.

    Ground cells receive their own rainfall with weight=1.
    For each connected building footprint, all roof-cell rainfall is spread
    uniformly across its 4-neighbour building/ground boundary edges.

    Sum(weights) == total number of raster cells, apart from floating error.
    """
    b = building_mask.astype(bool)
    nr, nc = b.shape
    labels, nlabels = label(b, structure=np.ones((3, 3), dtype=np.uint8))

    area = np.bincount(labels.ravel(), minlength=nlabels + 1).astype(np.float64)
    area[0] = 0.0
    edge_count = np.zeros(nlabels + 1, dtype=np.float64)

    # Count 4-neighbour building -> ground boundary edges for each component.
    masks = []

    mask = b[1:, :] & (~b[:-1, :])
    masks.append(("south", mask, labels[1:, :][mask]))
    edge_count += np.bincount(labels[1:, :][mask], minlength=nlabels + 1)

    mask = b[:-1, :] & (~b[1:, :])
    masks.append(("north", mask, labels[:-1, :][mask]))
    edge_count += np.bincount(labels[:-1, :][mask], minlength=nlabels + 1)

    mask = b[:, 1:] & (~b[:, :-1])
    masks.append(("west", mask, labels[:, 1:][mask]))
    edge_count += np.bincount(labels[:, 1:][mask], minlength=nlabels + 1)

    mask = b[:, :-1] & (~b[:, 1:])
    masks.append(("east", mask, labels[:, :-1][mask]))
    edge_count += np.bincount(labels[:, :-1][mask], minlength=nlabels + 1)

    rw = (~b).astype(np.float64)  # own rainfall on non-building cells

    for direction, mask, component_ids in masks:
        value = area[component_ids] / np.maximum(edge_count[component_ids], 1.0)
        rr, cc = np.where(mask)
        if direction == "south":
            np.add.at(rw, (rr, cc), value)
        elif direction == "north":
            np.add.at(rw, (rr + 1, cc), value)
        elif direction == "west":
            np.add.at(rw, (rr, cc), value)
        elif direction == "east":
            np.add.at(rw, (rr, cc + 1), value)

    rw[b] = 0.0
    return rw.astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dem", default="dem_1m.npz")
    ap.add_argument("--buildings", default="buildings.npz")
    ap.add_argument("--vectors", default="basemap_vectors.npz")
    ap.add_argument("--out", default="hydraulic_inputs")
    ap.add_argument("--road-half-width", type=float, default=3.0)
    ap.add_argument("--n-ground", type=float, default=0.030)
    ap.add_argument("--n-road", type=float, default=0.020)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    dem = np.load(args.dem)
    z = np.asarray(dem["z"], dtype=np.float32)
    xs = np.asarray(dem["x"], dtype=float)
    ys = np.asarray(dem["y"], dtype=float)
    nr, nc = z.shape
    if nr != nc:
        raise ValueError("Reference solver currently expects a square grid")
    if len(xs) != nc or len(ys) != nr:
        raise ValueError("Coordinate arrays do not match DEM shape")

    dx = float(np.median(np.diff(xs)))
    dy = float(np.median(np.diff(ys)))
    if not np.isclose(dx, dy, rtol=0, atol=1e-6):
        raise ValueError("Reference solver assumes dx == dy")

    transform = from_origin(xs[0] - dx / 2, ys[-1] + dy / 2, dx, dy)

    bdata = np.load(args.buildings, allow_pickle=True)
    vdata = np.load(args.vectors, allow_pickle=True)

    building = polygons_to_mask(bdata["buildings"], z.shape, transform)
    road = roads_to_mask(vdata["roads"], z.shape, transform, args.road_half_width)
    road &= ~building

    manning = np.full(z.shape, args.n_ground, dtype=np.float32)
    manning[road] = args.n_road

    rain_weight = roof_rain_weights(building)

    z.tofile(out / "z.bin")
    manning.tofile(out / "manning.bin")
    rain_weight.tofile(out / "rain_weight.bin")
    building.astype(np.uint8).tofile(out / "building.bin")
    road.astype(np.uint8).tofile(out / "road.bin")

    np.savez_compressed(
        out / "metadata.npz",
        x=xs,
        y=ys,
        dx=np.float32(dx),
        N=np.int32(nr),
        building=building.astype(np.uint8),
        road=road.astype(np.uint8),
        manning=manning,
        rain_weight=rain_weight,
    )

    print(f"grid: {nr} x {nc}, dx={dx:g} m")
    print(f"building fraction: {building.mean():.4f}")
    print(f"road fraction: {road.mean():.4f}")
    print(f"rain-weight mass check: {rain_weight.sum():.3f} / {z.size}")


if __name__ == "__main__":
    main()
