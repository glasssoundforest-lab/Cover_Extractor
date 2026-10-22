"""Rust DLL 連携およびシナリオ抽出モジュール (core/extractor.py)

Rust 製 DLL (cover_extractor.dll) を用いた高速な表紙画像抽出、メタデータ抽出、
および ZIP/PDF/フォルダの自動解析とフォールバック処理を提供します。
GUI（Tkinter/PySide6）から完全に独立したバックエンドサービスです。
"""

import ctypes
import io
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import zipfile

# セキュリティ・リソース保護用の制限値
MAX_TEXT_READ_SIZE = 1 * 1024 * 1024   # 最大1MB（概要・あらすじテキスト抽出上限）
MAX_COVER_READ_SIZE = 25 * 1024 * 1024  # 最大25MB（表紙画像データ上限）
MAX_IMAGE_PIXELS = 50_000_000           # ピクセルボム防止（最大5000万画素）


def _pil_image():
    """Pillow は起動時間を延ばすため、表紙のフォールバック探索で初めて読み込む"""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    return Image

from .database import canonical_tag, canonical_system, to_hiragana, is_excluded_tag, generate_player_tags

RUST_ROOT = None


class CoverExtractorError(Exception):
    """表紙抽出やDLL呼び出しに関するエラー"""
    pass


def _library_name():
    if sys.platform == "win32":
        return "cover_extractor.dll"
    if sys.platform == "darwin":
        return "libcover_extractor.dylib"
    return "libcover_extractor.so"


def _app_dir():
    # アプリケーションルート（実行ファイルにした場合は exe のあるフォルダ）
    from core.paths import app_dir

    return app_dir()


def _library_candidates():
    candidates = []
    if os.environ.get("COVER_EXTRACTOR_DLL"):
        candidates.append(os.environ["COVER_EXTRACTOR_DLL"])
    candidates.append(os.path.join(_app_dir(), _library_name()))
    return candidates


def _source_root(rust_root):
    candidates = []
    if os.environ.get("COVER_EXTRACTOR_SRC"):
        candidates.append(os.environ["COVER_EXTRACTOR_SRC"])
    if rust_root:
        candidates.append(rust_root)
    candidates.append(_app_dir())
    for c in candidates:
        if os.path.isfile(os.path.join(c, "Cargo.toml")):
            return c
    raise CoverExtractorError(
        "DLL がなく、ビルドするための Rust のソースも見つかりません（Cargo.toml がありません）。"
    )


def _find_cargo():
    found = shutil.which("cargo")
    if found:
        return found
    home = os.environ.get("CARGO_HOME") or os.path.join(os.path.expanduser("~"), ".cargo")
    exe = "cargo.exe" if sys.platform == "win32" else "cargo"
    path = os.path.join(home, "bin", exe)
    return path if os.path.isfile(path) else None


def _build_library_from_source(rust_root):
    rust_root = _source_root(rust_root)
    cargo = _find_cargo()
    if not cargo:
        raise CoverExtractorError("DLL がなく、ソースからビルドするための cargo も見つかりません。")
    cmd = [cargo, "rustc", "--release", "--lib", "--features", "pdf", "--crate-type", "cdylib"]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    ret = subprocess.run(
        cmd, cwd=rust_root, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=flags
    )
    if ret.returncode != 0:
        tail = "\n".join(ret.stderr.strip().splitlines()[-30:])
        raise CoverExtractorError(f"ソースからの DLL のビルドに失敗しました。\n\n{tail}")
    built = os.path.join(rust_root, "target", "release", _library_name())
    if not os.path.isfile(built):
        raise CoverExtractorError(f"ビルドは成功しましたが、DLL が見つかりません: {built}")
    dest = os.path.join(_app_dir(), _library_name())
    tmp = dest + ".tmp"
    try:
        shutil.copy2(built, tmp)
        os.replace(tmp, dest)
    except OSError as e:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise CoverExtractorError(f"DLL を配置できませんでした: {e}")
    return dest


def _find_library(rust_root):
    res = None
    for c in _library_candidates():
        if os.path.isfile(c):
            res = c
            break
    if res is None:
        res = _build_library_from_source(rust_root)
        # 旧 Tkinter 版の rust_gfx が読み込み済みなら、新しく作った DLL を読み直させる。
        # 未読み込みなら何もしない（rust_gfx は tkinter と Pillow を読むため、Qt 版の起動では import しない）
        gfx = sys.modules.get("rust_gfx")
        if gfx is not None:
            try:
                gfx.reload_gfx_lib()
            except Exception:
                pass
    return res


