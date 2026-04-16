# SSA 미션 실습 명령어 & 코드 해설

> 이 문서는 `mission.launch.py` 실행 상태에서 사용하는 모든 명령/코드를
> **한 줄씩 해설**합니다.

---

## 0. 사전 준비

### 플랫샛 (메인 데스크탑)
```bash
bash ~/kill_sim.sh                        # 이전 프로세스 정리
ros2 launch gz_cw_dynamics mission.launch.py   # 시뮬레이션 + rosbridge + web 시작
```

### 학생 노트북 (1회, ROS 2 불필요!)
```bash
sudo apt install -y python3-pip
pip3 install roslibpy --break-system-packages
git clone https://github.com/ndh8205/Controla_ROS2_lec.git ~/orbit_sim
cd ~/orbit_sim
```
> `ros2 run`, `ros2 launch` 는 학생 노트북에서 **사용 불가**.
> 반드시 `python3 student/...` 로 직접 실행.

---

## 1. 센서 모니터 (laptop_monitor.py)

### 실행 (학생 노트북에서)
```bash
cd ~/orbit_sim
python3 student/completed/laptop_monitor.py --host 192.168.0.54 --deputy deputy_formation
```

### 코드 해설

```python
#!/usr/bin/env python3
```
> 이 파일을 Python 3 으로 실행하라는 shebang. `python3 파일.py` 대신 `./파일.py` 로도 실행 가능.

```python
import roslibpy
```
> **roslibpy**: rosbridge WebSocket 프로토콜로 ROS 2 토픽에 접근하는 Python 라이브러리.
> rclpy (ROS 2 공식 Python) 와 달리 **DDS 없이 TCP/WebSocket 만으로 원격 접속** 가능.
> 학생 노트북에 ROS 2 가 없어도 이 라이브러리만으로 토픽 pub/sub 가능.

```python
import math, time, argparse
from threading import Lock
```
> - `math`: 벡터 크기 계산 (`sqrt`)
> - `time`: `time.sleep()` 으로 출력 주기 제어
> - `argparse`: 커맨드라인 인자 파싱 (`--host`, `--deputy`)
> - `Lock`: 멀티스레드 환경에서 데이터 보호. roslibpy 콜백은 별도 스레드에서 실행됨.

```python
client = roslibpy.Ros(host=args.host, port=9090)
client.run()
```
> **rosbridge 서버에 WebSocket 접속**. `host` = 플랫샛 IP, `port` = 9090 (rosbridge 기본).
> `run()` 은 백그라운드 스레드를 시작해서 비동기 수신 준비.

```python
state = {}
lock = Lock()

def put(k, v):
    with lock:
        state[k] = v
```
> **상태 저장소 패턴**. 콜백이 여러 스레드에서 호출되므로 `Lock` 으로 동시 접근 방지.
> `put('imu', msg)` → `state['imu'] = msg` 를 thread-safe 하게 수행.

```python
roslibpy.Topic(client, f'/{d}/imu/data', 'sensor_msgs/Imu').subscribe(lambda m: put('imu', m))
```
> **토픽 구독**. 3개 인자:
> - `client`: rosbridge 연결 객체
> - `f'/{d}/imu/data'`: 토픽 이름 (예: `/deputy_formation/imu/data`)
> - `'sensor_msgs/Imu'`: ROS 메시지 타입
>
> `.subscribe(콜백)` → 메시지 올 때마다 `put('imu', msg)` 호출.
> rosbridge 가 JSON 으로 직렬화해서 보내므로, `msg` 는 Python dict.
>
> **IMU 메시지 구조** (sensor_msgs/Imu):
> - `angular_velocity.{x,y,z}` — 자이로 (rad/s, body frame)
> - `linear_acceleration.{x,y,z}` — 가속도계 (m/s², body frame, specific force)
> - `orientation.{x,y,z,w}` — 쿼터니언 (LVLH 기준)

