"""Pixel Runner 自测：玩法规则、关卡波次、难度、界面状态与资源清理。"""
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pygame

from parkour_game import ParkourGame
from game_config import DIFFICULTY_ORDER, GameConfig, difficulty
from hud import HUD, TITLE_TEXT
from level import (CROUCH, CROUCH_KINDS, JUMP, JUMP_KINDS, PATTERNS, Event,
                   LevelSpawner, build_wave, conflicts)
from entities import Obstacle, Coin
from camera_preview import CameraPreview


class _Frame:
    """Stand-in for the RGB numpy array returned by the controller."""

    def __init__(self, height=180, width=320, value=40):
        self.shape = (height, width, 3)
        self._data = bytes([value]) * (height * width * 3)

    def tobytes(self):
        return self._data


class _PreviewStub:
    def __init__(self, annotated=True, framed=True):
        self.annotated = annotated
        self.framed = framed

    def get_annotated_preview(self, width=320):
        return _Frame(width=width) if (self.annotated and self.framed) else None

    def get_preview_frame(self, width=320):
        return _Frame(width=width, value=99) if self.framed else None


class _LegacyPreviewStub:
    """An older vision module without the annotated preview."""

    def get_preview_frame(self, width=320):
        return _Frame(width=width, value=99)


class GameTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._extra = []
        self.g = self.make_game(spawn=False)

    def make_game(self, **kwargs):
        game = ParkourGame(GameConfig(**kwargs))
        game.settings_path = Path(self.tmp.name) / 'preferences.json'
        game.choose('keyboard')
        game.guide = False
        game.countdown = 0.0
        self._extra.append(game)
        return game

    def tearDown(self):
        for game in self._extra:
            if game.c:
                game.c.stop()
            game.audio.close()
        pygame.quit()
        self.tmp.cleanup()

    def test_tracking_recovers_without_advancing_world(self):
        from camera_control.control_state import ControlState
        with patch.object(self.g.c, 'get_state', return_value=ControlState()):
            self.g.update(.02)
            self.assertTrue(self.g.paused)
            self.assertEqual(self.g.elapsed, 0)
        self.g.update(.02)
        self.assertFalse(self.g.paused)
        self.assertEqual(self.g.elapsed, 0)
        for _ in range(152):
            self.g.update(.02)
        self.assertGreater(self.g.elapsed, 0)

    def test_held_shield_only_charged_once_and_does_not_attract_coin(self):
        self.g.c.toggle_action('arms_open')
        self.g.coins_world = [Coin(1, .6, 0)]
        for _ in range(10):
            self.g.update(.02)
        self.assertAlmostEqual(self.g.energy, 45)
        self.assertGreater(self.g.shield_t, 2)
        self.assertEqual(self.g.coins_world[0].lane, 1)
        self.g.coins_world[0].z = .94
        self.g.update(.02)
        self.assertEqual(self.g.coins, 0)

    def test_dash_speeds_up_and_protects(self):
        base = self.g.speed()
        self.g.c.toggle_action('hands_up')
        self.g.obs = [Obstacle(0, 'wall', .94)]
        self.g.update(.02)
        self.assertFalse(self.g.over)
        self.assertGreater(self.g.speed(), base * 1.6)

    def test_jump_curve_lane_transition_and_crouch(self):
        self.g.c.trigger_jump()
        self.g.c.set_lane(1)
        self.g.update(.02)
        low = self.g.player.jump
        self.assertTrue(0 < self.g.player.position < 1)
        for _ in range(19):
            self.g.update(.02)
        self.assertGreater(self.g.player.jump, low)
        self.assertAlmostEqual(self.g.player.jump, 42)
        for _ in range(21):
            self.g.update(.02)
        self.assertEqual(self.g.player.jump, 0)
        self.g.c.toggle_action('crouch')
        for _ in range(10):
            self.g.update(.02)
        self.assertGreater(self.g.player.crouch_amount, .9)

    def test_collision_flash_decays_after_game_over(self):
        self.g.obs = [Obstacle(0, 'wall', .94)]
        self.g.update(.02)
        self.assertTrue(self.g.over)
        self.assertGreater(self.g.flash, 0)
        for _ in range(30):
            self.g.update(.02)
        self.assertEqual(self.g.flash, 0)

    def test_restart_resets_all_run_state_and_controller(self):
        self.g.c.set_lane(1)
        self.g.c.toggle_action('crouch')
        self.g.c.toggle_action('arms_open')
        self.g.update(.02)
        self.g.coins = 8
        self.g.coins_world = [Coin(1, .8, 0)]
        self.g.over = True
        self.g.reset_run()
        self.assertEqual((self.g.coins, self.g.score, self.g.energy), (0, 0, 65))
        self.assertEqual(self.g.coins_world, [])
        self.assertEqual(self.g.pixel.particles, [])
        self.assertFalse(self.g.c.get_state().crouch)
        self.assertEqual(self.g.player.position, 0)
        self.assertFalse(self.g.new_best)

    def test_render_audio_and_menu(self):
        self.g.obs = [Obstacle(l, k, .45 + i * .12)
                      for i, (l, k) in enumerate([(-1, 'wall'), (0, 'gap'),
                                                  (1, 'tunnel'), (-1, 'sign')])]
        self.g.coins_world = [Coin(1, .88, 0)]
        self.g.draw()
        self.assertTrue(self.g.audio.sounds['coin'].get_length() > 0)
        self.assertTrue(self.g.audio.music.get_length() > 2)
        self.g.home = True
        self.g.mode = None
        self.g.draw()
        self.assertTrue({'mode_select', 'settings', 'exit'} <= set(self.g.hud.buttons))
        if os.environ.get('RUNNER_PREVIEW'):
            pygame.image.save(self.g.s, os.environ['RUNNER_PREVIEW'])

    def test_obstacle_rules_and_actual_lane_position(self):
        for kind in ('wall', 'gap', 'tunnel', 'sign'):
            self.g.reset_run()
            self.g.countdown = 0
            if kind in ('wall', 'gap'):
                self.g.c.trigger_jump()
            else:
                self.g.c.toggle_action('crouch')
            for _ in range(15):
                self.g.update(.02)
            self.g.obs = [Obstacle(0, kind, .94)]
            self.g.update(.02)
            self.assertFalse(self.g.over, kind)
        self.g.reset_run()
        self.g.countdown = 0
        self.g.c.set_lane(1)
        self.g.obs = [Obstacle(0, 'wall', .94)]
        self.g.update(.02)
        self.assertTrue(self.g.over)  # 只换目标车道不能让碰撞体瞬移。

    def test_road_freezes_and_keyboard_event_loop_cleans_up(self):
        self.g.update(.02)
        distance = self.g.pixel.distance
        self.g.guide = True
        self.g.update(.02)
        self.g.draw()
        self.assertEqual(distance, self.g.pixel.distance)
        events = [pygame.event.Event(pygame.KEYDOWN, key=pygame.K_s),
                  pygame.event.Event(pygame.QUIT)]
        with patch('pygame.event.get', return_value=events):
            self.g.run()
        self.assertFalse(self.g.player.crouch)
        self.assertFalse(self.g.c.get_debug_snapshot()['calibrated'])


    def test_action_counters_count_rising_edges_only(self):
        self.g.update(.02)
        self.assertEqual(self.g.action_counts,
                         {"起跳": 0, "下蹲": 0, "张臂": 0, "举手": 0})
        self.g.c.trigger_jump()
        self.g.update(.02)
        self.assertEqual(self.g.action_counts["起跳"], 1)
        for _ in range(10):
            self.g.update(.02)
        self.assertEqual(self.g.action_counts["起跳"], 1)
        self.g.c.toggle_action("crouch")
        for _ in range(10):
            self.g.update(.02)
        self.assertEqual(self.g.action_counts["下蹲"], 1)
        self.g.c.toggle_action("arms_open")
        self.g.update(.02)
        self.g.c.toggle_action("hands_up")
        self.g.update(.02)
        self.assertEqual((self.g.action_counts["张臂"], self.g.action_counts["举手"]),
                         (1, 1))
        for _ in range(10):
            self.g.update(.02)
        self.assertEqual((self.g.action_counts["张臂"], self.g.action_counts["举手"]),
                         (1, 1))
        self.g.c.toggle_action("crouch")     # 站起
        self.g.update(.02)
        self.g.c.toggle_action("crouch")     # 再蹲一次
        self.g.update(.02)
        self.assertEqual(self.g.action_counts["下蹲"], 2)

    def test_countdown_and_guide_do_not_count_actions(self):
        self.g.guide = True
        self.g.c.trigger_jump()
        self.g.update(.02)
        self.assertEqual(self.g.action_counts["起跳"], 0)
        self.g.guide = False
        self.g.countdown = 2.0
        self.g.c.trigger_jump()
        self.g.update(.02)
        self.assertEqual(self.g.action_counts["起跳"], 0)
        self.g.countdown = 0.0
        self.g.c.trigger_jump()
        self.g.update(.02)
        self.assertEqual(self.g.action_counts["起跳"], 1)

    def test_exercise_summary_reports_counts_and_calories(self):
        self.g.action_counts.update({"起跳": 4, "下蹲": 3, "张臂": 2, "举手": 1})
        items, total, kcal = self.g.exercise_summary()
        self.assertEqual([label for label, _ in items],
                         ["起跳", "下蹲", "张臂", "举手", "热量"])
        self.assertEqual(dict(items)["起跳"], "4")
        self.assertEqual(total, 10)
        self.assertAlmostEqual(kcal, 2.0)
        self.assertEqual(dict(items)["热量"], "2.0")
        other = self.make_game(spawn=False, calories_per_action=0.5)
        other.action_counts.update({"起跳": 4, "下蹲": 3, "张臂": 2, "举手": 1})
        self.assertAlmostEqual(other.burned_calories(), 5.0)

    def test_result_panel_has_the_exercise_summary_in_pose_mode(self):
        self.g.countdown = 0.0
        self.g.mode = "pose"
        self.g.over = True
        self.g.death_reason = "测试原因"
        self.g.action_counts.update({"起跳": 5, "下蹲": 4, "张臂": 3, "举手": 2})
        self.g.draw()
        self.assertEqual(set(self.g.hud.buttons), {"restart", "menu"})
        self.assertAlmostEqual(self.g.burned_calories(), 2.8)
        self.g.mode = "keyboard"
        self.g.draw()          # 键盘模式同样要能画结算页
        self.assertEqual(set(self.g.hud.buttons), {"restart", "menu"})

    def test_home_screen_uses_the_art_title(self):
        self.assertEqual(TITLE_TEXT, "一起运动吧")
        self.g.home = True
        self.g.mode = None
        self.g.draw()
        self.assertEqual(set(self.g.hud.buttons), {"mode_select", "settings", "exit"})

    def test_restart_clears_the_counters(self):
        self.g.action_counts.update({"起跳": 3, "下蹲": 2})
        self.g.reset_run()
        self.assertEqual(sum(self.g.action_counts.values()), 0)


