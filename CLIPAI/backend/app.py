from pathlib import Path
import os, uuid, json, sqlite3, shutil, subprocess
from datetime import datetime, timezone
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
BASE=Path(__file__).resolve().parent; DATA=BASE/'database'; UP=DATA/'uploads'; OUT=DATA/'clips'
for p in (UP,OUT,DATA/'temporary'): p.mkdir(parents=True,exist_ok=True)
DB=DATA/'clipai.sqlite3'; MAX=int(os.getenv('MAX_UPLOAD_MB','2048'))*1048576
app=FastAPI(title='CLIPAI API'); app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
def db():
 c=sqlite3.connect(DB,timeout=30); c.row_factory=sqlite3.Row; return c
with db() as c:
 c.execute('CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT,filename TEXT,path TEXT,duration REAL,width INTEGER,height INTEGER,settings TEXT,status TEXT,progress INTEGER,stage TEXT,error TEXT,created TEXT)')
 c.execute('CREATE TABLE IF NOT EXISTS clips(id TEXT PRIMARY KEY,project_id TEXT,title TEXT,path TEXT,duration REAL,created TEXT)')
def probe(f):
 try:
  x=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(f)])); v=next(s for s in x['streams'] if s['codec_type']=='video'); return float(x['format']['duration']),int(v['width']),int(v['height'])
 except Exception as e: raise ValueError('Cannot inspect media. Confirm FFmpeg/ffprobe installation and valid video.') from e
class Settings(BaseModel): settings:dict
@app.get('/api/health')
def health(): return {'status':'ok','ffmpeg':shutil.which('ffmpeg') is not None,'whisper':shutil.which('whisper') is not None}
@app.get('/api/projects')
def list_projects():
 with db() as c: return [dict(r) for r in c.execute('SELECT * FROM projects ORDER BY created DESC')]
