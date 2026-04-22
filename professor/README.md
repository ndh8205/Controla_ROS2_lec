# 교수용 실습 제어 도구

학생 팀이 작성한 ADCS/ODCS/Vision/Navigation 이 **실제 상황에서 얼마나 강인한지** 테스트하기 위한 외란 주입 도구.

## 설치

서버(플랫샛)에서 이미 `roslibpy` 사용 가능한 환경이면 별도 설치 없음. 다른 곳에서 쓰려면:
```bash
pip3 install roslibpy --break-system-packages
```

## 사용 흐름 (예시 45분 세미나)

### 0. 리허설 (학생들 작업 중, 교수 터미널)
```bash
cd ~/Controla_ROS2_lec
# 수치 튜닝 단계엔 방해 없이 대기
```

### 1. SOFT 단계 (15–25분차, 팀이 기본 제어 수렴했을 때)

**랜덤 토크 외란 (자세제어 테스트)**
```bash
python3 professor/disturb.py --mode random-torque --target deputy_formation \
    --duration 90 --amplitude 0.05
```
- 3–5 초마다 랜덤 축에 ±0.05 N·m 토크 주입
- ADCS 팀이 PD 제어로 흡수해야 함
- amplitude 를 올려가며 ADCS 의 수렴 한계 테스트

**랜덤 추력 외란 (궤도제어 테스트)**
```bash
python3 professor/disturb.py --mode random-thrust --target deputy_docking \
    --duration 60
```
- 5–10 초 간격, 0.5–1.5 초 burst
- ODCS 팀이 감지 후 보상 burn 필요

### 2. HARD 단계 (30분차 이후, 팀이 자만할 때쯤)

**Chief 텔레포트 (TLE 신뢰 무너뜨리기)**
```bash
python3 professor/disturb.py --mode teleport-chief --offset 300 200 50
```
- Chief 위치가 순간 이동 → TLE 추정치와 실제 크게 차이
- Navigation 팀의 TLE 건전성 모니터가 감지해야 함
- Vision 팀이 카메라로 재탐색 필요
- ⚠ **이 모드는 서버 쪽 쉘에서 직접 `gz service` 호출 필요** — 스크립트가 정확한 명령을 출력해주니 복붙.

**액추에이터 간섭 (통신 교란 시나리오)**
```bash
# rw/z 토픽을 0 으로 계속 덮어씀 → ADCS 의 yaw 제어 무력화
python3 professor/disturb.py --mode actuator-jam --target deputy_formation \
    --topic rw/z --duration 30 --rate 50
```
- 학생의 명령이 50 Hz 로 덮어써지는 0 때문에 무시됨
- 팀이 토픽 충돌 개념을 이해하는지 관찰
- 다른 축은 살아있으니 대체 제어 가능

## 팁

### 페어 외란 (두 팀 동시 테스트)
두 터미널에서 각 팀에 다른 외란:
```bash
# Terminal A
python3 professor/disturb.py --mode random-torque --target deputy_formation &

# Terminal B
python3 professor/disturb.py --mode random-thrust --target deputy_docking &
```

### 점진적 강도 증가
```bash
for AMP in 0.02 0.04 0.06 0.08 0.10; do
    echo "====== amplitude $AMP ======"
    python3 professor/disturb.py --mode random-torque \
        --target deputy_formation --duration 30 --amplitude $AMP
    sleep 10   # 팀 복구 대기
done
```

### 긴급 정지 (Ctrl+C)
`Ctrl+C` 누르면 자동으로 `rw/*` 과 `thruster/*` 모든 토픽에 0 발행해서 외란 즉시 중지.

## 모드 레퍼런스

| mode | 대상 | 주요 인자 | 효과 |
|---|---|---|---|
| `random-torque` | 1 deputy | `--amplitude` | RW 축에 랜덤 토크, 자세 교란 |
| `random-thrust` | 1 deputy | — | 랜덤 방향 추력, 궤도 교란 |
| `teleport-chief` | chief (만 물리 이동) | `--offset Δx Δy Δz` | Chief 위치 순간이동 (gz service 필요) |
| `actuator-jam` | 1 deputy 1 topic | `--topic`, `--rate` | 지정 토픽 덮어쓰기 |

## 디자인 노트

- **rosbridge 경유** — 학생과 동일한 경로라서 "교수는 추가 권한 없음" 시연 가능.
- **teleport-chief 만 gz service** — 이건 rosbridge 가 노출 안 하는 gz transport 영역. 서버 쉘 접근 필요.
- 학생 노트북 공유 네트워크에서도 교수 컴퓨터 또는 서버에서 실행 가능.

## 추가 아이디어 (미구현)

- `--mode sensor-noise`: chief_propagator 파라미터를 runtime 에 바꿔서 TLE 노이즈 증폭 (rclpy param set 필요, 별도 작업)
- `--mode power-brownout`: 모든 `rw/*`, `thruster/*` 을 30 초간 0 으로 덮어쓰기 (종합 전력 장애 시뮬)
- `--mode comm-dropout`: `rosbridge_server` 자체를 10 초 죽였다 살리기 (학생 reconnect 로직 테스트)

필요하면 추가 구현.