class LevelTests(unittest.TestCase):
    """波次关卡：结构、可解性与难度曲线。"""

    def test_every_pattern_produces_valid_events(self):
        rng = random.Random(7)
        for name in PATTERNS:
            for _ in range(120):
                wave = build_wave(name, rng, rng.choice((-1, 0, 1)))
                self.assertTrue(wave.events, name)
                self.assertTrue(wave.actions <= {JUMP, CROUCH}, name)
                self.assertTrue(
                    any(event.kind != 'coin' for event in wave.events), name)
                for event in wave.events:
                    self.assertIn(event.lane, (-1, 0, 1), name)
                    if event.kind != 'coin':
                        self.assertIn(event.kind, JUMP_KINDS + CROUCH_KINDS, name)

    def test_wave3_blocks_every_lane_with_one_single_action(self):
        rng = random.Random(3)
        for _ in range(120):
            wave = build_wave('wave3', rng, 0)
            obstacles = [e for e in wave.events if e.kind != 'coin']
            self.assertEqual(sorted(e.lane for e in obstacles), [-1, 0, 1])
            self.assertEqual({e.delay for e in obstacles}, {0.0})
            kinds = {JUMP if e.kind in JUMP_KINDS else CROUCH for e in obstacles}
            self.assertEqual(len(kinds), 1, "三道同封不能要求两种动作")

    def test_gauntlet_repeats_one_action_in_one_lane(self):
        rng = random.Random(5)
        for _ in range(120):
            wave = build_wave('gauntlet', rng, 0)
            obstacles = sorted((e for e in wave.events if e.kind != 'coin'),
                               key=lambda e: e.delay)
            self.assertEqual(len(obstacles), 3)
            self.assertEqual(len({e.lane for e in obstacles}), 1)
            self.assertEqual(len({JUMP if e.kind in JUMP_KINDS else CROUCH
                                  for e in obstacles}), 1)

    def test_combo_switches_action_with_recovery_time(self):
        rng = random.Random(11)
        for _ in range(120):
            wave = build_wave('combo', rng, 0)
            obstacles = sorted((e for e in wave.events if e.kind != 'coin'),
                               key=lambda e: e.delay)
            self.assertEqual(len(obstacles), 2)
            self.assertEqual(obstacles[0].lane, obstacles[1].lane)
            first = JUMP if obstacles[0].kind in JUMP_KINDS else CROUCH
            second = JUMP if obstacles[1].kind in JUMP_KINDS else CROUCH
            self.assertNotEqual(first, second)
            self.assertGreaterEqual(obstacles[1].delay - obstacles[0].delay, 0.9)

    def test_split_asks_for_two_different_actions_and_keeps_a_free_lane(self):
        rng = random.Random(19)
        for _ in range(120):
            wave = build_wave('split', rng, 0)
            obstacles = [e for e in wave.events if e.kind != 'coin']
            self.assertEqual(len(obstacles), 2)
            self.assertEqual(len({e.lane for e in obstacles}), 2)
            self.assertEqual(obstacles[0].delay, obstacles[1].delay)
            kinds = {JUMP if e.kind in JUMP_KINDS else CROUCH for e in obstacles}
            self.assertEqual(kinds, {JUMP, CROUCH})
            blocked = {e.lane for e in obstacles}
            coins = [e for e in wave.events if e.kind == 'coin']
            self.assertTrue(coins)
            self.assertTrue({e.lane for e in coins}.isdisjoint(blocked))

    def test_slalom_walks_three_different_lanes(self):
        rng = random.Random(13)
        for _ in range(120):
            wave = build_wave('slalom', rng, 0)
            obstacles = sorted((e for e in wave.events if e.kind != 'coin'),
                               key=lambda e: e.delay)
            self.assertEqual(len(obstacles), 3)
            self.assertEqual(sorted(e.lane for e in obstacles), [-1, 0, 1])
            deltas = [round(obstacles[i + 1].delay - obstacles[i].delay, 3)
                      for i in range(2)]
            self.assertEqual(len(set(deltas)), 1)
            self.assertGreater(deltas[0], 0.5)

    def test_coin_trails_lead_somewhere_else(self):
        rng = random.Random(17)
        for name in ('single', 'pair', 'corridor'):
            for _ in range(120):
                wave = build_wave(name, rng, 0)
                coins = [e for e in wave.events if e.kind == 'coin']
                if not coins:
                    continue
                blocked = {e.lane for e in wave.events if e.kind != 'coin'}
                self.assertTrue(all(e.delay < 0 for e in coins), name)
                self.assertTrue({e.lane for e in coins} <= set((-1, 0, 1)))
                if name == 'corridor':
                    self.assertTrue({e.lane for e in coins}.isdisjoint(blocked))

    def test_conflicting_actions_keep_a_recovery_gap(self):
        spawner = LevelSpawner(GameConfig(density=1.0), random.Random(2),
                               difficulty('hard'))
        jump_wave = type(build_wave('wave3', random.Random(1), 0))
        with patch('level.build_wave', side_effect=[
                jump_wave('jump', (Event(0.0, 'wall', 0),), frozenset({JUMP}),
                          frozenset({JUMP})),
                jump_wave('crouch', (Event(0.0, 'tunnel', 0),), frozenset({CROUCH}),
                          frozenset({CROUCH}))]):
            spawner._emit(0)
            spawner._emit(0)
        self.assertGreaterEqual(spawner.last_gap, 1.05)
        self.assertTrue(conflicts(frozenset({JUMP}), frozenset({CROUCH})))
        self.assertFalse(conflicts(frozenset({JUMP}), frozenset({JUMP})))

    def test_difficulty_raises_speed_and_wave_rate(self):
        waves = {}
        for key in DIFFICULTY_ORDER:
            spawner = LevelSpawner(GameConfig(), random.Random(23), difficulty(key))
            obstacles, coins = [], []
            elapsed = 0.0
            while elapsed < 120:
                spawner.update(1 / 60, 0, obstacles, coins)
                elapsed += 1 / 60
            waves[key] = spawner.waves
            self.assertTrue(obstacles)
        self.assertLess(waves['easy'], waves['normal'])
        self.assertLess(waves['normal'], waves['hard'])
        self.assertLess(difficulty('easy').speed_scale, difficulty('normal').speed_scale)
        self.assertLess(difficulty('normal').speed_scale, difficulty('hard').speed_scale)

    def test_only_hard_and_normal_use_waves_that_block_every_lane(self):
        for key in ('easy', 'normal'):
            names = {name for name, _ in difficulty(key).patterns}
            self.assertNotIn('wave3', names, key)
        self.assertIn('wave3', {name for name, _ in difficulty('hard').patterns})

    def test_spawner_stops_when_asked(self):
        spawner = LevelSpawner(GameConfig(spawn=False), random.Random(3),
                               difficulty('hard'))
        obstacles, coins = [], []
        for _ in range(600):
            spawner.update(1 / 60, 0, obstacles, coins)
        self.assertEqual((obstacles, coins, spawner.waves), ([], [], 0))


