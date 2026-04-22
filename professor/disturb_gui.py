#!/usr/bin/env python3
"""교수님 실습 방해 GUI — 노트북에서 roslibpy 경유로 플랫샛에 외란 주입.

기능:
    * 추력기 hold-to-fire  (6축 × 2 deputy)
    * 반작용휠 hold-to-apply (3축 × 2 deputy)
    * Chief TLE 노이즈 주입 (σ 상향 → 구독자 jitter 증폭)
    * Camera 블랙 프레임 주입 (시야 교란)
    * 모든 actuator 긴급 정지

설치 (노트북):
    pip3 install roslibpy --break-system-packages
    sudo apt install -y python3-tk   # tkinter (Windows 파이썬은 기본 포함)

사용법:
    python3 disturb_gui.py --host 220.67.219.55
    python3 disturb_gui.py --host localhost        # 서버 자체에서
"""
import argparse
import base64
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, scrolledtext
import threading

try:
    import roslibpy
except ImportError as e:
    raise SystemExit('roslibpy 필요: pip3 install roslibpy --break-system-packages')


# 한글·특수문자 렌더링 가능한 폰트. OS 별 우선순위.
_KOREAN_FONT_CANDIDATES = [
    'Malgun Gothic',        # Windows 기본 한글 글꼴
    'Noto Sans CJK KR',     # Linux (fonts-noto-cjk)
    'NanumGothic',          # Linux (fonts-nanum)
    'Apple SD Gothic Neo',  # macOS
    'AppleGothic',          # macOS fallback
    'Gulim', 'Dotum',       # Windows legacy
]
_FIXED_FONT_CANDIDATES = [
    'Consolas',             # Windows
    'Noto Sans Mono CJK KR',
    'D2Coding', 'NanumGothicCoding',
    'DejaVu Sans Mono',     # Linux
    'Menlo',                # macOS
]


def _pick_font(candidates, fallback):
    families = set(tkfont.families())
    for name in candidates:
        if name in families:
            return name
    return fallback


AXES_TH  = ('fx_plus', 'fx_minus', 'fy_plus', 'fy_minus', 'fz_plus', 'fz_minus')
AXES_RW  = ('x', 'y', 'z')
DEPUTIES = ('deputy_formation', 'deputy_docking')
CAM_TOPICS = [
    '/nasa_satellite/camera',
    '/nasa_satellite2/camera',
    '/observer/chief/camera',
    '/observer/formation/camera',
    '/observer/docking/camera',
]

# 블랙 프레임 해상도 (카메라 원본과 동일)
CAM_W, CAM_H = 640, 480


