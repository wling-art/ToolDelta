import asyncio
import importlib
import threading
import time
import traceback
from typing import Any, Callable, Type

from tooldelta import constants
from tooldelta.basic_mods import dotcs_module_env
from tooldelta.color_print import Print
from tooldelta.get_python_libs import get_single_lib
from tooldelta.plugin_load.classic_plugin import Plugin
from tooldelta.plugin_load import (
    classic_plugin,
    dotcs_plugin,
    injected_plugin,
    NON_FUNC,
    NotValidPluginError,
    PluginAPINotFoundError,
    PluginAPIVersionError
)

class PluginGroup:
    plugins: list[Plugin] = []
    plugins_funcs: dict[str, list] = {
        "on_def": [],
        "on_inject": [],
        "on_player_prejoin": [],
        "on_player_join": [],
        "on_player_message": [],
        "on_player_death": [],
        "on_player_leave": [],
    }
    plugin_added_cache = {"plugin": None, "packets": []}
    pluginAPI_added_cache = []

    def __init__(self):
        self.listen_packet_ids = set()
        self.old_dotcs_env = {}
        self.dotcs_global_vars = {}
        self.packet_funcs: dict[str, list[Callable]] = {}
        self.plugins_api: dict[str, Plugin] = {}
        self.excType = 0
        self._broadcast_evts = {}
        self.dotcs_plugin_loaded_num = 0
        self.normal_plugin_loaded_num = 0
        self.injected_plugin_loaded_num = 0
        self.dotcs_repeat_threadings = {"1s": [], "10s": [], "30s": [], "1m": []}
        self.loaded_plugins_name = []
        self.linked_frame = None

    def set_frame(self, frame):
        self.linked_frame = frame

    @staticmethod
    def require(module_name: str, pip_name=""):
        try:
            importlib.import_module(module_name)
        except (ModuleNotFoundError, ImportError):
            get_single_lib(pip_name if pip_name else module_name)

    def read_all_plugins(self):
        try:
            dotcs_plugin.read_plugins(self, dotcs_module_env)
            classic_plugin.read_plugins(self)
            self.execute_def(self.linked_frame.on_plugin_err)
            asyncio.run(injected_plugin.load_plugin(self))
        except Exception:
            err_str = '\n'.join(traceback.format_exc().split('\n')[1:])
            Print.print_err(f"加载插件出现问题: \n{err_str}")
            raise SystemExit

    @staticmethod
    def load_plugin_hot(plugin_name: str, plugin_type: str):
        plugin = None
        if plugin_type == "dotcs":
            Print.print_war("暂时无法热载入DotCS插件")
        elif plugin_type == "classic":
            plugin = classic_plugin.load_plugin(plugin_name, True)
        elif plugin_type == "injected":
            asyncio.run(injected_plugin.load_plugin_file(plugin_name))
        if plugin is not None:
            plugin.on_def()
        Print.print_suc(f"成功热加载插件: {plugin_name}")

    def add_broadcast_listener(self, evt_name: str):
        "将下面的方法作为一个广播事件接收器"

        def deco(func: Callable[[Any], bool]):
            if self._broadcast_evts.get(evt_name):
                self._broadcast_evts[evt_name].append(func)
            else:
                self._broadcast_evts[evt_name] = [func]
        return deco

    def broadcastEvt(self, evt_name: str, **kwargs) -> list[Any] | None:
        "向全局广播一个特定事件, 可以传入附加信息参数"
        callback_list = []
        res = self._broadcast_evts.get(evt_name)
        if res:
            for f in res:
                interrupt, *res2 = f(**kwargs)
                if res2:
                    callback_list.append(res2)
                    if interrupt:
                        break
            return callback_list
        return None

    def test_plugin(self, plugin: Plugin):
        if self.linked_frame is None:
            # 很可能是直接单独运行此插件的代码.
            Print.clean_print(f"插件主类信息({plugin.name}): ")
            Print.clean_print(f" - 作者: {plugin.author}\n - 版本: {plugin.version}")
            Print.clean_print(f" - 数据包监听: {', '.join(str(i) for i in self.listen_packet_ids)}")

    def add_plugin(self, plugin: Plugin):
        try:
            if not Plugin.__subclasscheck__(plugin):
                raise NotValidPluginError(f"插件主类必须继承Plugin类 而不是 {plugin}")
        except TypeError:
            if not Plugin.__subclasscheck__(type(plugin)):
                raise NotValidPluginError(
                    f"插件主类必须继承Plugin类 而不是 {plugin.__class__.__name__}"
                )
        self.plugin_added_cache["plugin"] = plugin
        self.test_plugin(plugin)
        return plugin

    def add_packet_listener(self, pktID):
        def deco(func):
            if isinstance(pktID, int):
                self.plugin_added_cache["packets"].append((pktID, func))
            else:
                for i in pktID:
                    self.plugin_added_cache["packets"].append((i, func))
            return func

        return deco

    def add_plugin_as_api(self, apiName: str):
        def _add_plugin_2_api(api_plugin: Type[Plugin]):
            if not Plugin.__subclasscheck__(api_plugin):
                raise NotValidPluginError(
                    "API插件主类必须继承Plugin类"
                )
            self.plugin_added_cache["plugin"] = api_plugin
            self.pluginAPI_added_cache.append(apiName)
            self.test_plugin(api_plugin)
            return api_plugin

        return _add_plugin_2_api

    def get_plugin_api(
        self, apiName: str, min_version: tuple | None = None
    ) -> Plugin:
        api = self.plugins_api.get(apiName)
        if api:
            if min_version and api.version < min_version:
                raise PluginAPIVersionError(apiName, min_version, api.version)
            return api
        raise PluginAPINotFoundError(f"无法找到API插件：{apiName}")

    def checkSystemVersion(self, need_vers: tuple[int, int, int]):
        if need_vers > self.linked_frame.sys_data.system_version:
            raise self.linked_frame.SystemVersionException(
                f"该组件需要{self.linked_frame.PRG_NAME}为{'.'.join([str(i) for i in self.linked_frame.sys_data.system_version])}版本"
            )

    def add_listen_packet_id(self, packetType: int):
        self.listen_packet_ids.add(packetType)
        self.linked_frame.link_game_ctrl.add_listen_pkt(packetType)

    def add_listen_packet_func(self, packetType, func: Callable):
        if self.packet_funcs.get(str(packetType)):
            self.packet_funcs[str(packetType)].append(func)
        else:
            self.packet_funcs[str(packetType)] = [func]

    def execute_dotcs_repeat(self):
        "启动dotcs插件的循环执行模式插件事件"
        threading.Thread(target=self.run_dotcs_repeat_funcs).start()

    def run_dotcs_repeat_funcs(self):
        lastTime10s = 0
        lastTime30s = 0
        lastTime1m = 0
        if not any(self.dotcs_repeat_threadings.values()):
            return
        Print.print_inf(
            f"开始运行 {sum(len(funcs) for funcs in self.dotcs_repeat_threadings.values())} 个原dotcs计划任务方法"
        )
        while 1:
            time.sleep(1)
            nowTime = time.time()
            if nowTime - lastTime1m > 60:
                for fname, func in self.dotcs_repeat_threadings["1m"]:
                    try:
                        # A strong desire to remove "try" block !!
                        func()
                    except Exception as err:
                        Print.print_err(f"原dotcs插件 <{fname}> (计划任务1min)报错: {err}")
                lastTime1m = nowTime
            if nowTime - lastTime30s > 30:
                for fname, func in self.dotcs_repeat_threadings["30s"]:
                    try:
                        func()
                    except Exception as err:
                        Print.print_err(f"原dotcs插件 <{fname}> (计划任务30s)报错: {err}")
                lastTime30s = nowTime
            if nowTime - lastTime10s > 10:
                for fname, func in self.dotcs_repeat_threadings["10s"]:
                    try:
                        func()
                    except Exception as err:
                        Print.print_err(f"原dotcs插件 <{fname}> (计划任务10s)报错: {err}")
                lastTime10s = nowTime
            for fname, func in self.dotcs_repeat_threadings["1s"]:
                try:
                    func()
                except Exception as err:
                    Print.print_err(f"原dotcs插件 <{fname}> (计划任务1s) 报错: {err}")

    def execute_def(self, onerr: Callable[[str, Exception, str], None] = NON_FUNC):
        for name, func in self.plugins_funcs["on_def"]:
            try:
                func()
            except PluginAPINotFoundError as err:
                Print.print_err(f"插件 {name} 需要包含该种接口的前置组件: {err.name}")
                raise SystemExit
            except PluginAPIVersionError as err:
                Print.print_err(
                    f"插件 {name} 需要该前置组件 {err.name} 版本: {err.m_ver}, 但是现有版本过低: {err.n_ver}"
                )
                raise SystemExit
            except Exception as err:
                onerr(name, err, traceback.format_exc())

    def execute_init(self, onerr: Callable[[str, Exception, str], None] = NON_FUNC):
        for name, func in self.plugins_funcs["on_inject"]:
            try:
                func()
            except Exception as err:
                onerr(name, err, traceback.format_exc())

    def execute_player_prejoin(
        self, player, onerr: Callable[[str, Exception, str], None] = NON_FUNC
    ):
        for name, func in self.plugins_funcs["on_player_prejoin"]:
            try:
                func(player)
            except Exception as err:
                onerr(name, err, traceback.format_exc())

    def execute_player_join(
        self, player, onerr: Callable[[str, Exception, str], None] = NON_FUNC
    ):
        for name, func in self.plugins_funcs["on_player_join"]:
            try:
                func(player)
            except Exception as err:
                onerr(name, err, traceback.format_exc())

    def execute_player_message(
        self, player, msg, onerr: Callable[[str, Exception, str], None] = NON_FUNC
    ):
        pat = f"[{player}] "
        if msg.startswith(pat):
            msg = msg.strip(pat)
        for name, func in self.plugins_funcs["on_player_message"]:
            try:
                func(player, msg)
            except Exception as err:
                onerr(name, err, traceback.format_exc())

    def execute_player_leave(
        self, player, onerr: Callable[[str, Exception, str], None] = NON_FUNC
    ):
        for name, func in self.plugins_funcs["on_player_leave"]:
            try:
                func(player)
            except Exception as err:
                onerr(name, err, traceback.format_exc())

    def execute_player_death(
        self,
        player: str,
        killer: str | None,
        msg: str,
        onerr: Callable[[str, Exception, str], None] = NON_FUNC,
    ):
        for name, func in self.plugins_funcs["on_player_death"]:
            try:
                func(player, killer, msg)
            except Exception as err:
                onerr(name, err, traceback.format_exc())

    def processPacketFunc(self, pktID: int, pkt: dict):
        d = self.packet_funcs.get(str(pktID))
        if d:
            for func in d:
                try:
                    res = func(pkt)
                    if res:
                        return True
                except:
                    Print.print_err(f"插件方法 {func.__name__} 出错：")
                    Print.print_err(traceback.format_exc())
        return False

plugin_group = PluginGroup()
