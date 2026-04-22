#!/usr/bin/env python3
"""노트북 → 플랫샛 deputy 반작용휠 토크 명령 (rosbridge 경유).

사용법:
    python3 laptop_rw.py --host 192.168.0.54 \
        --deputy deputy_formation --axis z --torque 0.1 --duration 5

인자:
    --host      rosbridge WebSocket 서버 IP (플랫샛 기본 192.168.0.54)
    --deputy    deputy_formation | deputy_docking
    --axis      x | y | z  (x=roll, y=pitch, z=yaw, body frame)
    --torque    부호 있는 N·m 값. 플러그인이 ±0.1 N·m 로 clamp.
                100 kg 위성 (Izz=10 kg·m²) 기준 max 토크 → α = 0.01 rad/s².
                예: 5 s 분사 → ω ≈ 0.05 rad/s (~3°/s).
    --duration  분사 시간 (s). 종료 후에도 ω 는 보존되므로 반대 부호
                토크로 동일 시간 분사해야 정지.

주의:
    * 추력기와 달리 반작용휠은 각운동량 보존됨 → 명령 끄면 자동으로
      안 멈추고 회전 유지. detumble 하려면 반대 부호로 한 번 더.
"""
import argparse
import time
import roslibpy

ap = argparse.ArgumentParser(description='Reaction wheel torque command')
ap.add_argument('--host',     default='192.168.0.54')
ap.add_argument('--deputy',   default='deputy_formation',
                choices=('deputy_formation', 'deputy_docking'))
ap.add_argument('--axis',     default='z', choices=('x', 'y', 'z'))
ap.add_argument('--torque',   type=float, default=0.1,
                help='N·m, plugin clamps to ±0.1')
ap.add_argument('--duration', type=float, default=5.0, help='seconds')
args = ap.parse_args()

client = roslibpy.Ros(host=args.host, port=9090)
client.run()
topic = f'/{args.deputy}/rw/{args.axis}/cmd'
pub = roslibpy.Topic(client, topic, 'std_msgs/Float32')

print(f'[rw] {topic}  tau={args.torque} N*m  for {args.duration}s')
t_end = time.time() + args.duration
try:
    while time.time() < t_end:
        pub.publish(roslibpy.Message({'data': float(args.torque)}))
        time.sleep(0.05)
finally:
    # stop 메시지는 WebSocket flush race 때문에 1회 발행으로는 plugin 에
    # 도달하지 못할 수 있음. 5회 반복 + 100 ms 간격으로 확실히 전달.
    for _ in range(5):
        pub.publish(roslibpy.Message({'data': 0.0}))
        time.sleep(0.1)
    print('[rw] stopped')
    client.terminate()
