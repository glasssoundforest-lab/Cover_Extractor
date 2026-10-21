"""メイン書架グリッドコンポーネント (gui_qt/components/bookshelf_grid.py)

大・中・小のグリッド表示、および2カラム一覧（リスト）表示に対応。
書架フレーム、見出し、カード配置、クリック・ダブルクリックの中継を提供します。
"""

from collections import OrderedDict

from PySide6.QtCore import Qt, Signal, QPoint, QEvent, QPropertyAnimation, QEasingCurve, QTimer, QRect
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QLabel,
    QFrame,
    QComboBox,
)

from ..theme import Theme
from core.database import global_tag_sort_key
from .ornate import OrnateFrame, OrnateDivider, make_fleur_pixmap, PillTag
from .scenario_card import ScenarioCard, ScenarioListCard, card_stylesheet
from .cover_loader import CoverLoader


class BookshelfSlidePanel(QFrame):
    """書架一覧の枠の下辺からスライドインする概要・あらすじオーバーレイパネル"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.panel_height = 140  # 読みやすい大きめの高さ
        self.hide_y = 600
        self.show_y = 446

        self.anim = QPropertyAnimation(self, b"pos")
        self.anim.setDuration(380)  # 速度を少し落とし、滑らかで高級感のあるスライドインにする (240ms -> 380ms)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.finished.connect(self._on_anim_finished)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(6)

        # 1. ヘッダー行: 【あらすじ/概要】バッジ + 書名 (太字・16px) + システム名・人数・時間
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        self.badge_lbl = QLabel("📜 あらすじ")
        self.badge_lbl.setStyleSheet(f"""
            background-color: #2b1f14;
            color: {Theme.BRASS_LIGHT};
            border: 1px solid {Theme.BRASS_BASE};
            border-radius: 3px;
            padding: 2px 8px;
            font-size: 12px;
            font-weight: bold;
            font-family: {Theme.FONT_SERIF};
        """)
        header_layout.addWidget(self.badge_lbl)

        self.title_lbl = QLabel("無題")
        self.title_lbl.setStyleSheet(f"""
            color: {Theme.BRASS_LIGHT};
            font-size: 16px;
            font-weight: bold;
            font-family: {Theme.FONT_SERIF};
        """)
        header_layout.addWidget(self.title_lbl)

        # グローバルタグ（ピルアイコン）コンテナ
        self.tags_layout = QHBoxLayout()
        self.tags_layout.setSpacing(6)
        self.tags_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addLayout(self.tags_layout)

        self.meta_lbl = QLabel("")
        self.meta_lbl.setStyleSheet(f"""
            color: {Theme.TEXT_MUTED};
            font-size: 12px;
            font-family: {Theme.FONT_SERIF};
        """)
        header_layout.addWidget(self.meta_lbl)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # 2. 本文行: あらすじ・概要（14pxの大きな文字、行間1.5、高コントラスト白文字）
        self.body_lbl = QLabel("")
        self.body_lbl.setWordWrap(True)
        self.body_lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.body_lbl.setTextFormat(Qt.PlainText)
        self.body_lbl.setStyleSheet(f"""
            color: #f7f1e8;
            font-size: 14px;
            line-height: 1.5;
            font-family: {Theme.FONT_SANS};
        """)
        layout.addWidget(self.body_lbl, 1)

        # 西洋古書・魔導書架調の半透明ダークパネル・上部に真鍮の光沢ライン
        self.setStyleSheet(f"""
            BookshelfSlidePanel {{
                background-color: rgba(18, 14, 11, 0.96);
                border: 1px solid #4a3a2a;
                border-top: 2px solid {Theme.BRASS_LIGHT};
                border-radius: 5px;
            }}
        """)

        self.hide()

    def update_geometry(self, parent_w, parent_h):
        """親ウィジェット（書架グリッド）のサイズに合わせて幅と座標を再計算"""
        margin_x = 14
        margin_bottom = 12
        w = max(200, parent_w - margin_x * 2)
        self.setFixedSize(w, self.panel_height)
        self.hide_y = parent_h
        self.show_y = max(0, parent_h - self.panel_height - margin_bottom)

        if self.isVisible():
            if self.anim.state() != QPropertyAnimation.Running:
                self.move(margin_x, self.show_y)
        else:
            self.move(margin_x, self.hide_y)

    def set_item(self, item, global_tags=None):
        """表示するシナリオアイテムの情報をセット"""
        title = item[2] or "無題"
        system = item[3] or "システム未設定"
        players = item[4] or ""
        duration = item[5] or ""
        overview = (item[6] or "").strip() if len(item) > 6 and item[6] else ""
        synopsis = (item[7] or "").strip() if len(item) > 7 and item[7] else ""

        self.title_lbl.setText(title)

        # 既存のピルタグをクリア
        while self.tags_layout.count():
            item_tag = self.tags_layout.takeAt(0)
            w = item_tag.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        # タイトルの右側にグローバルタグを優先順序（CoC > マダミス > 未通過 > 通過済 > GM可）で動的配置
        if global_tags:
            for tag_item in sorted(global_tags, key=global_tag_sort_key):
                if isinstance(tag_item, (list, tuple)):
                    if len(tag_item) >= 3:
                        tname = tag_item[1]
                        tcolor = tag_item[2]
                    else:
                        tname = tag_item[0]
                        tcolor = tag_item[1] if len(tag_item) > 1 else None
                else:
                    tname = str(tag_item)
                    tcolor = None

                pill = PillTag(tname, color=tcolor, is_checkable=False)
                pill.setFixedHeight(22)
                self.tags_layout.addWidget(pill)

        meta_parts = [system]
        if players:
            meta_parts.append(f"人数: {players}")
        if duration:
            meta_parts.append(f"時間: {duration}")
        self.meta_lbl.setText(" │ ".join(meta_parts))

        if synopsis:
            self.badge_lbl.setText("📜 あらすじ")
            self.body_lbl.setText(synopsis)
        elif overview:
            self.badge_lbl.setText("📜 概要")
            self.body_lbl.setText(overview)
        else:
            self.badge_lbl.setText("📜 あらすじ・概要")
            self.body_lbl.setText("あらすじ・概要は未登録です（ダブルクリックで編集できます）")

    def slide_in(self):
        """書架一覧の枠の下辺からスッと競り上がる"""
        self.anim.stop()
        self.show()
        self.raise_()
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(QPoint(self.x(), self.show_y))
        self.anim.start()

    def slide_out(self):
        """枠の下辺へスライドアウトして消える"""
        self.anim.stop()
        self.anim.setStartValue(self.pos())
        self.anim.setEndValue(QPoint(self.x(), self.hide_y))
        self.anim.start()

    def _on_anim_finished(self):
        if self.y() >= self.hide_y:
            self.hide()


class BookshelfGrid(OrnateFrame):
    """メイン書架グリッドビュー"""
    card_clicked = Signal(int)       # item_id
    card_double_clicked = Signal(int) # item_id
    card_context_menu_requested = Signal(int, QPoint) # item_id, global_pos
    sort_changed = Signal(str)       # 選択されたソートキー
    selection_cleared = Signal()     # 選択解除シグナル

    def __init__(self, parent=None, db=None):
        # 半透明ダークパネル (alpha: 100 で背景テクスチャと右下の古城アートが美しく透ける)
        super().__init__(parent, bracket_size=22, bg_color=QColor(20, 16, 12, 100))

        self.db = db
        self.cards = []
        self.current_items = []
        self.selected_item_id = None
        self.view_mode = "medium"  # "large", "medium", "small", "list"

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(10)

        # 1. 見出しバー
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        fleur_lbl = QLabel()
        fleur_lbl.setPixmap(make_fleur_pixmap(16, Theme.BRASS_LIGHT))
        header_layout.addWidget(fleur_lbl)

        self.title_label = QLabel("書架一覧  ―  すべて (0 冊)")
        self.title_label.setStyleSheet(f"""
            color: {Theme.BRASS_LIGHT};
            font-weight: bold;
            font-size: 14px;
            font-family: {Theme.FONT_SERIF};
        """)
        header_layout.addWidget(self.title_label)

        # 中央の飾り線
        header_layout.addWidget(OrnateDivider(self, height=12))

        # 並び順ラベル＋コンボボックス（書架一覧の枠の右上に配置）
        sort_lbl = QLabel("並び順:")
        sort_lbl.setStyleSheet(f"""
            color: {Theme.TEXT_MUTED};
            font-size: 11px;
            font-family: {Theme.FONT_SERIF};
        """)
        header_layout.addWidget(sort_lbl)

        self.sort_combo = QComboBox()
        self.sort_combo.setFixedWidth(135)
        self.sort_combo.setFixedHeight(26)
        self.sort_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: #1a1511;
                color: {Theme.BRASS_LIGHT};
                border: 1px solid #4a3a2a;
                border-radius: 2px;
                padding: 2px 8px;
                font-size: 11px;
                font-family: {Theme.FONT_SERIF};
            }}
            QComboBox:hover {{
                border: 1px solid {Theme.BRASS_LIGHT};
                background-color: #261f18;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 16px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #1c1612;
                color: {Theme.TEXT_WHITE};
                selection-background-color: #3b2c1d;
                selection-color: #ffffff;
                border: 1px solid {Theme.BRASS_DARK};
            }}
        """)
        sort_options = [
            ("登録が新しい順", "added_desc"),
            ("登録が古い順", "added_asc"),
            ("題名順（あ→ん）", "title_asc"),
            ("題名順（ん→あ）", "title_desc"),
            ("システム順", "system"),
            ("PL人数順", "players"),
            ("所要時間順", "duration"),
        ]
        for label, val in sort_options:
            self.sort_combo.addItem(label, val)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)
        header_layout.addWidget(self.sort_combo)

        main_layout.addLayout(header_layout)

        # 2. スクロールエリア
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                border: 1px solid {Theme.BRASS_DARK};
                background-color: #14100c;
                width: 12px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background-color: {Theme.BRASS_DARK};
                min-height: 28px;
                border-radius: 3px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {Theme.BRASS_BASE};
            }}
            QScrollBar::handle:vertical:pressed {{
                background-color: {Theme.BRASS_LIGHT};
            }}
            QScrollBar::sub-line:vertical {{
                height: 0px;
                width: 0px;
                background-color: #14100c;
                border: none;
                subcontrol-position: top;
                subcontrol-origin: margin;
            }}
            QScrollBar::add-line:vertical {{
                height: 0px;
                width: 0px;
                background-color: #14100c;
                border: none;
                subcontrol-position: bottom;
                subcontrol-origin: margin;
            }}
            QScrollBar::sub-page:vertical {{
                background-color: #14100c;
                border: none;
            }}
            QScrollBar::add-page:vertical {{
                background-color: #14100c;
                border: none;
            }}
        """)

        # カードを並べる面。カードは表示範囲の分だけ作り、位置は自前で計算して配置する（仮想化）。
        # 数千冊でも、作るカードは画面に見えている分と前後1画面分だけで済む。
        self.grid_container = QWidget()
        self.grid_container.setObjectName("bookshelfGrid")
        # カードの見た目の規則はここで1度だけ設定し、各カードは状態（プロパティ）だけを切り替える
        self.grid_container.setProperty("cardStyleHost", True)
        self.grid_container.setStyleSheet("* { background: transparent; }\n" + card_stylesheet())

        # 空状態メッセージ
        self.empty_label = QLabel("書架にシナリオがありません。\nファイルをここにドラッグ＆ドロップするか、\n右上の「＋ シナリオを追加」から登録してください。", self.grid_container)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 13px; line-height: 1.6;")
        self.empty_label.hide()

        self.scroll.setWidget(self.grid_container)
        main_layout.addWidget(self.scroll)

        # 背景・余白クリック時の選択解除用イベントフィルター
        self.scroll.viewport().installEventFilter(self)
        self.grid_container.installEventFilter(self)

        # 3. 書架一覧の枠の下辺からスライドインする概要・あらすじオーバーレイパネル
        self.slide_panel = BookshelfSlidePanel(self)
        self.slide_timer = QTimer(self)
        self.slide_timer.setSingleShot(True)
        self.slide_timer.timeout.connect(self._on_slide_timeout)
        self.current_hovered_item_id = None

        # 4. カードの再利用と表紙のバックグラウンド読み込み
        #    絞り込み・並べ替えのたびにカードを作り直さず、内容が同じカードはそのまま使い回す。
        self.all_gtags = {}
        self._card_cache = OrderedDict()  # item_id -> (signature, card)  ※現在の表示モードのカードのみ。古い順
        self._grid = None                 # 配置の計算結果（_compute_grid）
        self._shown_range = None          # 現在カードを作って表示している範囲 (先頭, 末尾+1)
        self._cover_generation = {}       # item_id -> 表紙の世代（invalidate_items のたびに増える）
        self.cover_loader = None
        db_path = getattr(db, "db_path", None)
        if db_path:
            self.cover_loader = CoverLoader(db_path, self)
            self.cover_loader.loaded.connect(self._on_cover_loaded)
        self._cover_timer = QTimer(self)
        self._cover_timer.setSingleShot(True)
        self._cover_timer.setInterval(40)
        self._cover_timer.timeout.connect(self._request_covers)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scrolled)

    # 表示範囲の外で作り置きしておくカードの上限（これを超えたら古いものから破棄する）
    MAX_IDLE_CARDS = 240

    def set_view_mode(self, mode):
        """表示モードを切り替え ('large', 'medium', 'small', 'list')"""
        if self.view_mode != mode:
            self.view_mode = mode
            self._discard_cards(list(self._card_cache))
            self.display_items(self.current_items, self.all_gtags or None)

    def set_title(self, system_name, count):
        """見出しテキストの更新"""
        mode_suffix = " [一覧]" if self.view_mode == "list" else ""
        self.title_label.setText(f"書架一覧  ―  {system_name}  ({count} 冊){mode_suffix}")

    # -------------------------------------------------------------------------
    # カードの再利用
    # -------------------------------------------------------------------------
    def invalidate_items(self, item_ids):
        """指定アイテムのカードを次回表示時に作り直す（表紙の差し替えなど、内容の比較で検知できない変更用）"""
        for item_id in item_ids:
            # 世代を進め、作り直す前に依頼済みだった表紙の読み込み結果を新しいカードが受け取らないようにする
            self._cover_generation[item_id] = self._cover_generation.get(item_id, 0) + 1
            cached = self._card_cache.get(item_id)
            if cached:
                self._card_cache[item_id] = (None, cached[1])

    def invalidate_all(self):
        """全カードを次回表示時に作り直す（取り込み・同期など、まとめて変わる操作の後）"""
        self.invalidate_items(list(self._card_cache))

    def prune(self, valid_ids):
        """削除されたアイテムのカードを破棄する"""
        self._discard_cards([i for i in self._card_cache if i not in valid_ids])

    def _discard_cards(self, item_ids):
        for item_id in item_ids:
            cached = self._card_cache.pop(item_id, None)
            if cached:
                card = cached[1]
                self.cards = [c for c in self.cards if c is not card]
                card.hide()
                card.setParent(None)
                card.deleteLater()

    def _make_card(self, it, gtags):
        if self.view_mode == "list":
            card = ScenarioListCard(it, global_tags=gtags, parent=self.grid_container)
        else:
            card = ScenarioCard(it, size_mode=self.view_mode, global_tags=gtags, parent=self.grid_container)
        card.clicked.connect(self._on_card_clicked)
        card.double_clicked.connect(self.card_double_clicked.emit)
        card.context_menu_requested.connect(self.card_context_menu_requested.emit)
        card.hover_entered.connect(self._on_card_hover_entered)
        card.hover_left.connect(self._on_card_hover_left)
        if card.thumb_key:
            # 表紙の識別子は「元画像の大きさ」なので、同じ大きさの画像への差し替えも区別できるよう世代を加える
            card.thumb_key = (card.thumb_key, self._cover_generation.get(it[0], 0))
        if it[0] == self.selected_item_id:
            card.set_selected(True)
        return card

    def _card_for(self, it):
        """アイテムのカードを返す（内容が同じ作り置きがあれば再利用し、なければ作る）"""
        item_id = it[0]
        gtags = self.all_gtags.get(item_id, [])
        signature = (tuple(it), tuple(tuple(g) for g in gtags))
        cached = self._card_cache.get(item_id)
        if cached and cached[0] == signature:
            card = cached[1]
            self._card_cache.move_to_end(item_id)
        else:
            if cached:
                self._discard_cards([item_id])
            card = self._make_card(it, gtags)
            self._card_cache[item_id] = (signature, card)
        want_selected = (item_id == self.selected_item_id)
        if card.is_selected != want_selected:
            card.set_selected(want_selected)
        return card

    def display_items(self, items, global_tags=None):
        """シナリオアイテム一覧を現在の表示モードに応じて展開

        global_tags: {item_id: [(id, name, color), ...]}。省略時は DB から読む。
        カードは画面に見えている範囲（と前後1画面分）だけ作る。内容（アイテムの各値とグローバルタグ）が
        前回と同じカードは作り直さずに再利用する。
        """
        self.current_items = list(items)

        if hasattr(self, "slide_panel"):
            self.slide_panel.hide()

        if global_tags is None:
            global_tags = self.db.get_all_item_global_tags() if self.db else {}
        self.all_gtags = global_tags

        # 同じ ID が重複している一覧（テスト用のダミーなど）はカードを使い回せないため、作り置きを使わない
        ids = [it[0] for it in self.current_items]
        self._allow_reuse = len(set(ids)) == len(ids)
        if not self._allow_reuse:
            self._discard_cards(list(self._card_cache))

        for c in self.cards:
            c.hide()
        self.cards = []
        self._shown_range = None
        self._grid = None

        if not self.current_items:
            self.empty_label.show()
            self._relayout_cards()
            return

        self.empty_label.hide()
        self._relayout_cards()

    # -------------------------------------------------------------------------
    # 配置（仮想化）
    # -------------------------------------------------------------------------
    def _get_usable_width(self):
        """スクロールエリアのビューポートの有効幅を取得"""
        vw = self.scroll.viewport().width()
        if vw > 100:
            return vw
        return max(400, self.width() - 32)

    def _viewport_height(self):
        vh = self.scroll.viewport().height()
        # 表示前（大きさが決まる前）は、一般的な画面1枚分として扱う
        return vh if self.scroll.viewport().isVisible() and vh > 50 else 900

    def _calc_grid_cols(self):
        """モードとウィンドウ幅に応じた適切な列数を計算"""
        w = self._get_usable_width()
        if self.view_mode == "large":
            cw = 270
            min_spacing = 16
            return max(2, w // (cw + min_spacing))
        elif self.view_mode == "small":
            cw = 165
            min_spacing = 12
            return max(3, w // (cw + min_spacing))
        elif self.view_mode == "list":
            # 一覧モード: 通常幅で2列、大画面で3〜4列以上に拡張
            return max(2 if w >= 560 else 1, w // 380)
        else:
            # "medium"
            cw = 216
            min_spacing = 14
            return max(2, w // (cw + min_spacing))

    def column_count(self):
        """現在の列数"""
        return self._calc_grid_cols()

    def _compute_grid(self):
        """列数・カードの大きさ・間隔・余白を計算する（従来のグリッド配置と同じ寸法）"""
        w = self._get_usable_width()
        cols = self._calc_grid_cols()
        top = 8
        if self.view_mode == "list":
            spacing = 12
            margin_lr = 8
            cell_w = max(1, (w - margin_lr * 2 - spacing * (cols - 1)) // cols)
            card_w, card_h = cell_w, ScenarioListCard.HEIGHT
        else:
            card_w, card_h = ScenarioCard.SIZE_CONFIGS.get(self.view_mode, {}).get("card", (216, 305))
            extra_w = max(0, w - cols * card_w)
            # 余白の配分: カード間スペースを 14〜36px の範囲で動的に広げ、残りを左右マージンにする
            if cols > 1:
                spacing = max(14, min(36, extra_w // (cols + 1)))
                margin_lr = max(8, (extra_w - spacing * (cols - 1)) // 2)
            else:
                spacing = 14
                margin_lr = max(8, extra_w // 2)
            cell_w = card_w
        return {
            "width": w, "cols": cols, "spacing": spacing, "margin_lr": margin_lr, "top": top,
            "cell_w": cell_w, "card_w": card_w, "card_h": card_h, "pitch": card_h + spacing,
        }

    def _card_rect(self, index):
        g = self._grid
        r, c = divmod(index, g["cols"])
        x = g["margin_lr"] + c * (g["cell_w"] + g["spacing"])
        y = g["top"] + r * g["pitch"]
        return QRect(x, y, g["card_w"], g["card_h"])

    def _relayout_cards(self):
        """列数・余白を計算し直し、表示範囲のカードを配置する（幅が変わったとき・表示されたとき）"""
        grid = self._compute_grid()
        n = len(self.current_items)
        if n:
            rows = (n - 1) // grid["cols"] + 1
            content_h = grid["top"] * 2 + rows * grid["card_h"] + (rows - 1) * grid["spacing"]
        else:
            content_h = self._viewport_height()
        self.grid_container.setFixedHeight(max(content_h, 1))
        self.empty_label.setGeometry(0, 0, grid["width"], max(content_h, self._viewport_height()))

        if grid != self._grid:
            self._grid = grid
            self._shown_range = None  # 位置が変わったので表示範囲のカードを置き直す
        self._update_visible_cards()

    def _on_scrolled(self, _value):
        self._update_visible_cards()

    def _update_visible_cards(self):
        """画面に見えている範囲（と前後1画面分）のカードだけを作って配置し、それ以外は隠す"""
        if self._grid is None:
            return
        n = len(self.current_items)
        g = self._grid
        if n == 0:
            first, last = 0, 0
        else:
            top = self.scroll.verticalScrollBar().value()
            vh = self._viewport_height()
            first_row = max(0, (top - vh - g["top"]) // g["pitch"])
            last_row = max(0, (top + vh * 2 - g["top"]) // g["pitch"])
            first = min(n, first_row * g["cols"])
            last = min(n, (last_row + 1) * g["cols"])
        if (first, last) == self._shown_range:
            return
        self._shown_range = (first, last)

        reuse = getattr(self, "_allow_reuse", True)
        new_cards = []
        for index in range(first, last):
            it = self.current_items[index]
            card = self._card_for(it) if reuse else self._make_card(it, self.all_gtags.get(it[0], []))
            card.setGeometry(self._card_rect(index))
            if card.isHidden():
                card.show()
            new_cards.append(card)

        shown = set(map(id, new_cards))
        for c in self.cards:
            if id(c) not in shown:
                c.hide()
                if not reuse:
                    c.setParent(None)
                    c.deleteLater()
        self.cards = new_cards
        self._trim_idle_cards(shown)

        # 配置が確定してから、見えているカードの表紙を優先して読み込む
        self._cover_timer.start()

    def _trim_idle_cards(self, shown):
        """表示範囲外の作り置きカードが多すぎる場合、長く使われていないものから破棄する"""
        idle = [item_id for item_id, (_sig, c) in self._card_cache.items() if id(c) not in shown]
        excess = len(idle) - self.MAX_IDLE_CARDS
        if excess > 0:
            self._discard_cards(idle[:excess])

    # -------------------------------------------------------------------------
    # 表紙のバックグラウンド読み込み
    # -------------------------------------------------------------------------
    def _request_covers(self):
        """表紙が未読み込みのカードについて、画面に見えているものから順に読み込みを依頼する"""
        if not self.cover_loader:
            return
        pending = [c for c in self.cards if c.needs_cover]
        if not pending:
            return
        top = self.scroll.verticalScrollBar().value()
        visible = QRect(0, top, max(1, self._get_usable_width()), self._viewport_height())
        first = [c for c in pending if c.geometry().intersects(visible)]
        first_ids = set(map(id, first))
        rest = [c for c in pending if id(c) not in first_ids]
        mode = self.view_mode
        self.cover_loader.request([(c.item_id, mode, c.thumb_key) for c in first + rest])

    def _on_cover_loaded(self, item_id, mode, key, image, conflict):
        if mode != self.view_mode:
            return
        cached = self._card_cache.get(item_id)
        targets = [cached[1]] if cached else [c for c in self.cards if c.item_id == item_id]
        for card in targets:
            if card.thumb_key == key and not card.cover_loaded:
                card.set_cover_image(image, conflict)

    def wait_for_covers(self, msecs=5000):
        """表紙の読み込みが終わるまで待ち、結果を反映する（テスト・画面キャプチャ用）"""
        from PySide6.QtWidgets import QApplication
        self._cover_timer.stop()
        self._request_covers()
        if self.cover_loader:
            self.cover_loader.wait(msecs)
        QApplication.processEvents()

    # -------------------------------------------------------------------------
    # 選択
    # -------------------------------------------------------------------------
    def clear_selection(self):
        """カードの選択状態を解除"""
        self.selected_item_id = None
        for _sig, card in self._card_cache.values():
            if card.is_selected:
                card.set_selected(False)
        for card in self.cards:
            if card.is_selected:
                card.set_selected(False)
        if hasattr(self, "slide_panel"):
            self.slide_panel.slide_out()

    def select_card_by_id(self, item_id):
        """指定IDのカードを選択状態にし、必要に応じてスクロール"""
        self.selected_item_id = item_id
        for _sig, card in self._card_cache.values():
            if card.is_selected != (card.item_id == item_id):
                card.set_selected(card.item_id == item_id)
        index = next((i for i, it in enumerate(self.current_items) if it[0] == item_id), None)
        if index is not None and self._grid is not None:
            rect = self._card_rect(index)
            self.scroll.ensureVisible(rect.center().x(), rect.center().y(), rect.width() // 2, rect.height() // 2)
            self._update_visible_cards()

    def _on_card_clicked(self, item_id):
        # 既に選択中のカードを再度クリックした場合は選択を解除
        if self.selected_item_id == item_id:
            self.clear_selection()
            self.selection_cleared.emit()
            return

        self.selected_item_id = item_id
        for _sig, card in self._card_cache.values():
            if card.is_selected != (card.item_id == item_id):
                card.set_selected(card.item_id == item_id)
        self.card_clicked.emit(item_id)

    def eventFilter(self, watched, event):
        """書架の背景・余白がクリックされたらカード選択を解除"""
        if watched is self.scroll.viewport() and event.type() == QEvent.Resize:
            # スクロールバーの出入りなどでビューポート幅だけが変わった場合も並べ直す
            if event.size().width() != event.oldSize().width():
                QTimer.singleShot(0, self._relayout_cards)
        if watched in (self.scroll.viewport(), self.grid_container):
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                # viewport から見た場合は grid_container の座標系に変換
                if watched == self.scroll.viewport():
                    cont_pos = self.grid_container.mapFrom(self.scroll.viewport(), pos)
                else:
                    cont_pos = pos

                child = self.grid_container.childAt(cont_pos)
                is_card_child = False
                curr = child
                while curr and curr != self.grid_container:
                    if isinstance(curr, (ScenarioCard, ScenarioListCard)):
                        is_card_child = True
                        break
                    curr = curr.parentWidget()

                if not is_card_child:
                    if self.selected_item_id is not None:
                        self.clear_selection()
                        self.selection_cleared.emit()

        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        """書架フレーム自体の余白をクリックされた場合の選択解除"""
        if event.button() == Qt.LeftButton:
            if self.selected_item_id is not None:
                self.clear_selection()
                self.selection_cleared.emit()
        super().mousePressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.slide_panel.update_geometry(self.width(), self.height())
        # ウィンドウ表示直後のビューポート確定タイミングで再配置を実行
        QTimer.singleShot(0, self._relayout_cards)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.slide_panel.update_geometry(self.width(), self.height())
        self._relayout_cards()

    def _on_card_hover_entered(self, item):
        """カードにマウスが乗った時、書架枠の下辺からあらすじパネルをスライドイン"""
        self.slide_timer.stop()
        item_id = item[0]
        self.current_hovered_item_id = item_id

        gtags = []
        if hasattr(self, "all_gtags") and item_id in self.all_gtags:
            gtags = self.all_gtags[item_id]
        elif self.db:
            gtags = self.db.get_item_tags(item_id, is_global=True)

        self.slide_panel.set_item(item, global_tags=gtags)
        self.slide_panel.update_geometry(self.width(), self.height())
        self.slide_panel.slide_in()

    def _on_card_hover_left(self, item):
        """カードからマウスが離れた時、短時間のディレイ後にスライドアウト（カード間移動時は維持）"""
        if self.current_hovered_item_id == item[0]:
            self.slide_timer.start(90)

    def _on_slide_timeout(self):
        """ディレイ経過後にパネルを枠下へ退避"""
        self.current_hovered_item_id = None
        self.slide_panel.slide_out()

    def _on_sort_changed(self, idx):
        sort_key = self.sort_combo.currentData()
        self.sort_changed.emit(sort_key)
