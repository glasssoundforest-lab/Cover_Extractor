"""アプリの設定ファイル（settings.ini）の読み書き。

- 設定は main.py と同じフォルダの settings.ini に保存する（データベースには保存しない）。
- Notion のトークンなどの秘密の値は、この PC でしか戻せない形に暗号化して保存する。
  - Windows: DPAPI（CryptProtectData）。今のユーザーと、この PC の MachineGuid に結び付く。
  - それ以外: この PC の machine-id とユーザー名から作った鍵で暗号化する（HMAC-SHA256 の鍵の流れ + 改ざん検知）。
  別の PC や別のユーザーで開くと読めないので、その場合はトークンを入れ直す。
"""

import base64
import configparser
import getpass
import hashlib
import hmac
import json
import os
import platform
import secrets
import sys
import urllib.parse
import re

SETTINGS_FILE = "settings.ini"
_APP_SALT = "cover_extractor/notion-token/v1"

_HEADER = (
    "; グリモワールシェルフ（シナリオ・メディア カタログ）の設定\n"
    "; token の値は、この PC でしか読めない形に暗号化されています。別の PC へ写しても使えません。\n\n"
)


# ----------------------------------------------------------------------------
# この PC に固有の値
# ----------------------------------------------------------------------------
def machine_id():
    """この PC を見分ける値（Windows は MachineGuid、Linux は machine-id）。"""
    value = None
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | getattr(winreg, "KEY_WOW64_64KEY", 0)
            )
            try:
                value, _ = winreg.QueryValueEx(key, "MachineGuid")
            finally:
                winreg.CloseKey(key)
            if value:
                return str(value)
        except OSError:
            pass

    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(path, encoding="ascii") as f:
                value = f.read().strip()
            if value:
                return value
        except OSError:
            pass
    return platform.node() or "unknown-host"


def _user_name():
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - 取れなければ空
        return ""


def _entropy():
    return hashlib.sha256(f"{_APP_SALT}|{machine_id()}".encode("utf-8")).digest()


# ----------------------------------------------------------------------------
# Windows: DPAPI
# ----------------------------------------------------------------------------
def _dpapi(data, entropy, protect_mode):
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(b):
        buf = ctypes.create_string_buffer(b, len(b))
        return Blob(len(b), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char))), buf

    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    args = [
        ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.POINTER(Blob), ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)
    ]
    crypt32.CryptProtectData.argtypes = args
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p

    data_in, _keep1 = blob(data)
    ent, _keep2 = blob(entropy)
    out = Blob()
    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    if protect_mode:
        ok = crypt32.CryptProtectData(
            ctypes.byref(data_in), "cover_extractor", ctypes.byref(ent), None, None, flags, ctypes.byref(out)
        )
    else:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(data_in), None, ctypes.byref(ent), None, None, flags, ctypes.byref(out)
        )
    if not ok:
        raise OSError(ctypes.get_last_error(), "DPAPI での暗号化・復号に失敗しました")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


# ----------------------------------------------------------------------------
# それ以外: この PC とユーザーから作った鍵
# ----------------------------------------------------------------------------
def _local_key():
    material = f"{_APP_SALT}|{machine_id()}|{_user_name()}".encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", material, b"cover_extractor-local", 100_000)


def _keystream(key, nonce, length):
    if length > 65536:
        raise ValueError("復号データ長が上限(64KB)を超えています")
    out = bytearray()
    counter = 0
    while len(out) < length:
        out += hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:length])


def _local_encrypt(data):
    key = _local_key()
    nonce = secrets.token_bytes(16)
    body = bytes(a ^ b for a, b in zip(data, _keystream(key, nonce, len(data))))
    tag = hmac.new(key, b"tag" + nonce + body, hashlib.sha256).digest()[:16]
    return nonce + tag + body


def _local_decrypt(blob):
    if len(blob) < 32:
        raise ValueError("暗号化データの形式が不正です")
    key = _local_key()
    nonce, tag, body = blob[:16], blob[16:32], blob[32:]
    expect = hmac.new(key, b"tag" + nonce + body, hashlib.sha256).digest()[:16]
    if len(nonce) != 16 or not hmac.compare_digest(tag, expect):
        raise ValueError("この PC で暗号化した値ではありません")
    return bytes(a ^ b for a, b in zip(body, _keystream(key, nonce, len(body))))


# ----------------------------------------------------------------------------
# 暗号化・復号
# ----------------------------------------------------------------------------
def protect(text):
    """文字列を、この PC でしか戻せない形にする（"dpapi:..." または "local:..."）。"""
    data = (text or "").encode("utf-8")
    if sys.platform == "win32":
        try:
            return "dpapi:" + base64.b64encode(_dpapi(data, _entropy(), True)).decode("ascii")
        except OSError:
            pass
    return "local:" + base64.b64encode(_local_encrypt(data)).decode("ascii")