class RustDllExtractor:
    """Rust 製 cover_extractor.dll との FFI インターフェース"""
    MORE_CANDIDATES = 8

    def __init__(self, rust_root=RUST_ROOT, options=None):
        self.lib_path = _find_library(rust_root)
        lib = ctypes.CDLL(self.lib_path)
        p, s = ctypes.c_void_p, ctypes.c_char_p

        lib.ce_version.restype = s
        lib.ce_last_error.restype = s
        lib.ce_extractor_new.argtypes = [s]
        lib.ce_extractor_new.restype = p
        lib.ce_extractor_free.argtypes = [p]
        lib.ce_extractor_free.restype = None
        lib.ce_extract.argtypes = [p, s]
        lib.ce_extract.restype = p
        lib.ce_more_candidates.argtypes = [p, s, s, ctypes.c_uint32]
        lib.ce_more_candidates.restype = p
        lib.ce_extract_info.argtypes = [p, s]
        lib.ce_extract_info.restype = p
        self.has_url = hasattr(lib, "ce_extract_url")
        if self.has_url:
            lib.ce_extract_url.argtypes = [p, s]
            lib.ce_extract_url.restype = p
        lib.ce_result_json.argtypes = [p]
        lib.ce_result_json.restype = p
        lib.ce_result_image_count.argtypes = [p]
        lib.ce_result_image_count.restype = ctypes.c_uint32
        lib.ce_result_image.argtypes = [p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_size_t)]
        lib.ce_result_image.restype = ctypes.c_int32
        lib.ce_result_free.argtypes = [p]
        lib.ce_result_free.restype = None
        self.lib = lib

        opts = json.dumps(options).encode("utf-8") if options else None
        self.handle = lib.ce_extractor_new(opts)
        if not self.handle:
            raise CoverExtractorError(f"抽出器を作れませんでした: {self._last_error()}")

    def close(self):
        if getattr(self, "handle", None):
            self.lib.ce_extractor_free(self.handle)
            self.handle = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _last_error(self):
        e = self.lib.ce_last_error()
        return e.decode("utf-8", "replace") if e else "unknown error"

    def _take_result(self, handle, what):
        if not handle:
            raise CoverExtractorError(f"{what}: {self._last_error()}")
        try:
            ptr = self.lib.ce_result_json(handle)
            data = json.loads(ctypes.string_at(ptr).decode("utf-8")) if ptr else {}
            images = []
            for i in range(self.lib.ce_result_image_count(handle)):
                buf, size = ctypes.c_void_p(), ctypes.c_size_t()
                if self.lib.ce_result_image(handle, i, ctypes.byref(buf), ctypes.byref(size)) == 0 and buf.value:
                    images.append(ctypes.string_at(buf.value, size.value))
                else:
                    images.append(b"")
            return data, images
        finally:
            self.lib.ce_result_free(handle)

    @staticmethod
    def _path_arg(path):
        return os.fspath(path).encode("utf-8")

    def extract_cover(self, path):
        return self._take_result(self.lib.ce_extract(self.handle, self._path_arg(path)), "表紙の抽出")

    def more_candidates(self, path, exclude, limit):
        ex = json.dumps(list(exclude), ensure_ascii=False).encode("utf-8")
        return self._take_result(
            self.lib.ce_more_candidates(self.handle, self._path_arg(path), ex, limit), "候補の取得"
        )

    def placeholder_jpeg(self):
        if not hasattr(self, "_placeholder"):
            self._placeholder = None
            try:
                cover, images = self.extract_cover(os.path.join(_app_dir(), "__no_such_source__"))
                if cover.get("cover", {}).get("placeholder") and images:
                    self._placeholder = images[0]
            except CoverExtractorError:
                pass
        return self._placeholder

    def extract_url(self, url):
        if not self.has_url:
            raise CoverExtractorError("この DLL は URL からの取得に対応していません。")
        data, images = self._take_result(self.lib.ce_extract_url(self.handle, url.strip().encode("utf-8")), "URL からの取得")
        idx = data.get("image")
        jpeg = images[idx] if idx is not None and idx < len(images) and images[idx] else None
        return data, jpeg

    def extract_info(self, path):
        data, _ = self._take_result(self.lib.ce_extract_info(self.handle, self._path_arg(path)), "情報の抽出")
        return data

    def run_extract(self, target_path):
        thumb_bytes = None
        choices = []
        info_dict = {}

        try:
            cover, images = self.extract_cover(target_path)
            c = cover.get("cover", {})
            for ch in cover.get("choices", []):
                idx = ch.get("image")
                if idx is not None and idx < len(images) and images[idx]:
                    choices.append({"entry_path": ch.get("entry_path", ""), "jpeg": images[idx]})

            if not c.get("placeholder"):
                thumb_bytes = images[c.get("image", 0)] if images else None
            else:
                shown = [ch["entry_path"] for ch in choices]
                more, more_images = self.more_candidates(target_path, shown, self.MORE_CANDIDATES)
                for ch in more.get("candidates", []):
                    idx = ch.get("image")
                    if idx is not None and idx < len(more_images) and more_images[idx]:
                        choices.append({"entry_path": ch.get("entry_path", ""), "jpeg": more_images[idx]})
                if not choices and images:
                    thumb_bytes = images[c.get("image", 0)]
        except CoverExtractorError:
            pass

        try:
            info_dict = self.extract_info(target_path)
        except CoverExtractorError:
            pass

        return thumb_bytes, choices, info_dict


