"""Pick the control source; both modes expose the same six-field interface."""
import importlib
import os
import sys
from pathlib import Path

VISION_DIR = str(Path(__file__).resolve().parent.parent / "camera_behavior_detect")


def _vision_root():
    return os.environ.get("MOTIONQUEST_VISION_DIR", VISION_DIR)


def create_controller(mode: str):
    root = _vision_root()
    if Path(root).is_dir() and root not in sys.path:
        sys.path.insert(0, root)
    try:
        mod = importlib.import_module("camera_control")
    except ImportError as exc:
        raise RuntimeError(
            "找不到摄像头控制模块 camera_control（查找目录：" + str(root) + "）。"
            "键盘模式也复用它提供输入接口；请把 camera_behavior_detect 放在项目旁边，"
            "或用环境变量 MOTIONQUEST_VISION_DIR 指定它的位置。"
        ) from exc
    if mode == "keyboard":
        return mod.FakeCameraController()
    if mode == "pose":
        return mod.CameraController(camera_index=0)
    raise ValueError("未知控制方式：" + str(mode))
