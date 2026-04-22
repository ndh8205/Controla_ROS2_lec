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

UI 는 영문 라벨로 통일 (플랫폼별 한글 폰트 이슈 회피). 여기 docstring,
코드 주석은 한국어 유지.
"""
import argparse
import base64
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext

try:
    import roslibpy
except ImportError:
    raise SystemExit('roslibpy required: pip3 install roslibpy --break-system-packages')


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

CAM_W, CAM_H = 640, 480   # black frame 해상도


class DisturbGUI:
    def __init__(self, host):
        self.host = host
        self.client = None
        self.pubs = {}              # topic -> roslibpy.Topic
        self.active = {}            # topic -> {'value': float}
        self.cam_enabled = False
        self.cam_last = 0.0
        self.tle_enabled = False
        self.tle_last_state = None
        self.tle_last_pub = 0.0

        self.root = tk.Tk()
        self.root.title(f'Professor Disturb Console - {self.host}:9090')
        self.root.geometry('620x780')
        self._build_widgets()
        self._connect_async()
        # tick 은 메인 스레드에서 시작 (tkinter after 는 thread-unsafe)
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

        # thrusters
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
        self._slider_row(f, 'torque [N*m]', self.torque, -0.1, 0.1, 0, '+.3f')
        bfr = ttk.Frame(f); bfr.grid(row=1, column=0, columnspan=3, sticky='w', pady=4)
        for i, ax in enumerate(AXES_RW):
            b = tk.Button(bfr, text=f'rw/{ax}', bg='#ddddff', width=10, relief='raised')
            b.grid(row=0, column=i, padx=2)
            b.bind('<ButtonPress-1>',   lambda e, a=ax: self._rw_start(a))
            b.bind('<ButtonRelease-1>', lambda e, a=ax: self._rw_stop(a))

        # TLE noise
        f = ttk.LabelFrame(self.root,
                           text='Chief TLE noise bombard (Gaussian added on top)')
        f.pack(fill='x', **pad)
        self._slider_row(f, 'pos sigma [m]',   self.pos_sigma, 0, 5000, 0, '.0f')
        self._slider_row(f, 'vel sigma [m/s]', self.vel_sigma, 0, 10,   1, '.2f')
        self.tle_btn = tk.Button(f, text='TLE noise: OFF', bg='#cccccc',
                                 width=18, command=self._tle_toggle)
        self.tle_btn.grid(row=2, column=1, pady=4, sticky='w')

        # Camera
        f = ttk.LabelFrame(self.root, text='Camera black-frame inject')
        f.pack(fill='x', **pad)
        ttk.Label(f, text='topic:').grid(row=0, column=0, sticky='w', padx=4)
        ttk.Combobox(f, textvariable=self.cam_topic, values=CAM_TOPICS,
                     width=35, state='readonly').grid(row=0, column=1,
                                                      columnspan=2, sticky='w')
        self._slider_row(f, 'rate [Hz]', self.cam_hz, 1, 15, 1, '.0f')
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
        self._log(f'TORQ   {topic}  tau={self.torque.get():+.3f} N*m')

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
        self._log('STOP ALL - both deputies, all axes zeroed, noise/cam OFF')

    # --------- TLE noise ---------
    def _on_chief_state(self, msg):
        self.tle_last_state = msg

    def _tle_toggle(self):
        if not self.tle_enabled:
            self.tle_enabled = True
            self.tle_btn.configure(text='TLE noise: ON', bg='#ff9999')
            self._log(f'TLE noise ON  pos_sigma={self.pos_sigma.get():.0f}m '
                      f'vel_sigma={self.vel_sigma.get():.2f}m/s')
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
                        'orientation', {'x': 0, 'y': 0, 'z': 0, 'w': 1}),
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
                        'angular', {'x': 0, 'y': 0, 'z': 0}),
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
            self._log(f'CAM inject ON  {self.cam_topic.get()} @ '
                      f'{self.cam_hz.get():.0f} Hz')
        else:
            self.cam_enabled = False
            self.cam_btn.configure(text='Camera inject: OFF', bg='#cccccc')
            self._log('CAM inject OFF')

    _black_cache = None
    def _black_frame_payload(self):
        """640x480 rgb8 올제로 프레임을 1회 만들어 base64 캐시."""
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
        if self.tle_enabled and (now - self.tle_last_pub) >= 0.05:
            self._tle_publish_noisy()
            self.tle_last_pub = now

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
                    help='rosbridge WebSocket host')
    args = ap.parse_args()
    DisturbGUI(args.host).run()


if __name__ == '__main__':
    main()