class InteractionTests(GameTests):
    def test_energy_ticks_and_pause(self):
        self.g.energy = 10
        for _ in range(39):
            self.g.update(.02)
        self.assertEqual(self.g.energy, 10)
        self.g.update(.02)
        self.assertEqual(self.g.energy, 11)
        self.g.manual_pause = True
        for _ in range(50):
            self.g.update(.02)
        self.assertEqual(self.g.energy, 11)

    def test_hold_release_and_focus_loss(self):
        self.g.key(pygame.K_s)
        self.g.key(pygame.K_s)
        self.assertTrue(self.g.c.peek_state().crouch)
        self.g.release_keys()
        self.assertFalse(self.g.c.peek_state().crouch)

    def test_practice_preview_and_start_countdown(self):
        self.g.action('practice')
        self.g.key(pygame.K_o)
        self.g.update(.02)
        self.assertIn('护盾', self.g.practice_done)
        self.assertEqual(self.g.energy, 65)
        self.g.draw()
        self.g.action('start')
        self.g.update(.02)
        self.assertGreater(self.g.countdown, 2)
        self.assertEqual(self.g.elapsed, 0)

    def test_panels_and_calibration_progress_even_with_guide(self):
        self.g.mode = 'pose'
        self.g.guide = True
        self.g.calibrating = True
        with patch.object(self.g.c, 'get_debug_snapshot',
                          return_value={'calibrated': False,
                                        'diagnostics': {'calibration_progress': .5,
                                                        'calibration_hint': '保持稳定'}}):
            self.g.update(.02)
            self.assertEqual(self.g.calibration_progress, .5)
            self.g.draw()
        with patch.object(self.g.c, 'get_debug_snapshot',
                          return_value={'calibrated': True}):
            self.g.update(.02)
        self.assertFalse(self.g.calibrating)
        self.assertTrue(self.g.guide)

    def test_difficulty_cycles_and_changes_speed(self):
        speeds = {}
        for key in DIFFICULTY_ORDER:
            self.g.set_difficulty(key)
            speeds[key] = self.g.speed()
        self.assertLess(speeds['easy'], speeds['normal'])
        self.assertLess(speeds['normal'], speeds['hard'])
        self.g.set_difficulty('easy')
        self.g.action('difficulty')
        self.assertEqual(self.g.difficulty_key, 'normal')
        self.g.action('difficulty')
        self.g.action('difficulty')
        self.assertEqual(self.g.difficulty_key, 'easy')
        self.assertIn('difficulty', self.g.settings_path.read_text(encoding='utf-8'))

    def test_level_spawns_waves_into_the_world(self):
        game = self.make_game()
        for _ in range(600):
            game.update(1 / 60)
        self.assertGreaterEqual(game.level.waves, 1)
        self.assertTrue(game.obs or game.coins_world)
        self.assertTrue(all(o.z >= 0 for o in game.obs))