def parse_info(info):
    """抽出された info 辞書から正規化されたフィールドとタグを抽出する"""
    fields = {"title": None, "system_name": None, "players_text": None, "duration_text": None, "overview": None, "synopsis": None}
    auto_tags = []
    if not info:
        return fields, auto_tags

    def value(key):
        obj = info.get(key)
        return obj.get("value") if isinstance(obj, dict) else obj

    title = value("title")
    if title and len(str(title)) >= 2:
        fields["title"] = str(title)[:200]

    system_name = value("system")
    if system_name:
        fields["system_name"] = str(system_name)[:100]
        auto_tags.append(str(system_name)[:100])

    if info.get("players"):
        p_obj = info["players"]
        p_val = value("players")
        if isinstance(p_val, dict):
            min_p, max_p = p_val.get("min"), p_val.get("max")
            if min_p is not None and max_p is not None:
                fields["players_text"] = f"{min_p}〜{max_p}人" if min_p != max_p else f"{min_p}人"
        elif isinstance(p_val, str):
            fields["players_text"] = p_val[:50]

        # 共通ヘルパーで人数タグ（5人以上は「5PL以上」、4人以下は「4PL」「2PL」等）を生成
        p_input = p_val if p_val else (p_obj if isinstance(p_obj, str) else p_obj.get("raw_text"))
        for p_tag in generate_player_tags(p_input):
            if p_tag not in auto_tags:
                auto_tags.append(p_tag)

    d_val = value("duration")
    if isinstance(d_val, dict):
        min_h, max_h = d_val.get("min_hours"), d_val.get("max_hours")
        if min_h is not None and max_h is not None:
            fields["duration_text"] = f"{min_h}〜{max_h}時間" if min_h != max_h else f"{min_h}時間"
    elif isinstance(d_val, str):
        fields["duration_text"] = d_val[:50]

    if value("overview"):
        fields["overview"] = str(value("overview"))[:10000]
    if value("synopsis"):
        fields["synopsis"] = str(value("synopsis"))[:10000]
    return fields, auto_tags


def is_scenario_file(filename):
    """単体でシナリオとなり得る拡張子かどうか"""
    ext = os.path.splitext(filename)[1].lower()
    return ext in {".pdf", ".zip"}


def collect_scenario_targets(paths):
    """
    与えられたパスリスト（ファイルまたはフォルダ）から、
    「1フォルダ=1シナリオ」、または「1ファイル=1シナリオ」として取り込み対象を収集する。
    1つのフォルダ内の複数PDF/ZIPをバラバラに登録せず、フォルダ全体で1つのシナリオとして扱う。
    """
    results = []
    seen = set()

    def add_target(p):
        norm = os.path.abspath(p)
        if norm not in seen and os.path.exists(norm):
            seen.add(norm)
            results.append(norm)

    for p in paths:
        if isinstance(p, bytes):
            try:
                p = p.decode("utf-8")
            except UnicodeDecodeError:
                p = p.decode("cp932", errors="replace")

        p = os.path.abspath(p)
        if not os.path.exists(p):
            continue

        if os.path.isdir(p):
            # フォルダの場合：直下にファイル（PDF, ZIP, TXT等）があるか確認
            has_direct_files = False
            sub_dirs = []
            try:
                for entry in os.scandir(p):
                    if entry.is_file() and not entry.name.startswith("."):
                        has_direct_files = True
                    elif entry.is_dir() and not entry.name.startswith("."):
                        sub_dirs.append(entry.path)
            except Exception:
                pass

            if has_direct_files or not sub_dirs:
                # 直下にファイルが存在する、または子フォルダが存在しない場合は、このフォルダ自身を1つのシナリオとする
                add_target(p)
            else:
                # 直下にファイルがなく子フォルダが並んでいる場合は、まとめ親フォルダとみなして各子フォルダを1つのシナリオとする
                for sub in sub_dirs:
                    add_target(sub)

        elif os.path.isfile(p):
            if is_scenario_file(p):
                add_target(p)

    return results


