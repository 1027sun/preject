"""One camera thread, with no queue of stale frames."""

import sys
import threading
import time

import cv2


def now_ms():
    return time.monotonic_ns() // 1_000_000


class CameraCapture:
    def __init__(self, camera_index=0, width=1280, height=720, fps=30):
        self.camera_index = camera_index
        self.width, self.height, self.fps = width, height, fps
        self._camera = None
        self._thread = None
        self._stop = threading.Event()

    def start(self, on_frame, on_error):
        if self._thread and self._thread.is_alive():
            raise RuntimeError("摄像头已经启动。")
        self._camera = None
        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF] if sys.platform == "win32" else [cv2.CAP_ANY]
        for backend in backends:
            camera = cv2.VideoCapture(self.camera_index, backend)
            if camera.isOpened():
                self._camera = camera
                break
            camera.release()
        if self._camera is None:
            raise RuntimeError(
                f"无法打开摄像头 {self.camera_index}。请关闭占用摄像头的软件、检查 Windows 摄像头权限，"
                "或使用 python camera_demo.py --camera 1 选择设备。"
            )
        self._camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self._camera.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._camera.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._camera.set(cv2.CAP_PROP_FPS, self.fps)
        self._camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._stop.clear()

        def run():
            last_ms = 0
            failures = 0
            try:
                while not self._stop.is_set():
                    ok, frame = self._camera.read()
                    if self._stop.is_set():
                        break
                    if not ok or frame is None:
                        failures += 1
                        if failures >= 8:
                            raise RuntimeError("摄像头连续读取失败，请检查设备连接后重新启动。")
                        self._stop.wait(0.03)
                        continue
                    failures = 0
                    timestamp = max(now_ms(), last_ms + 1)
                    last_ms = timestamp
                    on_frame(cv2.flip(frame, 1), timestamp)
            except Exception as exc:
                if not self._stop.is_set():
                    on_error(str(exc))
            finally:
                self._camera.release()

        self._thread = threading.Thread(target=run, name="motionquest-camera", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
            if self._thread.is_alive():
                # Some drivers unblock read() only when the device is released.
                self._camera.release()
                self._thread.join(timeout=2)
            if self._thread.is_alive():
                raise RuntimeError("摄像头驱动未能及时停止，请关闭本程序后重新连接摄像头。")
        elif self._camera:
            self._camera.release()
        self._thread = None
        self._camera = None
