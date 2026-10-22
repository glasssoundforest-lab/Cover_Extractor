"""メインウィンドウモジュール (gui_qt/main_window.py)

西洋古書・グリモワール調の世界観で統一されたメインウィンドウ。
上部ヘッダー、左側サイドバー、中央書架グリッド、下部ステータスバーを統合し、
データ層および Rust DLL と連携してリアルタイムな閲覧・検索・取り込みを提供します。
"""

import os
import sys
import threading
from PySide6.QtCore import Qt, QSettings, QRect, QEvent, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFileDialog,
    QMessageBox,
    QApplication,
)

import app_settings
from core import (
    Database,
    RustDllExtractor,
    collect_scenario_targets,
    extract_scenario_data,
    sort_items,
    global_tag_sort_key,
)
from .theme import Theme
from .components import (
    OrnateFrame,
    OrnateDivider,
    HeaderBar,
    Sidebar,
    BookshelfGrid,
    StatusBar,
    ScenarioContextMenu,
)
# ダイアログ類は Notion 通信（urllib / http.client）などを連鎖的に読み込み起動を遅くするため、
# 開くときに初めて import する。

from .components.ornate_title_bar import OrnateTitleBar


UNSET_TAG_KEYWORDS = {
    "未設定",
    "タグなし",
    "タグ無し",
    "ローカルタグなし",
    "ローカルタグ無し",
    "なし",
    "#なし",
    "#タグなし",
    "tag:none",
    "local:none",
}


