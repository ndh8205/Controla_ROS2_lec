#!/usr/bin/env python3
"""자세 제어 담당 — 노트북 스타터 (rosbridge 경유).

역할: Star Tracker + IMU 자이로 모니터 + Reaction Wheel 명령
목표: Deputy 의 body 자세를 LVLH 와 정렬 유지 또는 카메라를 chief 방향으로 회전

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
    g = msg['angular_velocity']
    with lock:
        state['gyro'] = (g['x'], g['y'], g['z'])


def on_star_tracker(msg):
    q = msg['quaternion']
    with lock:
        state['q_eci'] = (q['x'], q['y'], q['z'], q['w'])


roslibpy.Topic(client, f'/{args.deputy}/imu/data',
               'sensor_msgs/Imu').subscribe(on_imu)
roslibpy.Topic(client, f'/{args.deputy}/star_tracker/attitude',
               'geometry_msgs/QuaternionStamped').subscribe(on_star_tracker)

# ===================== 액추에이터 =====================
rw_x = roslibpy.Topic(client, f'/{args.deputy}/rw/x/cmd', 'std_msgs/Float32')
rw_y = roslibpy.Topic(client, f'/{args.deputy}/rw/y/cmd', 'std_msgs/Float32')
rw_z = roslibpy.Topic(client, f'/{args.deputy}/rw/z/cmd', 'std_msgs/Float32')

# ===================== 제어 루프 =====================
# TODO: 학생이 구현할 부분!
#
# 아이디어:
#   1. star_tracker 로부터 q_body/ECI 읽기
#   2. 목표 자세 정의 (예: LVLH 정렬 = chief propagator 의 q_LVLH/ECI)
#   3. 자세 오차 계산: q_error = q_target^-1 * q_measured
#   4. 작은 각 근사: theta ≈ 2 * q_error[0:3]
#   5. PD 제어: tau = -Kp * theta - Kd * gyro
#   6. reaction wheel 로 토크 명령
#
# 지금은 센서 출력만 표시합니다. 직접 채워보세요!

print('[attitude] 자세 센서 모니터 시작 (Ctrl+C 종료)')
print('  제어 로직을 이 파일에 직접 구현하세요!\n')

try:
    while True:
        time.sleep(0.5)
        with lock:
            if 'gyro' in state:
                gx, gy, gz = state['gyro']
                print(f'  gyro=({gx:+.4e}, {gy:+.4e}, {gz:+.4e}) rad/s', end='')
            if 'q_eci' in state:
                qx, qy, qz, qw = state['q_eci']
                print(f'  q_ECI=({qx:+.4f},{qy:+.4f},{qz:+.4f},{qw:+.4f})', end='')
            print()

        # ▼ 여기에 제어 로직 추가 ▼
        # 예시: z축 0.001 Nm 토크 (주석 해제해서 테스트)
        # rw_z.publish(roslibpy.Message({'data': 0.001}))

except KeyboardInterrupt:
    # 정지
    for rw in (rw_x, rw_y, rw_z):
        rw.publish(roslibpy.Message({'data': 0.0}))
    print('\n[attitude] 종료')

client.terminate()
