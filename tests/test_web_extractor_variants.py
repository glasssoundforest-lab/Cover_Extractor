"""BOOTH 等の商品ページの書き方の揺れに対する抽出テスト (tests/test_web_extractor_variants.py)

これまでに修正した取り込み（題名の飾り・人数・時間・概要とあらすじの切り分け）と同じ系統で、
今後出てきそうな書き方をまとめて確かめる。

1. 題名: 前後に付くシステム名・SPLL・本文無料・人数・対応版・読みの副題などを除く
2. 人数: プレイヤー表記、全角 ＰＬ、HO 番号付き、漢数字、両方に単位が付く範囲など
3. 時間: h 表記の範囲、短い説明を挟む表記、「半」「日」単位、半角チルダ
4. 見出し: ◇ ― ＜＞ ☆ 『』 ━ † § などの飾りや英語の見出し、見出しなしの区切り線
5. 誤認しないこと: セリフや評価（★★★☆☆）の行を見出し・区切り線として扱わない
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.web_extractor import WebScenarioExtractor

STORY = (
    "ある雨の夜、あなたのもとに一通の手紙が届いた。\n"
    "差出人は十年前に亡くなったはずの友人だった。\n"
    "手紙に記された住所へ向かったあなたは、古びた洋館の前に立つ。"
)
SPEC = "人数：2～3人\n時間：ボイセ4～5時間\n推奨技能：目星、聞き耳\nロスト率：低"
BODY = f"■あらすじ\n{STORY}\n■概要\n{SPEC}"


def booth_page(title, description="", sections=()):
    """BOOTH の商品ページに似せた HTML（説明文は <br> 区切り、追加の説明は shop__text セクション）"""
    secs = "".join(
        f'<section class="shop__text"><h2>{h}</h2><p>{b.replace(chr(10), "<br>")}</p></section>'
        for h, b in sections
    )
    return (
        f"<html><head><title>{title} - テスト工房 - BOOTH</title></head><body>"
        f'<div class="js-market-item-detail-description">{description.replace(chr(10), "<br>")}</div>'
        f"{secs}</body></html>"
    )


def extract(html):
    return WebScenarioExtractor.extract_from_html(html, url="https://test.booth.pm/items/1")


class TestTitleVariants(unittest.TestCase):
    CASES = [
        ("【CoC6th】廻る灯籠【SPLL:E123456】", "廻る灯籠"),
        ("新クトゥルフ神話TRPGシナリオ『星を喰む』", "星を喰む"),
        ("【エモクロアTRPG】夜明けの標本｜本文無料", "夜明けの標本"),
        ("白昼夢の檻【CoC6版/新クトゥルフ対応】", "白昼夢の檻"),
        ("マーダーミステリー『嘘つきの晩餐』（4人用）", "嘘つきの晩餐"),
        ("CoC「月下の約束」 / 2PL / 本文無料", "月下の約束"),
        ("【無料】クトゥルフ神話TRPGシナリオ「硝子の海」", "硝子の海"),
        ("CoCシナリオ『檻の中の聖女』【SPLL:E199999】【R18G】", "檻の中の聖女"),
        ("灰色の楽園（CoC6版／SPLL:E188888）", "灰色の楽園"),
        ("CoC6th『きみのいない夏』 #SPLL:E177777", "きみのいない夏"),
        ("【CoCシナリオ】黄昏図書館 -禁書の頁-", "黄昏図書館 -禁書の頁-"),
        ("ひとりぼっちの天文台【新クトゥルフ神話TRPG】【タイマン】", "ひとりぼっちの天文台"),
        ("《深淵の聖歌隊》CoC7版対応シナリオ", "深淵の聖歌隊"),
        ("【CoC新7版】《夜鳴きの塔》【無料】", "夜鳴きの塔"),
        ("エモクロアTRPGシナリオ「花葬」｜SPLL:E101010", "花葬"),
        ("CoC6th/7th両対応『鏡の国の晩餐会』", "鏡の国の晩餐会"),
        ("CoC『3人の魔女』", "3人の魔女"),
        ("霧の街のレクイエム", "霧の街のレクイエム"),
        ("【クトゥルフ神話TRPG】 蒼穹のアトラス 【SPLL:E1】", "蒼穹のアトラス"),
        ("CoCシナリオ「残響」-ZANKYO-", "残響"),
    ]

    def test_titles(self):
        for raw, expected in self.CASES:
            with self.subTest(raw=raw):
                self.assertEqual(extract(booth_page(raw, BODY))["title"], expected)


class TestPlayersVariants(unittest.TestCase):
    CASES = [
        ("プレイヤー：3人", "3人"),
        ("人数：３～４ＰＬ", "3～4人"),
        ("人数：2人用", "2人用"),
        ("推奨人数：2-3人（最大4人）", "2-3人"),
        ("人数：HO1・HO2の2人固定", "2人固定"),
        ("PL：4人（秘匿HOあり）", "4人"),
        ("人数：KPC＋PL1人", "1人"),
        ("人数：1～4PL", "1～4人"),
        ("人数：二人用", "2人用"),
        ("人数：3PL推奨", "3人"),
        ("人数：ソロ（KPレス）", "1人"),
        ("人数：KP＋PL2～4人", "2～4人"),
        ("人数：PL1～2名", "1～2人"),
        ("人数：三人固定", "3人固定"),
        ("PL人数：３人（KPC込み）", "3人"),
        ("人数：1PL〜2PL", "1〜2人"),
        ("プレイ人数 ： ２ 名", "2人"),
        ("人数：四人", "4人"),
        ("推奨プレイヤー数：2～4人", "2～4人"),
    ]

    def test_players(self):
        for line, expected in self.CASES:
            with self.subTest(line=line):
                body = f"■あらすじ\n{STORY}\n■概要\n{line}\n時間：3時間\n推奨技能：目星\nロスト率：低"
                self.assertEqual(extract(booth_page("CoC『人数』", body))["players"], expected)


class TestDurationVariants(unittest.TestCase):
    CASES = [
        ("時間：3h〜4h", "3時間〜4時間"),
        ("プレイ時間：短め（2時間程度）", "2時間"),
        ("プレイ時間：ボイセ約3時間", "3時間"),
        ("プレイ時間：4時間半", "4時間半"),
        ("時間：ボイセ1.5～2時間", "1.5～2時間"),
        ("想定プレイ時間：3時間", "3時間"),
        ("所要時間：テキセ2日", "2日"),
        ("時間：90分", "90分"),
        ("時間：3~4時間", "3~4時間"),
        ("所要時間：約30分～1時間", "30分～1時間"),
        ("プレイ時間：約３時間～４時間", "3時間～4時間"),
        ("所要時間：テキセ２～３日", "2～3日"),
        ("時間：2.5h", "2.5時間"),
        ("時間：５時間程度（ボイセ）", "5時間"),
    ]

    def test_durations(self):
        for line, expected in self.CASES:
            with self.subTest(line=line):
                body = f"■あらすじ\n{STORY}\n■概要\n人数：2人\n{line}\n推奨技能：目星\nロスト率：低"
                self.assertEqual(extract(booth_page("CoC『時間』", body))["duration"], expected)


class TestHeadingVariants(unittest.TestCase):
    HEADINGS = [
        ("◇あらすじ◇", "◇概要◇"), ("―あらすじ―", "―概要―"), ("＜あらすじ＞", "＜概要＞"),
        ("≪あらすじ≫", "≪概要≫"), ("☆あらすじ", "☆概要"), ("✿あらすじ✿", "✿概要✿"),
        ("SYNOPSIS", "OVERVIEW"), ("◆◇あらすじ◇◆", "◆◇概要◇◆"), ("- あらすじ -", "- 概要 -"),
        ("▶あらすじ", "▶シナリオ概要"), ("『あらすじ』", "『概要』"), ("○あらすじ", "○概要"),
        ("〔あらすじ〕", "〔概要〕"), ("━━ あらすじ ━━", "━━ 概要 ━━"), ("▽あらすじ", "▽概要"),
        ("■ Story", "■ Spec"), ("【 あらすじ 】", "【 概要 】"), ("あらすじ：", "概要："),
        ("†あらすじ†", "†概要†"), ("✧ Story ✧", "✧ Spec ✧"), ("▍あらすじ", "▍概要"),
        ("§あらすじ", "§概要"), ("■□あらすじ□■", "■□概要□■"), ("Synopsis:", "Information:"),
        ("＊あらすじ＊", "＊概要＊"),
    ]

    def test_decorated_headings(self):
        for syn_head, spec_head in self.HEADINGS:
            with self.subTest(heading=syn_head):
                data = extract(booth_page("CoC『見出し』", f"{syn_head}\n{STORY}\n\n{spec_head}\n{SPEC}"))
                self.assertEqual(data["synopsis"], STORY)
                self.assertEqual(data["overview"], SPEC)

    def test_overview_before_synopsis(self):
        data = extract(booth_page("CoC『順序』", f"◇概要◇\n{SPEC}\n\n◇あらすじ◇\n{STORY}"))
        self.assertEqual(data["synopsis"], STORY)
        self.assertEqual(data["overview"], SPEC)

    def test_no_heading_with_separator(self):
        data = extract(booth_page("CoC『見出しなし』", f"{STORY}\n\n＊＊＊＊＊\n\n{SPEC}"))
        self.assertEqual(data["synopsis"], STORY)
        self.assertEqual(data["overview"], SPEC)

    def test_english_section_titles(self):
        data = extract(booth_page("CoC『セクション』", "", [("STORY", STORY), ("INFORMATION", SPEC)]))
        self.assertEqual(data["synopsis"], STORY)
        self.assertEqual(data["overview"], SPEC)


class TestNoFalseHeadings(unittest.TestCase):
    def test_dialogue_line_is_not_heading(self):
        story = "少女は言った。\n「概要は以上よ」\n扉の向こうで、何かが息をひそめている。\nあなたは静かに頷いた。"
        data = extract(booth_page("CoC『セリフ』", f"■あらすじ\n{story}\n■概要\n{SPEC}"))
        self.assertEqual(data["synopsis"], story)
        self.assertEqual(data["overview"], SPEC)

    def test_rating_line_is_kept(self):
        spec = "形式：シティ\n人数：2人\n時間：3時間\n難易度★★★☆☆"
        data = extract(booth_page("CoC『評価』", f"■あらすじ\n{STORY}\n■概要\n{spec}"))
        self.assertEqual(data["synopsis"], STORY)
        self.assertEqual(data["overview"], spec)


if __name__ == "__main__":
    unittest.main()