@app.post('/api/projects')
async def upload(file:UploadFile=File(...),name:str=Form(''),settings:str=Form('{}')):
 ext=Path(file.filename or '').suffix.lower()
 if ext not in {'.mp4','.mov','.webm','.mkv','.m4v','.avi'}: raise HTTPException(415,'Unsupported video format.')
 pid=uuid.uuid4().hex; path=UP/(pid+ext); size=0
 try:
  with path.open('wb') as out:
   while chunk:=await file.read(1048576):
    size+=len(chunk)
    if size>MAX: raise HTTPException(413,f'File exceeds {MAX//1048576} MB limit.')
    out.write(chunk)
  dur,w,h=probe(path)
  with db() as c: c.execute('INSERT INTO projects VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(pid,(name.strip() or Path(file.filename).stem)[:120],file.filename,str(path),dur,w,h,settings,'Uploaded',0,'Ready to process',None,datetime.now(timezone.utc).isoformat()))
  return {'id':pid,'status':'Queued','duration':dur,'width':w,'height':h}
 except HTTPException: path.unlink(missing_ok=True); raise
 except Exception as e: path.unlink(missing_ok=True); raise HTTPException(400,str(e))
@app.get('/api/projects/{pid}')
def get_project(pid:str):
 with db() as c: r=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
 if not r: raise HTTPException(404,'Project not found')
 d=dict(r); d['settings']=json.loads(d['settings']); return d
@app.put('/api/projects/{pid}/settings')
def save_settings(pid:str,b:Settings):
 with db() as c:
  cur=c.execute('UPDATE projects SET settings=? WHERE id=?',(json.dumps(b.settings),pid))
  if not cur.rowcount: raise HTTPException(404,'Project not found')
 return {'saved':True}
def setjob(pid,s,p,stage,error=None):
 with db() as c: c.execute('UPDATE projects SET status=?,progress=?,stage=?,error=? WHERE id=?',(s,p,stage,error,pid))
def render_job(pid):
 with db() as c: p=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
 try:
  if not shutil.which('ffmpeg'): raise RuntimeError('FFmpeg is missing. Install it and restart backend.')
  settings=json.loads(p['settings']); duration=p['duration']; count=max(1,min(15,int(settings.get('count',3))))
  val=settings.get('clipSeconds','30-45'); length=int(settings.get('customDuration',30)) if val=='custom' else int(str(val).split('-')[0]); length=max(5,min(90,length))
  ratio=settings.get('ratio','9:16'); filters={'9:16':'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920','1:1':'scale=1080:1080:force_original_aspect_ratio=increase,crop=1080:1080','4:5':'scale=1080:1350:force_original_aspect_ratio=increase,crop=1080:1350','16:9':'scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2'}
  setjob(pid,'Analyzing',10,'Selecting representative segments')
  for i in range(count):
   seg=min(length,duration); start=max(0,(duration-seg)*(i+.5)/count); cid=uuid.uuid4().hex; dest=OUT/(cid+'.mp4')
   setjob(pid,'Rendering',30+int(60*i/count),f'Rendering clip {i+1} of {count}')
   cmd=['ffmpeg','-y','-ss',str(start),'-i',p['path'],'-t',str(seg),'-vf',filters.get(ratio,filters['9:16']),'-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac','-movflags','+faststart',str(dest)]
   r=subprocess.run(cmd,capture_output=True,text=True,timeout=3600)
   if r.returncode or not dest.exists() or not dest.stat().st_size: raise RuntimeError(r.stderr[-1200:])
   with db() as c: c.execute('INSERT INTO clips VALUES (?,?,?,?,?,?)',(cid,pid,f"{p['name']} — Clip {i+1}",str(dest),seg,datetime.now(timezone.utc).isoformat()))
  setjob(pid,'Completed',100,f'{count} clips rendered')
 except Exception as e: setjob(pid,'Failed',0,'Processing failed',str(e))
@app.post('/api/projects/{pid}/process')
def process(pid:str,bg:BackgroundTasks):
 with db() as c:
  p=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
  if not p: raise HTTPException(404,'Project not found')
  if p['status'] in ('Queued','Processing','Analyzing','Rendering'): raise HTTPException(409,'Already processing')
  c.execute("UPDATE projects SET status='Queued',progress=0,error=NULL,stage='Waiting in queue' WHERE id=?",(pid,))
 bg.add_task(render_job,pid); return {'id':pid,'status':'Queued'}
@app.post('/api/projects/{pid}/cancel')
def cancel(pid:str):
 with db() as c:
  cur=c.execute("UPDATE projects SET status='Cancelled',stage='Cancelled by user' WHERE id=? AND status='Queued'",(pid,))
  if not cur.rowcount: raise HTTPException(409,'Only queued jobs can be cancelled safely.')
 return {'status':'Cancelled'}
@app.get('/api/clips')
def list_clips():
 with db() as c: return [dict(x) for x in c.execute('SELECT clips.*,projects.name project_name FROM clips JOIN projects ON projects.id=clips.project_id ORDER BY clips.created DESC')]
@app.get('/api/clips/{cid}/file')
def get_file(cid:str):
 with db() as c: r=c.execute('SELECT path FROM clips WHERE id=?',(cid,)).fetchone()
 if not r or not Path(r['path']).is_file(): raise HTTPException(404,'Rendered file is missing')
 return FileResponse(r['path'],media_type='video/mp4',filename=cid+'.mp4')
@app.patch('/api/clips/{cid}')
def rename(cid:str,b:dict):
 title=str(b.get('title','')).strip()[:120]
 if not title: raise HTTPException(400,'Title required')
 with db() as c: r=c.execute('UPDATE clips SET title=? WHERE id=?',(title,cid))
 if not r.rowcount: raise HTTPException(404,'Clip not found')
 return {'saved':True}
@app.delete('/api/clips/{cid}')
def delete_clip(cid:str):
 with db() as c:
  r=c.execute('SELECT path FROM clips WHERE id=?',(cid,)).fetchone()
  if not r: raise HTTPException(404,'Clip not found')
  Path(r['path']).unlink(missing_ok=True); c.execute('DELETE FROM clips WHERE id=?',(cid,))
 return {'deleted':True}
