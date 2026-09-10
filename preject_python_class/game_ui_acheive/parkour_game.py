"""Three-lane runner; pose and keyboard share the same control boundary."""
import argparse
import random
from pathlib import Path
import json
import pygame
from game_config import DIFFICULTY_ORDER, GameConfig, difficulty
from input_adapter import create_controller
from level import LevelSpawner
from player import Player
from hud import HUD
from rendering.pixel_renderer import PixelRenderer
from audio import Audio

class ParkourGame:
    def __init__(self, cfg):
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("一起运动吧")
        self.s = pygame.display.set_mode((1280, 720), pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.cfg = cfg
        self.c = None
        self.mode = None
        self.guide = True
        self.calibrating = False
        self.calibration_hint = ""
        self.preview_on = True
        self.settings = False
        self.home = True
        self.camera_preview = None
        self.error = ""
        self.rng = random.Random()
        self.hud = HUD()
        self.pixel = PixelRenderer()
        self.audio = Audio()
        self.settings_path = Path(__file__).with_name("preferences.json")
        try: self.preferences = json.loads(self.settings_path.read_text(encoding="utf-8"))
        except (OSError, ValueError): self.preferences = {}
        stored = self.preferences.get("difficulty")
        if stored not in DIFFICULTY_ORDER:
            stored = "easy" if self.preferences.get("easy", False) else "normal"
        self.difficulty_key = str(stored)
        self.difficulty = difficulty(self.difficulty_key)
        self.reduced_flash = self.preferences.get("reduced_flash", False)
        self.best = self.preferences.get("best", 0)
        self.audio.enabled = self.preferences.get("sound", self.audio.enabled) and self.audio.enabled
        self.audio.set_volumes(self.preferences.get("music",.6),self.preferences.get("effects",.8))
        self.level = LevelSpawner(cfg, self.rng, self.difficulty)
        self.reset_run(False)

    def reset_run(self, reset_controller=True):
        self.paused = self.over = False
        self.manual_pause = False
        self.countdown = 0.
        self.energy_clock = 0.
        self.distance = 0.
        self.passed = 0
        self.death_reason = ""
        self.new_best = False
        self.notice = ""
        self.notice_t = 0.
        self.held = set()
        self.practice = False
        self.practice_done = set()
        self.last_state = None
        self.jump_preview = 0.
        self.calibration_progress = 0.
        self.elapsed = 0.
        self.score = self.coins = 0
        self.energy = min(65., self.cfg.energy_max)
        self.shield_t = self.dash_t = 0.
        self.prev_arms = self.prev_hands = False
        self.prev_crouch = False
        self.action_counts = {"起跳": 0, "下蹲": 0, "张臂": 0, "举手": 0}
        self.flash = 0.
        self.player = Player()
        self.obs = []
        self.coins_world = []
        self.level.reset()
        self.pixel.reset()
        if reset_controller and self.c:
            if self.mode == "keyboard":
                self.c.request_calibration()
            else:
                # Preserve standing calibration; held gestures must be released.
                state = self.c.get_state()
                self.prev_arms, self.prev_hands = state.arms_open, state.hands_up
                self.prev_crouch = state.crouch
        self.audio.set_running(False)
        if reset_controller: self.countdown = 3.

    def choose(self, mode):
        controller = None
        try:
            controller = create_controller(mode)
            controller.start()
            if mode == "pose":
                controller.request_calibration()
        except Exception as exc:
            if controller:
                controller.stop()
            self.error = str(exc)
            return
        if self.c: self.c.stop()
        self.c, self.mode = controller, mode
        self.guide = True
        self.calibrating = mode == "pose"
        self.error = ""

    def speed(self):
        base = max(self.cfg.end_speed, self.cfg.start_speed -
                   (self.cfg.start_speed-self.cfg.end_speed)*self.elapsed/120)
        return base*self.difficulty.speed_scale*(1.65 if self.dash_t > 0 else 1)

    def set_difficulty(self, key):
        """切换难度并立即生效（障碍波次与速度同时改变）。"""
        self.difficulty = difficulty(key)
        self.difficulty_key = self.difficulty.key
        self.level.set_difficulty(self.difficulty)

    def next_hint(self):
        """轻松模式提示前方障碍需要的动作；标准模式返回空串。"""
        if not self.difficulty.hint:
            return ""
        pending = [o for o in self.obs if not o.checked
                   and abs(o.lane-self.player.position) < .46]
        if not pending:
            return ""
        kind = max(pending, key=lambda o: o.z).kind
        return "前方 " + ("跳跃" if kind in ("wall", "gap") else "下蹲")

    def burned_calories(self):
        """按每个动作 0.2 千卡估算本轮消耗。"""
        return sum(self.action_counts.values()) * self.cfg.calories_per_action

    def exercise_summary(self):
        """返回 (显示项, 动作总次数, 千卡)，供结算页展示。"""
        counts = self.action_counts
        items = (("起跳", str(counts["起跳"])), ("下蹲", str(counts["下蹲"])),
                 ("张臂", str(counts["张臂"])), ("举手", str(counts["举手"])),
                 ("热量", f"{self.burned_calories():.1f}"))
        return items, sum(counts.values()), self.burned_calories()

    def key(self, key):
        if not self.c or self.mode != "keyboard":
            return
        if key in (pygame.K_LEFT, pygame.K_a):
            self.c.set_lane(max(-1, self.c.peek_state().lane-1))
        elif key in (pygame.K_RIGHT, pygame.K_d):
            self.c.set_lane(min(1, self.c.peek_state().lane+1))
        elif key in (pygame.K_UP, pygame.K_w, pygame.K_SPACE):
            self.c.trigger_jump()
        elif key in (pygame.K_DOWN, pygame.K_s):
            self.held.add(key)
            if not self.c.peek_state().crouch: self.c.toggle_action("crouch")
        elif key == pygame.K_o:
            self.c.toggle_action("arms_open")
        elif key == pygame.K_u:
            self.c.toggle_action("hands_up")

    def update(self, dt):
        dt = max(0., min(dt, .05))
        self.flash = max(0., self.flash-dt)
        self.pixel.update_effects(dt)
        self.notice_t = max(0.,self.notice_t-dt)
        self.jump_preview = max(0.,self.jump_preview-dt)
        if not self.mode or self.over:
            self.audio.set_running(False)
            return
        state = self.c.get_state()
        self.last_state = state
        if state.jump_triggered: self.jump_preview = .5
        if self.calibrating:
            snap = self.c.get_debug_snapshot()
            self.calibrating = not snap.get("calibrated", False)
            diagnostics = snap.get("diagnostics") or {}
            self.calibration_progress = diagnostics.get("calibration_progress",0.)
            self.calibration_hint = diagnostics.get("calibration_hint", "请全身入镜并自然站立")
            self.error = snap.get("error") or ""
            self.audio.set_running(False)
            return
        if state.tracking_confidence < .5:
            self.paused = True
            self.countdown = 3.
            self.audio.set_running(False)
            return
        if self.paused:
            self.paused = False
            self.prev_arms, self.prev_hands = state.arms_open, state.hands_up
            self.prev_crouch = state.crouch
            self.countdown = 3.
        if self.guide or self.manual_pause or self.settings:
            self.audio.set_running(False)
            return
        if self.practice:
            self.player.apply(state,dt)
            for name,done in (("换道",state.lane != 0),("跳跃",state.jump_triggered),
                              ("下蹲",state.crouch),("护盾",state.arms_open),("冲刺",state.hands_up)):
                if done: self.practice_done.add(name)
            self.audio.set_running(False)
            return
        if self.countdown > 0:
            self.countdown = max(0.,self.countdown-dt)
            self.prev_arms,self.prev_hands=state.arms_open,state.hands_up
            self.prev_crouch=state.crouch
            self.audio.set_running(False)
            return
        self.audio.set_running(True)
        self.elapsed += dt
        # 体态结算用的动作次数：只统计上升沿，持续保持不会重复计数。
        if state.crouch and not self.prev_crouch: self.action_counts["下蹲"] += 1
        if state.arms_open and not self.prev_arms: self.action_counts["张臂"] += 1
        if state.hands_up and not self.prev_hands: self.action_counts["举手"] += 1
        self.prev_crouch = state.crouch
        self.energy_clock += dt
        while self.energy_clock >= .8-1e-9:
            self.energy_clock = max(0.,self.energy_clock-.8)
            self.energy = min(self.cfg.energy_max,self.energy+1)
        for active,previous,cost,timer,label in ((state.arms_open,self.prev_arms,20,self.shield_t,"护盾"),(state.hands_up,self.prev_hands,30,self.dash_t,"冲刺")):
            if active and not previous:
                self.notice = "技能生效中，请结束后重新做动作" if timer else ("能量不足，需要 " + str(cost) + " 点" if self.energy<cost else label+"已开启")
                self.notice_t = 2.
        self.shield_t = max(0., self.shield_t-dt)
        self.dash_t = max(0., self.dash_t-dt)
        if state.arms_open and not self.prev_arms and self.shield_t == 0 and self.energy >= 20:
            self.energy -= 20
            self.shield_t = 3.
            self.audio.play("skill")
        if state.hands_up and not self.prev_hands and self.dash_t == 0 and self.energy >= 30:
            self.energy -= 30
            self.dash_t = 2.
            self.audio.play("skill")
        self.prev_arms, self.prev_hands = state.arms_open, state.hands_up
        was_airborne = self.player.jump_time > 0
        if self.player.apply(state, dt):
            self.action_counts["起跳"] += 1
            self.audio.play("jump")
        if was_airborne and self.player.jump_time == 0:
            self.pixel.burst(self.pixel.player_x(self.player), 163, (190,155,110), 8)
        speed = self.speed()
        old_distance = self.distance
        self.distance += speed*dt/10
        self.score += int(self.distance//10)-int(old_distance//10)
        self.pixel.advance(dt, speed, self.player, self.dash_t > 0)
        self.level.update(dt, int(round(self.player.position)),
                          self.obs, self.coins_world)
        for obstacle in self.obs:
            obstacle.z += speed*dt/900
            if obstacle.z >= .94 and not obstacle.checked:
                obstacle.checked = True
                self.passed += 1
                if abs(obstacle.lane-self.player.position) < .46:
                    safe = ((obstacle.kind in ("wall","gap") and self.player.jump >= 16) or
                            (obstacle.kind in ("tunnel","sign") and self.player.crouch_amount >= .65
                             and self.player.jump < 4))
                    if not safe and not (self.shield_t or self.dash_t):
                        self.over = True
                        self.passed -= 1
                        self.death_reason = ("换道尚未完成：请提前横移" if self.player.lane != obstacle.lane else
                            ("跳跃高度不足或起跳时机不合适" if obstacle.kind in ("wall","gap") else "需要提前下蹲，保持到通过障碍"))
                        self.new_best = self.score > self.best
                        self.best = max(self.best,self.score)
                        self.save_preferences()
                        self.flash = .45
                        self.audio.play("hit")
                        self.audio.set_running(False)
                        self.pixel.burst(self.pixel.player_x(self.player), 145, (255,95,65), 30)
                        break
                    self.score += 12
                    if not safe:
                        self.pixel.burst(self.pixel.player_x(self.player), 145, (75,220,255), 15)
        if self.over:
            return
        for coin in self.coins_world[:]:
            coin.z += speed*dt/900
            coin.phase += dt*5
            if coin.z >= .94:
                if abs(coin.lane-self.player.position) < .55:
                    self.coins += 1
                    self.score += 5
                    self.audio.play("coin")
                    self.pixel.burst(self.pixel.player_x(self.player),145,(255,218,70),12)
                self.coins_world.remove(coin)
        self.obs = [o for o in self.obs if o.z < 1.15]

    def draw(self):
        self.pixel.begin()
        self.pixel.draw_world(self.obs,self.coins_world,self.player)
        self.pixel.draw_player(self.player,self.shield_t > 0,self.dash_t > 0,self.flash > 0 and not self.reduced_flash)
        self.pixel.draw_effects()
        self.pixel.present(self.s)
        if self.flash and not self.reduced_flash:
            overlay = pygame.Surface(self.s.get_size(),pygame.SRCALPHA)
            overlay.fill((255,55,40,int(100*self.flash/.45)))
            self.s.blit(overlay,(0,0))
        self.hud.draw(self.s,self)
    def save_preferences(self):
        try:
            self.settings_path.write_text(json.dumps({"difficulty":self.difficulty_key,"reduced_flash":self.reduced_flash,
                "best":self.best,"sound":self.audio.enabled,"music":self.audio.music_volume,"effects":self.audio.effects_volume},ensure_ascii=False),encoding="utf-8")
        except OSError:
            self.notice="设置暂时无法保存"; self.notice_t=2.

    def release_keys(self):
        self.held.clear()
        if self.c and self.mode=="keyboard" and self.c.peek_state().crouch:
            self.c.toggle_action("crouch")

    def action(self,name):
        if name == "mode_select": self.home=False
        elif name in ("keyboard","pose"): self.choose(name)
        elif name=="start" and not self.calibrating:
            if self.over: self.reset_run()
            if self.practice or self.elapsed==0: self.player=Player()
            self.guide=False; self.practice=False; self.manual_pause=False; self.countdown=3.
            self.release_keys()
        elif name=="practice" and not self.calibrating:
            self.reset_run()
            self.guide=False; self.practice=True; self.practice_done.clear()
        elif name=="practice_exit":
            # 离开练习：回到说明页，但不开始正式奔跑。
            self.practice=False; self.guide=True; self.release_keys()
        elif name=="settings": self.settings=True
        elif name=="close_settings": self.settings=False
        elif name=="exit": raise SystemExit
        elif name in ("home","menu"):
            # 回主菜单：停掉控制器并清空本局状态。
            self.home=True; self.mode=None; self.settings=False; self.guide=False
            self.calibrating=False
            if self.c: self.c.stop(); self.c=None
            self.reset_run(False)
        elif name=="pause":
            self.manual_pause=not self.manual_pause
            self.release_keys()
            if not self.manual_pause: self.countdown=3.
        elif name=="guide":
            self.guide=not self.guide; self.settings=False; self.release_keys()
            if not self.guide: self.countdown=3.
        elif name=="restart": self.reset_run(); self.guide=False; self.settings=False
        elif name=="difficulty":
            step = (DIFFICULTY_ORDER.index(self.difficulty_key)+1) % len(DIFFICULTY_ORDER)
            self.set_difficulty(DIFFICULTY_ORDER[step])
            self.notice = "难度：" + self.difficulty.label; self.notice_t = 2.
        elif name=="flash": self.reduced_flash=not self.reduced_flash
        elif name=="sound": self.audio.toggle()
        elif name=="music": self.audio.set_volumes(0. if self.audio.music_volume>=.99 else round(self.audio.music_volume+.2,1),self.audio.effects_volume)
        elif name=="effects": self.audio.set_volumes(self.audio.music_volume,0. if self.audio.effects_volume>=.99 else round(self.audio.effects_volume+.2,1))
        elif name=="fullscreen":
            if self.s.get_flags() & pygame.FULLSCREEN:
                self.s=pygame.display.set_mode((1280,720),pygame.RESIZABLE)
            else: self.s=pygame.display.set_mode((0,0),pygame.FULLSCREEN)
        elif name=="calibrate" and self.mode=="pose":
            self.c.request_calibration(); self.calibrating=True; self.guide=True
        # 只在真正改动偏好时写盘，避免每次按键都覆盖 preferences.json。
        if name in ("difficulty","flash","sound","music","effects"):
            self.save_preferences()

    def run(self):
        try:
            while True:
                dt = min(.05,self.clock.tick(60)/1000)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return
                    if event.type == pygame.WINDOWFOCUSLOST:
                        self.release_keys()
                        if self.mode: self.manual_pause=True
                    if event.type == pygame.VIDEORESIZE and not self.s.get_flags() & pygame.FULLSCREEN:
                        self.s=pygame.display.set_mode((max(960,event.w),max(640,event.h)),pygame.RESIZABLE)
                    if event.type == pygame.KEYUP and event.key in (pygame.K_DOWN,pygame.K_s):
                        self.held.discard(event.key)
                        if not self.held: self.release_keys()
                    if event.type == pygame.KEYDOWN:
                        key=event.key
                        if key==pygame.K_ESCAPE:
                            if self.settings: self.settings=False
                            elif not self.mode: return
                            elif self.over: self.action("menu")
                            else: self.action("pause")
                        elif key==pygame.K_F11: self.action("fullscreen")
                        elif key==pygame.K_m: self.action("sound")
                        elif key==pygame.K_p: self.preview_on=not self.preview_on
                        elif key==pygame.K_g and self.mode: self.action("guide")
                        elif key==pygame.K_c and self.mode=="pose": self.action("calibrate")
                        elif key==pygame.K_RETURN:
                            if self.settings: self.settings=False
                            elif not self.mode: self.home=False
                            elif self.over: self.action("restart")
                            elif self.manual_pause: self.action("pause")
                            elif self.guide or self.practice: self.action("start")
                        elif not self.mode and key in (pygame.K_k,pygame.K_c): self.home=False; self.choose("keyboard" if key==pygame.K_k else "pose")
                        elif not self.settings and not self.manual_pause and not self.over and not self.calibrating: self.key(key)
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button==1:
                        for name,rect in self.hud.buttons.items():
                            if rect.collidepoint(event.pos): self.action(name); break
                self.update(dt)
                self.draw()
                pygame.display.flip()
        finally:
            self.audio.close()
            try:
                if self.c:
                    self.c.stop()
            finally:
                pygame.quit()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fake",action="store_true")
    parser.add_argument("--density",type=float,default=.58)
    parser.add_argument("--difficulty",choices=list(DIFFICULTY_ORDER),default=None)
    args = parser.parse_args()
    game = ParkourGame(GameConfig(density=max(.35,min(1,args.density))))
    if args.difficulty:
        game.set_difficulty(args.difficulty)
    if args.fake:
        game.choose("keyboard")
    game.run()

if __name__ == "__main__":
    main()


