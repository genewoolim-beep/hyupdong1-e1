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
```

> 서비스(.srv)는 순수 `ament_python` 에서 생성이 안 되므로, 표준 방식대로
> 별도 `ament_cmake` 인터페이스 패키지(`svg_drawing_interfaces`)로 분리했습니다.

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
