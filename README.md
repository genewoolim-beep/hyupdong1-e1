# svg_drawing

Doosan Robotics **M0609** 협동로봇으로 아크릴 표면에 철 펜(0.5mm)을 이용해
**SVG(만다라 라인아트)** 를 스크래치 드로잉하는 ROS2 **Humble** 패키지.

> 📖 **처음 쓰는 팀원은 [사용설명서.md](사용설명서.md) 를 보세요** (실행 방법·키보드 조작·문제해결).
> 이 README 는 패키지 구조·서비스 방식 등 **개발자용 기술 문서**입니다.
>
> ⚠️ 실사용은 서비스보다 **`scripts/lower_to_paper.py`(키보드로 표면 잡고 위치제어로 그리기)** 를 권장.
> **힘제어(`use_force_control`)는 payload/TCP 캘리 전엔 펜이 박혀 못 씁니다** → 기본 위치제어 사용.

- 입력: **ROS2 Service** 로 **SVG 파일 경로** 전달 (PNG/JPG 등 래스터 미사용)
- SVG **벡터(`<path>` 중심 + line/polyline/polygon/circle/ellipse/rect)** 를 직접 분석
  (OpenCV edge/contour **미사용**)
- Bezier/Arc 곡선을 **실측 0.5mm 간격**으로 샘플링 → 연속 폴리라인
- **A5(148×210mm)** 작업영역에 **비율 유지 + 중앙 정렬**로 스케일
- 획 순서를 **Nearest-Neighbor** 로 최적화(공중 이동 최소화)
- 펜 자세(Rx,Ry,Rz) 고정, **XY 평면**에서만 이동
- **펜 집기/놓기는 구현 제외**(스펙). **Z 높이·TCP·용지 위치는 config 로 분리**(추후 캘리브레이션)

## 패키지 구성

```
svg_drawing_interfaces/         # ament_cmake : 서비스 정의
  srv/DrawSvg.srv               #   string svg_path --- bool success, string message
svg_drawing/                    # ament_python : 노드 + 모듈
  svg_drawing/
    svg_parser.py               # SVG → 획(Path) 리스트 (svgelements: use/transform 평탄화)
    bezier_sampler.py           # 곡선 → 0.5mm 폴리라인 샘플링
    coordinate_mapper.py        # SVG → A5 용지 mm (비율유지·중앙정렬)
    trajectory_planner.py       # Nearest-Neighbor 획 순서 최적화
    robot_controller.py         # 용지 mm → Base 좌표, Doosan 모션 실행
    drawing_server.py           # ROS2 서비스 서버(전체 파이프라인)
  config/drawing_params.yaml    # Z높이/TCP/용지/속도/샘플간격 등 전 파라미터
  launch/drawing.launch.py
scripts/                        # 독립 실행 스크립트(빌드 불필요, 바로 python3 실행)
  lower_to_paper.py             #   키보드로 표면 잡고 위치제어로 SVG 그리기(가장 많이 씀)
  drl_motions.py                #   pen_up/pen_down/brush/grab 픽앤플레이스 모션 정의
  run_drl_motion.py             #   drl_motions.py 단일 모션 CLI 실행기(--speed-scale 등)
  run_signature_sequence.py     #   pen_up→그리기→pen_down→brush→grab 전체 시퀀스 오케스트레이터
  gui_bridge_server.py          #   브라우저 GUI ↔ 로봇 제어 로컬 HTTP 브릿지(포트 8787)
  emergency_stop.py             #   motion/move_stop 서비스 직접 호출(긴급정지)
  go_home.py                    #   준비자세 복귀
  force_monitor.py / velocity_monitor.py  # 힘/속도 실측 모니터링(디버그용)
samples/                        # 테스트용 SVG(square, hex_spiral 등)
PersonalitySignature_spiral.jsx # MBTI→문양 생성기 React 소스(GUI 원본, 로봇 연동 버튼 포함)
personality_signature.html      # 위 jsx를 CDN React+Babel로 즉시 실행하는 정적 페이지(빌드 불필요)
```

