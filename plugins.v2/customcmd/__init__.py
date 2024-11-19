from typing import List, Tuple, Dict, Any

from fastapi import Response

import requests
import base64
from app import schemas
from app.core.config import settings
from app.plugins import _PluginBase
from app.log import logger
from app.schemas import NotificationType
from app.core.event import EventManager, eventmanager, Event

from pyikuai import IKuaiClient

from app.schemas.types import EventType


class CustomCmd(_PluginBase):
    # 插件名称
    plugin_name = "自用命令行"
    # 插件描述
    plugin_desc = "自用的命令行工具"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/xushier/HD-Icons/refs/heads/main/border-radius/Cloudcmd_A.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "happyhaha"
    # 作者主页
    author_url = "https://github.com/happyhaha1"
    # 插件配置项ID前缀
    plugin_config_prefix = "customcmd_"
    # 加载顺序
    plugin_order = 4
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _enabled = False
    _onlyonce = False
    _ikuai_url = None
    _ikuai_username = None
    _ikuai_password = None

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled")
            self._onlyonce = config.get("onlyonce")
            self._ikuai_url = config.get("ikuai_url")
            self._ikuai_username = config.get("ikuai_username")
            self._ikuai_password = config.get("ikuai_password")

    def get_api(self) -> List[Dict[str, Any]]:
        """
        获取插件API
        [{
            "path": "/xx",
            "endpoint": self.xxx,
            "methods": ["GET", "POST"],
            "summary": "API说明"
        }]
        """
        pass

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        return [{
            "cmd": "/ikuai_toggle_mac_limit",
            "event": EventType.PluginAction,
            "desc": "ikuai限速",
            "data": {
                "action": "ikuai_toggle_mac_limit"
            }
        }]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'url',
                                            'label': 'ikuai 的 url',
                                            'placeholder': 'http://192.168.1.1'
                                        }
                                    }
                                ]
                            },

                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'username',
                                            'label': ' ikuai 的用户名',
                                            'placeholder': 'admin'
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'password',
                                            'label': ' ikuai 的密码',
                                            'placeholder': 'admin'
                                        }
                                    }
                                ]
                            },
                        ]
                    }
                ],
            }
        ], {
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            'url': self._ikuai_url,
            'username': self._ikuai_username,
            'password': self._ikuai_password,
        }

    @eventmanager.register(EventType.PluginAction)
    def handle_command(self, event: Event = None):
        if event:
            event_data = event.event_data
            if not event_data or event_data.get("action") != "ikuai_toggle_mac_limit":
                return

        # TODO: 实现ikuai的命令
        # event_data.get('')
        self.post_message(mtype=NotificationType.Plugin, title=f" 收到 ikuai_toggle_mac_limit 命令",)

    def get_page(self) -> List[dict]:
        pass

    def get_state(self) -> bool:
        return self._enabled

    def stop_service(self):
        pass

    def __update_config(self):
        """更新设置"""
        self.update_config(
            {
                "enabled": self._enabled,
                "onlyonce": self._onlyonce,
                "ikuai_url": self._ikuai_url,
                "ikuai_username": self._ikuai_username,
                "ikuai_password": self._ikuai_password,
            }
        )
