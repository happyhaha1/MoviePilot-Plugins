from typing import List, Tuple, Dict, Any, Optional


from app import schemas
from app.core.config import settings
from app.plugins import _PluginBase


class AutoStunPort(_PluginBase):
    # 插件名称
    plugin_name = "自动Stun端口"
    # 插件描述
    plugin_desc = "使用lucky进行stun 端口映射，返回最新的 stun 端口"
    # 插件图标
    plugin_icon = "lucky.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "jxxghp"
    # 作者主页
    author_url = "https://github.com/happyhaha1"
    # 插件配置项ID前缀
    plugin_config_prefix = "autostun_"
    # 加载顺序
    plugin_order = 4
    # 可使用的用户级别
    auth_level = 1

    # 私有属性
    # ss://YWVzLTI1Ni1nY206NjM3MDg5MjNAMTEyLjEyLjIwNC43MDoxMDc5NQ==
    _enabled = False
    _ip = None
    _port = None
    _method = None
    _password = None

    def init_plugin(self, config: dict = None):
        if config:
            self._enabled = config.get("enabled")
            self._ip = config.get('ip')
            self._port = config.get('port')
            self._method = config.get('method')
            self._password = config.get('password')

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
        if self._enabled:
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
                "summary": "更新 ip 以及端口",
            }]
        else:
            pass

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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'method',
                                            'label': 'ss的method',
                                            'placeholder': 'aes-256-gcm'
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
                            }
                        ]
                    }
                ],
            }
        ], {
            "enabled": False,
            'ip': '',
            '_port': '',
            'method': '',
            'password': ''
        }

    def change_ip_port(self, apikey: str, ip: str, port: str):
        if apikey != settings.API_TOKEN:
            return schemas.Response(success=False, message="API密钥错误")
        self._ip = ip
        self._port = port
        config = {
            "ip": self._ip,
            "port": self._port,
        }
        self.update_config(config=config)

    def get_ip_port(self, apikey: str):
        if apikey != settings.API_TOKEN:
            return schemas.Response(success=False, message="API密钥错误")
        return schemas.Response(success=True, data={
            "ip": self._ip,
            "port": self._port,
        })

    def get_page(self) -> List[dict]:
        pass

    def get_state(self) -> bool:
        return self._enable

    def stop_service(self):
        pass