```python
roslibpy.Topic(client, f'/{d}/star_tracker/attitude',
               'geometry_msgs/QuaternionStamped').subscribe(lambda m: put('st', m))
```
> **Star Tracker**: body-in-ECI 쿼터니언. 별센서가 직접 관측한 절대 자세.
> 메시지: `quaternion.{x,y,z,w}`, `header.frame_id = "eci"`.
> 노이즈 σ = 0.05° (소각 Gaussian).

```python
roslibpy.Topic(client, f'/{d}/gps/odometry',
               'nav_msgs/Odometry').subscribe(lambda m: put('gps', m))
```
> **GPS**: deputy ECI 위치 (m) + 속도 (m/s).
> 메시지: `pose.pose.position.{x,y,z}`, `twist.twist.linear.{x,y,z}`.
> 노이즈 σ_pos = 5 m, σ_vel = 0.05 m/s.

```python
roslibpy.Topic(client, '/chief/eci_state',
               'nav_msgs/Odometry').subscribe(lambda m: put('tle', m))
```
> **Chief TLE 추정**: SGP4 전파 + Gaussian 노이즈.
> 이것이 **학생이 아는 유일한 chief 정보**. 실제 chief 와 ~km 수준 오차.
> `/chief/eci_truth` 는 진실값이지만 학생에게 공개하지 않음 (센서 내부용).

```python
roslibpy.Topic(client, '/chief/sun_vector_lvlh',
               'geometry_msgs/Vector3Stamped').subscribe(lambda m: put('sun', m))
```
> **태양 방향** (LVLH 프레임 단위벡터). 전력 계획, 태양센서 시뮬레이션용.

```python
# 출력 루프
while True:
    time.sleep(0.5)
    with lock:
        # state dict 에서 최신 값 읽어서 출력
```
> 0.5초 주기로 최신 센서 값 출력. `with lock:` 으로 콜백과 동시 접근 방지.

---

## 2. 추력기 명령 (laptop_thruster.py)

### 실행
```bash
# deputy_docking 의 +y 방향 추력, 0.5 throttle, 2초
python3 student/completed/laptop_thruster.py --host 192.168.0.54 \
    --deputy deputy_docking --axis fy_plus --throttle 0.5 --duration 2
```

### 코드 해설

```python
AXES = ('fx_plus','fx_minus','fy_plus','fy_minus','fz_plus','fz_minus')
```
> **6 추력기 이름**. Hill 프레임 (LVLH) 기준:
> - `fx_plus` / `fx_minus`: ±x (radial, 지구 방향)
> - `fy_plus` / `fy_minus`: ±y (along-track, 진행 방향) ← **접근에 주로 사용**
> - `fz_plus` / `fz_minus`: ±z (cross-track, 궤도면 수직)

```python
topic = f'/{args.deputy}/thruster/{args.axis}/cmd'
pub = roslibpy.Topic(client, topic, 'std_msgs/Float32')
```
> **발행 토픽 생성**. 타입 `std_msgs/Float32` — 단일 float 값.
> throttle [0, 1] 범위. 1.0 = 최대 추력 (1 N).

```python
t_end = time.time() + args.duration
while time.time() < t_end:
    pub.publish(roslibpy.Message({'data': float(args.throttle)}))
    time.sleep(0.05)
```
> **지정 시간 동안 반복 발행** (20 Hz).
> rosbridge 는 비연결형이라 한 번만 보내면 유실 가능 → 반복 발행 필요.
> `roslibpy.Message({'data': 값})` = ROS Float32 메시지의 JSON 표현.

```python
pub.publish(roslibpy.Message({'data': 0.0}))
```
> **정지 명령**. throttle = 0 으로 추력 해제.
> 우주에서는 추력 해제 = 관성 유지 (등속 운동), 멈추는 게 아님!

### 물리
> 추력 F = throttle × max_force = 0.5 × 1.0 = **0.5 N**
> 가속도 a = F / m = 0.5 / 2.0 = **0.25 m/s²**
> 2초 발사 → ΔV = 0.25 × 2 = **0.5 m/s** 속도 변화
> IMU 가속도계에서 이 값이 관측됨 (추력 방향 축)

