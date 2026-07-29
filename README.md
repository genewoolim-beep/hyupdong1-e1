# svg_drawing — MBTI 성향 시그니처 로봇 드로잉 시스템

Doosan Robotics **M0609** 협동로봇 + **OnRobot RG2** 그리퍼로, 펜을 쥐고 아크릴판에
**SVG 도안(성향 시그니처 문양 / 샘플 도형)**을 스크래치로 그린 뒤, 붓으로 먼지를 털고
완성된 판을 집어 전달까지 하는 **완전 자동화 파이프라인**입니다.

> 처음 쓰는 분은 이 문서 순서대로(설치 → GUI 실행) 따라 하면 됩니다.
> 터미널에서 SVG 하나만 빠르게 그려보고 싶다면 [6. 터미널에서 직접 그리기](#6-터미널에서-직접-그리기)로 바로 가세요.
> 상세 변경 이력은 [`CHANGELOG_2026-07-28.md`](CHANGELOG_2026-07-28.md) 참고.

---

## 1. 전체 그림

```
브라우저 (personality_signature.html)
   │  MBTI 설문 → 문양 생성 → [로봇으로 그리기] 클릭
   │  fetch("http://127.0.0.1:8787/...")
   ▼
scripts/gui_bridge_server.py   ── 로컬 HTTP 브릿지(포트 8787, 표준 라이브러리만 사용)
   │  subprocess 로 아래를 순서대로 실행
   ▼
scripts/run_signature_sequence.py   ── 오케스트레이터(하나라도 실패하면 즉시 중단)
   ├─ run_drl_motion.py --motion pen_up     펜 집기 (+ Modbus로 실제 파지 확인)
   ├─ lower_to_paper.py --svg <문양.svg>     아크릴에 실제로 그리기 (핵심 로직)
   ├─ run_drl_motion.py --motion pen_down   펜 반납
   ├─ run_drl_motion.py --motion brush      붓으로 가루 제거 (+ Modbus로 파지 확인)
   └─ run_drl_motion.py --motion grab       완성판 집어서 전달

# pen_up/brush 파지 실패 시: 그리퍼 열고 준비자세 자동 복귀 → GUI에 재시작 버튼 표시
# brush 실패는 --start-from brush 로 그리기 재실행 없이 brush→grab만 이어서 재개 가능
```

`lower_to_paper.py`가 내부적으로 쓰는 그리기 엔진은 `svg_drawing/robot_controller.py`
(ROS2 패키지 소스지만, `scripts/`에서 같은 폴더 상대경로로 import하기 때문에 **수정 후
빌드 없이 바로 반영**됩니다 — `svg_parser.py`/`bezier_sampler.py` 등도 마찬가지).

---

## 2. 폴더 구조

```
svg_drawing_interfaces/         # ament_cmake: ROS2 서비스 정의(.srv) — 선택적 경로용
svg_drawing/                    # ament_python 패키지 (핵심 로직)
  svg_drawing/
    svg_parser.py               #   SVG → 획(Path) 리스트
    bezier_sampler.py           #   곡선 샘플링(2mm) + RDP 점 단순화
    coordinate_mapper.py        #   SVG 좌표 → 실제 mm 좌표 매핑
    trajectory_planner.py       #   획 순서 최적화(이동거리 최소화)
    robot_controller.py         #   실제 로봇 모션 실행(힘제어·블렌드·슬로우존 등 전부 여기)
scripts/                        # 독립 실행 스크립트(빌드 불필요, python3 로 바로 실행)
  lower_to_paper.py             #   ★ SVG 한 장을 아크릴에 그리는 핵심 스크립트
  drl_motions.py                #   pen_up/pen_down/brush/grab 모션 정의 + 파지 검증
  run_drl_motion.py             #   drl_motions.py 단일 모션 CLI 실행기
  run_signature_sequence.py     #   pen_up→그리기→pen_down→brush→grab 전체 오케스트레이터
  gui_bridge_server.py          #   브라우저 GUI ↔ 로봇 로컬 HTTP 브릿지(포트 8787)
  gripper_modbus.py             #   그리퍼 Modbus TCP 직접 조회(실제 파지 여부 판정)
  probe_gripper_modbus.py       #   그리퍼 Modbus 레지스터 탐색용 진단 스크립트
  calibrate_pen_grasp.py / calibrate_grip_inplace.py  # 파지 임계값 실측 도구
  tcp_check.py / tcp_info.py    #   TCP(펜 오프셋 289mm) 리셋 감지 안전 가드
  emergency_stop.py             #   긴급정지
  go_home.py                    #   준비자세 복귀
samples/                        # 테스트/데모용 SVG 도안
PersonalitySignature_spiral.jsx # MBTI→문양 생성기 React 소스(GUI 원본)
personality_signature.html      # 위 jsx를 CDN React+Babel로 즉시 실행하는 정적 페이지
CHANGELOG_2026-07-*.md          # 작업 이력(문제/원인/해결 정리)
```

---

## 3. 설치 (새 컴퓨터에서 처음 켤 때)

```bash
# 1) ROS2 Humble + Doosan M0609 드라이버(dsr_bringup2, dsr_msgs2 등)가 이미
#    설치돼 있어야 합니다(제조사 워크스페이스 설정을 먼저 마칠 것).

# 2) 이 저장소를 콜콘 워크스페이스의 src/ 에 클론
cd ~/ws_cobot_pjt/ws_dsr/src
git clone <이 저장소 URL> svg_drawing

# 3) 파이썬 의존성
pip install svgelements numpy pymodbus   # pymodbus는 그리퍼 파지 검증(7-6)에 필요

# 4) 빌드(최초 1회 — 이후 scripts/, svg_drawing/*.py 수정은 재빌드 불필요)
cd ~/ws_cobot_pjt/ws_dsr
colcon build --packages-select svg_drawing_interfaces svg_drawing
source install/setup.bash
```

`personality_signature.html`은 **파일 하나로 바로 열리는 정적 페이지**입니다
(React/Babel을 CDN에서 불러오므로 최초 실행 시 인터넷 연결만 있으면 되고, Node.js/npm은
불필요합니다).

---

## 4. GUI로 로봇 구동하기 (가장 많이 쓰는 방법)

### 4-1. 터미널 A — 로봇 켜기

```bash
source /opt/ros/humble/setup.bash
source ~/ws_cobot_pjt/ws_dsr/install/setup.bash
ros2 launch m0609_rg2_bringup bringup.launch.py mode:=real host:=192.168.1.100
```
- 실행 전: 로봇 전원 ON → 안전(safety) 해제 → **자율(Autonomous) 모드**
- 처음 켜는 컴퓨터/로봇 조합이면 `mode:=virtual`(시뮬)로 먼저 전체 흐름을 검증하세요.

### 4-2. 터미널 B — 브릿지 서버 (그리는 동안 계속 켜둘 것)

```bash
source /opt/ros/humble/setup.bash
source ~/ws_cobot_pjt/ws_dsr/install/setup.bash
cd ~/ws_cobot_pjt/ws_dsr/src/svg_drawing/scripts
python3 gui_bridge_server.py --port 8787
```
아래처럼 뜨면 성공(진행 로그가 이 창에 계속 찍힙니다):
```
[gui_bridge_server] http://127.0.0.1:8787 대기 중 (plate_size=112.5mm, pen_up=0.595, ...)
```

### 4-3. 브라우저 — GUI 열기

`personality_signature.html`을 더블클릭(또는 브라우저 주소창에 파일 경로 입력)해서 엽니다.

| 화면 | 버튼 | 동작 |
|---|---|---|
| 인트로 | 샘플: 사각형 / hex_spiral | 설문 없이 저장된 도형을 바로 그림 — **처음 켰을 때 전체 흐름 검증용으로 추천** |
| 인트로/결과 | 긴급중지 | 로봇을 그 자리에서 즉시 세움 |
| 인트로/결과 | 원위치 | 준비자세로 복귀(다른 동작 진행 중이면 거절) |
| 인트로/결과 | 펜 내려놓기 | 힘 안 들이고 펜을 그리퍼에서 즉시 놓는 단독 동작 |
| 결과(설문 후) | 로봇으로 그리기 | 방금 만든 문양으로 전체 시퀀스(펜집기→그리기→펜반납→붓질→전달) 수행 |

버튼을 누르면 화면에 진행 상태(대기중/진행중/완료/오류/중지됨)와 획 진행률(%)이
자동 갱신됩니다.

### 4-4. gui_bridge_server.py 엔드포인트

| 메서드/경로 | 역할 |
|---|---|
| `POST /draw-signature` | body = GUI 문양의 로봇용 폴리라인 JSON → 전체 시퀀스 실행, `{job_id}` 반환 |
| `POST /draw-sample` | body = `{"sample":"square"\|"hex_spiral"}` → `samples/`의 기존 SVG를 그대로 그림 |
| `POST /pen-down` | 펜 내려놓기 단독 실행 |
| `POST /resume-brush` | 도안을 다시 그리지 않고 brush→grab만 이어서 실행(브러쉬 파지 실패 후 재시작용) |
| `POST /estop` | 즉시 정지 + 실행 중 시퀀스 프로세스 그룹 강제 종료 |
| `POST /go-home` | 준비자세 복귀(다른 작업 실행 중이면 409로 거절) |
| `GET /status?job=<id>` | `{state, log_tail, progress:{current,total,percent}}` — GUI가 폴링 |
| `GET /tcp-info` | 현재 활성 TCP 오프셋(mm) 조회 — TCP 리셋(289→0) 감지용 |
| `GET /health` | 헬스체크 |

로컬(127.0.0.1) 전용이며 CORS는 전체 허용. **실제 로봇을 움직이므로 외부 네트워크에
절대 노출하지 마세요.**

---

## 5. 안전 수칙 (꼭 지킬 것)

1. **그리는 동안 자리를 비우지 마세요.** 이상하면 즉시 GUI [긴급중지] 또는 물리 E-stop.
2. **아크릴판은 설정된 크기(기본 112.5mm 정사각) 이하**로 준비하세요. 판이 작으면 판
   밖을 긁을 수 있습니다. 크기를 바꾸려면 브릿지 서버 실행 시 `--plate-size-mm <mm>`.
3. **처음 켜는 컴퓨터/로봇 조합이면 반드시 시뮬(가상 모드)로 먼저** 전체 시퀀스를 돌려보고,
   이상 없으면 실장비로 전환하세요.
4. 각 동작(pen_up/pen_down/brush/grab)의 속도 배율은 실기에서 검증된 안전값이 기본으로
   들어 있습니다. **임의로 올리지 말고** 필요하면 한 단계씩 눈으로 보며 조정하세요.
5. **로봇 컨트롤러를 재시작했다면** 기존 속도 배율을 그대로 믿지 말고 저속으로 먼저 검증
   하세요 — 과거 재기동 직후 배율이 그대로 적용돼 위험하게 빨라진 사례가 있었습니다.
6. **TCP(펜 오프셋 289mm)가 리셋되면 충돌 위험**이 있습니다 — `lower_to_paper.py`와
   `run_drl_motion.py` 양쪽에 실행 전 자동 검증(`tcp_check.py`)이 들어 있어, 오프셋이
   289mm±20mm를 벗어나면 자동으로 동작을 중단합니다. 경고가 뜨면 펜던트에서 TCP를
   다시 확인하세요.
7. **펜/브러쉬를 못 집으면 자동으로 그리퍼를 열고 준비자세로 복귀**합니다(Modbus로 실제
   파지 여부 확인, [7-6](#7-6-그리퍼-파지-검증-modbus) 참고). GUI에 전용 안내와 재시작
   버튼이 뜨니 원인(펜/브러쉬 위치)을 확인한 뒤 눌러주세요.

---

## 6. 터미널에서 직접 그리기

GUI 없이 SVG 한 장만 빠르게 그려보고 싶을 때:

```bash
source /opt/ros/humble/setup.bash
source ~/ws_cobot_pjt/ws_dsr/install/setup.bash
python3 ~/ws_cobot_pjt/ws_dsr/src/svg_drawing/scripts/lower_to_paper.py --svg samples/merkaba.svg
```

- `--surface-z`(기본 9.5mm)가 이미 알려진 값이라, 실행하면 대화형 하강 없이 바로 그 높이를
  신뢰하고 준비자세에서 "그릴까요? (y/N)"만 확인한 뒤 그립니다.
- 표면 높이가 바뀌었다면 `--no-auto-z`로 예전처럼 키보드로 눈으로 잡는 대화형 모드를
  쓸 수 있습니다(`Enter`=하강, `u`=상승, `z<값>`=그 Z로 점프, `done`=확정, `q`=취소).

전체 옵션: `python3 scripts/lower_to_paper.py --help`

---

## 7. 그리기 파이프라인 상세 사양

현재(2026-07-29) `lower_to_paper.py` 기본값 기준입니다. 실기 튜닝값이니 함부로 크게
바꾸지 말고, 바꿀 땐 한 파라미터씩 검증하세요.

### 7-1. 좌표·크기

| 파라미터 | 값 |
|---|---|
| 도안 크기(`--size`) | 100.75mm |
| 회전(`--rotate-deg`) | 90° |
| 오프셋(`--off-x` / `--off-y`) | 0.0mm / -10.0mm |
| 표면 Z(`--surface-z`) | 9.2mm |
| 점 샘플 간격 | 2.0mm |

### 7-2. TCP 안전 가드

- 사용 툴: `pen`, 오프셋 약 **289mm**(RG2 그리퍼 + 펜 길이).
- 컨트롤러 재부팅 시 TCP가 플랜지(0mm)로 리셋되는 경우가 있어, 실행 직전
  `verify_pen_tcp()`가 실측 오프셋을 확인하고 289mm±20mm를 벗어나면 중단합니다.

### 7-3. 힘제어 (하이브리드 위치/힘 + 좌우 그라디언트)

XY는 위치제어(강성 3000, 도형 정확도), Z만 힘제어(표면 추종).

| 파라미터 | 값 | 비고 |
|---|---|---|
| 목표 힘(`--force-n`, 그라디언트 끈 경우) | 6.0N | |
| 좌우 힘 그라디언트(`--force-split`) | 기본 **켬** | 도안을 로봇이 보는 방향 기준 좌/우로 힘을 다르게 |
| 왼쪽 힘(`--force-n-left`) | **7.0N** (Base +Y 쪽) | |
| 오른쪽 힘(`--force-n-right`) | **5.0N** (Base -Y 쪽) | |
| Z축 강성(`--stiffness-z`) | **10** | 5까지 낮췄을 때 불안정했던 이력 있음 — 실기에서 튀면 20~30으로 |
| XY·회전 강성 | 3000(고정) | 회전도 3000으로 딱딱하게: 긴 펜(289mm) 지렛대 효과로 인한 팁 흔들림 억제 |
| 힘 램프 대기(`--force-ramp-wait`) | 2.0초 | 힘제어 ON 후 목표힘 안정될 때까지 그리기 전 대기 |
| DRL 내부 힘 램프 시간 | 0.1초 | 너무 짧으면 오버슈트 위험 |
| 접촉(아크릴 유무) 판정 임계값 | 4.0N | 최초 획에서만 검사, 미검출 시 자동 중단+원위치 |

**좌우 그라디언트 동작 방식**: 딱 자르지 않고 도안 폭 전체에 걸쳐 오른쪽→왼쪽 힘으로
선형 보간됩니다. 획 시작 시 컴플라이언스 모드는 한 번만 켜고, 이후로는 목표힘만
갱신하는 가벼운 호출(`_update_desired_force`)로 매 점마다 부드럽게 바꿉니다 —
처음엔 경계에서 컴플라이언스 모드 자체를 재설정했다가 진행 중이던 이동과 얽혀
**에러 없이 멈추는 문제**가 있었고, 지금 방식으로 바꿔 해결했습니다.

### 7-4. 그리기 속도·가속도·블렌드

| 파라미터 | 값 |
|---|---|
| 그리기 속도(힘제어) | 12.68mm/s |
| 그리기 가속도(힘제어) | 50.26mm/s² |
| 이동(펜업) 속도/가속도 | 51.0mm/s / 255.0mm/s² |
| 기본 블렌드 반경 | 0.8mm(진짜 코너용) |
| 최대 블렌드 반경(완만한 곡선) | 4.0mm |
| 코너 판정 각도 | 25° 이상이면 "진짜 코너"로 좁게 유지 |
| RDP 점 단순화 허용오차 | 0.15mm |
| 획 연장 비율 | 1.5%(마지막 진행 방향으로 직선 연장) |
| 시작/끝 슬로우존 | 각 6mm(거리 기준, 정확한 mm 경계에 보간점 삽입), 34% 속도 |

**곡선이 느린 이유와 해결**: 곡선은 촘촘한 점마다 계속 꺾여 매번 감속·재가속을
반복해서 느립니다. RDP로 불필요한 중간점을 없애 세그먼트를 길게 만들고, 완만한
지점은 블렌드 반경을 키워(최대 4mm) 더 빠르게 코너를 통과하되, 진짜 뾰족한
꼭짓점(25° 이상)은 0.8mm로 좁게 유지해 도형이 뭉개지지 않게 했습니다.

**슬로우존이 정확한 mm인 이유**: 점 개수만 세면 RDP로 세그먼트가 길어졌을 때 목표
거리를 훌쩍 넘는 경우가 있어서, 목표 거리 지점에 보간점을 미리 삽입해 항상 정확한
물리적 길이만큼만 감속하도록 만들었습니다.

### 7-5. 그리퍼(OnRobot RG2) — DO 신호

신호 방식: Doosan 디지털 출력(DO1~DO5) → OnRobot WebLogic 룰 매핑
(`http://192.168.1.1/#/weblogic`).

| DO 신호 | 결과 |
|---|---|
| DO1=1 | 96mm(열림) |
| DO2=1 | 0mm(파지) |
| DO3=1 | 40mm |
| DO1+DO2 동시=1(rule#4) | 5mm — DO4·DO5 미배선이라 이 조합으로 대체 |

파지 시 신호 순서(DO1/3/4 먼저 끄고 DO2 마지막에 켜기)가 중요합니다 — 반대 순서면
순간적으로 5mm 룰이 잘못 걸려 간헐적으로 오동작합니다. `set_digital_output` 반환값도
확인해 실패 시 재시도합니다(`_do()` 래퍼).

| grab 단계 | 대기시간 |
|---|---|
| 파지 후(들어올리기 전) | 2.5초 |
| 놓기 전 | 1.0초 |
| 놓은 후 | 5.0초 |

### 7-6. 그리퍼 파지 검증 (Modbus)

DO 신호만으로는 "닫으라고 명령했다"만 알 수 있지, 실제로 펜/브러쉬를 물었는지는
알 수 없습니다(닫기 명령을 보내면 뭘 물었든 안 물었든 명령값은 똑같음). 그래서
그리퍼(OnRobot Compute Box)의 **Modbus TCP**(`192.168.1.1:502`, device_id=65)에
직접 접속해 실측값을 읽습니다.

| 항목 | 값 |
|---|---|
| 사용 레지스터 | holding reg **275** |
| 빈 상태(아무것도 안 물림) | ≈5 |
| 펜을 물었을 때(실측) | ≈200 |
| 브러쉬를 물었을 때(실측) | ≈254 |
| 판정 임계값(`PEN_GRASP_MIN_REG`) | **80** |

pen_up/brush가 파지한 직후 이 값을 확인해서, 80 미만이면 "못 집었다"고 판단 →
그리퍼를 열고 준비자세로 자동 복귀 + `PenGraspError` 발생 → GUI에 전용 안내와
재시작 버튼 표시. Modbus 응답 자체가 없으면(네트워크 문제 등) 판단을 포기하고
그냥 진행합니다(그리퍼 이상만으로 매번 멈추는 게 더 나쁘다고 판단).

필요 패키지: `pip install pymodbus`

---

## 8. 샘플 도안 (`samples/`)

| 파일 | 획 수 | 설명 |
|---|---|---|
| `merkaba.svg` | 5 | 별사면체(메르카바) — 정삼각형 2개 + 안쪽 사면체, 좌우대칭 정확히 검증됨 |
| `hex_spiral.svg` | 4 | 위로 꼭짓점 있는(pointy-top) 육각형만 남긴 버전(회전 30/90/150/210°, 0.75배씩 축소) |
| `hex_spiral_full.svg` | 44 | hex_spiral의 최초 원본(30개 전 층 포함) 버전, 보존용 |
| `square.svg` | - | 기본 동작 검증용 사각형 |
| `tiger3*.svg` | - | 초기 개발용 호랑이 도안(벡터화·서명·회전 버전) |

안 쓰는 초기 개발용 샘플(mandala, octagon, entj_star, tiger3 이전 버전 등)과 구버전
스크립트(`make_spiral.py`, `lower_to_paper_초기_*.py`)는 정리되어 삭제되었습니다.

GUI 인트로 화면의 "샘플: 사각형 / hex_spiral" 버튼이 이 파일들을 직접 참조합니다.
내 SVG를 추가하려면 `samples/`에 넣고 `--svg` 옵션(터미널) 또는
`gui_bridge_server.py`의 `SAMPLE_SVGS` 딕셔너리(GUI 버튼)에 경로를 등록하면 됩니다.

---

## 9. 문제 해결 (FAQ)

**Q. GUI에서 버튼을 눌러도 반응이 없어요**
→ 터미널 B(브릿지 서버)가 켜져 있는지 확인. 브라우저에서
`http://127.0.0.1:8787/health`가 `{"status":"ok"}`를 안 주면 서버부터 켤 것.

**Q. `Cannot use import statement outside a module` 에러가 떠요**
→ GUI는 번들러 없이 브라우저에서 즉석 변환 후 실행하는 방식이라 jsx 소스에
`import`/`export` 문이 있으면 안 됩니다. `PersonalitySignature_spiral.jsx` 최상단이
`const { useState, ... } = React;`로, 맨 끝 컴포넌트 정의가 `function
PersonalitySignature() {`(export 없이)로 되어 있는지 확인하세요.

**Q. `The passed service type is invalid` / import 에러 (터미널)**
→ 그 터미널에서 ROS2 소싱 2줄을 안 한 것입니다. 새 터미널마다 항상:
```bash
source /opt/ros/humble/setup.bash
source ~/ws_cobot_pjt/ws_dsr/install/setup.bash
```

**Q. 그리퍼가 가끔 아크릴을 못 잡아요**
→ DO 신호 순서/대기시간 문제였던 이력이 있습니다(이미 수정됨 — `drl_motions.py`의
`_grab_grasp()` 참고). 여전히 발생하면 파지 후 대기(현재 2.5초)를 더 늘려보세요.

**Q. 펜/브러쉬를 못 집었다는 메시지가 떠요**
→ [7-6](#7-6-그리퍼-파지-검증-modbus)의 Modbus 파지 검증이 작동한 것입니다. 펜/브러쉬가
제자리에 있는지 확인하고 GUI의 [재시작] 버튼을 누르세요. 브러쉬 실패는 그리기를 다시
안 하고 brush→grab만 이어서 재개합니다. `pymodbus`가 설치돼 있어야 이 기능이 동작하고,
없으면(또는 그리퍼 네트워크 응답이 없으면) 검증을 건너뛰고 그냥 진행합니다.

**Q. 그리다가 에러 없이 갑자기 멈춰요**
→ 힘제어 관련 컴플라이언스 모드를 그리기 도중(움직이는 중간에) 다시 설정하면 진행 중인
이동 대기열과 얽혀 멈추는 현상이 있었습니다(좌우 힘 그라디언트 개발 중 발견). 지금은
모드는 획 시작 시 한 번만 켜고 이후로는 목표힘만 갱신하도록 고쳐져 있습니다 — 혹시 이
증상이 다시 보이면 그리기 도중 컴플라이언스 관련 함수(`_task_compliance_ctrl`,
`_set_stiffnessx`)를 호출하는 코드가 새로 들어간 게 없는지 확인하세요.

**Q. 곡선이 직선보다 훨씬 느려요**
→ 블렌드 반경이 작을수록 코너 감속이 커지는 구조적 특성입니다. [7-4](#7-4-그리기-속도가속도블렌드)의
적응형 블렌드가 이미 완화하고 있지만, 여전히 느리면 `draw_blend_radius_max_mm`을
올려보세요(`svg_drawing/robot_controller.py`, 코너가 부풀면 다시 낮출 것).

**Q. 로봇이 표면에 안 닿거나 너무 세게 눌러요**
→ `--surface-z` 값이 실제 표면과 다를 수 있습니다. `--no-auto-z`로 대화형 모드를 켜서
키보드로 다시 표면을 잡으세요.

**Q. TCP 검증 경고가 떠요**
→ 컨트롤러 재부팅 등으로 활성 TCP가 `pen`(289mm)에서 플랜지(0mm)로 바뀐 것입니다.
펜던트에서 TCP를 `pen`으로 다시 선택하세요. 하드코딩된 좌표로 그대로 움직이면 충돌
위험이 있어 자동 중단하도록 되어 있습니다.

**Q. 다른 컴퓨터 브라우저에서 GUI를 열었더니 로봇 연동 버튼이 안 돼요**
→ 브릿지 서버는 `127.0.0.1`(같은 컴퓨터) 전용입니다. **로봇을 제어하는 바로 그
컴퓨터에서** GUI를 열어야 합니다.

---

## 10. 개발 참고

- `scripts/`의 파일들은 `svg_drawing` 패키지 밖의 독립 스크립트라 **colcon 빌드가
  필요 없습니다**(수정 후 바로 `python3 scripts/파일명.py`). `svg_drawing/` 패키지
  내부 모듈(`robot_controller.py` 등)도 `scripts/`와 같은 상위 폴더에서 실행하면 상대
  경로 import로 소스가 바로 반영되어 마찬가지로 빌드가 필요 없습니다.
- 각 모듈 단독 테스트:
  ```bash
  python3 svg_drawing/coordinate_mapper.py     # SVG→mm 매핑 검증
  python3 svg_drawing/trajectory_planner.py    # 획 순서 최적화 검증
  python3 svg_drawing/robot_controller.py      # 좌표변환·통계 검증(dry-run)
  python3 svg_drawing/bezier_sampler.py        # 샘플링/RDP 단순화 검증
  ```
- 로봇 IP `192.168.1.100`, 그리퍼(WebLogic) IP `192.168.1.1` — 컴퓨터/로봇 조합이
  다르면 `ros2 launch` 명령의 `host:=` 값을 바꾸세요.
- ROS2 서비스 방식(`drawing.launch.py` + `/dsr01/draw_svg`)도 `svg_drawing_interfaces`에
  정의돼 있지만, 실사용은 위 GUI/스크립트 경로가 표준입니다.
- 상세 변경 이력(문제 상황·원인·해결)은 [`CHANGELOG_2026-07-28.md`](CHANGELOG_2026-07-28.md),
  이전 이력은 [`CHANGELOG_2026-07-23.md`](CHANGELOG_2026-07-23.md) 참고. 좌우 힘 그라디언트·
  Modbus 파지 검증 등 이후 변경사항은 이 README와 `git log`가 최신 기준입니다.
