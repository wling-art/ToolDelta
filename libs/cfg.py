import ujson, os

NoneType = type(None)

PLUGINCFG_DEFAULT = {
    "配置版本": "0.0.1",
    "配置项": None
}
PLUGINCFG_STANDARD_TYPE = {
    "配置版本": str,
    "配置项": [type(None), dict]
}

def _CfgIsinstance(obj, typ):
    # 专用于Cfg的类型检测
    if isinstance(typ, type):
        return {
            Cfg.PInt: lambda:isinstance(obj, int) and obj > 0, 
            Cfg.NNInt: lambda:isinstance(obj, int) and obj >= 0,
            Cfg.PFloat: lambda:isinstance(obj, float) and obj > 0,
            Cfg.NNFloat: lambda:(isinstance(obj, float) or obj == 0) and obj >= 0,
            Cfg.PNumber: lambda:isinstance(obj, (int, float)) and obj > 0,
            Cfg.NNNumber: lambda:isinstance(obj, (int, float)) and obj >= 0
        }.get(typ, lambda:isinstance(obj, typ))()
    elif isinstance(typ, tuple):
        try:
            for i in typ:
                result = {
                    Cfg.PInt: lambda:isinstance(obj, int) and obj > 0, 
                    Cfg.NNInt: lambda:isinstance(obj, int) and obj >= 0,
                    Cfg.PFloat: lambda:isinstance(obj, float) and obj > 0,
                    Cfg.NNFloat: lambda:(isinstance(obj, float) or obj == 0) and obj >= 0,
                    Cfg.PNumber: lambda:isinstance(obj, (int, float)) and obj > 0,
                    Cfg.NNNumber: lambda:isinstance(obj, (int, float)) and obj >= 0
                }.get(i, lambda:isinstance(obj, typ))()
                if result:
                    return True
            return False
        except TypeError:
            raise ValueError(f"Can't be: {typ}")
    raise ValueError(f"Can't be: {typ}")


def _CfgShowType(typ):
    if type(typ) != type:
        typ = type(typ)
    return {
        Cfg.PInt: "正整数",
        Cfg.NNInt: "非负整数",
        Cfg.PFloat: "正浮点小数",
        Cfg.NNFloat: "非负浮点小数",
        str: "字符串",
        float: "浮点小数",
        int: "整数",
        dict: "json对象",
        list: "列表",
        NoneType: "null"
    }.get(typ, typ.__name__)

FIND_NONE = r"%FindNone"

