#!/usr/bin/env python3
"""자세 제어 담당 — 노트북 스타터 (rosbridge 경유).

[역할]
  Star Tracker + IMU (자이로+가속도계) 모니터 + Reaction Wheel 토크 명령.
  Deputy 의 body 자세를 제어하여 카메라를 chief 방향으로 정렬.

[센서 입력]
  /deputy_*/star_tracker/attitude  → body-in-ECI 쿼터니언 (노이즈 0.05° 1σ)
  /deputy_*/imu/data               → 자이로 (rad/s) + 가속도계 (m/s^2)
                                     자이로 z ≈ 1.1e-3 (LVLH 회전)
                                     가속도 ≈ 0 (추력 없을 때, specific force)

[액추에이터 출력]
  /deputy_*/rw/{x,y,z}/cmd        → 각 축 토크 명령 (Float32, N·m, max 0.01)

사용법:
    python3 attitude_controller.py --host 192.168.0.54 --deputy deputy_formation
"""
import argparse
import math
import time
from threading import Lock
import roslibpy

# ===================== 설정 =====================
ap = argparse.ArgumentParser()
ap.add_argument('--host',   default='192.168.0.54')
ap.add_argument('--deputy', default='deputy_formation')
args = ap.parse_args()

client = roslibpy.Ros(host=args.host, port=9090)
client.run()
print(f'[attitude] 접속: {args.host}:9090, deputy={args.deputy}')

# ===================== 센서 구독 =====================
state = {}
lock = Lock()


def on_imu(msg):
    """IMU 콜백: 자이로 + 가속도계."""
    g = msg['angular_velocity']       # rad/s, body frame
    a = msg['linear_acceleration']    # m/s^2, body frame (specific force)
    with lock:
        state['gyro'] = (g['x'], g['y'], g['z'])
        state['accel'] = (a['x'], a['y'], a['z'])


def on_star_tracker(msg):
    """Star Tracker 콜백: body-in-ECI 쿼터니언 (x, y, z, w)."""
    q = msg['quaternion']
    with lock:
        state['q_eci'] = (q['x'], q['y'], q['z'], q['w'])


roslibpy.Topic(client, f'/{args.deputy}/imu/data',
               'sensor_msgs/Imu').subscribe(on_imu)
roslibpy.Topic(client, f'/{args.deputy}/star_tracker/attitude',
               'geometry_msgs/QuaternionStamped').subscribe(on_star_tracker)

# ===================== 액추에이터 (Reaction Wheel) =====================
rw_x = roslibpy.Topic(client, f'/{args.deputy}/rw/x/cmd', 'std_msgs/Float32')
rw_y = roslibpy.Topic(client, f'/{args.deputy}/rw/y/cmd', 'std_msgs/Float32')
rw_z = roslibpy.Topic(client, f'/{args.deputy}/rw/z/cmd', 'std_msgs/Float32')


def send_rw(x=0.0, y=0.0, z=0.0):
    """3축 RW 토크 명령 전송 (N·m). max ±0.01."""
    rw_x.publish(roslibpy.Message({'data': float(x)}))
    rw_y.publish(roslibpy.Message({'data': float(y)}))
    rw_z.publish(roslibpy.Message({'data': float(z)}))


# ===================== 제어 루프 =====================
# -------------------------------------------------------
# TODO: 학생이 구현할 부분!
#
# [PD 자세 제어 스켈레톤]
#
# 1. Star Tracker 로부터 q_body_ECI 읽기
#    q = state['q_eci']  # (x, y, z, w)
#
# 2. 목표 자세 정의
#    - LVLH 정렬 유지: q_target = q_LVLH_in_ECI (chief propagator 제공)
#    - 카메라를 chief 방향으로: 궤도 담당에게 상대 벡터 받아서 계산
#
# 3. 자세 오차 계산 (small angle approximation)
#    q_err = quat_multiply(quat_conj(q_target), q_measured)
#    theta = 2 * [q_err.x, q_err.y, q_err.z]  # 라디안
#
# 4. PD 제어
#    Kp = 0.001  # 비례 게인 (N·m/rad)
#    Kd = 0.0005 # 미분 게인 (N·m/(rad/s))
#    gyro = state['gyro']
#    tau_x = -Kp * theta[0] - Kd * gyro[0]
#    tau_y = -Kp * theta[1] - Kd * gyro[1]
#    tau_z = -Kp * theta[2] - Kd * gyro[2]
#    send_rw(tau_x, tau_y, tau_z)
#
# 5. 추력 감지 (가속도계)
#    accel = state['accel']
#    # 추력기 발사 중이면 accel ≠ 0 → 자세 외란 예상
# -------------------------------------------------------

print('[attitude] 센서 모니터 + 자세 제어 (Ctrl+C 종료)')
print('  TODO 주석을 보고 PD 제어 로직을 구현하세요!\n')

try:
    while True:
        time.sleep(0.5)
        with lock:
            if 'gyro' in state:
                gx, gy, gz = state['gyro']
                print(f'  [GYRO] ({gx:+.4e}, {gy:+.4e}, {gz:+.4e}) rad/s', end='')
            if 'accel' in state:
                ax, ay, az = state['accel']
                print(f'  [ACCEL] ({ax:+.4e}, {ay:+.4e}, {az:+.4e}) m/s²', end='')
            if 'q_eci' in state:
                qx, qy, qz, qw = state['q_eci']
                print(f'  [Q] ({qx:+.4f},{qy:+.4f},{qz:+.4f},{qw:+.4f})', end='')
            print()

        # ▼▼▼ 여기에 제어 로직 넣기 ▼▼▼
        # send_rw(tau_x, tau_y, tau_z)

except KeyboardInterrupt:
    send_rw(0, 0, 0)
    print('\n[attitude] RW 정지, 종료')

client.terminate()
