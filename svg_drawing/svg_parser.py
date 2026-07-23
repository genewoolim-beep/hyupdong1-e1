"""svg_parser.py

SVG 벡터 데이터를 읽어 '연속 획(폴리라인 후보)' 리스트로 변환한다.

[중요] 파싱 엔진: svgelements
    - 예전엔 svgpathtools 를 썼으나, 설치본이 <path>/<use> 의 transform(회전·이동 등)을
      '무시'해서 <use ... transform="rotate(180)"> 로 복제된 도형이 누락되는 문제가 있었다.
    - svgelements 는 <use>/<defs> 참조와 transform(회전/스케일/이동), viewBox, 단위까지
      모두 해석해 '절대 좌표'로 평탄화(flatten)해 준다. 그래서 이걸로 교체했다.

지원 요소: <path> 중심 + <line>/<polyline>/<polygon>/<circle>/<ellipse>/<rect>
           + <use>/<defs>/group/transform (svgelements 가 자동 평탄화)

출력:
    ParsedSvg(
        strokes : List[List[_SegAdapter]]   # '연속 서브패스' 단위 = 펜다운 1회 = 획
        viewbox : ViewBox                    # 평탄화된 전체 도형의 바운딩박스(스케일 계산용)
    )

각 stroke 는 아직 SVG(절대) 좌표계이며 곡선(Bezier/Arc)이 그대로 들어있다.
샘플링은 bezier_sampler 가, 실좌표 변환은 coordinate_mapper 가 담당한다(관심사 분리).

bezier_sampler 는 각 세그먼트의 .length()/.point(t)(→복소수)/.start/.end 만 사용하므로,
svgelements 세그먼트를 그 인터페이스로 감싸는 _SegAdapter 만 제공하면 downstream 은 무변경.

단독 테스트:
    python3 svg_parser.py sample.svg
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ViewBox:
    """도형 좌표계 범위. (min_x, min_y) 좌상단, width/height 는 SVG 단위."""
    min_x: float
    min_y: float
    width: float
    height: float

    @property
    def max_x(self) -> float:
        return self.min_x + self.width

    @property
    def max_y(self) -> float:
        return self.min_y + self.height


@dataclass
class ParsedSvg:
    strokes: List[list] = field(default_factory=list)   # List[List[_SegAdapter]]
    viewbox: ViewBox = None


def _require_svgelements():
    """svgelements 지연 import. 없으면 친절한 에러."""
    try:
        import svgelements  # noqa: F401
        return svgelements
    except ImportError as e:
        raise ImportError(
            "svgelements 가 필요합니다. 'pip install svgelements' 로 설치하세요. "
            "(SVG 의 <use>/transform 을 정확히 해석하기 위해 사용합니다)"
        ) from e


class _SegAdapter:
    """svgelements 세그먼트를 bezier_sampler 가 기대하는 인터페이스로 감싼다.
    .start/.end 는 복소수, .point(t) 는 복소수, .length() 는 float."""

    __slots__ = ("_s", "start", "end")

    def __init__(self, seg):
        self._s = seg
        s, e = seg.start, seg.end
        self.start = complex(s.x, s.y) if s is not None else None
        self.end = complex(e.x, e.y) if e is not None else None

    def length(self) -> float:
        try:
            return float(self._s.length())
        except Exception:
            if self.start is not None and self.end is not None:
                return abs(self.end - self.start)
            return 0.0

    def point(self, t: float) -> complex:
        p = self._s.point(t)
        return complex(p.x, p.y)


class SvgParser:
    """SVG 파일 → 연속 획(세그먼트 리스트) 목록 + ViewBox(평탄화 도형 bbox)."""

    def parse(self, svg_path: str) -> ParsedSvg:
        svgelements = _require_svgelements()
        SVG = svgelements.SVG
        Shape = svgelements.Shape
        Path = svgelements.Path
        Move = svgelements.Move

        # 1) 파싱 + 평탄화(use/defs/transform/viewBox 를 절대좌표로 reify)
        svg = SVG.parse(svg_path)

        strokes: List[list] = []
        xmin = ymin = float("inf")
        xmax = ymax = float("-inf")
        found_bbox = False

        # 2) 모든 그래픽 요소를 순회(그룹/use 는 이미 펼쳐져 개별 Shape 로 나온다)
        for el in svg.elements():
            if not isinstance(el, Shape):
                continue
            try:
                path = abs(Path(el))          # 도형→Path 변환 + transform 적용
            except Exception:
                continue
            if len(path) == 0:
                continue

            # 전체 바운딩박스 누적(스케일용 viewbox 대체)
            try:
                bb = path.bbox()
            except Exception:
                bb = None
            if bb:
                xmin, ymin = min(xmin, bb[0]), min(ymin, bb[1])
                xmax, ymax = max(xmax, bb[2]), max(ymax, bb[3])
                found_bbox = True

            # 3) Move 를 경계로 '연속 서브패스(획)' 분해
            cur: List[_SegAdapter] = []
            for seg in path:
                if isinstance(seg, Move):
                    if cur:
                        strokes.append(cur)
                        cur = []
                    continue
                # Line/Close/CubicBezier/QuadraticBezier/Arc → 어댑터
                if seg.start is None or seg.end is None:
                    continue
                cur.append(_SegAdapter(seg))
            if cur:
                strokes.append(cur)

        if not found_bbox:
            raise ValueError("SVG 에서 그릴 도형을 찾지 못했습니다.")

        viewbox = ViewBox(xmin, ymin, max(xmax - xmin, 1e-6), max(ymax - ymin, 1e-6))
        return ParsedSvg(strokes=strokes, viewbox=viewbox)


# ── 단독 테스트 ──────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("사용법: python3 svg_parser.py <파일.svg>")
        raise SystemExit(1)
    parsed = SvgParser().parse(sys.argv[1])
    vb = parsed.viewbox
    print(f"ViewBox(bbox): min=({vb.min_x:.2f},{vb.min_y:.2f}) "
          f"size=({vb.width:.2f}x{vb.height:.2f})")
    print(f"획(연속 서브패스) 개수: {len(parsed.strokes)}")
    for i, sp in enumerate(parsed.strokes[:6]):
        total = sum(s.length() for s in sp)
        print(f"  [{i}] segments={len(sp)} length={total:.2f}")
