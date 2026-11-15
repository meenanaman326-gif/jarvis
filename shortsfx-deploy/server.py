import os,json,uuid,time,subprocess,threading,tempfile,shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from fastapi import FastAPI,UploadFile,File,HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field

ROOT=Path(__file__).parent
ENGINE=Path('/app/engine')
STORE=Path(tempfile.gettempdir())/'shortsfx'
STORE.mkdir(exist_ok=True)
app=FastAPI(title='ShortsFX')
QUEUE=ThreadPoolExecutor(max_workers=1)
JOBS={}
NAMES=['noise','lineup','locked-on','orbit','lean-in','backdrop-word','spotlight','the-bill','moody','swipe','todo','tap','pause-point','uninstall','reel-frame','shortcut-rain','reject-stamp','countdown-flip','rabbit-hole','cover-star','scribble','red-collage','split-headline','pastel-word','check-pills','headline-box','profile-wall','tier-list','broll-split','phone-fan','dot-reveal','headline-wall','checklist','glass-widgets','timeline','comment-box','liquid-glass-graph','carousel-spin','match-cut','apple-toggles','led-sign','slow-push','over-the-shoulder-zoom','messages','place-in-grid','tape-label','select-resize','wave-trim','huge-strike','crayon-write','fan-build']

def call(args,timeout=120):
    x=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if x.returncode:raise RuntimeError((x.stderr or x.stdout)[-500:])
    return x

def probe(p):
    try:
        data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=width,height,codec_type','-of','json',str(p)],timeout=20))
        v=next(s for s in data['streams'] if s.get('codec_type')=='video')
        duration=float(data['format']['duration'])
        if duration<.1 or duration>600:raise ValueError()
        return dict(duration=round(duration,2),width=v['width'],height=v['height'])
    except Exception:raise HTTPException(400,'Invalid video or duration over 10 minutes')

def getmedia(k):
    if len(k)!=32 or any(c not in '0123456789abcdef' for c in k):raise HTTPException(404,'Not found')
    d=STORE/k
    try:
        m=json.loads((d/'meta.json').read_text())
        return d,d/m['filename'],m
    except Exception:raise HTTPException(404,'Upload expired')

@app.get('/api/health')
def health():return dict(ok=True,effects=len(NAMES))
@app.get('/api/effects')
def effects():return [dict(id=x,name=x.replace('-',' ').title()) for x in NAMES]

@app.post('/api/upload')
async def upload(video:UploadFile=File(...)):
    extension=Path(video.filename or '').suffix.lower()
    if extension not in ('.mp4','.mov','.m4v','.webm','.mkv'):raise HTTPException(400,'Please select a video file')
    k=uuid.uuid4().hex;d=STORE/k;d.mkdir()
    p=d/('source'+extension);size=0
    try:
        with p.open('wb') as f:
            while chunk:=await video.read(1024*1024):
                size+=len(chunk)
                if size>150*1024*1024:raise HTTPException(413,'Maximum video is 150 MB')
                f.write(chunk)
        meta=dict(filename=p.name,**probe(p))
        (d/'meta.json').write_text(json.dumps(meta))
        return dict(id=k,url='/api/video/'+k,**meta)
    except Exception:
        shutil.rmtree(d,ignore_errors=True);raise
    finally:await video.close()

@app.get('/api/video/{key}')
def original(key:str):
    d,p,m=getmedia(key)
    return FileResponse(p)

class Finder(BaseModel):
    length:int=Field(20,ge=8,le=45)
