import cv2
import numpy as np
import datetime
from datetime import timedelta

class MotionDetector:
    def __init__(self, threshold=25, min_area=500, accumulation_weight=0.5):
        self.threshold = threshold
        self.min_area = min_area
        self.accumulation_weight = accumulation_weight
        self.avg = None

    def update_params(self, threshold=None, min_area=None, accumulation_weight=None):
        """Updates the detector parameters on the fly."""
        if threshold is not None: self.threshold = threshold
        if min_area is not None: self.min_area = min_area
        if accumulation_weight is not None: self.accumulation_weight = accumulation_weight

    def detect(self, frame):
        """
        Detects motion in the given frame using a running average background model.
        Returns: (is_motion_detected, list_of_bounding_boxes)
        """
        if frame is None:
            return False, []

        # Convert to grayscale and blur to reduce noise
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        # Initialize background model
        if self.avg is None:
            self.avg = gray.copy().astype("float")
            return False, []

        # Accumulate weighted average for adaptive background
        cv2.accumulateWeighted(gray, self.avg, self.accumulation_weight)
        frame_delta = cv2.absdiff(gray, cv2.convertScaleAbs(self.avg))

        # Threshold and dilate to fill in holes
        thresh = cv2.threshold(frame_delta, self.threshold, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)

        # Find contours of movement
        cnts, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        locs = []
        for c in cnts:
            if cv2.contourArea(c) < self.min_area:
                continue
            locs.append(cv2.boundingRect(c))
            
        return len(locs) > 0, locs

class SRTGenerator:
    def __init__(self, file_path):
        self.file_path = file_path
        self.index = 1
        self.start_time = None

    def _format_srt_time(self, seconds):
        td = timedelta(seconds=seconds)
        total_seconds = int(td.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60
        millis = int(td.microseconds / 1000)
        return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"

    def add_entry(self, start_sec, end_sec, text):
        entry = (
            f"{self.index}\n"
            f"{self._format_srt_time(start_sec)} --> {self._format_srt_time(end_sec)}\n"
            f"{text}\n\n"
        )
        with open(self.file_path, "a", encoding="utf-8") as f:
            f.write(entry)
        self.index += 1

class OverlayManager:
    @staticmethod
    def apply_standard_overlay(frame, status_text="", show_timestamp=True, is_motion=False):
        """
        Applies a professional HUD overlay to the frame.
        """
        if frame is None:
            return frame

        h, w = frame.shape[:2]
        
        # 1. Background for bottom status bar
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, h - 40), (w, h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.4, frame, 0.6, 0, frame)

        # 2. Timestamp (Bottom Left)
        if show_timestamp:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            cv2.putText(frame, ts, (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

        # 3. Status Text (Bottom Right)
        if status_text:
            text_size = cv2.getTextSize(status_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)[0]
            cv2.putText(frame, status_text, (w - text_size[0] - 10, h - 12), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1, cv2.LINE_AA)

        # 4. Motion Indicator (Top Right)
        if is_motion:
            # Red circle for motion
            cv2.circle(frame, (w - 30, 30), 10, (0, 0, 255), -1, cv2.LINE_AA)
            cv2.putText(frame, "MOTION", (w - 110, 38), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)

        return frame

    @staticmethod
    def draw_motion_boxes(frame, locs):
        """
        Draws bounding boxes around detected motion.
        """
        for (x, y, w, h) in locs:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        return frame
