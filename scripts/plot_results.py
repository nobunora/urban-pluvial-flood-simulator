#!/usr/bin/env python3
"""Minimal rainbow plot for solver output; deliberately contains no location labels."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, LogNorm
from matplotlib.patches import Patch
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metadata", default="hydraulic_inputs/metadata.npz")
    ap.add_argument("--prefix", default="result")
    ap.add_argument("--out", default="max_depth_rainbow.png")
    ap.add_argument(
        "--overlay-infrastructure",
        action="store_true",
        help="overlay rasterized PLATEAU/OSM building and road information",
    )
    args = ap.parse_args()

    meta = np.load(args.metadata)
    x = meta["x"].astype(float)
    y = meta["y"].astype(float)
    N = int(meta["N"])
    building = meta["building"].astype(bool)
    road = meta["road"].astype(bool) if "road" in meta.files else np.zeros((N, N), dtype=bool)
    extent = [x[0] - 0.5, x[-1] + 0.5, y[0] - 0.5, y[-1] + 0.5]

    hmax = np.fromfile(args.prefix + "_hmax.bin", dtype=np.float32).reshape(N, N)
    hmax = np.where(building, np.nan, hmax)

    positive_depth = hmax[np.isfinite(hmax) & (hmax > 0.0)]
    if positive_depth.size == 0:
        raise ValueError("Maximum-depth output contains no positive water depth")
    vmin = float(positive_depth.min())
    vmax = float(positive_depth.max())
    if np.isclose(vmin, vmax):
        vmin = vmax / 10.0
    cmap = plt.get_cmap("turbo")
    norm = LogNorm(vmin=vmin, vmax=vmax)

    fig, ax = plt.subplots(figsize=(10, 9), dpi=180)
    im = ax.imshow(
        np.ma.masked_less_equal(hmax, 0.0),
        extent=extent,
        origin="lower",
        cmap=cmap,
        norm=norm,
        interpolation="nearest",
    )
    if args.overlay_infrastructure:
        ax.imshow(
            np.ma.masked_where(~road, road),
            extent=extent,
            origin="lower",
            cmap=ListedColormap(["#3d3d3d"]),
            alpha=0.25,
            interpolation="nearest",
        )
        ax.imshow(
            np.ma.masked_where(~building, building),
            extent=extent,
            origin="lower",
            cmap=ListedColormap(["#5c5c5c"]),
            alpha=0.85,
            interpolation="nearest",
        )
    ax.set_aspect("equal")
    ax.set_xlabel("Local X [m]")
    ax.set_ylabel("Local Y [m]")
    title = "Local-Inertial 2D Flood Simulation — Maximum Water Depth (log scale)"
    ax.set_title(title + (" with infrastructure" if args.overlay_infrastructure else ""))
    cb = fig.colorbar(im, ax=ax)
    cb.set_label("Maximum water depth [m]")
    if args.overlay_infrastructure:
        ax.legend(
            handles=[
                Patch(color="#5c5c5c", label="Building"),
                Patch(color="#3d3d3d", alpha=0.25, label="Road"),
            ],
            loc="lower left",
        )
    fig.tight_layout()
    fig.savefig(args.out, bbox_inches="tight")
    print(Path(args.out).resolve())


if __name__ == "__main__":
    main()
