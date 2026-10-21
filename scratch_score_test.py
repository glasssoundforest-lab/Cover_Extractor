import re

def score_section_type(text: str) -> dict:
    """テキストがあらすじ（story）かスペック（spec）かをスコアリングして判定"""
    if not text:
        return {"type": "unknown", "story_score": 0, "spec_score": 0}
    
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return {"type": "unknown", "story_score": 0, "spec_score": 0}

    spec_score = 0
    story_score = 0

    # 1. 箇条書き・キーバリュー形式の検出
    for l in lines:
        # キーバリュー形式（例: "人数: 3人", "システム：CoC", "舞台: 現代"）
        if re.match(r'^(?:プレイ)?(?:人数|時間|システム|舞台|推奨|ロスト|形式|難易度|傾向|ハンドアウト|HO|日程|ツール)[:：\s]', l):
            spec_score += 2
        # 箇条書き記号
        elif re.match(r'^[・\-\*■◆●★☆]', l):
            spec_score += 1
        # 文末が「。」「した」「する」「いる」「だ」「である」「――」「……」「！」
        if re.search(r'(?:[。！？」』]|(?:した|する|いる|だ|である|た|ない|れる|られる|――|……))$', l):
            story_score += 1
        # セリフ引用
        if "「" in l and "」" in l:
            story_score += 2

    # ストーリー頻出語
    story_words = ["あなた", "探索者たち", "彼", "彼女", "目が覚める", "事件", "世界", "運命", "記憶", "真実"]
    for w in story_words:
        if w in text:
            story_score += 1

    section_type = "story" if story_score > spec_score else "spec"
    return {"type": section_type, "story_score": story_score, "spec_score": spec_score}

cases = [
    ("Coffee info", "新クトゥルフ神話TRPG\nプレイ時間：30分-1時間　程度\nプレイ人数：2-4人　推奨\n舞台：現代日本"),
    ("Coffee summary", "舞台は現代の日本。寒さの厳しい2月の冬。\n探索者たちは初めて入った喫茶店で、名状し難い体験をする。\n探索できるポイントが明示されており、短い時間でプレイできるようになっている。\n\n著：内山靖二郎（アーカム・メンバーズ）"),
    ("Buriki main", "ペアマダ×スチームパンク\n\n・推理難易度★★★☆☆\n・ココフォリア使用有り\n・PL6人＋GM1人\n・プレイ時間推定4時間"),
    ("Buriki synopsis", "ここはマキナ国。\n産業革命。\n人類の叡智が急激に発展した世界。\n機械の登場により、人類は都市ユーフォリアで安寧を手に入れた。\nそう人類は。\n\nでは、機械は？"),
    ("Katashiro", "探索者は、目が覚めると病院にいた。\n医者が言うには、雷に打たれたらしい。\nそれ以前の記憶は、失われている。"),
    ("Usotsuki spec", "■プレイ人数\n2人( 完全GMレス )\n※GM+1PLというタイマン改変はしないでください。\n\n■プレイ時間\n30分〜1.5時間(準備・感想戦含む)"),
    ("Usotsuki synopsis", "最初に、嘘を吐いた。\n最後に、嘘を吐く。\n\n「ずっと、そばにいるからね」")
]

for name, t in cases:
    res = score_section_type(t)
    print(f"{name:16}: {res['type']:5} (story={res['story_score']}, spec={res['spec_score']})")
