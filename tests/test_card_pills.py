"""書架カードのシステム・人数ピルアイコンの検証テスト (tests/test_card_pills.py)"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from gui_qt.components.card_pills import system_pill_info, players_pill_info, players_count, PLAYERS_COLORS
from gui_qt.components.scenario_card import ScenarioCard


class TestCardPills(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def test_system_labels_and_colors(self):
        names = {
            "クトゥルフ神話TRPG": "CoC", "新クトゥルフ神話TRPG": "CoC", "CoC": "CoC",
            "マーダーミステリー": "マダミス", "マダミス": "マダミス",
            "ストーリープレイング": "ストプレ", "ストプレ": "ストプレ",
            "シノビガミ": "その他", "": "その他", None: "その他",
        }
        colors = set()
        for name, label in names.items():
            got, color = system_pill_info(name)
            self.assertEqual(got, label, name)
            colors.add((label, color))
        self.assertEqual(len({c for _l, c in colors}), 4, "システムごとに色が違わない")

    def test_players_colors_differ_per_count(self):
        colors = [players_pill_info(t)[1] for t in ("1人", "2人", "3人", "4人", "5人以上")]
        self.assertEqual(len(set(colors)), 5)
        self.assertEqual(players_pill_info("6人")[1], PLAYERS_COLORS[5])
        self.assertEqual(players_pill_info("タイマン")[1], PLAYERS_COLORS[1])
        self.assertEqual(players_count("2〜4人"), 4)
        self.assertIsNone(players_pill_info(""))
        self.assertEqual(players_pill_info("3")[0], "3人")

    def test_card_has_pills(self):
        item = (1, "x.pdf", "題", "マーダーミステリー", "4人", "", "", "", None, 0, 0)
        card = ScenarioCard(item, "small")
        self.assertEqual(card.system_pill.text(), "マダミス")
        self.assertEqual(card.players_pill.text(), "4人")
        self.assertTrue(card.meta_label.isHidden())
        item = (2, "y.pdf", "題", "", "", "3時間", "", "", None, 0, 0)
        card = ScenarioCard(item, "medium")
        self.assertEqual(card.system_pill.text(), "その他")
        self.assertIsNone(card.players_pill)
        self.assertEqual(card.meta_label.text(), "3時間")

    def test_player_tags_are_color_coded(self):
        from gui_qt.components.card_pills import player_tag_color, resolve_tag_color
        from gui_qt.components.ornate import PillTag

        tags = ["1PL", "2PL", "3PL", "4PL", "5PL以上"]
        colors = [player_tag_color(t) for t in tags]
        self.assertEqual(len(set(colors)), 5)
        self.assertEqual(colors, [PLAYERS_COLORS[i] for i in range(1, 6)])
        self.assertEqual(player_tag_color("2〜4PL"), PLAYERS_COLORS[4])
        self.assertIsNotNone(player_tag_color("GMレス"))
        self.assertIsNone(player_tag_color("ホラー"))
        self.assertIsNone(player_tag_color("2時間"))
        # 色を決めていないタグは人数の色、ユーザーが選んだ色は尊重する
        self.assertEqual(resolve_tag_color("3PL", "#546e7a"), PLAYERS_COLORS[3])
        self.assertEqual(resolve_tag_color("3PL", None), PLAYERS_COLORS[3])
        self.assertEqual(resolve_tag_color("3PL", "#123456"), "#123456")
        self.assertEqual(resolve_tag_color("ホラー", "#546e7a"), "#546e7a")
        self.assertEqual(PillTag("3PL", color="#546e7a", is_checkable=False).tag_color, PLAYERS_COLORS[3])

    def test_gm_plus_players_extracts_players_only(self):
        from core.web_extractor import WebScenarioExtractor as W

        text = "プレイ人数：GM1人 + 2人\n　　　　　　GMレスの場合は2人\nプレイ時間：2.5時間"
        self.assertEqual(W._extract_players(text), "2人")
        self.assertEqual(W._extract_players("人数：KP1名 + PL2〜3名"), "2〜3人")


if __name__ == "__main__":
    unittest.main()
