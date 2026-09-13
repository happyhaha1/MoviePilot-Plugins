"""MoviePilot V3 自动 STUN 端口插件。"""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Tuple

import requests
from fastapi import HTTPException, Response

from app import schemas
from app.plugins import _PluginBase
from app.schemas.types import MessageType
from app.sdk.logging import logger


def _as_bool(value: Any, default: bool = False) -> bool:
    """把配置中的布尔值规范化，兼容旧版本写入的字符串值。"""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_text(value: Any, default: str = "") -> str:
    """把配置值转换为去除首尾空白的文本。"""
    if value is None:
        return default
    return str(value).strip()


class AutoStunPort(_PluginBase):
    """使用 lucky STUN 端口映射，并提供 SS 订阅地址。"""

    plugin_name = "自动Stun端口"
    plugin_desc = "使用lucky进行stun 端口映射，返回最新的 stun 端口"
    plugin_icon = "https://raw.githubusercontent.com/happyhaha1/MoviePilot-Plugins/refs/heads/main/icons/lucky.png"
    plugin_version = "3.0.0"
    plugin_author = "happyhaha"
    author_url = "https://github.com/happyhaha1"
    plugin_config_prefix = "autostun_"
    plugin_order = 4
    auth_level = 1

    _enabled = False
    _ip = ""
    _port = ""
    _method = "aes-256-gcm"
    _password = ""
    _sub_store_url = ""

    def init_plugin(self, config: dict | None = None) -> None:
        """读取配置；重复初始化时始终以最新配置重建插件状态。"""
        config = config or {}
        self._enabled = _as_bool(config.get("enabled"))
        self._ip = _as_text(config.get("ip"))
        self._port = _as_text(config.get("port"))
        self._method = _as_text(config.get("method")) or "aes-256-gcm"
        self._password = _as_text(config.get("password"))
        self._sub_store_url = _as_text(config.get("sub_store_url"))

    def get_api(self) -> List[Dict[str, Any]]:
        """注册供外部系统调用的端口更新和订阅地址接口。"""
        return [
            {
                "path": "/change_ip_port",
                "endpoint": self.change_ip_port,
                "methods": ["GET"],
                "auth": "apikey",
                "summary": "更新 IP 以及端口",
                "response_model": schemas.Response[None],
            },
            {
                "path": "/get_ip_port",
                "endpoint": self.get_ip_port,
                "methods": ["GET"],
                "auth": "apikey",
                "summary": "获取 IP 以及端口",
                "response_class": Response,
                "responses": {
                    200: {
                        "description": "Base64 编码的 SS 订阅地址",
                        "content": {
                            "text/plain": {"schema": {"type": "string"}}
                        },
                    },
                    409: {"description": "服务未启用"},
                },
            },
        ]

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """当前插件不注册远程命令。"""
        return []

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
                                        "component": "VTextField",
                                        "props": {
                                            "model": "ip",
                                            "label": "IP 地址",
                                            "placeholder": "0.0.0.0/24",
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
                                            "model": "port",
                                            "label": "端口",
                                            "placeholder": "0-65535",
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
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "method",
                                            "label": "加密方式",
                                            "items": [
                                                {
                                                    "title": "aes-256-gcm",
                                                    "value": "aes-256-gcm",
                                                },
                                                {
                                                    "title": "aes-128-gcm",
                                                    "value": "aes-128-gcm",
                                                },
                                                {
                                                    "title": "aes-192-gcm",
                                                    "value": "aes-192-gcm",
                                                },
                                            ],
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
                                            "model": "password",
                                            "label": "密码",
                                            "type": "password",
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
                                            "model": "sub_store_url",
                                            "label": "订阅通知地址",
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
            "ip": self._ip,
            "port": self._port,
            "method": self._method,
            "password": self._password,
            "sub_store_url": self._sub_store_url,
        }

    def change_ip_port(self, ip: str, port: str) -> schemas.Response[None]:
        """更新映射地址，并通知订阅服务。"""
        if not self._enabled:
            return schemas.Response(success=False, message="服务未启用")

        self._ip = _as_text(ip)
        self._port = _as_text(port)
        self._update_config()
        self.post_message(
            mtype=MessageType.Plugin,
            title="【自动更新STUN端口】",
            text=f"STUN 端口变更为{self._ip}:{self._port}",
        )
        logger.info("Stun服务已更新为 %s:%s", self._ip, self._port)

        if self._sub_store_url:
            try:
                response = requests.get(self._sub_store_url, timeout=10)
                if response.status_code == 200:
                    logger.info("请求%s成功", self._sub_store_url)
                else:
                    logger.error(
                        "请求%s失败，状态码：%s",
                        self._sub_store_url,
                        response.status_code,
                    )
            except requests.RequestException as error:
                logger.error("请求SubStore异常：%s", error)
        else:
            logger.info("未设置订阅通知地址")

        return schemas.Response(success=True, message="STUN 端口更新成功")

    def _update_config(self) -> None:
        """持久化当前插件配置。"""
        self.update_config(
            config={
                "enabled": self._enabled,
                "ip": self._ip,
                "port": self._port,
                "method": self._method,
                "password": self._password,
                "sub_store_url": self._sub_store_url,
            }
        )

    def get_ip_port(self) -> Response:
        """返回 Base64 编码的 SS 订阅地址（原生 text/plain 响应）。"""
        if not self._enabled:
            raise HTTPException(status_code=409, detail="服务未启用")

        url = f"{self._method}:{self._password}@{self._ip}:{self._port}"
        url_base64 = base64.b64encode(url.encode("utf-8")).decode("utf-8")
        subscription = base64.b64encode(
            f"ss://{url_base64}#Stun回家".encode("utf-8")
        ).decode("utf-8")
        return Response(content=subscription, media_type="text/plain")

    def get_page(self) -> List[dict]:
        """当前插件没有额外详情页。"""
        return []

    def get_state(self) -> bool:
        """返回插件启用状态。"""
        return self._enabled

    def stop_service(self) -> None:
        """插件没有自建后台任务，停止时清理运行状态。"""
        self._enabled = False
