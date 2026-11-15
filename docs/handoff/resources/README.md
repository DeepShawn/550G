# 资源状态

本目录 JSON 是供 Claude 实现时参考的规格/示例，**当前 main.py 不读取这些 JSON**，不能直接替换源码运行。

- `asset_inventory.json`：真实存在与待制作资源分列；正式路径是目标路径，不表示文件已存在。
- `animation_spec.json`：动作、时序、优先级和缺帧策略建议。
- `dialogues.example.json`：原创补充对白示例；原始对白仍在 source_original/main.py。
- `参考图说明.md`：用户参考图的可见视觉描述与原始链接；图片本体未包含。

原有图像保存在 source_original/assets，不重复复制，避免误以为已有一套新画稿。
