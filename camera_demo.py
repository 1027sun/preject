"""Run the independent camera test window or a bounded headless smoke run."""

import argparse
from dataclasses import asdict
import json
import sys
import time


def _arguments():
    parser = argparse.ArgumentParser(description="MotionQuest 摄像头动作测试")
    parser.add_argument("--camera", type=int, default=0, help="摄像头编号，默认 0")
    parser.add_argument("--fake", action="store_true", help="键盘模拟六字段接口，不打开摄像头")
    parser.add_argument("--headless", action="store_true", help="无窗口运行，终端输出状态")
    parser.add_argument("--duration", type=float, help="运行多少秒后退出；默认持续运行")
    args = parser.parse_args()
    if args.duration is not None and args.duration <= 0:
        parser.error("--duration 必须大于 0")
    return args


def main():
    args = _arguments()
    # The fake controller can run headless without importing the vision stack.
    if args.fake:
        from camera_control.fake_controller import FakeCameraController
        controller = FakeCameraController()
    else:
        from camera_control.camera_controller import CameraController
        controller = CameraController(camera_index=args.camera)

    cv2 = view = None
    window = "MotionQuest - Camera Control"
    if not args.headless:
        import cv2
        from camera_control.debug_view import DebugView
        view = DebugView(fake=args.fake)

    started = time.monotonic()
    next_report = started
    samples = jumps = 0
    maximum_confidence = 0.0
    ever_calibrated = False
    last_snapshot = None
    result = 0
    last_error = None
    print("MotionQuest 键盘模拟启动中…" if args.fake else "MotionQuest 摄像头启动中…", flush=True)
    try:
        controller.start()
        controller.request_calibration()
        if cv2 is not None:
            cv2.namedWindow(window, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(window, 1240, 810)
        started = time.monotonic()
        next_report = started
        while args.duration is None or time.monotonic() - started < args.duration:
            iteration_start = time.monotonic()
            snapshot = controller.get_debug_snapshot()
            last_snapshot = snapshot
            state = snapshot["state"]
            samples += 1
            jumps += int(state.jump_triggered)
            maximum_confidence = max(maximum_confidence, state.tracking_confidence)
            ever_calibrated = ever_calibrated or bool(snapshot.get("calibrated"))
            error = snapshot.get("error")
            if error and error != last_error:
                print(f"错误：{error}", file=sys.stderr, flush=True)
                last_error = error
                result = 1
            if iteration_start >= next_report:
                print(json.dumps({
                    "calibrated": bool(snapshot.get("calibrated")),
                    "camera_fps": round(float(snapshot.get("camera_fps") or 0.0), 1),
                    "pose_fps": round(float(snapshot.get("pose_fps") or 0.0), 1),
                    "latency_ms": snapshot.get("latency_ms"),
                    **asdict(state),
                }, ensure_ascii=False), flush=True)
                next_report = iteration_start + 1.0
            if cv2 is not None:
                cv2.imshow(window, view.render(snapshot))
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q"), ord("Q")):
                    break
                if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                    break
                if key in (ord("c"), ord("C")):
                    controller.request_calibration()
                elif args.fake:
                    if key in (ord("a"), ord("A")):
                        controller.set_lane(-1)
                    elif key in (ord("f"), ord("F")):
                        controller.set_lane(0)
                    elif key in (ord("d"), ord("D")):
                        controller.set_lane(1)
                    elif key == 32:
                        controller.trigger_jump()
                    elif key in (ord("s"), ord("S")):
                        controller.toggle_action("crouch")
                    elif key in (ord("o"), ord("O")):
                        controller.toggle_action("arms_open")
                    elif key in (ord("u"), ord("U")):
                        controller.toggle_action("hands_up")
            elif error:
                break
            # Capture and pose run independently; keep UI overhead to 20 Hz.
            time.sleep(max(0.0, 0.05 - (time.monotonic() - iteration_start)))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"启动或运行失败：{exc}", file=sys.stderr, flush=True)
        result = 1
        last_error = str(exc)
    finally:
        try:
            controller.stop()
        except Exception as exc:
            result = 1
            last_error = f"释放摄像头失败：{exc}"
            print(last_error, file=sys.stderr, flush=True)
        if cv2 is not None:
            cv2.destroyAllWindows()
        summary = {
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "samples": samples,
            "jump_count": jumps,
            "max_tracking_confidence": round(maximum_confidence, 3),
            "calibrated": ever_calibrated,
            "error": last_error,
        }
        if last_snapshot is not None:
            summary["final_state"] = asdict(last_snapshot["state"])
        print("运行结束 " + json.dumps(summary, ensure_ascii=False), flush=True)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