class Cfg:
    class Group:
        def __init__(self, *keys):
            self.members = keys
        def __repr__(self) -> str:
            return 'Cfg.Group("' + '", "'.join(self.members) + '")'
    class ConfigError(Exception):
        def __init__(self, errStr: str, errPos: list = []):
            self.errPos = errPos
            self.args = (errStr,)
    class UnneccessaryKey:
        def __init__(self, key):
            self.key = key
        def __repr__(self):
            return f"Cfg.UnneccessaryKey({self.key})"
    class ConfigKeyError(ConfigError):...
    class ConfigValueError(ConfigError):...
    class VersionLowError(ConfigError):...
    class PInt(int):"正整数"
    class NNInt(int):"非负整数"
    class PFloat(float):"正浮点小数"
    class NNFloat(float):"非负浮点小数"
    class PNumber:"正数"
    class NNNumber:"大于0的数"

    def get_cfg(self, path: str, standard_type: dict):
        # 从path路径获取json文件文本信息, 并按照standard_type给出的标准形式进行检测.
        path = path if path.endswith(".json") else path + ".json"
        with open(path, "r", encoding="utf-8") as f:
            try:
                obj = ujson.load(f)
            except ujson.JSONDecodeError:
                raise self.ConfigValueError("JSON配置文件格式不正确, 请修正或直接删除", None)
        self.check_dict_2(standard_type, obj)
        return obj

    def default_cfg(self, path: str, default: dict, force: bool = False):
        # 向path路径写入json文本, 若文件不存在或参数force为True, 将写入提供的默认json文本
        path = path if path.endswith(".json") else path + ".json"
        if force or not os.path.isfile(path):
            with open(path, "w", encoding='utf-8') as f:
                ujson.dump(default, f, indent = 4, ensure_ascii = False)

    def exists(self, path: str):
        return os.path.isfile(path if path.endswith(".json") else path + ".json")

    def getPluginConfigAndVersion(self, pluginName: str, standardType: dict, default: dict, default_vers: tuple[int, int, int]):
        # 详情见 插件编写指南.md
        assert isinstance(standardType, dict)
        p = "插件配置文件/" + pluginName
        if not self.exists(p) and default:
            defaultCfg = PLUGINCFG_DEFAULT.copy()
            defaultCfg["配置项"] = default
            defaultCfg["配置版本"] = ".".join([str(n) for n in default_vers])
            self.default_cfg(p + ".json", defaultCfg, force=True)
        cfg_stdtyp = PLUGINCFG_STANDARD_TYPE.copy()
        cfg_stdtyp["配置项"] = standardType
        cfgGet = self.get_cfg(p, cfg_stdtyp)
        cfgVers = tuple(int(c) for c in cfgGet["配置版本"].split("."))
        return cfgGet["配置项"], cfgVers
    
    def check_auto(self, standard, val, fromkey = []):
        if fromkey == FIND_NONE:
            raise ValueError("不允许传入FindNone")
        if isinstance(standard, type):
            if not _CfgIsinstance(val, standard):
                raise self.ConfigValueError(
                    f"JSON键\"{fromkey[-1]}\" 对应值的类型不正确: 需要 {_CfgShowType(standard)}, 实际上为 {_CfgShowType(val)}",
                    fromkey.copy()
                )
        elif isinstance(standard, list):
            # [%list] or [multi[type/dict]]
            self.check_list_2(standard, val, fromkey)
        elif isinstance(standard, dict):
            self.check_dict_2(standard, val, fromkey)
        else:
            raise ValueError(f"JSON键 \"{fromkey[-1]}\"未曾遇到过的类型: {standard.__class__.__name__}, 另外两个参数 standard={standard}, val={val}")
    
    def check_dict_2(self, pattern: dict, jsondict: dict, fromkey = []):
        if not isinstance(jsondict, dict):
            raise self.ConfigValueError(
                f"JSON键\"{fromkey[-1]}\" 对应值的类型不正确: 需要 json对象, 实际上为 {_CfgShowType(jsondict)}",
                fromkey.copy()
            )
        for key, std_val in pattern.items():
            if key == r"%any":
                # supports ANY-String key
                for js_key, js_val in jsondict.items():
                    self.check_auto(std_val, js_val, fromkey.copy() + [js_key])
            elif isinstance(key, self.Group):
                # any key in members? if so, check it
                js_val = FIND_NONE
                for member_key in key.members:
                    val_get = jsondict.get(member_key, FIND_NONE)
                    if val_get != FIND_NONE:
                        self.check_auto(std_val, val_get, fromkey.copy() + [member_key])
            elif isinstance(key, self.UnneccessaryKey):
                val_get = jsondict.get(key.key, FIND_NONE)
                if val_get != FIND_NONE:
                    self.check_auto(std_val, val_get, fromkey.copy() + [key.key])
            elif isinstance(key, str):
                val_get = jsondict.get(key, FIND_NONE)
                if val_get == FIND_NONE:
                    raise self.ConfigKeyError(f'不存在的JSON键: {key[-1]}', fromkey.copy() + [key])
                self.check_auto(std_val, val_get, fromkey.copy() + [key])
            else:
                raise Cfg.ConfigError(f"Type val is invalid: {key}")
               
    def check_list_2(self, pattern: list, value, fromkey = []):
        if not isinstance(pattern, list):
            raise ValueError("Not a valid list pattern")
        if len(pattern) == 0:
            raise ValueError("Pattern's length can't be 0")
        if isinstance(pattern[0], str) and pattern[0].startswith(r"%list"):
            if not isinstance(value, list):
                raise self.ConfigValueError(
                    f"JSON键 \"{fromkey[-1]}\" 需要列表 而不是 {_CfgShowType(value)}",
                    fromkey
                )
            limitNumber = 0
            if pattern[0].replace(r"%list", "").isnumeric():
                limitNumber = int(pattern[0].replace(r"%list", ""))
            if limitNumber and len(value) != limitNumber:
                raise self.ConfigValueError(
                    f"JSON键 \"{fromkey[-1]}\" 所对应的值列表有误: 需要 {limitNumber} 项, 实际上为 {len(value)} 项",
                    fromkey
                )
            for val in value:
                self.check_auto(pattern[1], val, fromkey)
        else:
            probably_exc_type = ""
            for single_type in pattern:
                try:
                    self.check_auto(single_type, value, fromkey.copy() + [fromkey])
                    return
                except Cfg.ConfigError as err:
                    probably_exc_type = f"\n还有可能是: {err}"
            raise self.ConfigValueError(
                f"JSON列表的值 \"{fromkey[-1]}\" 类型不正确: 需要 {' 或 '.join(_CfgShowType(i) for i in pattern)}, 实际上为 {_CfgShowType(value)}{probably_exc_type}",
                fromkey
            )
            
    checkDict = check_dict_2


if __name__ == "__main__":
    # Test Part
    try:
        test_cfg = {"a": {"a": 3.2}, "b": {"a": 5.1}, "c": {"a":1}}
        a_std = {r"%any": {"a": Cfg.PFloat}}
        Cfg().check_dict_2(a_std, test_cfg)
    except Cfg.ConfigError as err:
        print(err, ":::", err.errPos)
