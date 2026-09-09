# MotionQuest 摄像头控制模块

本模块负责摄像头采集、单人人体姿态、站立校准和动作识别。游戏通过 Python 直接读取 `ControlState`，无需处理 MediaPipe 关键点；游戏自己的碰撞、动画和跳跃物理仍由游戏负责。

## 先运行测试

Windows 已配置环境后，双击项目根目录的 `start_camera.bat`。窗口有摄像头画面、人体骨架、左右车道、动作开关、跳跃累计次数，以及 FPS、追踪可信度和延迟。

1. 关闭占用摄像头的会议、拍照程序，把镜头固定好。
2. 后退至全身入框；肩、髋、膝、双手和双脚均需可见，头顶留一点空间。周围留出左右各一步和跳跃的位置，保持光线均匀。
3. 面向镜头，双手自然下垂，站入中央框并保持约 2 秒。界面会提示校准进度；移动或姿态不合适时会提示重新站稳。
4. 校准完成后跟随提示：向画面左侧移动 → 回中 → 向右移动。画面已镜像，屏幕中的左侧对应 `lane=-1`。
5. 回到中央，按下表测试动作。`C` 重新校准，`Esc` 或 `Q` 退出，也可关闭窗口。

首次试用先保持固定的距离和镜头角度；换人、搬动摄像头或明显改变站立距离后按 `C` 重新校准。真实摄像头模式下，键盘不能伪造动作。

### 45 秒动作测试

以下时间从校准完成后开始。测试时观察界面的六字段状态和跳跃累计次数。

| 时间 | 动作 | 预期结果 |
| --- | --- | --- |
| 0–5 秒 | 中间自然站立 | `lane=0`，四个动作均为 `False`，可信度较高 |
| 5–8 秒 | 向画面左侧横移并站稳 | `lane=-1` |
| 8–11 秒 | 回到中央 | `lane=0` |
| 11–14 秒 | 向画面右侧横移并站稳 | `lane=1` |
| 14–17 秒 | 回到中央 | `lane=0` |
| 17–20 秒 | 下蹲并保持 | `crouch=True` |
| 20–23 秒 | 自然站起 | `crouch=False`，不应因起立增加跳跃次数 |
| 23–26 秒 | 小跳一次，落地站稳 | 跳跃累计只增加 1；`jump_triggered` 仅触发一次 |
| 26–30 秒 | 双臂向两侧水平张开 | `arms_open=True`，`hands_up=False` |
| 30–34 秒 | 双手举起，均高于肩部 | `hands_up=True`，`arms_open=False` |
| 34–45 秒 | 放下手，自然小幅晃动、整理衣服 | 不应频繁误触发跳跃、移道或下蹲 |

之后离开镜头约 1 秒：可信度应下降，持续动作清除且不产生跳跃，保留最后车道；重新入镜后应恢复追踪。可继续站立和移动 2–3 分钟，观察误触发与追踪是否稳定。

若某个动作识别不合适，反馈“哪一步、实际显示状态、可信度、界面中的相关数值”。动作阈值在 `camera_control/config.py` 中统一配置。

### 无摄像头的键盘模拟

双击 `start_fake.bat`，或运行 `python camera_demo.py --fake`。模拟模式提供相同 `ControlState`，适合同学先接通游戏。

| 按键 | 模拟输入 |
| --- | --- |
| `A` / `F` / `D` | 左道 / 中道 / 右道 |
| 空格 | 触发一次跳跃 |
| `S` | 开关下蹲 |
| `O` | 开关水平张臂 |
| `U` | 开关举手 |
| `C` | 重置模拟状态 |
| `Esc` / `Q` | 退出 |

模拟画面只用于解释接口状态；真实人体动作需要用摄像头模式测试。

## 安装和命令行

环境使用 Python 3.12 与 `requirements.txt` 中的依赖。首次使用先双击 `setup_camera.bat`，它会创建 `.venv`、安装依赖，并下载 Pose Landmarker Lite 模型到 `models/pose_landmarker_lite.task`。这一步需要联网，日常识别在本机运行。本机已经配置完成后无需重复安装。

