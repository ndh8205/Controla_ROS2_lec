#!/usr/bin/env python3
"""[완성 예시] Vision — 카메라 관측 + 자동 스냅샷 캡처.

Vision 담당은 액추에이터를 직접 안 쓰고 "관측" 에만 집중. 이 예시는:
    1) 브라우저 자동 열기 (web_video_server 라이브 스트림)
    2) 일정 주기마다 JPEG 스냅샷 저장 (Formation 사진 6장 미션용)
    3) GPS + TLE 구독해서 chief 와의 거리 모니터
    4) 화면 가운데 픽셀 밝기로 "chief 보이는지" 간단 판정

고급 기능 (OpenCV 기반 chief 픽셀 위치 추적) 은 vision_practice.md 참고.

사용법:
    python3 vision_operator_example.py --host 220.67.219.55 --deputy deputy_formation
    python3 vision_operator_example.py --host 220.67.219.55 --deputy deputy_docking --snap-interval 5
"""

# ─────────────────────────────────────────────────────────────────────
# 1) Imports
#    os       : 폴더 생성
#    urllib.request : requests 라이브러리 없이도 HTTP GET 가능 (stdlib)
#    webbrowser : 사용자 기본 브라우저로 URL 열기
#    datetime : 파일명에 시각 넣기
#    roslibpy : ROS 토픽용 (센서 데이터)
# ─────────────────────────────────────────────────────────────────────
import argparse
import os
import time
import math
import webbrowser
from datetime import datetime
from threading import Lock
from urllib.request import urlopen
from urllib.error import URLError

import roslibpy


# ─────────────────────────────────────────────────────────────────────
# 2) 명령줄 인자
#    --snap-interval : 몇 초마다 스냅샷 저장할지 (0 = 저장 안 함)
#    --out           : 스냅샷 저장 폴더
#    --cam           : 관측 카메라 타입 (onboard = deputy 탑재 카메라,
#                      chase = 뒤따라 가는 3인칭 카메라)
# ─────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument('--host',   default='220.67.219.55')
ap.add_argument('--deputy', default='deputy_formation',
                choices=('deputy_formation', 'deputy_docking'))
ap.add_argument('--snap-interval', type=float, default=10.0,
                help='스냅샷 간격(초). 0 이면 안 저장.')
ap.add_argument('--out',    default='./captured_frames',
                help='스냅샷 저장 폴더.')
ap.add_argument('--cam',    default='onboard',
                choices=('onboard', 'chase', 'observer'),
                help='관측할 카메라 종류.')
args = ap.parse_args()


# ─────────────────────────────────────────────────────────────────────
# 3) 카메라 토픽 선택
#    deputy 와 --cam 조합으로 실제 ROS 토픽 이름 결정.
#    * onboard  : deputy 탑재 전방 카메라 (chief 관측용)
#    * chase    : deputy 뒤따라 다니는 3인칭
#    * observer : 월드에 고정된 외부 시점 (deputy 관측용)
# ─────────────────────────────────────────────────────────────────────
CAM_MAP = {
    'deputy_formation': {
        'onboard':  '/nasa_satellite/camera',
        'chase':    '/chase/formation/camera',
        'observer': '/observer/formation/camera',
    },
    'deputy_docking': {
        'onboard':  '/nasa_satellite2/camera',
        'chase':    '/chase/docking/camera',
        'observer': '/observer/docking/camera',
    },
}
CAM_TOPIC = CAM_MAP[args.deputy][args.cam]

# web_video_server URL — 브라우저 라이브 뷰 + HTTP snapshot API
STREAM_URL   = f'http://{args.host}:8080/stream_viewer?topic={CAM_TOPIC}&type=mjpeg'
SNAPSHOT_URL = f'http://{args.host}:8080/snapshot?topic={CAM_TOPIC}&type=jpeg'


# ─────────────────────────────────────────────────────────────────────
# 4) 저장 폴더 준비
#    os.makedirs(path, exist_ok=True) : 있어도 에러 안 냄.
# ─────────────────────────────────────────────────────────────────────
os.makedirs(args.out, exist_ok=True)
print(f'[vision] deputy={args.deputy}  cam={args.cam}  topic={CAM_TOPIC}')
print(f'[vision] 라이브 뷰: {STREAM_URL}')
print(f'[vision] 저장 폴더: {args.out}/  (간격 {args.snap_interval}s)')


# ─────────────────────────────────────────────────────────────────────
# 5) 브라우저 자동 오픈
#    webbrowser.open(URL) : 시스템 기본 브라우저에 탭 하나 연다.
#    실패해도 예외로 멈추지 않고 URL 안내만 출력.
# ─────────────────────────────────────────────────────────────────────
try:
    webbrowser.open(STREAM_URL)
    print('[vision] 브라우저에서 라이브 스트림 확인하세요.')
