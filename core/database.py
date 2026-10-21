import sqlite3
import re
import unicodedata
import os
import json

DB_PATH = "catalog.db"

# グローバルタグの初期設定項目と連想色（ユーザー指定: CoC > マダミス > ストプレ > その他 > 未通過 > 通過済み > GM可）
INITIAL_GLOBAL_TAGS = [
    ("CoC", "#1b5e20"),      # 深緑（クトゥルフ神話TRPG・秘術）
    ("マダミス", "#6a1b9a"),  # 深紫（マーダーミステリー・幻惑）
    ("ストプレ", "#0e7490"),  # 深碧（ストーリープレイング・演劇）
    ("その他", "#546e7a"),    # スレートグレー（その他・雑書）
    ("未通過", "#1565c0"),    # 青藍（未通過・夜空）
    ("通過済み", "#9e2a2b"),  # 深紅（通過済み・封蝋）
    ("GM可", "#b3882a"),     # 真鍮金（GM可・古金）
]
GLOBAL_TAG_COLORS = dict(INITIAL_GLOBAL_TAGS)
GLOBAL_TAG_NAMES = {name for name, _ in INITIAL_GLOBAL_TAGS}
GLOBAL_TAG_PRIORITY = ["CoC", "マダミス", "ストプレ", "その他", "未通過", "通過済み", "通過済", "GM可"]


def global_tag_sort_key(tag):
    """グローバルタグをユーザー指定順序（CoC > マダミス > ストプレ > その他 > 未通過 > 通過済み > GM可 > その他ローカル）にソートするためのキー"""
    if isinstance(tag, (list, tuple)):
        if len(tag) > 1 and isinstance(tag[0], int):
            name = tag[1]
        else:
            name = tag[0]
    else:
        name = str(tag)
    clean = (name or "").strip()

    if clean in ("通過済み", "通過済"):
        return (0, 5, clean)
    if clean in GLOBAL_TAG_PRIORITY:
        idx = GLOBAL_TAG_PRIORITY.index(clean)
        return (0, idx, clean)
    return (1, 0, clean)


# 後方互換用エイリアス
BOOKMARK_ITEMS = INITIAL_GLOBAL_TAGS
BOOKMARK_COLORS = GLOBAL_TAG_COLORS

EXCLUDED_AUTO_TAGS = {"trpg"}


def clean_text(text, max_len=None, keep_newlines=False):
    """NULLバイトや不正な不可視制御文字を安全に除去・サニタイズする"""
    if text is None:
        return None
    s = str(text)
    # NULLバイトの除去
    s = s.replace("\x00", "")
    # 制御文字のフィルタリング（改行・タブの保持フラグに対応）
    if keep_newlines:
        s = "".join(c for c in s if c in "\r\n\t" or ord(c) >= 32)
    else:
        s = "".join(c for c in s if ord(c) >= 32 or c == "\t")
    s = s.strip()
    if max_len is not None and max_len > 0:
        s = s[:max_len]
    return s


def to_hiragana(text):
    s = unicodedata.normalize("NFKC", text or "")
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def auto_reading(title):
    t = unicodedata.normalize("NFKC", title or "").strip()
    if not t:
        return None
    for c in t:
        if not ("\u3041" <= c <= "\u3096" or "\u30a1" <= c <= "\u30fa" or c in "ー・  " or c.isascii()):
            return None
    return to_hiragana(t)[:200]


def reading_key(text):
    s = to_hiragana(text).lower()
    s = s.lstrip("「『【［〔（(<《〈\"'・  ")
    base = "".join(c for c in unicodedata.normalize("NFD", s) if c not in "\u3099\u309a")
    return (base, s)


def first_number(text):
    m = re.search(r"\d+", unicodedata.normalize("NFKC", str(text or "")[:100]))
    return int(m.group()) if m else None


def is_excluded_tag(name):
    return unicodedata.normalize("NFKC", name or "").strip().lower() in EXCLUDED_AUTO_TAGS


def _is_murder_mystery(name):
    n = unicodedata.normalize("NFKC", name or "").lower().replace(" ", "")
    return n in ("マダミス", "マーダーミステリー", "murdermystery")


def _is_story_playing(name):
    n = unicodedata.normalize("NFKC", name or "").lower().replace(" ", "")
    return n in ("ストプレ", "ストーリープレイング", "storyplaying")


def canonical_tag(name):
    raw = clean_text(name, max_len=50)
    if not raw:
        return ""
    n = unicodedata.normalize("NFKC", raw).lower().replace(" ", "")
    if "クトゥルフ" in n or "cthulhu" in n or re.fullmatch(r"coc\d*(版|th|rd|ed)?", n):
        return "CoC"
    if _is_murder_mystery(raw):
        return "マダミス"
    if _is_story_playing(raw):
        return "ストプレ"
    if "通過済" in n:
        return "通過済み"

    # 人数タグ正規化（5人以上は「5PL以上」、4人以下は「4PL」「2PL」等）
    # 例: 5PL, 6PL, 7PL, 8PL, 5pl以上, 5｀l以上, 5`l以上, 6人pl
    if re.fullmatch(r"([5-9]|\d{2,})\s*(?:pl|｀l|`l|人pl|人)?\s*(?:以上|\+|〜|～)?", n) and any(
        k in n for k in ["pl", "｀l", "`l", "以上"]
    ):
        return "5PL以上"
    m_under5 = re.fullmatch(r"([1-4])\s*(?:pl|｀l|`l)", n)
    if m_under5:
        return f"{m_under5.group(1)}PL"

    return raw


def canonical_system(name):
    if name is None:
        return None
    raw = clean_text(name, max_len=100)
    if not raw:
        return None
    if _is_murder_mystery(raw):
        return "マーダーミステリー"
    if _is_story_playing(raw):
        return "ストーリープレイング"
    return raw


