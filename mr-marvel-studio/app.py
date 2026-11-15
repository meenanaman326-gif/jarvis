import os,subprocess,tempfile,uuid,threading,time,hmac,pathlib,shutil
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
 if topic not in SCRIPTS or story not in SCRIPTS[topic]:return jsonify(error='Invalid topic'),400
 job=uuid.uuid4().hex;directory=WORK/job;directory.mkdir()
 up=request.files.get('video');src=None
 if up and up.filename:
  ext=pathlib.Path(up.filename).suffix.lower()
  if ext not in ('.mp4','.mov','.mkv'):return jsonify(error='Only MP4 MOV MKV supported'),400
  src=directory/('source'+ext);up.save(src)
 with LOCK:JOBS[job]={'status':'queued'}
 POOL.submit(run_job,job,topic,story,str(src) if src else None)
 return jsonify(job_id=job,status='queued'),202
def run_job(job,topic,story,src):
 d=WORK/job
 try:
  with LOCK:JOBS[job]={'status':'processing'}
  lines=SCRIPTS[topic][story]
  script=' '.join(lines)
  voice=str(d/'voice.wav');out=str(d/'short.mp4')
  subprocess.run(['espeak','-v','en-in','-s','135','-w',voice,script],check=True,timeout=40)
  from PIL import Image,ImageDraw,ImageFont
  font='/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
  colors=['#0b1430','#132b35','#182139','#241535','#1e2434','#102c30']
  imgs=[]
  for i,line in enumerate(lines):
   im=Image.new('RGB',(720,1280),colors[i]);dr=ImageDraw.Draw(im)
   dr.rounded_rectangle((55,175,665,1100),radius=38,outline=('#54e6d0' if topic=='gta6' else '#dd8bff'),width=6)
   dr.text((78,226),'GTA 6' if topic=='gta6' else 'MARVEL',font=ImageFont.truetype(font,64),fill='white')
   import textwrap
   wrapped=textwrap.fill(line,width=21)
   dr.multiline_text((78,460),wrapped,font=ImageFont.truetype(font,40),fill='#f0fbff',spacing=20)
   dr.text((78,990),'@Marvelexplainer0',font=ImageFont.truetype(font,25),fill='#a9d8db')
   path=d/f'frame{i}.png';im.save(path);imgs.append(path)
  dur=33
  if src:
   cmd=['ffmpeg','-y','-stream_loop','-1','-i',src,'-i',voice,'-filter_complex',
   '[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24,format=yuv420p[v]',
   '-map','[v]','-map','1:a','-t',str(dur),'-af','apad','-c:v','libx264','-preset','ultrafast','-crf','28','-c:a','aac','-movflags','+faststart',out]
  else:
   concat=d/'frames.txt';concat.write_text(''.join("file '"+str(p)+"'\nduration 5.5\n" for p in imgs)+"file '"+str(imgs[-1])+"'\n")
   cmd=['ffmpeg','-y','-f','concat','-safe','0','-i',str(concat),'-i',voice,'-t',str(dur),'-vf','fps=24,format=yuv420p','-af','apad','-c:v','libx264','-preset','ultrafast','-crf','28','-c:a','aac','-movflags','+faststart',out]
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=600)
  if p.returncode:raise RuntimeError(p.stderr[-450:])
  with LOCK:JOBS[job]={'status':'complete','file':out}
 except Exception as e:
  with LOCK:JOBS[job]={'status':'failed','error':str(e)[-300:]}
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
