import cv2
import threading
import time

class CameraStream:
    def __init__(self, camera_id):
        self.camera_id = camera_id
        self.cap = cv2.VideoCapture(camera_id)
        # Ensure high resolution for OCR
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        
        self.latest_frame = None
        self.running = False
        self.lock = threading.Lock()
        
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()
        
    def _update(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                with self.lock:
                    self.latest_frame = frame.copy()
            else:
                time.sleep(0.01)
                
    def get_frame(self):
        with self.lock:
            if self.latest_frame is not None:
                return self.latest_frame.copy()
            return None
            
    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join()
        self.cap.release()
