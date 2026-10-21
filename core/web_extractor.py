"""Webシナリオ情報抽出モジュール (core/web_extractor.py)

Booth (booth.pm) や TALTO (talto.cc) などのWebページから、
シナリオのタイトル・作者・システム・人数・時間・概要・あらすじ・表紙画像を自動抽出します。
"""

import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser


class OGPHTMLParser(HTMLParser):
    """OGPメタタグおよびタイトル、メタデスクリプション、JSON-LDを抽出するパーサー"""

    def __init__(self):
        super().__init__()
        self.meta = {}
        self.title_text = ""
        self._in_title = False
        self.json_lds = []
        self._in_script_ld_json = False
        self._script_buffer = []
        self.body_texts = []
        self._in_body = False
        self._in_ignore = False

    def handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        attr_dict = {k.lower(): v for k, v in attrs if v is not None}

        if tag_lower in ("script", "style", "noscript"):
            if tag_lower == "script" and attr_dict.get("type") == "application/ld+json":
                self._in_script_ld_json = True
                self._script_buffer = []
            else:
                self._in_ignore = True
            return

        if tag_lower == "title":
            self._in_title = True
            return

        if tag_lower == "body":
            self._in_body = True
            return

        if tag_lower == "meta":
            prop = attr_dict.get("property") or attr_dict.get("name")
            content = attr_dict.get("content")
            if prop and content:
                self.meta[prop.lower()] = content

    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower == "title":
            self._in_title = False
        elif tag_lower == "body":
            self._in_body = False
        elif tag_lower in ("script", "style", "noscript"):
            if self._in_script_ld_json:
                raw_json = "".join(self._script_buffer).strip()
                if raw_json:
                    try:
                        self.json_lds.append(json.loads(raw_json))
                    except Exception:
                        pass
                self._in_script_ld_json = False
            self._in_ignore = False

    def handle_data(self, data):
        if self._in_title:
            self.title_text += data
        elif self._in_script_ld_json:
            self._script_buffer.append(data)
        elif self._in_body and not self._in_ignore:
            t = data.strip()
            if t:
                self.body_texts.append(t)


