#!/usr/bin/env python3
"""probe_gripper_modbus.py — OnRobot RG2 Compute Box(192.168.1.1)가 Modbus TCP로
현재 그리퍼 폭(width)을 직접 읽어줄 수 있는지 확인하는 진단 스크립트.

이게 되면 Doosan 컨트롤러 DI/AI 배선과 무관하게, 이 스크립트를 그대로 파이프라인에
넣어서 "펜을 실제로 잡았는지"를 폭 값으로 판단할 수 있다(가장 빠르고 확실한 방법).

사용법:
    pip install pymodbus   # 없으면 먼저 설치
    python3 scripts/probe_gripper_modbus.py

무엇을 하는지:
    1) 192.168.1.1:502 (표준 Modbus TCP 포트) 접속 시도
    2) OnRobot RG2 Compute Box 흔한 레지스터 후보 몇 개를 읽어서 값을 그대로 출력
       (정확한 레지스터 주소는 기기/펌웨어마다 달라 이 스크립트는 "후보들을 훑어서
       그리퍼를 손으로 열었다 닫았다 할 때 값이 바뀌는 레지스터를 찾는" 용도)
    3) 그리퍼를 손으로 다른 폭으로 만들어보면서 이 스크립트를 반복 실행 →
       값이 폭에 따라 바뀌는 레지스터를 찾으면 그게 width 레지스터

주의: 이 스크립트는 그리퍼에 아무 명령도 보내지 않는다(READ ONLY, 안전).
"""
import sys

try:
    from pymodbus.client import ModbusTcpClient           # pymodbus 3.x
except ImportError:
    try:
        from pymodbus.client.sync import ModbusTcpClient  # pymodbus 2.x
    except ImportError:
        print("[안내] pymodbus 가 설치되어 있지 않습니다. 설치 후 다시 실행하세요:")
        print("    pip install pymodbus")
        sys.exit(1)

HOST = "192.168.1.1"
PORT = 502

# OnRobot Compute Box 계열에서 흔히 쓰이는 홀딩 레지스터 후보 범위.
# (기기/펌웨어마다 다를 수 있어 "훑어보기" 용도 — 정확한 매핑은 OnRobot 문서/펌웨어 버전 참고)
CANDIDATE_RANGES = [
    (0, 20),      # 상태/폭 관련 레지스터가 앞쪽에 몰려있는 경우가 많음
    (256, 20),    # 일부 OnRobot 장비는 256번대부터 시작
]


def main():
    print(f"[연결시도] {HOST}:{PORT} (Modbus TCP) ...")
    client = ModbusTcpClient(HOST, port=PORT, timeout=3)
    if not client.connect():
        print(f"[실패] {HOST}:{PORT} 에 연결할 수 없습니다.")
        print("  - 이 PC가 로봇/그리퍼와 같은 네트워크에 있는지 확인")
        print("  - Compute Box가 Modbus TCP를 지원 안 할 수도 있음(웹UI(WebLogic)만 제공하는 모델일 수 있음)")
        sys.exit(1)

    print("[성공] 연결됨. 후보 레지스터를 읽어봅니다 — 그리퍼를 손으로 벌렸다 오므렸다"
          " 하면서 이 스크립트를 여러 번 실행해, 값이 바뀌는 레지스터를 찾으세요.\n")

    for start, count in CANDIDATE_RANGES:
        try:
            # Holding Registers(0x03) 기준. Input Registers(0x04)를 쓰는 기기도 있어
            # 여기서 안 잡히면 read_input_registers 로도 시도해보라고 안내.
            # pymodbus 버전마다 키워드 인자명이 달라(count/slave vs unit 등) 순서인자로 통일.
            result = client.read_holding_registers(start, count=count)
            if result.isError():
                print(f"  [{start}~{start+count-1}] holding register 읽기 실패: {result}")
                continue
            print(f"  [holding {start}~{start+count-1}] {result.registers}")
        except Exception as e:
            print(f"  [{start}~{start+count-1}] 예외: {e}")

    print()
    for start, count in CANDIDATE_RANGES:
        try:
            result = client.read_input_registers(start, count=count)
            if result.isError():
                print(f"  [{start}~{start+count-1}] input register 읽기 실패: {result}")
                continue
            print(f"  [input {start}~{start+count-1}] {result.registers}")
        except Exception as e:
            print(f"  [{start}~{start+count-1}] 예외: {e}")

    client.close()
    print("\n[안내] 그리퍼를 손으로 다른 폭(예: 완전히 벌림 vs 완전히 오므림)으로 만든 뒤"
          " 이 스크립트를 다시 실행해서, 값이 폭에 비례해 바뀌는 레지스터 번호를 알려주세요.")


if __name__ == "__main__":
    main()
