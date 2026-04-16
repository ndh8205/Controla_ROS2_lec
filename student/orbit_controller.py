#!/usr/bin/env python3
"""궤도 제어 담당 — 노트북 스타터 (rosbridge 경유).

역할: GPS + Chief TLE → 상대 위치 계산 + 추력기 명령
목표: 5 km 에서 chief 쪽으로 접근 (V-bar approach)

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
    p = msg['pose']['pose']['position']
    v = msg['twist']['twist']['linear']
    with lock:
        state['gps_pos'] = (p['x'], p['y'], p['z'])
        state['gps_vel'] = (v['x'], v['y'], v['z'])


def on_tle(msg):
    p = msg['pose']['pose']['position']
    v = msg['twist']['twist']['linear']
    with lock:
        state['tle_pos'] = (p['x'], p['y'], p['z'])
        state['tle_vel'] = (v['x'], v['y'], v['z'])


roslibpy.Topic(client, f'/{args.deputy}/gps/odometry',
               'nav_msgs/Odometry').subscribe(on_gps)
roslibpy.Topic(client, '/chief/eci_state',
               'nav_msgs/Odometry').subscribe(on_tle)

# ===================== 액추에이터 =====================
thrusters = {}
for axis in ('fx_plus', 'fx_minus', 'fy_plus', 'fy_minus',
             'fz_plus', 'fz_minus'):
    thrusters[axis] = roslibpy.Topic(
        client, f'/{args.deputy}/thruster/{axis}/cmd', 'std_msgs/Float32')


def fire(axis, throttle):
    thrusters[axis].publish(roslibpy.Message({'data': float(throttle)}))


def stop_all():
    for t in thrusters.values():
        t.publish(roslibpy.Message({'data': 0.0}))


# ===================== 유틸 =====================
def vec_sub(a, b):
    return (a[0]-b[0], a[1]-b[1], a[2]-b[2])


def vec_norm(v):
    return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)


# ===================== 제어 루프 =====================
# TODO: 학생이 구현할 부분!
#
# 아이디어:
#   1. deputy GPS ECI 위치 - chief TLE ECI 위치 = 상대 벡터 (ECI)
#   2. 상대 거리 = |delta_r|  (처음에 ~5 km)
#   3. 접근 전략:
#      - V-bar approach (along-track 방향으로 ΔV)
#      - chief 는 +y (or -y) 방향에 있으므로 fy_minus (or fy_plus) 추력
#      - 속도 제어: 너무 빠르면 감속, 너무 느리면 가속
#   4. 주의: TLE 는 ~1 km 오차! 근접 시 카메라 VBN 필요 (영상팀 연계)
#
# 지금은 상대 위치만 표시합니다.

print('[orbit] 상대 네비게이션 모니터 시작 (Ctrl+C 종료)')
print('  접근 제어 로직을 이 파일에 직접 구현하세요!\n')

try:
    while True:
        time.sleep(1.0)
        with lock:
            if 'gps_pos' in state and 'tle_pos' in state:
                dr = vec_sub(state['tle_pos'], state['gps_pos'])
                dist = vec_norm(dr)
                print(f'  상대벡터 ECI: ({dr[0]:+.0f}, {dr[1]:+.0f}, {dr[2]:+.0f}) m  '
                      f'거리: {dist:.0f} m ({dist/1000:.2f} km)')

                # ▼ 여기에 접근 제어 추가 ▼
                # 예시: chief 가 +y 방향이면 fy_minus 로 접근 (주석 해제)
                # if dist > 100:
                #     fire('fy_minus', 0.3)
                # else:
                #     stop_all()

            else:
                print('  (GPS 또는 TLE 대기 중...)')

except KeyboardInterrupt:
    stop_all()
    print('\n[orbit] 종료, 모든 추력기 정지')

client.terminate()
