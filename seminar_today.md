# 오늘 실습 — 팀별 근접 운전 미션

**환경**
- 플랫샛 서버 IP: **`220.67.219.55`** (학교 백본 직접 접근 가능)
- rosbridge WebSocket: TCP 9090
- web_video_server: TCP 8080
- 학생 노트북: ROS 2 불필요, **Python + roslibpy 만**으로 동작

**시뮬레이션**
- 플랫샛 Gazebo + `mission.sdf` 상시 실행 (교수님 or 조교가 기동)
- chief: 모델 `chief` (`intel_sat_dummy` mesh 사용) 원점 고정, SSO 545 km 궤도의 LVLH 원점
- deputy 2대: 동일한 100 kg 위성, 외관/센서 구성 완전 통일
  - `deputy_formation` 초기 위치 `(0, +5000, 0)` m
  - `deputy_docking`  초기 위치 `(0, −5000, 0)` m

---

## 팀 편성 (각 팀 4명)

| 팀 | 목표 | 임무 이름 |
|---|---|---|
| **Team Formation** | chief 주변 **~50 m 편대 궤도**로 이동 후 사진 6장 확보 | **GCO Watcher** |
| **Team Docking** | **5 km → 1 m** 근접 도킹 접근 | **Final Approach** |

각 팀 내 역할:
| 역할 | 책임 | 짝 스크립트 / 가이드 |
|---|---|---|
| **ADCS** | 자세 결정·제어 (ST + IMU → RW) | `attitude_controller.py` / [`adcs_practice.md`](adcs_practice.md) |
| **ODCS** | 궤도 결정·제어 (GPS + TLE → Thruster) | `orbit_controller.py` / [`odcs_practice.md`](odcs_practice.md) |
| **Vision** | 카메라 관측·캡처, 포인팅 피드백 | `vision_operator.py` / [`vision_practice.md`](vision_practice.md) |
| **Navigation** | 센서 융합·CW 전파·건전성 모니터 | `navigation.py` / [`navigation_practice.md`](navigation_practice.md) |

---

## 실습 타임라인 (가이드, 즉석 조정 가능)

| 분 | 단계 | 공통 | Formation | Docking |
|---|---|---|---|---|
| 0–5 | 접속 확인 | 각자 브라우저로 `http://220.67.219.55:8080/` 열기, `curl` 또는 `Test-NetConnection` 으로 9090 확인 | | |
| 5–15 | 센서 관찰 | 네 개 스캐폴드 그냥 실행해서 센서값 해석 | | |
| 15–30 | 기본 제어 루프 | ADCS: P-only → PD; ODCS: 거리별 throttle 전략; Vision: 카메라 관측 시작 | 초기 위치 유지 | 초기 위치 유지 |
| 30–45 | 기동 시작 | Navigation 이 단계 결정 브리핑 | `fy_minus` V-bar 접근 (→ chief) | `fy_plus` V-bar 접근 (→ chief) |
| 45–60 | **교수님 방해 (SOFT)** | ADCS/ODCS 가 외란 흡수 | 랜덤 토크 | 랜덤 추력 |
| 60–75 | 근접 단계 | Vision ↔ ADCS 폐루프 (chief 포인팅) | 50 m 편대 주입 | 브레이크 burn 연습 |
| 75–85 | **교수님 방해 (HARD)** | Navigation 이 감지 → Vision 재탐색 | Chief 텔레포트 | Actuator jam (rw/z) |
| 85–90 | 디브리핑 | 각 팀 발표: 어디서 막혔고 어떻게 풀었는지 | 사진 6장 제시 | 최종 거리/속도 공개 |

---

## 성공 기준 (즉석 확정, 초기 제안치)

### Team Formation — GCO Watcher
- [ ] chief 기준 거리 **40–60 m** 유지 (±20 m 여유) ≥ 2 분
- [ ] 카메라로 chief 관측 사진 **서로 다른 각도 6장** 확보
- [ ] 교수님 SOFT 외란 흡수 후 원상 복귀 30 초 이내

### Team Docking — Final Approach
- [ ] 최종 거리 **≤ 5 m** 도달
- [ ] 접근 속도 **≤ 0.1 m/s** 유지
- [ ] 충돌 없음 (거리 < 0.5 m 무시)
- [ ] 교수님 HARD 외란 후 30초 내 재획득

구체 수치는 시뮬 중 팀 평균 능력 보고 교수님이 조정.

---

## 도구 치트시트

### 서버 상태 확인 (교수/조교 전용)
```bash
# 미션 기동
ros2 launch gz_cw_dynamics mission.launch.py            # GUI
ros2 launch gz_cw_dynamics mission.launch.py headless:=true

# 상태 점검
ps -eo pid,cmd | grep -E 'gz sim|rosbridge|web_video'
ss -tlnp | grep -E ':9090|:8080'
ros2 topic list | head -20

# 위성 위치 즉시 조회
gz model -m deputy_formation --pose
gz model -m deputy_docking --pose
gz model -m chief --pose

# 긴급 정리
bash ~/Controla_ROS2_lec/kill_sim.sh
# 또는 WSLg 오류 시 Windows PS:  wsl --shutdown
```

