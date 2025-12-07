"""
==============================================================================
Script Name: voice_extractor_gui.py
Purpose    : ボイスデータの検索・再生・設定管理・一括抽出 (GUI)
Author     : Gemini (Assisted by User)
Description:
    SQLiteデータベース (`scenario_data.db`) を読み込み、シナリオデータの閲覧と
    ボイスデータセット作成支援を行います。
    
    【V2 アップデート】
    学習設定用の `voice_settings` テーブルと連携し、各ボイスに対して
    「学習除外(Exclude)」フラグと「スタイル(Style)」を設定・保存できるようになりました。
    エクスポート時には除外フラグがONのデータは自動的にスキップされます。

    【V3 アップデート】
    表(Treeview)上での直接編集に対応しました。
    - Exclude列: ダブルクリックでトグル切り替え
    - Style列: ダブルクリックで入力ボックス表示

    【V4 アップデート】
    検索フィルタ機能の強化。
    - "Hide Rows without Voice" チェックボックスを追加。
      ボイスIDがない（ナレーション等の）行を一覧から隠せるようになりました。
      
    【V5 アップデート】
    UIDによるフィルタリング機能を追加。
    - 検索フィルタに "UID" 項目を追加し、特定UIDの部分一致検索が可能になりました。

Key Features:
    1. **Data Browsing & Filtering**:
        - 複合条件検索に加え、設定済みの Style や Exclude 状態も確認可能。
    2. **Voice Settings Management**:
        - 選択した行に対し「学習から除外」「スタイル」を設定し、DBへ保存(UPSERT)。
        - **表上でのインライン編集（ダブルクリック）に対応。**
    3. **Batch Export with Exclusion**:
        - フィルタリング結果からボイスを一括コピー。
        - **重要**: `Exclude=True` のデータは出力から除外されます。
    4. **Dataset Creation (Style-Bert-VITS2)**:
        - `esd.list` ファイルを自動生成。
        - 高度な日本語テキストクリーニング処理を搭載。

Dependencies:
    - tkinter, sqlite3, pygame, shutil

Usage:
    1. `python voice_extractor_gui.py` を実行。
    2. 上部のフィルタエリアでUIDやキャラ名などで検索。
    3. リストから行を選択し、下部の "Voice Settings" エリアで設定を変更 -> "Update" で保存。
    4. **または、リストのExclude/Style列をダブルクリックして直接編集。**
    5. "Export..." でデータセット出力（除外設定が反映されます）。
==============================================================================
"""

import os
import shutil
import sqlite3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pygame
import re

# ================= 設定 =================
DB_PATH = 'scenario_data.db'
DEFAULT_VOICE_EXTENSIONS = ['.ogg', '.wav', '.mp3']

# 日本語文字の Unicode レンジ (クリーニング処理用)
_JP_RANGE = r"\u3040-\u30FF\u4E00-\u9FFF\uFF66-\uFF9F"
# ========================================

class VoiceExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Scenario Voice Extractor V5")
        self.root.geometry("1400x950") # 幅と高さを拡張

        # 音声再生の初期化
        pygame.mixer.init()
        self.current_playing_file = None

        # 設定値（ディレクトリパス）
        self.voice_source_dir = tk.StringVar(value="./voice_assets")
        self.export_dest_dir = tk.StringVar(value="./exported_voices")
        
        # Style-Bert-VITS2 Export Options
        self.export_lang_id = tk.StringVar(value="JP")
        self.export_speaker_name = tk.StringVar() 

        # 個別設定用変数（選択行の編集用）
        self.selected_uid = tk.StringVar()
        self.setting_exclude = tk.BooleanVar()
        self.setting_style = tk.StringVar()

        # ★ページング用の状態
        self.all_rows = []              # フィルタ結果を全件保持
        self.current_page = 0           # 0-based
        self.page_size = tk.IntVar(value=500)  # 1ページの行数（コンボボックスで変更）

        # DB接続
        self.conn = None
        self.cursor = None
        if os.path.exists(DB_PATH):
            self.connect_db()
            self.ensure_settings_table() # GUI起動時にもテーブル存在確認
        else:
            messagebox.showwarning("Warning", f"Database not found: {DB_PATH}\nPlease run import script first.")

        self.create_widgets()
        self.load_initial_data()

    def connect_db(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

    def ensure_settings_table(self):
        """voice_settingsテーブルがない場合に作成する（安全策）"""
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS voice_settings (
            uid TEXT PRIMARY KEY,
            exclude_learning INTEGER DEFAULT 0,
            style TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        self.conn.commit()

    def __del__(self):
        if self.conn:
            self.conn.close()

    def create_widgets(self):
        # --- 上部: フィルタリングエリア ---
        filter_frame = ttk.LabelFrame(self.root, text="Search Filters", padding=10)
        filter_frame.pack(fill="x", padx=10, pady=5)

        # フィルタ用変数
        self.filter_act = tk.StringVar()
        self.filter_chapter = tk.StringVar()
        self.filter_adv = tk.StringVar()
        self.filter_actor = tk.StringVar()
        
        # ★追加: UIDフィルタ
        self.filter_uid = tk.StringVar()
        
        self.filter_text = tk.StringVar()
        self.filter_style = tk.StringVar() 
        self.filter_style_empty_only = tk.BooleanVar(value=False)
        self.filter_hide_no_voice = tk.BooleanVar(value=False)
        

        # グリッド配置 (Row 0)
        ttk.Label(filter_frame, text="Act:").grid(row=0, column=0, padx=5, sticky="e")
        ttk.Entry(filter_frame, textvariable=self.filter_act, width=8).grid(row=0, column=1, padx=5)

        ttk.Label(filter_frame, text="Chapter:").grid(row=0, column=2, padx=5, sticky="e")
        ttk.Entry(filter_frame, textvariable=self.filter_chapter, width=8).grid(row=0, column=3, padx=5)

        ttk.Label(filter_frame, text="Adv/Bad:").grid(row=0, column=4, padx=5, sticky="e")
        ttk.Entry(filter_frame, textvariable=self.filter_adv, width=12).grid(row=0, column=5, padx=5)

        ttk.Label(filter_frame, text="Actor:").grid(row=0, column=6, padx=5, sticky="e")
        ttk.Entry(filter_frame, textvariable=self.filter_actor, width=12).grid(row=0, column=7, padx=5)

        # (Row 1)
        # ★UID入力欄 (新規追加)
        ttk.Label(filter_frame, text="UID:").grid(row=1, column=0, padx=5, sticky="e")
        ttk.Entry(filter_frame, textvariable=self.filter_uid, width=15).grid(row=1, column=1, columnspan=2, padx=5, sticky="w")

        # Style入力欄 & Emptyチェックボックス (位置調整: Column 2以降へ)
        style_frame = ttk.Frame(filter_frame) 
        style_frame.grid(row=1, column=2, columnspan=2, sticky="w", padx=(20,0)) # UIDとの間隔を開ける
        
        ttk.Label(style_frame, text="Style:").pack(side="left", padx=(5, 2))
        ttk.Entry(style_frame, textvariable=self.filter_style, width=10).pack(side="left")
        ttk.Checkbutton(style_frame, text="Empty Only", variable=self.filter_style_empty_only).pack(side="left", padx=(5, 0))

        # Text入力欄
        ttk.Label(filter_frame, text="Text:").grid(row=1, column=4, padx=5, sticky="e")
        ttk.Entry(filter_frame, textvariable=self.filter_text, width=25).grid(row=1, column=5, columnspan=2, padx=5, sticky="w")
        
        # ボイスなし除外チェックボックス
        ttk.Checkbutton(filter_frame, text="Hide No-Voice", variable=self.filter_hide_no_voice).grid(row=1, column=7, padx=5, sticky="w")

        # 検索ボタン & リセット
        btn_frame = ttk.Frame(filter_frame)
        btn_frame.grid(row=0, column=8, rowspan=2, padx=10, sticky="ns")
        ttk.Button(btn_frame, text="Search", command=self.apply_filters).pack(fill="x", pady=2)
        ttk.Button(btn_frame, text="Reset", command=self.reset_filters).pack(fill="x", pady=2)

        # ★ ここからページング用コントロール (変更なし) ★
        page_frame = ttk.Frame(self.root)
        page_frame.pack(fill="x", padx=10, pady=(0, 5))

        self.prev_page_btn = ttk.Button(page_frame, text="◀ Prev", width=8, command=self.goto_prev_page)
        self.prev_page_btn.pack(side="left")

        self.next_page_btn = ttk.Button(page_frame, text="Next ▶", width=8, command=self.goto_next_page)
        self.next_page_btn.pack(side="left", padx=(5, 0))

        ttk.Label(page_frame, text="Rows/Page:").pack(side="left", padx=(20, 2))
        page_size_cb = ttk.Combobox(
            page_frame,
            textvariable=self.page_size,
            values=[200, 500, 1000, 2000],
            width=6,
            state="readonly"
        )
        page_size_cb.pack(side="left")
        page_size_cb.bind("<<ComboboxSelected>>", self.on_page_size_changed)

        self.page_info_label = ttk.Label(page_frame, text="Page 0/0")
        self.page_info_label.pack(side="right")
        # ★ ページングUIここまで ★

        # --- 中央: データ表示エリア (Treeview) ---
        tree_frame = ttk.Frame(self.root)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Scrollbar
        tree_scroll_y = ttk.Scrollbar(tree_frame)
        tree_scroll_y.pack(side="right", fill="y")
        tree_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal")
        tree_scroll_x.pack(side="bottom", fill="x")

        # カラム定義
        columns = ("id", "uid", "act", "chapter", "adv", "actor", "exclude", "style", "voice", "text")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", 
                                 yscrollcommand=tree_scroll_y.set, xscrollcommand=tree_scroll_x.set)
        
        # ヘッダー設定
        self.tree.heading("id", text="ID")
        self.tree.heading("uid", text="UID")
        self.tree.heading("act", text="Act")
        self.tree.heading("chapter", text="Ch")
        self.tree.heading("adv", text="Adv")
        self.tree.heading("actor", text="Actor")
        self.tree.heading("exclude", text="Excl") 
        self.tree.heading("style", text="Style")
        self.tree.heading("voice", text="Voice File")
        self.tree.heading("text", text="Text")

        # カラム幅設定
        self.tree.column("id", width=40, stretch=False)
        self.tree.column("uid", width=120)
        self.tree.column("act", width=40, stretch=False)
        self.tree.column("chapter", width=40, stretch=False)
        self.tree.column("adv", width=60, stretch=False)
        self.tree.column("actor", width=80)
        self.tree.column("exclude", width=80, stretch=False, anchor="center") 
        self.tree.column("style", width=100, anchor="center")                  
        self.tree.column("voice", width=140)
        self.tree.column("text", width=350)

        self.tree.pack(fill="both", expand=True)
        
        tree_scroll_y.config(command=self.tree.yview)
        tree_scroll_x.config(command=self.tree.xview)

        # イベントバインド
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)


        # --- 下部: 設定編集 & エクスポート ---
        bottom_frame = ttk.Frame(self.root, padding=5)
        bottom_frame.pack(fill="x", side="bottom")

        # 1. 個別設定エリア (左側)
        settings_frame = ttk.LabelFrame(bottom_frame, text="Selected Voice Settings (Detail)", padding=10)
        settings_frame.pack(side="left", fill="both", expand=True, padx=5, pady=5)

        # UID表示
        ttk.Label(settings_frame, text="UID:").grid(row=0, column=0, sticky="e")
        ttk.Label(settings_frame, textvariable=self.selected_uid, foreground="blue").grid(row=0, column=1, sticky="w", padx=5)

        # 設定項目
        ttk.Checkbutton(settings_frame, text="Exclude from Learning", variable=self.setting_exclude).grid(row=1, column=0, columnspan=2, sticky="w", pady=5)
        
        ttk.Label(settings_frame, text="Style:").grid(row=2, column=0, sticky="e")
        ttk.Entry(settings_frame, textvariable=self.setting_style, width=20).grid(row=2, column=1, sticky="w", padx=5)

        # 更新ボタン
        ttk.Button(settings_frame, text="Update DB", command=self.save_current_settings).grid(row=3, column=0, columnspan=2, pady=10, sticky="ew")


        # 2. 共通設定 & コントロールエリア (右側)
        control_frame = ttk.LabelFrame(bottom_frame, text="Global Control & Export", padding=10)
        control_frame.pack(side="right", fill="both", expand=True, padx=5, pady=5)

        # フォルダ選択
        path_frame = ttk.Frame(control_frame)
        path_frame.pack(fill="x", pady=2)
        ttk.Label(path_frame, text="Assets Dir:").pack(side="left")
        ttk.Entry(path_frame, textvariable=self.voice_source_dir, width=30).pack(side="left", padx=5)
        ttk.Button(path_frame, text="...", width=3, command=self.browse_source_dir).pack(side="left")

        path_frame2 = ttk.Frame(control_frame)
        path_frame2.pack(fill="x", pady=2)
        ttk.Label(path_frame2, text="Export To:").pack(side="left")
        ttk.Entry(path_frame2, textvariable=self.export_dest_dir, width=30).pack(side="left", padx=5)
        ttk.Button(path_frame2, text="...", width=3, command=self.browse_dest_dir).pack(side="left")

        # 再生 & ステータス
        action_frame = ttk.Frame(control_frame)
        action_frame.pack(fill="x", pady=5)
        ttk.Button(action_frame, text="▶ Play", command=self.play_selected_voice).pack(side="left", padx=2)
        ttk.Button(action_frame, text="■ Stop", command=self.stop_voice).pack(side="left", padx=2)
        self.status_label = ttk.Label(action_frame, text="Ready", foreground="gray")
        self.status_label.pack(side="left", padx=10)

        # Dataset Options
        sbv2_frame = ttk.Frame(control_frame)
        sbv2_frame.pack(fill="x", pady=5)
        ttk.Label(sbv2_frame, text="Lang:").pack(side="left")
        ttk.Combobox(sbv2_frame, textvariable=self.export_lang_id, values=["JP", "EN", "ZH"], width=4, state="readonly").pack(side="left", padx=2)
        ttk.Label(sbv2_frame, text="Speaker Override:").pack(side="left", padx=(10, 2))
        ttk.Entry(sbv2_frame, textvariable=self.export_speaker_name, width=15).pack(side="left")

        # Export Button
        ttk.Button(control_frame, text="Export Filtered Voices (Skip Excluded)", command=self.export_filtered_voices).pack(fill="x", pady=5)    # --- ロジック ---

    def load_initial_data(self):
        if self.cursor:
            self.apply_filters()

    def reset_filters(self):
        self.filter_act.set("")
        self.filter_chapter.set("")
        self.filter_adv.set("")
        self.filter_actor.set("")
        self.filter_uid.set("") # ★追加
        self.filter_text.set("")
        self.filter_style.set("")
        self.filter_style_empty_only.set(False)
        self.filter_hide_no_voice.set(False)
        self.apply_filters()

    def build_filter_query(self):
        """
        現在のフィルタ UI の内容から SQL とパラメータを組み立てて返すヘルパー。
        フィルタ表示とエクスポートで共用する。
        """
        if not self.cursor:
            return None, None

        query = """
            SELECT t.*, s.exclude_learning, s.style 
            FROM scenario_text t
            LEFT JOIN voice_settings s ON t.uid = s.uid
            WHERE 1=1
        """
        params = []

        # ★追加: UIDフィルタ (部分一致検索)
        if self.filter_uid.get():
            query += " AND t.uid LIKE ?"
            params.append(f"%{self.filter_uid.get()}%")

        if self.filter_act.get():
            query += " AND t.act = ?"
            params.append(self.filter_act.get())
        
        if self.filter_chapter.get():
            query += " AND t.chapter = ?"
            params.append(self.filter_chapter.get())

        if self.filter_adv.get():
            query += " AND t.adv LIKE ?"
            params.append(f"%{self.filter_adv.get()}%")

        if self.filter_actor.get():
            query += " AND t.actor LIKE ?"
            params.append(f"%{self.filter_actor.get()}%")

        if self.filter_text.get():
            query += " AND t.text LIKE ?"
            params.append(f"%{self.filter_text.get()}%")

        # Styleフィルタ (Empty Only優先)
        if self.filter_style_empty_only.get():
            # NULL (設定なし) または 空文字 (削除済み) を検索
            query += " AND (s.style IS NULL OR s.style = '')"
        elif self.filter_style.get():
            # チェックがない場合はテキスト検索
            query += " AND s.style LIKE ?"
            params.append(f"%{self.filter_style.get()}%")
        
        if self.filter_hide_no_voice.get():
            query += " AND t.voice_file_name IS NOT NULL AND t.voice_file_name != ''"

        query += " ORDER BY t.act, t.chapter, t.adv, t.id"

        return query, params

    def apply_filters(self):
        if not self.cursor:
            return

        query, params = self.build_filter_query()
        if query is None:
            return

        self.cursor.execute(query, params)
        rows = self.cursor.fetchall()

        # 全件保持してから、現在ページだけ Treeview に反映
        self.all_rows = rows
        self.current_page = 0
        self.refresh_tree_page()

        self.status_label.config(text=f"Found {len(rows)} records.")

    def update_tree(self, rows):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for row in rows:
            voice = row['voice_file_name'] if row['voice_file_name'] else ""
            
            # 設定情報の取得 (NULLの場合はデフォルト値)
            excl = "Yes" if row['exclude_learning'] == 1 else "-"
            style = row['style'] if row['style'] else ""

            self.tree.insert("", "end", values=(
                row['id'],
                row['uid'],
                row['act'],
                row['chapter'],
                row['adv'],
                row['actor'],
                excl,
                style,
                voice,
                row['text']
            ))

    def refresh_tree_page(self):
        """self.all_rows と self.current_page / self.page_size から、
        現在ページの内容だけを Treeview に描画する。
        """
        # Treeview を一旦クリア
        for item in self.tree.get_children():
            self.tree.delete(item)

        if not self.all_rows:
            self.page_info_label.config(text="Page 0/0 (Total 0)")
            self.prev_page_btn.config(state="disabled")
            self.next_page_btn.config(state="disabled")
            return

        page_size = max(1, int(self.page_size.get()))
        total = len(self.all_rows)
        total_pages = (total + page_size - 1) // page_size

        # current_page が範囲外になっていないか保護
        if self.current_page >= total_pages:
            self.current_page = total_pages - 1
        if self.current_page < 0:
            self.current_page = 0

        start = self.current_page * page_size
        end = start + page_size
        page_rows = self.all_rows[start:end]

        # 既存の update_tree ロジックを流用して描画
        self.update_tree(page_rows)

        self.page_info_label.config(
            text=f"Page {self.current_page + 1}/{total_pages} (Total {total})"
        )
        self.prev_page_btn.config(state="normal" if self.current_page > 0 else "disabled")
        self.next_page_btn.config(state="normal" if self.current_page < total_pages - 1 else "disabled")

    def on_page_size_changed(self, event=None):
        """Rows/Page のコンボボックス変更時に現在ページをリセットして再描画"""
        self.current_page = 0
        self.refresh_tree_page()

    def goto_prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.refresh_tree_page()

    def goto_next_page(self):
        page_size = max(1, int(self.page_size.get()))
        total = len(self.all_rows)
        total_pages = (total + page_size - 1) // page_size

        if self.current_page < total_pages - 1:
            self.current_page += 1
            self.refresh_tree_page()

    def on_tree_select(self, event):
        """リスト選択時に設定エリアに値を反映"""
        selected_items = self.tree.selection()
        if not selected_items:
            return

        item = self.tree.item(selected_items[0])
        vals = item['values']
        
        # vals: id, uid, act, chap, adv, actor, exclude, style, voice, text
        uid = vals[1]
        exclude_disp = vals[6]
        style = vals[7]

        self.selected_uid.set(uid)
        self.setting_exclude.set(True if exclude_disp == "Yes" else False)
        self.setting_style.set(style)

    def on_double_click(self, event):
        """ダブルクリック時の挙動: カラムによって編集または再生"""
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        column_id = self.tree.identify_column(event.x) # Returns '#1', '#2', ...
        row_id = self.tree.identify_row(event.y)
        
        if not row_id:
            return

        # カラムインデックスの特定 (1-based string -> 0-based integer index)
        # columns = ("id", "uid", "act", "chapter", "adv", "actor", "exclude", "style", "voice", "text")
        # index:      0      1      2        3       4       5         6        7        8       9
        # col_id:    #1     #2     #3       #4      #5      #6        #7       #8       #9      #10
        
        col_num = int(column_id.replace('#', '')) - 1
        
        # 行の値を取得
        item = self.tree.item(row_id)
        values = item['values']
        uid = values[1]

        # 分岐処理
        if col_num == 6: # Exclude Column
            self.toggle_exclude_cell(row_id, uid, values)
        elif col_num == 7: # Style Column
            self.edit_style_cell(row_id, column_id, uid, values[7])
        else:
            # それ以外のカラムは再生
            self.play_selected_voice()

    def toggle_exclude_cell(self, row_id, uid, current_values):
        """Excludeフラグをトグルする"""
        current_disp = current_values[6]
        new_val = 1 if current_disp != "Yes" else 0
        new_disp = "Yes" if new_val == 1 else "-"
        
        try:
            # 既存のStyleを取得して維持
            current_style = current_values[7]

            self.cursor.execute('''
                INSERT OR REPLACE INTO voice_settings (uid, exclude_learning, style)
                VALUES (?, ?, ?)
            ''', (uid, new_val, current_style))
            self.conn.commit()

            # Treeview更新
            new_values = list(current_values)
            new_values[6] = new_disp
            self.tree.item(row_id, values=new_values)
            
            # 下部の表示も同期
            if self.selected_uid.get() == uid:
                self.setting_exclude.set(True if new_val == 1 else False)

            self.status_label.config(text=f"Updated Exclude: {uid} -> {new_disp}")
            
        except sqlite3.Error as e:
            messagebox.showerror("DB Error", str(e))

    def edit_style_cell(self, row_id, col_id, uid, current_style):
        """StyleセルにEntryを表示してインライン編集させる"""
        x, y, w, h = self.tree.bbox(row_id, col_id)
        
        # セルの位置にEntryを配置
        entry = ttk.Entry(self.tree, width=w)
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, current_style)
        entry.focus()

        def save_edit(event=None):
            new_style = entry.get().strip()
            entry.destroy()
            
            try:
                # Excludeの値を取得して維持
                item = self.tree.item(row_id)
                current_exclude_disp = item['values'][6]
                exclude_val = 1 if current_exclude_disp == "Yes" else 0

                self.cursor.execute('''
                    INSERT OR REPLACE INTO voice_settings (uid, exclude_learning, style)
                    VALUES (?, ?, ?)
                ''', (uid, exclude_val, new_style))
                self.conn.commit()

                # Treeview更新
                new_values = list(item['values'])
                new_values[7] = new_style
                self.tree.item(row_id, values=new_values)

                # 下部の表示も同期
                if self.selected_uid.get() == uid:
                    self.setting_style.set(new_style)

                self.status_label.config(text=f"Updated Style: {uid} -> {new_style}")

            except sqlite3.Error as e:
                messagebox.showerror("DB Error", str(e))

        def cancel_edit(event=None):
            entry.destroy()

        # Enterまたはフォーカスアウトで保存
        entry.bind("<Return>", save_edit)
        entry.bind("<FocusOut>", save_edit) 
        entry.bind("<Escape>", cancel_edit)

    def save_current_settings(self):
        """(下部パネル用) 設定をDBに保存し、リストを更新"""
        uid = self.selected_uid.get()
        if not uid:
            return

        exclude_val = 1 if self.setting_exclude.get() else 0
        style_val = self.setting_style.get().strip()

        try:
            # UPSERT (UIDはPKなので重複時はUPDATE)
            self.cursor.execute('''
                INSERT OR REPLACE INTO voice_settings (uid, exclude_learning, style)
                VALUES (?, ?, ?)
            ''', (uid, exclude_val, style_val))
            self.conn.commit()
            
            # 選択行の見た目だけ更新
            selected = self.tree.selection()
            if selected:
                current_vals = list(self.tree.item(selected[0], 'values'))
                current_vals[6] = "Yes" if exclude_val == 1 else "-"
                current_vals[7] = style_val
                self.tree.item(selected[0], values=current_vals)

            self.status_label.config(text=f"Saved settings for {uid}")

        except sqlite3.Error as e:
            messagebox.showerror("DB Error", str(e))

    # --- ディレクトリ選択 ---
    def browse_source_dir(self):
        d = filedialog.askdirectory(initialdir=self.voice_source_dir.get())
        if d: self.voice_source_dir.set(d)

    def browse_dest_dir(self):
        d = filedialog.askdirectory(initialdir=self.export_dest_dir.get())
        if d: self.export_dest_dir.set(d)

    # --- 音声再生 ---
    def find_voice_path(self, voice_name):
        if not voice_name: return None
        base_dir = self.voice_source_dir.get()
        if not os.path.exists(base_dir): return None

        for ext in DEFAULT_VOICE_EXTENSIONS:
            path = os.path.join(base_dir, voice_name + ext)
            if os.path.exists(path): return path
        return None

    def play_selected_voice(self):
        selected = self.tree.selection()
        if not selected: return

        item = self.tree.item(selected[0])
        voice_name = item['values'][8] # Voice column

        if not voice_name:
            self.status_label.config(text="No voice file.")
            return

        file_path = self.find_voice_path(voice_name)
        if file_path:
            try:
                pygame.mixer.music.load(file_path)
                pygame.mixer.music.play()
                self.status_label.config(text=f"Playing: {os.path.basename(file_path)}")
            except Exception as e:
                messagebox.showerror("Playback Error", str(e))
        else:
            self.status_label.config(text="File not found.")

    def stop_voice(self):
        pygame.mixer.music.stop()
        self.status_label.config(text="Stopped.")

    # --- エクスポート処理 ---
    def replace_dots_contextual(self, text: str) -> str:
        t = text
        pattern_middle = rf"([{_JP_RANGE}])…+([{_JP_RANGE}])"
        t = re.sub(pattern_middle, r"\1、\2", t)
        t = re.sub(r"…+$", "。", t)
        t = re.sub(r"(、|。|！|？)…+", r"\1", t)
        t = re.sub(r"…+(、|。|！|？)", r"\1", t)
        t = re.sub(r"…+", "", t)
        return t

    def clean_text_for_dataset(self, text):
        if not text: return ""
        t = re.sub(r'<[^>]+>', '', text)
        t = t.replace('\n', '').replace('\r', '')
        t = t.strip()
        t = t.translate(str.maketrans({"【": "", "】": ""}))
        t = self.replace_dots_contextual(t)
        t = re.sub(r"―+", "", t)
        t = re.sub(r"ー{2,}", "ー", t)
        t = t.replace("\u3000", "")
        t = re.sub(r"\s+", " ", t)
        jp = _JP_RANGE
        pattern = re.compile(rf"([{jp}]) ([{jp}])")
        while True:
            new_t = pattern.sub(r"\1\2", t)
            if new_t == t: break
            t = new_t
        def _shrink(m): return m.group(0)[-1]
        t = re.sub(r"[!?！？]{2,}", _shrink, t)
        return t.strip()

    def export_filtered_voices(self):
        if not self.cursor:
            messagebox.showerror("Error", "Database is not connected.")
            return

        query, params = self.build_filter_query()
        if query is None:
            return

        # ページングに関係なく、フィルタに合致する全行を取得
        self.cursor.execute(query, params)
        rows = self.cursor.fetchall()

        if not rows:
            messagebox.showinfo("Info", "No data to export.")
            return

        dest_dir = self.export_dest_dir.get()
        if not os.path.exists(dest_dir):
            try:
                os.makedirs(dest_dir)
            except Exception as e:
                messagebox.showerror("Error", f"Could not create dir:\n{e}")
                return

        count_success = 0
        count_excluded = 0
        count_missing = 0
        count_skip = 0 
        
        esd_lines = []
        target_lang = self.export_lang_id.get()
        override_speaker = self.export_speaker_name.get()

        total = len(rows)
        
        for row in rows:
            # row から値を取得
            voice_name = row['voice_file_name'] if row['voice_file_name'] else ""
            raw_text = row['text'] if row['text'] else ""
            actor = row['actor'] if row['actor'] else ""

            # 除外フラグ（NULL の場合は 0 扱い）
            exclude_learning = row['exclude_learning'] if row['exclude_learning'] is not None else 0

            if exclude_learning == 1:
                count_excluded += 1
                continue

            if not voice_name:
                count_skip += 1
                continue

            src_path = self.find_voice_path(voice_name)
            if src_path:
                try:
                    ext = os.path.splitext(src_path)[1]
                    dst_filename = voice_name + ext
                    dst_path = os.path.join(dest_dir, dst_filename)
                    
                    shutil.copy2(src_path, dst_path)
                    count_success += 1
                    
                    clean_text = self.clean_text_for_dataset(raw_text)
                    speaker_name = override_speaker if override_speaker else actor
                    
                    # esd.list: filename|speaker|lang|text
                    line = f"{dst_filename}|{speaker_name}|{target_lang}|{clean_text}"
                    esd_lines.append(line)
                    
                except Exception as e:
                    print(f"Error: {e}")
            else:
                count_missing += 1

        esd_path = os.path.join(dest_dir, "esd.list")
        try:
            with open(esd_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(esd_lines))
        except Exception as e:
            messagebox.showerror("Error", f"Failed to write esd.list:\n{e}")

        messagebox.showinfo("Export Result", 
                            f"Export Completed!\n\n"
                            f"Total Rows: {total}\n"
                            f"Excluded: {count_excluded}\n"
                            f"Copied: {count_success}\n"
                            f"Missing: {count_missing}\n"
                            f"No Voice ID: {count_skip}\n\n"
                            f"List: {esd_path}")

def main():
    root = tk.Tk()
    app = VoiceExtractorApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()