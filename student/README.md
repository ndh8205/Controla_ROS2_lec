# 역할별 스타터 코드 (학생용)

노트북에서 `python3 <스크립트>.py` 로 직접 실행합니다.
플랫샛 (192.168.0.54) 의 Gazebo 시뮬레이션에 rosbridge 경유로 연결됩니다.

## 필요 설치 (1회)

```bash
sudo apt install -y python3-roslibpy
# 또는
pip3 install roslibpy --user
```

## 역할 배정

### 팀 1: Formation (50 m GCO → chief 사진)

| 역할 | 파일 | 토픽 (주력) |
|---|---|---|
| **자세 제어** | `attitude_controller.py --deputy deputy_formation` | star_tracker + imu → rw 명령 |
| **궤도 제어** | `orbit_controller.py --deputy deputy_formation` | gps + tle → thruster 명령 |
| **영상 담당** | `vision_operator.py --deputy deputy_formation` | camera (web), gps (거리) |
| **미션 매니저** | 3개 모두 모니터 또는 `laptop_monitor.py --deputy deputy_formation` | 전체 |

### 팀 2: Docking (5 km → 1 m)

| 역할 | 파일 | 토픽 (주력) |
|---|---|---|
| **자세 제어** | `attitude_controller.py --deputy deputy_docking` | star_tracker + imu → rw 명령 |
| **궤도 제어** | `orbit_controller.py --deputy deputy_docking` | gps + tle → thruster 명령 |
| **영상 담당** | `vision_operator.py --deputy deputy_docking` | camera (web), gps (거리) |

## 실행 예시

```bash
# 자세 담당 (노트북에서)
python3 attitude_controller.py --host 192.168.0.54 --deputy deputy_docking

# 궤도 담당 (노트북에서)
python3 orbit_controller.py --host 192.168.0.54 --deputy deputy_docking

# 영상 담당 (노트북에서)
python3 vision_operator.py --host 192.168.0.54 --deputy deputy_docking
```

## 카메라 브라우저 URL

```
http://192.168.0.54:8080/                                                              # 전체 목록

# 탑재 카메라 (deputy 시점)
http://192.168.0.54:8080/stream_viewer?topic=/nasa_satellite/camera&type=mjpeg         # 팀1 탑재
http://192.168.0.54:8080/stream_viewer?topic=/nasa_satellite2/camera&type=mjpeg        # 팀2 탑재

# 옵저버 카메라 (외부 시점 — 위성 모습 확인)
http://192.168.0.54:8080/stream_viewer?topic=/observer/chief/camera&type=mjpeg         # Chief 근접
http://192.168.0.54:8080/stream_viewer?topic=/observer/formation/camera&type=mjpeg     # 팀1 Deputy 근접
http://192.168.0.54:8080/stream_viewer?topic=/observer/docking/camera&type=mjpeg       # 팀2 Deputy 근접
```

## 전체 명령어 모음 (복사용)

### 서버 (플랫샛)
```bash
# 시뮬레이션 시작
bash ~/kill_sim.sh
ros2 launch gz_cw_dynamics mission.launch.py

# 또는 headless (GUI 없이, 카메라 동작)
ros2 launch gz_cw_dynamics mission.launch.py headless:=true
```

### 학생 노트북 — 설치 (1회)
```bash
sudo apt install -y ros-jazzy-rosbridge-suite python3-pip
pip3 install roslibpy --break-system-packages
cd ~/space_ros_ws/src
git clone https://github.com/ndh8205/Controla_ROS2_lec.git orbit_sim
git clone https://github.com/ndh8205/gz_cw_dynamics.git
```

### 학생 노트북 — 완성 예제 (바로 실행)
```bash
# 센서 통합 모니터 (자이로+가속도계+GPS+ST+TLE+Sun+상대거리)
python3 student/completed/laptop_monitor.py --host 192.168.0.54 --deputy deputy_formation
python3 student/completed/laptop_monitor.py --host 192.168.0.54 --deputy deputy_docking

# 추력기 발사
python3 student/completed/laptop_thruster.py --host 192.168.0.54 --deputy deputy_docking --axis fy_plus --throttle 0.5 --duration 2

# 반작용휠 토크
python3 student/completed/laptop_rw.py --host 192.168.0.54 --deputy deputy_docking --axis z --torque 0.002 --duration 1
```

### 학생 노트북 — 역할별 scaffold (TODO 구현)
```bash
# 자세 제어 (ST + 자이로 + 가속도계 → RW)
python3 student/attitude_controller.py --host 192.168.0.54 --deputy deputy_formation

# 궤도 제어 (GPS + TLE + 가속도계 → 추력기)
python3 student/orbit_controller.py --host 192.168.0.54 --deputy deputy_docking

# 영상 (카메라 브라우저 + 거리 모니터)
python3 student/vision_operator.py --host 192.168.0.54 --deputy deputy_formation
```

