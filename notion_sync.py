"""Notion のデータベースとの読み込み・書き出し。

Notion の公式 API（https://api.notion.com）を、Python の標準ライブラリだけで呼ぶ。
"""

import gzip
import hashlib
import http.client
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid

API_BASE = "https://api.notion.com"
NOTION_VERSION = "2025-09-03"
# Notion APIレート制限（無料枠：平均3回/秒・180回/分）に合わせた安全初期ディレイ（0.5秒）
REQUEST_INTERVAL = 0.5
TEXT_CHUNK = 2000
MAX_TEXT_CHUNKS = 100

FIELDS = [
    ("title", "題名", ("title",), ("タイトル", "題名", "名前", "シナリオ名", "作品名", "name", "title")),
    ("title_kana", "読み仮名", ("rich_text",), ("読み", "よみ", "ふりがな", "フリガナ", "かな", "kana", "reading")),
    ("author", "作者", ("rich_text", "select", "multi_select"), ("作者", "著者", "作家", "制作", "author", "creator", "writer")),
    ("system_name", "システム", ("select", "rich_text", "multi_select", "status"), ("システム", "system", "ルール")),
    ("players_text", "PL人数", ("rich_text", "number", "select"), ("人数", "pl", "プレイヤー", "players")),
    ("duration_text", "所要時間", ("rich_text", "number", "select"), ("時間", "所要", "プレイ時間", "duration", "time")),
    ("overview", "概要", ("rich_text",), ("概要", "overview", "仕様")),
    ("synopsis", "あらすじ", ("rich_text",), ("あらすじ", "ストーリー", "synopsis", "story")),
    ("tags", "タグ", ("multi_select", "rich_text", "select", "status"), ("タグ", "tag", "tags", "ラベル", "しおり", "状態", "ステータス", "ジャンル", "カテゴリ", "category", "genre")),
    ("source_url", "情報元の URL", ("url", "rich_text"), ("url", "情報元", "販売", "booth", "リンク", "link")),
    ("file_path", "ファイルの場所", ("rich_text", "url"), ("ファイル", "パス", "場所", "path", "file")),
]
FIELD_LABELS = {k: label for k, label, _, _ in FIELDS}


def compute_cover_hash(data: bytes | None) -> str | None:
    """表紙画像バイナリの短縮SHA256ハッシュを計算する（重複アップロード防止用）"""
    if not data:
        return None
    return hashlib.sha256(data).hexdigest()[:16]


class NotionError(Exception):
    pass


# ----------------------------------------------------------------------------
# 接続
# ----------------------------------------------------------------------------
def database_id_from_url(text):
    """データベースの URL（または ID そのもの）から ID を取り出す。"""
    text = (text or "").strip()[:2048]
    if not text:
        raise NotionError("URLが空です。")
    path = text.split("?", 1)[0].split("#", 1)[0]
    
    # ReDoS 防止のため、固定長の UUID フォーマットまたは連続32文字のみを検出
    m = re.findall(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b|\b[0-9a-fA-F]{32}\b",
        path
    )
    if not m:
        raise NotionError("データベースの URL から ID を読み取れませんでした。Notion でデータベースを開き、URL をコピーしてください。")
    raw = m[-1].replace("-", "").lower()
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


