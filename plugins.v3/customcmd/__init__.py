"""MoviePilot V3 自用命令插件。"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from app.plugins import _PluginBase
from app.schemas.types import EventType, MessageType
from app.sdk.events import Event, eventmanager
from app.sdk.logging import logger


def _as_bool(value: Any, default: bool = False) -> bool:
    """把配置中的布尔值规范化，兼容旧版本写入的字符串值。"""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_text(value: Any) -> str:
    """把配置值转换为去除首尾空白的文本。"""
    return "" if value is None else str(value).strip()


class CustomCmd(_PluginBase):
    """提供自用的远程命令入口。"""

    plugin_name = "自用命令行"
    plugin_desc = "自用的命令行工具"
    plugin_icon = "https://raw.githubusercontent.com/xushier/HD-Icons/refs/heads/main/border-radius/Cloudcmd_A.png"
    plugin_version = "3.0.0"
    plugin_author = "happyhaha"
    author_url = "https://github.com/happyhaha1"
    plugin_config_prefix = "customcmd_"
    plugin_order = 4
    auth_level = 1

    _enabled = False
    _onlyonce = False
    _ikuai_url = ""
    _ikuai_username = ""
    _ikuai_password = ""

    def init_plugin(self, config: dict | None = None) -> None:
        """读取配置；重复初始化时始终以最新配置重建插件状态。"""
        config = config or {}
        self._enabled = _as_bool(config.get("enabled"))
        self._onlyonce = _as_bool(config.get("onlyonce"))
        # url/username/password 是早期表单使用的字段，保留读取兼容。
        self._ikuai_url = _as_text(
            config.get("ikuai_url") or config.get("url")
        )
        self._ikuai_username = _as_text(
            config.get("ikuai_username") or config.get("username")
        )
        self._ikuai_password = _as_text(
            config.get("ikuai_password") or config.get("password")
        )

    def get_api(self) -> List[Dict[str, Any]]:
        """当前插件不注册后端 API。"""
        return []

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """注册 ikuai 限速切换远程命令。"""
        return [
            {
                "cmd": "/ikuai_toggle_mac_limit",
                "event": EventType.PluginAction,
                "desc": "ikuai限速",
                "category": "插件命令",
                "data": {"action": "ikuai_toggle_mac_limit"},
            }
        ]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """返回 V3 Vuetify 配置页面及其默认模型。"""
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "enabled",
                                            "label": "启用插件",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "onlyonce",
                                            "label": "立即运行一次",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "ikuai_url",
                                            "label": "ikuai 的 URL",
                                            "placeholder": "http://192.168.1.1",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "ikuai_username",
                                            "label": "ikuai 的用户名",
                                            "placeholder": "admin",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "ikuai_password",
                                            "label": "ikuai 的密码",
                                            "placeholder": "admin",
                                            "type": "password",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                ],
            }
        ], {
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "ikuai_url": self._ikuai_url,
            "ikuai_username": self._ikuai_username,
            "ikuai_password": self._ikuai_password,
        }

    @eventmanager.register(EventType.PluginAction)
    def handle_command(self, event: Event | None = None) -> None:
        """处理 ikuai 限速切换命令。"""
        if not event:
            return

        event_data = event.event_data or {}
        if event_data.get("action") != "ikuai_toggle_mac_limit":
            return
        if not self._enabled:
            logger.info("自用命令行插件未启用，忽略 ikuai 命令")
            return

        # TODO: 接入 ikuai API，实现 MAC 限速切换。
        self.post_message(
            mtype=MessageType.Plugin,
            title="收到 ikuai_toggle_mac_limit 命令",
        )

    def get_page(self) -> List[dict]:
        """当前插件没有额外详情页。"""
        return []

    def get_state(self) -> bool:
        """返回插件启用状态。"""
        return self._enabled

    def stop_service(self) -> None:
        """插件没有自建后台任务，停止时清理运行状态。"""
        self._enabled = False

    def __update_config(self) -> None:
        """持久化当前插件配置，供后续命令实现复用。"""
        self.update_config(
            {
                "enabled": self._enabled,
                "onlyonce": self._onlyonce,
                "ikuai_url": self._ikuai_url,
                "ikuai_username": self._ikuai_username,
                "ikuai_password": self._ikuai_password,
            }
        )
