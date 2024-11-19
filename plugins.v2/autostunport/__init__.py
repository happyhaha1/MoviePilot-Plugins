from typing import List, Tuple, Dict, Any

from fastapi import Response

import requests
import base64
from app import schemas
from app.core.config import settings
from app.plugins import _PluginBase
from app.log import logger
from app.schemas import NotificationType


class AutoStunPort(_PluginBase):
    # 插件名称
    plugin_name = "自动Stun端口"
    # 插件描述
    plugin_desc = "使用lucky进行stun 端口映射，返回最新的 stun 端口"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/happyhaha1/MoviePilot-Plugins/refs/heads/main/icons/lucky.png"
    # 插件版本
    plugin_version = "1.2"
    # 插件作者
    plugin_author = "happyhaha"
    # 作者主页
    author_url = "https://github.com/happyhaha1"
    # 插件配置项ID前缀
    plugin_config_prefix = "autostun_"
    # 加载顺序
    plugin_order = 4
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    _enabled = False
    _ip = None
    _port = None
    _method = None
    _password = None
    _sub_store_url = None

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled")
            self._ip = config.get('ip')
            self._port = config.get('port')
            self._method = config.get('method')
            self._password = config.get('password')
            self._sub_store_url = config.get('sub_store_url')

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
        return [{
            "path": "/change_ip_port",
            "endpoint": self.change_ip_port,
            "methods": ["GET"],
            "summary": "更新 ip 以及端口",
        },
            {
                "path": "/get_ip_port",
                "endpoint": self.get_ip_port,
                "methods": ["GET"],
                "summary": "获取 ip 以及端口",
            }]

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'ip',
                                            'label': 'IP 地址',
                                            'placeholder': '0.0.0.0/24'
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
                                            'model': 'port',
                                            'label': ' 端口',
                                            'placeholder': '0-65535'
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
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'method',
                                            'label': '加密方式',
                                            'items': [
                                                {'title': 'aes-256-gcm', 'value': 'aes-256-gcm'},
                                                {'title': 'aes-128-gcm', 'value': 'aes-128-gcm'},
                                                {'title': 'aes-192-gcm', 'value': 'aes-192-gcm'},
                                            ]
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
                                            'model': 'password',
                                            'label': '密码',
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
                                            'model': 'sub_store_url',
                                            'label': '订阅通知地址',
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ],
            }
        ], {
            "enabled": self._enabled,
            'ip': self._ip,
            '_port': self._port,
            'method': self._method,
            'password': self._password,
            'sub_store_url': self._sub_store_url
        }

    def change_ip_port(self, apikey: str, ip: str, port: str):
        if apikey != settings.API_TOKEN:
            return schemas.Response(success=False, message="API密钥错误")
        if not self._enabled:
            return schemas.Response(success=False, message="服务未启用")
        self._ip = ip
        self._port = port

        self._update_config()
        self.post_message(mtype=NotificationType.Plugin, title=f"【自动更新STUN端口】", text=f"STUN 端口变更为{self._ip}:{self._port}")
        logger.info(f"Stun服务已更新为 {self._ip}:{self._port}")
        # 发送 http 请求
        if self._sub_store_url:
            try:
                response = requests.get(self._sub_store_url)
                if response.status_code == 200:
                    logger.info(f"请求{self._sub_store_url}成功")
                else:
                    logger.error(f"请求{self._sub_store_url}失败，状态码：{response.text}")
            except requests.RequestException as e:
                # print("请求异常：", e)
                logger.error(f"请求SubStore异常：{e}")
        else:
            logger.info('未设置订阅通知地址')
        return schemas.Response(success=True, message="STUN 端口更新成功")

    def _update_config(self):
        config = {
            "enabled": self._enabled,
            "ip": self._ip,
            "port": self._port,
            "method": self._method,
            "password": self._password,
            "sub_store_url": self._sub_store_url
        }
        self.update_config(config=config)

    def get_ip_port(self, apikey: str):
        if apikey != settings.API_TOKEN:
            return schemas.Response(success=False, message="API密钥错误")
        if not self._enabled:
            return schemas.Response(success=False, message="服务未启用")
        url = f"{self._method}:{self._password}@{self._ip}:{self._port}"
        # base64编码
        url_base64 = base64.b64encode(url.encode('utf-8')).decode('utf-8')
        res = base64.b64encode(f"ss://{url_base64}#Stun回家".encode('utf-8')).decode('utf-8')
        return Response(content=res, media_type="text/plain")

    def get_page(self) -> List[dict]:
        pass

    def get_state(self) -> bool:
        return self._enabled

    def stop_service(self):
        pass
