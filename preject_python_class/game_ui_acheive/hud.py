"""Pixel Runner HUD: menus, overlays and in-game readouts.

Every clickable widget is registered in ``self.buttons`` (name -> pygame.Rect)
so the main loop can dispatch a mouse click by name through
``ParkourGame.action``. Only the widgets of the current screen are registered,
which keeps hidden buttons unclickable.
"""
import math
from pathlib import Path

import pygame

from camera_preview import CameraPreview

_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
)

PANEL = (16, 25, 38)
EDGE = (62, 94, 124)
TEXT = (235, 245, 255)
MUTED = (152, 174, 198)
ACCENT = (96, 214, 255)
GOLD = (255, 214, 74)
WARN = (255, 183, 47)
BAD = (255, 108, 88)
GOOD = (110, 230, 170)
BUTTON = (42, 104, 134)

_LEGEND = (
    ("wall", "砖墙", "跳跃"),
    ("gap", "缺口", "跳跃"),
    ("tunnel", "隧道", "下蹲"),
    ("sign", "低标牌", "下蹲"),
)
_PRACTICE = ("换道", "跳跃", "下蹲", "护盾", "冲刺")
TITLE_TEXT = "一起运动吧"
TITLE_COLORS = ((96, 214, 255), (255, 214, 74), (110, 230, 170),
                (255, 150, 96), (198, 150, 255))


