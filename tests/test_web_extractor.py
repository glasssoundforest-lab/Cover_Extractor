import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.web_extractor import WebScenarioExtractor


class TestWebScenarioExtractor(unittest.TestCase):
    def test_booth_html_extraction(self):
        """BoothのHTML構造からの抽出テスト"""
        html_sample = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta property="og:title" content="狂気山脈 〜邪神の山嶺〜 - まだらの牛 - BOOTH">
            <meta property="og:description" content="【クトゥルフ神話TRPG】前人未到の狂気山脈へと挑んだ探検隊――。\n推奨人数: 3〜4人\n所要時間: 4〜6時間">
            <meta property="og:image" content="https://booth.pximg.net/c/620x620/item_123.jpg">
            <meta property="og:site_name" content="まだらの牛">
        </head>
        <body>
            <p>本文テキスト。探索者たちは南極大陸の秘境へ。</p>
        </body>
        </html>
        """
        data = WebScenarioExtractor.extract_from_html(html_sample, url="https://dappleox.booth.pm/items/1234567")
        self.assertEqual(data["title"], "狂気山脈 〜邪神の山嶺〜")
        self.assertEqual(data["author"], "まだらの牛")
        self.assertEqual(data["system"], "クトゥルフ神話TRPG")
        self.assertIn("3〜4人", data["players"])
        self.assertIn("4〜6時間", data["duration"])
        self.assertEqual(data["image_url"], "https://booth.pximg.net/c/620x620/item_123.jpg")
        self.assertIn("前人未到の狂気山脈", data["overview"])

    def test_talto_html_extraction(self):
        """TALTOのHTML構造からの抽出テスト"""
        html_sample = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>新約・コトダマの檻 | TALTO</title>
            <meta property="og:title" content="新約・コトダマの檻 | TALTO">
            <meta property="og:description" content="エモクロアTRPGシナリオ。言葉が変異する怪異に立ち向かう現代伝奇。\nプレイ人数：2〜3人\nプレイ時間：3時間">
            <meta property="og:image" content="https://talto.cc/storage/scenarios/cover_999.png">
            <meta name="author" content="ディズム">
        </head>
        <body>
            <div>シナリオ詳細本文</div>
        </body>
        </html>
        """
        data = WebScenarioExtractor.extract_from_html(html_sample, url="https://talto.cc/projects/kotodama_ori")
        self.assertEqual(data["title"], "新約・コトダマの檻")
        self.assertEqual(data["author"], "ディズム")
        self.assertEqual(data["system"], "エモクロアTRPG")
        self.assertIn("2〜3人", data["players"])
        self.assertIn("3時間", data["duration"])
        self.assertEqual(data["image_url"], "https://talto.cc/storage/scenarios/cover_999.png")

    def test_general_ogp_extraction(self):
        """一般的なWebサイトからのOGP抽出テスト"""
        html_sample = """
        <html>
        <head>
            <meta property="og:title" content="深淵の遺産">
            <meta property="og:description" content="シノビガミ現代編シナリオ。人数: 4人固定、時間: 3〜4時間">
            <meta property="og:image" content="/images/shinen.jpg">
            <meta name="author" content="忍びの里">
        </head>
        <body></body>
        </html>
        """
        data = WebScenarioExtractor.extract_from_html(html_sample, url="https://example.com/scenarios/shinen")
        self.assertEqual(data["title"], "深淵の遺産")
        self.assertEqual(data["author"], "忍びの里")
        self.assertEqual(data["system"], "シノビガミ")
        self.assertIn("4人", data["players"])
        self.assertIn("3〜4時間", data["duration"])
    def test_booth_story_playing_and_synopsis_extraction(self):
        """ストプレ作品（例: 嘘吐き）のあらすじ・概要・システム名・所要時間抽出テスト"""
        html_sample = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>【ストプレ】嘘吐き - 冷蔵庫の中身 - BOOTH</title>
            <meta property="og:title" content="【ストプレ】嘘吐き - 冷蔵庫の中身 - BOOTH">
            <meta property="og:description" content="Story Playing 嘘吐き -------------------------------------------------- おかげさまで四周年...">
            <meta property="og:image" content="https://booth.pximg.net/c/620x620/sample.jpg">
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": "【ストプレ】嘘吐き",
                "description": "Story Playing\\n嘘吐き\\n\\n--------------------------------------------------\\n\\nおかげさまで四周年を迎えることができました！\\n少しでも皆様に還元したく、本作は無料で遊べます！\\n\\n--------------------------------------------------\\n\\n■プレイ人数\\n2人( 完全GMレス )\\n※GM+1PLというタイマン改変はしないでください。\\n\\n■プレイ時間\\n30分〜1.5時間(準備・感想戦含む)\\n\\n■事前注意\\n・二人は恋人関係です。恋愛RP必須。\\n\\n■あらすじ\\n最初に、嘘を吐いた。\\n最後に、嘘を吐く。\\n\\n「ずっと、そばにいるからね」"
            }
            </script>
        </head>
        <body></body>
        </html>
        """
        data = WebScenarioExtractor.extract_from_html(html_sample, url="https://ponzu12345.booth.pm/items/8205068")
        self.assertEqual(data["title"], "嘘吐き")
        self.assertEqual(data["author"], "冷蔵庫の中身")
        self.assertEqual(data["system"], "ストーリープレイング")
        self.assertEqual(data["players"], "2人")
        self.assertEqual(data["duration"], "30分〜1.5時間")
        self.assertIn("2人", data["overview"])
        self.assertIn("30分〜1.5時間", data["overview"])
        self.assertNotIn("おかげさまで四周年", data["overview"])
        self.assertIn("最初に、嘘を吐いた。\n最後に、嘘を吐く。", data["synopsis"])
        self.assertNotIn("おかげさまで四周年", data["synopsis"])
        self.assertNotIn("■プレイ人数", data["synopsis"])

    def test_booth_buriki_extraction(self):
        """ペアマダ『ブリキノテレコピウム』のタイトル整形・あらすじ・概要・プレイ時間抽出テスト"""
        html_sample = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta property="og:title" content="ペアマーダーミステリー『ブリキノテレコピウム』 - もくもく書店 - BOOTH">
            <meta property="og:description" content="ペアマダ×スチームパンク ・推理難易度★★★☆☆ ・ココフォリア使用有り ・PL6人＋GM1人 ・プレイ時間推定4時間">
            <meta property="og:image" content="https://booth.pximg.net/c/620x620/item_7891055.jpg">
            <script type="application/ld+json">
            {
                "@context": "https://schema.org",
                "@type": "Product",
                "name": "ペアマーダーミステリー『ブリキノテレコピウム』",
                "description": "ペアマダ×スチームパンク\\n\\n・推理難易度★★★☆☆\\n・ココフォリア使用有り\\n・PL6人＋GM1人\\n・プレイ時間推定4時間"
            }
            </script>
        </head>
        <body>
            <div class="js-market-item-detail-description description">
                <p>ペアマダ×スチームパンク<br><br>・推理難易度★★★☆☆<br>・ココフォリア使用有り<br>・PL6人＋GM1人<br>・プレイ時間推定4時間</p>
            </div>
            <section class="shop__text">
                <h2>あらすじ</h2>
                <p>ここはマキナ国。<br>産業革命。<br>人類の叡智が急激に発展した世界。<br>機械の登場により、人類は都市ユーフォリアで安寧を手に入れた。<br>そう人類は。<br><br>では、機械は？<br>その傾げる首は問いかけなのか。<br>-----------------------------</p>
            </section>
            <section class="shop__text">
                <h2>キャラクター紹介</h2>
                <p>PC1 ポルックス<br>古くも新しくもない個体。<br>-----------------------------</p>
            </section>
            <section class="shop__text">
                <h2>資料内容</h2>
                <p>【GM用資料＋HOセット】<br>-----------------------------</p>
            </section>
        </body>
        </html>
        """
        data = WebScenarioExtractor.extract_from_html(html_sample, url="https://booth.pm/ja/items/7891055")
        # タイトルから「ペアマーダーミステリー」および『』が除去されていること
        self.assertEqual(data["title"], "ブリキノテレコピウム")
        self.assertEqual(data["system"], "マーダーミステリー")
        self.assertEqual(data["players"], "6人")
        self.assertEqual(data["duration"], "4時間")
        self.assertEqual(data["author"], "もくもく書店")
        # あらすじが shop__text から綺麗に抽出され、キャラクター紹介や資料内容が混ざっていないこと
        self.assertIn("ここはマキナ国。", data["synopsis"])
        self.assertIn("その傾げる首は問いかけなのか。", data["synopsis"])
        self.assertNotIn("PC1 ポルックス", data["synopsis"])
        self.assertNotIn("資料内容", data["synopsis"])
        # 概要に作品スペック（推理難易度、ココフォリア使用、プレイ時間等）が綺麗に切り出されていること
        self.assertIn("推理難易度★★★☆☆", data["overview"])
        self.assertIn("ココフォリア使用有り", data["overview"])
        self.assertIn("プレイ時間推定4時間", data["overview"])

    def test_booth_coffee_terror_extraction(self):
        """シナリオ情報が概要、シナリオ概要があらすじに正しく登録されることの検証（コーヒー一杯分の恐怖）"""
        html_sample = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta property="og:title" content="コーヒー一杯分の恐怖 - 【公式】クトゥルフ神話TRPG - BOOTH">
            <meta property="og:description" content="『新クトゥルフ神話TRPG シナリオ集 ビブリオテーク１３』の冒頭に掲載されている初心者キーパーでもプレイしやすいショート・ショート・シナリオです。">
            <meta property="og:image" content="https://booth.pximg.net/c/620x620/item_5649642.jpg">
        </head>
        <body>
            <div class="js-market-item-detail-description description">
                <p>『新クトゥルフ神話TRPG シナリオ集 ビブリオテーク１３』の冒頭に掲載されている初心者キーパーでもプレイしやすいショート・ショート・シナリオです。</p>
            </div>
            <section class="shop__text">
                <h2>シナリオ概要</h2>
                <p>舞台は現代の日本。寒さの厳しい2月の冬。<br>探索者たちは初めて入った喫茶店で、名状し難い体験をする。<br>探索できるポイントが明示されており、短い時間でプレイできるようになっている。<br><br>著：内山靖二郎（アーカム・メンバーズ）</p>
            </section>
            <section class="shop__text">
                <h2>シナリオ情報</h2>
                <p>新クトゥルフ神話TRPG<br>プレイ時間：30分-1時間　程度<br>プレイ人数：2-4人　推奨<br>舞台：現代日本</p>
            </section>
            <section class="shop__text">
                <h2>同梱物</h2>
                <p>・シナリオ<br>PDF×1（11ページ）</p>
            </section>
        </body>
        </html>
        """
        data = WebScenarioExtractor.extract_from_html(html_sample, url="https://booth.pm/ja/items/5649642")
        self.assertEqual(data["title"], "コーヒー一杯分の恐怖")
        self.assertEqual(data["system"], "新クトゥルフ神話TRPG")
        self.assertEqual(data["players"], "2-4人")
        self.assertEqual(data["duration"], "30分-1時間")

        # 概要には「シナリオ情報」の内容（スペック情報）が入ること
        self.assertIn("新クトゥルフ神話TRPG", data["overview"])
        self.assertIn("プレイ時間：30分-1時間", data["overview"])
        self.assertIn("プレイ人数：2-4人", data["overview"])
        self.assertIn("舞台：現代日本", data["overview"])

        # あらすじには「シナリオ概要」の内容（ストーリー本文）が入ること
        self.assertIn("舞台は現代の日本。寒さの厳しい2月の冬。", data["synopsis"])
        self.assertIn("探索者たちは初めて入った喫茶店で、名状し難い体験をする。", data["synopsis"])
        self.assertIn("著：内山靖二郎（アーカム・メンバーズ）", data["synopsis"])
        self.assertNotIn("同梱物", data["synopsis"])

    def test_clean_title_generalized(self):
        """汎用的なタイトル整形のテスト（接頭辞・接尾辞・システム名・タグ・括弧）"""
        cases = [
            ("【CoC6版】『生命の樹』", "生命の樹"),
            ("【公式】クトゥルフ神話TRPG『コーヒー一杯分の恐怖』PDF版", "コーヒー一杯分の恐怖"),
            ("ペアマーダーミステリー『ブリキノテレコピウム』", "ブリキノテレコピウム"),
            ("【ストプレ】嘘吐き", "嘘吐き"),
            ("狂気山脈 〜邪神の山嶺〜", "狂気山脈 〜邪神の山嶺〜"),
            ("深淵の遺産【シノビガミ】", "深淵の遺産"),
            ("カタシロ [DL版]", "カタシロ"),
            ("『夜の森の迷子たち』 - 無料版 -", "夜の森の迷子たち"),
            ("【エモクロアTRPG】変異都市 (シナリオ集)", "変異都市"),
            ("新クトゥルフ神話TRPG『カタシロ』", "カタシロ"),
        ]
        for raw, expected in cases:
            self.assertEqual(WebScenarioExtractor.clean_title(raw), expected)

    def test_extract_players_generalized(self):
        """汎用的なプレイ人数抽出のテスト（名、PL+GM、KPレス、タイマン等）"""
        self.assertEqual(WebScenarioExtractor._extract_players("プレイ人数：3〜4名 推奨"), "3〜4人")
        self.assertEqual(WebScenarioExtractor._extract_players("・PL6人＋GM1人"), "6人")
        self.assertEqual(WebScenarioExtractor._extract_players("推奨人数: 1人（ソロ）"), "1人")
        self.assertEqual(WebScenarioExtractor._extract_players("人数: KPレス"), "1人")
        self.assertEqual(WebScenarioExtractor._extract_players("PL人数：1人（タイマン）"), "1人")
        self.assertEqual(WebScenarioExtractor._extract_players("推奨人数：3名固定"), "3人固定")

    def test_content_based_hybrid_classification(self):
        """コンテンツ構造に基づくハイブリッド分類テスト（見出し名に左右されず物語とスペックを判別）"""
        # パターンA: 見出しが「シナリオ概要」で中身が箇条書きスペック、「ストーリー」に物語がある場合
        html_spec_in_overview = """
        <html>
        <body>
            <section class="shop__text">
                <h2>シナリオ概要</h2>
                <p>・プレイ人数：3〜4人<br>・プレイ時間：4時間<br>・舞台：現代日本<br>・推奨技能：目星、聞き耳</p>
            </section>
            <section class="shop__text">
                <h2>ストーリー</h2>
                <p>探索者たちは見知らぬ館で目を覚ます。<br>冷たいコンクリートの部屋。出口は見当たらない。<br>扉の向こうから、重い足音が響いてくる――。</p>
            </section>
            <section class="shop__text">
                <h2>利用規約</h2>
                <p>改変はご自由にどうぞ。自作発言は禁止です。</p>
            </section>
        </body>
        </html>
        """
        data_a = WebScenarioExtractor.extract_from_html(html_spec_in_overview)
        self.assertIn("プレイ人数：3〜4人", data_a["overview"])
        self.assertIn("推奨技能：目星、聞き耳", data_a["overview"])
        self.assertIn("探索者たちは見知らぬ館で目を覚ます。", data_a["synopsis"])
        self.assertNotIn("利用規約", data_a["overview"])
        self.assertNotIn("利用規約", data_a["synopsis"])

        # パターンB: 個別セクション（プレイ人数・プレイ時間）が分かれていて、見出し「ABOUT」に物語がある場合
        html_separated_specs = """
        <html>
        <body>
            <section class="shop__text">
                <h2>ABOUT</h2>
                <p>ここは誰も知らない霧の街。<br>失われた記憶を探すため、旅人たちは歩みを進める。<br>「信じられるのは、目の前の真実だけ」</p>
            </section>
            <section class="shop__text">
                <h2>推奨人数</h2>
                <p>2〜3人</p>
            </section>
            <section class="shop__text">
                <h2>所要時間</h2>
                <p>3時間</p>
            </section>
        </body>
        </html>
        """
        data_b = WebScenarioExtractor.extract_from_html(html_separated_specs)
        self.assertIn("推奨人数：2〜3人", data_b["overview"])
        self.assertIn("所要時間：3時間", data_b["overview"])
        self.assertIn("ここは誰も知らない霧の街。", data_b["synopsis"])
        self.assertIn("「信じられるのは、目の前の真実だけ」", data_b["synopsis"])

    def test_booth_spll_brackets_abbrev_split(self):
        """SPLL付きタイトル・山括弧人数表記・略称行による概要とあらすじの自動分割テスト"""
        from core.database import generate_player_tags

        title = "CoCシナリオ「TACTICS:ESCHAMPUS」SPLL:E197335 - ふわふわ帝国 - BOOTH"
        clean_t = WebScenarioExtractor.clean_title(title)
        self.assertEqual(clean_t, "TACTICS:ESCHAMPUS")

        desc = (
            "TACTICS:ESCHAMPUS\n"
            "-----------------------------------------\n"
            "クトゥルフ神話TRPG6版非公式シナリオ\n"
            "『TACTICS:ESCHAMPUS』\n"
            "（タクティクス:エスキャンパス）\n\n"
            "〈プレイ人数〉4人固定\n"
            "〈プレイ時間〉ボイスセッションで12時間〜\n"
            "〈ロスト率〉低〜中\n"
            "〈舞台〉現代アメリカの架空都市\n"
            "〈推奨技能〉三大探索技能＋交渉技能\n"
            "〈シナリオ傾向〉秘匿HOあり／協力型／シティ探索\n\n"
            "略称は「たけし」です。\n"
            "-----------------------------------------\n\n"
            "白亜の国、アメリカ。\n"
            "世界で最も自由で、最も繁栄したこの国には、\n"
            "しかし光の当たらない暗部が確かに存在していた。\n"
            "犯罪、暴力、貧困、そして――人知を超えた怪異。\n\n"
            "あなたたちは、それぞれの目的のために手を組むこととなる。"
        )
        html = f"<html><head><title>{title}</title></head><body><div class=\"user-text-content\">{desc}</div></body></html>"
        data = WebScenarioExtractor.extract_from_html(html, url="https://fuwatei.booth.pm/items/5270427")

        self.assertEqual(data["title"], "TACTICS:ESCHAMPUS")
        self.assertEqual(data["players"], "4人固定")
        self.assertEqual(data["duration"], "12時間〜")
        self.assertIn("4PL", generate_player_tags(data["players"]))

        # 概要にはスペックと略称が含まれ、あらすじ本文は含まれない
        self.assertIn("〈プレイ人数〉4人固定", data["overview"])
        self.assertIn("略称は「たけし」です。", data["overview"])
        self.assertNotIn("白亜の国、アメリカ。", data["overview"])

        # あらすじには物語本文が含まれ、スペックや略称は含まれない
        self.assertIn("白亜の国、アメリカ。", data["synopsis"])
        self.assertIn("世界で最も自由で", data["synopsis"])
        self.assertNotIn("略称は「たけし」です。", data["synopsis"])
        self.assertNotIn("〈プレイ人数〉", data["synopsis"])

    def test_booth_author_split_and_hidden_ho_players(self):
        """「■人数：秘匿 HO 有り 2PL」の人数抽出および「作者：〜」行による概要・あらすじ切り分けテスト"""
        from core.database import generate_player_tags

        title = "CoCシナリオ「拷戸審問」SPLL:E188008 - ふわふわ帝国 - BOOTH"
        desc = (
            "■システム：クトゥルフ神話 TRPG 第 6 版\n"
            "■人数：秘匿 HO 有り 2PL\n"
            "■プレイ時間：12-14 時間(ボイスセッション)\n"
            "■舞台：現代日本\n"
            "■ロスト率：低～中\n"
            "■推奨技能：交渉系技能、コンピューター(HO1)\n"
            "■準推奨技能：探索系技能\n\n"
            "作者：ぺんぎん（検索用：ふわ帝_ぺんぎんシナリオ）\n\n\n"
            "C県のそこそこ平和で不思議な町、栗夢町。大体の人が幸せに暮らすこの町には、悪者を裁く影の番人がいた。\n"
            "｢審問官｣――とあるSNSの非公開アカウント。ごく稀に鍵を開け、個別メッセージで栗夢町の｢嘆く人｣の訴えに耳を傾ける。"
        )
        html = f"<html><head><title>{title}</title></head><body><div class=\"user-text-content\">{desc}</div></body></html>"
        data = WebScenarioExtractor.extract_from_html(html, url="https://fuwatei.booth.pm/items/8229132")

        self.assertEqual(data["title"], "拷戸審問")
        self.assertEqual(data["author"], "ぺんぎん")
        self.assertEqual(data["players"], "2人")
        self.assertEqual(data["duration"], "12-14 時間")
        self.assertIn("2PL", generate_player_tags(data["players"]))

        # 概要にはスペックと作者が含まれ、あらすじ本文は含まれない
        self.assertIn("■人数：秘匿 HO 有り 2PL", data["overview"])
        self.assertIn("作者：ぺんぎん", data["overview"])
        self.assertNotIn("C県のそこそこ平和で不思議な町", data["overview"])

        # あらすじには物語本文が含まれ、スペックや作者は含まれない
        self.assertIn("C県のそこそこ平和で不思議な町", data["synopsis"])
        self.assertNotIn("作者：ぺんぎん", data["synopsis"])
        self.assertNotIn("■人数：", data["synopsis"])

    def test_booth_uminakimuras_extraction(self):
        """海哭村のパイプ区切りタイトル、末尾チルダ人数「1人～」、物語とスペックブロックの切り分けテスト"""
        title = "海哭村｜CoC6/エモクロア｜本文無料 - くらやみ病院 - BOOTH"
        desc = (
            "▾シナリオ概要　\n\n"
            "探索者たちはある日、バスに乗って出かけていた。\n"
            "しかし道中バスが故障してしまい、仕方なく一度バスを降りたあなたたちは、とある村にたどりつく……。\n\n"
            "タイトル　　　　　　　海哭村（うみなきむら）\n"
            "形式　　　　　　　　　クトゥルフ神話TRPG6版\n"
            "人数　　　　　　　　　1人～KPが管理できる人数\n"
            "プレイ時間　　　　　　ボイスセッション3-5時間/通話補助有テキストセッション6-8時間\n"
            "ロスト率　　　　　　　中\n"
            "発狂率　　　　　　　　中\n"
            "推奨技能　　　　　　　〈目星〉〈聞き耳〉〈図書館〉\n"
            "振る機会のある技能　　〈オカルト〉〈説得〉〈精神分析〉〈回避〉〈低すぎないPOW〉\n"
            "舞台　　　　　　　　　現代日本・廃村\n\n"
            "本作は、「 株式会社アークライト 」及び「株式会社KADOKAWA」が権利を有する『クトゥルフ神話TRPG』の二次創作物です。"
        )
        html = f"<html><head><title>{title}</title></head><body><section class=\"shop__text\"><h2>✦概要-CoC</h2><p>{desc}</p></section></body></html>"
        data = WebScenarioExtractor.extract_from_html(html, url="https://kazikiyoiko.booth.pm/items/8937752")

        self.assertEqual(data["title"], "海哭村")
        self.assertEqual(data["system"], "クトゥルフ神話TRPG")
        self.assertEqual(data["players"], "1人～")
        self.assertEqual(data["duration"], "3-5時間")

        # 概要にはスペックブロックが含まれ、あらすじ本文は含まれない
        self.assertIn("タイトル　　　　　　　海哭村", data["overview"])
        self.assertIn("形式　　　　　　　　　クトゥルフ神話TRPG6版", data["overview"])
        self.assertIn("舞台　　　　　　　　　現代日本・廃村", data["overview"])
        self.assertNotIn("探索者たちはある日", data["overview"])
        self.assertNotIn("本作は、「 株式会社アークライト 」", data["overview"])

        # あらすじには物語本文が含まれ、スペックブロックは含まれない
        self.assertIn("探索者たちはある日、バスに乗って出かけていた。", data["synopsis"])
        self.assertIn("とある村にたどりつく……。", data["synopsis"])
        self.assertNotIn("形式　　　　　　　　　クトゥルフ神話TRPG6版", data["synopsis"])
        self.assertNotIn("ロスト率", data["synopsis"])

    def test_booth_aouo_extraction(self):
        """青魚の牢/双魚の理の抽出テスト（span構造、年齢制限、物語文と想定時間スペックブロックの分離）"""
        title = "CoCシナリオ「青魚の牢/双魚の理」SPLL:E188909 - おさしみ大帝国 - BOOTH"
        main_desc = (
            "CoC「青魚の牢/双魚の理」\n"
            "(せいぎょのろう そうぎょのことわり)\n"
            "『永遠に美しい魚など、いないのだよ。』\n\n\n"
            "【概要】\n"
            "漪杜(なみもり)家の当主が亡くなった。\n"
            "齢八十九の当主、幻十郎は遺言を残す。\n"
            "それは、「存在しない七男に全ての遺産を相続する」という奇妙なものだった──\n"
            "探偵である探索者は、その謎を追うべく、漪杜家の門を潜る。\n\n\n"
            "想定時間：ボイセ15~30時間、テキセ30~40時間\n"
            "(RP・推理で変動あり。RP重視でボイセ24時間〜30時間)\n"
            "プレイ人数：1名固定\n"
            "推奨技能：基本探索技能、身を守れる技能、交渉技能\n"
            "振る機会がある技能：知識技能(知識1/2で代用可能)\n"
            "現代日本(時代改変可能)、シティシナリオ\n"
            "ロスト可能性：低～高(ルートによる)\n"
            "PL難易度：中〜高。初心者向けのシナリオではない。\n"
            "KP,PL共にCoCシナリオにある程度慣れている人物を想定している。\n"
            "R18,R18G要素あり：\n"
            "本編自体に探索者が性的な目に遭う・性的な加害をされるルートはない\n\n"
            "ルルブ6版対応シナリオですが、新版への改変はご自由にどうぞ。\n\n\n"
            "甘いもの市場×チーズフォンデュ工房 presents\n"
            "非公式クトゥルフ神話TRPGシナリオアンソロジー企画 \n"
            "『名探偵カケルの館へようこそ』 参加作品\n"
            "https://kakeru-yakata-3.jimdosite.com"
        )
        html = f"""<html>
        <head><title>{title}</title></head>
        <body>
            <span class="autolink js-expansion-content break-words whitespace-pre-line typography-16">{main_desc}</span>
            <section class="shop__text"><h2>NPC紹介</h2><p>主要人物のテキスト...</p></section>
        </body>
        </html>"""
        data = WebScenarioExtractor.extract_from_html(html, url="https://river1060.booth.pm/items/8500383")

        self.assertEqual(data["title"], "青魚の牢/双魚の理")
        self.assertEqual(data["system"], "クトゥルフ神話TRPG")
        self.assertEqual(data["author"], "おさしみ大帝国")
        self.assertEqual(data["players"], "1人固定")

        # あらすじ
        expected_synopsis = (
            "漪杜(なみもり)家の当主が亡くなった。\n"
            "齢八十九の当主、幻十郎は遺言を残す。\n"
            "それは、「存在しない七男に全ての遺産を相続する」という奇妙なものだった──\n"
            "探偵である探索者は、その謎を追うべく、漪杜家の門を潜る。"
        )
        self.assertEqual(data["synopsis"], expected_synopsis)

        # 概要
        expected_overview = (
            "想定時間：ボイセ15~30時間、テキセ30~40時間\n"
            "(RP・推理で変動あり。RP重視でボイセ24時間〜30時間)\n"
            "プレイ人数：1名固定\n"
            "推奨技能：基本探索技能、身を守れる技能、交渉技能\n"
            "振る機会がある技能：知識技能(知識1/2で代用可能)\n"
            "現代日本(時代改変可能)、シティシナリオ\n"
            "ロスト可能性：低～高(ルートによる)\n"
            "PL難易度：中〜高。初心者向けのシナリオではない。\n"
            "KP,PL共にCoCシナリオにある程度慣れている人物を想定している。\n"
            "R18,R18G要素あり：\n"
            "本編自体に探索者が性的な目に遭う・性的な加害をされるルートはない"
        )
        self.assertEqual(data["overview"], expected_overview)

    def test_booth_eye_of_the_storm_extraction(self):
        """Eye of the stormの抽出テスト（二重縦線║とSPLL、三角形ビュレット‣、装飾線ヘッダーのトリム）"""
        title = "CoC『Eye of the storm』║SPLL:E197608 - 神廻工場 - BOOTH"
        main_desc = (
            "クトゥルフ神話TRPG\n"
            "『 Eye of the storm 』\n\n"
            "＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿\n\n"
            "咆哮のような風が窓を叩く。\n"
            "今朝から突発的に発生した暴風、大雨の影響で早朝から交通網は麻痺しあなたたちの職場、学校からも出勤、通学を含め外出を控えるよう通達が来ていた。その言葉に従い、今日は家でやるべきことを……もしくはゆっくりしていようと思っていたところだった。\n"
            "あなたの携帯が鳴る。確認して見れば、KPCからあなたたちへのメッセージが入っていた。\n"
            "『こんな日にごめん、今から会えない？』\n\n"
            "───窓から暗雲が垂れ込める様は不吉な予感をもたらす。\n"
            "しばらくして、支度をしたあなたたちはゆっくりと各々の家の扉を開けた。\n\n"
            "＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿\n\n"
            "‣推奨人数：3～4人+KPC　\n"
            "　　　　　　いわゆる自陣から1人KPCを出す形を推奨\n"
            "‣プレイ時間：ボイスセッションで8hほど　RPによって変動\n"
            "‣推奨技能：<目星>、<戦闘技能>\n"
            "持っていればそこそこ使えるかもしれない技能 <心理学>\n"
            "‣形式：半シティ / 現代\n"
            "‣ロスト率：中～高　ダイスやルートによって大きく変化\n"
            "‣シナリオ傾向：劇場型SF、微シリアス\n\n"
            "＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿\n\n"
            "【注意事項】\n"
            "・登場する神話生物や呪文などについて、独自の解釈が含まれます。"
        )
        html = f"""<html>
        <head><title>{title}</title></head>
        <body>
            <span class="autolink js-expansion-content">{main_desc}</span>
        </body>
        </html>"""
        data = WebScenarioExtractor.extract_from_html(html, url="https://egamin.booth.pm/items/5422605")

        self.assertEqual(data["title"], "Eye of the storm")
        self.assertEqual(data["system"], "クトゥルフ神話TRPG")
        self.assertEqual(data["author"], "神廻工場")
        self.assertEqual(data["players"], "3～4人")
        self.assertEqual(data["duration"], "8時間")

        # あらすじ
        expected_synopsis = (
            "咆哮のような風が窓を叩く。\n"
            "今朝から突発的に発生した暴風、大雨の影響で早朝から交通網は麻痺しあなたたちの職場、学校からも出勤、通学を含め外出を控えるよう通達が来ていた。その言葉に従い、今日は家でやるべきことを……もしくはゆっくりしていようと思っていたところだった。\n"
            "あなたの携帯が鳴る。確認して見れば、KPCからあなたたちへのメッセージが入っていた。\n"
            "『こんな日にごめん、今から会えない？』\n\n"
            "───窓から暗雲が垂れ込める様は不吉な予感をもたらす。\n"
            "しばらくして、支度をしたあなたたちはゆっくりと各々の家の扉を開けた。"
        )
        self.assertEqual(data["synopsis"], expected_synopsis)

        # 概要
        expected_overview = (
            "‣推奨人数：3～4人+KPC　\n"
            "　　　　　　いわゆる自陣から1人KPCを出す形を推奨\n"
            "‣プレイ時間：ボイスセッションで8hほど　RPによって変動\n"
            "‣推奨技能：<目星>、<戦闘技能>\n"
            "持っていればそこそこ使えるかもしれない技能 <心理学>\n"
            "‣形式：半シティ / 現代\n"
            "‣ロスト率：中～高　ダイスやルートによって大きく変化\n"
            "‣シナリオ傾向：劇場型SF、微シリアス"
        )
        self.assertEqual(data["overview"], expected_overview)

    def test_booth_kakurenbo_ghost_extraction(self):
        """かくれんぼゴーストの抽出テスト（タイマン/2PL併記からの1～2人判定、スペックブロック抽出、あらすじ抽出）"""
        title = "【本文無料】かくれんぼゴースト SPLL:E186234 - Meat Meets Me too - BOOTH"
        main_desc = (
            "＋＋＋\n\n"
            "まっくらな夜の世界で、わたしは小さくなる。\n"
            "だれもいなくなった世界で、わたしはかくれんぼ。\n\n"
            "わたしをみつけてね。\n\n"
            "＋＋＋\n\n"
            "▋クトゥルフ神話TRPG6版\n"
            "「かくれんぼゴースト」\n"
            "舞台 現代日本(舞台改変可能)/終わった世界\n"
            "人数 2PL/PC＋KPCの一人用タイマンシナリオ\n"
            "時間 ボイスセッションで4時間～\n"
            "推奨技能 目星・聞き耳\n"
            "探索者 新規・継続不問\n"
            "概要 HO1がHO2を探す話\n"
            "ロスト 隠れる人は一生隠れるかも\n\n"
            "※神話生物の独自解釈を含みます。\n\n"
            "略称：かくゴ\n\n"
            "▋あらすじ\n"
            "天気のいいある日のこと。\n"
            "HO1は一人で出かけたHO2に連絡をする。だが、反応は一切ない。\n"
            "どうやらHO2はスマートフォンなどの連絡手段を忘れて出ていったようだ。\n"
            "どうしても連絡を取りたかったHO1はHO2を探しにいくことになる。\n"
            "その先で、あなたたちは迷い込んでしまう。\n"
            "「だれもいなくなった世界」、静かな終わりの世界に。\n\n"
            "▋ハンドアウト\n"
            "共通HO\n"
            "あなたたちは互いを大切に思っている。\n"
            "※秘匿HOは存在しない。\n\n"
            "HO1 あなたはみつけたい\n"
            "★人を探すことが得意/人を探すことが似合うPC向け\n"
            "HO2を心配して、すぐに探しに行ける人。\n\n"
            "HO2 わたしをさがしてね\n"
            "★手を離したらどこかに行ってしまいそう/隠れることが似合うPC向け\n"
            "スマートフォンの忘れ物に気が付かないような人。\n\n"
            "タイマンの場合\n"
            "KPCのHOはギミックの都合上、HO2を想定している。\n"
            "ギミックの改変がクリアできるならHO1をKPCにしても構わないが、推奨はしない。\n\n"
            "▋雰囲気\n"
            "二人だけで話しながら、静かな世界を歩く。\n\n"
            "▋どんなシナリオ？\n"
            "不思議な世界を楽しみながら、かくれんぼをするシナリオ。\n"
            "自分の住む世界とは異なる不思議な世界をゲーム感覚で探索するシーンもある。\n\n"
            "シナリオトーン：静か/綺麗/情緒的/RP重視/ゲーム\n\n"
            "×含まれない要素\n"
            "ド派手な展開/ハイレベルな戦闘/ハイテンションなコメディ/高濃度な推理\n\n"
            "▋想定している遊び方\n"
            "本作は、HO1がHO2を探す「かくれんぼ」と、夜に包まれた街の探索を楽しむシナリオです。\n"
            "探索では限られたリソースの中で、元の世界へ帰るための情報を集めることになります。\n"
            "どこを探索するか、限られたリソースをどう使うかなど、PL自身が考えて行動する場面があります。\n\n"
            "また、探索や判定によって、この世界に起きたことを知ることができます。\n"
            "得た情報やPCの選択によって、一部の展開やエンディング描写が変化します。\n\n"
            "こんな人におすすめ\n"
            "・PC同士でかくれんぼ（？）をして遊びたい\n"
            "・限られたリソースを使った探索が好き\n"
            "・終末世界、夜、廃墟の雰囲気が好き\n\n"
            "向いてない人\n"
            "・自由度の高い探索を求めている\n"
            "・一本道でなく、大きく展開が分岐するシナリオがいい\n"
            "・終末や死を扱う物語を避けたい\n\n"
            "▋要素\n"
            "オリジナルのAF、終末世界、幽霊、暗闇の中を歩く。\n\n"
            "▋更新情報\n"
            "2026.09.29 BOOTHページ公開\n"
            "2026.10.15 配布・販売開始\n\n"
            "▋同梱内容\n"
            "〈無料版〉\n"
            "・シナリオPDF　カラー・グレースケール\n"
            "・シナリオdocx　2万8千字程度\n"
            "・利用規約PDF\n"
            "・ココフォリア無料版ルームデータ公開リンクPDF\n"
            "・BGM参考リスト\n\n"
            "〈有料版〉\n"
            "無料版に追加して\n"
            "・トレーラー画像4枚+1\n"
            "・ロゴPNG\n"
            "・加工用PSD\n"
            "・部屋素材png　26点\n"
            "・部屋素材apng　12点\n"
            "・おまけBGM「しゅうまつへようこそ」\n"
        )
        html = f"""<html>
        <head><title>{title}</title></head>
        <body>
            <span class="autolink js-expansion-content">{main_desc}</span>
            <section class="shop__text">
                <h2>権利表記</h2>
                <p>本作は、「株式会社アークライト」及び「株式会社KADOKAWA」が権利を有する『クトゥルフ神話TRPG』シリーズの二次創作物です。</p>
            </section>
        </body>
        </html>"""
        data = WebScenarioExtractor.extract_from_html(html, url="https://meat-meets-me.booth.pm/items/8897888")

        self.assertEqual(data["title"], "かくれんぼゴースト")
        self.assertEqual(data["system"], "クトゥルフ神話TRPG")
        self.assertEqual(data["author"], "Meat Meets Me too")
        self.assertEqual(data["players"], "1～2人")
        self.assertEqual(data["duration"], "4時間～")

        expected_overview = (
            "「かくれんぼゴースト」\n"
            "舞台 現代日本(舞台改変可能)/終わった世界\n"
            "人数 2PL/PC＋KPCの一人用タイマンシナリオ\n"
            "時間 ボイスセッションで4時間～\n"
            "推奨技能 目星・聞き耳\n"
            "探索者 新規・継続不問\n"
            "概要 HO1がHO2を探す話\n"
            "ロスト 隠れる人は一生隠れるかも"
        )
        self.assertEqual(data["overview"], expected_overview)

        expected_synopsis = (
            "天気のいいある日のこと。\n"
            "HO1は一人で出かけたHO2に連絡をする。だが、反応は一切ない。\n"
            "どうやらHO2はスマートフォンなどの連絡手段を忘れて出ていったようだ。\n"
            "どうしても連絡を取りたかったHO1はHO2を探しにいくことになる。\n"
            "その先で、あなたたちは迷い込んでしまう。\n"
            "「だれもいなくなった世界」、静かな終わりの世界に。"
        )
        self.assertEqual(data["synopsis"], expected_synopsis)

    def test_booth_rappie_drink_shop_extraction(self):
        """ラッピードリンクショップ：概要セクション内の物語文→スペック→※注記→略称→区切り線 の分割"""
        title = "CoC『ラッピードリンクショップ』 - 災は投げられた - BOOTH"
        main_desc = (
            "CoC6版非公式シナリオ\n『ラッピードリンクショップ』\n\n\n"
            " ラッピードリンクショップ。\n それは一期一会の出会い。\n ドライブイン自動販売機で生まれる、心温まる愛の物語。\n\n\n"
            "───────────────\n\n\nシナリオ：災は投げられた / しく\n"
        )
        gaiyou = (
            "『ラッピードリンクショップ』<br><br>・　・　・<br><br>"
            " ラッピードリンクショップ。<br> それは一期一会の出会い。<br> ドライブイン自動販売機で生まれる、心温まる愛の物語。<br><br>"
            "・　・　・<br><br>"
            "プレイ人数：１PL～車に乗れる人数（KPC可）<br>"
            "プレイ時間：ボイセ１ｈ～<br>"
            "舞台　　　：車がある時代・国<br>"
            "推奨技能　：特になし<br>"
            "あらすじ　：深夜に車を運転していたら自動販売機のドライブインを見つけた。（バイクも可）<br><br>"
            "※大幅なSAN値の増減が発生する場合があります。<br>"
            "※実在するドライブイン自動販売機をモチーフにしたシナリオです。<br><br>"
            "略称：ラピショ<br><br>────────────────"
        )
        html = f"""<html><head><title>{title}</title></head><body>
            <span class="autolink js-expansion-content">{main_desc}</span>
            <section class="shop__text"><h2>【概要】</h2><p>{gaiyou}</p></section>
            <section class="shop__text"><h2>【頒布内容】</h2><p>■『ラッピードリンクショップ』 - free<br>　・シナリオ本文 約14,000字［ pdf / txt ］</p></section>
        </body></html>"""
        data = WebScenarioExtractor.extract_from_html(html, url="https://490.booth.pm/items/8678023")

        self.assertEqual(data["title"], "ラッピードリンクショップ")
        self.assertEqual(data["players"], "1人～")
        self.assertEqual(data["duration"], "1時間～")
        expected_overview = (
            "プレイ人数：１PL～車に乗れる人数（KPC可）\n"
            "プレイ時間：ボイセ１ｈ～\n"
            "舞台　　　：車がある時代・国\n"
            "推奨技能　：特になし\n"
            "あらすじ　：深夜に車を運転していたら自動販売機のドライブインを見つけた。（バイクも可）\n\n"
            "※大幅なSAN値の増減が発生する場合があります。\n"
            "※実在するドライブイン自動販売機をモチーフにしたシナリオです。\n\n"
            "略称：ラピショ"
        )
        self.assertEqual(data["overview"], expected_overview)
        expected_synopsis = (
            "ラッピードリンクショップ。\n"
            "それは一期一会の出会い。\n"
            "ドライブイン自動販売機で生まれる、心温まる愛の物語。"
        )
        self.assertEqual(data["synopsis"], expected_synopsis)

    def test_booth_kuchinashi_garden_extraction(self):
        """梔子の庭にて：概要セクション内に埋め込まれた■あらすじ／■こんな探索者におすすめ！等の見出し分割"""
        title = "クトゥルフ神話TRPG「梔子の庭にて」SPLL:E186567 - 落魄総合病院 - BOOTH"
        main_desc = "ここが天国だと錯覚する。\n地獄以外、知らないくせに。"
        gaiyou = (
            "人数：KPC＋PL（2人） <br>時間：2～3時間程度 <br>推奨技能：＜目星＞＜聞き耳＞ <br>"
            "ロスト率：低<br>舞台：奇妙な病室<br>傾向：生きているのが辛い探索者/無理矢理な正気度回復<br><br>"
            "■あらすじ<br>甘い香りがする。<br>自らの嗅覚を取り戻したあと、次に目を覚ました。<br>"
            "視界に飛び込んできたのは白い天井だった。その光景を見て、あなたはこの場所を病室のようだ、と思うことだろう。<br>"
            "あなたはどうやら、見知らぬ部屋のベッドに仰向けで寝転がっていたらしい。<br><br>"
            "■こんな探索者/状態におすすめ！<br>・この探索者を引退させたい。<br>・生きているのが辛い探索者。<br><br>"
            "■内容物<br>・PDF本文<br><br>■注意事項<br>・神話生物に対する独自解釈を含みます。"
        )
        html = f"""<html><head><title>{title}</title></head><body>
            <span class="autolink js-expansion-content">{main_desc}</span>
            <section class="shop__text"><h2>概要</h2><p>{gaiyou}</p></section>
            <section class="shop__text"><h2>権利表記</h2><p>本作は「株式会社 KADOKAWA 」が権利を有する「クトゥルフ神話 TRPG 」の二次創作物です。</p></section>
        </body></html>"""
        data = WebScenarioExtractor.extract_from_html(html, url="https://monoyukasy.booth.pm/items/9014125")

        self.assertEqual(data["title"], "梔子の庭にて")
        self.assertEqual(data["players"], "2人")
        self.assertEqual(data["duration"], "2～3時間")
        expected_overview = (
            "人数：KPC＋PL（2人） \n"
            "時間：2～3時間程度 \n"
            "推奨技能：＜目星＞＜聞き耳＞ \n"
            "ロスト率：低\n"
            "舞台：奇妙な病室\n"
            "傾向：生きているのが辛い探索者/無理矢理な正気度回復"
        )
        self.assertEqual(data["overview"], expected_overview)
        expected_synopsis = (
            "甘い香りがする。\n"
            "自らの嗅覚を取り戻したあと、次に目を覚ました。\n"
            "視界に飛び込んできたのは白い天井だった。その光景を見て、あなたはこの場所を病室のようだ、と思うことだろう。\n"
            "あなたはどうやら、見知らぬ部屋のベッドに仰向けで寝転がっていたらしい。"
        )
        self.assertEqual(data["synopsis"], expected_synopsis)


if __name__ == "__main__":
    unittest.main()