class WebScenarioExtractor:
    """WebページからTRPGシナリオのメタ情報を自動抽出するエンジン"""

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    # 認識対象のTRPGシステム名（判定優先度順）
    SYSTEM_PATTERNS = [
        ("新クトゥルフ神話TRPG", [r"新クトゥルフ神話trpg", r"新coc", r"coc\s*7(?:th|版)?", r"第7版"]),
        ("クトゥルフ神話TRPG", [r"クトゥルフ神話trpg", r"クトゥルフ神話", r"coc\s*6(?:th|版)?", r"call of cthulhu", r"\bcoc\b"]),
        ("エモクロアTRPG", [r"エモクロアtrpg", r"エモクロア"]),
        ("シノビガミ", [r"シノビガミ", r"忍神"]),
        ("インセイン", [r"インセイン", r"inSANe"]),
        ("マギカロギア", [r"マギカロギア", r"魔道書大戦"]),
        ("ダブルクロス The 3rd Edition", [r"ダブルクロス", r"\bdx3rd\b", r"\bdx3\b"]),
        ("ソード・ワールド2.5", [r"ソード・ワールド2\.5", r"ソードワールド2\.5", r"\bsw2\.5\b"]),
        ("ソード・ワールド2.0", [r"ソード・ワールド2\.0", r"ソードワールド2\.0", r"\bsw2\.0\b"]),
        ("マーダーミステリー", [r"マーダーミステリー", r"マダミス", r"ペアマーダーミステリー", r"ペアマダ"]),
        ("ストーリープレイング", [r"ストーリープレイング", r"story\s*playing", r"ストプレ"]),
        ("フタリソウサ", [r"フタリソウサ"]),
        ("ネクロニカ", [r"ネクロニカ", r"永い後日談のネクロニカ"]),
        ("フィアスコ", [r"フィアスコ", r"\bfiasco\b"]),
        ("アリアンロッド2E", [r"アリアンロッド", r"\bar2e\b"]),
        ("銀剣のステラナイツ", [r"ステラナイツ"]),
        ("ゆうやけこやけ", [r"ゆうやけこやけ"]),
    ]

    @classmethod
    def fetch_html(cls, url: str, timeout: int = 8) -> str:
        """指定URLのHTML文字列を取得する"""
        headers = {
            "User-Agent": cls.USER_AGENT,
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        if "booth.pm" in url:
            headers["Cookie"] = "adult=t"

        req = urllib.request.Request(
            url,
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            # エンコーディング判別
            content_type = response.headers.get("content-type", "")
            charset = "utf-8"
            match = re.search(r"charset=([\w\-]+)", content_type, re.IGNORECASE)
            if match:
                charset = match.group(1).lower()

            try:
                return raw.decode(charset)
            except Exception:
                try:
                    return raw.decode("utf-8", errors="replace")
                except Exception:
                    return raw.decode("cp932", errors="replace")

    @classmethod
    def fetch_image_bytes(cls, img_url: str, timeout: int = 8, max_size_bytes: int = 10 * 1024 * 1024) -> bytes | None:
        """指定画像URLのバイナリを取得する"""
        if not img_url:
            return None
        try:
            req = urllib.request.Request(
                img_url,
                headers={"User-Agent": cls.USER_AGENT, "Referer": img_url},
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = response.read(max_size_bytes + 1)
                if len(data) > max_size_bytes:
                    return None
                return data
        except Exception:
            return None

    @classmethod
    def extract_from_html(cls, html_content: str, url: str = "") -> dict:
        """HTMLコンテンツからシナリオ情報を抽出・整形する"""
        parser = OGPHTMLParser()
        try:
            parser.feed(html_content)
        except Exception:
            pass

        meta = parser.meta
        parsed_url = urllib.parse.urlparse(url) if url else None
        host = (parsed_url.hostname or "").lower() if parsed_url else ""

        # 1. タイトル
        title = meta.get("og:title") or parser.title_text.strip() or ""
        title = html.unescape(title).strip()
        raw_title = title

        # 2. 概要 / あらすじ
        description = meta.get("og:description") or meta.get("description") or ""
        description = html.unescape(description).strip()

        # 3. 表紙画像URL
        image_url = meta.get("og:image") or ""
        if image_url and url:
            image_url = urllib.parse.urljoin(url, image_url)

        # 4. 作者名 / サークル名
        author = meta.get("author") or meta.get("og:site_name") or ""

        # JSON-LD からの情報補完
        for ld in parser.json_lds:
            if isinstance(ld, dict):
                if not title and ld.get("name"):
                    title = str(ld["name"])
                # description は JSON-LD の方が詳細で改行が保持されているケースが多いため、
                # より情報量が多い（長い）方を優先して採用する
                ld_desc = str(ld.get("description") or "").strip()
                if ld_desc and len(ld_desc) > len(description):
                    description = ld_desc
                if not author and ld.get("author"):
                    auth_val = ld["author"]
                    if isinstance(auth_val, dict) and "name" in auth_val:
                        author = str(auth_val["name"])
                    elif isinstance(auth_val, str):
                        author = auth_val
                if not image_url and ld.get("image"):
                    img_val = ld["image"]
                    if isinstance(img_val, str):
                        image_url = img_val
                    elif isinstance(img_val, list) and img_val and isinstance(img_val[0], str):
                        image_url = img_val[0]

        # HTML本文中のセクション構造および商品説明コンテナの抽出
        direct_sections, booth_main_desc = cls._extract_html_sections(html_content)

        # セクション群とメイン説明文を統合したテキストを構築
        combined_texts = []
        if booth_main_desc:
            combined_texts.append(booth_main_desc)
        for h, b in direct_sections.items():
            combined_texts.append(f"■{h}\n{b}")

        full_html_desc = "\n\n".join(combined_texts).strip()
        if len(full_html_desc) > len(description):
            description = full_html_desc

        # サイト固有の整形
        # (A) Booth (booth.pm)
        if "booth.pm" in host:
            # 「シナリオ名 - ショップ名 - BOOTH」の形式をパース
            if " - BOOTH" in title:
                parts = title.split(" - ")
                if len(parts) >= 3:
                    title = " - ".join(parts[:-2]).strip()
                    if not author:
                        author = parts[-2].strip()
                elif len(parts) == 2:
                    title = parts[0].strip()
            # サークル名が「BOOTH」のままの場合はshop名を取得
            if author == "BOOTH" and host != "booth.pm":
                sub = host.split(".booth.pm")[0]
                if sub and sub != "www":
                    author = sub

        # (B) TALTO (talto.cc)
        elif "talto.cc" in host:
            if " | TALTO" in title:
                title = title.split(" | TALTO")[0].strip()
            elif " - TALTO" in title:
                title = title.split(" - TALTO")[0].strip()

        # (C) Pixiv
        elif "pixiv.net" in host:
            if " [pixiv]" in title:
                title = title.split(" [pixiv]")[0].strip()

        # タイトルのクリーンアップ（『』の内側抽出やシステム名プレフィックス等の除去）
        title = cls.clean_title(title)

        # 本文中の明示的な作者表記による作者名補完（例: 「作者：ぺんぎん」）
        m_body_author = re.search(
            r'(?m)^[ \t]*[【\[■◆・\-]*(?:作者|シナリオ作|シナリオ制作|著者|Created by|Written by)[:：\s]+([^（\(\[【\n]+)',
            description, re.IGNORECASE
        )
        if m_body_author:
            cand_auth = m_body_author.group(1).strip()
            if cand_auth and len(cand_auth) <= 25 and not any(cand_auth.startswith(x) for x in ("http", "www", "BOOTH", "Twitter")):
                author = cand_auth

        # 本文全テキストを結合
        body_corpus = " ".join(parser.body_texts[:200]) + " " + description

        # 二次創作ライセンス・定型権利表記（「クトゥルフ神話TRPG」「新クトゥルフ神話TRPG」の商標併記）の除去
        clean_body = re.sub(r'本作は、.*?(?:二次創作物です|権利を有する)[^\n]*', '', body_corpus, flags=re.IGNORECASE)
        clean_body = re.sub(r'Call of Cthulhu is copyright[^\n]*', '', clean_body, flags=re.IGNORECASE)
        clean_body = re.sub(r'「クトゥルフ神話TRPG」「新クトゥルフ神話TRPG」[^\n]*', '', clean_body, flags=re.IGNORECASE)

        # 5. システム名の推測
        # (A) まずタイトルまたは定型文除去後本文から判定
        system_name = cls._guess_system(title + " " + clean_body)
        if not system_name:
            system_name = cls._guess_system(raw_title)

        # 6. 人数・時間の抽出
        players = cls._extract_players(body_corpus)
        duration = cls._extract_duration(body_corpus)

        # 7. 概要・あらすじの振り分け
        overview, synopsis = cls._extract_overview_and_synopsis(
            description, direct_sections=direct_sections, main_desc=booth_main_desc
        )

        # (C) 概要（スペック情報）内に明示的な形式・システム表記がある場合、それを最優先で反映
        if overview:
            m_spec_sys = re.search(r'(?m)^[ \t]*[【\[■◆・▾\-]*\s*(?:形式|システム|ルールブック|ルルブ)[:：　\s]+(.*)$', overview)
            if m_spec_sys:
                spec_sys = cls._guess_system(m_spec_sys.group(1))
                if spec_sys:
                    system_name = spec_sys

        return {
            "title": title,
            "author": author,
            "system": system_name,
            "players": players,
            "duration": duration,
            "overview": overview,
            "synopsis": synopsis,
            "image_url": image_url,
        }

    @classmethod
    def _extract_html_sections(cls, html_content: str) -> tuple[dict, str]:
        """HTML内の見出しセクション構造および商品説明コンテナを汎用抽出する"""
        sections = {}

        # 1. BOOTH等の <section class="shop__text"> または明示的なセクションコンテナ
        container_sections = re.findall(
            r'<(?:section|div|article)[^>]*class=[\'"][^\'"]*(?:shop__text|item-section|scenario-section)[^\'"]*[\'"][^>]*>(.*?)</(?:section|div|article)>',
            html_content, re.DOTALL | re.IGNORECASE
        )
        for sec in container_sections:
            h_m = re.search(r'<h[1-6][^>]*>(.*?)</h[1-6]>', sec, re.DOTALL | re.IGNORECASE)
            heading = re.sub(r'<[^>]+>', '', h_m.group(1)).strip() if h_m else ""

            body = re.sub(r'<h[1-6][^>]*>.*?</h[1-6]>', '', sec, flags=re.DOTALL | re.IGNORECASE)
            body = re.sub(r'<br\s*/?>', '\n', body, flags=re.IGNORECASE)
            body = re.sub(r'</p>', '\n', body, flags=re.IGNORECASE)
            body = re.sub(r'</?(?:[a-zA-Z][a-zA-Z0-9:-]*|!--.*?--)(?:\s+[^>]*)?/?>', '', body, flags=re.DOTALL)
            body = html.unescape(body).strip()
            body = re.sub(r'\n?[ \t]*[\-\=＿_~〜*]{3,}[ \t]*$', '', body).strip()
            body = re.sub(r'[\u200b-\u200f\u202a-\u202e\ufeff]', '', body)
            if heading and body:
                clean_h = re.sub(r'^[【\[■◆▼●★*#・\-\s]+|[】\]:：\s\-]+$', '', heading).strip()
                sections[clean_h] = body

        # 2. コンテナが見つからない場合の汎用見出しタグ (<h1-h6>) パーサー（TALTOや個人サイト等）
        if not sections:
            body_m = re.search(r'<body[^>]*>(.*?)</body>', html_content, re.DOTALL | re.IGNORECASE)
            target_html = body_m.group(1) if body_m else html_content

            heading_pat = re.compile(r'<(h[1-6])[^>]*>(.*?)</\1>', re.DOTALL | re.IGNORECASE)
            matches = list(heading_pat.finditer(target_html))
            for i, m in enumerate(matches):
                raw_h = re.sub(r'<[^>]+>', '', m.group(2)).strip()
                clean_h = re.sub(r'^[【\[■◆▼●★*#・\-\s]+|[】\]:：\s\-]+$', '', raw_h).strip()
                start = m.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(target_html)
                raw_body = target_html[start:end]
                # スクリプトやスタイルは除外
                raw_body = re.sub(r'<(?:script|style|noscript)[^>]*>.*?</(?:script|style|noscript)>', '', raw_body, flags=re.DOTALL | re.IGNORECASE)
                raw_body = re.sub(r'<br\s*/?>', '\n', raw_body, flags=re.IGNORECASE)
                raw_body = re.sub(r'</p>', '\n', raw_body, flags=re.IGNORECASE)
                raw_body = re.sub(r'</?(?:[a-zA-Z][a-zA-Z0-9:-]*|!--.*?--)(?:\s+[^>]*)?/?>', '', raw_body, flags=re.DOTALL)
                body_text = html.unescape(raw_body).strip()
                body_text = re.sub(r'\n?[ \t]*[\-\=＿_~〜*]{3,}[ \t]*$', '', body_text).strip()
                body_text = re.sub(r'[\u200b-\u200f\u202a-\u202e\ufeff]', '', body_text)
                if clean_h and body_text and len(body_text) < 5000:
                    sections[clean_h] = body_text

        # 3. メイン商品説明コンテナ（BOOTHのトップ説明等）
        main_desc = ""
        main_desc_candidates = []
        for m in re.finditer(
            r'<(?:div|section|p|article|span)[^>]*class=[\'"][^\'"]*(?:js-market-item-detail-description|booth-description|js-expansion-content|item-description|user-text-content)[^\'"]*[\'"][^>]*>(.*?)</(?:div|section|p|article|span)>',
            html_content, re.DOTALL | re.IGNORECASE
        ):
            raw_desc = m.group(1)
            raw_desc = re.sub(r'<br\s*/?>', '\n', raw_desc, flags=re.IGNORECASE)
            raw_desc = re.sub(r'</p>', '\n', raw_desc, flags=re.IGNORECASE)
            raw_desc = re.sub(r'</?(?:[a-zA-Z][a-zA-Z0-9:-]*|!--.*?--)(?:\s+[^>]*)?/?>', '', raw_desc, flags=re.DOTALL)
            t = html.unescape(raw_desc).strip()
            t = re.sub(r'\n?[ \t]*[\-\=＿_~〜*]{3,}[ \t]*$', '', t).strip()
            t = re.sub(r'[\u200b-\u200f\u202a-\u202e\ufeff]', '', t)
            if t:
                main_desc_candidates.append(t)

        if main_desc_candidates:
            main_desc = max(main_desc_candidates, key=len)

        return sections, main_desc

    @classmethod
    def clean_title(cls, title: str) -> str:
        """タイトルから余分な接頭語・接尾語（システム名、ジャンル名、タグ記号、SPLLライセンス等）を汎用的に除去して整形する"""
        if not title:
            return ""
        t = title.strip()

        # 0. SPLL表記（二次創作ライセンスコード）の除去
        # 例: "SPLL:E197335", "【SPLL:E123456】", "SPLL：E197335", "║SPLL:E197608" など
        t = re.sub(r'[\s:：／/\-–—|｜║∥│┃]*[【\[［\(（〈《〔]?\s*SPLL[:：\s]*[A-Za-z0-9_-]+.*$', '', t, flags=re.IGNORECASE).strip()
        t = re.sub(r'[\s:：／/\-–—|｜║∥│┃]+$', '', t).strip()

        # 登録されている全システム名・エイリアスを収集
        sys_tokens = []
        for name, pats in cls.SYSTEM_PATTERNS:
            sys_tokens.append(re.escape(name))
            for p in pats:
                # \b 等の単語境界記号を除いてトークン化
                clean_p = p.replace(r"\b", "").strip()
                if clean_p:
                    sys_tokens.append(clean_p)

        general_tags = [
            r"ペアマーダーミステリー", r"マーダーミステリー", r"マダミス", r"ペアマダ",
            r"ストーリープレイング", r"ストプレ",
            r"TRPGシナリオ", r"TRPG", r"シナリオ集", r"シナリオ",
            r"キャンペーン", r"タイマン", r"ソロ", r"公式", r"無料版?", r"PDF版?", r"DL版?",
            r"第[0-9０-９]+版", r"SPLL[:：\s]*[A-Za-z0-9_-]+"
        ]
        all_noise = sys_tokens + general_tags
        noise_core = "|".join(dict.fromkeys(all_noise))  # 重複除去

        # 1. 『...』 や 「...」 や 《...》 が含まれている場合の内外判定
        m = re.search(r"[『「《]([^』」》]+)[』」》]", t)
        if m:
            before = t[:m.start()].strip()
            after = t[m.end():].strip()
            inner = m.group(1).strip()

            noise_pat = rf"^(?:【[^】]*】|\[[^\]]*\]|［[^］]*］|\([^\)]*\)|（[^）]*）|〈[^〉]*〉|{noise_core}|[!！★◆●▼▲\s:：／/\-–—|｜║∥│┃])*$"
            is_before_noise = not before or bool(re.match(noise_pat, before, re.IGNORECASE))
            is_after_noise = not after or bool(re.match(noise_pat, after, re.IGNORECASE))

            if is_before_noise and is_after_noise and inner:
                return inner

        # 2. 先頭のブラケット・システム名・タグプレフィックスを繰り返し除去
        prefix_pattern = (
            rf"^(?:【[^】]+】|\[[^\]]+\]|［[^］]+］|\([^\)]+\)|（[^）]+）|〈[^〉]+〉|{noise_core})"
            r"[\s:：／/\-–—]*"
        )
        while True:
            new_t = re.sub(prefix_pattern, "", t, count=1, flags=re.IGNORECASE).strip()
            if new_t == t:
                break
            t = new_t

        # 3. 末尾のブラケット・システム名・タグサフィックスを繰り返し除去
        suffix_pattern = (
            r"[\s:：／/\-–—]*"
            rf"(?:【[^】]+】|\[[^\]]+\]|［[^］]+］|\([^\)]+\)|（[^）]+）|〈[^〉]+〉|{noise_core})$"
        )
        while True:
            new_t = re.sub(suffix_pattern, "", t, count=1, flags=re.IGNORECASE).strip()
            if new_t == t:
                break
            t = new_t

        # 3-b. パイプ（｜, |）での分割チェック（例: 「海哭村｜CoC6/エモクロア｜本文無料」）
        if "｜" in t or "|" in t:
            pipe_parts = [p.strip() for p in re.split(r'[|｜]', t) if p.strip()]
            if len(pipe_parts) >= 2:
                noise_words = {
                    "本文無料", "無料", "無料版", "有料", "投げ銭", "おまけ付き", "素材付き", "pdf版", "dl版", "シナリオ", "trpg",
                    "ソロ", "タイマン", "公式", "本文"
                }
                def _is_noise_part(part: str) -> bool:
                    sub_tokens = [st.strip() for st in re.split(r'[/／\s]+', part) if st.strip()]
                    if not sub_tokens:
                        return True
                    for sub in sub_tokens:
                        if cls._guess_system(sub):
                            continue
                        if sub.lower() in noise_words or re.match(r'^(?:第[0-9０-９]+版|[0-9０-９]+PL|SPLL:.*)$', sub, re.IGNORECASE):
                            continue
                        return False
                    return True

                if all(_is_noise_part(p) for p in pipe_parts[1:]):
                    t = pipe_parts[0]
                elif _is_noise_part(pipe_parts[-1]):
                    t = "｜".join(pipe_parts[:-1]).strip()

        # 4. 先頭と末尾の囲み括弧の除去（タイトル全体が括弧で囲まれている場合）
        if len(t) >= 2:
            brackets = [("『", "』"), ("「", "」"), ("《", "》"), ("【", "】"), ("〈", "〉"), ("［", "］")]
            for open_c, close_c in brackets:
                if t.startswith(open_c) and t.endswith(close_c):
                    t = t[1:-1].strip()
                    break

        return t or title.strip()

    @classmethod
    def _guess_system(cls, text: str) -> str:
        """テキストからTRPGシステム名を推測する"""
        text_lower = text.lower()
        for sys_name, patterns in cls.SYSTEM_PATTERNS:
            for pat in patterns:
                if re.search(pat, text_lower):
                    return sys_name
        return ""

    @classmethod
    def _extract_players(cls, text: str) -> str:
        """テキストからプレイ人数（例: 2〜4人, 1人（ソロ）, 3人固定, 2PL, 1人～ 等）を抽出する"""
        # タイマン(1人)と2PLの併記パターン（例: 2PL/PC＋KPCの一人用タイマンシナリオ, 2PLまたはタイマン, タイマン/2PL）
        taiman_2pl_pat = re.compile(
            r'(?:人数|プレイ人数|推奨人数|PL人数|PL).*?'
            r'(?:'
            r'(?:2PL|2人|二人)[/／・、,\sまたは|｜]*(?:PC\s*[+＋]\s*KPC(?:の)?)?(?:一人|1人|タイマン)'
            r'|(?:一人|1人|タイマン|ソロ)[/／・、,\sまたは|｜]*(?:PC\s*[+＋]\s*KPC(?:の)?)?(?:2PL|2人|二人)'
            r'|(?:2PL|2人)\s*[（\(]\s*(?:一人|1人|タイマン)'
            r'|(?:一人|1人|タイマン)\s*[（\(]\s*(?:2PL|2人)'
            r')',
            re.IGNORECASE
        )
        if taiman_2pl_pat.search(text):
            return "1～2人"

        patterns = [
            # 人数見出しに続く修飾語（秘匿HO有り、推奨等）を挟んだ人数抽出（例: ■人数：秘匿 HO 有り 2PL, 〈プレイ人数〉4人固定, 人数　1人～）
            r"[【\[［\(（〈《〔■◆▼●★*#・\-]*\s*(?:推奨人数|プレイ人数|プレイヤー人数|人数|PL人数|PL)[】\]］\)）〉》〕]?[:：　\s]*(?:[^\n0-9０-９]{0,25}?)([0-9０-９]+(?:\s*[〜～\-–/]\s*[0-9０-９]+)?\s*(?:人|名|PL)(?:用|向け|前後|固定|〜|～)?)",
            r"[【\[［\(（〈《〔■◆▼●★*#・\-]*\s*(?:推奨人数|プレイ人数|プレイヤー人数|人数|PL人数|PL)[】\]］\)）〉》〕]?[:：　\s]*(?:推定|約|およそ|推奨)?[:：　\s]*(ソロ|1人（タイマン）|タイマン|一人|KPレス|GMレス)",
            r"([0-9０-９]+(?:\s*[〜～\-–]\s*[0-9０-９]+)\s*[人名](?:用|向け)?)",
            r"[【\[［\(（〈《〔■◆▼●★*#・\-]*\s*(?:推奨人数|プレイ人数|プレイヤー人数|人数|PL人数|PL)[】\]］\)）〉》〕]?[:：　\s]*(?:[^\n0-9０-９]{0,25}?)([0-9０-９]+)\s*(?:PL|人|名)(?:〜|～)?",
            r"(?m)^[ \t]*[■◆▼●★・\-]?[ \t]*(?:[0-9０-９]+(?:\s*[〜～\-–/]\s*[0-9０-９]+)?)\s*PL(?:〜|～)?\b",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                val = re.sub(r"[０-９]", lambda c: chr(ord(c.group(0)) - 0xFEE0), val)
                if val in ("ソロ", "一人", "KPレス", "GMレス"):
                    return "1人"
                val = val.replace("名", "人")
                val = re.sub(r'PL', '人', val, flags=re.IGNORECASE)
                val = re.sub(r'人+', '人', val)
                if not val.endswith(("人", "固定", "前後", "向け", "用", "タイマン", "〜", "～")):
                    val += "人"
                return val
        return ""

    @classmethod
    def _split_by_author(cls, text: str) -> tuple[str, str]:
        """テキスト内に作者表記がある場合、作者行の次が概要内容（スペック情報等）でないことを確認して概要とあらすじに分割する"""
        if not text:
            return "", ""

        # 作者行の検出パターン
        author_line_pat = re.compile(
            r'(?m)^[ \t]*[【\[［\(（〈《〔■◆▼●★*#・\-]*\s*'
            r'(?:作者|作|シナリオ制作|シナリオ作|制作|著|著者|クレジット|シナリオライター|ライター|Author|Created by|Written by)'
            r'\s*[】\]:：\s\-].*$',
            re.IGNORECASE
        )

        # 概要・スペックを示す見出しやキーワードのパターン
        spec_indicator_pat = re.compile(
            r'^[【\[［\(（〈《〔■◆▼●★*#・\-]*\s*'
            r'(?:システム|プレイ人数|推奨人数|プレイヤー人数|人数|PL人数|PL|プレイ時間|所要時間|想定時間|時間|セッション時間|舞台|ロスト率|ロスト|推奨技能|準推奨技能|推奨PC|形式|難易度|推理難易度|シナリオ傾向|傾向|注意事項|事前注意|注意|利用規約|規約|お願い|ハンドアウト|HO|公開HO|秘匿HO)',
            re.IGNORECASE
        )

        matches = list(author_line_pat.finditer(text))
        if not matches:
            return "", ""

        for m in matches:
            spec_candidate = text[:m.end()].strip()
            rest_candidate = text[m.end():].strip()
            # 区切り線などの除去
            rest_candidate = re.sub(r'^[ \t]*[\-\=＿_~〜*#]{3,}[ \t]*\n?', '', rest_candidate).strip()

            # 1. 作者行より前の部分が概要（スペック）内容を含んでいること
            if cls._analyze_section_type(spec_candidate) != "spec":
                if not any(k in spec_candidate for k in ("システム", "人数", "PL", "時間", "推奨技能", "舞台", "ロスト")):
                    continue

            rest_lines = [l.strip() for l in rest_candidate.splitlines() if l.strip()]
            if not rest_lines:
                continue

            first_line = rest_lines[0]
            # 2. 次に出てくる文言が概要（スペック）内容でないか確認
            is_spec_like = bool(spec_indicator_pat.match(first_line))
            if not is_spec_like and cls._analyze_section_type(first_line) == "spec":
                is_spec_like = True

            # 次に出てくる文言が概要内容でない場合のみ切り分けを行う
            if not is_spec_like and rest_candidate:
                return spec_candidate, rest_candidate

        return "", ""

    @classmethod
    def _split_narrative_and_spec_block(cls, text: str, keep_notes: bool = False) -> tuple[str, str]:
        """テキスト内に物語文（あらすじ）とスペックブロック（概要）が同居している場合、両者を切り分ける"""
        if not text:
            return "", ""

        # スペック項目の開始行パターン（三角形ビュレット ‣ ▹ ▸ ▶ ▷ ► ◄、ブロック記号 ▋ ▌ 等を含む）
        bullet_syms = r"【\[［\(（〈《〔■◆▼●★*#・▾\-‣▹▸▶▷►◄▋▌▍▎▏█✦✧"
        spec_line_pat = re.compile(
            rf'(?m)^[ \t]*[{bullet_syms}]*\s*'
            r'(?:タイトル|形式|システム|人数|プレイ人数|推奨人数|プレイヤー人数|プレイ時間|所要時間|想定時間|目安時間|時間|舞台|ロスト率|ロスト|発狂率|推奨技能|振る機会のある技能|技能|探索者|傾向|シナリオ傾向|難易度)'
            r'[:：　\t ]+.*$'
        )

        m = spec_line_pat.search(text)
        if not m:
            return "", ""

        story_part = text[:m.start()].strip()
        spec_part = text[m.start():].strip()

        # スペックブロックの直前の行が括弧付きタイトル（「...」や『...』等）の場合、タイトル行をスペックブロックに含める
        story_lines = [l.strip() for l in story_part.splitlines() if l.strip()]
        if story_lines and re.match(r'^[「『《【].+[」』》】]$', story_lines[-1]):
            spec_part = story_lines[-1] + "\n" + spec_part
            story_part = "\n".join(story_lines[:-1]).strip()

        # 物語文の前にタイトルや見出しラベル（【概要】など）がある場合、見出し以降を物語文としてトリム
        m_heading = re.search(rf'(?m)^[ \t]*[{bullet_syms}]*\s*(?:シナリオ概要|作品概要|概要|あらすじ|ストーリー|導入|はじめに)[ \t]*[】\]］\)）〉》〕:]*[ \t]*$', story_part)
        if m_heading:
            story_part = story_part[m_heading.end():].strip()
        else:
            # 先頭のシステム名・タイトル行＋装飾線ヘッダーのトリム
            story_part = re.sub(r'^(?:[ \t]*[^\n]{1,40}\n|[ \t]*\n){1,6}[ \t]*[\-\=＿_~〜*#+＋]{3,}[ \t]*\n?', '', story_part).strip()
            # 先頭の見出し記号トリム
            story_part = re.sub(rf'^[ \t]*[{bullet_syms}]*\s*(?:シナリオ概要|作品概要|概要|あらすじ|ストーリー|はじめに)[ \t]*\n?', '', story_part).strip()

        # 物語文末尾の装飾線トリム
        story_part = re.sub(r'\n?[ \t]*[\-\=＿_~〜*#+＋]{3,}[ \t]*$', '', story_part).strip()

        # 物語文の先頭の括弧付きタイトル行、および先頭・末尾の装飾行（「・　・　・」「───」等）を除去
        s_lines = [l.strip() for l in story_part.splitlines()]
        deco_line_pat = re.compile(r'^[・\s\-\=＿_~〜*#+＋─━―–—·•]*$')
        while s_lines and not s_lines[0]:
            s_lines.pop(0)
        if s_lines and re.match(r'^[『《【][^。！？!?]{1,40}[』》】]$', s_lines[0]):
            s_lines.pop(0)
        while s_lines and deco_line_pat.match(s_lines[0]):
            s_lines.pop(0)
        while s_lines and deco_line_pat.match(s_lines[-1]):
            s_lines.pop()
        story_part = "\n".join(s_lines).strip()

        # 末尾の二次創作表記・権利表記・企画・注記・略称・装飾線トリム
        # keep_notes=True の場合は「※」注記と「略称」行をスペック（概要）側に残す
        note_alts = r'' if keep_notes else r'※|略称|'
        spec_trim_pat = re.compile(
            r'(?m)^[ \t]*(?:'
            + note_alts +
            r'本作は、|クレジット|利用規約|規約|【利用規約】|ダイスタス・コモンズ|権利表記'
            r'|ルルブ.*?(?:ですが|どうぞ)|ルールブック.*?(?:ですが|どうぞ)'
            r'|甘いもの市場|presents|非公式.*?企画|参加作品'
            r'|［シナリオ本編にある要素］|【シナリオ傾向】|【特記事項】|【付属内容】|【注意'
            r'|[\-\=＿_~〜*#+＋─━]{3,}'
            r')'
        )
        spec_part = spec_trim_pat.split(spec_part)[0].strip()

        # スペック部分が一定のスペック行（3行以上）を含む場合、スペックブロックとして有効
        clean_spec_lines = [l for l in spec_part.splitlines() if l.strip()]
        has_spec = bool(spec_part and len(clean_spec_lines) >= 3)
        is_narrative = len(story_part) >= 20 and any(p in story_part for p in ("。", "……", "！", "？", "!", "?", "た", "る", "ない", "──", "――"))

        if has_spec:
            return spec_part, story_part if is_narrative else ""

        return "", ""

    @classmethod
    def _extract_duration(cls, text: str) -> str:
        """テキストから所要時間（例: 3〜4時間, 6時間, 30分, 30分〜1.5時間, 12時間〜 等）を抽出する"""
        qualifiers = r"(?:推定|約|およそ|目安|ボイスセッション|テキストセッション|ボイセ|半テキ|テキセ)?"
        prefix = rf"[【\[［\(（〈《〔]?(?:所要時間|プレイ時間|想定時間|目安時間|時間|セッション時間)[】\]］\)）〉》〕]?[:：\s]*(?:{qualifiers}(?:で|：|:|\s)*)*"
        h_unit = r"(?:時間|分|[hHｈＨ](?:ours?)?)"
        patterns = [
            rf"{prefix}([0-9０-９]+(?:\.[0-9０-９]+)?\s*(?:時間|分)?\s*[〜～\-–/]\s*[0-9０-９]+(?:\.[0-9０-９]+)?\s*{h_unit}(?:前後)?)",
            rf"{prefix}([0-9０-９]+(?:\.[0-9０-９]+)?\s*{h_unit}(?:前後|〜|～)?)",
            r"([0-9０-９]+(?:\.[0-9０-９]+)?\s*(?:時間|分)?\s*[〜～\-–/]\s*[0-9０-９]+(?:\.[0-9０-９]+)?\s*(?:時間|分))",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                val = m.group(1).strip()
                val = re.sub(r"[０-９]", lambda c: chr(ord(c.group(0)) - 0xFEE0), val)
                # h / ｈ / hours 表記を「時間」に統一（例: 1ｈ～ → 1時間～）
                val = re.sub(r"(?<=[0-9\s])[hHｈＨ](?:ours?)?", "時間", val)
                return val
        return ""

    @classmethod
    def _analyze_section_type(cls, text: str) -> str:
        """テキスト内容を構造分析し、'spec'（スペック情報）か 'story'（物語・あらすじ）かを判定する"""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return "neutral"

        spec_score = 0.0
        story_score = 0.0

        spec_keywords = [
            r"(?:プレイ|推奨|想定)?(?:人数|時間)",
            r"(?:推奨)?技能",
            r"舞台", r"ロスト(?:率)?", r"難易度", r"推理難易度",
            r"形式", r"タイプ", r"ジャンル",
            r"システム", r"ルルブ|ルールブック",
            r"ハンドアウト|HO[1-4１-４]?", r"事前HO", r"公開HO",
            r"ココフォリア|Discord|ツール",
            r"戦闘", r"発狂率", r"PvP", r"後遺症",
        ]
        spec_kw_pat = re.compile("|".join(spec_keywords), re.IGNORECASE)
        story_end_pat = re.compile(r"(?:[。！？!?…]|[―ー—]{2,}|(?:だ|である|した|された|ている|ていた|ゆく|いく|ない|あろう|だろうか|だろう|のだ|のです|ます|でした|ません))$")

        kv_count = 0
        bullet_count = 0
        sentence_end_count = 0
        dialogue_count = 0

        for line in lines:
            # 箇条書き記号
            if re.match(r"^[\-\*・■◆●▼▲★☆\d+\.][\s　]", line) or line.startswith("・"):
                bullet_count += 1

            # キーバリュー形式（コロンや全角コロンで区切られている）
            if re.search(r"^[^:：\n]{1,15}[:：]", line):
                kv_count += 1
                if spec_kw_pat.search(line):
                    spec_score += 2.0

            # スペックキーワードの出現
            if spec_kw_pat.search(line):
                spec_score += 1.5

            # 会話文（セリフ）
            if re.match(r"^[「『].*[」』]$", line):
                dialogue_count += 1
                story_score += 2.5

            # 物語らしい文末
            if story_end_pat.search(line):
                sentence_end_count += 1
                story_score += 1.2

            # 長い文章段落（30文字以上の文）
            if len(line) >= 30 and not line.startswith("・"):
                story_score += 1.5

        total_lines = len(lines)
        if kv_count / total_lines >= 0.25:
            spec_score += 3.0
        if bullet_count / total_lines >= 0.35:
            spec_score += 2.5
        if sentence_end_count / total_lines >= 0.35:
            story_score += 3.0

        if spec_score > story_score + 1.0:
            return "spec"
        elif story_score > spec_score + 1.0:
            return "story"
        return "neutral"

    @classmethod
    def _split_by_abbreviation_or_narrative(cls, text: str) -> tuple[str, str]:
        """テキスト内に「略称」表記がある場合、略称行までを概要、以降をあらすじに分割する"""
        if not text:
            return "", ""

        # 「略称」パターンによる分割
        # 例: 「略称は「たけし」です。」, 「略称：たけし」, 「【略称】たけし」, 「略称:〇〇」など
        m = re.search(r'(?m)^[ \t]*[【\[［\(（〈《〔]?\s*略称.*$', text)
        if m:
            spec_part = text[:m.end()].strip()
            rest = text[m.end():].strip()
            # 区切り線などの除去
            rest = re.sub(r'^[ \t]*[\-\=＿_~〜*#─━―]{3,}[ \t]*\n?', '', rest).strip()
            # 装飾記号のみの残り（区切り線だけ等）は本文とみなさない
            if rest and not re.fullmatch(r'[\s\-\=＿_~〜*#+＋─━―・·•]*', rest):
                return spec_part, rest

            # 略称が末尾にあり、その前に物語文＋スペックブロックが同居している場合（例: 物語→スペック→※注記→略称）
            spec_p, story_p = cls._split_narrative_and_spec_block(spec_part, keep_notes=True)
            if spec_p and story_p:
                return spec_p, story_p

        return "", ""

    @classmethod
    def _extract_overview_and_synopsis(
        cls, description: str, direct_sections: dict = None, main_desc: str = ""
    ) -> tuple[str, str]:
        """テキストから概要（overview）とあらすじ（synopsis）を高精度かつ汎用的に切り出す"""
        if not description and not direct_sections and not main_desc:
            return "", ""

        sections = dict(direct_sections) if direct_sections else {}

        # セクション見出しの正規表現（descriptionテキストからのフォールバック切り出し）
        bullet_syms = r"【\[［\(（〈《〔■◆▼●★*#・▾\-‣▹▸▶▷►◄▋▌▍▎▏█✦✧"
        section_kw = (
            r'(?:あらすじ|ストーリー|イントロダクション|イントロ|トレーラー|導入|プロローグ|STORY|Story|INTRODUCTION|Introduction|TRAILER|Trailer|PROLOGUE|Prologue'
            r'|シナリオ概要|作品概要|概要|基本情報|シナリオスペック|シナリオデータ|シナリオ情報|作品情報|スペック|プレイ情報|セッション情報|ABOUT|About|OVERVIEW|Overview'
            r'|キャラクター紹介|キャラクター|登場人物|登場NPC|NPC|PC|ハンドアウト|HO|事前HO|公開HO|秘匿HO'
            r'|資料内容|内容物|ファイル内容|収録内容|同梱物|セット内容|素材内容|データ内容|DL内容|ダウンロード内容'
            r'|事前注意|注意事項|注意|利用規約|規約|お願い|利用について|配信について|配信ガイドライン|動画配信について|ネタバレについて'
            r'|プレイ人数|推奨人数|人数|プレイ時間|所要時間|想定時間|時間|推奨技能|推奨PC|舞台|ロスト率|傾向|シナリオ傾向|難易度|推理難易度|形式'
            r'|作者等の情報|作者情報|制作|スタッフ|クレジット|更新履歴|更新情報|更新|GMをしてくださる方へ|GM向け|作者GM|公認GM|問い合わせ|ショップ|BOOTH|Booth'
            r'|雰囲気|どんなシナリオ|想定している遊び方|要素|同梱内容|権利表記|おすすめ)'
        )
        # 強い見出し記号（■◆▋▌）付きの行で、見出しキーワードを文中に含む短い行（例: 「■こんな探索者/状態におすすめ！」）も見出しとして扱う
        loose_kw = (
            r'(?:あらすじ|ストーリー|概要|内容物|同梱|頒布|注意|規約|権利|更新|クレジット'
            r'|ハンドアウト|キャラクター|登場人物|おすすめ|オススメ|お勧め)'
        )
        section_split_pat = re.compile(
            rf'(?m)^[ \t]*('
            rf'[{bullet_syms}]*\s*{section_kw}\s*[{bullet_syms}\]】:：\s\-]*'
            rf'|[■◆▋▌][^\n]{{0,20}}?{loose_kw}[^\n]{{0,20}}'
            r')[ \t]*$'
        )

        target_texts_for_split = []
        if main_desc:
            target_texts_for_split.append(main_desc)
        if description and description != main_desc:
            target_texts_for_split.append(description)

        for text_to_split in target_texts_for_split:
            matches = list(section_split_pat.finditer(text_to_split))
            if matches:
                # 最初の見出しの前のテキストからスペックブロックおよび物語文を抽出
                pre_text = text_to_split[:matches[0].start()].strip()
                if pre_text and "基本情報" not in sections and "概要" not in sections:
                    pre_spec, pre_story = cls._split_narrative_and_spec_block(pre_text)
                    if pre_spec:
                        sections["基本情報"] = pre_spec
                    if pre_story and "あらすじ" not in sections and "ストーリー" not in sections:
                        sections["あらすじ"] = pre_story
                for i, m in enumerate(matches):
                    header = m.group(1).strip()
                    clean_header = re.sub(rf'^[{bullet_syms}\s]+|[{bullet_syms}\s]+$', '', header).strip()
                    start = m.end()
                    end = matches[i + 1].start() if i + 1 < len(matches) else len(text_to_split)
                    content = text_to_split[start:end].strip()
                    content = re.sub(r'^[ \t]*[\-\=＿_~〜*#+＋]{3,}[ \t]*\n?', '', content).strip()
                    content = re.sub(r'\n?[ \t]*[\-\=＿_~〜*#+＋]{3,}[ \t]*$', '', content).strip()
                    content = re.sub(r'[\u200b-\u200f\u202a-\u202e\ufeff]', '', content)
                    if clean_header and content and clean_header not in sections:
                        sections[clean_header] = content

        # 各セクション本文の途中に別の見出し（■あらすじ 等）が埋め込まれている場合、その手前で切り詰める
        for sk in list(sections.keys()):
            sv = sections[sk]
            m_inner = section_split_pat.search(sv)
            if m_inner and m_inner.start() > 0:
                trimmed = sv[:m_inner.start()].strip()
                trimmed = re.sub(r'\n?[ \t]*[\-\=＿_~〜*#+＋─━]{3,}[ \t]*$', '', trimmed).strip()
                if trimmed:
                    sections[sk] = trimmed

        # 除外すべきノイズ見出し（あらすじや概要に含めない）
        ignore_keys = (
            'キャラクター', '登場人物', 'NPC', 'ハンドアウト', 'HO',
            '資料', '内容物', 'ファイル', '収録', '同梱物', 'セット内容', '素材', 'データ内容', 'DL', 'ダウンロード', '頒布',
            '注意', '規約', 'お願い', 'ガイドライン', 'ネタバレ',
            '文字数', 'ご意見', 'ご感想', '感想', 'アンケート', 'Other', 'その他',
            '作者', '制作', 'スタッフ', 'クレジット', '更新', 'GM', '問い合わせ', 'ショップ',
            '雰囲気', 'どんなシナリオ', '想定している遊び方', '要素', '同梱内容', '権利表記', 'おすすめ'
        )

        valid_sections = {k: v for k, v in sections.items() if not any(ik in k for ik in ignore_keys)}

        # 各セクションの内容タイプを判定
        section_types = {k: cls._analyze_section_type(v) for k, v in valid_sections.items()}
        main_desc_type = cls._analyze_section_type(main_desc) if main_desc else "neutral"

        strong_synopsis_keys = (
            "あらすじ", "ストーリー", "STORY", "Story",
            "イントロダクション", "イントロ", "INTRODUCTION", "Introduction",
            "トレーラー", "TRAILER", "Trailer",
            "導入", "プロローグ", "PROLOGUE", "Prologue"
        )
        strong_spec_keys = (
            "シナリオ情報", "基本情報", "シナリオスペック", "シナリオデータ",
            "作品情報", "スペック", "プレイ情報", "セッション情報"
        )
        spec_field_keys = (
            "プレイ人数", "推奨人数", "人数", "プレイ時間", "所要時間", "想定時間", "時間",
            "推奨技能", "推奨PC", "舞台", "ロスト率", "難易度", "推理難易度", "形式"
        )

        # 1. あらすじ (Synopsis) と概要 (Overview) の探索
        found_synopsis = ""
        found_overview = ""
        synopsis_key = None
        from_abbrev = False

        # 0. 「略称」「作者」「物語＋スペック同居」表記によるスペック概要とあらすじの優先分割
        # 0-a. 「略称」表記による分割
        for sk, scontent in valid_sections.items():
            spec_p, story_p = cls._split_by_abbreviation_or_narrative(scontent)
            if spec_p and story_p:
                found_overview = spec_p
                found_synopsis = story_p
                synopsis_key = sk
                from_abbrev = True
                break

        has_strong_synopsis = any(any(k in sk for k in strong_synopsis_keys) for sk in valid_sections)
        has_strong_spec = any(any(k in sk for k in strong_spec_keys) for sk in valid_sections)

        if not found_overview and not found_synopsis and not has_strong_synopsis and not has_strong_spec and description:
            spec_p, story_p = cls._split_by_abbreviation_or_narrative(description)
            if spec_p and story_p:
                found_overview = spec_p
                found_synopsis = story_p
                from_abbrev = True

        # 0-b. 「作者」表記による分割（独立したスペックセクションが存在せず、作者の次が概要内容でない事を確認して切り分け）
        if not has_strong_spec and not found_overview and not found_synopsis:
            for sk, scontent in valid_sections.items():
                spec_p, story_p = cls._split_by_author(scontent)
                if spec_p and story_p:
                    found_overview = spec_p
                    found_synopsis = story_p
                    synopsis_key = sk
                    from_abbrev = True
                    break

        if not has_strong_spec and not found_overview and not found_synopsis and not valid_sections and description:
            spec_p, story_p = cls._split_by_author(description)
            if spec_p and story_p:
                found_overview = spec_p
                found_synopsis = story_p
                from_abbrev = True

        # 0-c. 物語本文＋スペックブロックの分割（独立したスペックセクションが存在せず、1つのセクション内に物語とスペックブロックが同居している場合）
        if not has_strong_spec and not found_overview and not found_synopsis:
            # メイン説明文が存在する場合、最優先でチェック
            if main_desc:
                spec_p, story_p = cls._split_narrative_and_spec_block(main_desc)
                if spec_p and story_p:
                    found_overview = spec_p
                    found_synopsis = story_p
                    from_abbrev = True

        if not has_strong_spec and not found_overview and not found_synopsis:
            for sk, scontent in valid_sections.items():
                spec_p, story_p = cls._split_narrative_and_spec_block(scontent)
                if spec_p and story_p:
                    found_overview = spec_p
                    found_synopsis = story_p
                    synopsis_key = sk
                    from_abbrev = True
                    break

        if not has_strong_spec and not found_overview and not found_synopsis and description:
            spec_p, story_p = cls._split_narrative_and_spec_block(description)
            if spec_p and story_p:
                found_overview = spec_p
                found_synopsis = story_p
                from_abbrev = True

        # 1-a. 明示的な強いあらすじ見出し（略称分割されていない場合）
        if not found_synopsis:
            for k in strong_synopsis_keys:
                for sk in valid_sections:
                    if k in sk:
                        found_synopsis = valid_sections[sk]
                        synopsis_key = sk
                        break
                if found_synopsis:
                    break

        # 1-b. 強いあらすじ見出しがない場合、内容が「story」と判定されたセクションを採用
        if not found_synopsis:
            for sk, stype in section_types.items():
                if stype == "story":
                    found_synopsis = valid_sections[sk]
                    synopsis_key = sk
                    break

        # 1-c. それでもなければ main_desc が story かどうか
        if not found_synopsis and main_desc_type == "story":
            found_synopsis = main_desc

        # 2. 概要 (Overview) の探索（略称分割されていない場合）
        if not found_overview:
            # 2-a. 明示的な強いスペック見出し
            for k in strong_spec_keys:
                for sk in valid_sections:
                    if sk == synopsis_key:
                        continue
                    if k in sk:
                        found_overview = valid_sections[sk]
                        break
                if found_overview:
                    break

        # 2-b. 個別スペックセクション（プレイ人数、時間など）があれば合成
        if not found_overview:
            matched_spec_keys = [k for k in spec_field_keys if any(k == sk or k in sk for sk in valid_sections if sk != synopsis_key)]
            if matched_spec_keys:
                spec_parts = []
                for k in spec_field_keys:
                    for sk in valid_sections:
                        if sk == synopsis_key:
                            continue
                        if k == sk or k in sk:
                            val = valid_sections[sk].strip()
                            if val.startswith(k):
                                spec_parts.append(val)
                            else:
                                spec_parts.append(f"{k}：{val}")
                            break
                if spec_parts:
                    found_overview = "\n".join(spec_parts)

        # 2-c. 内容が「spec」と判定されたセクションを採用
        if not found_overview:
            for sk, stype in section_types.items():
                if sk == synopsis_key:
                    continue
                if stype == "spec":
                    found_overview = valid_sections[sk]
                    break

        # 2-d. main_desc が spec と判定され、あらすじとして使われていない場合
        if not found_overview and main_desc and main_desc.strip() != (found_synopsis or "").strip():
            if main_desc_type == "spec":
                found_overview = main_desc.strip()

        # 2-e. まだ概要が空で main_desc があれば採用
        if not found_overview and main_desc and main_desc.strip() != (found_synopsis or "").strip():
            found_overview = main_desc.strip()

        # 2-f. まだ概要が空で、あらすじ以外のセクションがあれば採用
        if not found_overview:
            for sk in valid_sections:
                if sk != synopsis_key:
                    found_overview = valid_sections[sk]
                    break

        # フォールバック処理
        synopsis = found_synopsis or description
        synopsis = re.sub(r'[\u200b-\u200f\u202a-\u202e\ufeff]', '', synopsis).strip()

        overview = found_overview
        if not overview:
            # フォールバック1: あらすじからの要約
            if found_synopsis:
                clean_lines = [l.strip() for l in found_synopsis.splitlines() if l.strip()]
                full_oneline = " ".join(clean_lines)
                if len(full_oneline) <= 120:
                    overview = full_oneline
                else:
                    paras = [p.strip() for p in found_synopsis.split("\n\n") if p.strip()]
                    first_block = " ".join(line.strip() for line in paras[0].splitlines() if line.strip()) if paras else full_oneline
                    overview = first_block if len(first_block) <= 120 else first_block[:117] + "..."
            else:
                # フォールバック2: 見出しがない場合のスペック・冒頭ブロック抽出
                lines = [line.strip() for line in description.splitlines() if line.strip()]
                filtered_lines = []
                for l in lines:
                    if re.match(r'^[\-\=＿_~〜*]{3,}$', l):
                        continue
                    if re.match(r'^(?:https?://|おかげさまで|ありがとう|更新|BOOTH|DL|ダウンロード)', l):
                        continue
                    filtered_lines.append(l)
                if filtered_lines:
                    block_lines = []
                    for fl in filtered_lines[:5]:
                        block_lines.append(fl)
                        if fl.endswith("。") or fl.endswith("！"):
                            break
                    overview = "\n".join(block_lines)
                    if len(overview) > 300:
                        overview = overview[:297] + "..."
                elif lines:
                    overview = lines[0][:117] + "..."
                else:
                    overview = ""

        overview = re.sub(r'[\u200b-\u200f\u202a-\u202e\ufeff]', '', overview).strip()
        if len(overview) > 400 and not from_abbrev:
            overview = overview[:397] + "..."

        return overview, synopsis

    @classmethod
    def extract_from_url(cls, url: str, fetch_image: bool = True) -> dict:
        """URLから直接情報を取得・抽出する（画像バイナリも取得可能）"""
        html_text = cls.fetch_html(url)
        data = cls.extract_from_html(html_text, url=url)
        data["image_bytes"] = None
        if fetch_image and data.get("image_url"):
            data["image_bytes"] = cls.fetch_image_bytes(data["image_url"])
        return data
