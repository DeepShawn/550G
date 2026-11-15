# 变更记录

## v0.2.0-dev-preview（2026-11-15）

在原型 v1（`source_original/`，未修改）基础上重构为可测试的模块结构。**开发预览版**：素材为工程占位、Windows 实机验收未完成。

### M1 可靠桌面交互
- 拆分 `app/controller.py`（两只角色、托盘、菜单、退出）与 `app/pet_window.py`（透明窗口、绘制、输入）。
- 修复“按下就说话”：释放时按 `startDragDistance` 阈值区分单击与拖动；拖动不触发对白，只移动当前角色。
- 呼吸浮动改为绘制偏移，不再每 45 ms `move()` 整个窗口；拖动时暂停浮动，睡眠时幅度减小。
- 基于帧 alpha 的命中区域（`setMask`），透明区域不拦截鼠标；区域包含浮动范围、可见气泡与睡眠 Z。
- 角色菜单：说句话、表情/动作、大小、隐藏这只、显示另一只、显示全部、恢复位置、关于、退出。
- 托盘菜单：每只子菜单（显示/隐藏、恢复位置、说话、表情、大小）、显示全部、隐藏全部、恢复主屏位置、空闲自动睡觉、关于、退出；单击/双击托盘显示全部；首次运行提示恢复方法。
- 托盘不可用时显示常驻控制窗口；托盘与控制窗口都没有时禁止隐藏最后一只。
- 位置（角色区域，支持负坐标）与大小持久化到用户目录，原子写入；损坏/版本不符时回退默认值并备份为 `.broken`。
- 启动和显示器拔插/工作区变化时校验位置，主要区域不可见才移回主屏；拖动结束收回所在屏幕。
- 单实例：`QLockFile` + `QLocalServer`，第二次启动会让已有实例“显示全部”。
- 日志写入用户目录（轮转），未处理异常记录并弹窗提示；“关于”使用真实换行并显示版本、配置和日志路径。

### M2 状态与表情
- `app/state_machine.py`：无 UI 的 idle / blink / cute / sleep 状态机，单调时钟，可注入时间测试。
- 随机 3～7 s 眨眼（half→closed→half）；单击 cute 2 s；气泡 4 s；空闲 180 s 睡觉；单击唤醒并说醒来对白。
- 眨眼不打断睡眠/卖萌；手动操作优先；隐藏时停止计时器并暂停状态，显示时平移全部截止时间。
- 缺可选 `blink_half` 时跳过；缺其他帧回退 idle 并记录；缺 `idle` 明确报错退出。
- 对白移入 `assets/dialogues.json`（合并原型对白与交接示例），洗牌轮播不连续重复。

### M3 素材（占位）
- `tools/make_placeholder_art.py` 生成两位角色各 5 帧 768×896 RGBA PNG（idle、blink_half、blink_closed、cute、sleep）及多尺寸托盘 ICO。**仅为工程占位，不是正式高清立绘。**
- `tools/validate_assets.py` 校验尺寸、RGBA、透明角落、边距、各帧轮廓对齐，并输出预览拼图；`--release` 拒绝占位素材。

### M4 构建
- 锁定依赖：`PySide6-Essentials==6.8.3`、`shiboken6==6.8.3`；构建 `pyinstaller==6.20.0`。
- `packaging/windows.spec`（onedir、图标、版本资源、资源打包）、`scripts/build-windows.ps1`（干净环境→测试→素材校验→构建→冻结包自检→ZIP+SHA-256）、`scripts/dev-start.ps1`。
- `--smoke-test` 冒烟自检模式；GitHub Actions `windows-build` 工作流在 windows-latest 上构建并上传产物。

### 偏离交接文档之处
- spec 放在 `packaging/windows.spec`（`build/` 是 PyInstaller 临时目录，会被清理）。
- 托盘单击也显示全部（文档只要求双击）。
