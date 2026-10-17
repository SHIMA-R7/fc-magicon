"""Portable Windows USB desktop sender; no Python installation on target PC."""
import os,sys,subprocess,time
from pathlib import Path

def main():
    if len(sys.argv)>1 and sys.argv[1]=='--sender':
        sys.argv.pop(1)
        import remote_pc
        remote_pc.main();return
    import tkinter as tk
    from tkinter import ttk,messagebox
    from remote_pc import find_port
    from serial.tools import list_ports
    state=Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'FC-MAGICON';state.mkdir(exist_ok=True)
    root=tk.Tk();root.title('FC-MAGICON USB転送 r2.3');root.geometry('740x650')
    panel=ttk.Frame(root,padding=16);panel.pack(fill='both',expand=True)
    ttk.Label(panel,text='FMV → USB → FC-MAGICON',font=('',16)).pack(anchor='w')
    row=ttk.Frame(panel);row.pack(fill='x',pady=12)
    ttk.Label(row,text='USBポート').pack(side='left')
    port=tk.StringVar();ports=ttk.Combobox(row,textvariable=port,width=15);ports.pack(side='left',padx=8)
    nano_enabled=tk.BooleanVar(value=False);nano_port=tk.StringVar();nano_gain=tk.StringVar(value='6')
    def refresh():
        names=find_port();ports['values']=names
        if names and port.get() not in names:port.set(names[0])
        nano_names=[p.device for p in list_ports.comports() if p.vid is not None and p.device!=port.get()]
        nano_ports['values']=nano_names
        if nano_port.get() not in nano_names:nano_port.set(nano_names[0] if len(nano_names)==1 else '')
    ttk.Button(row,text='再検索',command=refresh).pack(side='left')
    ttk.Label(row,text='FPS').pack(side='left',padx=10)
    fps=tk.StringVar(value='8');ttk.Combobox(row,textvariable=fps,values=['4','8'],width=5).pack(side='left')
    audio=tk.BooleanVar(value=True)
    ttk.Checkbutton(panel,text='PCの再生音も転送する',variable=audio).pack(anchor='w')
    relative=tk.BooleanVar(value=False);quality=tk.BooleanVar(value=False)
    ttk.Checkbutton(panel,text='ゲーム向けマウス（相対移動）',variable=relative).pack(anchor='w')
    ttk.Checkbutton(panel,text='輪郭と四角い境目を優先（低速）',variable=quality).pack(anchor='w')
    nano_row=ttk.LabelFrame(panel,text='Nano単独・SFCマウス（専用ファームが必要）',padding=8);nano_row.pack(fill='x',pady=8)
    ttk.Checkbutton(nano_row,text='Nanoのマウスを使う',variable=nano_enabled).pack(side='left')
    nano_ports=ttk.Combobox(nano_row,textvariable=nano_port,width=12);nano_ports.pack(side='left',padx=8)
    ttk.Label(nano_row,text='感度').pack(side='left')
    ttk.Combobox(nano_row,textvariable=nano_gain,values=['1','3','6','12'],width=5).pack(side='left',padx=5)
    ttk.Label(panel,text='メイン画面全体をカラー・4:3全画面で転送します。\n十字キー：マウス移動、A：左クリック、B：右クリック。\nSELECT：通常 → 少しズーム（広め） → ズーム、START：追随ON/OFF。\nNano使用時はマウス操作をNanoへ切り替えます。FCのズーム・キーボードは併用可。\nFCキーボードには「r1＋キーボード」受信版を使用してください。',wraplength=650).pack(anchor='w',pady=10)
    buttons=ttk.Frame(panel);buttons.pack(fill='x')
    log=tk.Text(panel,height=9,wrap='word');log.pack(fill='both',expand=True,pady=8)
    process=None;handle=None;stop=None;path=None;position=0;closing=False
    def start(preview=False,nano_only=False):
        nonlocal process,handle,stop,path,position
        if process:return
        try:
            rate=float(fps.get())
            if not 0<rate<=8:raise ValueError('FPSは0より大きく8以下にしてください')
            if not preview and not nano_only and not port.get().upper().startswith('COM'):raise ValueError('RP2350のUSBポートを選択してください')
            use_nano=(nano_enabled.get() or nano_only) and not preview
            gain=float(nano_gain.get())
            if use_nano:
                if not nano_port.get().upper().startswith('COM'):raise ValueError('NanoのUSBポートを選択してください')
                if not nano_only and nano_port.get().upper()==port.get().upper():raise ValueError('NanoとRP2350には別のCOMポートを選択してください')
                if not 0<gain<=32:raise ValueError('Nano感度は0より大きく32以下にしてください')
        except ValueError as e:messagebox.showerror('設定',str(e));return
        stamp=time.time_ns();stop=state/f'usb-stop-{stamp}';path=state/f'usb-{stamp}.log';position=0
        args=['--color','--stretch','--fps',str(rate),'--audio','pcm8','--solid','--fit-tiles','--software-cursor','--capture-delay','1','--stop-file',str(stop),'--stop-screen']
        if relative.get():args.append('--relative-mouse')
        if quality.get():args.append('--seam-quality')
        if use_nano:args+=['--nano-port',nano_port.get(),'--nano-gain',str(gain)]
        if not audio.get():args.append('--no-audio')
        if nano_only:args+=['--nano-only']
        elif preview:args+=['--preview',str(state/'usb-preview.png')]
        else:args+=['--port',port.get()]
        command=[sys.executable]+([] if getattr(sys,'frozen',False) else [str(Path(__file__).resolve())])+['--sender']+args
        handle=path.open('w',encoding='utf-8')
        process=subprocess.Popen(command,stdout=handle,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW,env=dict(os.environ,PYTHONUNBUFFERED='1',PYTHONIOENCODING='utf-8'))
        root.iconify()
    def halt():
        if process and stop:stop.touch()
    def close():
        nonlocal closing
        closing=True;halt()
        if not process:root.destroy()
    def diagnose():
        from win_input_diagnostics import save_snapshot
        diagnostic=state/f'input-diagnostics-{time.time_ns()}.json'
        try:
            save_snapshot(diagnostic)
            log.insert('end',f'入力診断を保存: {diagnostic}\n');log.see('end')
            messagebox.showinfo('入力診断',f'診断結果を保存しました。\n{diagnostic}\nブルアカを起動した状態で採取してください。')
        except Exception as e:messagebox.showerror('入力診断',str(e))
    def poll():
        nonlocal process,handle,position
        if process:
            with path.open(encoding='utf-8',errors='replace') as f:
                f.seek(position);text=f.read();position=f.tell()
            if text:log.insert('end',text);log.see('end')
            if process.poll() is not None:
                log.insert('end',f'終了コード: {process.returncode}\nログ: {path}\n');handle.close();process=None
                if closing:root.destroy();return
                root.deiconify()
        root.after(200,poll)
    ttk.Button(buttons,text='転送開始',command=start).pack(side='left')
    ttk.Button(buttons,text='停止',command=halt).pack(side='left',padx=8)
    ttk.Button(buttons,text='転送なしプレビュー',command=lambda:start(True)).pack(side='left')
    ttk.Button(buttons,text='Nanoマウスのみ',command=lambda:start(nano_only=True)).pack(side='left',padx=8)
    ttk.Button(buttons,text='入力診断',command=diagnose).pack(side='left')
    refresh();root.protocol('WM_DELETE_WINDOW',close);root.after(200,poll);root.mainloop()

if __name__=='__main__':main()