class UiTests(GameTests):
    def test_menu_settings_and_return(self):
        self.g.home = True
        self.g.mode = None
        self.g.draw()
        self.assertEqual(set(self.g.hud.buttons), {'mode_select', 'settings', 'exit'})
        self.g.action('settings')
        self.g.draw()
        self.assertTrue({'difficulty', 'flash', 'sound', 'music', 'effects',
                         'fullscreen', 'close_settings'} <= set(self.g.hud.buttons))
        self.g.action('close_settings')
        self.g.draw()
        self.assertTrue(self.g.home)
        self.assertIn('mode_select', self.g.hud.buttons)

    def test_settings_buttons_change_preferences(self):
        self.g.action('settings')
        flash = self.g.reduced_flash
        self.g.action('flash')
        self.assertNotEqual(self.g.reduced_flash, flash)
        self.assertTrue(self.g.settings_path.is_file())

    def test_pause_overlay_freezes_world_and_opens_menu(self):
        self.g.update(.02)
        distance = self.g.distance
        self.g.action('pause')
        self.g.draw()
        self.assertEqual(set(self.g.hud.buttons), {'pause', 'restart', 'settings', 'menu'})
        for _ in range(10):
            self.g.update(.02)
        self.assertEqual(self.g.distance, distance)
        self.g.action('menu')
        self.g.draw()
        self.assertTrue(self.g.home)
        self.assertIsNone(self.g.mode)
        self.assertIsNone(self.g.c)

    def test_countdown_is_labelled_before_the_run_starts(self):
        self.g.action('start')
        self.g.update(.02)
        self.assertEqual(HUD.countdown_label(self.g), '3')
        self.g.countdown = 1.4
        self.assertEqual(HUD.countdown_label(self.g), '2')
        self.g.countdown = 0
        self.assertEqual(HUD.countdown_label(self.g), '')

    def test_practice_mode_has_entry_feedback_and_exit(self):
        self.g.action('practice')
        self.g.draw()
        self.assertIn('start', self.g.hud.buttons)
        self.assertIn('practice_exit', self.g.hud.buttons)
        self.g.key(pygame.K_o)
        self.g.update(.02)
        self.g.draw()
        self.assertIn('护盾', self.g.practice_done)
        self.g.action('practice_exit')
        self.assertTrue(self.g.guide)
        self.assertFalse(self.g.practice)

    def test_game_over_offers_restart_and_menu(self):
        self.g.over = True
        self.g.death_reason = '测试原因'
        self.g.new_best = True
        self.g.draw()
        self.assertEqual(set(self.g.hud.buttons), {'restart', 'menu'})

    def test_easy_mode_hint_names_the_required_action(self):
        self.g.set_difficulty('easy')
        self.g.obs = [Obstacle(0, 'tunnel', .6)]
        self.assertIn('下蹲', self.g.next_hint())
        self.g.obs = [Obstacle(0, 'wall', .6)]
        self.assertIn('跳跃', self.g.next_hint())
        self.g.obs = [Obstacle(1, 'wall', .6)]
        self.assertEqual(self.g.next_hint(), '')
        self.g.set_difficulty('hard')
        self.g.obs = [Obstacle(0, 'wall', .6)]
        self.assertEqual(self.g.next_hint(), '')

    def test_camera_failure_is_reported_instead_of_silently_ignored(self):
        with patch('parkour_game.create_controller',
                   side_effect=RuntimeError('没有可用摄像头')):
            self.g.action('keyboard')
        self.assertIn('没有可用摄像头', self.g.error)
        self.g.home = False
        self.g.mode = None
        self.g.draw()
        self.assertTrue({'keyboard', 'pose', 'menu'} <= set(self.g.hud.buttons))

    def test_settings_overlay_freezes_the_world(self):
        self.g.update(.02)
        distance = self.g.distance
        self.g.action('settings')
        for _ in range(20):
            self.g.update(.02)
        self.assertEqual(self.g.distance, distance)


