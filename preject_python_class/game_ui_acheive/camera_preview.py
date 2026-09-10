"""Camera preview bridge for the game window.

The vision package owns the landmark semantics, so the skeleton is drawn by
``CameraController.get_annotated_preview()``; this module only converts the
returned RGB array into a Pygame Surface. That keeps MediaPipe's joint
topology out of the game and keeps keyboard mode free of the vision stack.
"""
import pygame


class CameraPreview:
    """Latest camera frame as a Surface, with the tracked skeleton on top."""

    def __init__(self, width=320, fake=False):
        self.width = int(width)
        self.fake = fake
        self.error = ""
        self.annotated = True

    def surface(self, controller):
        """Return a Surface for the latest frame, or ``None`` when unavailable."""
        if controller is None:
            return None
        frame = self._annotated(controller)
        if frame is None:
            frame = self._plain(controller)
        if frame is None:
            return None
        height, width = frame.shape[:2]
        # copy() detaches the Surface from the temporary frame buffer.
        return pygame.image.frombuffer(frame.tobytes(), (width, height), "RGB").copy()

    def _annotated(self, controller):
        """Skeleton preview; older vision modules do not implement it."""
        getter = getattr(controller, "get_annotated_preview", None)
        if getter is None:
            self.annotated = False
            return None
        try:
            frame = getter(self.width)
        except Exception as exc:  # surfaced to the player through self.error
            self.error = str(exc)
            return None
        self.annotated = frame is not None
        self.error = ""
        return frame

    def _plain(self, controller):
        try:
            frame = controller.get_preview_frame(self.width)
        except Exception as exc:
            self.error = str(exc)
            return None
        self.error = ""
        return frame