---

## 3. 반작용휠 (laptop_rw.py)

### 실행
```bash
# deputy_docking 의 z축 RW 토크 0.002 N·m, 1초
python3 student/completed/laptop_rw.py --host 192.168.0.54 \
    --deputy deputy_docking --axis z --torque 0.002 --duration 1
```

### 코드 해설

```python
topic = f'/{args.deputy}/rw/{args.axis}/cmd'
pub = roslibpy.Topic(client, topic, 'std_msgs/Float32')
```
> **RW 토크 명령 토픽**. 값 = 토크 (N·m), max ±0.01.
> 양수 토크 → body 반대 방향 회전 (Newton 3rd law).

```python
pub.publish(roslibpy.Message({'data': float(args.torque)}))
```
> 토크 명령 전송. 추력기와 달리 **양/음 모두 가능** (방향 반전).

### 물리
> 토크 τ = 0.002 N·m, body 관성 I_z ≈ 0.004 kg·m²
> 각가속도 α = τ / I = 0.002 / 0.004 = **0.5 rad/s²**
> 1초 → Δω = 0.5 rad/s (약 28.6°/s 회전 속도 증가)
> IMU 자이로에서 해당 축 angular_velocity 변화로 관측

---

## 4. 자세 제어 scaffold (attitude_controller.py)

### 실행
```bash
python3 student/attitude_controller.py --host 192.168.0.54 --deputy deputy_formation
```

### 구현해야 할 것 (TODO)

```python
# PD 제어 스켈레톤:
# 1. Star Tracker q_body_ECI 읽기
# 2. 목표 자세 q_target 정의
# 3. 오차: q_err = conj(q_target) * q_measured
# 4. 소각 근사: theta ≈ 2 * [q_err.x, q_err.y, q_err.z]
# 5. 제어: tau = -Kp * theta - Kd * gyro
# 6. send_rw(tau_x, tau_y, tau_z)
```

> **왜 PD 제어?**
> - P (비례): 자세 오차에 비례한 복원 토크 → 목표로 돌아감
> - D (미분): 각속도에 비례한 감쇠 토크 → 진동 방지
> - Kp, Kd 게인은 시행착오로 조정 (너무 크면 진동, 너무 작으면 느림)

### 센서 출력 의미

```python
state['gyro']   # (gx, gy, gz) rad/s — body frame 각속도
                # gz ≈ 1.1e-3 rad/s 가 기본 (LVLH 회전)
                # RW 토크 인가 시 해당 축 값 변화

state['accel']  # (ax, ay, az) m/s² — specific force (비중력)
                # 추력기 off 시 ≈ 0 (자유낙하)
                # 추력기 on 시 해당 방향 ≠ 0

state['q_eci']  # (qx, qy, qz, qw) — body-in-ECI 쿼터니언
                # body→ECI 회전. 자세 제어의 핵심 측정치.
```

---

## 5. 궤도 제어 scaffold (orbit_controller.py)

### 실행
```bash
python3 student/orbit_controller.py --host 192.168.0.54 --deputy deputy_docking
```

### 구현해야 할 것 (TODO)

```python
# V-bar 접근:
# 1. dr = tle_pos - gps_pos  (ECI 상대벡터)
# 2. dist = |dr|              (약 5000 m 시작)
# 3. 거리별 속도 제어:
#    dist > 1000 → 빠르게 (throttle 0.5)
#    dist > 100  → 천천히 (throttle 0.1)
#    dist < 100  → 매우 천천히 (throttle 0.02)
# 4. 방향: fy_plus or fy_minus (chief 쪽)
# 5. 가속도계로 추력 확인
```

> **왜 V-bar 접근?**
> CW 동역학에서 along-track (+y) 방향 접근이 가장 안정적.
> Radial (+x) 접근은 CW coupling 으로 궤적이 복잡해짐.