def unprotect(value):
    """protect した値を戻す。この PC・このユーザーで作ったものでなければ None。"""
    if not value:
        return ""
    kind, sep, payload = value.partition(":")
    if not sep:
        return None
    try:
        raw = base64.b64decode(payload.encode("ascii"), validate=True)
        if kind == "dpapi" and sys.platform == "win32":
            return _dpapi(raw, _entropy(), False).decode("utf-8")
        if kind == "local":
            return _local_decrypt(raw).decode("utf-8")
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return None


# ----------------------------------------------------------------------------
# 設定ファイル
# ----------------------------------------------------------------------------
class Settings:
    """settings.ini の読み書き。値を変えるたびにファイルへ書く。"""

    def __init__(self, path):
        self.path = path
        self.cp = configparser.ConfigParser(interpolation=None)
        self.cp.optionxform = str
        self.load_error = None
        if os.path.exists(path):
            try:
                self.cp.read(path, encoding="utf-8")
            except (configparser.Error, UnicodeDecodeError) as e:
                self.load_error = str(e)

    def get(self, section, key, default=None):
        return self.cp.get(section, key, fallback=default)

    def get_json(self, section, key, default):
        raw = self.get(section, key)
        if not raw:
            return default
        try:
            value = json.loads(raw)
        except (ValueError, TypeError):
            return default
        return value if value is not None else default

    def get_secret(self, section, key):
        return unprotect(self.get(section, key, ""))

    def set(self, section, key, value, save=True):
        if not self.cp.has_section(section):
            self.cp.add_section(section)
        if value is None or value == "":
            self.cp.remove_option(section, key)
        else:
            self.cp.set(section, key, str(value).replace("\n", " "))
        if save:
            self.save()

    def set_json(self, section, key, value, save=True):
        self.set(section, key, json.dumps(value, ensure_ascii=False, separators=(",", ":")) if value is not None else None, save)

    def set_secret(self, section, key, value, save=True):
        self.set(section, key, protect(value) if value else None, save)

    def get_section(self, section):
        if not self.cp.has_section(section):
            return {}
        return dict(self.cp.items(section))

    def remove_section(self, section):
        if self.cp.has_section(section):
            self.cp.remove_section(section)

    def save(self):
        folder = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(folder, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(_HEADER)
            self.cp.write(f)
        os.replace(tmp, self.path)


# ----------------------------------------------------------------------------
# シングルトンとショートカット設定
# ----------------------------------------------------------------------------
_settings_instance = None


def get_settings():
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = Settings(SETTINGS_FILE)
    return _settings_instance


DEFAULT_SHORTCUTS = {
    "detail_prev": "Left",
    "detail_next": "Right",
    "detail_favorite": "F",
    "detail_edit": "E",
    "detail_close": "Esc",
    "main_search": "Ctrl+F",
    "main_open": "Return",
}

SHORTCUT_LABELS = {
    "detail_prev": "詳細画面: 前の書物へめくる",
    "detail_next": "詳細画面: 次の書物へめくる",
    "detail_favorite": "詳細画面: お気に入り切り替え",
    "detail_edit": "詳細画面: 編集モード切り替え",
    "detail_close": "詳細画面: 閉じる / 取消",
    "main_search": "メイン書架: 検索バーにフォーカス",
    "main_open": "メイン書架: 選択中の本を開く",
}


def get_shortcut(key):
    s = get_settings()
    return s.get("shortcuts", key, DEFAULT_SHORTCUTS.get(key, ""))


def get_all_shortcuts():
    s = get_settings()
    res = {}
    for k, default in DEFAULT_SHORTCUTS.items():
        res[k] = s.get("shortcuts", k, default)
    return res


def save_all_shortcuts(mapping):
    s = get_settings()
    for k, val in mapping.items():
        s.set("shortcuts", k, val, save=False)
    s.save()


DEFAULT_DOMAINS = {
    "booth.pm": "Booth",
}


def clean_domain(domain_or_url: str) -> str:
    """ドメイン文字列またはURLからホスト名（小文字、ポートなし）を抽出・正規化する"""
    text = (domain_or_url or "").strip().lower()
    if not text:
        return ""
    if "://" not in text and not text.startswith("//"):
        text = "https://" + text
    try:
        parsed = urllib.parse.urlsplit(text)
        host = (parsed.hostname or "").lower()
        return host
    except Exception:
        cleaned = text.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0]
        return cleaned.strip()