except Exception:
    print(f'[vision] 브라우저 자동 실행 실패. 수동으로 열기: {STREAM_URL}')


# ─────────────────────────────────────────────────────────────────────
# 6) rosbridge 접속 + 센서 구독
#    카메라 자체는 HTTP 로 받지만, "chief 까지의 거리" 를 표시하려면
#    GPS + TLE 를 ROS 에서 받아야 함.
# ─────────────────────────────────────────────────────────────────────
client = roslibpy.Ros(host=args.host, port=9090)
client.run()

state = {}
lock = Lock()

def on_gps(msg):
    p = msg['pose']['pose']['position']
    with lock:
        state['gps_pos'] = (p['x'], p['y'], p['z'])

def on_tle(msg):
    p = msg['pose']['pose']['position']
    with lock:
        state['tle_pos'] = (p['x'], p['y'], p['z'])

roslibpy.Topic(client, f'/{args.deputy}/gps/odometry',
               'nav_msgs/Odometry').subscribe(on_gps)
roslibpy.Topic(client, '/chief/eci_state',
               'nav_msgs/Odometry').subscribe(on_tle)


# ─────────────────────────────────────────────────────────────────────
# 7) HTTP 스냅샷 다운로드
#    web_video_server 의 /snapshot 엔드포인트는 호출 시점의 최신 프레임을
#    JPEG 로 리턴. requests 라이브러리 대신 stdlib urllib 사용 (추가 설치 불필요).
# ─────────────────────────────────────────────────────────────────────
def save_snapshot():
    """현재 카메라 프레임을 timestamp 파일로 저장. 성공 시 bytes 반환."""
    try:
        # timeout=3 : 3초 안에 응답 안 오면 포기 (네트워크 문제일 때 멈추지 않게)
        with urlopen(SNAPSHOT_URL, timeout=3) as resp:
            data = resp.read()
        # 파일명: chief_140532.jpg  (시간:분:초)
        name = datetime.now().strftime('%H%M%S')
        fname = os.path.join(args.out, f'{args.cam}_{name}.jpg')
        with open(fname, 'wb') as f:
            f.write(data)
        print(f'[vision] saved {fname}  ({len(data)} bytes)')
        return data
    except URLError as e:
        print(f'[vision] 스냅샷 실패: {e}')
        return None


# ─────────────────────────────────────────────────────────────────────
# 8) 간단한 "프레임 중앙이 밝은가?" 판정
#    JPEG 을 디코드하지 않고도 대략 판단이 필요하면: 파일 크기 작으면
#    "대부분 검은색" (압축 잘됨), 크면 "정보 많음". 완벽한 지표는 아니지만
#    OpenCV 없이 가능한 제일 간단한 방법.
#    고급판: vision_practice.md 의 OpenCV 예시 참고.
# ─────────────────────────────────────────────────────────────────────
def jpeg_hint(data):
    """매우 단순한 heuristic:
        파일 크기 < 5 KB  → 거의 단색 (chief 안 보임)
        파일 크기 > 15 KB → 디테일 많음 (chief 보일 가능성)
    """
    if data is None:
        return 'no_data'
    n = len(data)
    if n < 5000:
        return f'dark ({n}B)'
    if n < 15000:
        return f'dim  ({n}B)'
    return f'bright ({n}B)'


def norm3(v):
    return math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)


# ─────────────────────────────────────────────────────────────────────
# 9) 메인 루프 — 1 Hz print, 스냅샷 저장은 별도 주기
# ─────────────────────────────────────────────────────────────────────
print('[vision] 모니터 시작. Ctrl+C 로 종료.\n')
last_snap = 0.0
snap_count = 0

try:
    while True:
        time.sleep(1.0)
        now = time.time()

        # 상대 거리 출력
        with lock:
            gp = state.get('gps_pos')
            tp = state.get('tle_pos')
        if gp and tp:
            rel = (tp[0]-gp[0], tp[1]-gp[1], tp[2]-gp[2])
            dist = norm3(rel)
            print(f'[vision]  dist→chief = {dist:8.1f} m  '
                  f'rel=({rel[0]:+6.0f},{rel[1]:+6.0f},{rel[2]:+6.0f})')
        else:
            print('[vision]  GPS/TLE 수신 대기...')

        # 스냅샷 저장 타이밍
        if args.snap_interval > 0 and (now - last_snap) >= args.snap_interval:
            data = save_snapshot()
            print(f'          hint: {jpeg_hint(data)}')
            last_snap = now
            if data:
                snap_count += 1

except KeyboardInterrupt:
    print(f'\n[vision] 종료. 저장된 스냅샷: {snap_count} 장 → {args.out}/')
finally:
    client.terminate()
