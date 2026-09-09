"""Download Google's official Lite Pose Landmarker model once for local use."""

from pathlib import Path
import sys
import urllib.request
import zipfile


MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
TARGET = Path(__file__).resolve().parent.parent / "models" / "pose_landmarker_lite.task"


def main():
    if TARGET.is_file() and zipfile.is_zipfile(TARGET):
        print(f"Model ready: {TARGET}")
        return
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    temporary = TARGET.with_suffix(".part")
    print("Downloading the official MediaPipe Lite model (about 6 MB)...", flush=True)
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=60) as response, temporary.open("wb") as out:
            while data := response.read(1024 * 1024):
                out.write(data)
        if not zipfile.is_zipfile(temporary):
            raise RuntimeError("The downloaded file isn't a valid task model. Please retry.")
        temporary.replace(TARGET)
        print(f"Model ready: {TARGET}")
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Model download failed: {error}", file=sys.stderr)
        sys.exit(1)
