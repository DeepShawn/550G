# 550G × 前辈GPT · Windows 双人桌宠

v0.2.0-dev-preview —— 开发预览版（占位素材；Windows 实机验收未完成，见 [docs/已知限制与测试记录.md](docs/已知限制与测试记录.md)）。

两位坐姿 Q 版角色常驻桌面：透明、置顶、各自独立拖动；单击对白并卖萌；随机眨眼、空闲睡觉、单击唤醒；右键与托盘可隐藏/显示/恢复/退出。PySide6 原生窗口，离线运行。

## 目录

```text
main.py                  启动、参数、日志、单实例、冒烟自检
app/
  controller.py          两只角色、托盘/控制窗口、菜单、持久化、多屏校验、退出
  pet_window.py          透明置顶窗口：绘制、浮动、气泡、命中区域、鼠标输入
  state_machine.py       无 UI 状态机（idle/blink/cute/sleep），单调时间
  interaction.py         点击/拖动判定
  geometry.py            多屏坐标约束（支持负坐标）
  settings.py            用户配置（原子写入、损坏回退）
  frames.py              帧加载、缺帧回退、DPR 缓存、alpha 命中区域
  assets.py              资源路径（源码/冻结包）与角色清单
  dialogues.py           离线对白
  single_instance.py     QLockFile + QLocalServer
assets/                  pets.json、dialogues.json、角色帧、托盘图标
tools/                   占位素材生成、素材校验与预览
packaging/windows.spec   PyInstaller onedir
scripts/                 dev-start.ps1、build-windows.ps1
tests/                   pytest（offscreen）
source_original/         原型 v1，保持原样作为基线
docs/handoff/            交接包文档与参考图
```

## 开发

Windows（PowerShell）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev-start.ps1
```

任意平台：

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
QT_QPA_PLATFORM=offscreen python -m pytest -q
python tools/validate_assets.py --sheet preview.png
python main.py                                    # --data-dir DIR / --reset-settings / --smoke-test report.json
```

调试开关：`DESKTOP_PETS_NO_MASK=1` 关闭 alpha 命中遮罩；`DESKTOP_PETS_FORCE_NO_TRAY=1` 模拟托盘不可用。

## Windows 构建

在 Windows 10/11 x64 + Python 3.11 x64：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1          # 预览版
powershell -ExecutionPolicy Bypass -File scripts\build-windows.ps1 -Release # 正式版（拒绝占位素材）
```

产物：`release/550G_GPT_DesktopPets_<版本>_win_x64.zip`、源码 ZIP、`SHA256SUMS.txt`。推送后 GitHub Actions `windows-build` 也会构建并上传同样的 ZIP。构建自检通过不等于实机验收，发布前按 `docs/handoff/05_Windows验收清单.md` 测试。

## 替换正式素材

见 [docs/素材来源.md](docs/素材来源.md)：同名 PNG（768×896 RGBA，脚底锚点 384,848）放入 `assets/pets/<id>/`，通过校验后把 `pets.json` 的 `placeholder` 改为 `false`。
