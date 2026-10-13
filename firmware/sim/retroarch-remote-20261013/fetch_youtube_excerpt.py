"""Acquire only the user-requested 0..30 second excerpt as transformation input."""
from pathlib import Path
import os,sys,json,shutil
sys.path.insert(0,str(Path(os.environ['TEMP'])/'fc-video-deps-20261013'))
import yt_dlp
from imageio_ffmpeg import get_ffmpeg_exe
out=Path(__file__).resolve().parent/'youtube-U6Wlb18KLrI';out.mkdir(exist_ok=True)
ffmpeg_dir=Path(os.environ['TEMP'])/'fc-video-deps-20261013/bin';ffmpeg_dir.mkdir(exist_ok=True)
shutil.copyfile(get_ffmpeg_exe(),ffmpeg_dir/'ffmpeg.exe')
os.environ['PATH']=str(ffmpeg_dir)+os.pathsep+os.environ.get('PATH','')
opts={'noplaylist':True,'quiet':True,'socket_timeout':20,
 'format':'bestvideo[height<=480]+bestaudio/best[height<=480]/best',
 'ffmpeg_location':str(ffmpeg_dir),'merge_output_format':'mp4',
 'outtmpl':str(out/'source-30s.%(ext)s'),
 'download_ranges':lambda info,ydl:[{'start_time':0,'end_time':30}],
 'js_runtimes':{'node':{'path':'C:/Users/Yugo/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'}}}
with yt_dlp.YoutubeDL(opts) as ydl:
 info=ydl.extract_info('https://www.youtube.com/watch?v=U6Wlb18KLrI',download=True)
(out/'source.json').write_text(json.dumps({'id':info['id'],'title':info['title'],'original_duration':info['duration'],'requested_start':0,'requested_end':30,'url':'https://www.youtube.com/watch?v=U6Wlb18KLrI'},ensure_ascii=False,indent=2),encoding='utf-8')
print('Excerpt acquired:',info['id'],flush=True)
