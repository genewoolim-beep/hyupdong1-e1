"""trajectory_planner.py

획(폴리라인) 순서 최적화.

SVG 에 저장된 순서를 그대로 쓰지 않고, 다음 획까지의 '공중 이동(펜업)' 거리를
최소화하도록 Nearest-Neighbor(그리디)로 재정렬한다. 각 획은 시작점/끝점 중
현재 펜 위치에 더 가까운 쪽으로 진입할 수 있으므로, 필요하면 획을 뒤집는다.

입력/출력: List[List[(x, y)]]  (용지 mm 폴리라인)

순수 파이썬이라 단독 테스트 가능:
    python3 trajectory_planner.py
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

Point = Tuple[float, float]
Polyline = List[Point]


def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def travel_distance(strokes: List[Polyline], start: Point = (0.0, 0.0)) -> float:
    """주어진 순서로 그릴 때의 총 '공중 이동(펜업)' 거리 합. 비교/디버그용."""
    total = 0.0
    cur = start
    for s in strokes:
        if not s:
            continue
        total += _dist(cur, s[0])
        cur = s[-1]
    return total


def optimize(strokes: List[Polyline],
             start: Point = (0.0, 0.0),
             allow_reverse: bool = True) -> List[Polyline]:
    """Nearest-Neighbor 그리디 재정렬. allow_reverse=True 면 획 뒤집기 허용.

    O(n^2) — 만다라 라인아트 수준(수백~수천 획)에서 충분히 빠르다.
    """
    remaining = [s for s in strokes if len(s) >= 2]
    ordered: List[Polyline] = []
    cur: Point = start

    while remaining:
        best_i: Optional[int] = None
        best_d = float('inf')
        best_reversed = False

        for i, s in enumerate(remaining):
            d_start = _dist(cur, s[0])
            if d_start < best_d:
                best_d, best_i, best_reversed = d_start, i, False
            if allow_reverse:
                d_end = _dist(cur, s[-1])
                if d_end < best_d:
                    best_d, best_i, best_reversed = d_end, i, True

        chosen = remaining.pop(best_i)
        if best_reversed:
            chosen = list(reversed(chosen))
        ordered.append(chosen)
        cur = chosen[-1]

    return ordered


# ── 단독 테스트 ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    # 일부러 나쁜 순서로 배치된 4개 선분. NN 최적화 후 총 이동거리가 줄어야 한다.
    strokes = [
        [(0, 0), (10, 0)],      # A: 0..10
        [(0, 30), (10, 30)],    # C: far
        [(12, 0), (20, 0)],     # B: right after A
        [(20, 30), (12, 30)],   # D
    ]
    before = travel_distance(strokes)
    opt = optimize(strokes)
    after = travel_distance(opt)
    print(f"공중 이동거리  before={before:.1f}  after={after:.1f}")
    for s in opt:
        print("  ", s[0], "->", s[-1])
    assert after <= before
    print("OK")
