"""MotionQuest camera controls. The game only consumes ControlState."""

from .control_state import ControlState

__all__ = ["ControlState", "CameraController", "FakeCameraController"]


def __getattr__(name):
    # Importing the interface or the fake does not load the camera/model stack.
    if name == "CameraController":
        from .camera_controller import CameraController
        return CameraController
    if name == "FakeCameraController":
        from .fake_controller import FakeCameraController
        return FakeCameraController
    raise AttributeError(name)