class DisturbGUI:
    def __init__(self, host):
        self.host = host
        self.client = None
        self.pubs = {}              # topic -> roslibpy.Topic
        self.active = {}            # topic -> {'value': float}  (hold-to-fire)
        self.cam_enabled = False
        self.cam_last = 0.0
        self.tle_enabled = False
        self.tle_last_state = None  # 마지막으로 수신한 진짜 /chief/eci_state
        self.tle_last_pub = 0.0

        # 순서 중요 — 폰트는 위젯 생성 전에 적용해야 ttk 위젯에도 반영됨
        self.root = tk.Tk()
        self.root.title(f'Professor Disturb Console — {self.host}:9090')
        self.root.geometry('620x820')
        self._apply_fonts()
        self._build_widgets()
        self._connect_async()
        # tick 루프는 반드시 메인 스레드에서 시작 (tkinter after 는 thread-unsafe).
        # 연결 전에도 tick 이 돌아야 연결 완료 즉시 publish 가능.
        self.root.after(100, self._schedule_tick)

    # --------- UI ---------
    def _build_widgets(self):
        self.target     = tk.StringVar(value='deputy_formation')
        self.throttle   = tk.DoubleVar(value=0.5)
        self.torque     = tk.DoubleVar(value=0.05)
        self.pos_sigma  = tk.DoubleVar(value=500.0)
        self.vel_sigma  = tk.DoubleVar(value=0.5)
        self.cam_topic  = tk.StringVar(value=CAM_TOPICS[0])
        self.cam_hz     = tk.DoubleVar(value=3.0)

        pad = {'padx': 6, 'pady': 4}

        # target
        f = ttk.LabelFrame(self.root, text='Target deputy')
        f.pack(fill='x', **pad)
        for d in DEPUTIES:
            ttk.Radiobutton(f, text=d, variable=self.target,
                            value=d).pack(side='left', padx=12, pady=4)

        # thruster
        f = ttk.LabelFrame(self.root, text='Thrusters  (hold to fire)')
        f.pack(fill='x', **pad)
        self._slider_row(f, 'throttle', self.throttle, 0.0, 1.0, 0, '.2f')
        bfr = ttk.Frame(f); bfr.grid(row=1, column=0, columnspan=3, sticky='w', pady=4)
        for i, ax in enumerate(AXES_TH):
            b = tk.Button(bfr, text=ax, bg='#ffdddd', width=9, relief='raised')
            b.grid(row=0, column=i, padx=2)
            b.bind('<ButtonPress-1>',   lambda e, a=ax: self._thrust_start(a))
            b.bind('<ButtonRelease-1>', lambda e, a=ax: self._thrust_stop(a))

        # RW
        f = ttk.LabelFrame(self.root, text='Reaction Wheels  (hold to apply)')
        f.pack(fill='x', **pad)
        self._slider_row(f, 'torque N·m', self.torque, -0.1, 0.1, 0, '+.3f')
        bfr = ttk.Frame(f); bfr.grid(row=1, column=0, columnspan=3, sticky='w', pady=4)
        for i, ax in enumerate(AXES_RW):
            b = tk.Button(bfr, text=f'rw/{ax}', bg='#ddddff', width=10, relief='raised')
            b.grid(row=0, column=i, padx=2)
            b.bind('<ButtonPress-1>',   lambda e, a=ax: self._rw_start(a))
            b.bind('<ButtonRelease-1>', lambda e, a=ax: self._rw_stop(a))

        # TLE noise
        f = ttk.LabelFrame(self.root, text='Chief TLE 노이즈 폭격 (σ 값만큼 가우시안 추가)')
        f.pack(fill='x', **pad)
        self._slider_row(f, 'pos σ (m)',    self.pos_sigma, 0, 5000, 0, '.0f')
        self._slider_row(f, 'vel σ (m/s)',  self.vel_sigma, 0, 10,   1, '.2f')
        self.tle_btn = tk.Button(f, text='TLE noise: OFF', bg='#cccccc',
                                 width=18, command=self._tle_toggle)
        self.tle_btn.grid(row=2, column=1, pady=4, sticky='w')

        # Camera
        f = ttk.LabelFrame(self.root, text='Camera 블랙 프레임 주입')
        f.pack(fill='x', **pad)
        ttk.Label(f, text='topic:').grid(row=0, column=0, sticky='w', padx=4)
        ttk.Combobox(f, textvariable=self.cam_topic, values=CAM_TOPICS,
                     width=35, state='readonly').grid(row=0, column=1, columnspan=2, sticky='w')
        self._slider_row(f, 'rate (Hz)', self.cam_hz, 1, 15, 1, '.0f')
        self.cam_btn = tk.Button(f, text='Camera inject: OFF', bg='#cccccc',
                                 width=20, command=self._cam_toggle)
        self.cam_btn.grid(row=2, column=1, pady=4, sticky='w')

        # Emergency
        f = ttk.LabelFrame(self.root, text='Emergency')
        f.pack(fill='x', **pad)
        tk.Button(f, text='STOP ALL ACTUATORS  (both deputies, all axes)',
                  bg='#ff3333', fg='white', font=('TkDefaultFont', 11, 'bold'),
                  command=self._stop_all).pack(fill='x', padx=8, pady=8)

        # Log
        f = ttk.LabelFrame(self.root, text='Log')
        f.pack(fill='both', expand=True, **pad)
        self.logbox = scrolledtext.ScrolledText(f, height=12, state='disabled',
                                                font=('TkFixedFont', 9))
        self.logbox.pack(fill='both', expand=True)

        self.status = tk.StringVar(value='connecting...')
        tk.Label(self.root, textvariable=self.status, anchor='w',
                 bg='#333', fg='#eee').pack(fill='x', side='bottom')

        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    def _apply_fonts(self):
        """한글·특수문자 렌더링 가능한 글꼴 자동 선택 + 3 경로 모두 적용.

        tkinter 폰트 시스템은 3 경로가 따로 있음:
          1) 이름있는 폰트 (TkDefaultFont 등) — 일반 tk 위젯의 기본
          2) option_add('*Font', ...) — tk 위젯의 저수준 기본
          3) ttk.Style().configure('.', font=...) — ttk 위젯
        한글이 박스로 보이는 건 ttk 위젯이 CJK 없는 폰트를 쓸 때 발생.
        세 경로 모두 바꿔야 LabelFrame 제목·라벨 등이 전부 한글 지원 폰트로.
        """
        fam = _pick_font(_KOREAN_FONT_CANDIDATES, None)
        fixed = _pick_font(_FIXED_FONT_CANDIDATES, None)
        size = 10

        if fam:
            # (1) 이름있는 폰트들
            for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont',
                         'TkHeadingFont', 'TkCaptionFont',
                         'TkSmallCaptionFont', 'TkIconFont', 'TkTooltipFont'):
                try:
                    tkfont.nametofont(name).configure(family=fam, size=size)
                except Exception:
                    pass
            # (2) tk 위젯 option DB
            self.root.option_add('*Font', (fam, size))
            # (3) ttk 위젯 스타일 — '.' 는 모든 ttk 기본
            style = ttk.Style()
            style.configure('.',               font=(fam, size))
            style.configure('TLabel',          font=(fam, size))
            style.configure('TButton',         font=(fam, size))
            style.configure('TRadiobutton',    font=(fam, size))
            style.configure('TCheckbutton',    font=(fam, size))
            style.configure('TLabelframe.Label', font=(fam, size, 'bold'))
            style.configure('TCombobox',       font=(fam, size))

        if fixed:
            try:
                tkfont.nametofont('TkFixedFont').configure(family=fixed,
                                                           size=max(9, size-1))
            except Exception:
                pass

        # 디버그용 폰트 목록 일부 로그
        available = sorted(tkfont.families())
        has_korean = [f for f in available if f in _KOREAN_FONT_CANDIDATES]
        print(f'[disturb_gui] picked default={fam} fixed={fixed}')
        print(f'[disturb_gui] Korean fonts available: {has_korean}')

    def _slider_row(self, parent, label, var, lo, hi, row, fmt):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', padx=4)
        ttk.Scale(parent, variable=var, from_=lo, to=hi, orient='horizontal',
                  length=320).grid(row=row, column=1, sticky='ew', padx=4)
        val = ttk.Label(parent, width=10)
        val.grid(row=row, column=2, sticky='w')

        def _upd(*_):
            val.configure(text=format(float(var.get()), fmt))
        var.trace_add('write', _upd)
        _upd()

    # --------- Connection ---------
    def _connect_async(self):
        def worker():
            try:
                self.client = roslibpy.Ros(host=self.host, port=9090)
                self.client.run()
                self.status.set(f'connected: {self.host}:9090')
                self._log(f'connected to {self.host}:9090')
                # Subscribe chief/eci_state for TLE noise mode
                sub = roslibpy.Topic(self.client, '/chief/eci_state',
                                     'nav_msgs/Odometry')
                sub.subscribe(self._on_chief_state)
            except Exception as e:
                self.status.set(f'CONNECT FAIL: {e}')
                self._log(f'connect fail: {e}')
        threading.Thread(target=worker, daemon=True).start()

    def _pub(self, topic, msg_type='std_msgs/Float32'):
        if topic not in self.pubs:
            self.pubs[topic] = roslibpy.Topic(self.client, topic, msg_type)
        return self.pubs[topic]

    def _log(self, msg):
        t = time.strftime('%H:%M:%S')
        self.logbox.configure(state='normal')
        self.logbox.insert('end', f'{t}  {msg}\n')
        self.logbox.see('end')
        # 최근 300줄만 유지
        total = int(self.logbox.index('end-1c').split('.')[0])
        if total > 300:
            self.logbox.delete('1.0', f'{total-300}.0')
        self.logbox.configure(state='disabled')

    # --------- Thruster ---------
    def _thrust_start(self, ax):
        topic = f'/{self.target.get()}/thruster/{ax}/cmd'
        self.active[topic] = {'value': float(self.throttle.get())}
        self._log(f'FIRE   {topic}  throttle={self.throttle.get():.2f}')

    def _thrust_stop(self, ax):
        topic = f'/{self.target.get()}/thruster/{ax}/cmd'
        self.active.pop(topic, None)
        self._send_zero(topic)
        self._log(f'stop   {topic}')

    # --------- RW ---------
    def _rw_start(self, ax):
        topic = f'/{self.target.get()}/rw/{ax}/cmd'
        self.active[topic] = {'value': float(self.torque.get())}
        self._log(f'TORQ   {topic}  τ={self.torque.get():+.3f} N·m')

    def _rw_stop(self, ax):
        topic = f'/{self.target.get()}/rw/{ax}/cmd'
        self.active.pop(topic, None)
        self._send_zero(topic)
        self._log(f'stop   {topic}')

    def _send_zero(self, topic):
        if not self.client or not self.client.is_connected:
            return
        pub = self._pub(topic)
        for _ in range(5):
            pub.publish(roslibpy.Message({'data': 0.0}))
            time.sleep(0.02)

    def _stop_all(self):
        self.active.clear()
        self.cam_enabled = False
        self.tle_enabled = False
        self.cam_btn.configure(text='Camera inject: OFF', bg='#cccccc')
        self.tle_btn.configure(text='TLE noise: OFF', bg='#cccccc')
        if self.client and self.client.is_connected:
            for dep in DEPUTIES:
                for ax in AXES_TH:
                    self._send_zero(f'/{dep}/thruster/{ax}/cmd')
                for ax in AXES_RW:
                    self._send_zero(f'/{dep}/rw/{ax}/cmd')
        self._log('STOP ALL — both deputies, all axes zeroed, noise/cam OFF')

    # --------- TLE noise ---------
    def _on_chief_state(self, msg):
        self.tle_last_state = msg

    def _tle_toggle(self):
        if not self.tle_enabled:
            self.tle_enabled = True
            self.tle_btn.configure(text='TLE noise: ON', bg='#ff9999')
            self._log(f'TLE noise ON  pos_σ={self.pos_sigma.get():.0f}m '
                      f'vel_σ={self.vel_sigma.get():.2f}m/s')
        else:
            self.tle_enabled = False
            self.tle_btn.configure(text='TLE noise: OFF', bg='#cccccc')
            self._log('TLE noise OFF')

    def _tle_publish_noisy(self):
        if not self.tle_last_state:
            return
        import random
        ps = float(self.pos_sigma.get())
        vs = float(self.vel_sigma.get())
        m = self.tle_last_state
        p = m['pose']['pose']['position']
        v = m['twist']['twist']['linear']
        fake = {
            'header': m.get('header', {'frame_id': 'j2000',
                                       'stamp': {'sec': 0, 'nanosec': 0}}),
            'child_frame_id': m.get('child_frame_id', ''),
            'pose': {
                'pose': {
                    'position': {
                        'x': p['x'] + random.gauss(0, ps),
                        'y': p['y'] + random.gauss(0, ps),
                        'z': p['z'] + random.gauss(0, ps),
                    },
                    'orientation': m['pose']['pose'].get(
                        'orientation', {'x':0,'y':0,'z':0,'w':1}),
                },
                'covariance': m['pose'].get('covariance', [0.0]*36),
            },
            'twist': {
                'twist': {
                    'linear': {
                        'x': v['x'] + random.gauss(0, vs),
                        'y': v['y'] + random.gauss(0, vs),
                        'z': v['z'] + random.gauss(0, vs),
                    },
                    'angular': m['twist']['twist'].get(
                        'angular', {'x':0,'y':0,'z':0}),
                },
                'covariance': m['twist'].get('covariance', [0.0]*36),
            },
        }
        try:
            self._pub('/chief/eci_state', 'nav_msgs/Odometry').publish(
                roslibpy.Message(fake))
        except Exception as e:
            self._log(f'TLE pub err: {e}')

    # --------- Camera inject ---------
    def _cam_toggle(self):
        if not self.cam_enabled:
            self.cam_enabled = True
            self.cam_btn.configure(text='Camera inject: ON', bg='#ff9999')
            self._log(f'CAM inject ON  {self.cam_topic.get()} @ {self.cam_hz.get():.0f} Hz')
        else:
            self.cam_enabled = False
            self.cam_btn.configure(text='Camera inject: OFF', bg='#cccccc')
            self._log('CAM inject OFF')

    _black_cache = None
    def _black_frame_payload(self):
        """Lazy-build 640x480 rgb8 black frame, base64 encoded."""
        if DisturbGUI._black_cache is None:
            data = bytes(CAM_W * CAM_H * 3)
            DisturbGUI._black_cache = base64.b64encode(data).decode('ascii')
        return DisturbGUI._black_cache

    def _cam_publish_black(self):
        topic = self.cam_topic.get()
        try:
            pub = self._pub(topic, 'sensor_msgs/Image')
            t = time.time()
            msg = {
                'header': {
                    'frame_id': 'prof_disturb',
                    'stamp': {'sec': int(t), 'nanosec': int((t - int(t))*1e9)},
                },
                'height': CAM_H,
                'width':  CAM_W,
                'encoding': 'rgb8',
                'is_bigendian': 0,
                'step': CAM_W * 3,
                'data': self._black_frame_payload(),
            }
            pub.publish(roslibpy.Message(msg))
        except Exception as e:
            self._log(f'cam pub err: {e}')

    # --------- Tick loop (50 ms) ---------
    def _schedule_tick(self):
        if not self.client or not self.client.is_connected:
            self.root.after(200, self._schedule_tick)
            return

        # actuator hold-to-fire republishing
        for topic, info in list(self.active.items()):
            try:
                self._pub(topic).publish(
                    roslibpy.Message({'data': float(info['value'])}))
            except Exception as e:
                self._log(f'pub err {topic}: {e}')

        now = time.time()
        # TLE noise
        if self.tle_enabled and (now - self.tle_last_pub) >= 0.05:
            self._tle_publish_noisy()
            self.tle_last_pub = now

        # Camera black frame
        if self.cam_enabled:
            interval = 1.0 / max(1, float(self.cam_hz.get()))
            if (now - self.cam_last) >= interval:
                self._cam_publish_black()
                self.cam_last = now

        self.root.after(50, self._schedule_tick)

    # --------- Close ---------
    def _on_close(self):
        try:
            self._stop_all()
        finally:
            try:
                if self.client:
                    self.client.terminate()
            except Exception:
                pass
            self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    ap = argparse.ArgumentParser(description='Professor disturbance GUI')
    ap.add_argument('--host', default='220.67.219.55',
                    help='rosbridge WebSocket host (default: 플랫샛 IP)')
    args = ap.parse_args()
    DisturbGUI(args.host).run()


if __name__ == '__main__':
    main()