> 서비스(.srv)는 순수 `ament_python` 에서 생성이 안 되므로, 표준 방식대로
> 별도 `ament_cmake` 인터페이스 패키지(`svg_drawing_interfaces`)로 분리했습니다.
>
> `scripts/` 아래 파일들은 `svg_drawing` 패키지 밖의 독립 스크립트라 **colcon 빌드가 필요 없습니다**
> (수정 후 바로 `python3 scripts/파일명.py` 로 실행). 빌드가 필요한 건 `svg_drawing/` 패키지
> 내부(`svg_parser.py` 등 서비스가 import 하는 모듈)를 고쳤을 때뿐입니다.

## 다른 컴퓨터(노트북)에서 설치하기

이 저장소를 새 컴퓨터에서 그대로 쓰려면:

```bash
# 1) ROS2 Humble 설치 + Doosan M0609 드라이버(dsr_bringup2, dsr_msgs2 등)는 별도로 이미
#    설치되어 있어야 함(이 저장소는 그 위에 얹는 응용 패키지). 로봇 제조사 워크스페이스 설정을 먼저 마칠 것.

# 2) 이 저장소를 콜콘 워크스페이스의 src/ 에 클론
cd ~/ws_cobot_pjt/ws_dsr/src
git clone <이 저장소 URL> svg_drawing

# 3) 파이썬 의존성
pip install svgelements numpy

# 4) 빌드
cd ~/ws_cobot_pjt/ws_dsr
colcon build --packages-select svg_drawing_interfaces svg_drawing
source install/setup.bash
```

브라우저 GUI(`personality_signature.html`)는 별도 설치 없이 **파일 하나로 바로 실행**됩니다
(React/Babel을 CDN에서 불러오므로 최초 실행 시 인터넷 연결만 있으면 됨, Node.js/npm 불필요).

> **실제로 GUI를 켜고 로봇을 움직이는 손에 잡히는 절차(터미널 명령·버튼 순서·안전 수칙)는
> [사용설명서.md](사용설명서.md) 의 "GUI로 로봇 구동하기" 절을 그대로 따라 하세요.**
> 이 README 는 코드 구조 설명이 목적이고, 실행 순서의 최종 기준은 사용설명서입니다.

## 의존성 설치

```bash
pip install svgelements numpy      # svgelements 는 rosdep 키가 없어 pip 설치 필요
```

## 빌드

```bash
cd ~/ws_cobot_pjt/ws_dsr
colcon build --packages-select svg_drawing_interfaces svg_drawing
source install/setup.bash
```

## 실행

```bash
# 1) (실장비) Doosan bringup 을 먼저 실행해 /dsr01/... 서비스가 떠 있어야 함
#    ros2 launch dsr_bringup2 dsr_bringup2_rviz.launch.py mode:=real host:=192.168.x.x ...

# 2) 드로잉 서버
ros2 launch svg_drawing drawing.launch.py
#   로봇 없이 경로만 검증하려면:
ros2 launch svg_drawing drawing.launch.py dry_run:=true

# 3) SVG 그리기 요청
ros2 service call /dsr01/draw_svg svg_drawing_interfaces/srv/DrawSvg \
    "{svg_path: '/absolute/path/mandala.svg'}"
```

## 파라미터 (config/drawing_params.yaml)

