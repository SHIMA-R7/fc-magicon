"""Windows sender launcher; --sender runs remote_pc in an isolated process."""
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time

STATE = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'FC-MAGICON'


def sender_arguments(settings):
    host = settings['host'].strip()
    if not host or any(c.isspace() for c in host) or host.startswith('-'):
        raise ValueError('C6のIPアドレス、または fc-magicon.local を入力してください')
    fps = float(settings['fps'])
    if not 0 < fps <= 60:
        raise ValueError('FPSは0より大きく60以下にしてください')
    args = ['--tcp', host, '--fps', str(fps), '--audio', 'pcm8']
    for key, flag in [('color', '--color'), ('stretch', '--stretch'),
                      ('chunked', '--chunked')]:
        if settings[key]:
            args.append(flag)
    if not settings['audio']:
        args.append('--no-audio')
    if not settings['input']:
        args.append('--no-input')
    return args


def child_command(args):
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--sender', *args]
    return [sys.executable, str(Path(__file__).resolve()), '--sender', *args]


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--sender':
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        import remote_pc
        remote_pc.main()
        return
    import tkinter as tk
    from tkinter import ttk, messagebox
    if getattr(sys, 'frozen', False):
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
    STATE.mkdir(parents=True, exist_ok=True)
    defaults = dict(host='fc-magicon.local', fps='8', color=True, stretch=True,
                    audio=True, input=True, chunked=False)
    config = STATE / 'wifi-settings.json'
    try:
        saved = json.loads(config.read_text(encoding='utf-8'))
        defaults.update({k: saved[k] for k in defaults if k in saved})
    except (OSError, ValueError, TypeError):
        pass
    root = tk.Tk()
    root.title('FC-MAGICON Wi-Fi送信 — Windows 11')
    root.geometry('740x580')
    vars = {k: (tk.BooleanVar(value=v) if isinstance(v, bool) else tk.StringVar(value=v))
            for k, v in defaults.items()}
    panel = ttk.Frame(root, padding=16)
    panel.pack(fill='both', expand=True)
    ttk.Label(panel, text='PC → Wi-Fi → ESP32-C6 → カセット', font=('', 15)).pack(anchor='w')
    row = ttk.Frame(panel)
    row.pack(fill='x', pady=12)
    ttk.Label(row, text='C6のIP / ホスト名').pack(side='left')
    ttk.Entry(row, textvariable=vars['host'], width=30).pack(side='left', padx=8)
    ttk.Label(row, text='FPS').pack(side='left')
    ttk.Combobox(row, textvariable=vars['fps'], values=['4', '8', '10', '15', '20'], width=5).pack(side='left', padx=6)
    for key, label in [('color', 'カラー'), ('stretch', '4:3全画面に変形'),
                       ('audio', 'PCの再生音も送る'), ('input', 'FCからマウス・キー操作'),
                       ('chunked', '分割プロトコル（対応受信ファーム専用）')]:
        ttk.Checkbutton(panel, text=label, variable=vars[key]).pack(anchor='w')
    ttk.Label(panel, text='メイン画面全体と既定出力の音を送ります。ブルアカはメイン画面に表示してください。\n'
              'C6は2.4GHzのWi-Fiへ接続。RP2350はUSBホストの受信ファームが必要です。\n'
              '接続確認はTCPのみ。FCでの表示・音声成功を保証するものではありません。',
              wraplength=700).pack(anchor='w', pady=10)
    buttons = ttk.Frame(panel)
    buttons.pack(fill='x')
    log = tk.Text(panel, height=12, state='disabled', wrap='word')
    log.pack(fill='both', expand=True, pady=10)
    events = queue.Queue()
    process = None
    stop_path = None
    log_file = None
    closing = False

    def append(text):
        log.configure(state='normal')
        log.insert('end', text.rstrip() + '\n')
        log.see('end')
        log.configure(state='disabled')

    def settings():
        return {k: v.get() for k, v in vars.items()}

    def check():
        try:
            host = settings()['host'].strip()
            sender_arguments(settings())
        except ValueError as e:
            messagebox.showerror('設定', str(e))
            return
        def worker():
            try:
                with socket.create_connection((host, 5000), timeout=5):
                    events.put('TCP接続成功。C6への到達のみ確認しました。')
            except OSError as e:
                events.put(f'接続できません: {e}\n同じLAN・C6のIP・ゲストWi-Fiの端末間隔離を確認してください。')
        threading.Thread(target=worker, daemon=True).start()

    def start(preview=False):
        nonlocal process, stop_path, log_file
        if process is not None:
            return
        try:
            values = settings()
            args = sender_arguments(values)
        except ValueError as e:
            messagebox.showerror('設定', str(e))
            return
        config.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
        stamp = time.time_ns()
        stop_path = STATE / f'stop-{stamp}'
        args += ['--stop-file', str(stop_path), '--capture-delay', '1']
        preview_path = STATE / 'preview.png'
        if preview:
            args += ['--preview', str(preview_path)]
        logfile_path = STATE / f'wifi-{stamp}.log'
        log_file = logfile_path.open('w', encoding='utf-8')
        env = dict(os.environ, PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
        try:
            process = subprocess.Popen(child_command(args), stdout=log_file, stderr=subprocess.STDOUT,
                                       env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as e:
            log_file.close()
            messagebox.showerror('起動できません', str(e))
            return
        start_button.configure(state='disabled')
        preview_button.configure(state='disabled')
        append(f'開始。ログ: {logfile_path}')
        root.iconify()
        def monitor():
            position = 0
            while process.poll() is None:
                with logfile_path.open(encoding='utf-8', errors='replace') as f:
                    f.seek(position)
                    text = f.read()
                    position = f.tell()
                if text:
                    events.put(text)
                time.sleep(0.2)
            with logfile_path.open(encoding='utf-8', errors='replace') as f:
                f.seek(position)
                events.put(f.read())
            events.put(('done', process.returncode, str(preview_path) if preview else None))
        threading.Thread(target=monitor, daemon=True).start()

    def stop():
        if process is not None and stop_path:
            stop_path.touch()
            append('停止を要求しました。')

    def close():
        nonlocal closing
        if process is None:
            root.destroy()
        else:
            closing = True
            stop()

    def poll():
        nonlocal process, log_file
        while not events.empty():
            event = events.get()
            if isinstance(event, tuple):
                _, code, preview = event
                process = None
                log_file.close()
                if stop_path.exists():
                    stop_path.unlink()
                append(f'終了（コード {code}）')
                start_button.configure(state='normal')
                preview_button.configure(state='normal')
                root.deiconify()
                if preview and code == 0:
                    os.startfile(preview)
                if closing:
                    root.destroy()
                    return
            elif event:
                append(event)
        root.after(200, poll)

    ttk.Button(buttons, text='接続確認', command=check).pack(side='left')
    preview_button = ttk.Button(buttons, text='転送なしプレビュー', command=lambda: start(True))
    preview_button.pack(side='left', padx=8)
    start_button = ttk.Button(buttons, text='転送開始', command=start)
    start_button.pack(side='left')
    ttk.Button(buttons, text='停止', command=stop).pack(side='left', padx=8)
    root.protocol('WM_DELETE_WINDOW', close)
    if '--gui-smoke' in sys.argv:
        root.after(1000, close)
    poll()
    root.mainloop()


if __name__ == '__main__':
    main()
