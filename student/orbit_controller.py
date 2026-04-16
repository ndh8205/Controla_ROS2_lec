#!/usr/bin/env python3
"""궤도 제어 담당 — 노트북 스타터 (rosbridge 경유).

[역할]
  GPS + Chief TLE → 상대 위치/속도 계산 → 추력기 명령으로 접근.
  5 km 떨어진 지점에서 chief 쪽으로 V-bar approach.

[센서 입력]
  /deputy_*/gps/odometry    → 내 ECI 위치 (m) + 속도 (m/s), 노이즈 σ=5m
  /chief/eci_state          → TLE 기반 chief ECI 추정 (노이즈 σ=100m + J2 drift)
  /deputy_*/imu/data        → 가속도계 (추력 확인용)

[액추에이터 출력]
  /deputy_*/thruster/{fx,fy,fz}_{plus,minus}/cmd  → Float32 [0,1] throttle

[주의]
  - TLE 오차 ~1-3 km! 근접 시 카메라 VBN 필요 (영상 담당 연계)
  - V-bar 접근 (along-track) 이 CW 에서 가장 안정적

사용법:
    python3 orbit_controller.py --host 192.168.0.54 --deputy deputy_docking
"""
import argparse
import math
import time
from threading import Lock
import roslibpy

# ===================== 설정 =====================
ap = argparse.ArgumentParser()
ap.add_argument('--host',   default='192.168.0.54')
ap.add_argument('--deputy', default='deputy_docking')
args = ap.parse_args()

client = roslibpy.Ros(host=args.host, port=9090)
client.run()
print(f'[orbit] 접속: {args.host}:9090, deputy={args.deputy}')

# ===================== 센서 구독 =====================
state = {}
lock = Lock()


def on_gps(msg):
    """GPS 콜백: deputy ECI 위치 (m) + 속도 (m/s)."""
    p = msg['pose']['pose']['position']
    v = msg['twist']['twist']['linear']
    with lock:
        state['gps_pos'] = (p['x'], p['y'], p['z'])
        state['gps_vel'] = (v['x'], v['y'], v['z'])


def on_tle(msg):
    """Chief TLE 콜백: SGP4 + 노이즈 기반 추정 ECI 위치/속도."""
    p = msg['pose']['pose']['position']
    v = msg['twist']['twist']['linear']
    with lock:
        state['tle_pos'] = (p['x'], p['y'], p['z'])
        state['tle_vel'] = (v['x'], v['y'], v['z'])


def on_imu(msg):
    """IMU 콜백: 가속도계로 추력기 인가 확인."""
    a = msg['linear_acceleration']
    with lock:
        state['accel'] = (a['x'], a['y'], a['z'])


roslibpy.Topic(client, f'/{args.deputy}/gps/odometry',
               'nav_msgs/Odometry').subscribe(on_gps)
roslibpy.Topic(client, '/chief/eci_state',
               'nav_msgs/Odometry').subscribe(on_tle)
roslibpy.Topic(client, f'/{args.deputy}/imu/data',
               'sensor_msgs/Imu').subscribe(on_imu)

# ===================== 액추에이터 (6 Thrusters) =====================
thrusters = {}
for axis in ('fx_plus', 'fx_minus', 'fy_plus', 'fy_minus',
             'fz_plus', 'fz_minus'):
    thrusters[axis] = roslibpy.Topic(
        client, f'/{args.deputy}/thruster/{axis}/cmd', 'std_msgs/Float32')


def fire(axis, throttle):
    """추력기 발사. axis='fy_plus' 등, throttle=[0,1]."""
    thrusters[axis].publish(roslibpy.Message({'data': float(throttle)}))


def stop_all():
    """모든 추력기 정지."""
    for t in thrusters.values():
        t.publish(roslibpy.Message({'data': 0.0}))


def vec_sub(a, b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])


def vec_norm(v):
    return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)


# ===================== 제어 루프 =====================
# -------------------------------------------------------
# TODO: 학생이 구현할 부분!
#
# [V-bar 접근 전략 스켈레톤]
#
# 1. 상대 벡터 계산 (ECI 프레임, 대략적)
#    dr = vec_sub(state['tle_pos'], state['gps_pos'])  # chief - deputy
#    dist = vec_norm(dr)   # 약 5000 m 에서 시작
#
# 2. 접근 방향 (단위 벡터)
#    dir = (dr[0]/dist, dr[1]/dist, dr[2]/dist)
#
# 3. 거리 기반 속도 제어
#    if dist > 1000:       # 원거리: 빠르게 접근
#        target_v = 1.0    # m/s
#    elif dist > 100:      # 중거리: 천천히
#        target_v = 0.3
#    else:                 # 근접: 매우 천천히
#        target_v = 0.05
#
# 4. 추력기 선택 (body frame 에서 chief 방향 → 어느 추력기?)
#    - 단순화: along-track (+y or -y) 접근 가정
#    - deputy_docking 은 y=-5000 에서 시작 → chief 는 +y 방향
#    - fy_plus 로 +y 방향 추력
#    fire('fy_plus', 0.3)
#
# 5. 가속도계 확인
#    accel = state['accel']  # 추력 인가 중이면 ≠ 0
#
# 6. 근접 시 영상 담당에게 VBN 요청
#    print("1km 이내 진입! 영상 담당 VBN 시작 요청")
# -------------------------------------------------------

print('[orbit] 상대 네비게이션 모니터 (Ctrl+C 종료)')
print('  TODO 주석을 보고 접근 전략을 구현하세요!\n')

try:
    while True:
        time.sleep(1.0)
        with lock:
            if 'gps_pos' in state and 'tle_pos' in state:
                dr = vec_sub(state['tle_pos'], state['gps_pos'])
                dist = vec_norm(dr)
                print(f'  [REL] 상대벡터: ({dr[0]:+.0f},{dr[1]:+.0f},{dr[2]:+.0f}) m  '
                      f'거리: {dist:.0f} m ({dist/1000:.2f} km)', end='')

            if 'accel' in state:
                ax, ay, az = state['accel']
                accel_mag = math.sqrt(ax*ax + ay*ay + az*az)
                if accel_mag > 0.01:
                    print(f'  [추력중! |a|={accel_mag:.3f}]', end='')

            print()

            # ▼▼▼ 여기에 접근 제어 넣기 ▼▼▼
            # fire('fy_plus', 0.3)

except KeyboardInterrupt:
    stop_all()
    print('\n[orbit] 모든 추력기 정지, 종료')

client.terminate()