## 코드 구조

각 파일은 동일 패턴:
1. rosbridge 접속 (`roslibpy.Ros(host, 9090)`)
2. 센서 토픽 구독 (subscribe)
3. 제어 루프 (`while True:`)
4. **`# TODO: 학생이 구현할 부분!`** — 제어 알고리즘을 여기에 넣으세요
5. 종료 시 액추에이터 정지 (KeyboardInterrupt)

## 테스트 (세미나 전 반드시 실행)

### 자동 통합 테스트 (플랫샛에서, 1분 소요)

모든 학생 스크립트가 crash 없이 데이터 수신/발신하는지 한 번에 체크:

```bash
bash student/test_all_student_scripts.sh
```

gz sim (mission) + rosbridge + chief_propagator 자동 기동 → 6개 스크립트 각 3~5초 실행 → PASS/FAIL 요약.

예상 결과:
```
  [PASS] completed/laptop_monitor
  [PASS] completed/laptop_thruster
  [PASS] completed/laptop_rw
  [PASS] attitude_controller
  [PASS] orbit_controller
  [PASS] vision_operator
  6 / 6 passed
```

### 개별 수동 테스트 (노트북에서, 서버가 이미 실행 중일 때)

```bash
# 1. 센서 수신 되는지
python3 student/completed/laptop_monitor.py --host 192.168.0.54 --deputy deputy_formation
# → gyro/q_ECI/r_ECI/sun 등 출력되면 OK

# 2. 추력기 명령이 가제보에 반영되는지
python3 student/completed/laptop_thruster.py --host 192.168.0.54 \
    --deputy deputy_docking --axis fy_plus --throttle 0.3 --duration 1
# → "[fire] ... [fire] stopped" 출력 + 가제보에서 deputy 움직임 확인

# 3. 반작용휠 명령
python3 student/completed/laptop_rw.py --host 192.168.0.54 \
    --deputy deputy_docking --axis z --torque 0.002 --duration 2
# → "[rw] ... [rw] stopped" + deputy 회전 확인

# 4. 카메라 브라우저 확인
# 브라우저에서:
#   http://192.168.0.54:8080/stream_viewer?topic=/nasa_satellite/camera&type=mjpeg
# → 영상 스트림 보이면 OK

# 5. 역할별 scaffold 실행
python3 student/attitude_controller.py --host 192.168.0.54 --deputy deputy_formation
# → gyro + q_ECI 출력 나오면 OK (제어 로직은 TODO)

python3 student/orbit_controller.py --host 192.168.0.54 --deputy deputy_docking
# → "상대벡터 ECI ... 거리: ~5000 m" 출력 나오면 OK

python3 student/vision_operator.py --host 192.168.0.54 --deputy deputy_formation
# → 브라우저 자동 열림 + 거리 출력 나오면 OK
```

---

## 완성 코드 vs 스캐폴드

```
student/
├── completed/                ← 바로 실행 가능한 완성 예제
│   ├── laptop_thruster.py    ← 추력기 점화 (argparse, throttle, duration)
│   ├── laptop_rw.py          ← 반작용휠 토크 (argparse, torque, duration)
│   └── laptop_monitor.py     ← 전 센서 통합 모니터 (IMU/ST/GPS/TLE/Sun)
│
├── attitude_controller.py    ← 자세 제어 스캐폴드 (TODO: PD 제어 구현)
├── orbit_controller.py       ← 궤도 제어 스캐폴드 (TODO: 접근 전략 구현)
├── vision_operator.py        ← 영상 스캐폴드 (TODO: VBN/캡처 구현)
└── README.md                 ← 이 파일
```

**완성 코드** (`completed/`): 명령 1줄로 즉시 동작. 기능 확인/테스트용.
**스캐폴드** (루트): 구조 + 센서 연결 완료, 제어 로직은 `# TODO` 로 비워둠. 학생이 채움.

## 각 역할이 해야 할 일

### 자세 제어 담당
- Star Tracker 쿼터니언 → 현재 body-in-ECI 자세 확인
- 목표 자세 결정 (카메라를 chief 쪽으로 정렬 등)
- 자세 오차 → PD 제어 → Reaction Wheel 토크 명령

### 궤도 제어 담당
- GPS (내 ECI) - TLE (chief ECI) = 상대 벡터 (ECI) 계산
- 접근 전략: V-bar 접근 (+y 방향 추력)
- 속도 제어: 거리 따라 접근속도 조절
- **주의: TLE 오차 ~1 km → 근접 시 영상 담당과 협조 필수**

### 영상 담당
- 브라우저로 카메라 영상 관측
- Chief 가 FOV 에 보이는지 자세 담당에게 피드백
- 원하는 각도에서 스크린샷 저장 (팀 1)
- VBN: chief 가 화면 어디 있는지 → 상대 방향 추정 (팀 2, 선택)
