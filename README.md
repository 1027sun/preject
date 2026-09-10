# preject

## MotionQuest 摄像头动作控制模块

将单人摄像头画面转换为游戏可直接读取的六字段 `ControlState`：左右移道、跳跃、下蹲、张臂、举手与追踪可信度。摄像头采集和姿态推理独立运行，Python 游戏循环只需调用 `get_state()`。

- 双击 `start_camera.bat`：打开中文摄像头测试窗口，自动进行站立校准。
- 双击 `start_fake.bat`：用键盘测试接口，不使用摄像头。
- 游戏右上角实时预览：通过独立的 `get_preview_frame()` 获取 RGB 小图。

安装、45 秒动作测试、接口说明和游戏接入代码见 [README_CAMERA.md](README_CAMERA.md)。

当前按 Python 游戏接入，公开控制接口保持六个字段。

## preject_python_class这个文件夹中
有完整的项目，包括视觉识别与游戏逻辑及界面；\
可以直接运行game_ui_acheive下的game.py\
有键盘模式与体态模式两个选择\
下面是一些游戏画面与视频：\

<img width="946" height="536" alt="屏幕截图 2026-09-10 174245" src="https://github.com/user-attachments/assets/c587e9b0-a804-4750-9734-b4438761ffd6" />
<img width="949" height="533" alt="屏幕截图 2026-09-10 174309" src="https://github.com/user-attachments/assets/5bd621da-03e6-40d1-a187-94749fe4e437" />
<img width="953" height="532" alt="屏幕截图 2026-09-10 174251" src="https://github.com/user-attachments/assets/e818bedb-2fdc-43b4-abd2-f23e98bea000" />
<img width="953" height="535" alt="屏幕截图 2026-09-10 174331" src="https://github.com/user-attachments/assets/dfdbe14a-35cb-485d-83f5-3a9674716f58" />
<img width="953" height="535" alt="屏幕录制 2026-09-10 164042" src="https://github.com/user-attachments/assets/a7dca967-dab1-41c0-8210-641cf34ce593" />\
之后可能会不断完善