@app.post('/api/suggest/{key}')
def suggest(key:str,opts:Finder):
    d,p,m=getmedia(key);duration=m['duration'];length=min(opts.length,duration)
    if duration<=length+2:return dict(clips=[dict(start=0,end=duration,score=100)],method='audio')
    try:
        data=subprocess.run(['ffmpeg','-v','error','-i',str(p),'-vn','-ac','1','-ar','4000','-f','f32le','-'],capture_output=True,timeout=55,check=True).stdout
        s=np.frombuffer(data,dtype='<f4')
        energy=np.array([float(np.sqrt(np.mean(s[i:i+2000].astype('float64')**2))) for i in range(0,len(s),2000) if len(s[i:i+2000])])
        energy=np.log1p(energy*60);energy/=energy.max()+1e-8
    except Exception:energy=np.zeros(int(duration*2)+2)
    try:
        data=subprocess.run(['ffmpeg','-v','error','-i',str(p),'-vf','fps=1,scale=64:36,format=gray','-an','-f','rawvideo','-'],capture_output=True,timeout=75,check=True).stdout
        f=np.frombuffer(data,dtype=np.uint8);f=f[:len(f)//2304*2304].reshape((-1,2304)).astype(float)
        motion=np.r_[0,np.abs(np.diff(f,axis=0)).mean(axis=1)/35] if len(f)>1 else np.zeros(1)
    except Exception:motion=np.zeros(1)
    ranked=[]
    for s in range(0,max(1,int((duration-length)*2)+1),2):
        a=energy[s:s+int(length*2)]
        b=motion[int(s/2):int(s/2+length)]
        score=.75*(a.mean() if len(a) else 0)+.25*min(1,(b.mean() if len(b) else 0))
        ranked.append((score,s/2))
    clips=[]
    for score,start in sorted(ranked,reverse=True):
        if any(max(0,min(start+length,c['end'])-max(start,c['start']))>length*.25 for c in clips):continue
        clips.append(dict(start=start,end=round(min(duration,start+length),1),score=round(min(99,45+score*48))))
        if len(clips)>=3:break
    return dict(clips=clips,method='Audio energy and motion, not semantic AI')

class Render(BaseModel):
    effect:str
    start:float=Field(ge=0)
    end:float=Field(gt=0)
    text:str=Field('',max_length=120)
    quality:int=360
    crop:str='fill'

def render_worker(job,key,r):
    d,p,m=getmedia(key)
    clip=d/(job+'_clip.mp4');out=d/(job+'.mp4')
    try:
        JOBS[job].update(state='working',stage='Formatting vertical video…')
        vf='fps=15,scale=360:640:force_original_aspect_ratio=' + ('decrease,pad=360:640:(ow-iw)/2:(oh-ih)/2' if r.crop=='fit' else 'increase,crop=360:640')+',setsar=1'
        call(['ffmpeg','-nostdin','-v','error','-y','-ss',str(r.start),'-i',str(p),'-t',str(r.end-r.start),'-vf',vf,'-c:v','libx264','-preset','ultrafast','-crf','25','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart',str(clip)],180)
        JOBS[job]['stage']='Applying selected effects…'
        cmd=['python','-u',str(ENGINE/'scripts/fx.py'),r.effect,str(clip),str(out),'--start','0','--end',str(probe(clip)['duration']),'--width',str(r.quality)]
        if r.text:cmd+=['--text',r.text]
        call(cmd,900)
        probe(out)
        JOBS[job].update(state='done',stage='Done',preview=f'/api/result/{key}/{job}',download=f'/api/download/{key}/{job}')
    except Exception as e:JOBS[job].update(state='error',stage=str(e)[-250:])
    finally:clip.unlink(missing_ok=True)

@app.post('/api/render/{key}')
def render(key:str,r:Render):
    d,p,m=getmedia(key)
    if r.effect not in NAMES:raise HTTPException(400,'Invalid effect')
    if r.start>=r.end or r.end>m['duration']+.03 or r.end-r.start>45:raise HTTPException(400,'Choose a clip of up to 45 seconds')
    if r.quality not in (360,540) or r.crop not in ('fill','fit'):raise HTTPException(400,'Invalid export settings')
    j=uuid.uuid4().hex
    JOBS[j]=dict(state='queued',stage='Waiting to render…',key=key)
    QUEUE.submit(render_worker,j,key,r)
    return dict(job_id=j)

@app.get('/api/job/{job}')
def job(job:str):
    if job not in JOBS:raise HTTPException(404,'Job expired')
    return JOBS[job]

def rendered(key,job):
    getmedia(key)
    t=JOBS.get(job)
    if not t or t['key']!=key or t['state']!='done':raise HTTPException(404,'Not ready')
    p=STORE/key/(job+'.mp4')
    if not p.exists():raise HTTPException(404,'File expired')
    return p
@app.get('/api/result/{key}/{job}')
def result(key:str,job:str):return FileResponse(rendered(key,job),media_type='video/mp4')
@app.get('/api/download/{key}/{job}')
def download(key:str,job:str):return FileResponse(rendered(key,job),media_type='video/mp4',filename='shortsfx_'+job[:8]+'.mp4')

app.mount('/',StaticFiles(directory=ROOT/'static',html=True),name='frontend')
