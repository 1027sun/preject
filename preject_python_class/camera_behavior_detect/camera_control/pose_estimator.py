"""MediaPipe LIVE_STREAM adapter; busy frames are dropped by MediaPipe."""

from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "models" / "pose_landmarker_lite.task"


class PoseEstimator:
    def __init__(self, callback, model_path=None, inference_width=640):
        path = Path(model_path) if model_path else DEFAULT_MODEL
        if not path.is_file():
            raise FileNotFoundError(f"缺少姿态模型：{path}。请先运行 setup_camera.bat。")
        self.inference_width = inference_width
        options = vision.PoseLandmarkerOptions(
            # Bytes also support Windows paths containing non-ASCII characters.
            base_options=python.BaseOptions(model_asset_buffer=path.read_bytes()),
            running_mode=vision.RunningMode.LIVE_STREAM,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            result_callback=callback,
        )
        self._model = vision.PoseLandmarker.create_from_options(options)

    def submit(self, frame, timestamp_ms):
        h, w = frame.shape[:2]
        if w > self.inference_width:
            frame = cv2.resize(frame, (self.inference_width, round(h * self.inference_width / w)))
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        self._model.detect_async(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp_ms)

    def close(self):
        self._model.close()