另一台 Windows 电脑需先安装 Python 3.12 或 uv，再运行 `setup_camera.bat`。也可以用下面的手动安装命令：

```powershell
# 在项目根目录打开 PowerShell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\download_model.py
```

已经安装好的本机环境可直接使用两个启动文件，也可手动运行：

```powershell
# 默认摄像头
.\.venv\Scripts\python.exe camera_demo.py

# 切换为编号 1 的摄像头
.\.venv\Scripts\python.exe camera_demo.py --camera 1

# 键盘模拟
.\.venv\Scripts\python.exe camera_demo.py --fake

# 无窗口运行 10 秒，终端输出状态及结束统计
.\.venv\Scripts\python.exe camera_demo.py --headless --duration 10

# 无摄像头、无窗口的接口检查
.\.venv\Scripts\python.exe camera_demo.py --fake --headless --duration 2
```

`--duration` 也可用于有窗口模式。无窗口模式无法接收模拟按键，适合启动与接口检查；使用 `Ctrl+C` 结束未指定时长的运行。

## 游戏接口：六字段 ControlState

```python
from camera_control.control_state import ControlState

# 字段定义固定
ControlState(
    lane=0,
    jump_triggered=False,
    crouch=False,
    arms_open=False,
    hands_up=False,
    tracking_confidence=0.0,
)
```

| 字段 | 类型 | 游戏含义 |
| --- | --- | --- |
| `lane` | `int` | `-1` 左、`0` 中、`1` 右；稳定状态 |
| `jump_triggered` | `bool` | 刚发生一次跳跃；读到 `True` 时触发一次游戏跳跃 |
| `crouch` | `bool` | 当前是否保持下蹲 |
| `arms_open` | `bool` | 当前是否双臂向两侧水平张开 |
| `hands_up` | `bool` | 当前是否双手均举到肩部以上 |
| `tracking_confidence` | `float` | `0.0–1.0`，综合关键关节的可见度 |

`jump_triggered` 是一次性事件，不代表人物持续在空中。每个游戏更新周期读取一次 `get_state()`，当次判断跳跃后立即完成处理；不要缓存一个 `True`，然后在后续渲染帧反复调用 `jump()`。调试窗口有独立读取通道，不会把游戏的跳跃事件提前消费掉。

可信度 `>=0.70` 时正常更新；`0.50–0.70` 时模块冻结车道并禁止新增跳跃；持续低于 `0.50` 约 300 ms 或结果过期时，模块清除持续动作、保留车道。游戏可在 `<0.50` 时暂停控制并提示回到镜头范围，恢复后继续。

### Python 游戏接入

```python
from camera_control.camera_controller import CameraController

controller = CameraController(camera_index=0)
controller.start()
try:
    # 在进入游戏主循环之前校准；不要每一帧调用。
    if not controller.calibrate(timeout=15):
        raise RuntimeError("校准尚未完成，请全身入镜、自然站稳后重试")

    # 以下 game/player 是游戏端已有对象，替换成同学的实际方法。
    while game.running:
        state = controller.get_state()  # 非阻塞，读取最新结果
        if state.tracking_confidence < 0.5:
            player.set_crouch(False)
            game.set_arms_open(False)
            game.set_hands_up(False)
            game.show_tracking_warning()
        else:
            player.set_lane(state.lane)
            if state.jump_triggered:
                player.jump()
            player.set_crouch(state.crouch)
            game.set_arms_open(state.arms_open)
            game.set_hands_up(state.hands_up)
        game.update_and_render()
finally:
    controller.stop()
```

游戏启动界面需要持续渲染时，调用 `request_calibration()` 启动非阻塞校准，并从 `get_debug_snapshot()["calibrated"]` 获取完成状态；不要在主循环中调用阻塞的 `calibrate()`。游戏控制只读取六字段，校准状态属于启动界面的独立诊断信息。

