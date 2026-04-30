import cv2
import time
import logging
from src.camera_manager import CameraStream
from src.hardware import ArduinoController
from src.alpr_pipeline import ALPRPipeline

# Configuration
CAM1_INDEX = 0
CAM2_INDEX = 1
ARDUINO_PORT = 'COM3'
DETECTION_MODEL = r'models\plate_detection.pt'
OCR_MODEL = r'models\character_recognition.pt'

logging.basicConfig(level=logging.INFO)

def main():
    # 1. Initialize Hardware (Arduino)
    arduino = ArduinoController(port=ARDUINO_PORT)
    
    # 2. Initialize Models
    alpr = ALPRPipeline(DETECTION_MODEL, OCR_MODEL)
    
    # 3. Initialize Webcams
    cam1 = CameraStream(CAM1_INDEX)
    cam2 = CameraStream(CAM2_INDEX)
    cam1.start()
    cam2.start()
    
    # Example Database lookup simulation
    authorized_plates = ["ABC1234", "XYZ9876", "TEST001"]

    logging.info("System Online. Monitoring cameras...")
    
    try:
        while True:
            # Process Camera 1 (Entry)
            frame1 = cam1.get_frame()
            plate_text1, bbox1 = alpr.process_frame(frame1)
            
            if plate_text1:
                logging.info(f"Cam 1 Detected: {plate_text1}")
                if plate_text1 in authorized_plates:
                    arduino.grant_access()
                    time.sleep(5)  # Cooldown while gate is open

            # Process Camera 2 (Exit)
            frame2 = cam2.get_frame()
            plate_text2, bbox2 = alpr.process_frame(frame2)
            
            if plate_text2:
                logging.info(f"Cam 2 Detected: {plate_text2}")
                if plate_text2 in authorized_plates:
                    arduino.grant_access()
                    time.sleep(5)
            
            # Press 'q' to quit if visualization is on
            # cv2.imshow('Cam1', frame1)
            # if cv2.waitKey(1) & 0xFF == ord('q'):
            #    break
                
            time.sleep(0.1) # Prevent CPU hogging
            
    except KeyboardInterrupt:
        logging.info("Shutting down...")
    finally:
        cam1.stop()
        cam2.stop()
        arduino.close()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