class PreviewTests(unittest.TestCase):
    """体态预览：骨架由视觉模块绘制，游戏端只做转换。"""

    def setUp(self):
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        pygame.init()

    def tearDown(self):
        pygame.quit()

    def test_annotated_frame_is_used_when_available(self):
        preview = CameraPreview(width=320)
        surface = preview.surface(_PreviewStub())
        self.assertEqual(surface.get_size(), (320, 180))
        self.assertTrue(preview.annotated)
        self.assertEqual(preview.error, '')

    def test_older_vision_module_falls_back_to_the_plain_frame(self):
        preview = CameraPreview(width=320)
        surface = preview.surface(_LegacyPreviewStub())
        self.assertEqual(surface.get_size(), (320, 180))
        self.assertFalse(preview.annotated)

    def test_no_frame_or_no_controller_returns_none(self):
        preview = CameraPreview(width=320)
        self.assertIsNone(preview.surface(None))
        self.assertIsNone(preview.surface(_PreviewStub(framed=False)))

    def test_controller_errors_are_surfaced(self):
        class Broken:
            def get_annotated_preview(self, width=320):
                raise RuntimeError('camera gone')

            def get_preview_frame(self, width=320):
                raise RuntimeError('camera gone')

        preview = CameraPreview(width=320)
        self.assertIsNone(preview.surface(Broken()))
        self.assertIn('camera gone', preview.error)


if __name__ == '__main__':
    unittest.main()