def get_domain_mappings() -> dict[str, str]:
    """登録されているドメインと表示名の辞書を取得する。"""
    s = get_settings()
    items = s.get_section("domains")
    if not items:
        return dict(DEFAULT_DOMAINS)
    result = {}
    for d, label in items.items():
        clean_d = clean_domain(d) or d.lower().strip()
        if clean_d and label:
            result[clean_d] = label.strip()
    if not result:
        return dict(DEFAULT_DOMAINS)
    return result


def save_domain_mappings(mapping: dict[str, str]):
    """ドメインと表示名の辞書を保存する。"""
    s = get_settings()
    s.remove_section("domains")
    for d, label in mapping.items():
        clean_d = clean_domain(d) or d.lower().strip()
        if clean_d and label:
            s.set("domains", clean_d, label.strip(), save=False)
    s.save()


def get_domain_label_for_url(url: str) -> str | None:
    """URLのホスト名が登録ドメインと一致（またはサブドメイン）する場合、表示名を返す。"""
    if not url:
        return None
    url_str = url.strip()
    if not url_str:
        return None
    try:
        if "://" not in url_str and not url_str.startswith("//"):
            url_str = "https://" + url_str
        parsed = urllib.parse.urlsplit(url_str)
        host = (parsed.hostname or "").lower()
        if not host:
            return None
    except Exception:
        return None

    mappings = get_domain_mappings()
    for d in sorted(mappings.keys(), key=lambda x: len(x), reverse=True):
        if host == d or host.endswith("." + d):
            return mappings[d]
    return None


# Notion API（無料枠）のレート制限（平均3回/秒・180回/分）を考慮し、安全マージンをとった初期値（0.5秒）
DEFAULT_API_INTERVAL = 0.5


def get_api_interval() -> float:
    """APIリクエスト間隔（秒）を取得する（初期値: 0.5秒）"""
    s = get_settings()
    raw = s.get("api", "request_interval") or s.get("notion", "request_interval")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_API_INTERVAL
    try:
        val = float(raw)
        # 旧デフォルト値 5.0（Gemini表記時代）が残っている場合は新デフォルト 0.5 に自動移行
        if abs(val - 5.0) < 1e-4:
            save_api_interval(DEFAULT_API_INTERVAL)
            return DEFAULT_API_INTERVAL
        if val < 0.0:
            return DEFAULT_API_INTERVAL
        return min(val, 300.0)
    except (ValueError, TypeError):
        return DEFAULT_API_INTERVAL


def save_api_interval(interval_sec: float):
    """APIリクエスト間隔（秒）を保存する"""
    s = get_settings()
    try:
        val = max(0.0, min(float(interval_sec), 300.0))
    except (ValueError, TypeError):
        val = DEFAULT_API_INTERVAL
    s.set("api", "request_interval", str(round(val, 2)))


DEFAULT_NOTION_IMPORT_LIMIT = 10


def get_notion_import_limit() -> int:
    """Notionからの取り込み件数上限を取得する（0の場合は無制限）"""
    s = get_settings()
    raw = s.get("notion", "import_limit")
    if raw is None or str(raw).strip() == "":
        return DEFAULT_NOTION_IMPORT_LIMIT
    try:
        val = int(raw)
        return max(0, val)
    except (ValueError, TypeError):
        return DEFAULT_NOTION_IMPORT_LIMIT


def save_notion_import_limit(limit: int):
    """Notionからの取り込み件数上限を保存する（0の場合は無制限）"""
    s = get_settings()
    try:
        val = max(0, int(limit))
    except (ValueError, TypeError):
        val = DEFAULT_NOTION_IMPORT_LIMIT
    s.set("notion", "import_limit", str(val))


def load():
    """辞書形式で設定を読み出す（互換関数）"""
    s = get_settings()
    return {
        "notion_api_key": s.get_secret("notion", "token") or "",
        "notion_database_id": s.get("notion", "database_id") or "",
        "notion_import_limit": get_notion_import_limit(),
        "api_request_interval": get_api_interval(),
        "shortcuts": get_all_shortcuts(),
        "domains": get_domain_mappings(),
    }


