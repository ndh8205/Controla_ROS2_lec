# 교수용 실습 조종·방해 도구

학생 팀이 작성한 ADCS/ODCS/Vision/Navigation 을 **교수님 노트북에서 실시간으로 괴롭히기**.

두 가지 도구:
- **`disturb_gui.py`** — tkinter GUI, **실시간 직접 조종** (thruster / RW / TLE noise / camera)
- **`disturb.py`** — CLI, **타이머 기반 자동 외란** (랜덤 토크 30초 같은 시나리오)

둘 다 **교수님 노트북에서 실행 가능** — rosbridge(ws://220.67.219.55:9090) 경유로 서버에 접속. 서버 쪽 설정·재시작 불필요.

---

## 설치 (교수님 노트북, 1회)

```bash
pip3 install roslibpy --break-system-packages

# Linux/WSL 의 경우 tkinter:
sudo apt install -y python3-tk

# Windows 파이썬: tkinter 기본 포함. 추가 설치 불필요.

git clone https://github.com/ndh8205/Controla_ROS2_lec.git ~/orbit_sim
cd ~/orbit_sim/professor
```

---

## 1. `disturb_gui.py` — 실시간 직접 조종 (메인)

```bash
python3 disturb_gui.py --host 220.67.219.55        # 플랫샛 원격
python3 disturb_gui.py --host localhost            # 서버 자체에서
```

실행 시 아래 창이 뜬다:

```
┌─ Target deputy ──────────────────────────────┐
│  (•) deputy_formation   ( ) deputy_docking   │
└──────────────────────────────────────────────┘
┌─ Thrusters  (hold to fire) ──────────────────┐
│  throttle: [==========]  0.50                │
│  [fx+][fx-][fy+][fy-][fz+][fz-]              │
└──────────────────────────────────────────────┘
┌─ Reaction Wheels  (hold to apply) ───────────┐
│  torque N·m: [=======]  +0.050               │
│  [rw/x]  [rw/y]  [rw/z]                      │
└──────────────────────────────────────────────┘
┌─ Chief TLE 노이즈 폭격 ──────────────────────┐
│  pos σ (m):   [====]  500                    │
│  vel σ (m/s): [===]   0.5                    │
│  [ TLE noise: OFF ]                          │
└──────────────────────────────────────────────┘
┌─ Camera 블랙 프레임 주입 ────────────────────┐
│  topic: [/nasa_satellite/camera        v]    │
│  rate (Hz): [===]  3                         │
│  [ Camera inject: OFF ]                      │
└──────────────────────────────────────────────┘
┌─ Emergency ──────────────────────────────────┐
│    [ STOP ALL ACTUATORS ]                    │
└──────────────────────────────────────────────┘
┌─ Log ────────────────────────────────────────┐
│  14:32:10 FIRE /deputy_formation/thr/fy+ @0.5│
│  ...                                          │
└──────────────────────────────────────────────┘
```

### 조작

| 위젯 | 동작 |
|---|---|
| **Thruster 버튼** | **마우스 누르고 있는 동안** 분사, 떼면 정지. slider 로 throttle 조절. |
| **RW 버튼** | 마우스 누르면 해당 축 토크 인가, 떼면 0 토크. slider 로 +/- 방향·크기. |
| **TLE noise 토글** | GUI 가 `/chief/eci_state` 구독한 실측값에 σ 만큼 가우시안 덧붙여 같은 토픽에 고속 재발행. 학생 GPS/Navigation 이 변동 큰 chief 값을 보게 됨. |
| **Camera inject 토글** | 선택 카메라 토픽에 **640×480 블랙 RGB 프레임** 주입. 진짜 카메라 프레임과 interleave → 학생 영상 스트림이 깜빡이거나 검은 프레임 섞임. |
| **STOP ALL** | 두 deputy × 6 추력기 × 3 RW 전부 0. noise/camera 도 OFF. |

### 활용 예시 (세미나 중)

| 시점 | 조작 | 학습 효과 |
|---|---|---|
| 팀이 PD 자세제어 튜닝 중 | RW 버튼 몇 초 누름 | 외란 들어와도 PD 가 잡는지 확인 |
| Vision 이 카메라 정렬 성공 | Camera inject ON | Vision 이 블랙프레임 처리/알림 할 수 있는지 |
| Navigation 이 TLE 기반 예측 안정 | TLE σ 2000 m 으로 올린 뒤 ON | TLE 불신 감지 로직 / 필터 강화 필요성 학습 |
| ODCS 가 브레이크 burn 근처 | 반대방향 추력기 몇 초 | overshoot 대응 |
| 도킹 팀 최종 근접 | 작은 RW torque + 작은 추력 동시 | 자세-궤도 커플링 대응 |

### 주의

- GUI 가 publish 하는 모든 명령은 학생 publisher 와 **race 관계**. 학생 쪽 명령과 번갈아 덮어쓰기됨. 학생이 과제로 "교수 외란과 공존" 하는 제어를 구현해야 함.
- TLE noise mode 는 **서버 쪽 chief_propagator 원본은 그대로** 둠. GUI 의 가짜 메시지가 구독자 쪽에서 interleave.
- Camera inject 는 JPEG 가 아닌 **raw rgb8 640×480**. 네트워크 부하 1–3 MB/s (해상도·Hz 비례). 학생 브라우저가 1–2 Hz 로 블랙 프레임 받게 됨.
- Ctrl+C 나 창 닫기 → 자동 `STOP ALL` 호출 후 종료.

---

## 2. `disturb.py` — 자동 시나리오 (보조)

고정 시간 동안 자동 외란. GUI 로 일일이 누르기 싫을 때 or 리허설 체크리스트용.

```bash
python3 disturb.py --help
```

### 모드

| mode | 효과 |
|---|---|
| `random-torque` | 3–5 초마다 랜덤 축에 ±amp N·m 토크 |
| `random-thrust` | 5–10 초 간격, 0.5–1.5 초 짧은 랜덤 추력 burst |
| `actuator-jam` | 지정 토픽에 0 을 고속 발행해 학생 명령 무력화 |

### 예시

```bash
# 자세제어 연습: 1분간 랜덤 토크
python3 disturb.py --host 220.67.219.55 \
    --mode random-torque --target deputy_formation --duration 60 --amplitude 0.05

# 궤도제어 연습: 30초간 랜덤 추력
python3 disturb.py --host 220.67.219.55 \
    --mode random-thrust --target deputy_docking --duration 30

# yaw 축만 30초 간섭 (다른 축 살아있음)
python3 disturb.py --host 220.67.219.55 \
    --mode actuator-jam --target deputy_formation --topic rw/z --duration 30 --rate 50
```

모든 모드 Ctrl+C 로 안전 종료 (자동 stop_all).

---

## 디자인 원칙

- **학생 위성에만 영향** — chief 모델, chief_propagator 내부, 시뮬레이션 물리 엔진은 건드리지 않음. 교육적으로 "학생이 작성한 딥ute 제어 코드가 얼마나 강인한가" 를 테스트.
- **서버 설정 불필요** — 모든 외란은 rosbridge 경유 publish. 서버 재시작 / 코드 수정 없음. 학생과 동일 경로로 접근해 "교수도 학생과 같은 권한" 시뮬.
- **동시 여러 외란 가능** — GUI 는 actuator hold + TLE noise + camera inject 동시 활성화. 스트레스 테스트.
- **언제든 STOP ALL** — 한 버튼으로 전부 0, 학생이 정상 상태에서 디버그 계속 가능.

## 디렉토리 내용

```
professor/
├── disturb_gui.py   # tkinter GUI (메인)
├── disturb.py       # CLI 자동 외란 (보조)
└── README.md        # 이 파일
```
