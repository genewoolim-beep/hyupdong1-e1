"""coordinate_mapper.py

SVG 좌표계 → 작업 영역(용지) 좌표계(mm) 변환.

작업 영역 규약 (스펙):
    - A5 (기본 148mm x 210mm), 원점 = 좌상단
    - X : 오른쪽이 양수,  Y : 아래쪽이 양수  (SVG 와 동일 방향 → y 뒤집기 불필요)

기능:
    - ViewBox 크기를 읽어 그림 전체가 작업 영역(여백 제외) 안에 '비율 유지'로
      들어가도록 균일 스케일(min-fit) 계산 → Aspect Ratio 보존(찌그러짐 없음)
    - center=True 면 작업 영역 중앙에 자동 정렬

이 단계의 출력은 '용지 mm' 좌표(좌상단 원점, x→오른쪽, y→아래).
용지 mm → 로봇 Base 좌표 변환은 robot_controller 가 담당한다(관심사 분리).

순수 파이썬(외부 의존성 없음)이라 단독 테스트가 쉽다:
    python3 coordinate_mapper.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

Point = Tuple[float, float]
Polyline = List[Point]


@dataclass
class WorkArea:
    width_mm: float = 148.0     # A5 가로
    height_mm: float = 210.0    # A5 세로
    margin_mm: float = 5.0      # 가장자리 여백
    center: bool = True         # 중앙 정렬 여부


class CoordinateMapper:
    """ViewBox(min_x,min_y,width,height) 와 WorkArea 로 SVG→용지mm 변환기를 만든다."""

    def __init__(self, viewbox, work_area: WorkArea):
        self.vb = viewbox
        self.wa = work_area

        usable_w = max(work_area.width_mm - 2 * work_area.margin_mm, 1e-6)
        usable_h = max(work_area.height_mm - 2 * work_area.margin_mm, 1e-6)

        vb_w = max(viewbox.width, 1e-9)
        vb_h = max(viewbox.height, 1e-9)

        # 비율 유지 min-fit : 가로/세로 중 더 빡빡한 쪽에 맞춘다 → 절대 삐져나가지 않음
        self.scale = min(usable_w / vb_w, usable_h / vb_h)   # mm per SVG unit

        drawn_w = vb_w * self.scale
        drawn_h = vb_h * self.scale

        if work_area.center:
            self.offset_x = (work_area.width_mm - drawn_w) / 2.0
            self.offset_y = (work_area.height_mm - drawn_h) / 2.0
        else:
            self.offset_x = work_area.margin_mm
            self.offset_y = work_area.margin_mm

    def map_point(self, x: float, y: float) -> Point:
        """SVG 좌표 → 용지 mm 좌표(좌상단 원점, x→오른쪽, y→아래)."""
        px = (x - self.vb.min_x) * self.scale + self.offset_x
        py = (y - self.vb.min_y) * self.scale + self.offset_y
        return (px, py)

    def map_polyline(self, poly: Polyline) -> Polyline:
        return [self.map_point(x, y) for (x, y) in poly]

    def map_strokes(self, strokes: List[Polyline]) -> List[Polyline]:
        return [self.map_polyline(p) for p in strokes]

    def describe(self) -> str:
        return (f"scale={self.scale:.4f} mm/unit, "
                f"offset=({self.offset_x:.2f},{self.offset_y:.2f}) mm, "
                f"drawn=({self.vb.width*self.scale:.1f}x{self.vb.height*self.scale:.1f}) mm")


# ── 단독 테스트 ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    @dataclass
    class _VB:
        min_x: float
        min_y: float
        width: float
        height: float

    # 정사각 SVG(100x100) → A5 세로 용지. 비율 유지되어 가로(148-여백)에 맞고 세로 중앙정렬.
    vb = _VB(0, 0, 100, 100)
    wa = WorkArea()
    m = CoordinateMapper(vb, wa)
    print(m.describe())

    corners = [(0, 0), (100, 0), (100, 100), (0, 100), (50, 50)]
    for (x, y) in corners:
        print(f"  SVG({x},{y}) -> paper{tuple(round(v, 2) for v in m.map_point(x, y))} mm")

    # 검증: 중심(50,50) 은 용지 중앙(74,105) 근처
    cx, cy = m.map_point(50, 50)
    assert abs(cx - wa.width_mm / 2) < 1e-6 and abs(cy - wa.height_mm / 2) < 1e-6
    # 검증: 스케일이 usable 폭에 맞음 (정사각이라 폭이 더 빡빡: (148-10)/100)
    assert abs(m.scale - (wa.width_mm - 2 * wa.margin_mm) / 100) < 1e-9
    print("OK")
