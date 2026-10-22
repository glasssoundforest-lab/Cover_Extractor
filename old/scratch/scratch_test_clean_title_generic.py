import re

SYSTEM_PATTERNS = [
    ("新クトゥルフ神話TRPG", [r"新クトゥルフ神話trpg", r"新coc", r"coc7th", r"coc7版", r"第7版"]),
    ("クトゥルフ神話TRPG", [r"クトゥルフ神話trpg", r"クトゥルフ神話", r"coc6th", r"coc6版", r"call of cthulhu", r"\bcoc\b"]),
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

def clean_title(title: str) -> str:
    if not title:
        return ""
    t = title.strip()

    # 1. 『...』 や 「...」 や 《...》 が含まれている場合
    m = re.search(r"[『「《]([^』」》]+)[』」》]", t)
    if m:
        before = t[:m.start()].strip()
        after = t[m.end():].strip()
        inner = m.group(1).strip()

        # システム名および一般タグのパターンを動的合成
        sys_tokens = []
        for name, pats in SYSTEM_PATTERNS:
            sys_tokens.append(re.escape(name))
            for p in pats:
                sys_tokens.append(p)
        general_tags = [
            r"ペアマーダーミステリー", r"マーダーミステリー", r"マダミス", r"ペアマダ",
            r"ストーリープレイング", r"ストプレ",
            r"TRPGシナリオ", r"TRPG", r"シナリオ集", r"シナリオ",
            r"キャンペーン", r"タイマン", r"ソロ", r"公式", r"無料版?", r"PDF版?", r"DL版?",
            r"第[0-9０-９]+版"
        ]
        all_noise = sys_tokens + general_tags
        noise_core = "|".join(all_noise)
        noise_pat = rf"^(?:【[^】]*】|\[[^\]]*\]|［[^］]*］|\([^\)]*\)|（[^）]*）|〈[^〉]*〉|{noise_core}|[!！★◆●▼▲\s:：／/\-–—])*$"

        is_before_noise = not before or bool(re.match(noise_pat, before, re.IGNORECASE))
        is_after_noise = not after or bool(re.match(noise_pat, after, re.IGNORECASE))

        if is_before_noise and is_after_noise and inner:
            return inner

    # 2. 『』の内側抽出が適用できない場合、先頭のタグ・システム名プレフィックスを繰り返し除去
    prefix_tags = [
        r"【[^】]+】", r"\[[^\]]+\]", r"［[^］]+］", r"\([^\)]+\)", r"（[^）]+）", r"〈[^〉]+〉",
        r"ペアマーダーミステリー", r"マーダーミステリー", r"マダミス", r"ペアマダ",
        r"新クトゥルフ神話TRPG", r"クトゥルフ神話TRPG", r"クトゥルフ神話", r"CoC(?:6th|7th)?", r"新CoC",
        r"エモクロアTRPG", r"エモクロア",
        r"ストーリープレイング", r"ストプレ",
        r"シノビガミ", r"インセイン", r"マギカロギア", r"ダブルクロス(?:\s*The\s*3rd\s*Edition)?", r"DX3rd",
        r"ソード・ワールド2\.[05]", r"SW2\.[05]", r"フタリソウサ", r"ネクロニカ", r"フィアスコ",
        r"アリアンロッド(?:2E)?", r"ステラナイツ", r"ゆうやけこやけ",
        r"TRPGシナリオ", r"TRPG", r"シナリオ集", r"シナリオ", r"公式", r"無料版?", r"PDF版?", r"DL版?"
    ]
    prefix_pattern = rf"^(?:{'|'.join(prefix_tags)})[\s:：／/\-–—]*"

    while True:
        new_t = re.sub(prefix_pattern, "", t, count=1, flags=re.IGNORECASE).strip()
        if new_t == t:
            break
        t = new_t

    # 先頭と末尾の囲み記号の除去
    if len(t) >= 2:
        for open_c, close_c in [("『", "』"), ("「", "」"), ("《", "》"), ("【", "】"), ("〈", "〉")]:
            if t.startswith(open_c) and t.endswith(close_c):
                t = t[1:-1].strip()
                break

    return t or title.strip()

cases = [
    ("【CoC6th】[無料]『海も枯れるまで』", "海も枯れるまで"),
    ("ペアマーダーミステリー『ブリキノテレコピウム』", "ブリキノテレコピウム"),
    ("【ストプレ】嘘吐き", "嘘吐き"),
    ("【公式】クトゥルフ神話TRPG『コーヒー一杯分の恐怖』", "コーヒー一杯分の恐怖"),
    ("ネクロニカ『壊れた人形のワルツ』", "壊れた人形のワルツ"),
    ("ダブルクロス The 3rd Edition『Crumble Days』", "Crumble Days"),
    ("フィアスコ『ノー・エンジェルズ』", "ノー・エンジェルズ"),
    ("狂気山脈 〜邪神の山嶺〜", "狂気山脈 〜邪神の山嶺〜"),
    ("新約・コトダマの檻", "新約・コトダマの檻"),
]

for inp, expected in cases:
    res = clean_title(inp)
    status = "OK" if res == expected else f"FAIL (got {res!r})"
    print(f"[{status:4}] {inp} -> {res}")
