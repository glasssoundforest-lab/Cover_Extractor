"""PySide6 向けテーマ・スタイル定義 (gui_qt/theme.py)

西洋古書・グリモワール調（案A＋くすんだ真鍮アクセント）の配色定義と
Qtスタイルシート (QSS)、フォント設定を集約します。
"""

class Theme:
    # ベース背景（深みのあるアンティークウッド・黒檀）
    BG_BASE = "#16120f"         # 最暗部背景
    BG_PANEL = "#1a1511"        # パネル・サイドバー背景
    BG_SHELF = "#181310"        # 書架エリア背景
    BG_CARD = "#14100d"         # シナリオカード背景
    BG_CARD_HOVER = "#241c14"   # シナリオカードホバー背景
    BG_INPUT = "#1c1713"        # 入力フィールド背景

    # アンティーク真鍮（ブラスカラー）
    BRASS_LIGHT = "#d4b26f"     # くすんだ真鍮（金文字・ハイライト）
    BRASS_BASE = "#8c703e"      # くすんだ真鍮（メイン枠線・アイコン）
    BRASS_DARK = "#4a3c20"      # くすんだ真鍮（シャドウ・陰影）
    BRASS_MUTED = "#302616"     # 深い真鍮・溝線

    # テキストカラー
    TEXT_GOLD = "#d4b26f"       # 見出し・重要項目（真鍮ゴールド）
    TEXT_WHITE = "#ebe1d0"      # 本文（羊皮紙生成り色）
    TEXT_LIGHT = TEXT_WHITE     # 互換エイリアス
    TEXT_MUTED = "#8c7d6c"      # 補助テキスト（セピアグレー）
    TEXT_HINT = "#5a5044"       # プレースホルダー色


    # しおり（ブックマーク）カラーパレット
    BOOKMARK_COLORS = {
        "CoC": "#1b5e20",       # 深緑（クトゥルフ神話TRPG）
        "マダミス": "#6a1b9a",   # 紫（マーダーミステリー）
        "ストプレ": "#0e7490",   # 深碧（ストーリープレイング）
        "その他": "#546e7a",     # スレートグレー
        "未通過": "#1565c0",     # ブルー（未通過）
        "通過済": "#9e2a2b",     # 深紅（通過済）
        "通過済み": "#9e2a2b",   # 深紅（通過済み）
        "GM可": "#b3882a",      # 真鍮金（GM可）
    }

    # フォントファミリー（Qt Style Sheetはカンマ区切りフォールバック非対応のため単一フォント名を解決）
    # platform.system() は Windows で WMI 照会を伴い起動が遅くなるため sys.platform で判定する
    import sys as _sys
    if _sys.platform == "win32":
        FONT_SERIF = "Yu Mincho"
        FONT_SANS = "Yu Gothic UI"
    elif _sys.platform == "darwin":
        FONT_SERIF = "Hiragino Mincho ProN"
        FONT_SANS = "Hiragino Sans"
    else:
        FONT_SERIF = "Noto Serif CJK JP"
        FONT_SANS = "Noto Sans CJK JP"

    @classmethod
    def get_application_stylesheet(cls):
        """アプリケーション全体の共通QSS"""
        return f"""
        QWidget {{
            background-color: {cls.BG_BASE};
            color: {cls.TEXT_WHITE};
            font-family: {cls.FONT_SANS};
            font-size: 13px;
        }}

        QMainWindow, QDialog {{
            background-color: {cls.BG_BASE};
        }}

        /* スクロールバー装飾（真鍮レール調・空白部分の破損防止） */
        QScrollBar:vertical {{
            border: 1px solid {cls.BRASS_DARK};
            background-color: {cls.BG_PANEL};
            width: 12px;
            margin: 0px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {cls.BRASS_DARK};
            min-height: 28px;
            border-radius: 3px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical:hover {{
            background-color: {cls.BRASS_BASE};
        }}
        QScrollBar::handle:vertical:pressed {{
            background-color: {cls.BRASS_LIGHT};
        }}
        QScrollBar::sub-line:vertical {{
            height: 0px;
            width: 0px;
            background-color: {cls.BG_PANEL};
            border: none;
            subcontrol-position: top;
            subcontrol-origin: margin;
        }}
        QScrollBar::add-line:vertical {{
            height: 0px;
            width: 0px;
            background-color: {cls.BG_PANEL};
            border: none;
            subcontrol-position: bottom;
            subcontrol-origin: margin;
        }}
        QScrollBar::sub-page:vertical {{
            background-color: {cls.BG_PANEL};
            border: none;
        }}
        QScrollBar::add-page:vertical {{
            background-color: {cls.BG_PANEL};
            border: none;
        }}

        QScrollBar:horizontal {{
            border: 1px solid {cls.BRASS_DARK};
            background-color: {cls.BG_PANEL};
            height: 12px;
            margin: 0px;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {cls.BRASS_DARK};
            min-width: 28px;
            border-radius: 3px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background-color: {cls.BRASS_BASE};
        }}
        QScrollBar::handle:horizontal:pressed {{
            background-color: {cls.BRASS_LIGHT};
        }}
        QScrollBar::sub-line:horizontal {{
            width: 0px;
            height: 0px;
            background-color: {cls.BG_PANEL};
            border: none;
            subcontrol-position: left;
            subcontrol-origin: margin;
        }}
        QScrollBar::add-line:horizontal {{
            width: 0px;
            height: 0px;
            background-color: {cls.BG_PANEL};
            border: none;
            subcontrol-position: right;
            subcontrol-origin: margin;
        }}
        QScrollBar::sub-page:horizontal {{
            background-color: {cls.BG_PANEL};
            border: none;
        }}
        QScrollBar::add-page:horizontal {{
            background-color: {cls.BG_PANEL};
            border: none;
        }}

        /* 入力フィールド */
        QLineEdit, QTextEdit, QPlainTextEdit {{
            background-color: {cls.BG_INPUT};
            color: {cls.TEXT_WHITE};
            border: 1px solid {cls.BRASS_BASE};
            border-radius: 2px;
            padding: 5px 8px;
            selection-background-color: {cls.BRASS_BASE};
            selection-color: #ffffff;
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
            border: 1px solid {cls.BRASS_LIGHT};
        }}

        /* ボタン（西洋アンティーク真鍮調） */
        QPushButton {{
            background-color: {cls.BG_PANEL};
            color: {cls.TEXT_GOLD};
            border: 1px solid {cls.BRASS_BASE};
            border-radius: 2px;
            padding: 5px 14px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {cls.BG_CARD_HOVER};
            border: 1px solid {cls.BRASS_LIGHT};
            color: #ffffff;
        }}
        QPushButton:pressed {{
            background-color: {cls.BG_BASE};
            border: 1px solid {cls.BRASS_DARK};
        }}

        /* コンボボックス */
        QComboBox {{
            background-color: {cls.BG_INPUT};
            color: {cls.TEXT_WHITE};
            border: 1px solid {cls.BRASS_BASE};
            border-radius: 2px;
            padding: 4px 10px;
            min-height: 20px;
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 20px;
            border-left: 1px solid {cls.BRASS_DARK};
        }}
        QComboBox QAbstractItemView {{
            background-color: {cls.BG_PANEL};
            color: {cls.TEXT_WHITE};
            selection-background-color: {cls.BRASS_DARK};
            selection-color: {cls.TEXT_GOLD};
            border: 1px solid {cls.BRASS_BASE};
        }}

        /* ツールチップ */
        QToolTip {{
            background-color: {cls.BG_PANEL};
            color: {cls.TEXT_GOLD};
            border: 1px solid {cls.BRASS_BASE};
            padding: 5px;
            border-radius: 2px;
        }}

        /* ポップアップメニュー (QMenu) - 西洋アンティーク真鍮調 */
        QMenu {{
            background-color: {cls.BG_PANEL};
            color: {cls.TEXT_WHITE};
            border: 1px solid {cls.BRASS_BASE};
            padding: 5px;
            border-radius: 2px;
            font-size: 13px;
        }}
        QMenu::item {{
            padding: 6px 28px 6px 20px;
            border-radius: 2px;
        }}
        QMenu::item:selected {{
            background-color: {cls.BG_CARD_HOVER};
            color: {cls.BRASS_LIGHT};
        }}
        QMenu::item:checked {{
            font-weight: bold;
            color: {cls.BRASS_LIGHT};
        }}
        QMenu::separator {{
            height: 1px;
            background: {cls.BRASS_DARK};
            margin: 4px 8px;
        }}
        """