> **TLE 오차 주의!**
> `/chief/eci_state` 는 ~km 수준 오차 (SGP4 J2 drift + Gaussian).
> 1 km 이내부터는 **카메라 VBN** 으로 보정해야 정확한 도킹 가능.
> → 영상 담당과 협조!

### 센서 출력 의미

```python
state['gps_pos']   # (x, y, z) m — 내 ECI 위치. |r| ≈ 6923 km
state['gps_vel']   # (vx, vy, vz) m/s — 내 ECI 속도. |v| ≈ 7588 m/s
state['tle_pos']   # (x, y, z) m — chief ECI 추정 위치 (노이즈!)
state['accel']     # (ax, ay, az) m/s² — 추력 확인용
```

---

## 6. 영상 담당 (vision_operator.py)

### 실행
```bash
python3 student/vision_operator.py --host 192.168.0.54 --deputy deputy_formation
```

### 카메라 URL

```
# Deputy 탑재 카메라 (deputy 시점에서 본 우주)
http://192.168.0.54:8080/stream_viewer?topic=/nasa_satellite/camera&type=mjpeg   # 팀1
http://192.168.0.54:8080/stream_viewer?topic=/nasa_satellite2/camera&type=mjpeg  # 팀2

# 옵저버 카메라 (외부에서 본 위성 모습)
http://192.168.0.54:8080/stream_viewer?topic=/observer/chief/camera&type=mjpeg       # Chief
http://192.168.0.54:8080/stream_viewer?topic=/observer/formation/camera&type=mjpeg   # 팀1 Deputy
http://192.168.0.54:8080/stream_viewer?topic=/observer/docking/camera&type=mjpeg     # 팀2 Deputy

# 전체 카메라 목록
http://192.168.0.54:8080/
```

> **web_video_server**: ROS 2 Image 토픽을 HTTP mjpeg 스트림으로 변환.
> 브라우저만 있으면 카메라 영상 확인 가능. 코드 필요 없음.
> `&type=mjpeg` 필수 — 기본 코덱은 브라우저 호환 안 됨.

---

## 7. ROS 2 CLI 명령어 (플랫샛 로컬)

### 추력기 (1회 발사)
```bash
ros2 topic pub -1 /deputy_docking/thruster/fy_plus/cmd std_msgs/Float32 "{data: 1.0}"
```

### 추력기 (연속, 정지)
```bash
ros2 topic pub /deputy_docking/thruster/fy_plus/cmd std_msgs/Float32 "{data: 0.5}" --rate 10 &
# ... 원하는 만큼 대기 ...
pkill -f "ros2 topic pub"
ros2 topic pub -1 /deputy_docking/thruster/fy_plus/cmd std_msgs/Float32 "{data: 0.0}"
```

### 반작용휠
```bash
ros2 topic pub -1 /deputy_docking/rw/z/cmd std_msgs/Float32 "{data: 0.005}"
ros2 topic pub -1 /deputy_docking/rw/z/cmd std_msgs/Float32 "{data: 0.0}"
```

### 센서 확인
```bash
# IMU (자이로 + 가속도)
ros2 topic echo /deputy_docking/imu/data --once | grep -A3 angular_velocity
ros2 topic echo /deputy_docking/imu/data --once | grep -A3 linear_acceleration

# Star Tracker (쿼터니언)
ros2 topic echo /deputy_docking/star_tracker/attitude --once

# GPS (ECI 위치/속도)
ros2 topic echo /deputy_docking/gps/odometry --once | grep -A3 position

# Chief TLE (학생에게 주어진 chief 정보)
ros2 topic echo /chief/eci_state --once | grep -A3 position

# Sun 벡터
ros2 topic echo /chief/sun_vector_lvlh --once
```

### 토픽/노드 확인
```bash
ros2 topic list | grep deputy
ros2 node list | grep thruster
ros2 topic info /deputy_docking/thruster/fy_plus/cmd -v   # QoS 확인
ros2 topic hz /deputy_docking/imu/data                     # 발행 빈도
```