def generate_player_tags(players_text) -> list[str]:
    """プレイ人数テキストから人数タグを生成する。

    仕様:
    - 5人以上の場合は「5PL以上」
    - 4人以下の場合は従来通り「4PL」「2PL」「1PL」または「2〜4PL」
    - ソロ、KPレス、GMレス等の場合は「GMレス」および「1PL」
    """
    if not players_text:
        return []

    tags = []
    min_p = None
    max_p = None

    def _to_int(v):
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, float):
            import math
            return int(v) if not math.isnan(v) else None
        try:
            norm_v = unicodedata.normalize("NFKC", str(v)).strip()
            # 'NaN' などの非数値を安全に除外
            if norm_v.lower() in ("nan", "none", "null"):
                return None
            m = re.search(r"\d+", norm_v)
            return int(m.group()) if m else None
        except Exception:
            return None

    if isinstance(players_text, dict):
        min_p = _to_int(players_text.get("min"))
        max_p = _to_int(players_text.get("max"))
        raw_text = str(players_text.get("raw_text", "")).lower()
        if any(k in raw_text for k in ["gmレス", "kpレス", "ソロ", "一人", "タイマン"]):
            tags.append("GMレス")
            if min_p is None:
                min_p = 1
                max_p = 1
    elif isinstance(players_text, str):
        raw_text = players_text.lower()
        if any(k in raw_text for k in ["gmレス", "kpレス", "ソロ", "一人", "タイマン"]):
            tags.append("GMレス")

        # GM/KPの人数表記（例: "PL6人＋GM1人", "KP1名"）はプレイヤー人数から除外
        norm = unicodedata.normalize("NFKC", players_text)
        cleaned_for_pl = re.sub(r"(?:gm|kp)\s*\d+\s*(?:人|名)?", "", norm, flags=re.IGNORECASE)

        # 範囲表記の抽出（例: 2〜4人, 2-4人, 3～5名）
        m_range = re.search(r"(\d+)\s*(?:〜|～|~|-|ー|to)\s*(\d+)", cleaned_for_pl)
        if m_range:
            min_p = int(m_range.group(1))
            max_p = int(m_range.group(2))
        else:
            digits = [_to_int(d) for d in re.findall(r"\d+", cleaned_for_pl)]
            digits = [d for d in digits if d is not None]
            if len(digits) == 1:
                min_p = digits[0]
                max_p = digits[0]
            elif len(digits) >= 2:
                min_p = digits[0]
                max_p = digits[1]
            elif any(k in raw_text for k in ["gmレス", "kpレス", "ソロ", "一人", "タイマン"]):
                min_p = 1
                max_p = 1

    if min_p is not None:
        if max_p is None:
            max_p = min_p
        if min_p > max_p:
            min_p, max_p = max_p, min_p

        # 5人以上判定
        if min_p >= 5:
            tags.append("5PL以上")
        elif max_p >= 5:
            tags.append("5PL以上")
            if min_p != max_p:
                tags.append(f"{min_p}〜{max_p}PL")
        else:
            # 4人以下の場合
            if min_p == max_p:
                tags.append(f"{min_p}PL")
            else:
                tags.append(f"{min_p}〜{max_p}PL")

    return tags


SORT_OPTIONS = [
    ("登録が新しい順", "added_desc"),
    ("登録が古い順", "added_asc"),
    ("題名順（あ→ん）", "title_asc"),
    ("題名順（ん→あ）", "title_desc"),
    ("システム順", "system"),
    ("PL人数が少ない順", "players"),
    ("所要時間が短い順", "duration"),
    ("最近開いた順", "opened"),
]


def sort_items(items, key):
    def title_key(it):
        row, kana = it[0], it[1]
        return reading_key(kana or row[2] or "")

    def missing_last(v):
        return (v is None, v if v is not None else 0)

    if key == "added_asc":
        return sorted(items, key=lambda it: it[0][0])
    if key == "title_asc":
        return sorted(items, key=title_key)
    if key == "title_desc":
        return sorted(items, key=title_key, reverse=True)
    if key == "system":
        return sorted(items, key=lambda it: ((it[0][3] or "") == "", reading_key(it[0][3] or ""), title_key(it)))
    if key == "players":
        return sorted(items, key=lambda it: (missing_last(first_number(it[0][4])), title_key(it)))
    if key == "duration":
        return sorted(items, key=lambda it: (missing_last(first_number(it[0][5])), title_key(it)))
    if key == "opened":
        return sorted(items, key=lambda it: (it[2] or "", it[0][0]), reverse=True)
    return sorted(items, key=lambda it: it[0][0], reverse=True)