class NotionClient:
    def __init__(self, token, api_base=None, request_interval=None):
        token = (token or "").strip()
        if not token:
            raise NotionError("Notion のトークンが設定されていません。")
        self.token = token
        self.api_base = (api_base or API_BASE).rstrip("/")
        if request_interval is None:
            try:
                import app_settings
                request_interval = app_settings.get_api_interval()
            except Exception:
                request_interval = REQUEST_INTERVAL
        self.request_interval = max(0.0, float(request_interval))
        self._last = 0.0
        self._conns = {}

    def _wait(self):
        delay = self.request_interval - (time.monotonic() - self._last)
        if delay > 0:
            time.sleep(delay)
        self._last = time.monotonic()

    def _headers(self, content_type="application/json"):
        h = {"Authorization": f"Bearer {self.token}", "Notion-Version": NOTION_VERSION}
        if content_type:
            h["Content-Type"] = content_type
        return h

    def _connection(self, scheme, host):
        """ホストごとの接続を使い回す（毎回の TCP・TLS の接続確立を省く）"""
        key = (scheme, host)
        conn = self._conns.get(key)
        if conn is None:
            cls = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
            conn = cls(host, timeout=60)
            self._conns[key] = conn
        return conn

    def _drop_connection(self, scheme, host):
        conn = self._conns.pop((scheme, host), None)
        if conn is not None:
            conn.close()

    def close(self):
        """使い回している接続を閉じる"""
        for key in list(self._conns):
            self._drop_connection(*key)

    def _send(self, method, url, data, headers):
        """1回分の送受信。(状態コード, 応答ヘッダー, 本文) を返す。本文は gzip 圧縮なら展開する"""
        parts = urllib.parse.urlsplit(url)
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
        conn = self._connection(parts.scheme, parts.netloc)
        try:
            conn.request(method, target, body=data, headers=headers)
            resp = conn.getresponse()
            payload = resp.read()
        except (http.client.HTTPException, OSError):
            # 相手に閉じられた接続を使い回した場合などは、接続を作り直して呼び出し元で再試行する
            self._drop_connection(parts.scheme, parts.netloc)
            raise
        if resp.getheader("Content-Encoding", "").lower() == "gzip":
            payload = gzip.decompress(payload)
        if resp.getheader("Connection", "").lower() == "close":
            self._drop_connection(parts.scheme, parts.netloc)
        return resp.status, resp.headers, payload

    def request(self, method, path, body=None, raw=None, content_type="application/json", retries=4):
        url = path if path.startswith("http") else f"{self.api_base}{path}"
        data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
        headers = self._headers(content_type)
        headers["Accept-Encoding"] = "gzip"
        for attempt in range(retries + 1):
            self._wait()
            try:
                status, resp_headers, payload = self._send(method, url, data, headers)
            except (http.client.HTTPException, OSError) as e:
                if attempt < retries:
                    # 使い回していた接続が切れていただけのことが多いため、初回はすぐ再試行する
                    if attempt:
                        time.sleep(1.5 * attempt)
                    continue
                raise NotionError(f"Notion に接続できませんでした: {e}") from None
            if status < 400:
                text = payload.decode("utf-8")
                return json.loads(text) if text else {}
            detail = payload.decode("utf-8", "replace")
            if status in (429, 502, 503, 504) and attempt < retries:
                retry_hdr = resp_headers.get("Retry-After")
                wait = None
                if retry_hdr:
                    try:
                        wait = float(retry_hdr)
                    except (ValueError, TypeError):
                        pass
                if wait is None:
                    try:
                        body_info = json.loads(detail)
                        wait = float(body_info.get("retry_after") or body_info.get("additional_data", {}).get("retry_after") or 0)
                    except Exception:
                        pass
                if not wait or wait <= 0:
                    wait = 1.0 * (attempt + 1)
                time.sleep(min(wait, 60))
                continue
            raise NotionError(self._describe(status, detail))
        raise NotionError("Notion の応答がありませんでした。")

    @staticmethod
    def _describe(code, detail):
        try:
            info = json.loads(detail)
            msg, err = info.get("message", ""), info.get("code", "")
        except ValueError:
            msg, err = detail[:300], ""
        if code == 401:
            return "Notion のトークンが正しくありません（401）。インテグレーションのトークンを確認してください。"
        if code == 404 or err == "object_not_found":
            return (
                "データベースが見つかりません（404）。データベースをインテグレーションに共有しているか確認してください"
                "（データベースの「…」→「接続」→ インテグレーションを追加）。"
            )
        if code == 403:
            return f"この操作の権限がありません（403）。インテグレーションの機能（読み取り・更新・挿入）を確認してください。{msg}"
        return f"Notion がエラーを返しました（{code} {err}）: {msg}"

    def data_sources(self, database_id):
        db = self.request("GET", f"/v1/databases/{database_id}")
        sources = [(d["id"], d.get("name") or "") for d in db.get("data_sources") or []]
        if not sources:
            sources = [(database_id, "")]
        title = "".join(t.get("plain_text", "") for t in db.get("title") or [])
        return title, sources

    def schema(self, data_source_id):
        try:
            ds = self.request("GET", f"/v1/data_sources/{data_source_id}")
        except NotionError:
            ds = self.request("GET", f"/v1/databases/{data_source_id}")
        return {name: prop.get("type") for name, prop in (ds.get("properties") or {}).items()}

    def query_all(self, data_source_id, progress=None, limit=None, filter=None, sorts=None):
        """ページを全件（または limit 件）取得する。filter / sorts は Notion の query の指定をそのまま渡す"""
        pages, cursor = [], None
        use_data_sources_endpoint = True
        while True:
            page_size = 100
            if limit is not None:
                remaining = limit - len(pages)
                if remaining <= 0:
                    break
                page_size = max(1, min(100, remaining))

            body = {"page_size": page_size}
            if filter:
                body["filter"] = filter
            if sorts:
                body["sorts"] = sorts
            if cursor:
                body["start_cursor"] = cursor

            if use_data_sources_endpoint:
                try:
                    res = self.request("POST", f"/v1/data_sources/{data_source_id}/query", body)
                except NotionError:
                    use_data_sources_endpoint = False
                    res = self.request("POST", f"/v1/databases/{data_source_id}/query", body)
            else:
                res = self.request("POST", f"/v1/databases/{data_source_id}/query", body)

            filtered = [
                p for p in res.get("results", [])
                if p.get("object") == "page" and not p.get("in_trash") and not p.get("archived")
            ]
            if limit is not None and len(pages) + len(filtered) > limit:
                filtered = filtered[: limit - len(pages)]

            pages.extend(filtered)
            if progress:
                progress(len(pages))
            if limit is not None and len(pages) >= limit:
                return pages[:limit]
            if not res.get("has_more"):
                return pages
            cursor = res.get("next_cursor")
        return pages

    def create_page(self, data_source_id, properties, cover_upload_id=None):
        body = {"parent": {"data_source_id": data_source_id}, "properties": properties}
        if cover_upload_id:
            body["cover"] = {"type": "file_upload", "file_upload": {"id": cover_upload_id}}
        try:
            return self.request("POST", "/v1/pages", body)
        except NotionError:
            # 旧APIバージョン（database_id指定）へのフォールバック
            body["parent"] = {"database_id": data_source_id}
            return self.request("POST", "/v1/pages", body)

    def update_page(self, page_id, properties=None, cover_upload_id=None):
        body = {}
        if properties:
            body["properties"] = properties
        if cover_upload_id:
            body["cover"] = {"type": "file_upload", "file_upload": {"id": cover_upload_id}}
        return self.request("PATCH", f"/v1/pages/{page_id}", body) if body else {}

    def upload_file(self, data, filename="cover.jpg", content_type="image/jpeg"):
        created = self.request("POST", "/v1/file_uploads", {"filename": filename, "content_type": content_type})
        boundary = uuid.uuid4().hex
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8") + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
        send_url = created.get("upload_url") or f"{self.api_base}/v1/file_uploads/{created['id']}/send"
        self.request("POST", send_url, raw=body, content_type=f"multipart/form-data; boundary={boundary}")
        return created["id"]

    def download(self, url, limit=32 * 1024 * 1024):
        # 表紙画像は Notion API ではなくファイル置き場（署名付き URL）から取るため、API の間隔待ちは不要
        req = urllib.request.Request(url, headers={"User-Agent": "cover-extractor"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read(limit + 1)
        if len(data) > limit:
            raise NotionError("画像が大きすぎます。")
        return data


# ----------------------------------------------------------------------------
# 列の対応付け
# ----------------------------------------------------------------------------
def guess_mapping(schema):
    mapping, used = {}, set()
    norm = lambda s: unicodedata.normalize("NFKC", s or "").lower().replace(" ", "")
    for key, _label, types, words in FIELDS:
        candidates = [n for n, t in schema.items() if t in types and n not in used]
        if key == "title":
            pick = next((n for n in candidates if schema[n] == "title"), None)
        else:
            pick = next((n for w in words for n in candidates if norm(w) in norm(n)), None)
        if pick:
            mapping[key] = pick
            used.add(pick)
    return mapping


def find_cover_column(schema):
    """スキーマ内に表紙・カバー用の files 型列があればその列名を返す"""
    cover_keywords = ("表紙", "カバー", "サムネ", "画像", "cover", "thumb", "image")
    for name, prop_type in (schema or {}).items():
        if prop_type == "files":
            norm_name = unicodedata.normalize("NFKC", name or "").lower()
            if any(w in norm_name for w in cover_keywords):
                return name
    return None


def check_mapping(schema, mapping, require_file_path=False):
    title_col = mapping.get("title")
    if not title_col:
        return "「題名」に対応する列（Notion の名前の列）を選んでください。"
    for key, col in mapping.items():
        if col and col not in schema:
            return f"「{FIELD_LABELS.get(key, key)}」の列「{col}」がデータベースにありません。"
    if require_file_path and not mapping.get("file_path"):
        return "「ファイルの場所」に対応する列を選んでください（どのシナリオか見分けるのに使います）。"
    return None


# ----------------------------------------------------------------------------
# 値の読み書き
# ----------------------------------------------------------------------------
def _rich_text(value):
    text = str(value or "")
    chunks = [text[i:i + TEXT_CHUNK] for i in range(0, len(text), TEXT_CHUNK)][:MAX_TEXT_CHUNKS]
    return [{"type": "text", "text": {"content": c}} for c in chunks]


def _option_name(value):
    return str(value or "").replace(",", "、").strip()[:100]


def first_number(text):
    m = re.search(r"\d+(?:\.\d+)?", unicodedata.normalize("NFKC", str(text or "")[:100]))
    if not m:
        return None
    v = float(m.group())
    return int(v) if v.is_integer() else v


def to_property(prop_type, value):
    if prop_type == "title":
        if isinstance(value, (list, tuple)):
            value = "、".join(str(v) for v in value if v)
        return {"title": _rich_text(value)}
    if prop_type == "rich_text":
        if isinstance(value, (list, tuple)):
            value = "、".join(str(v) for v in value if v)
        return {"rich_text": _rich_text(value)}
    if prop_type == "select":
        if isinstance(value, (list, tuple)):
            value = "・".join(str(v).strip() for v in value if str(v).strip())
        name = _option_name(value)
        return {"select": {"name": name} if name else None}
    if prop_type == "status":
        if isinstance(value, (list, tuple)):
            value = next((str(v).strip() for v in value if str(v).strip()), "")
        name = _option_name(value)
        return {"status": {"name": name} if name else None}
    if prop_type == "multi_select":
        if isinstance(value, str):
            values = [v.strip() for v in re.split(r"[、,]", value) if v.strip()]
        elif isinstance(value, (list, tuple)):
            values = list(value)
        else:
            values = [value] if value else []
        names = []
        for v in values:
            n = _option_name(v)
            if n and n not in names:
                names.append(n)
        return {"multi_select": [{"name": n} for n in names]}
    if prop_type == "number":
        return {"number": first_number(value)}
    if prop_type == "url":
        return {"url": str(value)[:2000] if value else None}
    if prop_type == "files":
        if isinstance(value, str) and value:
            return {"files": [{"type": "file_upload", "name": "cover.jpg", "file_upload": {"id": value}}]}
        if isinstance(value, list):
            return {"files": value}
        return {"files": []}
    raise NotionError(f"この種類の列には書き込めません: {prop_type}")


def from_property(prop):
    if not prop:
        return None
    t = prop.get("type")
    v = prop.get(t)
    if t in ("title", "rich_text"):
        s = "".join(x.get("plain_text") or x.get("text", {}).get("content", "") for x in v or [])
        return s or None
    if t in ("select", "status"):
        return v.get("name") if v else None
    if t == "multi_select":
        return [o.get("name") for o in v or [] if o.get("name")]
    if t == "number":
        if v is None:
            return None
        return str(int(v)) if float(v).is_integer() else str(v)
    if t in ("url", "email", "phone_number"):
        return v or None
    return None


def page_cover_url(page):
    cover = page.get("cover") or {}
    t = cover.get("type")
    if t in ("file", "external"):
        url = (cover.get(t) or {}).get("url")
        if url:
            return url

    # ページカバーが未設定の場合、プロパティ内の files 型（表紙・カバー・画像等）から抽出
    props = page.get("properties") or {}
    cover_keywords = ("表紙", "カバー", "サムネ", "画像", "cover", "thumb", "image")
    sorted_props = sorted(
        props.items(),
        key=lambda kv: (0 if any(w in kv[0].lower() for w in cover_keywords) else 1),
    )
    for _name, prop in sorted_props:
        if isinstance(prop, dict) and prop.get("type") == "files":
            for fobj in prop.get("files") or []:
                ft = fobj.get("type")
                if ft in ("file", "external"):
                    furl = (fobj.get(ft) or {}).get("url")
                    if furl:
                        return furl
    return None


def page_notion_url(page):
    """Notionのページから誰とでも共有可能なグローバルURL（public_url優先、なければurlまたはページID）を取得する"""
    if not isinstance(page, dict):
        return ""
    pub = page.get("public_url")
    if pub and isinstance(pub, str) and pub.strip():
        return pub.strip()
    u = page.get("url")
    if u and isinstance(u, str) and u.strip():
        return u.strip()
    pid = page.get("id") or ""
    clean_id = pid.replace("-", "").strip()
    if clean_id:
        return f"https://www.notion.so/{clean_id}"
    return ""


def page_values(page, mapping, schema):
    props = page.get("properties") or {}
    out = {}
    for key, col in mapping.items():
        if not col:
            continue
        value = from_property(props.get(col))
        if key == "tags":
            if isinstance(value, str):
                value = [v.strip() for v in re.split(r"[、,]", value) if v.strip()]
            value = value or []
        elif isinstance(value, list):
            value = "、".join(value) or None
        if value and schema.get(col) == "number":
            if key == "players_text":
                value = f"{value}人"
            elif key == "duration_text":
                value = f"{value}時間"
        out[key] = value

    # Notion共有グローバルURL（public_url優先）
    notion_url = page_notion_url(page)
    if notion_url:
        out["notion_url"] = notion_url

    # tags が未取得または空の場合、multi_select / select 型のプロパティからタグを自動収集
    if not out.get("tags"):
        collected = []
        for prop_name, prop_val in props.items():
            if isinstance(prop_val, dict):
                p_type = prop_val.get("type")
                if p_type == "multi_select":
                    ms = prop_val.get("multi_select") or []
                    for item in ms:
                        t_name = item.get("name")
                        if t_name and t_name not in collected:
                            collected.append(t_name)
        if collected:
            out["tags"] = collected

    return out


def import_from_notion(db, client, data_source_id, mapping=None, schema=None, progress_callback=None, limit=10):
    """Notion データベースからページ一覧を読み込み、シナリオ名・表紙・タグ等を切り分けて DB に登録する。"""
    if schema is None:
        schema = client.schema(data_source_id)
    if not mapping:
        mapping = guess_mapping(schema)
    else:
        guessed = guess_mapping(schema)
        for k, v in guessed.items():
            if not mapping.get(k):
                mapping[k] = v

    query_limit = None if (limit is None or limit == 0) else limit
    pages = client.query_all(data_source_id, limit=query_limit)
    if query_limit is not None and len(pages) > query_limit:
        pages = pages[:query_limit]
    total = len(pages)
    imported_ids = []

    for idx, page in enumerate(pages):
        page_id = page.get("id") or f"notion-page-{idx}"
        notion_edit_time = page.get("last_edited_time") or ""
        vals = page_values(page, mapping, schema)
        title = vals.get("title") or "無題のシナリオ"

        if progress_callback:
            progress_callback(idx + 1, total, title)

        cover_url = page_cover_url(page)
        thumb_bytes = None
        if cover_url:
            try:
                thumb_bytes = client.download(cover_url)
            except Exception as e:
                print(f"[NotionSync] Cover download failed for {title}: {e}")

        item_id = db.save_or_update_from_notion(
            page_id, vals, thumbnail_bytes=thumb_bytes, last_edited_time=notion_edit_time
        )
        imported_ids.append(item_id)

    return imported_ids


def build_properties(values, mapping, schema, cover_upload_id=None):
    """Notion 側のテーブルスキーマ（列名・型）に沿った properties 辞書を構築する。"""
    props = {}
    for key, col in mapping.items():
        if not col or key not in values or col not in schema:
            continue
        props[col] = to_property(schema[col], values[key])

    # スキーマ内に表紙用の files 型列があり、かつアップロード済みファイルIDがある場合は列にも設定
    if cover_upload_id:
        cover_col = find_cover_column(schema)
        if cover_col and cover_col not in props:
            props[cover_col] = to_property("files", cover_upload_id)

    return props


def edited_since_filter(watermark, margin_minutes=1):
    """「watermark 以降に更新されたページ」を取り出す query の filter（Notion の更新日時は分単位のため少し余裕を持たせる）"""
    from datetime import datetime, timedelta

    since = datetime.fromisoformat(watermark.replace("Z", "+00:00")) - timedelta(minutes=margin_minutes)
    return {
        "timestamp": "last_edited_time",
        "last_edited_time": {"on_or_after": since.strftime("%Y-%m-%dT%H:%M:%S.000Z")},
    }


OLDEST_EDIT_FIRST = [{"timestamp": "last_edited_time", "direction": "ascending"}]


def properties_hash(props):
    """Notion へ送る properties の要約（前回送った内容から変わったかの判定用）"""
    text = json.dumps(props, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def export_to_notion(db, client, data_source_id, mapping=None, schema=None, target_items=None, progress_callback=None):
    """ローカル DB のシナリオデータを Notion テーブルのスキーマに合わせて書き出し（新規作成・更新）する。"""
    if schema is None:
        schema = client.schema(data_source_id)
    if not mapping:
        mapping = guess_mapping(schema)
    else:
        guessed = guess_mapping(schema)
        for k, v in guessed.items():
            if not mapping.get(k) or mapping.get(k) not in schema:
                mapping[k] = v

    items = target_items if target_items is not None else db.items_for_notion()
    total = len(items)
    exported_page_ids = []

    for idx, it in enumerate(items):
        title = it.get("title") or "無題"
        if progress_callback:
            progress_callback(idx + 1, total, title)

        export_it = dict(it)
        if str(export_it.get("file_path") or "").startswith("notion://"):
            export_it["file_path"] = ""

        page_id = it.get("notion_page_id")
        thumb_bytes = it.get("thumbnail")
        new_cover_hash = compute_cover_hash(thumb_bytes)
        old_cover_hash = it.get("notion_cover_hash")

        cover_upload_id = None
        if thumb_bytes and (not page_id or new_cover_hash != old_cover_hash):
            try:
                cover_upload_id = client.upload_file(thumb_bytes, filename="cover.jpg", content_type="image/jpeg")
            except Exception as ce:
                print(f"[NotionSync] Cover upload failed for {title}: {ce}")

        props = build_properties(export_it, mapping, schema, cover_upload_id=cover_upload_id)

        if page_id:
            upd_res = client.update_page(page_id, properties=props, cover_upload_id=cover_upload_id)
            n_url = page_notion_url(upd_res) if isinstance(upd_res, dict) else ""
            if cover_upload_id and new_cover_hash:
                db.set_notion_link(it["id"], page_id, cover_hash=new_cover_hash, notion_url=n_url or None)
            elif n_url:
                db.set_notion_link(it["id"], page_id, cover_hash=old_cover_hash, notion_url=n_url)
            exported_page_ids.append(page_id)
        else:
            new_page = client.create_page(data_source_id, props, cover_upload_id=cover_upload_id)
            new_pid = new_page.get("id")
            if new_pid:
                n_url = page_notion_url(new_page)
                db.set_notion_link(
                    it["id"],
                    new_pid,
                    cover_hash=new_cover_hash if cover_upload_id else old_cover_hash,
                    notion_url=n_url or None,
                )
                exported_page_ids.append(new_pid)

    return exported_page_ids


def normalize_path(path):
    p = unicodedata.normalize("NFC", str(path or "")).replace("\\", "/")
    return re.sub(r"/+", "/", p).rstrip("/").lower()


def same_value(old, new, prop_type):
    if old == new:
        return True
    if prop_type == "number":
        n_old, n_new = first_number(old), first_number(new)
        return n_old is not None and n_old == n_new
    return False


# ----------------------------------------------------------------------------
# 書架対照照合（手元データとNotion側の不足分リストアップ）
# ----------------------------------------------------------------------------
def audit_notion_diff(db, client, data_source_id, mapping=None, schema=None, progress_callback=None):
    """手元DBとNotion側の全データを照合し、お互いに足りていないもの（未登録・項目欠落）をリストアップする"""
    if schema is None:
        schema = client.schema(data_source_id)
    if not mapping:
        mapping = guess_mapping(schema)
    else:
        guessed = guess_mapping(schema)
        for k, v in guessed.items():
            if not mapping.get(k):
                mapping[k] = v

    if progress_callback:
        progress_callback("Notionから全シナリオを取得しています...")

    # 1. Notion 側の全ページを取得
    notion_pages = client.query_all(data_source_id, limit=None)

    # 2. 手元 DB の全アイテムを取得
    local_items = db.items_for_notion()

    if progress_callback:
        progress_callback("手元データとNotionデータを照合・比較しています...")

    # 3. Notion データの整形
    notion_data_list = []
    for page in notion_pages:
        pid = page.get("id")
        vals = page_values(page, mapping, schema)
        c_url = page_cover_url(page)
        vals["page_id"] = pid
        vals["cover_url"] = c_url
        vals["last_edited_time"] = page.get("last_edited_time") or ""
        vals["_raw_page"] = page
        notion_data_list.append((pid, vals))

    notion_by_pid = {pid: vals for pid, vals in notion_data_list if pid}
    notion_by_title = {
        (vals.get("title") or "").strip().lower(): (pid, vals)
        for pid, vals in notion_data_list
        if (vals.get("title") or "").strip()
    }

    matched_notion_pids = set()
    matched_local_ids = set()

    local_only = []
    notion_only = []
    field_lacking = []
    in_sync_count = 0

    # 4. 手元アイテム基準で照合
    for it in local_items:
        lid = it["id"]
        pid = it.get("notion_page_id")
        clean_title = (it.get("title") or "").strip().lower()

        matched_vals = None
        matched_pid = None
        if pid and pid in notion_by_pid:
            matched_pid = pid
            matched_vals = notion_by_pid[pid]
        elif clean_title and clean_title in notion_by_title:
            matched_pid, matched_vals = notion_by_title[clean_title]

        if matched_vals:
            matched_local_ids.add(lid)
            matched_notion_pids.add(matched_pid)

            # 項目ごとの不足（欠落）をチェック
            local_missing = []
            notion_missing = []

            field_checks = [
                ("author", "作者"),
                ("system_name", "システム"),
                ("players_text", "プレイ人数"),
                ("duration_text", "所要時間"),
                ("overview", "概要"),
                ("synopsis", "あらすじ"),
                ("source_url", "情報元のURL"),
            ]
            for f_key, label in field_checks:
                l_has = bool(str(it.get(f_key) or "").strip())
                n_has = bool(str(matched_vals.get(f_key) or "").strip())
                if not l_has and n_has:
                    local_missing.append(label)
                elif l_has and not n_has:
                    notion_missing.append(label)

            # タグの不足
            l_tags = set(it.get("tags") or [])
            raw_n_tags = matched_vals.get("tags") or []
            if isinstance(raw_n_tags, str):
                n_tags = set(t.strip() for t in raw_n_tags.split(",") if t.strip())
            else:
                n_tags = set(raw_n_tags)

            missing_in_local_tags = n_tags - l_tags
            if missing_in_local_tags:
                local_missing.append(f"タグ ({', '.join(sorted(missing_in_local_tags))})")

            missing_in_notion_tags = l_tags - n_tags
            if missing_in_notion_tags:
                notion_missing.append(f"タグ ({', '.join(sorted(missing_in_notion_tags))})")

            # 表紙の不足
            l_has_cover = bool(it.get("thumbnail"))
            n_has_cover = bool(matched_vals.get("cover_url"))
            if not l_has_cover and n_has_cover:
                local_missing.append("表紙画像")
            elif l_has_cover and not n_has_cover:
                notion_missing.append("表紙画像")

            if local_missing or notion_missing:
                field_lacking.append({
                    "item_id": lid,
                    "page_id": matched_pid,
                    "title": it.get("title") or matched_vals.get("title") or "無題",
                    "local_item": it,
                    "notion_vals": matched_vals,
                    "local_missing": local_missing,
                    "notion_missing": notion_missing,
                })
            else:
                in_sync_count += 1
        else:
            # 手元にのみ存在（Notion側に未登録）
            local_only.append(it)

    # 5. Notion 側基準で、手元に存在しないものを抽出
    for pid, vals in notion_data_list:
        if pid not in matched_notion_pids:
            notion_only.append(vals)

    return {
        "local_total": len(local_items),
        "notion_total": len(notion_pages),
        "local_only": local_only,
        "notion_only": notion_only,
        "field_lacking": field_lacking,
        "in_sync_count": in_sync_count,
        "mapping": mapping,
        "schema": schema,
    }


def export_single_item_to_notion(db, client, data_source_id, item_id, mapping=None, schema=None):
    """手元の単一アイテムをNotionへ新規作成または更新して書き出す"""
    if schema is None:
        schema = client.schema(data_source_id)
    if not mapping:
        mapping = guess_mapping(schema)

    items = [it for it in db.items_for_notion() if it["id"] == item_id]
    if not items:
        raise ValueError(f"Item ID {item_id} not found in DB.")
    it = items[0]
    title = it.get("title") or "無題"

    export_it = dict(it)
    if str(export_it.get("file_path") or "").startswith("notion://"):
        export_it["file_path"] = ""

    page_id = it.get("notion_page_id")
    thumb_bytes = it.get("thumbnail")
    new_cover_hash = compute_cover_hash(thumb_bytes)
    old_cover_hash = it.get("notion_cover_hash")

    cover_upload_id = None
    if thumb_bytes and (not page_id or new_cover_hash != old_cover_hash):
        try:
            cover_upload_id = client.upload_file(thumb_bytes, filename="cover.jpg", content_type="image/jpeg")
        except Exception as ce:
            print(f"[NotionSync] Single item cover upload failed for {title}: {ce}")

    props = build_properties(export_it, mapping, schema, cover_upload_id=cover_upload_id)

    if page_id:
        upd_res = client.update_page(page_id, properties=props, cover_upload_id=cover_upload_id)
        n_url = page_notion_url(upd_res) if isinstance(upd_res, dict) else ""
        if cover_upload_id and new_cover_hash:
            db.set_notion_link(it["id"], page_id, cover_hash=new_cover_hash, notion_url=n_url or None)
        elif n_url:
            db.set_notion_link(it["id"], page_id, cover_hash=old_cover_hash, notion_url=n_url)
        return page_id
    else:
        new_page = client.create_page(data_source_id, props, cover_upload_id=cover_upload_id)
        new_pid = new_page.get("id")
        if new_pid:
            n_url = page_notion_url(new_page)
            db.set_notion_link(
                it["id"],
                new_pid,
                cover_hash=new_cover_hash if cover_upload_id else old_cover_hash,
                notion_url=n_url or None,
            )
        return new_pid


def import_single_page_from_notion(db, client, page_or_vals, mapping=None, schema=None, data_source_id=None):
    """Notionの単一ページを手元DBへ取り込む"""
    if schema is None and data_source_id:
        schema = client.schema(data_source_id)
    if not mapping and schema:
        mapping = guess_mapping(schema)

    if "_raw_page" in page_or_vals:
        page = page_or_vals["_raw_page"]
        vals = page_or_vals
    elif "properties" in page_or_vals:
        page = page_or_vals
        vals = page_values(page, mapping or {}, schema or {})
    else:
        page = page_or_vals
        vals = page_or_vals

    page_id = page.get("id") or vals.get("page_id")
    cover_url = vals.get("cover_url") or page_cover_url(page)
    thumb_bytes = None
    if cover_url:
        try:
            thumb_bytes = client.download(cover_url)
        except Exception as e:
            print(f"[NotionSync] Single cover download error: {e}")

    last_edited = page.get("last_edited_time") or vals.get("last_edited_time") or ""
    return db.save_or_update_from_notion(page_id, vals, thumbnail_bytes=thumb_bytes, last_edited_time=last_edited)