接口准备阶段可将控制器改为 `FakeCameraController`：

```python
from camera_control.fake_controller import FakeCameraController

controller = FakeCameraController()
controller.start()
controller.set_lane(-1)
controller.trigger_jump()
state = controller.get_state()  # lane=-1, jump_triggered=True
assert controller.get_state().jump_triggered is False
controller.toggle_action("crouch")
controller.stop()
```

模拟按键处理位于 `camera_demo.py`；同学可在游戏自己的键盘事件中调用 `set_lane()`、`trigger_jump()`、`toggle_action()`。独立 demo 与游戏应分别启动测试，不能让两个进程同时抢占同一个摄像头。

### 游戏右上角摄像头小窗

`get_preview_frame(width=320)` 返回镜像后的 RGB `numpy.ndarray`，形状为 `(高, 宽, 3)`，保留原始比例；720p 摄像头默认得到 320×180 小图。摄像头未启动、帧过期或发生错误时返回 `None`。该接口独立于 `ControlState`，不会消费跳跃事件。

Pygame 游戏在绘制场景后、刷新屏幕前加入：

```python
frame = controller.get_preview_frame(width=320)
if frame is not None:
    h, w = frame.shape[:2]
    preview = pygame.image.frombuffer(frame.tobytes(), (w, h), "RGB")
    screen.blit(preview, (screen.get_width() - w - 16, 16))
pygame.display.flip()
```

`screen` 与 `pygame` 使用游戏端已有对象。每帧先绘制游戏背景再叠加小窗；`None` 时不绘制，就不会继续显示过期画面。其他 Python 引擎可将同一 RGB 数组交给其纹理接口；Pygame 仅为接入示例，不是摄像头模块依赖。

## 识别与性能说明

- 采集线程读取摄像头最新帧，MediaPipe LIVE_STREAM 异步返回人体姿态；游戏循环不等待模型推理。
- 站立校准建立身体中心、肩宽与身高等个人基准。左右移道采用肩宽归一化、滞回和确认时长，持续动作采用防抖。
- 跳跃结合髋部相对上升高度、上升速度、落地复位与冷却判断；摄像头向上位移识别存在单目局限，需要按 45 秒动作序列进行真人确认。
- UI 中的“推理延迟”是输入帧到姿态结果的时间，“结果年龄”是当前时刻距用于控制的那一帧的时间。它们不包含屏幕显示和游戏渲染的全部延迟。
- 参数集中于 `camera_control/config.py` 的 `Config`；先用 `from camera_control.config import Config` 导入，再用 `CameraController(config=Config(lane_enter_threshold=0.6))` 调整移道距离。修改前记录实际误触发动作和对应指标，避免同时改变多个阈值。

## 常见问题

| 现象 | 处理 |
| --- | --- |
| 无摄像头画面或启动错误 | 看终端错误；关闭其他占用摄像头的软件，允许桌面应用访问摄像头，尝试 `--camera 1` |
| 一直等待校准 | 全身入镜、自然站直、双手放下并保持稳定；根据校准提示后退或移至中央 |
| 向左和向右不容易切换 | 先校准，再实际横移身体，不只是伸手；观察“横向位移（肩宽）” |
| 蹲下无反应 | 让膝盖清晰可见，弯膝下蹲；只弯腰并不等于下蹲 |
| 举手后可信度下降 | 双手可能超出画面；后退或调整摄像头角度后重新校准 |
| FPS 较低或结果年龄高 | 关闭其他高负载应用，观察“姿态 FPS”；是否满足游戏体验以目标电脑实测为准 |
| 游戏看不到跳跃 | 每个游戏更新读取一次状态并当次处理；不要让多个游戏逻辑分别调用同一默认 `get_state()` 来抢同一事件 |

控制器需要在游戏退出时调用 `stop()` 释放摄像头。窗口退出会自动清理资源。
