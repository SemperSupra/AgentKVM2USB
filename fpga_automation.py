import cv2
import time
import sys

def find_kvm2usb_camera():
    """
    Scans for connected UVC video devices to find the Epiphan KVM2USB 3.0.
    Returns the camera index if found, else -1.
    """
    print("Scanning for Epiphan KVM2USB 3.0 video input...")
    # Typically, 0 is the built-in webcam, 1 or 2 would be the capture card.
    for i in range(5):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            # In a real scenario, you can check cap.getBackendName() or resolution to verify
            ret, frame = cap.read()
            if ret:
                print(f"[*] Found active video source at index {i}")
                return i
        cap.release()
    return -1

def capture_fpga_output():
    """
    Connects to the Spartan-6 / FX3 via the KVM2USB 3.0 and captures frames.
    """
    cam_idx = find_kvm2usb_camera()
    if cam_idx == -1:
        print("[!] Could not find KVM2USB 3.0 input. Please ensure it is plugged into a USB 3.0 port.")
        sys.exit(1)
        
    cap = cv2.VideoCapture(cam_idx, cv2.CAP_DSHOW)
    
    # Try setting high resolution for KVM2USB 3.0
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    cap.set(cv2.CAP_PROP_FPS, 60)
    
    print("[*] Starting automated capture of Spartan-6 / FX3. Press 'q' to quit.")
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("[!] Failed to grab frame from KVM2USB 3.0")
                break
                
            # Automation Logic Goes Here
            # For example: template matching to detect if the Spartan-6 / FX3 booted correctly
            # match = cv2.matchTemplate(frame, template_image, cv2.TM_CCOEFF_NORMED)
            
            # Display the stream
            cv2.imshow('Spartan-6 / FX3 (Epiphan KVM2USB 3.0)', frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    except KeyboardInterrupt:
        print("\n[*] Stopping automation...")
    finally:
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    capture_fpga_output()
