#!/usr/bin/env python3
"""[완성] 노트북 → 플랫샛 deputy 센서 통합 모니터 (rosbridge).

모든 센서를 구독하고 0.5초마다 한 줄씩 출력:
  - IMU: 자이로 (angular_velocity) + 가속도계 (linear_acceleration)
  - Star Tracker: body-in-ECI 쿼터니언
  - GPS: ECI 위치 + 속도
  - Chief TLE: 추정 ECI 위치 (노이즈 포함)
  - Sun: LVLH 방향 벡터
  - 상대 거리: GPS - TLE (deputy 에서 본 chief 까지 거리 추정)

사용법:
    python3 laptop_monitor.py --host 192.168.0.54 --deputy deputy_formation
"""
import argparse
import math
import time
from threading import Lock

import roslibpy

# ===================== 인자 파싱 =====================
ap = argparse.ArgumentParser(description='Deputy 센서 통합 모니터')
ap.add_argument('--host',   default='192.168.0.54',
                help='플랫샛 IP (rosbridge 서버)')
ap.add_argument('--deputy', default='deputy_formation',
                choices=('deputy_formation', 'deputy_docking'),
                help='모니터할 deputy 이름')
args = ap.parse_args()

# ===================== rosbridge 접속 =====================
client = roslibpy.Ros(host=args.host, port=9090)
client.run()

state = {}
lock = Lock()


def put(k, v):
    with lock:
        state[k] = v


# ===================== 토픽 구독 =====================
d = args.deputy

# IMU: 자이로 (rad/s, body frame) + 가속도계 (m/s^2, body frame)
# 가속도계는 비중력 specific force (추력/외란만, CW pseudo-accel 제거됨)
roslibpy.Topic(client, f'/{d}/imu/data',
               'sensor_msgs/Imu').subscribe(lambda m: put('imu', m))

# Star Tracker: body-in-ECI 쿼터니언 (x, y, z, w)
# frame_id = "eci" → 이 쿼터니언으로 body→ECI 변환 가능
roslibpy.Topic(client, f'/{d}/star_tracker/attitude',
               'geometry_msgs/QuaternionStamped').subscribe(
                   lambda m: put('st', m))

# GPS: deputy 의 ECI 위치 (m) + 속도 (m/s) + Gaussian 노이즈
roslibpy.Topic(client, f'/{d}/gps/odometry',
               'nav_msgs/Odometry').subscribe(lambda m: put('gps', m))

# Chief TLE 추정: SGP4 전파 + 노이즈 (학생이 아는 유일한 chief 정보)
roslibpy.Topic(client, '/chief/eci_state',
               'nav_msgs/Odometry').subscribe(lambda m: put('tle', m))

# Sun 벡터: LVLH 프레임 단위벡터 (태양센서/전력 계획용)
roslibpy.Topic(client, '/chief/sun_vector_lvlh',
               'geometry_msgs/Vector3Stamped').subscribe(
                   lambda m: put('sun', m))

# ===================== 출력 루프 =====================
print(f'[monitor] {d} @ {args.host}:9090 (Ctrl+C 종료)\n')
print('  [IMU] gyro=자이로(rad/s)  accel=가속도계(m/s^2)')
print('  [ST]  q=body-in-ECI 쿼터니언')
print('  [GPS] r=ECI위치(km)  v=ECI속도(m/s)')
print('  [TLE] chief 추정위치  [REL] 상대거리')
print('  [SUN] LVLH 태양방향')
print()

try:
    while True:
        time.sleep(0.5)
        with lock:
            lines = []

            # --- IMU (자이로 + 가속도계) ---
            if 'imu' in state:
                g = state['imu']['angular_velocity']
                a = state['imu']['linear_acceleration']
                lines.append(
                    f"  [IMU] gyro=({g['x']:+.2e},{g['y']:+.2e},{g['z']:+.2e}) "
                    f"accel=({a['x']:+.2e},{a['y']:+.2e},{a['z']:+.2e})")

            # --- Star Tracker ---
            if 'st' in state:
                q = state['st']['quaternion']
                lines.append(
                    f"  [ST]  q=({q['x']:+.4f},{q['y']:+.4f},"
                    f"{q['z']:+.4f},{q['w']:+.4f})")

            # --- GPS (위치 + 속도) ---
            if 'gps' in state:
                p = state['gps']['pose']['pose']['position']
                v = state['gps']['twist']['twist']['linear']
                r_km = math.sqrt(p['x']**2 + p['y']**2 + p['z']**2) / 1000
                v_ms = math.sqrt(v['x']**2 + v['y']**2 + v['z']**2)
                lines.append(
                    f"  [GPS] r=({p['x']/1000:+.1f},{p['y']/1000:+.1f},"
                    f"{p['z']/1000:+.1f}) km  |r|={r_km:.1f} km  "
                    f"|v|={v_ms:.1f} m/s")

            # --- Chief TLE + 상대 거리 ---
            if 'tle' in state:
                tp = state['tle']['pose']['pose']['position']
                lines.append(
                    f"  [TLE] chief=({tp['x']/1000:+.1f},{tp['y']/1000:+.1f},"
                    f"{tp['z']/1000:+.1f}) km")

            if 'gps' in state and 'tle' in state:
                gp = state['gps']['pose']['pose']['position']
                tp = state['tle']['pose']['pose']['position']
                dr = math.sqrt(sum((tp[k]-gp[k])**2 for k in ('x','y','z')))
                lines.append(
                    f"  [REL] chief까지 ≈ {dr:.0f} m ({dr/1000:.2f} km)")

            # --- Sun ---
            if 'sun' in state:
                s = state['sun']['vector']
                lines.append(
                    f"  [SUN] lvlh=({s['x']:+.3f},{s['y']:+.3f},{s['z']:+.3f})")

        if lines:
            print(f'--- {d} ---')
            for l in lines:
                print(l)
        else:
            print('  (토픽 대기 중...)')

except KeyboardInterrupt:
    pass

client.terminate()
