#!/usr/bin/env python3
"""[완성] 노트북 → 플랫샛 deputy 센서 통합 모니터 (rosbridge).

모든 센서 (IMU, ST, GPS, TLE chief, sun) 를 구독해서 0.5초마다 한 줄씩 출력.

사용법:
    python3 laptop_monitor.py --host 192.168.0.54 --deputy deputy_formation
"""
import argparse, math, time
from threading import Lock
import roslibpy

ap = argparse.ArgumentParser()
ap.add_argument('--host',   default='192.168.0.54')
ap.add_argument('--deputy', default='deputy_formation',
                choices=('deputy_formation', 'deputy_docking'))
args = ap.parse_args()

client = roslibpy.Ros(host=args.host, port=9090); client.run()
state, lock = {}, Lock()
def put(k, v):
    with lock: state[k] = v

d = args.deputy
roslibpy.Topic(client, f'/{d}/imu/data',
               'sensor_msgs/Imu').subscribe(lambda m: put('imu', m))
roslibpy.Topic(client, f'/{d}/star_tracker/attitude',
               'geometry_msgs/QuaternionStamped').subscribe(
                   lambda m: put('st', m))
roslibpy.Topic(client, f'/{d}/gps/odometry',
               'nav_msgs/Odometry').subscribe(lambda m: put('gps', m))
roslibpy.Topic(client, '/chief/eci_state',
               'nav_msgs/Odometry').subscribe(lambda m: put('tle', m))
roslibpy.Topic(client, '/chief/sun_vector_lvlh',
               'geometry_msgs/Vector3Stamped').subscribe(
                   lambda m: put('sun', m))

print(f'[monitor] {d} @ {args.host}:9090 (Ctrl+C 종료)')
try:
    while True:
        time.sleep(0.5)
        with lock:
            parts = []
            if 'imu' in state:
                g = state['imu']['angular_velocity']
                parts.append(
                    f"gyro=({g['x']:+.2e},{g['y']:+.2e},{g['z']:+.2e})")
            if 'st' in state:
                q = state['st']['quaternion']
                parts.append(
                    f"q=({q['x']:+.3f},{q['y']:+.3f},{q['z']:+.3f},{q['w']:+.3f})")
            if 'gps' in state:
                p = state['gps']['pose']['pose']['position']
                r = math.sqrt(p['x']**2 + p['y']**2 + p['z']**2)
                parts.append(f"|r_ECI|={r/1000:.1f}km")
            if 'tle' in state and 'gps' in state:
                tp = state['tle']['pose']['pose']['position']
                gp = state['gps']['pose']['pose']['position']
                dr = math.sqrt(sum((tp[k]-gp[k])**2
                    for k in ('x','y','z')))
                parts.append(f"chief거리≈{dr:.0f}m")
            if 'sun' in state:
                s = state['sun']['vector']
                parts.append(
                    f"sun=({s['x']:+.2f},{s['y']:+.2f},{s['z']:+.2f})")
        if parts:
            print('  ' + '  '.join(parts))
        else:
            print('  (토픽 대기 중...)')
except KeyboardInterrupt:
    pass
client.terminate()