collect_scenario_files = collect_scenario_targets


def parse_name_clues(name):
    """
    フォルダ名やファイル名からシステム名、タイトル、タグのヒントを抽出する。
    例:
      '【CoC】海も枯れるまで' -> system: 'クトゥルフ神話TRPG', title: '海も枯れるまで', tags: ['CoC']
      '[マダミス]狂気山脈' -> system: 'マーダーミステリー', title: '狂気山脈', tags: ['マダミス']
    """
    clean_name = os.path.splitext(name)[0]
    clues = {"title": clean_name, "system_name": None, "tags": []}

    sys_patterns = [
        (r"(?i)\b(CoC|クトゥルフ|Call of Cthulhu)\b", "クトゥルフ神話TRPG", "CoC"),
        (r"(?i)\b(マダミス|マーダーミステリー|Murder Mystery)\b", "マーダーミステリー", "マダミス"),
        (r"(?i)\b(エモクロア|Emoklore)\b", "エモクロアTRPG", "その他"),
        (r"(?i)\b(インセイン|inSANe)\b", "インセイン", "その他"),
        (r"(?i)\b(シノビガミ|Shinobigami)\b", "シノビガミ", "その他"),
        (r"(?i)\b(マギカロギア|Magicarogia)\b", "マギカロギア", "その他"),
        (r"(?i)\b(フタリソウサ)\b", "フタリソウサ", "その他"),
        (r"(?i)\b(ソード・ワールド|SW2\.5|SW2\.0)\b", "ソード・ワールド2.5", "その他"),
        (r"(?i)\b(ダブルクロス|DX3rd)\b", "ダブルクロス The 3rd Edition", "その他"),
    ]

    for pat, sys_name, tag in sys_patterns:
        if re.search(pat, clean_name):
            clues["system_name"] = sys_name
            if tag:
                clues["tags"].append(tag)
            break

    # 【...】や [...] や (...) を除去したものをタイトル候補にする
    t = re.sub(r"^[【\[［\(（][^】\]］\)）]+[】\]］\)）]\s*", "", clean_name)
    t = re.sub(r"\s*[【\[［\(（][^】\]］\)）]+[】\]］\)）]$", "", t)
    m = re.search(r"[「『]([^」』]+)[」』]", clean_name)
    if m:
        t = m.group(1)

    t = t.strip()
    if t and len(t) >= 2:
        clues["title"] = t

    return clues


def search_fallback_cover(target_path):
    """フォルダ内またはZIP内から表紙画像の候補を探索してJPEGバイト列として返す"""
    valid_exts = {".png", ".jpg", ".jpeg", ".webp"}
    candidates = []

    if os.path.isdir(target_path):
        for root, _, files in os.walk(target_path):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in valid_exts:
                    candidates.append((f.lower(), os.path.join(root, f)))
    elif os.path.isfile(target_path) and target_path.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(target_path, "r") as z:
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    fname = os.path.basename(info.filename)
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in valid_exts:
                        candidates.append((fname.lower(), (target_path, info.filename)))
        except Exception:
            pass

    if not candidates:
        return None

    def score(item):
        name = item[0]
        s = 0
        if any(k in name for k in ["cover", "表紙", "thumb", "main", "title", "トレーラー", "top", "01"]):
            s += 50
        if not any(k in name for k in ["icon", "map", "npc", "立ち絵", "token", "bg", "chip"]):
            s += 10
        return s

    candidates.sort(key=score, reverse=True)
    best = candidates[0][1]

    try:
        if isinstance(best, tuple):
            with zipfile.ZipFile(best[0], "r") as z:
                info = z.getinfo(best[1])
                if info.file_size > MAX_COVER_READ_SIZE:
                    return None
                with z.open(best[1]) as entry_f:
                    data = entry_f.read(MAX_COVER_READ_SIZE)
        else:
            if os.path.getsize(best) > MAX_COVER_READ_SIZE:
                return None
            with open(best, "rb") as f:
                data = f.read(MAX_COVER_READ_SIZE)

        img = _pil_image().open(io.BytesIO(data))
        img.thumbnail((450, 450))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    except Exception:
        return None


