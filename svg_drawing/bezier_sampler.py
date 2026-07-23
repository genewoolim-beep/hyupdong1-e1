"""bezier_sampler.py

svgpathtools 의 Path(직선/Cubic·Quadratic Bezier/Arc 세그먼트 혼합)를
일정 간격으로 샘플링하여 연속 좌표 리스트(폴리라인)로 변환한다.

- 곡선이든 직선이든 세그먼트별 .length()·.point(t) 를 이용하므로 타입에 무관하게 동작.
- 샘플 간격은 "SVG 단위" 기준(max_seg_len_svg). 실측 0.5mm 로 찍고 싶으면
  호출부에서 max_seg_len_svg = 0.5 / scale (scale=mm/‪SVG단위‬) 로 계산해 넘긴다.
  → 관심사 분리: 샘플러는 순수 기하만, 실좌표 스케일은 coordinate_mapper 가.

출력: List[List[Tuple[float, float]]]  (SVG 좌표계 폴리라인들)

단독 테스트:
    python3 bezier_sampler.py
"""

from __future__ import annotations

import math
from typing import List, Tuple

Point = Tuple[float, float]
Polyline = List[Point]


def _sample_segment(seg, max_seg_len: float) -> List[complex]:
    """단일 세그먼트를 max_seg_len(SVG 단위) 이하 간격으로 샘플. 시작점 제외, 끝점 포함.
    (연속 이어붙이기 위해 시작점은 호출부에서 중복 없이 관리)"""
    try:
        seg_len = seg.length()
    except Exception:
        seg_len = abs(seg.end - seg.start)

    # 세그먼트를 몇 조각으로 나눌지 (최소 1). 아주 짧으면 끝점만.
    n = max(1, int(math.ceil(seg_len / max_seg_len))) if max_seg_len > 0 else 1
    pts = []
    for i in range(1, n + 1):
        t = i / n
        c = seg.point(t)       # 파라미터 t∈[0,1] 위치(복소수). 세그먼트 내부는 균일 t 로 충분.
        pts.append(c)
    return pts


def sample_path(path, max_seg_len: float) -> Polyline:
    """연속 Path(하나의 획) → 폴리라인. 시작점을 넣고 세그먼트마다 이어붙인다."""
    if len(path) == 0:
        return []
    poly: List[complex] = [path[0].start]
    for seg in path:
        poly.extend(_sample_segment(seg, max_seg_len))

    # 복소수 → (x, y), 그리고 인접 중복점 제거(수치오차로 붙는 점 정리)
    out: Polyline = []
    for c in poly:
        p = (float(c.real), float(c.imag))
        if not out or (abs(p[0] - out[-1][0]) > 1e-9 or abs(p[1] - out[-1][1]) > 1e-9):
            out.append(p)
    return out


def sample_paths(paths, max_seg_len: float,
                 min_points: int = 2) -> List[Polyline]:
    """여러 Path(획) → 폴리라인 리스트. 점이 너무 적은(퇴화된) 획은 버린다."""
    result: List[Polyline] = []
    for p in paths:
        poly = sample_path(p, max_seg_len)
        if len(poly) >= min_points:
            result.append(poly)
    return result


# ── 단독 테스트 ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    # svgpathtools 없이도 최소 검증이 되도록, 없으면 가짜 세그먼트로 테스트한다.
    try:
        from svgpathtools import Path, Line, CubicBezier
        line = Line(0 + 0j, 10 + 0j)
        curve = CubicBezier(10 + 0j, 15 + 10j, 25 + 10j, 30 + 0j)
        path = Path(line, curve)
        poly = sample_path(path, max_seg_len=0.5)
        print(f"svgpathtools 경로 샘플: {len(poly)} points, "
              f"start={poly[0]}, end={poly[-1]}")
    except ImportError:
        class _FakeSeg:
            def __init__(self, a, b):
                self.start, self.end = a, b

            def length(self):
                return abs(self.end - self.start)

            def point(self, t):
                return self.start + (self.end - self.start) * t
        seg = _FakeSeg(0 + 0j, 10 + 0j)
        poly = sample_path([seg], max_seg_len=0.5)
        print(f"[svgpathtools 미설치] 가짜 직선 샘플: {len(poly)} points, "
              f"start={poly[0]}, end={poly[-1]}")
        assert abs(poly[-1][0] - 10.0) < 1e-6
        print("OK")
