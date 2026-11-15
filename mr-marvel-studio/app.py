import os,subprocess,tempfile,uuid,threading,time,hmac,pathlib,shutil,zipfile,textwrap,math
from flask import Flask,request,jsonify,send_file,Response
from concurrent.futures import ThreadPoolExecutor
ROOT=pathlib.Path(__file__).resolve().parent;WORK=pathlib.Path('/tmp/mrmarvel');WORK.mkdir(exist_ok=True)
app=Flask(__name__);app.config['MAX_CONTENT_LENGTH']=100*1024*1024
PASSWORD=os.environ.get('AGENT_PASSWORD','')
JOBS={};LOCK=threading.Lock();POOL=ThreadPoolExecutor(max_workers=1)
SCRIPTS={
'gta6':{
'auto':["GTA six fans, ye suno!","Vice City ki duniya mein naye characters ki journey dekhne ko milegi.","Jason aur Lucia ki story par gaming community ki nazar hai.","Official Rockstar videos ko hi authentic samjho; fake gameplay se bacho.","Real updates ke liye Rockstar Newswire check karo.","Aur aise gaming shorts ke liye subscribe karo!"],
'characters':["GTA six mein Jason aur Lucia kaun hain?","Rockstar ne dono lead characters ko apni official marketing mein dikhaya hai.","Dono ka connection kahani ke centre mein nazar aata hai.","Lekin trailer se bahar ke claims ko confirmed facts mat samjho.","Official trailer dekho aur apni theory comment karo.","GTA six ke aur updates ke liye subscribe karo!"],
'city':["Vice City is back!","GTA six ka official setting Leonida ka fictional state hai.","Yahan neon-lit streets, beaches, aur modern city culture ki jhalak milti hai.","Yeh visuals illustrative hain; asli gameplay nahi.","Official Rockstar trailers mein aur details milengi.","Aise gaming explainers ke liye subscribe karo!"]},
'marvel':{
'auto':["Marvel fans, ek interesting sawaal!","Doctor Doom Marvel comics ka ek iconic villain hai.","Woh science, technology aur mysticism ka combination use karta hai.","Comic book history aur upcoming films ki stories ko mix mat karo.","Official Marvel announcements follow karo.","Aur superhero facts ke liye subscribe karo!"],
'characters':["Doctor Doom itna popular kyun hai?","Marvel comics mein Victor Von Doom ko brilliant scientist aur ruler dikhaya gaya hai.","Uske ambition ki wajah se Fantastic Four ke saath conflict hota hai.","Comic stories ka screen adaptations se alag hona normal hai.","Tumhara favourite Marvel villain kaun hai?","Comment karke batao aur subscribe karo!"],
'city':["Marvel multiverse explained in seconds!","Comics mein alternate universes different character outcomes explore karte hain.","Ek universe ki event har story ke liye automatically canon nahi hoti.","Screen par confirmed information ke liye Marvel ki official releases dekho.","Aage kis superhero ka short chahiye?","Subscribe karna mat bhoolna!"]}}
def authorized(req):return bool(PASSWORD) and hmac.compare_digest(req.headers.get('X-Agent-Key',''),PASSWORD)
@app.get('/')
def home():return Response((ROOT/'index.html').read_text(),mimetype='text/html')
@app.get('/api/health')
def health():return jsonify(status='online',locked=bool(PASSWORD))