def search_fallback_texts(target_path):
    """フォルダ内またはZIP内からあらすじ・概要になりそうなテキストを探索して返す"""
    valid_exts = {".txt", ".md", ".html"}
    candidates = []

    if os.path.isdir(target_path):
        for root, _, files in os.walk(target_path):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in valid_exts:
                    candidates.append((f.lower(), os.path.join(root, f)))
    elif os.path.isfile(target_path) and target_path.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(target_path, "r") as z:
                for info in z.infolist():
                    if info.is_dir():
                        continue
                    fname = os.path.basename(info.filename)
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in valid_exts:
                        candidates.append((fname.lower(), (target_path, info.filename)))
        except Exception:
            pass

    if not candidates:
        return None, None

    def score(item):
        name = item[0]
        s = 0
        if any(k in name for k in ["readme", "概要", "シナリオ", "あらすじ", "story", "info", "はじめに"]):
            s += 50
        return s

    candidates.sort(key=score, reverse=True)
    best = candidates[0][1]

    try:
        if isinstance(best, tuple):
            with zipfile.ZipFile(best[0], "r") as z:
                with z.open(best[1]) as entry_f:
                    raw_bytes = entry_f.read(MAX_TEXT_READ_SIZE)
        else:
            with open(best, "rb") as f:
                raw_bytes = f.read(MAX_TEXT_READ_SIZE)

        text = ""
        for enc in ("utf-8", "cp932", "euc-jp"):
            try:
                text = raw_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                pass

        if not text:
            return None, None

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None, None

        synopsis_lines = []
        capture = False
        for l in lines:
            if any(k in l for k in ["【あらすじ】", "【ストーリー】", "【概要】", "■あらすじ", "■ストーリー", "◆あらすじ"]):
                capture = True
                continue
            if capture:
                if any(l.startswith(prefix) for prefix in ["【", "■", "◆", "▼", "・"]):
                    break
                synopsis_lines.append(l)

        if synopsis_lines:
            syn = "\n".join(synopsis_lines[:6])
            return None, syn
        else:
            ov = "\n".join(lines[:4])
            return ov, None
    except Exception:
        return None, None


def extract_scenario_data(extractor, target_path):
    """
    フォルダまたはZIP（または単体ファイル）から情報を統合抽出する。
    1. Rust DLL による抽出
    2. フォルダ名/ファイル名からのタイトル・システム名補正
    3. 表紙画像のフォールバック探索
    4. 概要・あらすじのフォールバック探索
    5. 不足項目の判定
    """
    raw_name = os.path.basename(target_path.rstrip(r"\/"))
    name_clues = parse_name_clues(raw_name)

    thumb_bytes = None
    choices = []
    info = {}

    if extractor:
        try:
            thumb_bytes, choices, info = extractor.run_extract(target_path)
        except Exception:
            pass

    fields, auto_tags = parse_info(info)

    # 1. タイトル補正
    ext_title = (fields.get("title") or "").strip()
    generic_words = {"readme", "scenario", "無題", "シナリオ", "本編", "ルールブック", "新規テキスト ドキュメント", "index", "data"}
    if not ext_title or ext_title.lower() in generic_words:
        fields["title"] = name_clues["title"] or raw_name
    elif name_clues.get("title") and len(ext_title) < 4 and len(name_clues["title"]) >= 4:
        fields["title"] = name_clues["title"]

    # 2. システム名補正
    if not fields.get("system_name") and name_clues.get("system_name"):
        fields["system_name"] = name_clues["system_name"]

    # 3. タグ統合
    combined_tags = set(auto_tags)
    for t in name_clues.get("tags", []):
        combined_tags.add(t)

    # 4. 表紙画像のフォールバック補完
    if not thumb_bytes:
        thumb_bytes = search_fallback_cover(target_path)

    # 5. 概要・あらすじのフォールバック補完
    if not fields.get("overview") and not fields.get("synopsis"):
        ov, syn = search_fallback_texts(target_path)
        if ov:
            fields["overview"] = ov
        if syn:
            fields["synopsis"] = syn

    # 6. 不足項目の判定
    missing_items = []
    if not thumb_bytes:
        missing_items.append("表紙画像")
    if not fields.get("system_name"):
        missing_items.append("システム名")
    if not (fields.get("synopsis") or fields.get("overview")):
        missing_items.append("概要・あらすじ")

    return {
        "target_path": target_path,
        "raw_name": raw_name,
        "title": fields.get("title") or raw_name,
        "fields": fields,
        "thumb_bytes": thumb_bytes,
        "tags": combined_tags,
        "missing_items": missing_items,
    }
