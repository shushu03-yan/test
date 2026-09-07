from __future__ import annotations

import math
import re
from pathlib import Path

CELL_TAGS = {
    "_cell_length_a": "a",
    "_cell_length_b": "b",
    "_cell_length_c": "c",
    "_cell_angle_alpha": "alpha",
    "_cell_angle_beta": "beta",
    "_cell_angle_gamma": "gamma",
}


def cif_number(value: str) -> float:
    value = value.strip().strip("'\"")
    value = re.sub(r"\(\d+\)$", "", value)
    return float(value)


def read_cell(path: str | Path) -> dict[str, float]:
    values: dict[str, float] = {}
    with Path(path).open(encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            parts = raw.split()
            if len(parts) >= 2 and parts[0].lower() in CELL_TAGS:
                values[CELL_TAGS[parts[0].lower()]] = cif_number(parts[1])
    missing = sorted(set(CELL_TAGS.values()) - set(values))
    if missing:
        raise ValueError(f"CIF 缺少晶胞参数: {', '.join(missing)}")
    return values


def compute_supercell(cell: dict[str, float], minimum_length: float) -> tuple[int, int, int]:
    a, b, c = cell["a"], cell["b"], cell["c"]
    alpha, beta, gamma = (math.radians(cell[x]) for x in ("alpha", "beta", "gamma"))
    ca, cb, cg = math.cos(alpha), math.cos(beta), math.cos(gamma)
    radicand = 1 - ca * ca - cb * cb - cg * cg + 2 * ca * cb * cg
    if min(a, b, c) <= 0 or radicand <= 0:
        raise ValueError("CIF 晶胞几何无效")
    volume = a * b * c * math.sqrt(radicand)
    heights = (
        volume / (b * c * math.sin(alpha)),
        volume / (a * c * math.sin(beta)),
        volume / (a * b * math.sin(gamma)),
    )
    if min(heights) <= 0:
        raise ValueError("无法计算有效晶胞面间距")
    return tuple(max(1, math.ceil(minimum_length / height)) for height in heights)  # type: ignore[return-value]

