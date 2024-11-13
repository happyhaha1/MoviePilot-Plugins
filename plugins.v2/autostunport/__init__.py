import datetime
import re
import threading
import traceback
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver

from app import schemas
from app.core.config import settings
from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType
from app.schemas.types import EventType
from app.utils.system import SystemUtils


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
    _ip = None
    _port = None
    _method = None
    _password = None

    def init_plugin(self, config: dict = None):
        if config:
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
