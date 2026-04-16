#!/usr/bin/env python3
"""[완성] 노트북 → 플랫샛 deputy 반작용휠 토크 (rosbridge).

사용법:
    python3 laptop_rw.py --host 192.168.0.54 \
        --deputy deputy_docking --axis z --torque 0.001 --duration 3
"""
import argparse, time, roslibpy

ap = argparse.ArgumentParser()
ap.add_argument('--host',     default='192.168.0.54')
ap.add_argument('--deputy',   default='deputy_docking')
ap.add_argument('--axis',     choices=('x','y','z'), default='z')
ap.add_argument('--torque',   type=float, default=0.001)
ap.add_argument('--duration', type=float, default=3.0)
args = ap.parse_args()

client = roslibpy.Ros(host=args.host, port=9090); client.run()
topic  = f'/{args.deputy}/rw/{args.axis}/cmd'
pub    = roslibpy.Topic(client, topic, 'std_msgs/Float32')

print(f'[rw] {topic} tau={args.torque} Nm for {args.duration}s')
t_end = time.time() + args.duration
while time.time() < t_end:
    pub.publish(roslibpy.Message({'data': float(args.torque)}))
    time.sleep(0.05)
pub.publish(roslibpy.Message({'data': 0.0}))
print('[rw] stopped')
client.terminate()