def init_cover_cache(conn):
    """書架カード用の縮小済み表紙のキャッシュ表を用意する。

    表紙の元画像（items.thumbnail）を毎回読み込み・縮小するのは重いため、表示サイズごとに加工済みの画像を保存しておく。
    元画像が変わった・アイテムが消えたときは、トリガーで自動的に破棄される（どの経路で更新しても古い表紙は残らない）。
    """
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cover_cache (
            item_id INTEGER NOT NULL,
            mode TEXT NOT NULL,
            version INTEGER NOT NULL,
            image BLOB NOT NULL,
            conflict INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (item_id, mode)
        );
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS cover_cache_on_thumbnail_update
        AFTER UPDATE OF thumbnail ON items
        WHEN OLD.thumbnail IS NOT NEW.thumbnail
        BEGIN
            DELETE FROM cover_cache WHERE item_id = NEW.id;
        END;
    """)
    conn.execute("""
        CREATE TRIGGER IF NOT EXISTS cover_cache_on_item_delete
        AFTER DELETE ON items
        BEGIN
            DELETE FROM cover_cache WHERE item_id = OLD.id;
        END;
    """)


class Database:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path, timeout=10.0)
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.init_db()

    def init_db(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    system_name TEXT,
                    players_text TEXT,
                    duration_text TEXT,
                    overview TEXT,
                    synopsis TEXT,
                    thumbnail BLOB,
                    is_last_opened INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            for col in ["overview", "synopsis", "source_url", "title_kana", "last_opened_at", "notion_page_id", "notion_cover_hash",
                        "author", "play_status", "notion_last_edited_time", "notion_url"]:
                try:
                    self.conn.execute(f"ALTER TABLE items ADD COLUMN {col} TEXT;")
                except sqlite3.OperationalError:
                    pass
            try:
                self.conn.execute("ALTER TABLE items ADD COLUMN favorite INTEGER DEFAULT 0;")
            except sqlite3.OperationalError:
                pass
            try:
                self.conn.execute("ALTER TABLE items ADD COLUMN bookmarked INTEGER DEFAULT 0;")
            except sqlite3.OperationalError:
                pass

            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    color TEXT,
                    is_global INTEGER DEFAULT 0
                );
            """)
            try:
                self.conn.execute("ALTER TABLE tags ADD COLUMN color TEXT;")
            except sqlite3.OperationalError:
                pass
            try:
                self.conn.execute("ALTER TABLE tags ADD COLUMN is_global INTEGER DEFAULT 0;")
            except sqlite3.OperationalError:
                pass

            # 「通過済」があれば「通過済み」に統合・移行
            try:
                self.conn.execute("UPDATE tags SET name = '通過済み' WHERE name = '通過済';")
            except sqlite3.IntegrityError:
                old_row = self.conn.execute("SELECT id FROM tags WHERE name = '通過済';").fetchone()
                new_row = self.conn.execute("SELECT id FROM tags WHERE name = '通過済み';").fetchone()
                if old_row and new_row:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO item_tags (item_id, tag_id) SELECT item_id, ? FROM item_tags WHERE tag_id = ?;",
                        (new_row[0], old_row[0]),
                    )
                    self.conn.execute("DELETE FROM tags WHERE id = ?;", (old_row[0],))
            except sqlite3.OperationalError:
                pass

            # グローバルタグの初期登録および色・is_globalフラグの設定
            for tname, tcolor in INITIAL_GLOBAL_TAGS:
                self.conn.execute(
                    "INSERT OR IGNORE INTO tags (name, color, is_global) VALUES (?, ?, 1);",
                    (tname, tcolor),
                )
                self.conn.execute(
                    "UPDATE tags SET is_global = 1, color = COALESCE(NULLIF(color, ''), ?) WHERE name = ?;",
                    (tcolor, tname),
                )

            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS item_tags (
                    item_id INTEGER,
                    tag_id INTEGER,
                    PRIMARY KEY (item_id, tag_id),
                    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE,
                    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
                );
            """)

            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS play_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item_id INTEGER NOT NULL,
                    session_date TEXT,
                    role TEXT,
                    party_members TEXT,
                    character_name TEXT,
                    result TEXT,
                    memo TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
                );
            """)

            init_cover_cache(self.conn)

    def save_item(self, file_path, title, system_name, players_text, duration_text, overview, synopsis, thumbnail_bytes):
        file_path = clean_text(file_path, max_len=1000)
        title = clean_text(title, max_len=200) or "無題のシナリオ"
        system_name = canonical_system(system_name)
        players_text = clean_text(players_text, max_len=50)
        duration_text = clean_text(duration_text, max_len=50)
        overview = clean_text(overview, max_len=10000, keep_newlines=True)
        synopsis = clean_text(synopsis, max_len=10000, keep_newlines=True)
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO items (file_path, title, system_name, players_text, duration_text, overview, synopsis, thumbnail)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    title = excluded.title,
                    system_name = excluded.system_name,
                    players_text = excluded.players_text,
                    duration_text = excluded.duration_text,
                    overview = excluded.overview,
                    synopsis = excluded.synopsis,
                    thumbnail = excluded.thumbnail;
            """, (file_path, title, system_name, players_text, duration_text, overview, synopsis, thumbnail_bytes))
            cursor.execute("SELECT id FROM items WHERE file_path = ?;", (file_path,))
            return cursor.fetchone()[0]

    def update_item_cover(self, item_id, thumbnail_bytes):
        with self.conn:
            self.conn.execute("UPDATE items SET thumbnail = ? WHERE id = ?;", (thumbnail_bytes, item_id))

    def delete_item(self, item_id):
        """指定したシナリオアイテムおよび関連タグをデータベースから安全に削除する"""
        with self.conn:
            self.conn.execute("DELETE FROM item_tags WHERE item_id = ?;", (item_id,))
            self.conn.execute("DELETE FROM items WHERE id = ?;", (item_id,))

    def update_item_meta(self, item_id, title, system_name, players_text, duration_text, title_kana=None, author=None):
        system_name = canonical_system(system_name)
        with self.conn:
            self.conn.execute("""
                UPDATE items SET
                    title = ?,
                    title_kana = ?,
                    system_name = ?,
                    players_text = ?,
                    duration_text = ?,
                    author = ?
                WHERE id = ?;
            """, (title, title_kana, system_name, players_text, duration_text, author, item_id))

    def get_author(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT author FROM items WHERE id = ?;", (item_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def set_favorite(self, item_id, on):
        with self.conn:
            self.conn.execute("UPDATE items SET favorite = ? WHERE id = ?;", (1 if on else 0, item_id))

    def get_favorite(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT favorite FROM items WHERE id = ?;", (item_id,))
        row = cursor.fetchone()
        return bool(row[0]) if row and row[0] is not None else False

    def set_bookmarked(self, item_id, on):
        with self.conn:
            self.conn.execute("UPDATE items SET bookmarked = ? WHERE id = ?;", (1 if on else 0, item_id))

    def get_bookmarked(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT bookmarked FROM items WHERE id = ?;", (item_id,))
        row = cursor.fetchone()
        return bool(row[0]) if row and row[0] is not None else False

    def toggle_bookmarked(self, item_id):
        cur = self.get_bookmarked(item_id)
        new_val = not cur
        self.set_bookmarked(item_id, new_val)
        return new_val

    def set_play_status(self, item_id, status):
        with self.conn:
            self.conn.execute("UPDATE items SET play_status = ? WHERE id = ?;", (status or None, item_id))

    def all_records(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, file_path, title, title_kana, system_name, players_text, duration_text, overview, synopsis,
                   thumbnail, author, favorite, play_status, last_opened_at
            FROM items ORDER BY id DESC;
        """)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        cursor.execute("""
            SELECT it.item_id, t.id, t.name FROM item_tags it JOIN tags t ON t.id = it.tag_id ORDER BY t.name;
        """)
        tags = {}
        for item_id, tid, name in cursor.fetchall():
            tags.setdefault(item_id, []).append((tid, name))
        for r in rows:
            r["tags"] = tags.get(r["id"], [])
            r["favorite"] = bool(r["favorite"])
            r["play_status"] = r["play_status"] or ""
        return rows

    def get_title_kana(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT title_kana FROM items WHERE id = ?;", (item_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def set_title_kana(self, item_id, kana):
        with self.conn:
            self.conn.execute("UPDATE items SET title_kana = ? WHERE id = ?;", (kana or None, item_id))

    def pop_legacy_settings(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'settings';")
        if not cursor.fetchone():
            return {}
        cursor.execute("SELECT key, value FROM settings;")
        values = dict(cursor.fetchall())
        with self.conn:
            self.conn.execute("DROP TABLE settings;")
        return values

    def items_for_notion(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, file_path, title, title_kana, author, system_name, players_text, duration_text, overview, synopsis,
                   source_url, thumbnail, notion_page_id, notion_cover_hash, notion_last_edited_time
            FROM items ORDER BY id;
        """)
        cols = [d[0] for d in cursor.description]
        rows = [dict(zip(cols, r)) for r in cursor.fetchall()]
        for r in rows:
            r["tags"] = [t[1] for t in self.get_item_tags(r["id"])]
        return rows

    def set_notion_link(self, item_id, page_id, cover_hash=None, notion_url=None):
        with self.conn:
            if cover_hash is None:
                self.conn.execute(
                    "UPDATE items SET notion_page_id = ?, notion_url = COALESCE(?, notion_url) WHERE id = ?;",
                    (page_id, notion_url, item_id),
                )
            else:
                self.conn.execute(
                    "UPDATE items SET notion_page_id = ?, notion_cover_hash = ?, notion_url = COALESCE(?, notion_url) WHERE id = ?;",
                    (page_id, cover_hash, notion_url, item_id),
                )

    def get_notion_page_id(self, item_id):
        """指定アイテムのNotionページIDを取得する"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT notion_page_id FROM items WHERE id = ?;", (item_id,))
        row = cursor.fetchone()
        return row[0] if row and row[0] else ""

    def get_notion_url(self, item_id):
        """指定アイテムのNotion共有グローバルURLを取得する。
        notion_url カラムの値があればそれを優先し、無ければ notion_page_id または file_path (notion://...)
        から共有可能なグローバルURLを構築して返す。
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT notion_url, notion_page_id, file_path FROM items WHERE id = ?;", (item_id,))
        row = cursor.fetchone()
        if not row:
            return ""
        n_url, page_id, file_path = row
        if n_url and str(n_url).strip():
            return str(n_url).strip()
        pid = (page_id or "").strip()
        if not pid and file_path and file_path.startswith("notion://"):
            pid = file_path.replace("notion://", "").strip()
        if pid:
            clean_id = pid.replace("-", "").strip()
            return f"https://www.notion.so/{clean_id}"
        return ""

    def set_notion_url(self, item_id, notion_url):
        """指定アイテムのNotion共有URLを設定する"""
        clean_u = clean_text(notion_url, max_len=2000)
        with self.conn:
            self.conn.execute("UPDATE items SET notion_url = ? WHERE id = ?;", (clean_u, item_id))

    def find_existing_item_for_notion(self, page_id=None, title=None, file_path=None):
        """Notion取り込み時に対応する既存レコード（page_id一致、file_path一致、またはtitle一致）を探索して辞書で返す"""
        cursor = self.conn.cursor()
        row = None
        if page_id:
            cursor.execute("""
                SELECT id, file_path, title, author, system_name, players_text, duration_text,
                       overview, synopsis, thumbnail, notion_page_id, notion_cover_hash, notion_last_edited_time,
                       notion_url
                FROM items WHERE notion_page_id = ?;
            """, (page_id,))
            row = cursor.fetchone()

        if not row and file_path:
            cursor.execute("""
                SELECT id, file_path, title, author, system_name, players_text, duration_text,
                       overview, synopsis, thumbnail, notion_page_id, notion_cover_hash, notion_last_edited_time,
                       notion_url
                FROM items WHERE file_path = ?;
            """, (file_path,))
            row = cursor.fetchone()

        if not row and title:
            clean_t = clean_text(title, max_len=200)
            if clean_t:
                cursor.execute("""
                    SELECT id, file_path, title, author, system_name, players_text, duration_text,
                           overview, synopsis, thumbnail, notion_page_id, notion_cover_hash, notion_last_edited_time,
                           notion_url
                    FROM items WHERE title = ?;
                """, (clean_t,))
                row = cursor.fetchone()

        if not row:
            return None

        item_id = row[0]
        tags = [t[1] for t in self.get_item_tags(item_id)]
        return {
            "id": row[0],
            "file_path": row[1] or "",
            "title": row[2] or "",
            "author": row[3] or "",
            "system_name": row[4] or "",
            "players_text": row[5] or "",
            "duration_text": row[6] or "",
            "overview": row[7] or "",
            "synopsis": row[8] or "",
            "thumbnail": row[9],
            "notion_page_id": row[10] or "",
            "notion_cover_hash": row[11] or "",
            "notion_last_edited_time": row[12] or "",
            "notion_url": row[13] or "",
            "tags": tags,
        }

    def get_item_detail_dict(self, item_id: int):
        """アイテムの詳細情報を辞書形式で取得する"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, file_path, title, author, system_name, players_text, duration_text,
                   overview, synopsis, thumbnail, source_url, title_kana, notion_page_id,
                   notion_cover_hash, notion_last_edited_time, notion_url
            FROM items WHERE id = ?;
        """, (item_id,))
        row = cursor.fetchone()
        if not row:
            return None
        tags = [t[1] for t in self.get_item_tags(item_id)]
        return {
            "id": row[0],
            "file_path": row[1] or "",
            "title": row[2] or "",
            "author": row[3] or "",
            "system": row[4] or "",
            "system_name": row[4] or "",
            "players": row[5] or "",
            "players_text": row[5] or "",
            "duration": row[6] or "",
            "duration_text": row[6] or "",
            "overview": row[7] or "",
            "synopsis": row[8] or "",
            "thumbnail_bytes": row[9],
            "thumbnail": row[9],
            "source_url": row[10] or "",
            "title_kana": row[11] or "",
            "notion_page_id": row[12] or "",
            "notion_cover_hash": row[13] or "",
            "notion_last_edited_time": row[14] or "",
            "notion_url": row[15] or "",
            "tags": tags,
        }

    def save_or_update_from_notion(self, page_id, values, thumbnail_bytes=None, last_edited_time=None):
        """Notionから読み込んだ1ページ分のデータ（シナリオ名、表紙、タグ等）をDBへ登録または更新する"""
        import hashlib

        page_id = clean_text(page_id, max_len=100) or ""
        raw_fp = clean_text(values.get("file_path"), max_len=1000)
        file_path = raw_fp if raw_fp else f"notion://{page_id}"

        title = clean_text(values.get("title"), max_len=200) or "無題のシナリオ"
        title_kana = clean_text(values.get("title_kana"), max_len=200) or auto_reading(title)
        author = clean_text(values.get("author"), max_len=100)
        system_name = canonical_system(values.get("system_name"))
        players_text = clean_text(values.get("players_text"), max_len=50)
        duration_text = clean_text(values.get("duration_text"), max_len=50)
        overview = clean_text(values.get("overview"), max_len=10000, keep_newlines=True)
        synopsis = clean_text(values.get("synopsis"), max_len=10000, keep_newlines=True)
        source_url = clean_text(values.get("source_url"), max_len=1000)
        notion_url = clean_text(values.get("notion_url"), max_len=2000)
        cover_hash = hashlib.sha256(thumbnail_bytes).hexdigest()[:16] if thumbnail_bytes else None

        cursor = self.conn.cursor()
        existing_row = None
        if page_id:
            cursor.execute("SELECT id, file_path, thumbnail FROM items WHERE notion_page_id = ?;", (page_id,))
            existing_row = cursor.fetchone()
        if not existing_row and raw_fp:
            cursor.execute("SELECT id, file_path, thumbnail FROM items WHERE file_path = ?;", (raw_fp,))
            existing_row = cursor.fetchone()
        if not existing_row and title and title != "無題のシナリオ":
            cursor.execute("SELECT id, file_path, thumbnail FROM items WHERE title = ?;", (title,))
            existing_row = cursor.fetchone()

        if existing_row:
            item_id, old_fp, old_thumb = existing_row
            final_fp = raw_fp if raw_fp else old_fp
            final_thumb = thumbnail_bytes if thumbnail_bytes is not None else old_thumb
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE items SET
                        file_path = ?,
                        title = ?,
                        title_kana = COALESCE(?, title_kana),
                        author = COALESCE(?, author),
                        system_name = COALESCE(?, system_name),
                        players_text = COALESCE(?, players_text),
                        duration_text = COALESCE(?, duration_text),
                        overview = COALESCE(?, overview),
                        synopsis = COALESCE(?, synopsis),
                        source_url = COALESCE(?, source_url),
                        thumbnail = ?,
                        notion_page_id = ?,
                        notion_cover_hash = COALESCE(?, notion_cover_hash),
                        notion_last_edited_time = COALESCE(?, notion_last_edited_time),
                        notion_url = COALESCE(?, notion_url)
                    WHERE id = ?;
                    """,
                    (
                        final_fp,
                        title,
                        title_kana,
                        author,
                        system_name,
                        players_text,
                        duration_text,
                        overview,
                        synopsis,
                        source_url,
                        final_thumb,
                        page_id or None,
                        cover_hash,
                        last_edited_time,
                        notion_url,
                        item_id,
                    ),
                )
        else:
            item_id = self.save_item(
                file_path=file_path,
                title=title,
                system_name=system_name,
                players_text=players_text,
                duration_text=duration_text,
                overview=overview,
                synopsis=synopsis,
                thumbnail_bytes=thumbnail_bytes,
            )
            with self.conn:
                self.conn.execute(
                    """
                    UPDATE items SET
                        title_kana = ?,
                        author = ?,
                        source_url = ?,
                        notion_page_id = ?,
                        notion_cover_hash = ?,
                        notion_last_edited_time = ?,
                        notion_url = ?
                    WHERE id = ?;
                    """,
                    (title_kana, author, source_url, page_id or None, cover_hash, last_edited_time, notion_url, item_id),
                )

        # タグデータの登録・紐付け
        all_tags_to_apply = []

        if "tags" in values and values["tags"] is not None:
            # Notionからタグが提供されている場合、Notion側のタグセットを正として反映する
            raw_tags = values["tags"]
            if isinstance(raw_tags, str):
                raw_tags = [v.strip() for v in re.split(r"[、,]", raw_tags) if v.strip()]
            for t in raw_tags:
                clean_t = str(t).strip()
                if not clean_t:
                    continue
                # canonical_tag で人数タグ（5人以上は「5PL以上」、4人以下は「4PL」「2PL」等）や「CoC」等に正規化
                canon = canonical_tag(clean_t)
                if canon and canon not in all_tags_to_apply:
                    all_tags_to_apply.append(canon)
        else:
            # Notion側にタグ列がない/未指定の場合
            if existing_row:
                current_tags = [t[1] for t in self.get_item_tags(item_id)]
                all_tags_to_apply.extend(current_tags)
            else:
                p_text = values.get("players_text") or values.get("players")
                if p_text:
                    for pt in generate_player_tags(p_text):
                        if pt not in all_tags_to_apply:
                            all_tags_to_apply.append(pt)
                s_name = values.get("system_name") or values.get("system")
                if s_name:
                    clean_s = str(s_name).strip()
                    if clean_s and clean_s not in all_tags_to_apply:
                        all_tags_to_apply.append(clean_s)

        # DBへタグを登録・紐付け
        tag_ids = []
        for t in all_tags_to_apply:
            if is_excluded_tag(t):
                continue
            tid = self.add_tag(t)
            if tid and tid not in tag_ids:
                tag_ids.append(tid)
        self.set_item_tags(item_id, tag_ids)

        return item_id

    def update_item(self, item_id, **kwargs):
        """update_item_all の後方互換用エイリアス"""
        return self.update_item_all(item_id, **kwargs)

    def find_existing_item_for_web(self, url, title=None):
        """Web取り込み時に対象となる既存アイテム（URL一致、ベースURL一致、またはタイトル一致）を探索して (id, file_path, thumbnail, title, source_url) を返す"""
        clean_u = clean_text(url, max_len=1000)
        cursor = self.conn.cursor()
        existing_row = None

        # 1. source_url または file_path 完全一致
        if clean_u:
            cursor.execute("SELECT id, file_path, thumbnail, title, source_url FROM items WHERE source_url = ? OR file_path = ?;", (clean_u, clean_u))
            existing_row = cursor.fetchone()

        # 2. クエリパラメータを除去したベースURL一致
        if not existing_row and clean_u and "?" in clean_u:
            base_url = clean_u.split("?")[0].rstrip("/")
            cursor.execute("SELECT id, file_path, thumbnail, title, source_url FROM items WHERE source_url LIKE ? OR file_path LIKE ?;", (f"{base_url}%", f"{base_url}%"))
            existing_row = cursor.fetchone()

        # 3. タイトル完全一致（無題でない場合）
        clean_t = clean_text(title, max_len=200)
        if not existing_row and clean_t and clean_t != "無題のシナリオ":
            cursor.execute("SELECT id, file_path, thumbnail, title, source_url FROM items WHERE title = ?;", (clean_t,))
            existing_row = cursor.fetchone()

        # 4. タイトル正規化（空白・記号トリム、NFKC）一致
        if not existing_row and clean_t and clean_t != "無題のシナリオ":
            norm_target = unicodedata.normalize("NFKC", clean_t).strip().lower()
            cursor.execute("SELECT id, file_path, thumbnail, title, source_url FROM items;")
            for r in cursor.fetchall():
                if r[3] and unicodedata.normalize("NFKC", r[3]).strip().lower() == norm_target:
                    existing_row = r
                    break

        return existing_row

    def save_or_update_from_web(self, url, data, selected_fields=None, existing_item_id=None):
        """Webサイトから取得したデータ（タイトル、作者、表紙、あらすじ等）をDBへ登録または更新する。
        selected_fields が指定されている場合は選択された項目のみを更新する。
        """
        title = clean_text(data.get("title"), max_len=200) or "無題のシナリオ"
        system_name = canonical_system(data.get("system") or data.get("system_name"))
        players_text = clean_text(data.get("players") or data.get("players_text"), max_len=50)
        duration_text = clean_text(data.get("duration") or data.get("duration_text"), max_len=50)
        overview = clean_text(data.get("overview"), max_len=10000, keep_newlines=True)
        synopsis = clean_text(data.get("synopsis"), max_len=10000, keep_newlines=True)
        author = clean_text(data.get("author"), max_len=100)
        title_kana = clean_text(data.get("title_kana"), max_len=200) or auto_reading(title)
        thumb_bytes = data.get("image_bytes") or data.get("thumbnail_bytes")
        clean_u = clean_text(url, max_len=1000)

        existing_row = None
        if existing_item_id:
            cursor = self.conn.cursor()
            cursor.execute("SELECT id, file_path, thumbnail, title, source_url FROM items WHERE id = ?;", (existing_item_id,))
            existing_row = cursor.fetchone()
        if not existing_row:
            existing_row = self.find_existing_item_for_web(clean_u, title)

        if existing_row:
            item_id, old_fp, old_thumb, old_title, old_url = existing_row
            # 既存のfile_pathがURLでなくローカルファイル（PDF/ZIP等）ならそれを温存
            final_fp = old_fp if (old_fp and not old_fp.startswith("http://") and not old_fp.startswith("https://") and not old_fp.startswith("notion://")) else clean_u
            final_url = clean_u or old_url

            fields_to_update = {}
            if selected_fields is None or "title" in selected_fields:
                fields_to_update["title"] = title
                fields_to_update["title_kana"] = title_kana
            if selected_fields is None or "system" in selected_fields:
                fields_to_update["system_name"] = system_name
            if selected_fields is None or "players" in selected_fields:
                fields_to_update["players_text"] = players_text
            if selected_fields is None or "duration" in selected_fields:
                fields_to_update["duration_text"] = duration_text
            if selected_fields is None or "overview" in selected_fields:
                fields_to_update["overview"] = overview
            if selected_fields is None or "synopsis" in selected_fields:
                fields_to_update["synopsis"] = synopsis
            if selected_fields is None or "author" in selected_fields:
                fields_to_update["author"] = author
            if selected_fields is None or "cover" in selected_fields:
                if thumb_bytes is not None:
                    fields_to_update["thumbnail_bytes"] = thumb_bytes

            fields_to_update["url"] = final_url

            self.update_item_all(item_id=item_id, **fields_to_update)

            # file_path の更新（もし必要なら）
            if final_fp != old_fp:
                with self.conn:
                    self.conn.execute("UPDATE items SET file_path = ? WHERE id = ?;", (final_fp, item_id))
        else:
            init_title = title if (selected_fields is None or "title" in selected_fields) else "無題のシナリオ"
            init_sys = system_name if (selected_fields is None or "system" in selected_fields) else None
            init_players = players_text if (selected_fields is None or "players" in selected_fields) else ""
            init_dur = duration_text if (selected_fields is None or "duration" in selected_fields) else ""
            init_ov = overview if (selected_fields is None or "overview" in selected_fields) else ""
            init_syn = synopsis if (selected_fields is None or "synopsis" in selected_fields) else ""
            init_thumb = thumb_bytes if (selected_fields is None or "cover" in selected_fields) else None
            init_author = author if (selected_fields is None or "author" in selected_fields) else ""
            init_kana = title_kana if (selected_fields is None or "title" in selected_fields) else auto_reading(init_title)

            item_id = self.save_item(
                file_path=clean_u,
                title=init_title,
                system_name=init_sys,
                players_text=init_players,
                duration_text=init_dur,
                overview=init_ov,
                synopsis=init_syn,
                thumbnail_bytes=init_thumb,
            )
            with self.conn:
                self.conn.execute(
                    "UPDATE items SET source_url = ?, author = ?, title_kana = ? WHERE id = ?;",
                    (clean_u, init_author, init_kana, item_id),
                )

        # システム名・人数からタグを自動登録
        if selected_fields is None or "tags" in selected_fields:
            tags = []
            if system_name:
                tags.append(canonical_tag(system_name))
            if players_text:
                tags.extend(generate_player_tags(players_text))

            tag_ids = [self.add_tag(t) for t in tags if t]
            tag_ids = [tid for tid in tag_ids if tid]
            if tag_ids:
                current_tags = {t[0] for t in self.get_item_tags(item_id)}
                all_tags = list(current_tags | set(tag_ids))
                self.set_item_tags(item_id, all_tags)

        it = self.get_item(item_id)
        final_title = it[2] if it else title
        return item_id, final_title

    def get_source_url(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT source_url FROM items WHERE id = ?;", (item_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def set_source_url(self, item_id, url):
        with self.conn:
            self.conn.execute("UPDATE items SET source_url = ? WHERE id = ?;", (url or None, item_id))

    def update_item_fields(self, item_id, fields):
        allowed = {"title", "system_name", "players_text", "duration_text", "overview", "synopsis", "thumbnail", "source_url", "author"}
        cols = [c for c in fields if c in allowed]
        if not cols:
            return
        if "system_name" in fields:
            fields = {**fields, "system_name": canonical_system(fields["system_name"])}
        with self.conn:
            self.conn.execute(
                f"UPDATE items SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?;",
                (*[fields[c] for c in cols], item_id),
            )

    def add_tags_to_item(self, item_id, names):
        current = [t[0] for t in self.get_item_tags(item_id)]
        for name in names:
            tid = self.add_tag(name)
            if tid and tid not in current:
                current.append(tid)
        self.set_item_tags(item_id, current)

    def update_item_texts(self, item_id, overview, synopsis):
        with self.conn:
            self.conn.execute("UPDATE items SET overview = ?, synopsis = ? WHERE id = ?;", (overview, synopsis, item_id))

    def get_items(self):
        """全シナリオアイテムの基本情報をタプルリストで取得する"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, file_path, title, system_name, players_text, duration_text, overview, synopsis, thumbnail, favorite, bookmarked
            FROM items ORDER BY id DESC;
        """)
        return cursor.fetchall()

    def get_item_summaries(self):
        """書架表示用に get_items() と同じ並びで全件を取得する（表紙本体は読まない）。

        9番目の列には表紙のバイト数（無ければ None）が入る。表紙は get_thumbnail() で個別に読む。
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, file_path, title, system_name, players_text, duration_text, overview, synopsis,
                   length(thumbnail), favorite, bookmarked
            FROM items ORDER BY id DESC;
        """)
        return cursor.fetchall()

    def get_thumbnail(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute("SELECT thumbnail FROM items WHERE id = ?;", (item_id,))
        row = cursor.fetchone()
        return row[0] if row else None

    def get_item(self, item_id):
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, file_path, title, system_name, players_text, duration_text, overview, synopsis, thumbnail, favorite, bookmarked
            FROM items WHERE id = ?;
        """, (item_id,))
        return cursor.fetchone()

    def update_item_all(self, item_id, title=None, system_name=None, players_text=None,
                        duration_text=None, overview=None, synopsis=None, author=None,
                        url=None, tags=None, title_kana=None, thumbnail_bytes=None):
        """シナリオの各種情報を一括更新するトランザクションヘルパー"""
        with self.conn:
            fields = {}
            if title is not None:
                fields["title"] = clean_text(title, max_len=200)
            if system_name is not None:
                fields["system_name"] = canonical_system(system_name)
            if players_text is not None:
                fields["players_text"] = clean_text(players_text, max_len=50)
            if duration_text is not None:
                fields["duration_text"] = clean_text(duration_text, max_len=50)
            if overview is not None:
                fields["overview"] = clean_text(overview, max_len=10000, keep_newlines=True)
            if synopsis is not None:
                fields["synopsis"] = clean_text(synopsis, max_len=10000, keep_newlines=True)
            if author is not None:
                fields["author"] = clean_text(author, max_len=100)
            if url is not None:
                fields["source_url"] = clean_text(url, max_len=1000)
            if title_kana is not None:
                fields["title_kana"] = clean_text(title_kana, max_len=200)
            if thumbnail_bytes is not None:
                fields["thumbnail"] = thumbnail_bytes

            if fields:
                cols = list(fields.keys())
                vals = [fields[c] for c in cols]
                sql = f"UPDATE items SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?;"
                self.conn.execute(sql, (*vals, item_id))

            if tags is not None:
                tag_ids = []
                for t in tags:
                    tid = self.add_tag(t)
                    if tid:
                        tag_ids.append(tid)
                self.set_item_tags(item_id, tag_ids)

    def set_last_opened(self, item_id):
        with self.conn:
            self.conn.execute("UPDATE items SET is_last_opened = 0;")
            self.conn.execute(
                "UPDATE items SET is_last_opened = 1, last_opened_at = strftime('%Y-%m-%d %H:%M:%f', 'now') WHERE id = ?;",
                (item_id,),
            )

    def get_last_opened(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, file_path, title FROM items WHERE is_last_opened = 1 LIMIT 1;")
        return cursor.fetchone()

    def get_tags(self, is_global=None):
        """全タグの (id, name, color, is_global) リストを取得する"""
        cursor = self.conn.cursor()
        if is_global is None:
            cursor.execute("SELECT id, name, color, is_global FROM tags ORDER BY is_global DESC, name ASC;")
        else:
            cursor.execute(
                "SELECT id, name, color, is_global FROM tags WHERE is_global = ? ORDER BY id ASC, name ASC;",
                (1 if is_global else 0,),
            )
        return cursor.fetchall()

    def get_global_tags(self):
        """グローバルタグ一覧を優先順序（CoC > マダミス > 未通過 > 通過済み > GM可）で取得する"""
        tags = self.get_tags(is_global=True)
        return sorted(tags, key=global_tag_sort_key)

    def get_local_tags(self):
        """ローカルタグ一覧を取得する"""
        return self.get_tags(is_global=False)

    def get_tags_with_counts(self, is_global=None):
        """全タグの (id, name, count, color, is_global) リストを取得する（使用件数の多い順）"""
        cursor = self.conn.cursor()
        query = """
            SELECT t.id, t.name, COUNT(it.item_id) as count, t.color, t.is_global
            FROM tags t
            LEFT JOIN item_tags it ON it.tag_id = t.id
        """
        params = ()
        if is_global is not None:
            query += " WHERE t.is_global = ?"
            params = (1 if is_global else 0,)
        query += " GROUP BY t.id, t.name, t.color, t.is_global ORDER BY count DESC, t.name ASC;"
        cursor.execute(query, params)
        return cursor.fetchall()

    def add_tag(self, name, color=None, is_global=None):
        name = canonical_tag(name)
        if not name:
            return None
        if is_global is None:
            is_global = 1 if name in GLOBAL_TAG_NAMES else 0
        if not color:
            color = GLOBAL_TAG_COLORS.get(name, "#546e7a")
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO tags (name, color, is_global) VALUES (?, ?, ?);",
                (name, color, 1 if is_global else 0),
            )
            cursor.execute("SELECT id FROM tags WHERE name = ?;", (name,))
            row = cursor.fetchone()
            return row[0] if row else None

    def delete_tag(self, tag_id):
        with self.conn:
            self.conn.execute("DELETE FROM tags WHERE id = ?;", (tag_id,))

    def get_tag_by_name(self, name):
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, name, color, is_global FROM tags WHERE name = ?;", (str(name).strip(),))
        return cursor.fetchone()

    def rename_tag(self, tag_id, new_name):
        return self.update_tag(tag_id, new_name=new_name)

    def update_tag(self, tag_id, new_name=None, new_color=None, is_global=None):
        """タグの名前、色、およびグローバル区分を更新する"""
        with self.conn:
            if new_name is not None:
                new_name = canonical_tag(new_name)
                if not new_name:
                    return None
                existing = self.get_tag_by_name(new_name)
                if existing and existing[0] != tag_id:
                    # 統合処理
                    self.conn.execute(
                        "INSERT OR IGNORE INTO item_tags (item_id, tag_id) SELECT item_id, ? FROM item_tags WHERE tag_id = ?;",
                        (existing[0], tag_id),
                    )
                    self.conn.execute("DELETE FROM tags WHERE id = ?;", (tag_id,))
                    if new_color is not None:
                        self.conn.execute("UPDATE tags SET color = ? WHERE id = ?;", (new_color, existing[0]))
                    if is_global is not None:
                        self.conn.execute("UPDATE tags SET is_global = ? WHERE id = ?;", (1 if is_global else 0, existing[0]))
                    return existing[0]
                else:
                    self.conn.execute("UPDATE tags SET name = ? WHERE id = ?;", (new_name, tag_id))

            if new_color is not None:
                self.conn.execute("UPDATE tags SET color = ? WHERE id = ?;", (new_color, tag_id))

            if is_global is not None:
                self.conn.execute("UPDATE tags SET is_global = ? WHERE id = ?;", (1 if is_global else 0, tag_id))

            return tag_id

    def normalize_tags(self):
        for t in self.get_tags():
            tid, name = t[0], t[1]
            canonical = canonical_tag(name)
            if canonical != name:
                self.rename_tag(tid, canonical)
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, system_name FROM items WHERE system_name IS NOT NULL;")
        with self.conn:
            for item_id, system_name in cursor.fetchall():
                canonical = canonical_system(system_name)
                if canonical != system_name:
                    self.conn.execute("UPDATE items SET system_name = ? WHERE id = ?;", (canonical, item_id))

    def get_tag_usage(self):
        cursor = self.conn.cursor()
        cursor.execute("SELECT tag_id, COUNT(*) FROM item_tags GROUP BY tag_id;")
        return dict(cursor.fetchall())

    def get_item_tags(self, item_id, is_global=None):
        cursor = self.conn.cursor()
        query = """
            SELECT t.id, t.name, t.color, t.is_global FROM tags t
            JOIN item_tags it ON t.id = it.tag_id
            WHERE it.item_id = ?
        """
        params = [item_id]
        if is_global is not None:
            query += " AND t.is_global = ?"
            params.append(1 if is_global else 0)
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()

        def item_tag_sort_key(row):
            # row: (id, name, color, is_global)
            is_glob = bool(row[3])
            if is_glob:
                return (0,) + global_tag_sort_key(row[1])
            return (1, 0, row[1])

        return sorted(rows, key=item_tag_sort_key)

    def get_all_item_global_tags(self):
        """全アイテムのグローバルタグを優先順序でソートした {item_id: [(id, name, color), ...]} 辞書で一括取得"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT it.item_id, t.id, t.name, t.color
            FROM item_tags it
            JOIN tags t ON t.id = it.tag_id
            WHERE t.is_global = 1;
        """)
        res = {}
        for item_id, tid, tname, tcolor in cursor.fetchall():
            if item_id not in res:
                res[item_id] = []
            res[item_id].append((tid, tname, tcolor))
        for item_id in res:
            res[item_id].sort(key=global_tag_sort_key)
        return res

    def get_all_item_local_tags(self):
        """全アイテムのローカルタグを {item_id: [(id, name, color), ...]} 辞書で一括取得"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT it.item_id, t.id, t.name, t.color
            FROM item_tags it
            JOIN tags t ON t.id = it.tag_id
            WHERE t.is_global = 0
            ORDER BY t.id ASC, t.name ASC;
        """)
        res = {}
        for item_id, tid, tname, tcolor in cursor.fetchall():
            if item_id not in res:
                res[item_id] = []
            res[item_id].append((tid, tname, tcolor))
        return res

    def get_all_item_tags(self):
        """全アイテムの全タグを {item_id: [(id, name, color, is_global), ...]} 辞書で一括取得"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT it.item_id, t.id, t.name, t.color, t.is_global
            FROM item_tags it
            JOIN tags t ON t.id = it.tag_id
            ORDER BY t.is_global DESC, t.name ASC;
        """)
        res = {}
        for item_id, tid, tname, tcolor, is_glob in cursor.fetchall():
            if item_id not in res:
                res[item_id] = []
            res[item_id].append((tid, tname, tcolor, is_glob))
        return res

    def set_item_tags(self, item_id, tag_ids):
        valid_ids = [tid for tid in tag_ids if isinstance(tid, int)]
        with self.conn:
            self.conn.execute("DELETE FROM item_tags WHERE item_id = ?;", (item_id,))
            for tid in valid_ids:
                self.conn.execute("INSERT INTO item_tags (item_id, tag_id) VALUES (?, ?);", (item_id, tid))

    def toggle_item_tag(self, item_id, tag_name, enabled=None):
        """指定したタグの付与/解除を切り替える（enabled が指定されていればその状態に設定）"""
        current_tags = {t[1]: t[0] for t in self.get_item_tags(item_id)}
        tid = self.add_tag(tag_name)
        if not tid:
            return False
        with self.conn:
            has_tag = tag_name in current_tags
            new_state = (not has_tag) if enabled is None else bool(enabled)
            if new_state and not has_tag:
                self.conn.execute("INSERT OR IGNORE INTO item_tags (item_id, tag_id) VALUES (?, ?);", (item_id, tid))
            elif not new_state and has_tag:
                self.conn.execute("DELETE FROM item_tags WHERE item_id = ? AND tag_id = ?;", (item_id, tid))
            return new_state

    # -------------------------------------------------------------------------
    # 冒険録（プレイ履歴・セッション記録）
    # -------------------------------------------------------------------------
    def add_play_log(self, item_id, session_date="", role="PL", party_members="", character_name="", result="", memo=""):
        """セッション記録を追加する"""
        session_date = clean_text(session_date, max_len=50) or ""
        role = clean_text(role, max_len=50) or "PL"
        party_members = clean_text(party_members, max_len=200) or ""
        character_name = clean_text(character_name, max_len=100) or ""
        result = clean_text(result, max_len=100) or ""
        memo = clean_text(memo, max_len=5000, keep_newlines=True) or ""
        with self.conn:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO play_logs (item_id, session_date, role, party_members, character_name, result, memo)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (item_id, session_date, role, party_members, character_name, result, memo))
            return cursor.lastrowid

    def get_play_logs(self, item_id):
        """指定アイテムの全セッション記録を取得する（日付降順）"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, item_id, session_date, role, party_members, character_name, result, memo, created_at
            FROM play_logs
            WHERE item_id = ?
            ORDER BY COALESCE(NULLIF(session_date, ''), '0000-00-00') DESC, id DESC;
        """, (item_id,))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r[0],
                "item_id": r[1],
                "session_date": r[2] or "",
                "role": r[3] or "",
                "party_members": r[4] or "",
                "character_name": r[5] or "",
                "result": r[6] or "",
                "memo": r[7] or "",
                "created_at": r[8] or "",
            })
        return result

    def update_play_log(self, log_id, session_date="", role="PL", party_members="", character_name="", result="", memo=""):
        """セッション記録を更新する"""
        session_date = clean_text(session_date, max_len=50) or ""
        role = clean_text(role, max_len=50) or "PL"
        party_members = clean_text(party_members, max_len=200) or ""
        character_name = clean_text(character_name, max_len=100) or ""
        result = clean_text(result, max_len=100) or ""
        memo = clean_text(memo, max_len=5000, keep_newlines=True) or ""
        with self.conn:
            self.conn.execute("""
                UPDATE play_logs
                SET session_date = ?, role = ?, party_members = ?, character_name = ?, result = ?, memo = ?
                WHERE id = ?;
            """, (session_date, role, party_members, character_name, result, memo, log_id))

    def delete_play_log(self, log_id):
        """セッション記録を削除する"""
        with self.conn:
            self.conn.execute("DELETE FROM play_logs WHERE id = ?;", (log_id,))
