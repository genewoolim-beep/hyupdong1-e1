#!/usr/bin/env python3
"""make_spiral.py — 파라미터로 나선(회전+축소 다각형) 도안 SVG 를 생성한다.

lower_to_paper.py 는 SVG '읽기' 전용이라, 이 스크립트로 원하는 나선을 만들어
samples/ 에 저장한 뒤 --svg 로 그린다.

예:
    # 팔각 핀휠(현재 기본 octagon_pinwheel 과 동일 파라미터)
    python3 scripts/make_spiral.py --sides 8 --layers 40 --rotation 90 --hole 0.34 \
        --out samples/my_octagon.svg
    # 육각·더 촘촘·회오리(기하 축소)
    python3 scripts/make_spiral.py --sides 6 --layers 46 --rotation 130 --hole 0.13 \
        --spacing geometric --out samples/my_hex.svg
    그린 뒤:
    python3 scripts/lower_to_paper.py --svg samples/my_octagon.svg --size 175

파라미터 의미:
    --sides     다각형 변 수 (3=삼각, 4=사각, 6=육각, 8=팔각 …). 클수록 원에 가까움.
    --layers    겹(획) 수. 많을수록 촘촘·오래 걸림(각 겹 = 펜 1획).
    --rotation  전체 회전량(deg). 작으면 동심 다각형, 크면 강한 소용돌이/핀휠.
                (한 변 사이각 = 360/sides. 그 정도면 블레이드 1칸 스월)
    --hole      중심 구멍 비율(0~1). 0.3 이면 바깥의 30% 크기에서 멈춰 구멍을 남김.
    --spacing   linear(등간격, 회오리 없음·균일) | geometric(중심에 몰림·회오리 느낌)
    --flat-top  다각형을 flat-top 방향으로(평평한 윗변). 기본 on.
"""

from __future__ import annotations
import argparse
import math



def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def personality_to_params(v):
    """성향 벡터(0~100 6종) → 나선 파라미터.
    v = dict(creativity, planning, sociability, challenge, focus, sensitivity)
    PersonalitySignature 실험대와 동일 공식."""
    c = v["creativity"]; pl = v["planning"]; so = v["sociability"]
    ch = v["challenge"]; fo = v["focus"]; se = v["sensitivity"]
    sides = round(3 + c / 100 * 9)                       # 3~12
    layers = round(16 + fo / 100 * 30)                   # 16~46
    rotation = round(20 + (ch * 0.7 + se * 0.3) / 100 * 160)  # 20~180
    hole = round((0.16 + so / 100 * 0.26), 3)            # 0.16~0.42
    spacing = "linear" if pl >= 50 else "geometric"
    return dict(sides=int(sides), layers=int(layers), rotation=float(rotation),
                hole=float(hole), spacing=spacing)


def polygon_pts(sides: float, r: float, rot_deg: float, flat_top: bool) -> str:
    """중심(0,0) 기준 정다각형 꼭짓점 → SVG points 문자열."""
    # flat-top: 꼭짓점을 반칸(180/sides) 돌려 윗변이 수평이 되게
    base = (180.0 / sides) if flat_top else 0.0
    pts = []
    for k in range(int(sides)):
        a = math.radians(base + k * 360.0 / sides + rot_deg)
        pts.append(f"{r * math.cos(a):.2f},{r * math.sin(a):.2f}")
    return " ".join(pts)


def build_svg(sides, layers, rotation, hole, spacing, flat_top, stroke=1.0):
    R = 100.0
    body = []
    for k in range(layers):
        f = k / (layers - 1) if layers > 1 else 0.0
        if spacing == "geometric":
            # 기하 축소: r = R * ratio^k  (ratio 는 hole 로 결정)
            ratio = hole ** (1.0 / (layers - 1)) if layers > 1 else 1.0
            r = R * (ratio ** k)
        else:  # linear (등간격) — 중심 몰림 없음
            r = R * (1.0 - f * (1.0 - hole))
        rot = f * rotation
        body.append(f'    <polygon points="{polygon_pts(sides, r, rot, flat_top)}" />')
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'viewBox="-120 -120 240 240" width="800" height="800">\n'
        f'  <g fill="none" stroke="#1a1a1a" stroke-width="{stroke}" '
        'vector-effect="non-scaling-stroke">\n'
        + "\n".join(body)
        + "\n  </g>\n</svg>\n"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sides", type=int, default=8, help="다각형 변 수 (기본 8)")
    ap.add_argument("--layers", type=int, default=40, help="겹(획) 수 (기본 40)")
    ap.add_argument("--rotation", type=float, default=90.0,
                    help="전체 회전량 deg (기본 90). 0=동심, 크면 핀휠/소용돌이")
    ap.add_argument("--hole", type=float, default=0.34,
                    help="중심 구멍 비율 0~1 (기본 0.34)")
    ap.add_argument("--spacing", choices=["linear", "geometric"], default="linear",
                    help="linear=등간격(회오리 없음, 기본) | geometric=중심 몰림")
    ap.add_argument("--flat-top", dest="flat_top", action=argparse.BooleanOptionalAction,
                    default=True, help="flat-top 방향(기본 on)")
    ap.add_argument("--stroke", type=float, default=1.0, help="선 두께(미리보기용, 기본 1.0)")
    # ── 성격유형 모드: 성향 벡터(0~100) 주면 위 파라미터를 자동 도출 ──
    ap.add_argument("--creativity", type=float, help="창의성 0~100 (성격 모드)")
    ap.add_argument("--planning", type=float, help="계획성 0~100")
    ap.add_argument("--sociability", type=float, help="사교성 0~100")
    ap.add_argument("--challenge", type=float, help="도전성 0~100")
    ap.add_argument("--focus", type=float, help="집중력 0~100")
    ap.add_argument("--sensitivity", type=float, help="감수성 0~100")
    ap.add_argument("--out", required=True, help="출력 SVG 경로 (예: samples/my_spiral.svg)")
    args = ap.parse_args()

    _pv = ["creativity", "planning", "sociability", "challenge", "focus", "sensitivity"]
    if any(getattr(args, k) is not None for k in _pv):
        v = {k: (getattr(args, k) if getattr(args, k) is not None else 50.0) for k in _pv}
        d = personality_to_params(v)
        args.sides, args.layers = d["sides"], d["layers"]
        args.rotation, args.hole, args.spacing = d["rotation"], d["hole"], d["spacing"]
        print(f"[성격→나선] 벡터 {v}")

    if args.layers < 1:
        ap.error("--layers 는 1 이상")
    if not (0.0 < args.hole < 1.0):
        ap.error("--hole 은 0~1 사이")

    svg = build_svg(args.sides, args.layers, args.rotation, args.hole,
                    args.spacing, args.flat_top, args.stroke)
    with open(args.out, "w") as fp:
        fp.write(svg)
    print(f"생성: {args.out}")
    print(f"  변{args.sides}각 · 겹{args.layers}(=획) · 회전{args.rotation:g}° · "
          f"구멍{args.hole:g} · {args.spacing}")
    print(f"  그리기: python3 scripts/lower_to_paper.py --svg {args.out} --size 175")


if __name__ == "__main__":
    main()
