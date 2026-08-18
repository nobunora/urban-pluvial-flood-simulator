#!/usr/bin/env python3
"""Minimal rainbow plot for solver output; deliberately contains no location labels."""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--metadata", default="hydraulic_inputs/metadata.npz")
    ap.add_argument("--prefix", default="result")
    ap.add_argument("--out", default="max_depth_rainbow.png")
    args = ap.parse_args()

    meta = np.load(args.metadata)
    x = meta["x"].astype(float)
    y = meta["y"].astype(float)
    N = int(meta["N"])
    building = meta["building"].astype(bool)

    hmax = np.fromfile(args.prefix + "_hmax.bin", dtype=np.float32).reshape(N, N)
    hmax = np.where(building, np.nan, hmax)

    levels = np.array([0.02, 0.05, 0.10, 0.20, 0.30, 0.50, 0.75, 1.0, 1.5, 2, 3, 5, 8])
    cmap = plt.get_cmap("turbo", len(levels) - 1)
    norm = BoundaryNorm(levels, cmap.N, clip=True)

    fig, ax = plt.subplots(figsize=(10, 9), dpi=180)
    im = ax.imshow(
        np.ma.masked_less(hmax, 0.02),
        extent=[x[0] - 0.5, x[-1] + 0.5, y[0] - 0.5, y[-1] + 0.5],
        origin="lower",
        cmap=cmap,
        norm=norm,
        interpolation="nearest",
    )
    ax.set_aspect("equal")
    ax.set_xlabel("Local X [m]")
    ax.set_ylabel("Local Y [m]")
    ax.set_title("Local-Inertial 2D Flood Simulation — Maximum Water Depth")
    cb = fig.colorbar(im, ax=ax, boundaries=levels, ticks=levels[:-1])
    cb.set_label("Maximum water depth [m]")
    fig.tight_layout()
    fig.savefig(args.out, bbox_inches="tight")
    print(Path(args.out).resolve())


if __name__ == "__main__":
    main()
