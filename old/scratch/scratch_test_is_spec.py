import sys
import re
import html

sys.stdout.reconfigure(encoding='utf-8')

def is_spec_content(text: str) -> bool:
    """テキストがスペック情報（人数、時間、システム、難易度等）を中心とするものかを判定"""
    if not text:
        return False
    spec_keywords = [
        "人数", "時間", "推奨", "pl", "gm", "システム", "舞台", "ロスト",
        "難易度", "ココフォリア", "形式", "傾向", "探索者", "技能", "シナリオ",
        "所要時間", "プレイ人数", "想定時間"
    ]
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return False
    # 箇条書き記号で始まる行の割合
    bullet_lines = sum(1 for l in lines if re.match(r'^[・\-\*■◆●★:：]', l))
    bullet_ratio = bullet_lines / len(lines)

    # スペックキーワードのヒット数
    text_lower = text.lower()
    keyword_hits = sum(1 for kw in spec_keywords if kw in text_lower)

    # 箇条書きが多いか、スペックキーワードが複数含まれていればスペックと判定
    if bullet_ratio >= 0.4 or keyword_hits >= 3:
        return True
    return False

# テスト1: ブリキノテレコピウムのメイン説明
test_buriki_main = """
ペアマダ×スチームパンク

・推理難易度★★★☆☆
・ココフォリア使用有り
・PL6人＋GM1人
・プレイ時間推定4時間
"""
print("Buriki main is spec:", is_spec_content(test_buriki_main))

# テスト2: コーヒー一杯分の恐怖の「シナリオ情報」
test_coffee_info = """
新クトゥルフ神話TRPG
プレイ時間：30分-1時間　程度
プレイ人数：2-4人　推奨
舞台：現代日本
"""
print("Coffee info is spec:", is_spec_content(test_coffee_info))

# テスト3: コーヒー一杯分の恐怖の「シナリオ概要」
test_coffee_summary = """
舞台は現代の日本。寒さの厳しい2月の冬。
探索者たちは初めて入った喫茶店で、名状し難い体験をする。
探索できるポイントが明示されており、短い時間でプレイできるようになっている。

著：内山靖二郎（アーカム・メンバーズ）
"""
print("Coffee summary is spec:", is_spec_content(test_coffee_summary))

# テスト4: ブリキノテレコピウムの「あらすじ」
test_buriki_synopsis = """
ここはマキナ国。
産業革命。
人類の叡智が急激に発展した世界。
機械の登場により、人類は都市ユーフォリアで安寧を手に入れた。
そう人類は。
"""
print("Buriki synopsis is spec:", is_spec_content(test_buriki_synopsis))