class HUD:
    def __init__(self):
        self.buttons = {}
        self._fonts = {}
        self._dim = None
        self._preview = None
        self.preview_error = ""
        self._title_cache = {}

    # ---------------------------------------------------------------- primitives
    def _font(self, size):
        font = self._fonts.get(size)
        if font is None:
            font = self._load_font(size)
            self._fonts[size] = font
        return font

    @staticmethod
    def _load_font(size):
        for path in _FONT_CANDIDATES:
            if Path(path).is_file():
                try:
                    return pygame.font.Font(path, size)
                except OSError:
                    continue
        return pygame.font.Font(None, size)

    def t(self, s, text, pos, c=TEXT, size=22):
        s.blit(self._font(size).render(str(text), True, c), (int(pos[0]), int(pos[1])))

    def center(self, s, text, cx, y, size=22, c=TEXT):
        image = self._font(size).render(str(text), True, c)
        s.blit(image, (int(cx - image.get_width() / 2), int(y)))
        return image

    def panel(self, s, rect, alpha=236, edge=EDGE, fill=PANEL):
        rect = pygame.Rect(rect)
        layer = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(layer, (*fill, alpha), layer.get_rect(), border_radius=14)
        if edge:
            pygame.draw.rect(layer, (*edge, 255), layer.get_rect(), width=2, border_radius=14)
        s.blit(layer, rect.topleft)
        return rect

    def dim(self, s, alpha=150):
        if self._dim is None or self._dim.get_size() != s.get_size():
            self._dim = pygame.Surface(s.get_size(), pygame.SRCALPHA)
            self._dim.fill((3, 7, 13, alpha))
        self._dim.set_alpha(alpha)
        s.blit(self._dim, (0, 0))

    def button(self, s, name, label, rect, hint="", fill=BUTTON, size=22):
        rect = pygame.Rect(rect)
        pygame.draw.rect(s, fill, rect, border_radius=10)
        pygame.draw.rect(s, EDGE, rect, width=2, border_radius=10)
        image = self._font(size).render(str(label), True, TEXT)
        s.blit(image, (rect.x + 20, rect.centery - image.get_height() // 2))
        if hint:
            small = self._font(17).render(str(hint), True, MUTED)
            s.blit(small, (rect.right - small.get_width() - 20,
                           rect.centery - small.get_height() // 2))
        self.buttons[name] = rect
        return rect

    def bar(self, s, rect, ratio, color=ACCENT):
        rect = pygame.Rect(rect)
        pygame.draw.rect(s, (30, 44, 60), rect, border_radius=6)
        width = int(rect.width * max(0.0, min(1.0, ratio)))
        if width:
            pygame.draw.rect(s, color, (rect.x, rect.y, width, rect.height), border_radius=6)
        pygame.draw.rect(s, EDGE, rect, width=2, border_radius=6)

    def fit(self, text, size, max_width):
        """Trim a long message so it cannot overflow its panel."""
        text = str(text)
        font = self._font(size)
        if font.size(text)[0] <= max_width:
            return text
        while text and font.size(text + "…")[0] > max_width:
            text = text[:-1]
        return text + "…"

    @staticmethod
    def countdown_label(g):
        """Digits shown during the 3-2-1 freeze before the world starts moving."""
        if g.countdown <= 0:
            return ""
        return str(max(1, int(math.ceil(g.countdown - 1e-9))))

    def _preview_surface(self, g, width):
        """Camera frame with the skeleton drawn by the vision module."""
        if self._preview is None or self._preview.width != width:
            self._preview = CameraPreview(width=width)
        surface = self._preview.surface(getattr(g, "c", None))
        self.preview_error = self._preview.error
        return surface

    def _preview_caption(self, s, g, x, y, width, height):
        """实时动作读数：车道、追踪可信度与当前识别到的动作。"""
        state = getattr(g, "last_state", None)
        confidence = state.tracking_confidence if state else 0.0
        color = GOOD if confidence >= .7 else WARN if confidence >= .5 else BAD
        lane = "中" if state is None else ("左", "中", "右")[state.lane + 1]
        actions = []
        if state is not None:
            if state.jump_triggered: actions.append("跳跃")
            if state.crouch: actions.append("下蹲")
            if state.arms_open: actions.append("张臂护盾")
            if state.hands_up: actions.append("举手冲刺")
        text = (f"车道 {lane} · 追踪 {confidence:.0%} · "
                + ("/".join(actions) if actions else "自然站立"))
        strip = pygame.Rect(x, y + height - 26, width, 26)
        layer = pygame.Surface(strip.size, pygame.SRCALPHA)
        layer.fill((8, 14, 22, 205))
        s.blit(layer, strip.topleft)
        self.t(s, self.fit(text, 17, width - 12), (strip.x + 6, strip.y + 4),
               color, size=17)

    # ------------------------------------------------------------------- screens
    def draw(self, s, g):
        self.buttons = {}
        w, h = s.get_size()
        if g.mode:
            self._top_bar(s, g, w)
        if g.settings:
            self._settings(s, g, w, h)
        elif g.home and not g.mode:
            self._home(s, g, w, h)
        elif not g.mode:
            self._mode_select(s, g, w, h)
        elif g.over:
            self._game_over(s, g, w, h)
        elif g.manual_pause:
            self._pause(s, g, w, h)
        elif g.mode == "pose" and (g.guide or g.calibrating):
            self._briefing(s, g, w, h, pose=True)
        elif g.guide:
            self._briefing(s, g, w, h, pose=False)
        elif g.practice:
            self._practice(s, g, w, h)
        else:
            self._play(s, g, w, h)
        if g.mode and not g.settings:
            if g.error:
                self._toast(s, g.error, w, BAD)
            elif g.notice and g.notice_t > 0:
                self._toast(s, g.notice, w, WARN)

    def _top_bar(self, s, g, w):
        self.t(s, f"分数 {g.score}", (24, 16), size=38)
        self.t(s, f"金币 {g.coins}", (26, 62), GOLD, size=22)
        self.bar(s, (24, 98, 220, 18), g.energy / max(1.0, g.cfg.energy_max))
        self.t(s, f"能量 {int(g.energy)}/{int(g.cfg.energy_max)}", (256, 97), MUTED, size=17)
        self.t(s, f"距离 {int(g.distance)} 米   最高 {g.best}"
               f"   难度 {g.difficulty.label}", (24, 124), MUTED, size=17)
        if g.shield_t > 0:
            self.t(s, f"护盾 {g.shield_t:.1f}s", (24, 150), ACCENT, size=17)
        if g.dash_t > 0:
            self.t(s, f"冲刺 {g.dash_t:.1f}s", (24 + (110 if g.shield_t > 0 else 0), 150),
                   GOLD, size=17)

    def _art_title(self, s, w, y, size=84):
        """主菜单艺术字：描边、多色、逐字轻微起伏。"""
        ticks = pygame.time.get_ticks() / 1000.0
        font = self._font(size)
        images = []
        for index, char in enumerate(TITLE_TEXT):
            key = (char, index, size)
            canvas = self._title_cache.get(key)
            if canvas is None:
                body = font.render(char, True, TITLE_COLORS[index % len(TITLE_COLORS)])
                shade = font.render(char, True, (10, 18, 30))
                canvas = pygame.Surface((body.get_width() + 10, body.get_height() + 10),
                                        pygame.SRCALPHA)
                for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3),
                               (-2, -2), (2, -2), (-2, 2), (2, 2)):
                    canvas.blit(shade, (5 + dx, 5 + dy))
                canvas.blit(body, (5, 5))
                self._title_cache[key] = canvas
            angle = math.sin(ticks * 1.5 + index * 0.8) * 5
            images.append(pygame.transform.rotate(canvas, angle))
        gap = 8
        total = sum(image.get_width() for image in images) + gap * (len(images) - 1)
        x = w // 2 - total // 2
        for index, image in enumerate(images):
            bob = math.sin(ticks * 1.5 + index * 0.8) * 5
            s.blit(image, (x, int(y + bob)))
            x += image.get_width() + gap

    def _home(self, s, g, w, h):
        self._art_title(s, w, 72)
        self.center(s, "PIXEL RUNNER · 体感三车道跑酷", w // 2, 210, 22, MUTED)
        self.button(s, "mode_select", "开始游戏", (w // 2 - 180, 250, 360, 62), "Enter")
        self.button(s, "settings", "设置", (w // 2 - 180, 326, 360, 62))
        self.button(s, "exit", "退出游戏", (w // 2 - 180, 402, 360, 62))
        self.center(s, f"最高分 {g.best}", w // 2, 492, 22, GOLD)
        self.center(s, "K 键盘控制 · C 摄像头体态 · Esc 退出", w // 2, 532, 17, MUTED)

    def _mode_select(self, s, g, w, h):
        self.center(s, "选择控制方式", w // 2, 80, 38)
        left = self.panel(s, (w // 2 - 390, 150, 350, 310))
        right = self.panel(s, (w // 2 + 40, 150, 350, 310))
        self.center(s, "键盘控制", left.centerx, left.y + 24, 28)
        for i, line in enumerate(("← → / A D 换道", "空格 / W / ↑ 跳跃",
                                  "S / ↓ 按住下蹲", "O 张臂护盾 · U 举手冲刺")):
            self.center(s, line, left.centerx, left.y + 82 + i * 30, 17, MUTED)
        self.button(s, "keyboard", "用键盘开始", (left.x + 45, left.bottom - 70, 260, 54), "K")
        self.center(s, "摄像头体态", right.centerx, right.y + 24, 28)
        for i, line in enumerate(("身体左右横移换道", "实际跳起 / 下蹲",
                                  "张臂护盾 · 举手冲刺", "需要摄像头与体态模块")):
            self.center(s, line, right.centerx, right.y + 82 + i * 30, 17, MUTED)
        self.button(s, "pose", "用摄像头开始", (right.x + 45, right.bottom - 70, 260, 54), "C")
        self.button(s, "menu", "返回", (24, h - 84, 160, 54))
        if g.error:
            self.center(s, self.fit(g.error, 17, w - 160), w // 2, 486, 17, BAD)

    def _settings(self, s, g, w, h):
        self.dim(s, 170)
        rect = self.panel(s, (w // 2 - 330, 40, 660, h - 80))
        self.center(s, "设置", w // 2, rect.y + 16, 38)
        rows = (
            ("difficulty", "难度", g.difficulty.label,
             g.difficulty.note + "（点击切换）"),
            ("flash", "减少闪烁", "开" if g.reduced_flash else "关", "碰撞时不再整屏闪红"),
            ("sound", "声音总开关", "开" if g.audio.enabled else "关", "关闭后音乐与音效一起静音"),
            ("music", "背景音乐音量", f"{int(g.audio.music_volume * 100)}%", "点击循环 0% → 100%"),
            ("effects", "音效音量", f"{int(g.audio.effects_volume * 100)}%", "点击循环 0% → 100%"),
        )
        y = rect.y + 78
        for name, label, value, note in rows:
            self.t(s, label, (rect.x + 40, y), size=22)
            self.t(s, note, (rect.x + 40, y + 28), MUTED, size=17)
            self.button(s, name, value, (rect.right - 200, y - 6, 160, 48))
            y += 68
        footer = rect.bottom - 108
        self.button(s, "fullscreen", "全屏 / 窗口", (rect.x + 40, footer, 260, 50), "F11")
        self.button(s, "close_settings", "返回", (rect.right - 200, footer, 160, 50))
        note = self._preview_error_note()
        self.center(s, self.fit("设置立即生效并保存到 preferences.json" + note,
                               17, rect.width - 60),
                    w // 2, rect.bottom - 34, 17, MUTED)

    def _preview_error_note(self):
        return "" if not self.preview_error else f"　（预览不可用：{self.preview_error}）"

    def _game_over(self, s, g, w, h):
        self.dim(s, 175)
        pose = getattr(g, "mode", None) == "pose"
        height = 470 if pose else 380
        rect = self.panel(s, (w // 2 - 330, h // 2 - height // 2, 660, height))
        self.center(s, "本局结束", w // 2, rect.y + 20, 38)
        if g.new_best:
            self.center(s, "新纪录！", w // 2, rect.y + 70, 22, GOLD)
        self.center(s, self.fit(g.death_reason or "撞到了障碍", 22, rect.width - 80),
                    w // 2, rect.y + 106, 22, WARN)
        stats = (("距离", f"{int(g.distance)} 米"), ("得分", str(g.score)),
                 ("金币", str(g.coins)), ("避障", str(g.passed)),
                 ("最高分", str(g.best)))
        for index, (label, value) in enumerate(stats):
            column, row = index % 3, index // 3
            x = rect.x + 54 + column * 200
            y = rect.y + 146 + row * 46
            self.t(s, label, (x, y + 4), MUTED, size=17)
            self.t(s, value, (x + 62, y), size=22)
        if pose:
            # 体态模式独有的运动结算：四个动作次数与热量估算。
            items, total, kcal = g.exercise_summary()
            pygame.draw.line(s, EDGE, (rect.x + 40, rect.y + 240),
                             (rect.right - 40, rect.y + 240))
            self.center(s, "本轮运动数据", w // 2, rect.y + 250, 22)
            column = rect.width / len(items)
            for index, (label, value) in enumerate(items):
                cx = int(rect.x + column * (index + 0.5))
                color = GOLD if label == "热量" else ACCENT
                self.center(s, label, cx, rect.y + 292, 17, MUTED)
                self.center(s, value, cx, rect.y + 312, 30, color)
            self.center(s, f"共 {total} 次动作 · 每个动作计 {g.cfg.calories_per_action:g} 千卡",
                        w // 2, rect.y + 358, 17, MUTED)
        self.button(s, "restart", "再跑一次", (rect.x + 54, rect.bottom - 84, 250, 58), "Enter")
        self.button(s, "menu", "返回主菜单", (rect.right - 304, rect.bottom - 84, 250, 58))

    def _pause(self, s, g, w, h):
        self.dim(s, 155)
        rect = self.panel(s, (w // 2 - 270, h // 2 - 175, 540, 350))
        self.center(s, "已暂停", w // 2, rect.y + 22, 38)
        self.center(s, f"距离 {int(g.distance)} 米 · 得分 {g.score} · 金币 {g.coins}",
                    w // 2, rect.y + 84, 22, MUTED)
        self.button(s, "pause", "继续游戏", (rect.x + 40, rect.y + 134, 460, 54), "Esc")
        self.button(s, "restart", "重新开始", (rect.x + 40, rect.y + 198, 220, 54))
        self.button(s, "settings", "设置", (rect.x + 280, rect.y + 198, 220, 54))
        self.button(s, "menu", "返回主菜单", (rect.x + 40, rect.y + 262, 460, 54))

    def _briefing(self, s, g, w, h, pose):
        calibrating = bool(g.calibrating)
        title = ("摄像头体态 · 站立校准" if calibrating else
                 "摄像头体态 · 准备开始" if pose else "键盘控制 · 准备开始")
        self.center(s, title, w // 2, 36, 38)

        left_width = min(560, int(w * 0.48) - 20)
        left = pygame.Rect(40, 96, left_width, 315)
        if pose:
            surface = self._preview_surface(g, left_width)
            if surface:
                s.blit(surface, left.topleft)
                pygame.draw.rect(s, EDGE, left, width=2)
                if calibrating:
                    frame = pygame.Rect(left.x + int(left.width * 0.15),
                                        left.y + int(left.height * 0.05),
                                        int(left.width * 0.70), int(left.height * 0.90))
                    pygame.draw.rect(s, WARN, frame, width=2)
                self._preview_caption(s, g, left.x, left.y,
                                      surface.get_width(), surface.get_height())
            else:
                self.panel(s, left)
                self.center(s, "正在等待摄像头画面…", left.centerx, left.centery - 20, 22, MUTED)
                self.center(s, "请确认摄像头未被其他程序占用", left.centerx, left.centery + 14, 17, MUTED)
        else:
            self._monitor(s, g, left)

        self._legend(s, (40, 424, left_width, 140))

        right = self.panel(s, (left.right + 24, 96, w - left.right - 64, 468))
        if calibrating:
            self.t(s, self.fit("面向镜头 · 全身入框 · 自然站直", 22, right.width - 56),
                   (right.x + 28, right.y + 22), size=22)
            self.bar(s, (right.x + 28, right.y + 76, right.width - 56, 20), g.calibration_progress)
            self.t(s, f"校准进度 {int(g.calibration_progress * 100)}%",
                   (right.x + 28, right.y + 104), ACCENT, size=17)
            self.t(s, self.fit(g.calibration_hint or "请全身入镜并自然站立",
                               17, right.width - 56),
                   (right.x + 28, right.y + 140), WARN, size=17)
            self.t(s, self.fit("双手自然下垂，保持约 2 秒；移动后需重新站稳。",
                               17, right.width - 56),
                   (right.x + 28, right.y + 176), MUTED, size=17)
        else:
            self.t(s, "操作", (right.x + 28, right.y + 22), size=22)
            lines = (("身体左右横移换道", "身体下蹲 / 实际跳起",
                      "张臂护盾 · 举手冲刺", "C 重新校准") if pose else
                     ("← → / A D 换道", "空格 / W / ↑ 跳跃",
                      "S / ↓ 按住下蹲", "O 张臂护盾 · U 举手冲刺"))
            for i, line in enumerate(lines):
                self.t(s, self.fit(line, 17, right.width - 56),
                       (right.x + 28, right.y + 68 + i * 30), MUTED, size=17)
            tip = ("校准已完成，站回画面中央后按 Enter 开始。" if pose else
                   "红色砖墙与缺口要跳，隧道与低标牌要蹲；也可以换道躲开。")
            self.t(s, self.fit(tip, 17, right.width - 56),
                   (right.x + 28, right.y + 204), TEXT, size=17)

        width = right.width - 56
        if not calibrating:
            self.button(s, "start", "开始奔跑", (right.x + 28, right.bottom - 190, width, 54),
                        "Enter")
            self.button(s, "practice", "安全练习", (right.x + 28, right.bottom - 126,
                                                (width - 16) // 2, 54))
        if pose:
            x = right.x + 28 if calibrating else right.x + 28 + (width - 16) // 2 + 16
            self.button(s, "calibrate", "重新校准",
                        (x, right.bottom - 126, (width - 16) // 2, 54), "C")
        self.button(s, "menu", "返回主菜单", (right.x + 28, right.bottom - 62, width, 54))

    def _monitor(self, s, g, rect):
        self.panel(s, rect, alpha=214)
        self.t(s, "动作模拟 · 键盘输入状态", (rect.x + 24, rect.y + 14), size=22)
        self.t(s, f"能量 {int(g.energy)}/{int(g.cfg.energy_max)}",
               (rect.right - 150, rect.y + 18), MUTED, size=17)
        state = getattr(g, "last_state", None)
        lane = 0 if state is None else state.lane
        for index, name in enumerate(("左", "中", "右")):
            cell = pygame.Rect(rect.x + 40 + index * 118, rect.y + 62, 96, 66)
            here = (index - 1) == lane
            pygame.draw.rect(s, (30, 65, 62) if here else (26, 36, 50), cell, border_radius=10)
            pygame.draw.rect(s, GOOD if here else EDGE, cell, width=2, border_radius=10)
            self.center(s, name, cell.centerx, cell.y + 8, 22, GOOD if here else MUTED)
            self.center(s, f"{index - 1:+d}", cell.centerx, cell.y + 38, 17, MUTED)
        rows = (("跳跃事件", "触发" if state and state.jump_triggered else "—"),
                ("下蹲", "开" if state and state.crouch else "关"),
                ("张臂护盾", "开" if state and state.arms_open else "关"),
                ("举手冲刺", "开" if state and state.hands_up else "关"))
        for index, (label, value) in enumerate(rows):
            y = rect.y + 152 + index * 30
            self.t(s, label, (rect.x + 40, y), MUTED, size=17)
            self.t(s, value, (rect.x + 250, y), TEXT, size=17)

    def _legend(self, s, rect):
        rect = self.panel(s, rect, alpha=214)
        self.t(s, "障碍图例", (rect.x + 24, rect.y + 12), size=22)
        step = (rect.width - 72) / len(_LEGEND)
        for index, (kind, name, action) in enumerate(_LEGEND):
            cx = int(rect.x + 36 + step * (index + 0.5))
            self._obstacle_icon(s, cx, rect.y + 104, kind)
            self.center(s, name, cx, rect.y + 110, 17)
            self.center(s, action, cx, rect.y + 74, 17, WARN)

    def _obstacle_icon(self, s, cx, base, kind):
        if kind == "wall":
            pygame.draw.ellipse(s, (66, 53, 43), (cx - 18, base - 6, 36, 8))
            pygame.draw.rect(s, (188, 60, 46), (cx - 15, base - 36, 30, 32))
            pygame.draw.rect(s, (239, 159, 102), (cx - 15, base - 36, 30, 4))
            for row in (1, 2):
                pygame.draw.line(s, (114, 47, 41), (cx - 15, base - 36 + row * 11),
                                 (cx + 14, base - 36 + row * 11))
        elif kind == "gap":
            pygame.draw.polygon(s, (24, 27, 34), ((cx - 16, base - 30), (cx + 16, base - 30),
                                                  (cx + 21, base), (cx - 21, base)))
            pygame.draw.line(s, (229, 174, 63), (cx - 16, base - 30), (cx + 16, base - 30), 2)
        elif kind == "tunnel":
            pygame.draw.rect(s, (62, 80, 86), (cx - 17, base - 38, 34, 38))
            pygame.draw.rect(s, (23, 38, 46), (cx - 11, base - 29, 22, 29))
            pygame.draw.rect(s, (229, 189, 61), (cx - 17, base - 38, 34, 5))
        else:
            pygame.draw.rect(s, (117, 132, 134), (cx - 17, base - 30, 4, 30))
            pygame.draw.rect(s, (117, 132, 134), (cx + 13, base - 30, 4, 30))
            pygame.draw.rect(s, (239, 183, 47), (cx - 19, base - 38, 38, 11))

    def _practice(self, s, g, w, h):
        rect = self.panel(s, (30, 150, 430, 400))
        self.t(s, "安全练习", (rect.x + 26, rect.y + 18), size=28)
        self.t(s, "不扣能量、不会碰撞；做动作即可打勾", (rect.x + 26, rect.y + 58), MUTED, size=17)
        for index, name in enumerate(_PRACTICE):
            y = rect.y + 108 + index * 44
            done = name in g.practice_done
            pygame.draw.circle(s, GOOD if done else (56, 72, 92), (rect.x + 44, y + 14), 10)
            if done:
                pygame.draw.circle(s, (12, 32, 26), (rect.x + 44, y + 14), 10, 3)
            self.t(s, name, (rect.x + 68, y), TEXT if done else MUTED, size=22)
            self.t(s, "已完成" if done else "未完成", (rect.x + 250, y + 3),
                   GOOD if done else MUTED, size=17)
        self.t(s, "按 Enter 结束练习并开始正式奔跑", (rect.x + 26, rect.bottom - 116), MUTED, size=17)
        self.button(s, "start", "开始正式跑", (rect.x + 26, rect.bottom - 84, 210, 58))
        self.button(s, "practice_exit", "返回说明", (rect.x + 248, rect.bottom - 84, 156, 58))

    def _play(self, s, g, w, h):
        label = self.countdown_label(g)
        if label:
            self.dim(s, 96)
            self.center(s, label, w // 2, h // 2 - 96, 64)
            self.center(s, "准备…", w // 2, h // 2 + 4, 28, MUTED)
        hint = g.next_hint()
        if hint:
            box = self.panel(s, (w // 2 - 120, h - 148, 240, 52), alpha=214)
            self.center(s, hint, box.centerx, box.y + 13, 22, WARN)
        if g.mode == "pose" and g.preview_on:
            surface = self._preview_surface(g, 320)
            if surface:
                pos = (w - surface.get_width() - 24, 24)
                s.blit(surface, pos)
                pygame.draw.rect(s, EDGE, (pos[0], pos[1], surface.get_width(),
                                           surface.get_height()), width=2)
                self._preview_caption(s, g, pos[0], pos[1],
                                      surface.get_width(), surface.get_height())
            else:
                self.t(s, "预览不可用", (w - 130, 30), MUTED, size=17)
        self.t(s, "P 预览 · G 说明 · Esc 暂停", (20, h - 35), MUTED, size=17)

    def _toast(self, s, message, w, color):
        message = self.fit(message, 22, min(820, w - 200))
        width = min(860, max(320, self._font(22).size(message)[0] + 60))
        rect = self.panel(s, (w // 2 - width // 2, 190, width, 56), alpha=225,
                          edge=color, fill=(28, 34, 46))
        self.center(s, message, rect.centerx, rect.y + 15, 22, color)