def save(data):
    """辞書形式の設定を保存する（互換関数）"""
    s = get_settings()
    if "notion_api_key" in data:
        s.set_secret("notion", "token", data["notion_api_key"], save=False)
    if "notion_database_id" in data:
        s.set("notion", "database_id", data["notion_database_id"], save=False)
    if "notion_import_limit" in data and data["notion_import_limit"] is not None:
        try:
            val = max(0, int(data["notion_import_limit"]))
            s.set("notion", "import_limit", str(val), save=False)
        except (ValueError, TypeError):
            pass
    if "api_request_interval" in data and data["api_request_interval"] is not None:
        try:
            val = max(0.0, min(float(data["api_request_interval"]), 300.0))
            s.set("api", "request_interval", str(round(val, 2)), save=False)
        except (ValueError, TypeError):
            pass
    if "shortcuts" in data and isinstance(data["shortcuts"], dict):
        for k, v in data["shortcuts"].items():
            s.set("shortcuts", k, v, save=False)
    if "domains" in data and isinstance(data["domains"], dict):
        s.remove_section("domains")
        for d, label in data["domains"].items():
            clean_d = clean_domain(d) or d.lower().strip()
            if clean_d and label:
                s.set("domains", clean_d, label.strip(), save=False)
    s.save()


def get_window_geometry(section: str = "window") -> dict:
    """ウィンドウのサイズ・位置・最大化状態を settings.ini から読み出す"""
    s = get_settings()
    sec = s.get_section(section)
    res = {
        "width": None,
        "height": None,
        "maximized": False,
        "x": None,
        "y": None,
    }

    if sec:
        try:
            if "width" in sec and sec["width"]:
                w = int(sec["width"])
                if w >= 400:
                    res["width"] = w
        except (ValueError, TypeError):
            pass

        try:
            if "height" in sec and sec["height"]:
                h = int(sec["height"])
                if h >= 300:
                    res["height"] = h
        except (ValueError, TypeError):
            pass

        try:
            if "maximized" in sec:
                val = str(sec["maximized"]).strip().lower()
                res["maximized"] = val in ("true", "1", "yes")
        except Exception:
            pass

        try:
            if "x" in sec and sec["x"]:
                res["x"] = int(sec["x"])
        except (ValueError, TypeError):
            pass

        try:
            if "y" in sec and sec["y"]:
                res["y"] = int(sec["y"])
        except (ValueError, TypeError):
            pass

    # 過去の古いフォーマット (例: main_geometry = 1264x1162+778+106, detail_geometry = 940x800+937+386) の互換読み取り
    old_sec = s.get_section("window")
    geom_key = "main_geometry" if section == "window" else "detail_geometry"
    max_key = "main_maximized" if section == "window" else "detail_maximized"

    if (not res["width"] or not res["height"]) and old_sec and geom_key in old_sec:
        m = re.match(r"(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?", str(old_sec[geom_key]).strip())
        if m:
            if not res["width"]:
                res["width"] = int(m.group(1))
            if not res["height"]:
                res["height"] = int(m.group(2))
            if res["x"] is None and m.group(3):
                res["x"] = int(m.group(3))
            if res["y"] is None and m.group(4):
                res["y"] = int(m.group(4))

    if not res["maximized"] and old_sec and max_key in old_sec:
        val = str(old_sec[max_key]).strip().lower()
        res["maximized"] = val in ("true", "1", "yes")

    return res


def save_window_geometry(width: int, height: int, maximized: bool = False, x: int = None, y: int = None, section: str = "window"):
    """ウィンドウのサイズ・位置・最大化状態を settings.ini へ保存する"""
    s = get_settings()
    w_val = int(width) if width and width >= 400 else None
    h_val = int(height) if height and height >= 300 else None

    if w_val:
        s.set(section, "width", str(w_val), save=False)
    if h_val:
        s.set(section, "height", str(h_val), save=False)
    s.set(section, "maximized", "true" if maximized else "false", save=False)
    if x is not None:
        s.set(section, "x", str(int(x)), save=False)
    if y is not None:
        s.set(section, "y", str(int(y)), save=False)

    # 互換性のため main_geometry / detail_geometry 形式も保存
    if w_val and h_val:
        pos_part = f"+{int(x)}+{int(y)}" if (x is not None and y is not None) else ""
        compact_geom = f"{w_val}x{h_val}{pos_part}"
        if section == "window":
            s.set("window", "main_geometry", compact_geom, save=False)
            s.set("window", "main_maximized", "1" if maximized else "0", save=False)
        elif section == "detail_window":
            s.set("window", "detail_geometry", compact_geom, save=False)
            s.set("window", "detail_maximized", "1" if maximized else "0", save=False)

    s.save()


def get_detail_window_geometry() -> dict:
    """詳細画面のサイズ・位置・最大化状態を読み出す"""
    return get_window_geometry(section="detail_window")


def save_detail_window_geometry(width: int, height: int, maximized: bool = False, x: int = None, y: int = None):
    """詳細画面のサイズ・位置・最大化状態を保存する"""
    save_window_geometry(width, height, maximized, x, y, section="detail_window")