### 학생 기본 명령 (노트북 공통)
```bash
# 설치 (1회)
pip3 install roslibpy --break-system-packages
git clone https://github.com/ndh8205/Controla_ROS2_lec.git ~/orbit_sim
cd ~/orbit_sim

# 완성 예제 (한 줄 테스트)
python3 student/completed/laptop_monitor.py  --host 220.67.219.55 --deputy deputy_formation
python3 student/completed/laptop_thruster.py --host 220.67.219.55 --deputy deputy_docking --axis fy_plus --throttle 1.0 --duration 2
python3 student/completed/laptop_rw.py       --host 220.67.219.55 --deputy deputy_formation --axis z --torque 0.1 --duration 5

# 역할별 scaffold
python3 student/attitude_controller.py --host 220.67.219.55 --deputy deputy_formation
python3 student/orbit_controller.py    --host 220.67.219.55 --deputy deputy_docking
python3 student/vision_operator.py     --host 220.67.219.55 --deputy deputy_formation
python3 student/navigation.py          --host 220.67.219.55 --deputy deputy_docking
```

### 카메라 URL (브라우저)
```
http://220.67.219.55:8080/                                                           # 전체 목록
http://220.67.219.55:8080/stream_viewer?topic=/nasa_satellite/camera&type=mjpeg      # Formation 탑재
http://220.67.219.55:8080/stream_viewer?topic=/nasa_satellite2/camera&type=mjpeg     # Docking 탑재
http://220.67.219.55:8080/stream_viewer?topic=/observer/chief/camera&type=mjpeg      # Chief 외부 (정적)
http://220.67.219.55:8080/stream_viewer?topic=/observer/formation/camera&type=mjpeg  # Formation 외부 (정적)
http://220.67.219.55:8080/stream_viewer?topic=/observer/docking/camera&type=mjpeg    # Docking 외부 (정적)
http://220.67.219.55:8080/stream_viewer?topic=/chase/formation/camera&type=mjpeg     # Formation chase (body-rigid follower)
http://220.67.219.55:8080/stream_viewer?topic=/chase/docking/camera&type=mjpeg       # Docking chase (body-rigid follower)
```

### 교수님 방해 도구 → `professor/README.md` 참조

---

## 토픽 충돌 주의 (같은 팀 내 같은 토픽에 여러 학생이 publish 하면 안 됨)

역할 분담 원칙 — **절대 교차하지 말 것**:

| 토픽 prefix | **pub 권한** | sub 누구나 |
|---|---|---|
| `/deputy_*/rw/{x,y,z}/cmd` | **ADCS 만** | ADCS, Vision (폐루프 협력 시) |
| `/deputy_*/thruster/{*}/cmd` | **ODCS 만** | ODCS, Navigation (감지용) |
| `/deputy_*/imu/data` | (plugin) | 누구나 |
| `/deputy_*/gps/odometry` | (plugin) | 누구나 |
| `/deputy_*/star_tracker/attitude` | (plugin) | 누구나 |
| `/chief/eci_state` | (propagator) | 누구나 |
| `/chief/eci_truth` | (propagator) | 누구나 (TLE 편의 검증용) |
| `/chief/sun_vector_lvlh` | (propagator) | 누구나 |

Vision 이 "자동 중앙 정렬" 시도할 때 RW 에 직접 쓰면 ADCS 와 충돌. 이때는 Vision 이 bearing 만 계산해서 ADCS 에 **값 전달**, 실제 명령은 ADCS 가 발행.

---

## 트러블슈팅 체크리스트

| 증상 | 확인 순서 |
|---|---|
| 센서값 수신 안 됨 | 1. `curl http://220.67.219.55:8080/` HTTP 200? → 2. `Test-NetConnection ... 9090`? → 3. `--host` 오타? |
| 카메라 화면 까맣게 | 거리 ≥ 1 km 면 보이기 힘들어. `/observer/chief/camera` 로 바꿔 확인 |
| RW 토크 받아도 안 돎 | 같은 토픽에 다른 팀원이 0 덮어쓰는 중일 수 있음 (stop race). `ros2 topic info --verbose /deputy_*/rw/z/cmd` |
| 거리 수치 ±3 km 진동 | GPS-TLE 비동기. Navigation 팀이 Coriolis 보정 + 스무딩 구현 |
| 브라우저 프리즈 | 10명 동시 접속이면 대역폭 한계. Vision 만 직접 시청, 나머지는 Navigation 요약 받기 |
| WSL GUI 까맣게 | `wsl --shutdown` (관리자 PS) 후 재접속 — [`lessons_learned.md`](lessons_learned.md) 교훈 #2 |

---

## 세미나 후 자체 점검

디브리핑에서 팀별로 답할 것:
- 작업 중 **가장 시간 많이 쓴 곳**?
- 교수님 외란 중 **가장 대응하기 어려웠던 것**?
- 역할 4개 중 **가장 협업이 필요했던 조합**?
- 만약 시뮬레이터가 **더 사실적 (e.g. 연료 제한, 휠 포화)** 이면 우리 전략 어디가 망가질까?

피드백은 `lessons_learned.md` 에 추가 권장.

---

## 실습 후 정리 (교수/조교)

- `~/Controla_ROS2_lec/kill_sim.sh` 로 프로세스 전체 정리
- 각 팀이 저장한 로그/캡처 수집 (위치는 팀별 노트북)
- `lessons_learned.md` 갱신