### RTF (시뮬레이션 속도)
```bash
# 빨리 감기 (원거리 접근)
gz service -s /world/mission/set_physics \
    --reqtype gz.msgs.Physics --reptype gz.msgs.Boolean --timeout 1000 \
    --req 'max_step_size: 0.01, real_time_factor: 30.0'

# 실시간 (근접)
gz service -s /world/mission/set_physics \
    --reqtype gz.msgs.Physics --reptype gz.msgs.Boolean --timeout 1000 \
    --req 'max_step_size: 0.01, real_time_factor: 1.0'
```

---

## 8. 토픽 전체 목록

### Chief (공유)

| 토픽 | 타입 | 내용 |
|---|---|---|
| `/chief/eci_state` | nav_msgs/Odometry | TLE+노이즈 chief 추정 (학생용) |
| `/chief/eci_truth` | nav_msgs/Odometry | 진실 (센서 내부용, 학생 비공개) |
| `/chief/sun_vector_lvlh` | geometry_msgs/Vector3Stamped | LVLH 태양 방향 |

### Deputy 별 (`deputy_formation` / `deputy_docking`)

| 토픽 | 타입 | 방향 | 내용 |
|---|---|---|---|
| `/{dep}/imu/data` | sensor_msgs/Imu | sub | 자이로 + 가속도 (LVLH aware) |
| `/{dep}/star_tracker/attitude` | geometry_msgs/QuaternionStamped | sub | body-in-ECI q (노이즈 0.05°) |
| `/{dep}/gps/odometry` | nav_msgs/Odometry | sub | ECI 위치+속도 (σ 5m) |
| `/{dep}/thruster/fx_plus/cmd` | std_msgs/Float32 | **pub** | +x 추력 [0,1] |
| `/{dep}/thruster/fx_minus/cmd` | std_msgs/Float32 | **pub** | -x 추력 |
| `/{dep}/thruster/fy_plus/cmd` | std_msgs/Float32 | **pub** | +y 추력 |
| `/{dep}/thruster/fy_minus/cmd` | std_msgs/Float32 | **pub** | -y 추력 |
| `/{dep}/thruster/fz_plus/cmd` | std_msgs/Float32 | **pub** | +z 추력 |
| `/{dep}/thruster/fz_minus/cmd` | std_msgs/Float32 | **pub** | -z 추력 |
| `/{dep}/rw/x/cmd` | std_msgs/Float32 | **pub** | x축 RW 토크 (N·m) |
| `/{dep}/rw/y/cmd` | std_msgs/Float32 | **pub** | y축 RW 토크 |
| `/{dep}/rw/z/cmd` | std_msgs/Float32 | **pub** | z축 RW 토크 |

### 카메라 (gz transport → ros_gz_bridge → web)

| 토픽 | 내용 |
|---|---|
| `/nasa_satellite/camera` | 팀1 deputy 탑재 |
| `/nasa_satellite2/camera` | 팀2 deputy 탑재 |
| `/observer/chief/camera` | Chief 외부 관측 |
| `/observer/formation/camera` | 팀1 deputy 외부 관측 |
| `/observer/docking/camera` | 팀2 deputy 외부 관측 |

---

## 9. 프레임 / 좌표계 정리

### Hill (LVLH) 프레임 = Gazebo 월드 프레임

```
+x : 지구 중심 → 위성 방향 (radial outward)
+y : 위성 진행 방향 (along-track, V-bar)
+z : 궤도면 수직 (cross-track, orbit normal)
```

### 주요 수치

| 항목 | 값 |
|---|---|
| Chief 고도 | 545 km (SSO) |
| 궤도 반경 (SMA) | 6923.137 km |
| 평균 운동 (n) | 1.0959 × 10⁻³ rad/s |
| 궤도 주기 | 95.55 분 |
| LVLH 회전 속도 | gyro_z ≈ n (body = LVLH 일 때) |
| 추력기 | 1 N × 6 방향 |
| RW 토크 | max 0.01 N·m × 3 축 |

---

*ControLA SSA 미션 세미나 — 2026-04-17*
