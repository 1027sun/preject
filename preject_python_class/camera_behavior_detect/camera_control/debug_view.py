"""中文独立调试画面；不参与游戏的动作判断。"""

from functools import lru_cache
from pathlib import Path
import math
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .pose_view import POSE_EDGES as _EDGES
from .pose_view import draw_pose


_BG = (15, 22, 34)
_PANEL = (24, 34, 49)
_LINE = (48, 64, 83)
_TEXT = (232, 239, 248)
_MUTED = (150, 169, 191)
_GREEN = (78, 218, 170)
_BLUE = (99, 171, 255)
_AMBER = (255, 198, 101)
_RED = (255, 117, 126)

@lru_cache(maxsize=8)
def _font(size):
    paths = (
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    )
    for path in paths:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _number(value, digits=2, suffix=""):
    try:
        value = float(value)
        return f"{value:.{digits}f}{suffix}" if math.isfinite(value) else "—"
    except (TypeError, ValueError):
        return "—"


def _wrap(draw, text, font, max_width):
    """Wrap mixed Chinese/English diagnostic messages without clipping."""
    lines, current = [], ""
    for char in str(text):
        if char == "\n":
            lines.append(current)
            current = ""
        elif draw.textlength(current + char, font=font) > max_width and current:
            lines.append(current)
            current = char
        else:
            current += char
    if current:
        lines.append(current)
    return lines


