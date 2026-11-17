"""统一版本与应用元数据（关于框、日志、打包脚本都从这里读取）。"""

APP_VERSION = "0.4.0"
APP_STAGE = "dev-preview"  # 正式素材与 Windows 实机验收完成前保持 dev-preview
APP_DISPLAY_NAME = "550G × 前辈GPT 桌宠"
APP_NAME = "DesktopPets550G"  # 用于配置目录、单实例名称、EXE 名
ORG_NAME = "DesktopPets550G"


def version_string() -> str:
    return f"{APP_VERSION}-{APP_STAGE}" if APP_STAGE else APP_VERSION
