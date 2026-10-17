"""Read-only Windows input context; does not inject input or elevate processes."""
import csv
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import threading

kernel=C.WinDLL('kernel32',use_last_error=True)
advapi=C.WinDLL('advapi32',use_last_error=True)
user=C.WinDLL('user32',use_last_error=True)
kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];kernel.OpenProcess.restype=W.HANDLE
kernel.CloseHandle.argtypes=[W.HANDLE];kernel.CloseHandle.restype=W.BOOL
kernel.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,C.POINTER(W.DWORD)]
advapi.OpenProcessToken.argtypes=[W.HANDLE,W.DWORD,C.POINTER(W.HANDLE)];advapi.OpenProcessToken.restype=W.BOOL
advapi.GetTokenInformation.argtypes=[W.HANDLE,C.c_int,C.c_void_p,W.DWORD,C.POINTER(W.DWORD)]
advapi.GetSidSubAuthorityCount.argtypes=[C.c_void_p];advapi.GetSidSubAuthorityCount.restype=C.POINTER(C.c_ubyte)
advapi.GetSidSubAuthority.argtypes=[C.c_void_p,W.DWORD];advapi.GetSidSubAuthority.restype=C.POINTER(W.DWORD)
user.GetForegroundWindow.restype=W.HWND
user.GetWindowThreadProcessId.argtypes=[W.HWND,C.POINTER(W.DWORD)]

def foreground_pid():
    pid=W.DWORD();user.GetWindowThreadProcessId(user.GetForegroundWindow(),C.byref(pid));return pid.value

def identity(pid):
    result={'pid':pid,'name':None,'integrity_rid':None,'elevated':None}
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:result['query_error']=C.get_last_error();return result
    token=W.HANDLE()
    try:
        name=C.create_unicode_buffer(32768);length=W.DWORD(len(name))
        if kernel.QueryFullProcessImageNameW(handle,0,name,C.byref(length)):result['name']=Path(name.value).name
        if not advapi.OpenProcessToken(handle,8,C.byref(token)):
            result['token_error']=C.get_last_error();return result
        value=W.DWORD();needed=W.DWORD()
        if advapi.GetTokenInformation(token,20,C.byref(value),C.sizeof(value),C.byref(needed)):
            result['elevated']=bool(value.value)
        advapi.GetTokenInformation(token,25,None,0,C.byref(needed))
        if 0<needed.value<4096:
            buffer=C.create_string_buffer(needed.value)
            if advapi.GetTokenInformation(token,25,buffer,len(buffer),C.byref(needed)):
                sid=C.cast(buffer,C.POINTER(C.c_void_p))[0]
                count=advapi.GetSidSubAuthorityCount(sid)[0]
                if count:result['integrity_rid']=advapi.GetSidSubAuthority(sid,count-1)[0]
        return result
    finally:
        if token:kernel.CloseHandle(token)
        kernel.CloseHandle(handle)

def context():
    own=identity(os.getpid());target=identity(foreground_pid())
    a,b=own['integrity_rid'],target['integrity_rid']
    return {'sender':own,'foreground':target,'target_higher_integrity':b>a if a is not None and b is not None else None}

def snapshot():
    result=context();result['game_processes']=[]
    try:
        output=subprocess.run(['tasklist','/FO','CSV','/NH'],capture_output=True,timeout=5,
                              creationflags=subprocess.CREATE_NO_WINDOW,check=True)
        for row in csv.reader(output.stdout.decode('mbcs',errors='replace').splitlines()):
            if len(row)>1 and any(s in row[0].lower() for s in ('bluearchive','yostar')):
                if row[1].isdigit():result['game_processes'].append(identity(int(row[1])))
    except (OSError,subprocess.SubprocessError) as e:result['enumeration_error']=str(e)
    result['note']='Integrity differences may block SendInput. A successful SendInput does not prove game acceptance.'
    return result

def save_snapshot(path):
    value=snapshot();Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');return value

class InputMonitor(threading.Thread):
    def __init__(self):super().__init__(daemon=True);self.stop=threading.Event()
    def run(self):
        previous=None
        while not self.stop.is_set():
            try:
                value=context();target=value['foreground'];key=(target['pid'],target['integrity_rid'],value['target_higher_integrity'])
                if key!=previous:
                    print('入力先診断: '+json.dumps(value,ensure_ascii=False),flush=True)
                    if value['target_higher_integrity']:print('入力権限差: 入力先の権限が高いため、SendInputが遮断される可能性があります。送信アプリを管理者として起動して比較してください。',flush=True)
                    previous=key
            except Exception as e:print('入力先診断エラー: '+str(e),flush=True)
            self.stop.wait(1)