class DebugView:
    """Render a snapshot from the dedicated debug consumer exactly once."""

    WIDTH = 1240
    HEIGHT = 810

    def __init__(self, fake=False):
        self.fake = fake
        self.jump_count = 0
        self._jump_until = 0.0
        self._last_jump_seen = None
        self._lane_step = 0
        self._was_calibrated = False

    def _camera_image(self, snapshot, state):
        frame = snapshot.get("frame")
        if frame is None:
            frame = np.zeros((495, 880, 3), dtype=np.uint8)
            frame[:] = (41, 31, 22)
            if self.fake:
                self._draw_fake_person(frame, state)
        else:
            frame = frame.copy()
            draw_pose(frame, snapshot.get("landmarks"))
        height, width = frame.shape[:2]
        scale = min(880 / width, 495 / height)
        scaled = cv2.resize(frame, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
        fitted = np.zeros((495, 880, 3), dtype=np.uint8)
        fitted[:] = (34, 25, 18)
        left, top = (880 - scaled.shape[1]) // 2, (495 - scaled.shape[0]) // 2
        fitted[top:top + scaled.shape[0], left:left + scaled.shape[1]] = scaled
        self._frame_bounds = (24 + left, 132 + top, scaled.shape[1], scaled.shape[0])
        return Image.fromarray(cv2.cvtColor(fitted, cv2.COLOR_BGR2RGB))

    def _draw_fake_person(self, frame, state):
        x = 440 + int(state.lane) * 195
        offset = -32 if time.monotonic() < self._jump_until else 0
        crouch = 65 if state.crouch else 0
        y = 153 + offset + crouch
        green = (170, 218, 78)
        cv2.circle(frame, (x, y - 50), 28, green, 3, cv2.LINE_AA)
        cv2.line(frame, (x, y - 21), (x, y + 132), green, 4, cv2.LINE_AA)
        for side in (-1, 1):
            shoulder = (x + side * 48, y + 15)
            cv2.line(frame, (x, y + 15), shoulder, green, 4, cv2.LINE_AA)
            if state.hands_up:
                wrist = (x + side * 90, y - 90)
            elif state.arms_open:
                wrist = (x + side * 145, y + 15)
            else:
                wrist = (x + side * 68, y + 123)
            cv2.line(frame, shoulder, wrist, green, 4, cv2.LINE_AA)
            knee = (x + side * (75 if state.crouch else 30), y + 180 - crouch)
            foot = (x + side * 55, 421 + offset)
            cv2.line(frame, (x, y + 132), knee, green, 4, cv2.LINE_AA)
            cv2.line(frame, knee, foot, green, 4, cv2.LINE_AA)

    def render(self, snapshot):
        state = snapshot["state"]
        calibrated = bool(snapshot.get("calibrated"))
        diagnostics = snapshot.get("diagnostics") or {}
        now = time.monotonic()
        if state.jump_triggered:
            self.jump_count += 1
            self._jump_until = now + 0.40
            self._last_jump_seen = now
        if not calibrated:
            self._lane_step = 0
        elif not self._was_calibrated:
            self._lane_step = 0
        if calibrated and self._lane_step < 3 and state.tracking_confidence >= 0.7:
            if state.lane == (-1, 0, 1)[self._lane_step]:
                self._lane_step += 1
        self._was_calibrated = calibrated

        canvas = Image.new("RGB", (self.WIDTH, self.HEIGHT), _BG)
        canvas.paste(self._camera_image(snapshot, state), (24, 132))
        draw = ImageDraw.Draw(canvas)

        def text(x, y, value, size=18, color=_TEXT):
            draw.text((x, y), str(value), font=_font(size), fill=color)

        def box(bounds, fill=_PANEL, outline=None, radius=13):
            draw.rounded_rectangle(bounds, radius, fill=fill, outline=outline, width=1)

        text(24, 17, "MOTIONQUEST", 29)
        text(275, 26, "摄像头动作控制 · 独立测试", 19, _MUTED)
        box((1023, 22, 1216, 61), fill=(30, 57, 56) if not self.fake else (56, 48, 33))
        text(1043, 30, "键盘模拟模式" if self.fake else "实时摄像头模式", 17,
             _AMBER if self.fake else _GREEN)

        error = snapshot.get("error")
        if error:
            headline, color = "设备异常 · 请检查终端中的错误详情", _RED
        elif self.fake:
            headline, color = "键盘模拟已就绪 · 可先验证游戏的六字段接口", _AMBER
        elif not calibrated:
            headline, color = "请全身站入中央框内，自然站直并保持约 2 秒", _AMBER
        elif state.tracking_confidence < 0.5:
            headline, color = "暂时失去追踪 · 请回到摄像头范围", _RED
        elif state.tracking_confidence < 0.7:
            headline, color = "追踪较弱 · 请让肩、髋、膝和双手保持可见", _AMBER
        elif self._lane_step < 3:
            headline = ("校准完成 · 请向画面左侧横移并站稳", "已识别左移 · 请回到中央",
                        "已识别回中 · 请向画面右侧横移并站稳")[self._lane_step]
            color = _GREEN
        else:
            headline, color = "左右移道验证完成 · 回到中央，继续测试跳跃和手臂动作", _GREEN
        text(24, 87, headline, 21, color)
        draw.rounded_rectangle((23, 131, 904, 627), 3, outline=_LINE, width=1)

        if not calibrated and not self.fake:
            fx, fy, fw, fh = self._frame_bounds
            # Match the default calibration limits, including letterboxed cameras.
            guide = (round(fx + fw * 0.15), round(fy + fh * 0.05),
                     round(fx + fw * 0.85), round(fy + fh * 0.95))
            draw.rectangle(guide, outline=_AMBER, width=2)
            center = round(fx + fw / 2)
            draw.line((center, guide[1], center, guide[3]), fill=(115, 112, 83), width=1)
            box((291, 146, 638, 182), fill=(35, 40, 41), radius=5)
            text(306, 152, "面向镜头 · 双脚入框 · 自然站直", 17, _AMBER)
        if snapshot.get("frame") is None:
            if self.fake:
                text(42, 146, "模拟示意 · 不使用摄像头", 17, _AMBER)
            else:
                text(312, 352, "正在等待摄像头画面…", 21, _MUTED)
        if error:
            box((42, 424, 886, 609), fill=(61, 32, 41), radius=8)
            text(58, 438, "启动 / 采集错误", 20, _RED)
            for index, line in enumerate(_wrap(draw, error, _font(17), 804)[:5]):
                text(58, 476 + index * 23, line, 17, _TEXT)

        # Lane tiles and calibration progress are separate from game state.
        for index, (label, value) in enumerate((("左道", -1), ("中道", 0), ("右道", 1))):
            x = 24 + index * 298
            selected = state.lane == value
            box((x, 645, x + 283, 716), fill=(30, 65, 62) if selected else _PANEL,
                outline=_GREEN if selected else _LINE)
            text(x + 20, 662, label, 24, _GREEN if selected else _MUTED)
            text(x + 208, 669, f"{value:+d}" if value else "0", 21,
                 _GREEN if selected else _MUTED)
        if not calibrated:
            progress = max(0.0, min(1.0, float(diagnostics.get("calibration_progress") or 0.0)))
            hint = diagnostics.get("calibration_hint") or "等待稳定人体"
            text(24, 731, f"校准 {progress:.0%} · {hint}", 16, _AMBER)
            draw.rounded_rectangle((24, 762, 904, 768), 3, fill=_LINE)
            if progress > 0:
                draw.rounded_rectangle((24, 762, 24 + round(880 * progress), 768), 3, fill=_GREEN)
        else:
            text(24, 736, "画面已经镜像：你在屏幕中向左移动，lane 就变为 -1。", 16, _MUTED)

        # Persistent action states and pulse counter.
        box((924, 132, 1216, 412))
        text(942, 148, "实时动作", 20)
        jumping = now < self._jump_until
        text(942, 190, "跳跃事件", 18, _MUTED)
        text(1080, 186, f"{self.jump_count} 次", 26, _GREEN if jumping else _TEXT)
        jump_hint = "刚刚触发一次" if jumping else (
            f"距上次 {now - self._last_jump_seen:.1f} 秒" if self._last_jump_seen is not None
            else "每次跳跃只计一次")
        text(942, 226, jump_hint, 15, _GREEN if jumping else _MUTED)
        draw.line((942, 259, 1198, 259), fill=_LINE)
        for index, (name, value) in enumerate((("下蹲", state.crouch), ("双臂水平张开", state.arms_open),
                                               ("双手举起", state.hands_up))):
            y = 276 + index * 40
            draw.ellipse((944, y + 6, 954, y + 16), fill=_GREEN if value else _LINE)
            text(966, y, name, 17, _TEXT if value else _MUTED)
            text(1140, y, "开启" if value else "关闭", 17, _GREEN if value else _MUTED)

        box((924, 428, 1216, 769))
        text(942, 445, "追踪与性能", 20)
        confidence = float(state.tracking_confidence)
        confidence_color = _GREEN if confidence >= 0.7 else _AMBER if confidence >= 0.5 else _RED
        text(942, 480, "追踪可信度", 17, _MUTED)
        text(1134, 480, f"{confidence:.0%}", 19, confidence_color)
        draw.rounded_rectangle((942, 511, 1198, 517), 3, fill=_LINE)
        if confidence > 0:
            draw.rounded_rectangle((942, 511, 942 + int(256 * min(confidence, 1)), 517), 3,
                                   fill=confidence_color)
        rows = (
            ("摄像头 / 姿态 FPS", f"{_number(snapshot.get('camera_fps'), 1)} / {_number(snapshot.get('pose_fps'), 1)}"),
            ("推理延迟 / 结果年龄", f"{_number(snapshot.get('latency_ms'), 0)} / {_number(snapshot.get('pose_age_ms'), 0)} ms"),
            ("横向位移（肩宽）", _number(diagnostics.get("normalized_dx"))),
            ("身体 x / 髋部 y", f"{_number(diagnostics.get('body_center_x'))} / {_number(diagnostics.get('hip_center_y'))}"),
            ("跳跃高度 / 速度", f"{_number(diagnostics.get('jump_height'))} / {_number(diagnostics.get('vertical_speed'))}"),
            ("候选 / 确认车道", f"{diagnostics.get('candidate_lane', '—')} / {state.lane}"),
        )
        for index, (label, value) in enumerate(rows):
            y = 535 + index * 34
            text(942, y, label, 14, _MUTED)
            text(1198 - draw.textlength(value, font=_font(14)), y, value, 14)
        keys = "A 左  F 中  D 右  空格 跳  S 蹲  O 张臂  U 举手  ·  C 重置  ·  Esc/Q 退出" if self.fake else "C 重新校准  ·  Esc / Q 退出  ·  身体尽量完整入镜，保持镜头固定"
        text(24, 786, keys, 14, _MUTED)
        return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)
