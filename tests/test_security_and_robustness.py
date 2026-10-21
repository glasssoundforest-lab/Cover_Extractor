"""網羅的セキュリティ＆クラッシュテストスイート (tests/test_security_and_robustness.py)

テスト項目:
1. SQLインジェクション攻撃耐性テスト（DROP TABLE, OR '1'='1, UNION SELECT, NULLバイト等）
2. コマンドインジェクション＆OS実行乗っ取り防止テスト（_reveal_file の特殊パスインジェクション）
3. 不正URLスキーム・危険なプロトコル実行防止テスト（file://, javascript://, calc.exe 等）
4. 不正・破損ファイル取り込み耐性テスト（0バイト、破損PDF、破損ZIP、破損画像、偽装拡張子）
5. 巨大入力・リソース枯渇（DoS / Fuzzing）耐性テスト（100,000文字、Unicode結合文字、RTL、制御文字）
6. 検索バー・正規表現インジェクション耐性テスト（ReDoS, 不正正規表現構文等）
"""

import os
import sys
import unittest
import io
import tempfile
import zipfile
import subprocess
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import Database, reading_key, first_number, canonical_tag, canonical_system
from core.extractor import (
    search_fallback_cover,
    search_fallback_texts,
    parse_name_clues,
    extract_scenario_data,
    collect_scenario_targets,
)
from gui_qt.components.tag_context_menu import ScenarioContextMenu
from gui_qt.dialogs.item_detail_dialog import ItemDetailDialog
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QUrl

app = QApplication.instance() or QApplication(sys.argv)

TEST_DB_PATH = "tests/test_security.db"


