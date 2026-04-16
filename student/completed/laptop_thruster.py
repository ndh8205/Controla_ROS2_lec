#!/usr/bin/env python3
"""[완성] 노트북 → 플랫샛 deputy 추력기 점화 (rosbridge).

사용법:
    python3 laptop_thruster.py --host 192.168.0.54 \
        --deputy deputy_docking --axis fy_plus --throttle 0.5 --duration 2
"""
import argparse, time, roslibpy

AXES = ('fx_plus','fx_minus','fy_plus','fy_minus','fz_plus','fz_minus')

ap = argparse.ArgumentParser()
ap.add_argument('--host',     default='192.168.0.54')
ap.add_argument('--deputy',   default='deputy_docking')
ap.add_argument('--axis',     choices=AXES, default='fy_plus')
ap.add_argument('--throttle', type=float,   default=0.5)
ap.add_argument('--duration', type=float,   default=2.0)
args = ap.parse_args()

client = roslibpy.Ros(host=args.host, port=9090); client.run()
topic  = f'/{args.deputy}/thruster/{args.axis}/cmd'
pub    = roslibpy.Topic(client, topic, 'std_msgs/Float32')

print(f'[fire] {topic} throttle={args.throttle} for {args.duration}s')
t_end = time.time() + args.duration
while time.time() < t_end:
    pub.publish(roslibpy.Message({'data': float(args.throttle)}))
    time.sleep(0.05)
pub.publish(roslibpy.Message({'data': 0.0}))
print('[fire] stopped')
client.terminate()
