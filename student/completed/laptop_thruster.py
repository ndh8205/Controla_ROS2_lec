#!/usr/bin/env python3
"""노트북 → 플랫샛 deputy 추력기 점화 명령 (rosbridge 경유).

사용법:
    python3 laptop_thruster.py --host 192.168.0.54 \
        --deputy deputy_docking --axis fy_plus --throttle 1.0 --duration 2

인자:
    --host      rosbridge WebSocket 서버 IP (플랫샛 기본 192.168.0.54)
    --deputy    deputy_formation | deputy_docking
    --axis      fx_plus | fx_minus | fy_plus | fy_minus | fz_plus | fz_minus
                body frame 방향 (각 ±축 = 6개 추력기)
    --throttle  [0, 1] 범위. max_force = 10 N 기준 실제 힘 = throttle × 10 N.
                100 kg 위성 → 가속도 a = throttle × 0.1 m/s².
                예: throttle=1.0 × 2 s → Δv = 0.2 m/s.
    --duration  분사 시간 (s).

주의:
    * 우주 공간이라 분사 종료 후에도 관성으로 계속 이동 → 반대 방향
      추력기로 같은 Δv 분사해야 정지.
    * CW 동역학에 의해 radial (x) 분사는 y 방향으로 커플링됨 (non-trivial).
      단순 이동은 cross-track (z) 방향이 가장 깔끔.
"""
import argparse
import time
import roslibpy

AXES = ('fx_plus', 'fx_minus', 'fy_plus', 'fy_minus', 'fz_plus', 'fz_minus')

ap = argparse.ArgumentParser(description='Thruster fire command')
ap.add_argument('--host',     default='192.168.0.54')
ap.add_argument('--deputy',   default='deputy_docking',
                choices=('deputy_formation', 'deputy_docking'))
ap.add_argument('--axis',     default='fy_plus', choices=AXES)
ap.add_argument('--throttle', type=float, default=1.0,
                help='[0, 1] fraction of max_force (10 N)')
ap.add_argument('--duration', type=float, default=2.0, help='seconds')
args = ap.parse_args()

client = roslibpy.Ros(host=args.host, port=9090)
client.run()
topic = f'/{args.deputy}/thruster/{args.axis}/cmd'
pub = roslibpy.Topic(client, topic, 'std_msgs/Float32')

print(f'[fire] {topic}  throttle={args.throttle}  for {args.duration}s')
t_end = time.time() + args.duration
try:
    while time.time() < t_end:
        pub.publish(roslibpy.Message({'data': float(args.throttle)}))
        time.sleep(0.05)
finally:
    # stop 메시지 race 방지 — 5회 반복 + 100 ms 간격
    for _ in range(5):
        pub.publish(roslibpy.Message({'data': 0.0}))
        time.sleep(0.1)
    print('[fire] stopped')
    client.terminate()