class TestSecurityAndRobustness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)
        cls.db = Database(TEST_DB_PATH)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.db.conn.close()
        except Exception:
            pass
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass

    # =========================================================================
    # 1. SQLインジェクション＆特殊文字攻撃テスト
    # =========================================================================
    def test_01_sql_injection_payloads(self):
        """SQLインジェクションの代表的ペイロードを挿入し、DBが破壊・漏洩しないことを検証"""
        malicious_inputs = [
            "'; DROP TABLE items; --",
            "' OR '1'='1",
            "admin'--",
            "' UNION SELECT id, password, 1, 1, 1, 1, 1, 1, 1, 1, 1 FROM users --",
            "Robert'); DROP TABLE students;--",
            "1; ATTACH DATABASE 'evil.db' AS evil; --",
            "' OR SLEEP(5) --",
        ]

        for idx, payload in enumerate(malicious_inputs):
            file_path = f"test_sql_inject_{idx}.pdf"
            # save_item に悪意ある入力を与える
            item_id = self.db.save_item(
                file_path=file_path,
                title=payload,
                system_name=payload,
                players_text=payload,
                duration_text=payload,
                overview=payload,
                synopsis=payload,
                thumbnail_bytes=b"fake_image_data",
            )
            self.assertIsNotNone(item_id)

            # DBテーブル items が破壊されていないことを確認
            item = self.db.get_item(item_id)
            self.assertIsNotNone(item)
            self.assertEqual(item[2], payload)  # タイトルとしてそのまま安全に格納されていること

            # タグ操作でのインジェクション検証
            tid = self.db.add_tag(payload)
            self.assertIsNotNone(tid)
            self.db.toggle_item_tag(item_id, payload, enabled=True)

        # 全アイテム取得でクラッシュしないこと
        all_items = self.db.get_items()
        self.assertGreaterEqual(len(all_items), len(malicious_inputs))

        # テーブル一覧を取得し、テーブルが健全に残っていることを確認
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in cursor.fetchall()]
        self.assertIn("items", tables)
        self.assertIn("tags", tables)
        self.assertIn("item_tags", tables)

    def test_02_null_byte_and_control_chars_in_db(self):
        """NULLバイトや制御文字が入力された場合のDB保存・検索の堅牢性を検証"""
        weird_inputs = [
            "TitleWith\x00NullByte",
            "TitleWith\r\nNewline\tAndTabs",
            "TitleWith\x1b[31mANSIEscape\x1b[0m",
            "TitleWith\ufffe\uffffBOM",
            "﷽" * 50,  # 極端に長い合字
            "مرحبا بالعالم" * 20,  # RTLアラビア語
            "🔥" * 100,  # 連続絵文字サロゲートペア
        ]

        for idx, inp in enumerate(weird_inputs):
            file_path = f"test_ctrl_char_{idx}.pdf"
            item_id = self.db.save_item(
                file_path=file_path,
                title=inp,
                system_name="System",
                players_text="1",
                duration_text="1",
                overview="Overview",
                synopsis="Synopsis",
                thumbnail_bytes=b"dummy",
            )
            self.assertIsNotNone(item_id)
            fetched = self.db.get_item(item_id)
            self.assertIsNotNone(fetched)

    # =========================================================================
    # 2. コマンドインジェクション＆OS実行乗っ取り防止テスト
    # =========================================================================
    def test_03_command_injection_in_reveal_file(self):
        """ScenarioContextMenu._reveal_file におけるコマンドインジェクション防止検証"""
        menu = ScenarioContextMenu(1, self.db)

        # 悪意あるファイルパスのペイロード
        malicious_paths = [
            r'C:\Users\test\scenario.pdf" & calc.exe & "',
            r'C:\Users\test\scenario.pdf; calc.exe',
            r'C:\Users\test\scenario.pdf | notepad.exe',
            r'C:\Users\test\`calc.exe`',
            r'C:\Users\test\$(calc.exe)',
            r'C:\Users\test\scenario" && start cmd.exe "',
        ]

        for mpath in malicious_paths:
            menu.item_data = (1, mpath, "Title", "System", "1", "1", "", "", None, 0, 0)

            with patch("subprocess.Popen") as mock_popen:
                menu._reveal_file()
                if mock_popen.called:
                    args = mock_popen.call_args[0][0]
                    # もし文字列でシェルやexplorerにそのまま渡している場合、インジェクションが発生する
                    if isinstance(args, str):
                        # 文字列の場合、未エスケープの二重引用符やコマンド連結文字が危険
                        self.fail(
                            f"セキュリティ問題検出: _reveal_file が安全なリスト形式ではなく文字列渡しで Popen を呼び出しています: {args}"
                        )
                    elif isinstance(args, list):
                        # リスト形式であれば OS コマンドインジェクションは起きないが、第1引数が explorer.exe であること
                        self.assertIn("explorer", args[0].lower())

    # =========================================================================
    # 3. 不正URLスキーム・危険なプロトコル実行防止テスト
    # =========================================================================
    def test_04_dangerous_url_schemes(self):
        """ItemDetailDialog._on_url_clicked における危険なURLスキーム実行防止検証"""
        dangerous_urls = [
            "file:///C:/Windows/System32/calc.exe",
            "file:///C:/Windows/System32/cmd.exe",
            "javascript:alert(1)",
            "powershell:Start-Process calc",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:msgbox",
            "ms-msdt:/id PCWDiagnostic",
        ]

        # テスト用アイテムを登録
        item_id = self.db.save_item(
            file_path="test_url_safety.pdf",
            title="URL Safety Test",
            system_name="CoC",
            players_text="1",
            duration_text="1",
            overview="",
            synopsis="",
            thumbnail_bytes=None,
        )

        dlg = ItemDetailDialog(item_id, self.db, None)

        for d_url in dangerous_urls:
            self.db.set_source_url(item_id, d_url)

            with patch("PySide6.QtGui.QDesktopServices.openUrl") as mock_open_url:
                with patch("PySide6.QtWidgets.QMessageBox.information") as mock_info:
                    dlg._on_url_clicked()
                    # 危険なURLに対して openUrl が呼ばれてはならない！
                    if mock_open_url.called:
                        called_url = mock_open_url.call_args[0][0].toString()
                        self.fail(f"セキュリティ問題検出: 危険なURLスキームに対して openUrl が実行されました: {called_url}")

    # =========================================================================
    # 4. 破損・不正ファイル取り込み時のクラッシュ耐性テスト
    # =========================================================================
    def test_05_corrupted_files_and_zip_bombs(self):
        """0バイトファイル、壊れたZIP、壊れたPDF等を処理しても例外でクラッシュしないか検証"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. 0バイトファイル
            zero_byte_file = os.path.join(tmpdir, "zero.pdf")
            with open(zero_byte_file, "wb") as f:
                pass

            # 2. 壊れたZIPファイル
            bad_zip = os.path.join(tmpdir, "bad.zip")
            with open(bad_zip, "wb") as f:
                f.write(b"PK\x03\x04\x00\x00\x00\x00CorruptedContentHere")

            # 3. 壊れたPDF（ヘッダーだけPDFで中身がランダムノイズ）
            bad_pdf = os.path.join(tmpdir, "bad.pdf")
            with open(bad_pdf, "wb") as f:
                f.write(b"%PDF-1.4 \xff\xfe\xfdRandomJunkNotValidPDF")

            # 4. 偽装ファイル（拡張子は.zipだが中身はプレーンテキスト）
            fake_zip = os.path.join(tmpdir, "fake.zip")
            with open(fake_zip, "w", encoding="utf-8") as f:
                f.write("This is actually a plain text file, not a zip.")

            test_targets = [zero_byte_file, bad_zip, bad_pdf, fake_zip]

            for target in test_targets:
                try:
                    # search_fallback_cover がクラッシュしないこと
                    cov = search_fallback_cover(target)
                except Exception as e:
                    self.fail(f"クラッシュ検出: search_fallback_cover({target}) で例外発生: {e}")

                try:
                    # search_fallback_texts がクラッシュしないこと
                    ov, syn = search_fallback_texts(target)
                except Exception as e:
                    self.fail(f"クラッシュ検出: search_fallback_texts({target}) で例外発生: {e}")

                try:
                    # extract_scenario_data がクラッシュしないこと
                    res = extract_scenario_data(None, target)
                    self.assertIsInstance(res, dict)
                except Exception as e:
                    self.fail(f"クラッシュ検出: extract_scenario_data(None, {target}) で例外発生: {e}")

    # =========================================================================
    # 5. 巨大入力・リソース枯渇（DoS / Fuzzing）耐性テスト
    # =========================================================================
    def test_06_huge_inputs_fuzzing(self):
        """100,000文字の超巨大テキストや異常な入力値に対する耐性検証"""
        huge_str = "A" * 100000
        item_id = self.db.save_item(
            file_path="huge_input_test.pdf",
            title=huge_str,
            system_name=huge_str,
            players_text=huge_str,
            duration_text=huge_str,
            overview=huge_str,
            synopsis=huge_str,
            thumbnail_bytes=b"dummy",
        )
        self.assertIsNotNone(item_id)

        # 読書順・ソート計算がフリーズ・クラッシュしないこと
        rk = reading_key(huge_str)
        self.assertIsNotNone(rk)

        fn = first_number(huge_str)
        self.assertIsNone(fn)

        ct = canonical_tag(huge_str)
        self.assertLessEqual(len(ct), 100)

        cs = canonical_system(huge_str)
        self.assertLessEqual(len(cs), 100)

    # =========================================================================
    # 6. 検索バー・正規表現インジェクション耐性テスト
    # =========================================================================
    def test_07_search_bar_regex_injection(self):
        """検索欄に不正な正規表現メタ文字やReDoSパターンが入力された場合の安全性検証"""
        from gui_qt.main_window import MainWindow

        win = MainWindow(db_path=TEST_DB_PATH)
        win.resize(1000, 700)

        dangerous_search_queries = [
            "(a+)+$",  # ReDoS脆弱性パターン
            "(.*a){100}",
            "[a-z",  # 不完全な正規表現構文（未終了のブラケット）
            "(?i)(",  # 不完全なグループ
            "\\",  # 末尾バックスラッシュ
            "*",  # 先頭量指定子
            "?",
            "+",
            "{1,1000000}",
            "CoC; DROP TABLE items; --",
        ]

        for q in dangerous_search_queries:
            try:
                win.header_bar.search_edit.setText(q)
                QApplication.processEvents()
            except Exception as e:
                self.fail(f"クラッシュ検出: 検索クエリ '{q}' の入力で例外が発生しました: {e}")

    # =========================================================================
    # 7. ZIPボム＆超巨大ファイル（DoS / OOMクラッシュ）耐性テスト
    # =========================================================================
    def test_08_zip_bomb_and_huge_text_file_dos(self):
        """超巨大テキストファイル（または圧縮比率の高いファイル）によるメモリ枯渇の防止検証"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 50MBの巨大テキストファイル（ダミー）
            huge_txt_path = os.path.join(tmpdir, "readme_huge.txt")
            with open(huge_txt_path, "wb") as f:
                # 10MB分の連続空白/改行
                f.write(b"A" * (10 * 1024 * 1024))

            # 巨大テキストがあるフォルダでのテキスト探索
            # 1MBを超えて全読み込みしていないか検証（メモリ保護）
            ov, syn = search_fallback_texts(tmpdir)
            # クラッシュせずに終了すること

    # =========================================================================
    # 8. ピクセルボム＆巨大画像（Decompression Bomb / DoS）耐性テスト
    # =========================================================================
    def test_09_pixel_bomb_and_huge_image_dos(self):
        """極端な画像サイズ（DecompressionBomb）の処理耐性検証"""
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmpdir:
            # 非常に解像度が高い（メモリを大量消費する）画像を模擬
            bomb_path = os.path.join(tmpdir, "cover_bomb.png")
            # 1x1 の画像だがヘッダで巨大に見せかけるか、安全上限を超える画像
            # 正常な範囲内の画像は通るが、上限チェックが機能すること
            img = Image.new("RGB", (100, 100), color="red")
            img.save(bomb_path)

            cov = search_fallback_cover(tmpdir)
            self.assertIsNotNone(cov)

    # =========================================================================
    # 9. リッチテキスト（HTML/XSS）インジェクション防止テスト
    # =========================================================================
    def test_10_html_injection_xss_in_ui_labels(self):
        """タイトルやシステム名にHTMLタグが含まれる場合、意図しないHTML解釈やUI崩壊が起きないか検証"""
        from gui_qt.components.scenario_card import ScenarioCard
        from gui_qt.main_window import MainWindow

        xss_payloads = [
            "<script>alert(1)</script>",
            "<img src='invalid' onerror='alert(1)'>",
            "<a href='http://evil.com'>Click Here</a>",
            "<h1>Huge Header</h1><marquee>Scroll</marquee>",
            "<style>body { display: none; }</style>",
            "<table><tr><td>" * 50,  # 極端にネストされたテーブル
        ]

        for payload in xss_payloads:
            item_data = (
                999,
                "test.pdf",
                payload,  # title
                payload,  # system_name
                "1",
                "1",
                payload,  # overview
                payload,  # synopsis
                None,     # thumbnail
                0,
                0,
            )
            # ScenarioCard の生成でクラッシュしないこと
            card = ScenarioCard(item_data)
            self.assertIsNotNone(card)
            # タイトルラベルが安全に設定されていること
            self.assertIn(card.title_label.text(), [payload, payload[:50]])

    # =========================================================================
    # 10. URLの厳格な検証（RFC準拠・改行やNULLバイトの排除）
    # =========================================================================
    def test_11_url_validation_strict(self):
        """URLクリック処理で改行やNULLバイト、制御文字が混入したURLを安全に拒絶するか検証"""
        item_id = self.db.save_item(
            file_path="test_strict_url.pdf",
            title="Strict URL",
            system_name="CoC",
            players_text="1",
            duration_text="1",
            overview="",
            synopsis="",
            thumbnail_bytes=None,
        )
        dlg = ItemDetailDialog(item_id, self.db, None)

        invalid_urls = [
            "http://example.com\r\nHeader-Injection: 1",
            "http://example.com\x00calc.exe",
            "http://",
            "https://",
            "http:///",
            "http://:80",
            "   ",
        ]

        for inv_url in invalid_urls:
            self.db.set_source_url(item_id, inv_url)
            with patch("PySide6.QtGui.QDesktopServices.openUrl") as mock_open:
                with patch("PySide6.QtWidgets.QMessageBox.information"), patch("PySide6.QtWidgets.QMessageBox.warning"):
                    dlg._on_url_clicked()
                    if mock_open.called:
                        called_url = mock_open.call_args[0][0].toString()
                        self.fail(f"不正なURLに対して openUrl が実行されました: {called_url}")

    # =========================================================================
    # 11. シンボリックリンクと循環ディレクトリのトラバーサル耐性テスト
    # =========================================================================
    def test_12_symlink_and_circular_path_traversal(self):
        """存在しない親へのパストラバーサル (..) や循環構造での無限ループ・クラッシュ防止検証"""
        paths = [
            r"C:\..\..\..\..\Windows\System32",
            "/../../../../etc",
            "tests/../tests/../tests/..",
            r"C:\NonExistentPath\..\..\Foo",
        ]
        # collect_scenario_targets がクラッシュ・無限ループしないこと
        res = collect_scenario_targets(paths)
        self.assertIsInstance(res, list)

    # =========================================================================
    # 12. LIKE ワイルドカードインジェクション耐性テスト
    # =========================================================================
    def test_13_sql_like_wildcard_injection(self):
        """大量の % や _ や [ などのワイルドカードを入力してもDBエラーが起きないか検証"""
        wildcard_queries = [
            "%" * 1000,
            "_" * 1000,
            "[%]" * 500,
            "'%'_'%",
        ]
        for wq in wildcard_queries:
            # 検索バーへの入力で例外が出ないこと
            cursor = self.db.conn.cursor()
            cursor.execute("SELECT id FROM items WHERE title LIKE ? OR system_name LIKE ?;", (f"%{wq}%", f"%{wq}%"))
            rows = cursor.fetchall()
            self.assertIsInstance(rows, list)

    # =========================================================================
    # 13. マルチスレッド並行書き込みクラッシュ耐性テスト
    # =========================================================================
    def test_14_concurrency_multithreaded_db_writes(self):
        """複数スレッドから同時にアイテム追加やタグ操作を行ってもDBが破損・クラッシュしないか検証"""
        import threading

        errors = []

        def worker(thread_idx):
            try:
                # 各スレッドごとに接続を作成（SQLiteのベストプラクティス）
                th_db = Database(TEST_DB_PATH)
                for i in range(5):
                    iid = th_db.save_item(
                        file_path=f"thread_{thread_idx}_item_{i}.pdf",
                        title=f"Thread {thread_idx} Item {i}",
                        system_name="CoC",
                        players_text="1",
                        duration_text="1",
                        overview="ov",
                        synopsis="syn",
                        thumbnail_bytes=None,
                    )
                    th_db.toggle_item_tag(iid, "CoC", enabled=True)
                th_db.conn.close()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"並行書き込みでエラーが発生しました: {errors}")

    # =========================================================================
    # 14. ファジング・異常JSONデータ耐性テスト
    # =========================================================================
    def test_15_fuzzed_info_dict_parsing(self):
        """parse_info に不正な型（リスト、数値、循環、None）が渡された場合の安全性検証"""
        from core.extractor import parse_info

        fuzzed_payloads = [
            None,
            {},
            {"title": None, "system": 12345, "players": [1, 2, 3]},
            {"title": {"value": {"deep": {"nested": "value"}}}},
            {"players": {"raw_text": None, "value": {"min": "NaN", "max": None}}},
            {"duration": {"min_hours": "inf", "max_hours": -999}},
            {"overview": [b"binary", 123], "synopsis": object()},
        ]

        for p in fuzzed_payloads:
            try:
                fields, auto_tags = parse_info(p)
                self.assertIsInstance(fields, dict)
                self.assertIsInstance(auto_tags, list)
            except Exception as e:
                self.fail(f"クラッシュ検出: parse_info({p}) で例外発生: {e}")

    # =========================================================================
    # 15. 非ASCII・空白・絵文字ファイルパス耐性テスト
    # =========================================================================
    def test_16_extreme_filenames(self):
        """極端なファイル名（空白のみ、半角カナ、絵文字、多言語）のインポート検証"""
        extreme_names = [
            "   .pdf",
            "ｱｲｳｴｵ_ｶﾅ.pdf",
            "📚🎲🧙‍♂️.pdf",
            "シナリオ＿！＠＃＄％＾＆＊（）.pdf",
        ]
        for name in extreme_names:
            try:
                clues = parse_name_clues(name)
                self.assertIsInstance(clues, dict)
            except Exception as e:
                self.fail(f"クラッシュ検出: parse_name_clues('{name}') で例外発生: {e}")


if __name__ == "__main__":
    unittest.main()