| 파라미터 | 의미 | 비고 |
|---|---|---|
| `draw_height_mm` / `travel_height_mm` / `approach_height_mm` | 긋기/이동/접근 Z(Base) | **추후 캘리브레이션 필수** |
| `paper_origin_x_mm` / `paper_origin_y_mm` | 용지 좌상단의 Base 좌표 | **추후 캘리브레이션 필수** |
| `paper_x_sign` / `paper_y_sign` | 용지축→Base축 방향 부호 | 설치 방향에 맞춤 |
| `tool_rx_deg/ry/rz` | 고정 펜 자세 | TCP 설정에 맞춤 |
| `sample_resolution_mm` | 곡선 샘플 간격(실측) | 기본 0.5 |
| `work_area_*` | A5 크기·여백·중앙정렬 | |
| `stroke_mode` | `movel`(충실)/`movesx`(빠름) | |
| `draw_blend_radius_mm` | movel 점간 블렌드 반경 | 0=정확, ↑=부드럽고 빠름 |
| `use_force_control` | Z축 힘제어로 긋기 | ⚠️ **payload/TCP 캘리 후에만**. 캘리 전엔 펜 박힘 → 기본 `false`(위치제어) |
| `draw_force_n` / `force_z_sign` | 누르는 힘(N) / 방향 부호 | 실장비 튜닝 |
| `compliance_stiffness` | [x,y,z,rx,ry,rz] 강성 | XY딱딱/Z물렁 |
| `probe_*` | 터치오프 힘·속도·안전한계 | `/touch_off` 서비스용 |
| `dry_run` | 로봇 미동작(경로만 계산) | 검증용 |

## Z축 힘 제어 (스크래치 접촉 품질)

`use_force_control: true` 면 획을 그을 때 **XY 는 위치제어(정확한 형태), Z 는 일정 힘으로
누르는 힘제어**로 그린다. 아크릴 표면이 미세하게 울퉁불퉁하거나 `draw_height` 가 조금
안 맞아도 펜이 **일정 압력**으로 눌려 접촉이 유지된다(스크래치 굵기 균일·안전).
`gear_assembly.py` 의 `task_compliance_ctrl`/`set_desired_force` 와 같은 방식이다.
> 실장비에서 `draw_force_n`(누르는 힘)과 `force_z_sign`(누르는 방향)은 반드시 튜닝하세요.

## 터치오프 (표면 Z 자동 측정) — `/touch_off` 서비스

펜을 표면 위에서 천천히 내려 **접촉을 감지**하고, 측정된 Base Z 로 `draw_height_mm` 를
자동 갱신한다. → 매번 손으로 Z 를 재는 수고를 없앤다.

```bash
# 용지 중앙(예: 74,105 mm) 근처를 짚어 표면 Z 측정
ros2 service call /dsr01/touch_off svg_drawing_interfaces/srv/TouchOff \
    "{x_mm: 74.0, y_mm: 105.0}"
# 성공 시 draw_height_mm 자동 갱신 → 바로 draw_svg 호출하면 됨
```
**안전장치**(config `probe_*`): 예상 표면보다 위에서만 하강 시작, 최대 하강거리·타임아웃
초과 시 중단, 툴 무게 정적힘 오탐 방지(최소 하강량 이상 내려간 뒤에만 접촉 인정).
> 시뮬(에뮬레이터)은 접촉 물리가 없어 터치오프가 항상 '안전 중단'된다(정상). 실장비 전용.

## 실장비 캘리브레이션 → 드로잉 순서

```bash
# 0) (실장비) bringup: ros2 launch m0609_rg2_bringup bringup.launch.py mode:=real host:=<IP>
# 1) 드로잉 서버(힘제어 켜서)
ros2 launch svg_drawing drawing.launch.py    # config 에서 use_force_control: true 로
# 2) TCP·용지원점·자세는 config 에 먼저 입력(펜 TCP 티칭 후)
# 3) 터치오프로 표면 Z 자동 측정
ros2 service call /dsr01/touch_off svg_drawing_interfaces/srv/TouchOff "{x_mm: 74, y_mm: 105}"
# 4) dry_run 없이 저속으로 첫 드로잉
ros2 service call /dsr01/draw_svg svg_drawing_interfaces/srv/DrawSvg "{svg_path: '/…/mandala.svg'}"
```

## GUI + 로봇 자동 시퀀스 (scripts/, PersonalitySignature 연동)

`drawing.launch.py`(서비스 방식)와는 별개로, MBTI 문양 생성 GUI에서 바로 로봇을
움직이는 **두 번째 실행 경로**가 `scripts/` 아래에 있습니다. 조작 절차는
[사용설명서.md](사용설명서.md)를 보고, 여기서는 구조만 설명합니다.

