#!/usr/bin/env python3
"""run_signature_sequence.py

PersonalitySignature GUI에서 만든 나선 문양을 아크릴판에 그리고 전달하는 전체 시퀀스.

    pen_up(펜꽂이에서 펜 집기)
    → lower_to_paper.py(아크릴에 문양 그리기)
    → pen_down(펜 반납)
    → brush(아크릴 먼지 제거)
    → grab(완성 아크릴판 집어서 전달)

입력은 GUI의 "로봇용 폴리라인(JSON)" 버튼(toRobotJSON())과 동일한 포맷:
    { canvas: {w,h}, units: "px", meta: {...}, strokes: [[[x,y],...], ...] }

각 단계는 기존 스크립트(run_drl_motion.py / lower_to_paper.py)를 독립 서브프로세스로
그대로 재사용한다 — 새 로직을 만들지 않고, 이미 실기/시뮬 양쪽에서 검증된 스크립트를
순서대로 호출하는 얇은 오케스트레이터. 한 단계라도 실패하면 즉시 중단한다(다음 단계로
넘어가지 않음 — 예: 그리기 실패했는데 grab 으로 넘어가면 안 됨).

사용:
    python3 run_signature_sequence.py --strokes-json signature_INTJ.json
    cat signature.json | python3 run_signature_sequence.py --strokes-json -
    python3 run_signature_sequence.py --strokes-json s.json --skip-pen --skip-brush-grab  # 그리기만 테스트
    python3 run_signature_sequence.py --svg-path ../samples/hex_spiral.svg  # 기존 SVG 파일 직접 사용(샘플 테스트용)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def strokes_to_svg(strokes, canvas_w=600, canvas_h=600) -> str:
    """GUI의 toSVG()와 동일한 포맷(M/L만 사용, viewBox 0 0 w h, fill 없음)."""

    def path_d(pts):
        parts = []
        for i, (x, y) in enumerate(pts):
            cmd = 'M' if i == 0 else 'L'
            parts.append(f"{cmd}{float(x):.1f} {float(y):.1f}")
        return " ".join(parts)

    paths = "\n".join(f'  <path d="{path_d(s)}" />' for s in strokes if len(s) >= 2)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {canvas_w} {canvas_h}" width="{canvas_w}" height="{canvas_h}">\n'
            f'  <g fill="none" stroke="#1a1a1a" stroke-width="1.5" '
            f'stroke-linecap="round" stroke-linejoin="round">\n{paths}\n  </g>\n</svg>\n')


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--strokes-json', default=None,
                    help='GUI 로봇용 폴리라인 JSON 파일 경로. stdin 이면 "-". '
                         '--svg-path 와 둘 중 하나만')
    ap.add_argument('--svg-path', default=None,
                    help='이미 있는 SVG 파일을 그대로 그리기(변환 없음, transform 있는 '
                         'SVG도 SvgParser 가 처리). samples/hex_spiral.svg 같은 샘플 '
                         '테스트용. --strokes-json 와 둘 중 하나만')
    ap.add_argument('--plate-size-mm', type=float, default=90.0,
                    help='아크릴판 한 변(mm). 기본 90(GUI 주석의 "명함 90mm" 기준). '
                         '실제 판 크기에 맞춰 조정하세요')
    ap.add_argument('--robot-id', default='dsr01')
    ap.add_argument('--model', default='m0609')
    # ── 안전 리셋(중요) ──────────────────────────────────────────────────
    # 이번 세션에서 배율을 여러 차례 누적 상승시켰는데("컨트롤러가 알아서 클램핑해줄 것"
    # 이라는 잘못된 가정 하에), 컨트롤러/모드가 리셋되자 그 큰 값이 그대로 적용돼 위험하게
    # 빨라지는 게 실기에서 확인됨. 전부 원본 DRL 속도(1.0 = 사람이 펜던트에서 가르치고
    # 검증한 속도)로 되돌린다. 다시 올릴 땐 반드시 실기에서 눈으로 보며 한 단계씩만.
    ap.add_argument('--pen-up-speed', type=float, default=0.595,
                    help='pen_up 속도 배율. 기본 0.595(0.7에서 -15%)')
    ap.add_argument('--pen-down-speed', type=float, default=0.595,
                    help='pen_down 속도 배율. 기본 0.595(0.7에서 -15%)')
    ap.add_argument('--brush-speed', type=float, default=0.6375,
                    help='brush 속도 배율. 기본 0.6375(0.75에서 -15%)')
    ap.add_argument('--grab-speed', type=float, default=0.85,
                    help='grab 속도 배율. 기본 0.85(1.0에서 -15%)')
    ap.add_argument('--skip-pen', action='store_true',
                    help='디버그용: pen_up/pen_down 생략(이미 펜을 쥐고 있을 때)')
    ap.add_argument('--skip-brush-grab', action='store_true',
                    help='디버그용: brush/grab 생략(그리기만 테스트할 때)')
    ap.add_argument('--step-delay-s', type=float, default=0.2,
                    help='단계(서브프로세스) 사이 대기(초). 2.0→0.5→0.2로 단축 — '
                         '너무 줄이면 rclpy 노드를 텀 없이 연달아 만들 때 간헐적으로 멈추는 '
                         '현상이 재발할 수 있음. 재발하면 다시 올릴 것')
    return ap.parse_args()


def run_step(name: str, cmd: list, stdin_text: str = "", timeout: float = 10000):
    print(f"\n===== [{name}] {' '.join(cmd)} =====", flush=True)
    result = subprocess.run(cmd, cwd=SCRIPT_DIR, input=stdin_text.encode('utf-8'),
                            timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(f"[{name}] 실패(exit={result.returncode}) — 시퀀스 중단")
    print(f"===== [{name}] 완료 =====", flush=True)


def main():
    args = parse_args()

    if bool(args.strokes_json) == bool(args.svg_path):
        print("[에러] --strokes-json 또는 --svg-path 중 정확히 하나만 지정하세요.")
        sys.exit(1)

    cleanup_svg = False
    if args.svg_path:
        svg_path = args.svg_path
        if not os.path.isfile(svg_path):
            print(f"[에러] SVG 없음: {svg_path}")
            sys.exit(1)
        print(f"[입력] 기존 SVG 그대로 사용: {svg_path}")
    else:
        raw = (sys.stdin.read() if args.strokes_json == '-'
               else open(args.strokes_json, encoding='utf-8').read())
        data = json.loads(raw)
        strokes = data.get('strokes') or []
        canvas = data.get('canvas') or {'w': 600, 'h': 600}
        meta = data.get('meta') or {}
        if not strokes:
            print("[에러] strokes 가 비어있습니다.")
            sys.exit(1)
        print(f"[입력] type={meta.get('type')} 획 {len(strokes)}개, canvas={canvas}")

        svg_text = strokes_to_svg(strokes, canvas.get('w', 600), canvas.get('h', 600))
        fd, svg_path = tempfile.mkstemp(prefix='signature_', suffix='.svg')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(svg_text)
        cleanup_svg = True
        print(f"[변환] SVG 저장: {svg_path} ({len(strokes)}획)")

    py = sys.executable

    def motion_cmd(motion, speed_scale, skip_ready_movej=False):
        cmd = [py, os.path.join(SCRIPT_DIR, 'run_drl_motion.py'),
               '--motion', motion, '--robot-id', args.robot_id, '--model', args.model,
               '--speed-scale', str(speed_scale)]
        if skip_ready_movej:
            cmd.append('--skip-ready-movej')
        return cmd

    try:
        if not args.skip_pen:
            run_step('pen_up', motion_cmd('pen_up', args.pen_up_speed), stdin_text="\n")
            time.sleep(args.step_delay_s)

        run_step('draw', [py, os.path.join(SCRIPT_DIR, 'lower_to_paper.py'),
                          '--svg', svg_path, '--size', str(args.plate_size_mm),
                          '--robot-id', args.robot_id, '--model', args.model],
                  stdin_text="y\n")
        time.sleep(args.step_delay_s)

        if not args.skip_pen:
            run_step('pen_down', motion_cmd('pen_down', args.pen_down_speed), stdin_text="\n")
            time.sleep(args.step_delay_s)

        if not args.skip_brush_grab:
            run_step('brush', motion_cmd('brush', args.brush_speed), stdin_text="\n")
            time.sleep(args.step_delay_s)

            # brush 가 정확히 같은 준비자세(0,0,90,0,90,0)로 끝나므로, grab 시작 movej 는
            # 완전 중복이라 생략(제자리 movej로 시간 낭비하던 문제).
            run_step('grab', motion_cmd('grab', args.grab_speed, skip_ready_movej=True),
                    stdin_text="\n")

        print("\n[전체 완료] 시그니처 드로잉 시퀀스 성공")
    finally:
        if cleanup_svg:
            try:
                os.remove(svg_path)
            except OSError:
                pass


if __name__ == '__main__':
    main()