class MainWindow(QMainWindow):
    """西洋古書・グリモワール調メインウィンドウ"""
    extractor_loaded = Signal(object, bool)  # (RustDllExtractor または None, 読み込めたか)

    SEARCH_DEBOUNCE_MS = 200  # 検索欄の入力が止まってから絞り込むまでの待ち時間
    AUTO_SYNC_STARTUP_DELAY_MS = 8000  # 自動同調が有効なとき、起動してから最初に同調するまでの待ち時間

    def __init__(self, db_path="catalog.db"):
        super().__init__()
        self.setWindowTitle("魔導書架  ―  TRPG Scenario Archive")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)

        # バックエンド初期化
        self.db = Database(db_path)
        self._notion_worker = None  # バックグラウンドで動いている Notion との同調
        self._auto_sync_timer = QTimer(self)
        self._auto_sync_timer.timeout.connect(lambda: self._start_notion_sync(auto=True))
        self._auto_sync_kickoff = QTimer(self)  # 起動直後の1回目
        self._auto_sync_kickoff.setSingleShot(True)
        self._auto_sync_kickoff.timeout.connect(lambda: self._start_notion_sync(auto=True))
        # Rust エンジン（DLL）は別スレッドで読み込む。DLL が無い場合はソースからのビルドに数分かかるため、
        # 画面の表示を待たせない。rust_ok は読み込み中 None、成功 True、失敗 False。
        self._extractor = None
        self.rust_ok = None
        self.extractor_loaded.connect(self._on_extractor_loaded)
        self._extractor_thread = threading.Thread(target=self._load_extractor, name="rust-extractor-loader", daemon=True)
        self._extractor_thread.start()

        # 一覧表示用のタグ情報（reload_data で読み込み、絞り込みのたびには DB を読まない）
        self._all_item_tags = {}
        self._all_item_global_tags = {}

        # 検索欄の入力は少し待ってからまとめて反映する（1文字ごとに書架を並べ直さない）
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(self.SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._filter_and_display)

        # 状態管理
        self.all_items = []
        self.search_text = ""
        self.search_type = "all"
        self.header_tags = []
        self.sidebar_local_search_text = ""
        self.current_system = "すべて"
        self.selected_tags = []
        self.current_sort = "added_desc"
        self.selected_item = None

        # ウィンドウサイズ・位置保存用タイマー（リサイズ・移動時のデバウンス保存）
        self._save_geom_timer = QTimer(self)
        self._save_geom_timer.setSingleShot(True)
        self._save_geom_timer.setInterval(400)
        self._save_geom_timer.timeout.connect(self._save_geometry_to_ini)

        self._init_ui()
        self._init_window_geometry()
        self.reload_data()
        self._apply_auto_sync_settings(at_startup=True)

    def _init_ui(self):
        from PySide6.QtGui import QPixmap

        # ウィンドウ全体の装飾外枠フレーム（背景画像: 羽ペン・懐中時計・アンティークデスク）
        bg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "window_bg.png")
        bg_pix = QPixmap(bg_path) if os.path.exists(bg_path) else None

        self.root_frame = OrnateFrame(self, bracket_size=0, bg_color=Theme.BG_BASE, bg_pixmap=bg_pix, draw_border=False, fit_mode="stretch")
        self.root_frame.setMouseTracking(True)
        self.root_frame.installEventFilter(self)
        self.setCentralWidget(self.root_frame)

        main_layout = QVBoxLayout(self.root_frame)
        main_layout.setContentsMargins(16, 10, 16, 22)
        main_layout.setSpacing(6)

        # 0. 画面デザイン一体型タイトルバー
        self.title_bar = OrnateTitleBar("魔導書架  ―  TRPG Scenario Archive", parent=self, show_minimize=True, show_maximize=True, show_close=True)
        main_layout.addWidget(self.title_bar)

        # 1. 上部ヘッダーバー (dbを渡してタグ複数選択ポップアップと連携)
        self.header_bar = HeaderBar(self, db=self.db)
        self.header_bar.search_changed.connect(self._on_search_changed)
        self.header_bar.search_edit.returnPressed.connect(self._flush_search)
        self.header_bar.search_type_changed.connect(self._on_search_type_changed)
        self.header_bar.tags_selected.connect(self._on_header_tags_selected)
        self.header_bar.sort_changed.connect(self._on_sort_changed)
        self.header_bar.import_requested.connect(self._on_import_requested)
        self.header_bar.import_url_requested.connect(self._on_import_url_requested)
        self.header_bar.view_mode_changed.connect(self._on_view_mode_changed)
        self.header_bar.settings_requested.connect(self._on_settings_requested)
        self.header_bar.notion_sync_requested.connect(self._on_notion_sync_requested)
        self.header_bar.notion_diff_requested.connect(self._on_notion_diff_requested)
        main_layout.addWidget(self.header_bar)


        main_layout.addWidget(OrnateDivider(self, height=8))

        # 2. 中央エリア（左: サイドバー、右: 書架グリッド）
        content_layout = QHBoxLayout()
        content_layout.setSpacing(10)

        # 左側サイドバー
        self.sidebar = Sidebar(self)
        self.sidebar.system_changed.connect(self._on_system_changed)
        self.sidebar.tags_changed.connect(self._on_tags_changed)
        self.sidebar.local_tag_search_changed.connect(self._on_sidebar_local_search_changed)
        content_layout.addWidget(self.sidebar)

        # 右側メイン書架（枠右上に並び順コンボボックスを配置）
        self.bookshelf = BookshelfGrid(self, db=self.db)
        self.bookshelf.card_clicked.connect(self._on_card_clicked)
        self.bookshelf.card_double_clicked.connect(self._on_card_double_clicked)
        self.bookshelf.card_context_menu_requested.connect(self._on_card_context_menu)
        self.bookshelf.sort_changed.connect(self._on_sort_changed)
        self.bookshelf.selection_cleared.connect(self._on_selection_cleared)
        content_layout.addWidget(self.bookshelf)

        main_layout.addLayout(content_layout)

        main_layout.addWidget(OrnateDivider(self, height=8))

        # 3. 下部ステータスバー
        self.status_bar = StatusBar(self)
        self.status_bar.sync_cancel_requested.connect(self._on_notion_sync_cancel)
        main_layout.addWidget(self.status_bar)

        # 4. ショートカットキー初期化
        self.shortcuts = []
        self._init_shortcuts()

    # -------------------------------------------------------------------------
    # Rust エンジンの読み込み
    # -------------------------------------------------------------------------
    def _load_extractor(self):
        """（別スレッド）Rust DLL を読み込む。完了を extractor_loaded で画面スレッドへ知らせる"""
        try:
            ex = RustDllExtractor()
        except Exception as e:  # noqa: BLE001
            print(f"[MainWindow] Rust engine unavailable: {e}")
            ex = None
        self._extractor = ex
        self.extractor_loaded.emit(ex, ex is not None)

    def _on_extractor_loaded(self, ex, ok):
        self._extractor = ex
        self.rust_ok = ok
        self._update_status_bar()

    @property
    def extractor(self):
        """Rust エンジン。読み込み中なら読み込み完了まで待つ（DLL のビルド中は時間がかかる）"""
        thread = getattr(self, "_extractor_thread", None)
        if thread is not None and thread.is_alive():
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                thread.join()
            finally:
                QApplication.restoreOverrideCursor()
        if self.rust_ok is None:
            self.rust_ok = self._extractor is not None
        return self._extractor

    @extractor.setter
    def extractor(self, value):
        self._extractor = value

    def _update_status_bar(self):
        sel = self.selected_item
        self.status_bar.update_status(
            total_count=len(self.all_items),
            selected_title=sel[2] if sel else None,
            selected_sys=sel[3] if sel else None,
            rust_ok=self.rust_ok,
        )

    def reload_data(self):
        """データベースから全件再読み込みしてUIを更新"""
        # 表紙の本体は読まない（表紙は書架がバックグラウンドで見えている分から読み込む）
        self.all_items = self.db.get_item_summaries()
        self._all_item_tags = self.db.get_all_item_tags()
        self._all_item_global_tags = self.db.get_all_item_global_tags()
        self.bookshelf.prune({it[0] for it in self.all_items})

        # システム件数、お気に入り件数、しおり件数の集計
        system_counts = {}
        fav_count = 0
        bm_count = 0
        for it in self.all_items:
            sys_name = it[3] or "その他"
            system_counts[sys_name] = system_counts.get(sys_name, 0) + 1
            if len(it) > 9 and it[9]:
                fav_count += 1
            if len(it) > 10 and it[10]:
                bm_count += 1
        self.sidebar.set_systems(system_counts, favorite_count=fav_count, bookmark_count=bm_count)

        # タグ一覧の取得: ユーザー要望に従い「グローバルタグのみ」をサイドバーに渡す
        global_tag_tuples = self.db.get_global_tags()
        tag_dict = {t[1]: t[2] for t in global_tag_tuples}
        tag_names = [t[1] for t in global_tag_tuples]
        # 優先順にソート (CoC, マダミス, 未通過, 通過済み, GM可)
        ordered_tags = sorted([t for t in tag_names if t != "未設定"], key=global_tag_sort_key)
        # ユーザー回答に基づき「未設定」ピルボタンを末尾に追加（グローバルタグ無の絞り込み用）
        ordered_tags.append("未設定")
        tag_dict["未設定"] = "#607d8b"  # シックなアンティークスレートグレー
        tags_with_colors = [(t, tag_dict.get(t)) for t in ordered_tags]
        self.sidebar.set_tags(tags_with_colors)

        self._filter_and_display()

    def _filter_and_display(self):
        """検索、システム、タグ、ソートを適用してカードを表示"""
        self._search_timer.stop()
        filtered = []
        all_tags_dict = self._all_item_tags

        for it in self.all_items:
            item_id = it[0]
            title = (it[2] or "").lower()
            sys_name = it[3] or "その他"
            if all_tags_dict:
                tag_rows = all_tags_dict.get(item_id, [])
                item_global_tags = [t[1] for t in tag_rows if len(t) > 3 and t[3] == 1]
                item_local_tags = [t[1] for t in tag_rows if len(t) > 3 and t[3] == 0]
                it_tags = [t[1] for t in tag_rows]
            else:
                tag_rows = self.db.get_item_tags(item_id)
                item_global_tags = [t[1] for t in tag_rows if len(t) > 3 and t[3] == 1]
                item_local_tags = [t[1] for t in tag_rows if len(t) > 3 and t[3] == 0]
                it_tags = [t[1] for t in tag_rows]

            # 1. システム分類・お気に入り・しおりフィルター
            if self.current_system == "__favorite__":
                is_fav = bool(it[9]) if len(it) > 9 and it[9] is not None else False
                if not is_fav:
                    continue
            elif self.current_system == "__bookmarked__":
                is_bm = bool(it[10]) if len(it) > 10 and it[10] is not None else False
                if not is_bm:
                    continue
            elif self.current_system != "すべて" and sys_name != self.current_system:
                continue

            # 2. グローバルタグフィルター（サイドバー選択）
            if self.selected_tags:
                if "未設定" in self.selected_tags:
                    # グローバルタグが1つも付いていないものを絞り込む
                    if len(item_global_tags) > 0:
                        continue
                else:
                    if not all(t in it_tags for t in self.selected_tags):
                        continue

            # 3. ヘッダーのタグ選択フィルター（複数タグ選択ポップアップ）
            if getattr(self, "header_tags", None):
                matched_header = True
                for ht in self.header_tags:
                    if ht == "未設定":
                        # 未設定が含まれている場合、グローバルまたはローカルタグが未設定
                        if len(item_global_tags) > 0 and len(item_local_tags) > 0:
                            matched_header = False
                            break
                    elif ht not in it_tags:
                        matched_header = False
                        break
                if not matched_header:
                    continue

            # 4. サイドバーのローカルタグ検索フィルター（互換用）
            if getattr(self, "sidebar_local_search_text", ""):
                q_local = self.sidebar_local_search_text.lower()
                if q_local in UNSET_TAG_KEYWORDS:
                    if len(item_local_tags) > 0:
                        continue
                else:
                    if not any(q_local in lt.lower() for lt in item_local_tags):
                        continue

            # 5. 上部ヘッダーの検索テキストフィルター（検索種類対応）
            if self.search_text:
                q = self.search_text.lower()
                stype = getattr(self, "search_type", "all")

                if stype == "tag":
                    # タグ検索モード
                    if q in UNSET_TAG_KEYWORDS:
                        if len(item_local_tags) > 0 and len(item_global_tags) > 0:
                            continue
                    else:
                        words = q.split()
                        matched_all_words = True
                        for w in words:
                            if not any(w in t.lower() for t in it_tags):
                                matched_all_words = False
                                break
                        if not matched_all_words:
                            continue
                elif stype == "title":
                    # 題名検索
                    words = q.split()
                    if not all(w in title for w in words):
                        continue
                elif stype == "system":
                    # システム検索
                    words = q.split()
                    if not all(w in sys_name.lower() for w in words):
                        continue
                else:
                    # すべて検索 (all)
                    if q in UNSET_TAG_KEYWORDS:
                        if len(item_local_tags) > 0:
                            continue
                    else:
                        words = q.split()
                        matched_all_words = True
                        overview = (it[6] or "").lower()
                        synopsis = (it[7] or "").lower()
                        for w in words:
                            w_match = (
                                w in title
                                or w in sys_name.lower()
                                or any(w in t.lower() for t in it_tags)
                                or w in overview
                                or w in synopsis
                            )
                            if not w_match:
                                matched_all_words = False
                                break
                        if not matched_all_words:
                            continue

            filtered.append(it)

        # 6. ソート適用
        filtered = self._sort_items_list(filtered, self.current_sort)
        self.filtered_items = filtered

        # 書架と見出しの更新
        if self.current_system == "__favorite__":
            display_title = "★ お気に入り"
        elif self.current_system == "__bookmarked__":
            display_title = "🔖 しおり"
        elif "未設定" in self.selected_tags:
            display_title = f"{self.current_system}  (タグ未設定)"
        elif getattr(self, "header_tags", None):
            display_title = f"{self.current_system}  (タグ選択: {len(self.header_tags)}件)"
        elif getattr(self, "sidebar_local_search_text", "") in UNSET_TAG_KEYWORDS:
            display_title = f"{self.current_system}  (ローカルタグ未設定)"
        elif self.search_text and self.search_text.lower() in UNSET_TAG_KEYWORDS:
            display_title = f"{self.current_system}  (ローカルタグ未設定)"
        elif self.search_text and getattr(self, "search_type", "all") == "tag":
            display_title = f"{self.current_system}  (タグ検索: {self.search_text})"
        else:
            display_title = self.current_system
        self.bookshelf.set_title(display_title, len(filtered))
        self.bookshelf.display_items(filtered, self._all_item_global_tags)

        # ステータスバー更新
        self._update_status_bar()

    def _sort_items_list(self, items, sort_key):
        """ソート処理"""
        if sort_key == "added_asc":
            return sorted(items, key=lambda it: it[0])
        elif sort_key == "title_asc":
            return sorted(items, key=lambda it: (it[2] or "").lower())
        elif sort_key == "title_desc":
            return sorted(items, key=lambda it: (it[2] or "").lower(), reverse=True)
        elif sort_key == "system":
            return sorted(items, key=lambda it: (it[3] or "").lower())
        else:
            # added_desc (デフォルト)
            return sorted(items, key=lambda it: it[0], reverse=True)

    def _on_search_changed(self, text):
        self.search_text = text.strip()
        if self.search_text:
            self._search_timer.start()
        else:
            # 検索欄を空にしたときは待たずにすぐ全件表示へ戻す
            self._filter_and_display()

    def _flush_search(self):
        """Enter キーで、待ち時間を待たずに検索を反映する"""
        if self._search_timer.isActive():
            self._filter_and_display()

    def _on_search_type_changed(self, stype):
        self.search_type = stype
        self._filter_and_display()

    def _on_header_tags_selected(self, tags):
        self.header_tags = list(tags)
        self._filter_and_display()

    def _on_sidebar_local_search_changed(self, text):
        self.sidebar_local_search_text = text.strip()
        self._filter_and_display()

    def _on_system_changed(self, sname):
        self.current_system = sname
        self._filter_and_display()

    def _on_tags_changed(self, tags):
        self.selected_tags = tags
        self._filter_and_display()

    def _on_sort_changed(self, sort_key):
        self.current_sort = sort_key
        self._filter_and_display()

    def _init_shortcuts(self):
        """設定ファイルからメイン画面ショートカットを登録"""
        for sc in self.shortcuts:
            sc.setEnabled(False)
            sc.deleteLater()
        self.shortcuts.clear()

        cfg = app_settings.get_all_shortcuts()
        search_seq = cfg.get("main_search", "Ctrl+F")
        if search_seq:
            sc_search = QShortcut(QKeySequence(search_seq), self)
            sc_search.activated.connect(self._focus_search)
            self.shortcuts.append(sc_search)

        open_seq = cfg.get("main_open", "Return")
        if open_seq:
            sc_open = QShortcut(QKeySequence(open_seq), self)
            sc_open.activated.connect(self._open_selected_item)
            self.shortcuts.append(sc_open)

    def _focus_search(self):
        """検索ボックスにフォーカスして全選択"""
        self.header_bar.search_edit.setFocus()
        self.header_bar.search_edit.selectAll()

    def _open_selected_item(self):
        """現在選択中のシナリオの本を開く"""
        if self.selected_item:
            self._on_card_double_clicked(self.selected_item[0])

    def _on_view_mode_changed(self, mode):
        self.bookshelf.set_view_mode(mode)

    def _on_settings_requested(self):
        from .dialogs.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self.db, self)
        dlg.settings_saved.connect(self._init_shortcuts)
        dlg.settings_saved.connect(self._apply_auto_sync_settings)
        dlg.tags_changed.connect(self.reload_data)
        dlg.exec()
        # バックアップからの復元で表紙が入れ替わった場合に備え、カードを作り直す
        self.bookshelf.invalidate_all()
        self.reload_data()

    def _on_notion_sync_requested(self):
        """Notion書架との同調をバックグラウンドで始める（同調中も書架はそのまま使える）"""
        self._start_notion_sync(auto=False)

    def _start_notion_sync(self, auto=False):
        """Notion との同調を別スレッドで始める。

        auto=True（自動同調）のときは、手元と Notion が食い違う本があっても比較画面を出さずに保留し、
        接続できない等のエラーもダイアログを出さずにステータスバーへ表示するだけにする。
        """
        if self._notion_worker is not None and self._notion_worker.isRunning():
            if not auto:
                self.status_bar.show_sync_message("Notion との同調はすでに実行中です", 3000)
            return
        from .dialogs.notion_sync_dialog import NotionSyncWorker, resolve_notion_diff

        worker = NotionSyncWorker(self.db, self)
        label = "Notion と自動同調中" if auto else "Notion と同調中"
        worker.progress.connect(
            lambda current, total, title: self.status_bar.show_sync_progress(
                current, total, f"{label}（{current}/{total}）: 『{title}』"
            )
        )
        if auto:
            worker.defer_conflicts = True
        else:
            # Notion 側で変わった本が手元とも食い違う場合だけ、比較画面で採用する内容を選んでもらう
            worker.has_diff_receiver = True
            worker.request_diff_resolution.connect(
                lambda current, notion, queue_and_id: resolve_notion_diff(self, self.db, current, notion, queue_and_id)
            )
        worker.finished_all.connect(
            lambda success, fail, error_msg: self._on_notion_sync_finished(worker, auto, success, fail, error_msg)
        )
        worker.finished.connect(worker.deleteLater)
        self._notion_worker = worker
        self.status_bar.show_sync_progress(0, 0, "Notion に接続しています…")
        worker.start()

    def _on_notion_sync_cancel(self):
        if self._notion_worker is not None and self._notion_worker.isRunning():
            self._notion_worker.requestInterruption()

    def _on_notion_sync_finished(self, worker, auto, success, fail, error_msg):
        self._notion_worker = None
        if error_msg:
            if auto:
                first_line = error_msg.strip().splitlines()[0] if error_msg.strip() else ""
                self.status_bar.show_sync_message(f"自動同調できませんでした: {first_line}", 12000)
            else:
                self.status_bar.hide_sync()
                QMessageBox.warning(self, "Notion同調エラー", error_msg)
            return
        if worker.imported_count:
            # 手元の内容が変わったときだけ書架を描き直す
            self.bookshelf.invalidate_all()
            self.reload_data()

        if worker.imported_count or worker.pushed_count:
            text = f"Notion と同調しました（取り込み {worker.imported_count} 件・送信 {worker.pushed_count} 件）"
        else:
            text = "Notion と同調しました（変更なし）"
        if worker.deferred_count:
            text += f"　食い違う {worker.deferred_count} 件は保留しました（手動の同調で確認できます）"
        if fail:
            text += f"　{fail} 件は失敗しました"
        self.status_bar.show_sync_message(text, 12000 if (fail or worker.deferred_count) else 6000)

    def _apply_auto_sync_settings(self, at_startup=False):
        """設定に合わせて自動同調のタイマーを動かす（初期値は無効）"""
        enabled, interval_min = app_settings.get_notion_auto_sync()
        self._auto_sync_timer.stop()
        if not enabled:
            self._auto_sync_kickoff.stop()
            return
        if interval_min > 0:
            self._auto_sync_timer.start(interval_min * 60 * 1000)
        if at_startup:
            # 起動直後の読み込みと重ならないよう、少し待ってから始める
            self._auto_sync_kickoff.start(self.AUTO_SYNC_STARTUP_DELAY_MS)

    def _on_notion_diff_requested(self):
        """Notion書架との差異・不足分照合ダイアログを表示"""
        from .dialogs.notion_diff_dialog import NotionDiffDialog
        dlg = NotionDiffDialog(self.db, self)
        dlg.exec()
        self.bookshelf.invalidate_all()
        self.reload_data()


    def _on_card_clicked(self, item_id):
        self.selected_item = self.db.get_item(item_id)
        self._update_status_bar()

    def _on_selection_cleared(self):
        """カード選択解除時のステータスバー表示リセット"""
        self.selected_item = None
        self._update_status_bar()

    def _on_card_double_clicked(self, item_id):
        """本を開く（詳細・あらすじ編集ダイアログを表示）"""
        from .dialogs.item_detail_dialog import ItemDetailDialog
        current_ids = [it[0] for it in getattr(self, "filtered_items", [])]
        # 詳細画面は Rust エンジンを使わないため、読み込み完了を待たずに渡す
        dlg = ItemDetailDialog(item_id, self.db, self._extractor, item_ids=current_ids, parent=self)
        dlg.item_updated.connect(self._on_item_updated)
        dlg.exec()

    def _on_item_updated(self, item_id):
        """詳細画面での編集（表紙の差し替えを含む）を書架へ反映する"""
        self.bookshelf.invalidate_items([item_id])
        self.reload_data()

    def _on_card_context_menu(self, item_id, global_pos):
        """右クリックコンテキストメニュー（複数タグ選択・欄外クリック保存・本を開く・削除・お気に入り）"""
        menu = ScenarioContextMenu(item_id, self.db, self)
        menu.tags_updated.connect(lambda _: self.reload_data())
        menu.favorite_toggled.connect(lambda _id, _fav: self.reload_data())
        menu.bookmark_toggled.connect(lambda _id, _bm: self.reload_data())
        menu.open_detail_requested.connect(self._on_card_double_clicked)
        menu.delete_requested.connect(self._on_delete_item_requested)
        menu.exec(global_pos)

    def _on_delete_item_requested(self, item_id):
        """シナリオの書架からの除籍（削除）"""
        it = self.db.get_item(item_id)
        title = it[2] if it else "このシナリオ"
        reply = QMessageBox.question(
            self,
            "書架からの除籍確認",
            f"『{title}』を書架から除籍（削除）しますか？\n（元のファイル自体は削除されません）",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.db.delete_item(item_id)
            if self.selected_item and self.selected_item[0] == item_id:
                self.selected_item = None
            self.reload_data()

    def _on_import_requested(self):
        """ファイルまたはフォルダ選択ダイアログからの取り込み"""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "シナリオファイルの取り込み",
            "",
            "シナリオファイル (*.pdf *.zip);;すべてのファイル (*.*)",
        )
        if paths:
            self._import_targets(paths)

    def _on_import_url_requested(self, initial_url=""):
        """WebサイトまたはNotionのURLからのシナリオ取り込みダイアログを表示"""
        from .dialogs.add_scenario_url_dialog import AddScenarioUrlDialog
        dlg = AddScenarioUrlDialog(self.db, initial_url=initial_url, parent=self)
        if dlg.exec():
            imported_id = getattr(dlg, "imported_item_id", None) or getattr(dlg, "added_item_id", None)
            if imported_id:
                self.bookshelf.invalidate_items([imported_id])
            self.reload_data()
            if imported_id:
                self.selected_item = self.db.get_item(imported_id)
                if self.selected_item:
                    self._update_status_bar()
                    # 追加されたカードが見えるようにフォーカス
                    self.bookshelf.select_card_by_id(imported_id)

    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasUrls():
            event.acceptProposedAction()
        elif md.hasText():
            text = md.text().strip()
            if text.startswith("http://") or text.startswith("https://") or text.startswith("notion://"):
                event.acceptProposedAction()

    def dropEvent(self, event):
        md = event.mimeData()
        paths = []
        urls_to_fetch = []

        if md.hasUrls():
            for url in md.urls():
                local_path = url.toLocalFile()
                if local_path and os.path.exists(local_path):
                    paths.append(local_path)
                else:
                    url_str = url.toString()
                    if url_str.startswith("http://") or url_str.startswith("https://") or url_str.startswith("notion://"):
                        urls_to_fetch.append(url_str)
        elif md.hasText():
            text = md.text().strip()
            if text.startswith("http://") or text.startswith("https://") or text.startswith("notion://"):
                urls_to_fetch.append(text)

        if paths:
            self._import_targets(paths)
        elif urls_to_fetch:
            self._on_import_url_requested(urls_to_fetch[0])

    def _import_targets(self, paths):
        """ターゲットの解析とデータベースへの一括保存（非同期プログレスダイアログ）"""
        targets = collect_scenario_targets(paths)
        if not targets:
            QMessageBox.information(self, "案内", "取り込み可能なシナリオ（PDF, ZIP, フォルダ）が見つかりませんでした。")
            return

        from .dialogs.import_progress_dialog import ImportProgressDialog
        dlg = ImportProgressDialog(targets, self.extractor, self.db, self)
        dlg.exec()

        # 同じファイルを取り込み直した場合は表紙が変わるため、カードを作り直す
        self.bookshelf.invalidate_all()
        self.reload_data()

        if dlg.success_count > 0:
            msg = f"{dlg.success_count} 件のシナリオを書架に追加しました。"
            if dlg.fail_count > 0:
                msg += f"\n({dlg.fail_count} 件の取り込みに失敗)"
            QMessageBox.information(self, "取り込み完了", msg)
        elif dlg.fail_count > 0:
            QMessageBox.warning(self, "取り込み失敗", f"{dlg.fail_count} 件の取り込みに失敗しました。")

    def _init_window_geometry(self):
        """settings.ini からウィンドウ位置・サイズ・最大化状態を読み出して適用"""
        self.setMinimumSize(900, 600)

        geom = app_settings.get_window_geometry()
        w = geom.get("width")
        h = geom.get("height")
        is_max = geom.get("maximized", False)
        x = geom.get("x")
        y = geom.get("y")

        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRect(0, 0, 1920, 1080)

        if w and h:
            # INI に保存されたサイズを忠実に適用（最小サイズ900x600を保証）
            applied_w = max(900, int(w))
            applied_h = max(600, int(h))
            self.resize(applied_w, applied_h)

            has_valid_pos = False
            if x is not None and y is not None:
                rect = QRect(x, y, applied_w, applied_h)
                for s in QApplication.screens():
                    if s.geometry().intersects(rect):
                        has_valid_pos = True
                        break

            if has_valid_pos:
                self.move(x, y)
            else:
                self.move(
                    avail.x() + max(0, (avail.width() - applied_w) // 2),
                    avail.y() + max(0, (avail.height() - applied_h) // 2),
                )

            if is_max:
                self.showMaximized()
        else:
            # 初回起動時: 画面解像度に応じた最適な初期サイズ（画面の88%〜最大1260x820）
            init_w = min(1260, max(900, int(avail.width() * 0.88)))
            init_h = min(820, max(600, int(avail.height() * 0.85)))
            self.resize(init_w, init_h)
            self.move(
                avail.x() + max(0, (avail.width() - init_w) // 2),
                avail.y() + max(0, (avail.height() - init_h) // 2),
            )
            # 初回サイズを settings.ini に保存
            self._save_geometry_to_ini()

    def _save_geometry_to_ini(self):
        """現在のウィンドウサイズ・位置・最大化状態を settings.ini に保存"""
        is_max = self.isMaximized()
        if is_max:
            geom = app_settings.get_window_geometry()
            norm = self.normalGeometry()
            norm_w = norm.width() if norm.isValid() and norm.width() >= 900 else (geom.get("width") or 1260)
            norm_h = norm.height() if norm.isValid() and norm.height() >= 600 else (geom.get("height") or 820)
            norm_x = norm.x() if norm.isValid() else geom.get("x")
            norm_y = norm.y() if norm.isValid() else geom.get("y")
            app_settings.save_window_geometry(
                width=norm_w,
                height=norm_h,
                maximized=True,
                x=norm_x,
                y=norm_y,
            )
        else:
            w = max(900, self.width())
            h = max(600, self.height())
            pos = self.pos()
            app_settings.save_window_geometry(
                width=w,
                height=h,
                maximized=False,
                x=pos.x(),
                y=pos.y(),
            )

    def _get_resize_edge(self, pos):
        """ウィンドウ四辺・四隅の判定とリサイズ用カーソルの取得"""
        if self.isMaximized():
            return None, Qt.ArrowCursor

        margin = 8
        w = self.width()
        h = self.height()
        x = pos.x()
        y = pos.y()

        on_left = x < margin
        on_right = x > w - margin
        on_top = y < margin
        on_bottom = y > h - margin

        edges = None
        cursor = Qt.ArrowCursor

        if on_top and on_left:
            edges = Qt.TopEdge | Qt.LeftEdge
            cursor = Qt.SizeFDiagCursor
        elif on_top and on_right:
            edges = Qt.TopEdge | Qt.RightEdge
            cursor = Qt.SizeBDiagCursor
        elif on_bottom and on_left:
            edges = Qt.BottomEdge | Qt.LeftEdge
            cursor = Qt.SizeBDiagCursor
        elif on_bottom and on_right:
            edges = Qt.BottomEdge | Qt.RightEdge
            cursor = Qt.SizeFDiagCursor
        elif on_left:
            edges = Qt.LeftEdge
            cursor = Qt.SizeHorCursor
        elif on_right:
            edges = Qt.RightEdge
            cursor = Qt.SizeHorCursor
        elif on_top:
            edges = Qt.TopEdge
            cursor = Qt.SizeVerCursor
        elif on_bottom:
            edges = Qt.BottomEdge
            cursor = Qt.SizeVerCursor

        return edges, cursor

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        edges, cursor = self._get_resize_edge(pos)
        self.setCursor(cursor)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            edges, _ = self._get_resize_edge(pos)
            if edges is not None:
                handle = self.windowHandle()
                if handle and hasattr(handle, "startSystemResize"):
                    handle.startSystemResize(edges)
                    event.accept()
                    return
            if hasattr(self, "bookshelf") and self.bookshelf.selected_item_id is not None:
                self.bookshelf.clear_selection()
                self._on_selection_cleared()
        super().mousePressEvent(event)

    def eventFilter(self, watched, event):
        if watched == getattr(self, "root_frame", None):
            ev_type = event.type()
            if ev_type == QEvent.MouseMove:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                edges, cursor = self._get_resize_edge(pos)
                self.setCursor(cursor)
            elif ev_type == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                edges, _ = self._get_resize_edge(pos)
                if edges is not None:
                    handle = self.windowHandle()
                    if handle and hasattr(handle, "startSystemResize"):
                        handle.startSystemResize(edges)
                        return True
                child = self.root_frame.childAt(pos)
                curr = child
                in_bookshelf = False
                while curr:
                    if curr == getattr(self, "bookshelf", None):
                        in_bookshelf = True
                        break
                    curr = curr.parentWidget()
                if not in_bookshelf and hasattr(self, "bookshelf") and self.bookshelf.selected_item_id is not None:
                    self.bookshelf.clear_selection()
                    self._on_selection_cleared()
        return super().eventFilter(watched, event)

    def nativeEvent(self, eventType, message):
        """Windows環境での滑らかなOSネイティブ・リサイズ処理（WM_NCHITTEST）"""
        if sys.platform == "win32" and eventType == b"windows_generic_MSG":
            import ctypes
            from ctypes import wintypes

            msg = wintypes.MSG.from_address(message.__int__())
            WM_NCHITTEST = 0x0084
            if msg.message == WM_NCHITTEST:
                if self.isMaximized():
                    return False, 0

                # 画面上の絶対カーソル座標
                x = msg.lParam & 0xFFFF
                y = (msg.lParam >> 16) & 0xFFFF
                if x >= 0x8000:
                    x -= 0x10000
                if y >= 0x8000:
                    y -= 0x10000

                rect = self.frameGeometry()
                margin = 8  # リサイズ検知マージン (px)

                on_left = (rect.left() <= x < rect.left() + margin)
                on_right = (rect.right() - margin < x <= rect.right())
                on_top = (rect.top() <= y < rect.top() + margin)
                on_bottom = (rect.bottom() - margin < y <= rect.bottom())

                HTLEFT = 10
                HTRIGHT = 11
                HTTOP = 12
                HTTOPLEFT = 13
                HTTOPRIGHT = 14
                HTBOTTOM = 15
                HTBOTTOMLEFT = 16
                HTBOTTOMRIGHT = 17

                if on_top and on_left:
                    return True, HTTOPLEFT
                if on_top and on_right:
                    return True, HTTOPRIGHT
                if on_bottom and on_left:
                    return True, HTBOTTOMLEFT
                if on_bottom and on_right:
                    return True, HTBOTTOMRIGHT
                if on_left:
                    return True, HTLEFT
                if on_right:
                    return True, HTRIGHT
                if on_top:
                    return True, HTTOP
                if on_bottom:
                    return True, HTBOTTOM

        return super().nativeEvent(eventType, message)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "bookshelf") and hasattr(self.bookshelf, "_relayout_cards"):
            QTimer.singleShot(0, self.bookshelf._relayout_cards)
            QTimer.singleShot(60, self.bookshelf._relayout_cards)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_save_geom_timer") and not self.isMaximized():
            self._save_geom_timer.start(400)

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "_save_geom_timer") and not self.isMaximized():
            self._save_geom_timer.start(400)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            if hasattr(self, "_save_geom_timer"):
                self._save_geom_timer.start(200)
            if hasattr(self, "title_bar") and hasattr(self.title_bar, "max_btn"):
                self.title_bar.max_btn.setText("❐" if self.isMaximized() else "□")
        super().changeEvent(event)

    def closeEvent(self, event):
        """終了時に settings.ini へウィンドウ位置・サイズと最大化状態を確実に保存"""
        if getattr(self.bookshelf, "cover_loader", None):
            self.bookshelf.cover_loader.cancel_all()
        self._auto_sync_timer.stop()
        self._auto_sync_kickoff.stop()
        # 同調中に閉じた場合は、今送っている1件が終わったところで止める
        if self._notion_worker is not None and self._notion_worker.isRunning():
            self._notion_worker.requestInterruption()
            self._notion_worker.wait(15000)
        if hasattr(self, "_save_geom_timer") and self._save_geom_timer.isActive():
            self._save_geom_timer.stop()
        try:
            self._save_geometry_to_ini()
        except Exception:
            pass

        # 既存QSettings互換
        try:
            settings = QSettings("GrimoireShelf", "CoverExtractor")
            settings.setValue("main_window_geometry", self.saveGeometry())
            settings.setValue("main_window_maximized", self.isMaximized())
        except Exception:
            pass

        super().closeEvent(event)
