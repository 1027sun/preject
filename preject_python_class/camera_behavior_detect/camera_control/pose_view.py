"""Skeleton overlay shared by the debug window and the game preview.

Only OpenCV is required here, so the game can reuse the exact landmark
topology and visibility rules without pulling in the drawing dependencies of
the full debug panel.
"""
import cv2

#: MediaPipe Pose connections used for the bone lines.
POSE_EDGES = ((11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
              (11, 23), (12, 24), (23, 24), (23, 25), (25, 27),
              (24, 26), (26, 28), (27, 29), (29, 31), (28, 30), (30, 32))

BONE_COLOR = (170, 218, 78)
JOINT_COLOR = (255, 245, 225)
MIN_VISIBILITY = 0.5


def draw_pose(frame, landmarks, scale=1.0, bone=BONE_COLOR, joint=JOINT_COLOR,
              min_visibility=MIN_VISIBILITY):
    """Draw the tracked skeleton on a BGR frame in place, then return it.

    ``landmarks`` is a MediaPipe-style sequence (``x`` / ``y`` in 0-1 plus
    ``visibility``); ``None`` or an empty sequence is a no-op. ``scale`` keeps
    the line weight readable when the frame is a small preview.
    """
    if not landmarks:
        return frame
    height, width = frame.shape[:2]
    thickness = max(1, int(round(3 * scale)))
    radius = max(1, int(round(4 * scale)))

    def visible(index):
        return (index < len(landmarks)
                and getattr(landmarks[index], "visibility", 1.0) >= min_visibility)

    def point(index):
        item = landmarks[index]
        return int(item.x * width), int(item.y * height)

    for first, second in POSE_EDGES:
        if visible(first) and visible(second):
            cv2.line(frame, point(first), point(second), bone, thickness, cv2.LINE_AA)
    for index in {item for edge in POSE_EDGES for item in edge}:
        if visible(index):
            cv2.circle(frame, point(index), radius, joint, -1, cv2.LINE_AA)
    return frame