@app.post('/api/generate')
def generate():
 if not PASSWORD:return jsonify(error='Server password is not configured'),503
 if not authorized(request):return jsonify(error='Wrong agent password'),401
 topic=request.form.get('topic','gta6');story=request.form.get('story','auto')
 mode=request.form.get('mode','clips')
 if topic not in SCRIPTS or story not in SCRIPTS[topic]:return jsonify(error='Invalid topic'),400
 if mode not in ('clips','animated'):return jsonify(error='Invalid mode'),400
 job=uuid.uuid4().hex;directory=WORK/job;directory.mkdir()
 uploads=request.files.getlist('video')
 sources=[]
 for k,up in enumerate(uploads[:6]):
  if not up or not up.filename:continue
  ext=pathlib.Path(up.filename).suffix.lower()
  if ext not in ('.mp4','.mov','.mkv','.zip'):return jsonify(error='Only MP4, MOV, MKV or ZIP files are supported'),400
  source=directory/('input_'+str(k)+ext);up.save(source)
  if ext=='.zip':
   try:
    with zipfile.ZipFile(source) as z:
     chosen=[i for i in z.infolist() if not i.is_dir() and pathlib.Path(i.filename).suffix.lower() in ('.mp4','.mov','.mkv')]
     if sum(i.file_size for i in chosen[:10])>200*1024*1024:
      return jsonify(error='ZIP clips over 200MB extracted are too large for this server'),400
     for j,info in enumerate(chosen[:10]):
      if info.file_size>120*1024*1024:continue
      dest=directory/('zip_'+str(k)+'_'+str(j)+pathlib.Path(info.filename).suffix.lower())
      with z.open(info) as inp,open(dest,'wb') as out:shutil.copyfileobj(inp,out)
      sources.append(str(dest))
   except (zipfile.BadZipFile,RuntimeError):
    return jsonify(error='Invalid ZIP file'),400
   source.unlink(missing_ok=True)
  else:sources.append(str(source))
 if mode=='clips' and not sources:
  return jsonify(error='Clip Mode needs footage. Please upload your own/licensed GTA 6 video or official media file, or switch to Animated Demo.'),400
 with LOCK:JOBS[job]={'status':'queued'}
 POOL.submit(run_job,job,topic,story,mode,sources)
 return jsonify(job_id=job,status='queued'),202

def probe_duration(filepath):
 p=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(filepath)],capture_output=True,text=True,timeout=20)
 try:return max(1.0,float(p.stdout.strip()))
 except:return 20.0

def compose_overlay(directory,i,title,line,topic,mode):
 from PIL import Image,ImageDraw,ImageFont
 W,H=720,1280
 accent='#3EF0D0' if topic=='gta6' else '#F35DB6'
 image=Image.new('RGBA',(W,H),(0,0,0,0))
 d=ImageDraw.Draw(image)
 font='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
 def ff(n):return ImageFont.truetype(font,n)
 d.rounded_rectangle((32,50,688,133),radius=25,fill=(7,14,26,220),outline=accent,width=3)
 d.text((62,77),'MR MARVEL EXPLAINER',font=ff(27),fill='white')
 d.rounded_rectangle((34,725,685,1150),radius=30,fill=(5,12,24,222),outline=(130,220,224,128),width=3)
 d.text((62,760),'GTA VI  |  QUICK FACTS' if topic=='gta6' else 'MARVEL | QUICK FACTS',font=ff(29),fill=accent)
 text=('GTA VI' if topic=='gta6' else 'MARVEL') + '  •  ' + str(i+1) + '/6'
 d.text((58,650),text,font=ff(25),fill='white')
 lines=textwrap.wrap(line,24)
 y=844
 for ln in lines[:5]:
  d.text((62,y),ln,font=ff(37),fill='white',stroke_width=1,stroke_fill='black')
  y+=53
 d.rectangle((34,1158,686,1166),fill=(75,90,110,160))
 d.rectangle((34,1158,34+int((i+1)/6*652),1166),fill=accent)
 d.text((52,1190),'SOURCE: USER FOOTAGE' if mode=='clips' else 'ILLUSTRATIVE VISUALS - NOT GAMEPLAY',font=ff(19),fill='#C4DCE8')
 overlay=directory/('overlay'+str(i)+'.png');image.save(overlay)
 return overlay

def animation_bg(directory,i,topic):
 from PIL import Image,ImageDraw,ImageFont
 W,H=720,1280
 im=Image.new('RGB',(W,H))
 d=ImageDraw.Draw(im)
 for y in range(H):
  c=(int(8+y*0.009),int((23 if topic=='gta6' else 10)+y*0.020),int((48 if topic=='gta6' else 39)+y*0.028))
  d.line((0,y,W,y),fill=c)
 accent=(25,223,198) if topic=='gta6' else (217,67,167)
 for k in range(12):
  x=(i*59+k*79)%760-25
  height=170+(k*53+i*17)%270
  d.rectangle((x,810-height,x+48,810),fill=(13,45,58) if topic=='gta6' else (47,16,68))
  for row in range(4):
   d.rectangle((x+7,830-height+row*37,x+12,848-height+row*37),fill=accent)
 d.ellipse((-120,35,490,645),outline=accent,width=12)
 d.ellipse((235,170,780,715),outline=(220,68,151) if topic=='gta6' else (135,79,235),width=8)
 d.line((0,810,720,810),fill=accent,width=8)
 path=directory/('bg'+str(i)+'.jpg');im.save(path,quality=88)
 return path

