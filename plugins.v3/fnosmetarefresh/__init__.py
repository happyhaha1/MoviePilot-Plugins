"""MoviePilot V3 飞牛影视元数据定时刷新插件。"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from apscheduler.triggers.cron import CronTrigger

from app import schemas
from app.plugins import _PluginBase
from app.sdk.events import Event, eventmanager
from app.sdk.logging import logger
from app.sdk.scheduler import add_plugin_once_job
from app.sdk.services import MediaServerHelper
from app.schemas.types import EventType, MessageType

# 飞牛影视媒体服务器类型标识
FNOS_TYPE = "trimemedia"

# 刷新粒度
SCOPE_HISTORY = "history"
SCOPE_LIBRARY = "library"

# 刷新方式：1 仅补充缺失，0 替换全部
REFRESH_MODE_FILL = 1
REFRESH_MODE_REPLACE = 0


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


def _as_int(value: Any, default: int) -> int:
    """把配置值转换为整数，无法解析时返回默认值。"""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _result_ok(result: Any) -> bool:
    """判断飞牛接口返回的业务结果是否成功。"""
    return bool(result is not None and getattr(result, "success", False))


def _result_message(result: Any) -> str:
    """提取飞牛接口返回的业务错误说明。"""
    if result is None:
        return "请求失败"
    msg = getattr(result, "msg", None)
    code = getattr(result, "code", None)
    if msg:
        return f"{msg}（code={code}）"
    return f"code={code}"


class FnosMetaRefresh(_PluginBase):
    """定时刷新飞牛影视媒体库元数据。"""

    plugin_name = "飞牛元数据刷新"
    plugin_desc = "定时刷新飞牛影视媒体库元数据，支持按入库条目或按媒体库刷新。"
    plugin_icon = (
        "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/refresh2.png"
    )
    plugin_version = "3.0.0"
    plugin_author = "happyhaha"
    author_url = "https://github.com/happyhaha1"
    plugin_config_prefix = "fnosmetarefresh_"
    plugin_order = 16
    auth_level = 1

    _enabled: bool = False
    _onlyonce: bool = False
    _cron: str = "0 3 * * *"
    _scope: str = SCOPE_HISTORY
    _mediaserver: str = ""
    _libraries: List[str] = []
    _refresh_mode: int = REFRESH_MODE_FILL
    _days: int = 7
    _interval: int = 3
    _notify: bool = False
    _fallback_library: bool = False

    # 运行期状态（在 init_plugin 中按实例重建，避免分身共享）
    _event: threading.Event = threading.Event()
    _running: bool = False

    def init_plugin(self, config: Optional[Dict[str, Any]] = None) -> None:
        """读取配置；重复初始化时始终以最新配置重建插件状态。"""
        # 先中断上一轮执行，再重建实例级状态
        self._event.set()
        self._event = threading.Event()
        self._running = False
        config = config or {}
        self._enabled = _as_bool(config.get("enabled"))
        self._onlyonce = _as_bool(config.get("onlyonce"))
        self._cron = _as_text(config.get("cron")) or "0 3 * * *"
        self._scope = _as_text(config.get("scope")) or SCOPE_HISTORY
        self._mediaserver = _as_text(config.get("mediaserver"))
        self._libraries = [
            _as_text(item) for item in (config.get("libraries") or []) if _as_text(item)
        ]
        self._refresh_mode = _as_int(config.get("refresh_mode"), REFRESH_MODE_FILL)
        if self._refresh_mode not in (REFRESH_MODE_FILL, REFRESH_MODE_REPLACE):
            self._refresh_mode = REFRESH_MODE_FILL
        self._days = max(1, _as_int(config.get("days"), 7))
        self._interval = max(0, _as_int(config.get("interval"), 3))
        self._notify = _as_bool(config.get("notify"))
        self._fallback_library = _as_bool(config.get("fallback_library"))

        if not (self._enabled or self._onlyonce):
            return

        if self._onlyonce:
            logger.info("飞牛元数据刷新服务启动，立即运行一次")
            scheduled = add_plugin_once_job(
                plugin_id=self.__class__.__name__,
                job_id=f"{self.__class__.__name__}_onlyonce",
                func=self.refresh,
                name="飞牛元数据刷新",
                delay_seconds=3,
            )
            if not scheduled:
                logger.warning("调度器未就绪，立即运行一次改为后台线程执行")
                threading.Timer(3.0, self.refresh).start()
            self._onlyonce = False
            self.__update_config()

    def get_state(self) -> bool:
        """返回插件启用状态。"""
        return self._enabled

    def __update_config(self) -> None:
        """持久化当前插件配置。"""
        self.update_config(
            config={
                "enabled": self._enabled,
                "onlyonce": self._onlyonce,
                "cron": self._cron,
                "scope": self._scope,
                "mediaserver": self._mediaserver,
                "libraries": self._libraries,
                "refresh_mode": self._refresh_mode,
                "days": self._days,
                "interval": self._interval,
                "notify": self._notify,
                "fallback_library": self._fallback_library,
            }
        )

    # ------------------------------------------------------------------
    # 飞牛服务访问
    # ------------------------------------------------------------------

    def __fnos_api(self, reconnect: bool = True) -> Optional[Any]:
        """获取已登录的飞牛影视 API 客户端。"""
        helper = MediaServerHelper()
        configs = helper.get_configs()
        candidates = [
            (name, conf)
            for name, conf in configs.items()
            if getattr(conf, "type", None) == FNOS_TYPE
        ]
        if not candidates:
            logger.error("未配置飞牛影视媒体服务器，请在系统设置中先添加")
            return None
        if self._mediaserver:
            selected = [item for item in candidates if item[0] == self._mediaserver]
            if not selected:
                logger.error(f"未找到名为 {self._mediaserver} 的飞牛影视媒体服务器")
                return None
            candidates = selected

        services = helper.get_services(
            type_filter=FNOS_TYPE, name_filters=[name for name, _ in candidates]
        )
        if not services:
            logger.error("获取飞牛影视服务实例失败，请检查媒体服务器配置")
            return None

        for name, service in services.items():
            instance = getattr(service, "instance", None)
            if instance is None:
                logger.error(f"飞牛影视 {name} 未连接")
                continue
            if reconnect and instance.is_inactive() and not instance.reconnect():
                logger.error(f"飞牛影视 {name} 重新连接失败")
                continue
            api = getattr(instance, "api", None)
            if api is None:
                logger.error(f"飞牛影视 {name} 未取得 API 客户端")
                continue
            return api
        return None

    def __running_ancestors(self, api: Any) -> set[str]:
        """查询正在运行的刷新任务所属条目，用于规避重复任务报错。"""
        try:
            result = api.request("/task/running")
        except Exception as err:  # noqa: BLE001 - 查询失败不应中断刷新
            logger.warning(f"查询飞牛运行任务失败：{err}")
            return set()
        if not _result_ok(result):
            return set()
        running: set[str] = set()
        for task in getattr(result, "data", None) or []:
            if not isinstance(task, dict):
                continue
            if task.get("type") != "TaskRefreshItem":
                continue
            for key in ("ancestor", "guid"):
                value = task.get(key)
                if value:
                    running.add(str(value))
        return running

    def __refresh_item(self, api: Any, guid: str) -> bool:
        """按条目刷新元数据。"""
        result = api.request(
            "/item/refresh",
            method="post",
            data={"item_guid": guid, "refresh_mode": self._refresh_mode},
            suppress_log=True,
        )
        if _result_ok(result):
            return True
        logger.error(f"条目 {guid} 元数据刷新失败：{_result_message(result)}")
        return False

    def __refresh_library(self, api: Any, guid: str) -> bool:
        """按媒体库刷新元数据。"""
        result = api.request(
            "/mdb/refresh",
            method="post",
            data={"mdb_guid": guid, "refresh_mode": self._refresh_mode},
            suppress_log=True,
        )
        if _result_ok(result):
            return True
        logger.error(f"媒体库 {guid} 元数据刷新失败：{_result_message(result)}")
        return False

    # ------------------------------------------------------------------
    # 条目定位
    # ------------------------------------------------------------------

    @staticmethod
    def __item_type_value(item: Any) -> str:
        """读取飞牛条目的类型字符串。"""
        item_type = getattr(item, "type", None)
        return _as_text(getattr(item_type, "value", item_type))

    @staticmethod
    def __item_date(item: Any) -> str:
        """读取飞牛条目的上映或首播日期文本。"""
        return _as_text(
            getattr(item, "release_date", None) or getattr(item, "air_date", None)
        )

    def __find_item(self, api: Any, title: str, year: str, media_type: str) -> Optional[str]:
        """在飞牛中按标题、年份和类型定位条目 guid。

        先按年份严格匹配；严格匹配未命中时退回仅按标题与类型匹配，
        因为飞牛的首播日期与 MoviePilot 记录的年份可能不一致（如综艺首季年份）。
        """
        if not title:
            return None
        expect_type = "Movie" if media_type == "电影" else "TV"
        try:
            items = api.search_list(keywords=title) or []
        except Exception as err:  # noqa: BLE001 - 搜索失败按未命中处理
            logger.warning(f"搜索飞牛条目 {title} 失败：{err}")
            return None

        candidates: List[Any] = []
        for item in items:
            if self.__item_type_value(item) != expect_type:
                continue
            names = [
                _as_text(getattr(item, "title", None)),
                _as_text(getattr(item, "original_title", None)),
            ]
            if title not in names:
                continue
            guid = _as_text(getattr(item, "guid", None))
            if guid:
                candidates.append(item)

        # 第一轮：年份严格匹配
        for item in candidates:
            item_date = self.__item_date(item)
            if year and item_date and item_date[:4] == year:
                return _as_text(getattr(item, "guid", None))
        # 第二轮：忽略年份，仅保留标题与类型匹配
        if candidates:
            guid = _as_text(getattr(candidates[0], "guid", None))
            if guid:
                logger.debug(f"条目 {title} 年份未匹配（MP 年份 {year}），按标题命中 {guid}")
                return guid
        return None

    # ------------------------------------------------------------------
    # 入库条目收集
    # ------------------------------------------------------------------

    def __collect_history_titles(self) -> List[Tuple[str, str, str]]:
        """读取近 N 天整理成功的入库条目，返回去重后的 (标题, 年份, 类型) 列表。"""
        from app.sdk.queries import (
            QueryPageRequest,
            QuerySort,
            QuerySortDirection,
            QuerySortField,
            TransferHistoryFilter,
            list_transfer_history,
        )

        cutoff = datetime.now() - timedelta(days=self._days)
        cutoff_text = cutoff.strftime("%Y-%m-%d %H:%M:%S")
        collected: List[Tuple[str, str, str]] = []
        seen: set[Tuple[str, str, str]] = set()
        page = 1
        page_size = 100
        sort = QuerySort(field=QuerySortField.DATE, direction=QuerySortDirection.DESC)

        while page <= 50:
            result = list_transfer_history(
                filters=TransferHistoryFilter(status=True),
                page=QueryPageRequest(page=page, count=page_size, sort=sort),
            )
            records = list(getattr(result, "items", None) or [])
            if not records:
                break
            stop = False
            for record in records:
                record_date = _as_text(getattr(record, "date", None))
                if record_date and record_date < cutoff_text:
                    stop = True
                    break
                title = _as_text(getattr(record, "title", None))
                if not title:
                    continue
                year = _as_text(getattr(record, "year", None))
                media_type = _as_text(getattr(record, "type", None))
                key = (title, year, media_type)
                if key in seen:
                    continue
                seen.add(key)
                collected.append(key)
            if stop or len(records) < page_size:
                break
            page += 1
        return collected

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """执行一次飞牛影视元数据刷新。"""
        if self._running:
            logger.warning("飞牛元数据刷新正在执行，跳过本次触发")
            return
        self._running = True
        self._event.clear()
        started = datetime.now()
        summary: Dict[str, Any] = {
            "time": started.strftime("%Y-%m-%d %H:%M:%S"),
            "scope": self._scope,
            "refresh_mode": self._refresh_mode,
            "success": [],
            "skipped": [],
            "failed": [],
            "missed": [],
        }
        try:
            api = self.__fnos_api()
            if api is None:
                summary["failed"].append("飞牛影视未连接")
                return
            if self._scope == SCOPE_LIBRARY:
                self.__run_library_scope(api, summary)
            else:
                self.__run_history_scope(api, summary)
        except Exception as err:  # noqa: BLE001 - 保证状态落盘
            logger.exception(f"飞牛元数据刷新异常：{err}")
            summary["failed"].append(f"异常：{err}")
        finally:
            self._running = False
            summary["elapsed"] = int((datetime.now() - started).total_seconds())
            self.save_data("last_run", summary)
            self.__report(summary)

    def __run_library_scope(self, api: Any, summary: Dict[str, Any]) -> None:
        """按媒体库刷新。"""
        # 直接读原始列表，才能拿到 refresh_disabled 标记
        result = api.request("/mdb/list", suppress_log=True)
        if not _result_ok(result):
            summary["failed"].append(f"读取飞牛媒体库列表失败：{_result_message(result)}")
            return
        targets: List[Tuple[str, str]] = []
        for info in getattr(result, "data", None) or []:
            if not isinstance(info, dict):
                continue
            guid = _as_text(info.get("guid"))
            name = _as_text(info.get("name")) or guid
            if not guid:
                continue
            if info.get("refresh_disabled"):
                summary["skipped"].append(f"{name}（已禁用刷新）")
                continue
            if self._libraries and guid not in self._libraries:
                continue
            targets.append((guid, name))
        if not targets:
            summary["failed"].append("没有可刷新的媒体库")
            return

        running = self.__running_ancestors(api)
        for index, (guid, name) in enumerate(targets):
            if self._event.is_set():
                logger.info("飞牛元数据刷新已中断")
                break
            if guid in running:
                logger.info(f"媒体库 {name} 已有刷新任务在运行，跳过")
                summary["skipped"].append(f"{name}（任务运行中）")
                continue
            logger.info(f"刷新媒体库：{name}")
            if self.__refresh_library(api, guid):
                summary["success"].append(name)
            else:
                summary["failed"].append(name)
            if self._interval and index < len(targets) - 1:
                time.sleep(self._interval)

    def __run_history_scope(self, api: Any, summary: Dict[str, Any]) -> None:
        """按近 N 天入库条目刷新。"""
        try:
            titles = self.__collect_history_titles()
        except Exception as err:  # noqa: BLE001 - 历史读取失败时给出明确提示
            logger.error(f"读取整理历史失败：{err}")
            summary["failed"].append(f"读取整理历史失败：{err}")
            return
        if not titles:
            logger.info(f"最近 {self._days} 天没有入库记录")
            summary["skipped"].append(f"最近 {self._days} 天无入库记录")
            return
        logger.info(f"最近 {self._days} 天入库条目 {len(titles)} 个，开始刷新元数据")

        running = self.__running_ancestors(api)
        refreshed: set[str] = set()
        for index, (title, year, media_type) in enumerate(titles):
            if self._event.is_set():
                logger.info("飞牛元数据刷新已中断")
                break
            guid = self.__find_item(api, title, year, media_type)
            if not guid:
                logger.warning(f"飞牛中未找到条目：{title}（{year}）")
                summary["missed"].append(f"{title}（{year}）")
                continue
            if guid in refreshed:
                summary["skipped"].append(f"{title}（已刷新）")
                continue
            if guid in running:
                logger.info(f"条目 {title} 已有刷新任务在运行，跳过")
                summary["skipped"].append(f"{title}（任务运行中）")
                continue
            refreshed.add(guid)
            if self.__refresh_item(api, guid):
                logger.info(f"已通知飞牛刷新元数据：{title}")
                summary["success"].append(f"{title}（{year}）")
            else:
                summary["failed"].append(f"{title}（{year}）")
            if self._interval and index < len(titles) - 1:
                time.sleep(self._interval)

        if self._fallback_library and summary["missed"]:
            logger.info("存在未命中条目，回退刷新全部媒体库元数据")
            fallback: Dict[str, Any] = {
                "success": [],
                "skipped": [],
                "failed": [],
                "missed": [],
            }
            self.__run_library_scope(api, fallback)
            for key in ("success", "skipped", "failed"):
                summary[key].extend(f"整库回退：{item}" for item in fallback[key])

    def __report(self, summary: Dict[str, Any]) -> None:
        """输出运行日志并按需发送通知。"""
        text = (
            f"模式：{'按入库条目' if summary['scope'] == SCOPE_HISTORY else '按媒体库'}\n"
            f"刷新方式：{'仅补充缺失' if summary['refresh_mode'] == REFRESH_MODE_FILL else '替换全部'}\n"
            f"成功 {len(summary['success'])} 个，跳过 {len(summary['skipped'])} 个，"
            f"失败 {len(summary['failed'])} 个，未命中 {len(summary['missed'])} 个\n"
            f"耗时 {summary.get('elapsed', 0)} 秒"
        )
        logger.info("飞牛元数据刷新完成：\n" + text)
        if not self._notify:
            return
        details = []
        for key, label in (
            ("success", "成功"),
            ("skipped", "跳过"),
            ("failed", "失败"),
            ("missed", "未命中"),
        ):
            if summary[key]:
                details.append(f"{label}：{'、'.join(summary[key][:20])}")
        self.post_message(
            mtype=MessageType.MediaServer,
            title="【飞牛元数据刷新】",
            text=text + ("\n\n" + "\n".join(details) if details else ""),
        )

    # ------------------------------------------------------------------
    # 插件对外接口
    # ------------------------------------------------------------------

    def get_service(self) -> List[Dict[str, Any]]:
        """注册定时刷新服务，由宿主调度器按 cron 触发。"""
        if not (self._enabled and self._cron):
            return []
        try:
            trigger = CronTrigger.from_crontab(self._cron)
        except (ValueError, TypeError) as err:
            logger.error(f"飞牛元数据刷新 cron 表达式无效：{self._cron}，{err}")
            return []
        return [
            {
                "id": self.__class__.__name__,
                "name": "飞牛元数据刷新服务",
                "trigger": trigger,
                "func": self.refresh,
                "kwargs": {},
            }
        ]

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """注册远程命令。"""
        return [
            {
                "cmd": "/fnos_meta_refresh",
                "event": EventType.PluginAction,
                "desc": "飞牛元数据刷新",
                "category": "",
                "data": {"action": "fnos_meta_refresh"},
            }
        ]

    def get_api(self) -> List[Dict[str, Any]]:
        """注册手动触发接口。"""
        return [
            {
                "path": "/refresh",
                "endpoint": self.api_refresh,
                "methods": ["GET"],
                "auth": "apikey",
                "summary": "立即刷新飞牛元数据",
                "response_model": schemas.Response[None],
            }
        ]

    def api_refresh(self) -> schemas.Response[None]:
        """外部触发一次刷新。"""
        if not self._enabled:
            return schemas.Response(success=False, message="插件未启用")
        if self._running:
            return schemas.Response(success=False, message="刷新正在执行中")
        threading.Thread(target=self.refresh, name="FnosMetaRefresh", daemon=True).start()
        return schemas.Response(success=True, message="已提交刷新任务")

    @eventmanager.register(EventType.PluginAction)
    def on_plugin_action(self, event: Event = None) -> None:
        """响应远程命令触发刷新。"""
        if not event or not event.event_data:
            return
        if event.event_data.get("action") != "fnos_meta_refresh":
            return
        logger.info("收到命令，开始飞牛元数据刷新 ...")
        self.refresh()

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """返回 V3 Vuetify 配置页面及其默认模型。"""
        server_items = [
            {"title": conf.name, "value": conf.name}
            for conf in MediaServerHelper().get_configs().values()
            if getattr(conf, "type", None) == FNOS_TYPE
        ]
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "enabled", "label": "启用插件"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "onlyonce", "label": "立即运行一次"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "notify", "label": "完成后通知"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 3},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "fallback_library",
                                            "label": "未命中回退整库",
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
                                        "component": "VCronField",
                                        "props": {
                                            "model": "cron",
                                            "label": "执行周期",
                                            "placeholder": "5位cron表达式，默认 0 3 * * *",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "scope",
                                            "label": "刷新粒度",
                                            "items": [
                                                {
                                                    "title": "按近N天入库条目（推荐）",
                                                    "value": SCOPE_HISTORY,
                                                },
                                                {
                                                    "title": "按媒体库整库刷新",
                                                    "value": SCOPE_LIBRARY,
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
                                        "component": "VSelect",
                                        "props": {
                                            "model": "refresh_mode",
                                            "label": "刷新方式",
                                            "items": [
                                                {
                                                    "title": "仅补充缺失的元数据（推荐）",
                                                    "value": REFRESH_MODE_FILL,
                                                },
                                                {
                                                    "title": "替换所有元数据",
                                                    "value": REFRESH_MODE_REPLACE,
                                                },
                                            ],
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
                                            "model": "mediaserver",
                                            "label": "飞牛影视服务",
                                            "items": server_items,
                                            "clearable": True,
                                            "hint": "留空时使用第一个已配置的飞牛影视",
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
                                            "model": "days",
                                            "label": "统计入库天数",
                                            "type": "number",
                                            "placeholder": "默认 7",
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
                                            "model": "interval",
                                            "label": "刷新间隔（秒）",
                                            "type": "number",
                                            "placeholder": "默认 3",
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
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "props": {
                                            "model": "libraries",
                                            "label": "指定媒体库",
                                            "multiple": True,
                                            "chips": True,
                                            "clearable": True,
                                            "hint": "仅「按媒体库整库刷新」时生效，留空表示全部媒体库",
                                            "items": self.__library_items(),
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ], {
            "enabled": self._enabled,
            "onlyonce": self._onlyonce,
            "cron": self._cron,
            "scope": self._scope,
            "mediaserver": self._mediaserver,
            "libraries": self._libraries,
            "refresh_mode": self._refresh_mode,
            "days": self._days,
            "interval": self._interval,
            "notify": self._notify,
            "fallback_library": self._fallback_library,
        }

    def __library_items(self) -> List[Dict[str, str]]:
        """尽力读取飞牛媒体库列表，用于配置页多选。"""
        try:
            api = self.__fnos_api(reconnect=False)
            if api is None or getattr(api, "token", None) is None:
                return []
            result = api.request("/mdb/list", suppress_log=True)
            if not _result_ok(result):
                return []
            libraries = getattr(result, "data", None) or []
        except Exception as err:  # noqa: BLE001 - 配置页不应因远端失败而报错
            logger.warning(f"读取飞牛媒体库列表失败：{err}")
            return []
        items = []
        for info in libraries:
            if not isinstance(info, dict):
                continue
            guid = _as_text(info.get("guid"))
            if not guid:
                continue
            label = _as_text(info.get("name")) or guid
            category = _as_text(info.get("category"))
            if category:
                label = f"{label}（{category}）"
            if info.get("refresh_disabled"):
                label = f"{label} [已禁用刷新]"
            items.append({"title": label, "value": guid})
        return items

    def get_page(self) -> List[dict]:
        """返回插件详情页，展示上次运行结果。"""
        last_run = self.get_data("last_run") or {}
        if not last_run:
            return [
                {
                    "component": "VRow",
                    "content": [
                        {
                            "component": "VCol",
                            "props": {"cols": 12},
                            "content": [
                                {
                                    "component": "VAlert",
                                    "props": {
                                        "type": "info",
                                        "variant": "tonal",
                                        "text": "尚无运行记录",
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]

        rows = [
            {"key": "运行时间", "value": last_run.get("time", "-")},
            {
                "key": "刷新粒度",
                "value": "按入库条目"
                if last_run.get("scope") == SCOPE_HISTORY
                else "按媒体库",
            },
            {
                "key": "刷新方式",
                "value": "仅补充缺失"
                if last_run.get("refresh_mode") == REFRESH_MODE_FILL
                else "替换全部",
            },
            {"key": "耗时", "value": f"{last_run.get('elapsed', 0)} 秒"},
            {"key": "成功", "value": "、".join(last_run.get("success") or []) or "-"},
            {"key": "跳过", "value": "、".join(last_run.get("skipped") or []) or "-"},
            {"key": "失败", "value": "、".join(last_run.get("failed") or []) or "-"},
            {"key": "未命中", "value": "、".join(last_run.get("missed") or []) or "-"},
        ]
        return [
            {
                "component": "VRow",
                "content": [
                    {
                        "component": "VCol",
                        "props": {"cols": 12},
                        "content": [
                            {
                                "component": "VTable",
                                "props": {"hover": True},
                                "content": [
                                    {
                                        "component": "tbody",
                                        "content": [
                                            {
                                                "component": "tr",
                                                "content": [
                                                    {
                                                        "component": "td",
                                                        "props": {"class": "text-caption"},
                                                        "text": row["key"],
                                                    },
                                                    {
                                                        "component": "td",
                                                        "props": {"class": "text-body-2"},
                                                        "text": row["value"],
                                                    },
                                                ],
                                            }
                                            for row in rows
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]

    def stop_service(self) -> None:
        """停止插件，中断正在执行的刷新。"""
        self._event.set()
