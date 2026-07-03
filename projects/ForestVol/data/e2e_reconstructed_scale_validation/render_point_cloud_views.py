from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import open3d as o3d
from PIL import Image, ImageDraw


VIEWS = {
    "front": ((0, 1), 2),
    "back": ((0, 1), 2),
    "left": ((1, 2), 0),
    "right": ((1, 2), 0),
    "top": ((0, 2), 1),
    "iso": None,
}


PLY_DTYPE = np.dtype(
    [
        ("x", "<f4"),
        ("y", "<f4"),
        ("z", "<f4"),
        ("nx", "<f4"),
        ("ny", "<f4"),
        ("nz", "<f4"),
        ("red", "u1"),
        ("blue", "u1"),
        ("green", "u1"),
        ("views", "u1"),
    ]
)


def read_cloud(path: str) -> tuple[np.ndarray, np.ndarray]:
    cloud = o3d.io.read_point_cloud(path)
    points = np.asarray(cloud.points, dtype=np.float64)
    colors = np.asarray(cloud.colors, dtype=np.float64)
    if len(points):
        if colors.size == 0:
            colors = np.full_like(points, 0.72)
        return points, np.clip(colors * 255.0, 0, 255)

    raw = Path(path).read_bytes()
    header_end = raw.index(b"end_header\n") + len(b"end_header\n")
    header = raw[:header_end].decode("ascii", errors="ignore")
    vertex_count = None
    for line in header.splitlines():
        if line.startswith("element vertex "):
            vertex_count = int(line.split()[-1])
            break
    if vertex_count is None:
        raise ValueError(f"Could not read vertex count from {path}")
    data = np.frombuffer(raw, dtype=PLY_DTYPE, count=vertex_count, offset=header_end)
    points = np.column_stack([data["x"], data["y"], data["z"]]).astype(np.float64)
    colors = np.column_stack([data["red"], data["green"], data["blue"]]).astype(np.float64)
    return points, colors


def normalize(values: np.ndarray) -> np.ndarray:
    vmin = float(np.min(values))
    vmax = float(np.max(values))
    if vmax <= vmin:
        return np.zeros_like(values, dtype=float)
    return (values - vmin) / (vmax - vmin)


def project_iso(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    centered = points - points.mean(axis=0)
    yaw = np.deg2rad(38.0)
    pitch = np.deg2rad(28.0)
    rz = np.array(
        [
            [np.cos(yaw), -np.sin(yaw), 0],
            [np.sin(yaw), np.cos(yaw), 0],
            [0, 0, 1],
        ]
    )
    rx = np.array(
        [
            [1, 0, 0],
            [0, np.cos(pitch), -np.sin(pitch)],
            [0, np.sin(pitch), np.cos(pitch)],
        ]
    )
    rotated = centered @ rz.T @ rx.T
    return rotated[:, 0], rotated[:, 1], rotated[:, 2]


def render(points: np.ndarray, colors: np.ndarray, view: str, output: Path, size: int = 1600) -> None:
    if view == "iso":
        x, y, depth = project_iso(points)
    else:
        axes, depth_axis = VIEWS[view]
        x = points[:, axes[0]]
        y = points[:, axes[1]]
        depth = points[:, depth_axis]
        if view in {"back", "right"}:
            x = -x

    margin = 80
    xn = normalize(x)
    yn = normalize(y)
    px = (margin + xn * (size - 2 * margin)).astype(np.int32)
    py = (size - margin - yn * (size - 2 * margin)).astype(np.int32)

    depth_n = normalize(depth)
    order = np.argsort(depth_n)
    px = px[order]
    py = py[order]
    rgb = colors[order]
    shade = (0.45 + 0.55 * depth_n[order])[:, None]
    rgb = np.clip(rgb * shade, 0, 255).astype(np.uint8)

    image = Image.new("RGB", (size, size), (18, 20, 22))
    draw = ImageDraw.Draw(image, "RGB")
    for chunk_start in range(0, len(px), 120000):
        chunk_end = min(chunk_start + 120000, len(px))
        for x0, y0, color in zip(px[chunk_start:chunk_end], py[chunk_start:chunk_end], rgb[chunk_start:chunk_end]):
            draw.point((int(x0), int(y0)), fill=tuple(int(c) for c in color))

    draw.rectangle((18, 18, size - 18, size - 18), outline=(70, 74, 78), width=2)
    draw.text((36, 32), view.upper(), fill=(235, 238, 240))
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cloud", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-points", type=int, default=350000)
    args = parser.parse_args()

    points, colors = read_cloud(args.cloud)

    if len(points) > args.max_points:
        rng = np.random.default_rng(1234)
        sample = rng.choice(len(points), size=args.max_points, replace=False)
        points = points[sample]
        colors = colors[sample]

    out = Path(args.out)
    for view in VIEWS:
        render(points, colors, view, out / f"{view}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
