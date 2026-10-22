import re
import html

def extract_sections_from_html(html_content: str) -> dict:
    sections = {}

    # 1. BOOTH等の shop__text または明確なセクションコンテナ
    shop_sections = re.findall(
        r'<(?:section|div|article)[^>]*class=[\'"][^\'"]*(?:shop__text|item-section|scenario-section)[^\'"]*[\'"][^>]*>(.*?)</(?:section|div|article)>',
        html_content, re.DOTALL | re.IGNORECASE
    )
    for sec in shop_sections:
        h_m = re.search(r'<h[1-6][^>]*>(.*?)</h[1-6]>', sec, re.DOTALL | re.IGNORECASE)
        heading = re.sub(r'<[^>]+>', '', h_m.group(1)).strip() if h_m else ""
        body = re.sub(r'<h[1-6][^>]*>.*?</h[1-6]>', '', sec, flags=re.DOTALL | re.IGNORECASE)
        body = re.sub(r'<br\s*/?>', '\n', body, flags=re.IGNORECASE)
        body = re.sub(r'</p>', '\n', body, flags=re.IGNORECASE)
        body = re.sub(r'<[^>]+>', '', body)
        body = html.unescape(body).strip()
        body = re.sub(r'[\u200b-\u200f\u202a-\u202e\ufeff]', '', body)
        clean_h = re.sub(r'^[【\[■◆▼●★*#・\-\s]+|[】\]:：\s\-]+$', '', heading).strip()
        if clean_h and body:
            sections[clean_h] = body

    # 2. 見つからなかった場合の汎用見出しパーサー
    if not sections:
        # bodyタグ内のコンテンツを対象にする
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
            raw_body = re.sub(r'<[^>]+>', '', raw_body)
            body_text = html.unescape(raw_body).strip()
            body_text = re.sub(r'[\u200b-\u200f\u202a-\u202e\ufeff]', '', body_text)
            if clean_h and body_text and len(body_text) < 5000:
                sections[clean_h] = body_text

    return sections

# 一般的なHTMLのテスト
sample_html = """
<html>
<body>
  <div class="content">
    <h2>シナリオスペック</h2>
    <p>人数：3〜4人<br>時間：4時間</p>
    <h2>あらすじ</h2>
    <p>霧の立ち込める夜、探索者たちは古い洋館へと辿り着いた。</p>
  </div>
</body>
</html>
"""
res = extract_sections_from_html(sample_html)
print("Generic HTML extraction:", list(res.keys()))
for k, v in res.items():
    print(f"[{k}]: {v}")