```
브라우저(personality_signature.html, React)
   │  fetch("http://127.0.0.1:8787/...")
   ▼
scripts/gui_bridge_server.py   (표준 라이브러리 http.server만 사용, 외부 의존성 0)
   │  subprocess.Popen(..., start_new_session=True)   ← 자식까지 한 프로세스 그룹으로 묶음
   ▼
scripts/run_signature_sequence.py   (오케스트레이터)
   │  각 단계를 독립 서브프로세스로 순차 호출, 하나라도 실패하면 즉시 중단
   ├─ run_drl_motion.py --motion pen_up     (drl_motions.py)
   ├─ lower_to_paper.py --svg <문양 SVG>     (아크릴에 실제로 그리기)
   ├─ run_drl_motion.py --motion pen_down
   ├─ run_drl_motion.py --motion brush
   └─ run_drl_motion.py --motion grab       (완성 아크릴판 집어서 전달)
```

**gui_bridge_server.py 엔드포인트**

| 메서드/경로 | 역할 |
|---|---|
| `POST /draw-signature` | body = GUI의 로봇용 폴리라인 JSON(`toRobotJSON()` 출력) → 전체 시퀀스 실행, `{job_id}` 반환 |
| `POST /draw-sample` | body = `{"sample":"square"\|"hex_spiral"}` → `samples/`의 기존 SVG를 변환 없이 그대로 그림(빠른 테스트용) |
| `GET /status?job=<id>` | `{state: queued\|running\|done\|error\|stopped, log_tail}` — GUI가 폴링 |
| `POST /estop` | `emergency_stop.py`로 즉시 정지 명령 전송 + 실행 중 시퀀스 프로세스 그룹 강제 종료 |
| `POST /go-home` | `go_home.py`로 준비자세 복귀(다른 작업 실행 중이면 409로 거절) |
| `GET /health` | 헬스체크 |

로컬(127.0.0.1) 전용이며 CORS는 전체 허용(로컬 파일/포트에서 브라우저가 바로 fetch 가능하게).
**실제 로봇을 움직이므로 외부 네트워크에 절대 노출하지 마세요.**

**속도/안전 파라미터**: `run_signature_sequence.py`/`gui_bridge_server.py`의
`pen-up-speed`/`pen-down-speed`/`brush-speed`/`grab-speed`(모두 1.0=DRL 펜던트 원속도 기준
배율)와 `plate-size-mm`(아크릴판 한 변, 실제 판보다 크면 안 됨)는 실기에서 검증된 안전값이
기본값으로 들어 있습니다. 컨트롤러를 재기동했거나 새 로봇/새 컴퓨터에서 처음 쓸 때는
반드시 낮은 배율로 먼저 검증하세요(컨트롤러 재기동 후 배율이 그대로 적용돼 위험하게
빨라진 사례가 있었음 — 자세한 경위는 git log 참고).

## 각 모듈 단독 테스트

```bash
python3 svg_drawing/coordinate_mapper.py     # SVG→A5 매핑 검증
python3 svg_drawing/trajectory_planner.py    # NN 최적화 검증
python3 svg_drawing/robot_controller.py      # 좌표변환·통계 검증(dry-run)
python3 svg_drawing/bezier_sampler.py        # 샘플링 검증
python3 svg_drawing/svg_parser.py <파일.svg> # 파싱 검증
```

## 확장 포인트 (객체지향 설계)

- **펜 자동 교체**: `robot_controller` 에 tool-change 시퀀스 메서드 추가.
- **TCP/Z 캘리브레이션**: 값만 `drawing_params.yaml` 에서 수정.
- **새 도형/구조 지원**: `svg_parser` 가 svgelements 로 <use>/<defs>/transform/group 을 자동 평탄화.
- **다른 용지 크기**: `work_area_*` 파라미터만 변경(A4 등).
- **경로 최적화 고도화**: `trajectory_planner.optimize` 를 2-opt 등으로 교체 가능.
