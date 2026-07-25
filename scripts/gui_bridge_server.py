#!/usr/bin/env python3
"""gui_bridge_server.py

PersonalitySignature 브라우저 GUI ↔ 로봇 시그니처 드로잉 시퀀스(run_signature_sequence.py)를
잇는 로컬 HTTP 브릿지. 외부 의존성 없음(표준 라이브러리 http.server만 사용).

왜 필요한가: GUI는 브라우저(JS)에서 돌고, 로봇 제어는 로컬 ROS2 Python 프로세스에서 돈다.
브라우저는 로컬 프로세스를 직접 실행할 수 없으므로, "그리겠습니다" 버튼 클릭 → 이 서버에
HTTP POST → 서버가 run_signature_sequence.py를 실행하는 다리 역할.

엔드포인트:
    POST /draw-signature   body: GUI의 로봇용 폴리라인 JSON 그대로(toRobotJSON() 출력)
                            → run_signature_sequence.py를 백그라운드로 실행, {job_id} 반환
    POST /draw-sample      body: {"sample": "square"|"hex_spiral"}
                            → samples/ 의 기존 SVG를 변환 없이 그대로 그림(설문 없이 빠른 테스트용)
    GET  /status?job=<id>  → {state: queued|running|done|error|stopped, log_tail: "..."}
    POST /estop             → ① emergency_stop.py로 로봇에 정지 명령 즉시 전송
                              ② 실행 중인 시퀀스 프로세스(자식 포함) 전체 종료(다음 단계로 못 넘어가게)
    POST /go-home           → go_home.py로 준비자세 복귀(다른 작업 실행 중이면 거절)
    GET  /health            → {status: "ok"}

CORS: 다른 포트(React dev server)에서 fetch할 수 있게 모든 origin 허용.
⚠ 로컬 전용입니다(127.0.0.1). 실제 로봇을 움직이는 만큼 외부 네트워크에 절대 노출하지 마세요.

실행:
    python3 gui_bridge_server.py --port 8787 --speed-scale 0.3 --plate-size-mm 90
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'samples')
# 샘플 그리기(테스트)용 — GUI 인트로 화면에서 설문 없이 바로 테스트할 수 있는 기존 SVG들.
SAMPLE_SVGS = {
    'square': os.path.join(SAMPLES_DIR, 'square.svg'),
    'hex_spiral': os.path.join(SAMPLES_DIR, 'hex_spiral.svg'),
}
JOBS: dict = {}
JOBS_LOCK = threading.Lock()
CURRENT_JOB_ID: list = [None]     # 가장 최근/실행 중인 job — /estop 이 job_id 없이도 멈출 수 있게

# main()에서 CLI 인자로 채움
# 안전 리셋: 컨트롤러 재기동 후 누적 상승시켜둔 배율이 그대로(클램핑 없이) 적용돼
# 위험하게 빨라지는 게 실기에서 확인됨 → 전부 원본 DRL 속도(1.0)로 되돌림.
CONFIG = {'plate_size_mm': 112.5,
         'pen_up_speed': 0.595, 'pen_down_speed': 0.595, 'brush_speed': 0.6375, 'grab_speed': 0.85}


def _run_job(job_id: str, strokes_json_path: str = None, svg_path: str = None):
    """strokes_json_path(임시 파일, 끝나면 삭제) 또는 svg_path(기존 샘플 SVG, 안 지움)
    둘 중 하나로 run_signature_sequence.py 를 실행한다."""
    with JOBS_LOCK:
        JOBS[job_id]['state'] = 'running'
    CURRENT_JOB_ID[0] = job_id
    log_path = (strokes_json_path or svg_path) + '.log'
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, 'run_signature_sequence.py')]
    if svg_path:
        cmd += ['--svg-path', svg_path]
    else:
        cmd += ['--strokes-json', strokes_json_path]
    cmd += ['--plate-size-mm', str(CONFIG['plate_size_mm']),
           '--pen-up-speed', str(CONFIG['pen_up_speed']),
           '--pen-down-speed', str(CONFIG['pen_down_speed']),
           '--brush-speed', str(CONFIG['brush_speed']),
           '--grab-speed', str(CONFIG['grab_speed'])]
    try:
        with open(log_path, 'w', encoding='utf-8') as logf:
            # start_new_session=True: 이 프로세스가 만드는 자식(run_drl_motion.py 등)까지
            # 하나의 프로세스 그룹으로 묶어서, /estop 시 os.killpg 로 통째로 종료 가능하게 한다.
            proc = subprocess.Popen(cmd, cwd=SCRIPT_DIR, stdout=logf,
                                    stderr=subprocess.STDOUT, start_new_session=True)
            with JOBS_LOCK:
                JOBS[job_id]['pid'] = proc.pid
            returncode = proc.wait(timeout=1800)
        with JOBS_LOCK:
            if JOBS[job_id]['state'] != 'stopped':   # /estop 이 이미 처리했으면 덮어쓰지 않음
                JOBS[job_id]['state'] = 'done' if returncode == 0 else 'error'
                JOBS[job_id]['returncode'] = returncode
    except Exception as e:
        with JOBS_LOCK:
            if JOBS[job_id]['state'] != 'stopped':
                JOBS[job_id]['state'] = 'error'
                JOBS[job_id]['error'] = str(e)
    finally:
        with JOBS_LOCK:
            JOBS[job_id]['log_path'] = log_path
        if strokes_json_path:      # 임시로 만든 파일만 지움. 샘플 SVG(svg_path)는 안 지움.
            try:
                os.remove(strokes_json_path)
            except OSError:
                pass


def _estop() -> dict:
    """① 로봇에 정지 명령부터 즉시 전송(가장 시급) ② 실행 중인 시퀀스 프로세스 그룹 종료."""
    result = {'stop_sent': False, 'stop_message': '', 'job_killed': None}

    # ① 물리적 정지 — 지금 어떤 프로세스가 movel 로 블로킹 중이어도 상관없이, 독립 노드로
    #    motion/move_stop 서비스를 직접 호출한다(가장 시급하니 먼저).
    try:
        stop_proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, 'emergency_stop.py')],
            cwd=SCRIPT_DIR, capture_output=True, text=True, timeout=5)
        result['stop_sent'] = (stop_proc.returncode == 0)
        result['stop_message'] = (stop_proc.stdout or stop_proc.stderr).strip()
    except Exception as e:
        result['stop_message'] = f'정지 명령 전송 실패: {e}'

    # ② 실행 중인 시퀀스가 다음 단계(예: grab)로 이어서 넘어가지 않도록 프로세스 그룹째 종료.
    job_id = CURRENT_JOB_ID[0]
    if job_id:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            pid = job.get('pid') if job else None
            busy = job and job['state'] in ('queued', 'running')
        if busy and pid:
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                time.sleep(0.5)
                os.killpg(os.getpgid(pid), signal.SIGKILL)  # 안 죽었으면 확실히
            except ProcessLookupError:
                pass
            except Exception as e:
                result['stop_message'] += f' (프로세스 종료 중 경고: {e})'
            with JOBS_LOCK:
                JOBS[job_id]['state'] = 'stopped'
            result['job_killed'] = job_id

    return result


def _go_home() -> dict:
    """준비자세 복귀. 다른 작업이 실행 중이면(동시에 두 프로세스가 로봇을 움직이면 충돌하니)
    거절한다 — 먼저 /estop 으로 세운 뒤 호출해야 함."""
    job_id = CURRENT_JOB_ID[0]
    if job_id:
        with JOBS_LOCK:
            job = JOBS.get(job_id)
            busy = job and job['state'] in ('queued', 'running')
        if busy:
            return {'ok': False,
                   'message': '다른 작업이 실행 중입니다. 먼저 긴급중지 후 시도하세요.'}

    try:
        proc = subprocess.run(
            [sys.executable, os.path.join(SCRIPT_DIR, 'go_home.py')],
            cwd=SCRIPT_DIR, capture_output=True, text=True, timeout=60)
        return {'ok': proc.returncode == 0,
               'message': (proc.stdout or proc.stderr).strip()}
    except Exception as e:
        return {'ok': False, 'message': f'원위치 실패: {e}'}


class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/health':
            self._json(200, {'status': 'ok'})
            return
        if parsed.path == '/status':
            job_id = (parse_qs(parsed.query).get('job') or [None])[0]
            with JOBS_LOCK:
                job = dict(JOBS.get(job_id, {}))
            if not job:
                self._json(404, {'error': 'unknown job'})
                return
            log_tail = ''
            lp = job.get('log_path')
            if lp and os.path.isfile(lp):
                with open(lp, encoding='utf-8', errors='replace') as f:
                    log_tail = ''.join(f.readlines()[-40:])
            self._json(200, {'state': job['state'], 'log_tail': log_tail})
            return
        self._json(404, {'error': 'not found'})

    def do_POST(self):
        if self.path == '/estop':
            result = _estop()
            self._json(200, result)
            return
        if self.path == '/go-home':
            result = _go_home()
            self._json(200 if result['ok'] else 409, result)
            return
        if self.path == '/draw-sample':
            length = int(self.headers.get('Content-Length', '0') or '0')
            body = self.rfile.read(length)
            try:
                data = json.loads(body.decode('utf-8')) if length else {}
            except Exception as e:
                self._json(400, {'error': f'invalid JSON: {e}'})
                return
            name = data.get('sample')
            svg_path = SAMPLE_SVGS.get(name)
            if not svg_path:
                self._json(400, {'error': f"알 수 없는 sample: {name!r}. "
                                          f"가능한 값: {list(SAMPLE_SVGS)}"})
                return
            if not os.path.isfile(svg_path):
                self._json(500, {'error': f'샘플 SVG 파일 없음: {svg_path}'})
                return
            job_id = uuid.uuid4().hex[:12]
            with JOBS_LOCK:
                JOBS[job_id] = {'state': 'queued'}
            threading.Thread(target=_run_job, args=(job_id,),
                             kwargs={'svg_path': svg_path}, daemon=True).start()
            self._json(202, {'job_id': job_id})
            return
        if self.path != '/draw-signature':
            self._json(404, {'error': 'not found'})
            return
        length = int(self.headers.get('Content-Length', '0') or '0')
        body = self.rfile.read(length)
        try:
            data = json.loads(body.decode('utf-8'))
        except Exception as e:
            self._json(400, {'error': f'invalid JSON: {e}'})
            return
        if not data.get('strokes'):
            self._json(400, {'error': 'strokes 가 비어있습니다'})
            return

        job_id = uuid.uuid4().hex[:12]
        tmp_path = os.path.join(SCRIPT_DIR, f'.job_{job_id}.json')
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

        with JOBS_LOCK:
            JOBS[job_id] = {'state': 'queued'}
        threading.Thread(target=_run_job, args=(job_id,),
                         kwargs={'strokes_json_path': tmp_path}, daemon=True).start()
        self._json(202, {'job_id': job_id})

    def log_message(self, fmt, *a):
        print("[bridge]", fmt % a)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=8787)
    ap.add_argument('--plate-size-mm', type=float, default=112.5)
    ap.add_argument('--pen-up-speed', type=float, default=0.595,
                    help='pen_up 속도 배율. 기본 0.595(0.7에서 -15%%)')
    ap.add_argument('--pen-down-speed', type=float, default=0.595,
                    help='pen_down 속도 배율. 기본 0.595(0.7에서 -15%%)')
    ap.add_argument('--brush-speed', type=float, default=0.6375,
                    help='brush 속도 배율. 기본 0.6375(0.75에서 -15%%)')
    ap.add_argument('--grab-speed', type=float, default=0.85,
                    help='grab 속도 배율. 기본 0.85(1.0에서 -15%%)')
    args = ap.parse_args()
    CONFIG['plate_size_mm'] = args.plate_size_mm
    CONFIG['pen_up_speed'] = args.pen_up_speed
    CONFIG['pen_down_speed'] = args.pen_down_speed
    CONFIG['brush_speed'] = args.brush_speed
    CONFIG['grab_speed'] = args.grab_speed

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f"[gui_bridge_server] http://127.0.0.1:{args.port} 대기 중 "
          f"(plate_size={args.plate_size_mm}mm, pen_up={args.pen_up_speed}, "
          f"pen_down={args.pen_down_speed}, brush={args.brush_speed}, grab={args.grab_speed})")
    print("      POST /draw-signature | GET /status?job=<id> | GET /health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[gui_bridge_server] 종료")


if __name__ == '__main__':
    main()