def run_job(job,topic,story,mode,sources):
 directory=WORK/job
 try:
  with LOCK:JOBS[job]={'status':'processing'}
  from PIL import Image
  lines=SCRIPTS[topic][story]
  parts=[]
  lengths=[probe_duration(s) for s in sources] if sources else []
  for i,line in enumerate(lines):
   voice=str(directory/('voice'+str(i)+'.wav'))
   p=subprocess.run(['espeak','-v','en-in','-s','140','-a','160','-w',voice,line],capture_output=True,timeout=55)
   if p.returncode:raise RuntimeError('Narration failed')
   dur=min(9.5,max(5.0,probe_duration(voice)+.55))
   overlay=compose_overlay(directory,i,story.upper(),line,topic,mode)
   out=directory/('seg'+str(i)+'.mp4')
   if sources:
    index=i%len(sources)
    src=sources[index];slen=lengths[index]
    # Reuse the source at evenly spaced points, so each scene has new footage.
    start=max(0.0,min(max(0.0,slen-dur),((i+.5)/len(lines))*slen-dur/2))
    # Loop short clips if needed; 9:16 crop keeps video within a social-safe frame.
    vf='[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1,fps=18[bg];[bg][1:v]overlay=0:0:format=auto,format=yuv420p[v]'
    cmd=['ffmpeg','-y','-ss',str(round(start,2)),'-stream_loop','-1','-i',src,'-loop','1','-i',str(overlay),'-i',voice,'-filter_complex',vf,
      '-map','[v]','-map','2:a','-t',str(dur),'-af','apad','-r','18','-c:v','libx264','-preset','ultrafast','-crf','27','-c:a','aac','-b:a','96k','-movflags','+faststart',str(out)]
   else:
    bg=animation_bg(directory,i,topic)
    vf="[0:v]zoompan=z='min(zoom+0.002,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=720x1280:fps=18[bg];[bg][1:v]overlay=0:0:format=auto,format=yuv420p[v]"
    cmd=['ffmpeg','-y','-loop','1','-framerate','18','-i',str(bg),'-loop','1','-i',str(overlay),'-i',voice,'-filter_complex',vf,
      '-map','[v]','-map','2:a','-t',str(dur),'-af','apad','-r','18','-c:v','libx264','-preset','ultrafast','-crf','27','-c:a','aac','-b:a','96k','-movflags','+faststart',str(out)]
   result=subprocess.run(cmd,capture_output=True,text=True,timeout=280)
   if result.returncode:raise RuntimeError('FFmpeg: '+result.stderr[-340:])
   parts.append(out)
  concat=directory/'list.txt'
  concat.write_text(''.join("file '"+str(p)+"'\n" for p in parts))
  final=directory/'short.mp4'
  result=subprocess.run(['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',str(final)],capture_output=True,text=True,timeout=75)
  if result.returncode:raise RuntimeError('Combining clips failed: '+result.stderr[-300:])
  with LOCK:JOBS[job]={'status':'complete','file':str(final)}
 except Exception as e:
  with LOCK:JOBS[job]={'status':'failed','error':str(e)[-450:]}
@app.get('/api/jobs/<job>')
def status(job):
 if not authorized(request):return jsonify(error='Unauthorized'),401
 with LOCK:j=JOBS.get(job)
 if not j:return jsonify(error='Not found'),404
 return jsonify(status=j['status'],error=j.get('error'))
@app.get('/api/jobs/<job>/download')
def download(job):
 if not authorized(request):return jsonify(error='Unauthorized'),401
 with LOCK:j=JOBS.get(job)
 if not j or j['status']!='complete':return jsonify(error='Not ready'),404
 return send_file(j['file'],as_attachment=True,download_name='MrMarvel_Short.mp4')
