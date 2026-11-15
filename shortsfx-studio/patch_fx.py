"""Small performance/resilience patch to the copied MIT-licensed upstream renderer.
Keeps the original effects unchanged and adds a graceful face-only fallback.
"""
from pathlib import Path
import re
path = Path(__file__).resolve().parent / 'vendor/scripts/fx.py'
content = path.read_text()
if '# ShortsFX fallback tracker' not in content:
    content = content.replace('aw = 540 if sw <= sh else int(round(540 * sw / sh / 2)) * 2',
                              'aw = min(360, a.width) if sw <= sh else int(round(min(360, a.width) * sw / sh / 2)) * 2')
    insert = '''# ShortsFX fallback tracker (used only if MediaPipe cannot initialize).
_RealTracker = Tracker
class Tracker:
    def __init__(self, aw, ah):
        self.aw, self.ah = aw, ah
        self.prev = None
        self.real = None
        try:
            self.real = _RealTracker(aw, ah)
        except Exception as ex:
            print('MediaPipe unavailable; using face-only tracking:', str(ex)[:160], flush=True)
            self.fd = cv2.FaceDetectorYN.create(os.path.join(ROOT, 'models', 'yunet.onnx'), '', (aw, ah), 0.5, 0.3, 20)
    def __call__(self, rgb, ms):
        if self.real is not None:
            return self.real(rgb, ms)
        _, boxes = self.fd.detect(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        if boxes is not None and len(boxes):
            b = max(boxes, key=lambda x: x[2] * x[3]); x, y, w, h = map(float, b[:4]); face = (x + w/2, y + h/2, w)
        else:
            face = (self.aw/2, self.ah*.27, self.aw*.22)
        mask = np.zeros((self.ah, self.aw), dtype=np.uint8)
        x, y, w = face
        cv2.ellipse(mask, (int(x), int(y+w*.2)), (max(4,int(w*.72)),max(8,int(w*1.2))), 0,0,360,255,-1)
        cv2.ellipse(mask, (int(x), int(y+w*2.4)), (max(10,int(w*1.7)),max(12,int(w*1.8))), 0,0,360,255,-1)
        mask = cv2.GaussianBlur(mask, (0,0), max(2,w*.04))
        return mask, face

'''
    anchor = "if __name__ == '__main__':\n    main()"
    assert anchor in content
    content = content.replace(anchor, insert + anchor)
    path.write_text(content)
    print('Patched original effects engine for mobile sizing and fallback.')
else:
    print('Already patched')