# preject

## MotionQuest 摄像头动作控制模块

将单人摄像头画面转换为游戏可直接读取的六字段 `ControlState`：左右移道、跳跃、下蹲、张臂、举手与追踪可信度。摄像头采集和姿态推理独立运行，Python 游戏循环只需调用 `get_state()`。

- 双击 `start_camera.bat`：打开中文摄像头测试窗口，自动进行站立校准。
- 双击 `start_fake.bat`：用键盘测试接口，不使用摄像头。
- 游戏右上角实时预览：通过独立的 `get_preview_frame()` 获取 RGB 小图。

安装、45 秒动作测试、接口说明和游戏接入代码见 [README_CAMERA.md](README_CAMERA.md)。

当前按 Python 游戏接入，公开控制接口保持六个字段。

## preject_python_class
有完整的项目，包括视觉识别与游戏逻辑及界面；
-可以直接运行game_ui_acheive下的game.py
有键盘模式与体态模式两个选择

