from pathlib import Path
p=Path('/app/engine/scripts/fx.py')
s=p.read_text()
s=s.replace("aw = 540 if sw <= sh else int(round(540 * sw / sh / 2)) * 2; ah = int(round(aw * sh / sw / 2)) * 2","aw = min(360, a.width) if sw <= sh else int(round(min(360, a.width) * sw / sh / 2)) * 2; ah = int(round(aw * sh / sw / 2)) * 2")
needle="if __name__ == '__main__':"
assert needle in s
fallback='''
_OriginalTracker=Tracker
class Tracker:
    def __init__(self, aw, ah):
        self.aw,self.ah=aw,ah
        self.prev=None
        try:self.original=_OriginalTracker(aw,ah)
        except Exception:
            self.original=None
            self.fd=cv2.FaceDetectorYN.create(os.path.join(ROOT,'models','yunet.onnx'),'',(aw,ah),0.5,0.3,20)
    def __call__(self,rgb,ms):
        if self.original is not None:return self.original(rgb,ms)
        _,boxes=self.fd.detect(cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        if boxes is not None and len(boxes):
            b=max(boxes,key=lambda v:v[2]*v[3]);x,y,w,h=map(float,b[:4]);face=(x+w/2,y+h/2,w)
        else:face=(self.aw/2,self.ah*.27,self.aw*.2)
        x,y,w=face;mask=np.zeros((self.ah,self.aw),np.uint8)
        cv2.ellipse(mask,(int(x),int(y+w*.3)),(max(5,int(w*.78)),max(8,int(w*1.25))),0,0,360,255,-1)
        cv2.ellipse(mask,(int(x),int(y+w*2.2)),(max(9,int(w*1.6)),max(9,int(w*1.8))),0,0,360,255,-1)
        return cv2.GaussianBlur(mask,(0,0),max(2,w*.04)),face
'''
p.write_text(s.replace(needle,fallback+'\n'+needle))
print('Face tracking fallback added')
