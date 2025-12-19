import sys
import sqlite3
import uuid
import pandas as pd
from datetime import datetime
from enum import Enum
import re

try:
    from PySide6.QtWidgets import (QApplication, QMainWindow, QTableView, QVBoxLayout, 
                                   QHBoxLayout, QWidget, QHeaderView, QToolBar, QFileDialog, 
                                   QMessageBox, QAbstractItemView, QMenu, QSplitter,
                                   QLineEdit, QLabel, QFormLayout, QComboBox, QPlainTextEdit,
                                   QPushButton, QGroupBox, QSpacerItem, QSizePolicy, QDialog,
                                   QInputDialog, QTextEdit, QDialogButtonBox, QVBoxLayout)
    from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal, Slot, QTimer, QSize, QEvent, QRect
    from PySide6.QtGui import QAction, QColor, QKeySequence, QIcon, QFont, QTextCursor, QTextCharFormat
except ImportError:
    print("必要なライブラリが見つかりません。以下のコマンドでインストールしてください:")
    print("pip install PySide6 pandas")
    sys.exit(1)

# -----------------------------------------------------------------------------
# 定数・設定
# -----------------------------------------------------------------------------
class SceneType(str, Enum):
    LINEAR = "linear"
    BRANCH = "branch"
    TESTIMONY = "testimony"
    TERMINAL = "terminal"
    REACTION = "reaction"
    CHOICE_TEXT = "choice_text"

# カラム定義: Scene (scenario_text)
COLS_SCENE = [
    {'id': 'uid', 'label': 'Scene ID', 'readonly': True, 'width': 120},
    {'id': 'scene_type', 'label': 'Type', 'readonly': False, 'options': [e.value for e in SceneType], 'width': 80},
    {'id': 'next_scene_uid', 'label': 'Next Scene', 'readonly': False, 'width': 120},
    {'id': 'actor', 'label': 'Actor', 'readonly': False, 'width': 80},
    {'id': 'text', 'label': 'Text', 'readonly': False, 'width': 300},
]

# カラム定義: Choice (scenario_choice)
COLS_CHOICE = [
    {'id': 'choice_id', 'label': 'ID', 'readonly': True, 'width': 80},
    {'id': 'choice_text_uid', 'label': 'Choice Text UID', 'readonly': False, 'width': 200},
    {'id': 'choice_text', 'label': 'Choice Text', 'readonly': True, 'width': 240},
    {'id': 'axis', 'label': 'Axis', 'readonly': False, 'width': 100},
    {'id': 'next_scene_id', 'label': 'Next Scene', 'readonly': False, 'width': 120},
    {'id': 'next_scene_text', 'label': 'Next Text', 'readonly': True, 'width': 240},
    {'id': 'correct', 'label': 'Correct', 'readonly': False, 'width': 60}, # Added correct column
    {'id': 'disp_order', 'label': 'Order', 'readonly': False, 'width': 60},
]

# カラム定義: Click Spot (scenario_click_spot)
COLS_SPOT = [
    {'id': 'spot_id', 'label': 'ID', 'readonly': True, 'width': 80},
    {'id': 'target_text', 'label': 'Target Text', 'readonly': False, 'width': 200},
    {'id': 'next_scene_id', 'label': 'Next Scene', 'readonly': False, 'width': 120},
    {'id': 'next_scene_text', 'label': 'Next Text', 'readonly': True, 'width': 260},
    {'id': 'correct', 'label': 'Correct', 'readonly': False, 'width': 60}, # 0 or 1
    {'id': 'disp_order', 'label': 'Order', 'readonly': False, 'width': 60},
]

# -----------------------------------------------------------------------------
# 汎用 Pandas Table Model (Filter機能付き)
# -----------------------------------------------------------------------------
class PandasTableModel(QAbstractTableModel):
    dataChangedSignal = Signal()
    layoutChangedSignal = Signal()

    def __init__(self, columns_def, parent=None):
        super().__init__(parent)
        self.columns_def = columns_def
        self.col_ids = [c['id'] for c in columns_def]
        self.headers = [c['label'] for c in columns_def]
        self.df = pd.DataFrame(columns=self.col_ids)
        self._view_df = self.df.copy() # フィルタリング等の表示用
        
        # フィルタ保持用
        self.column_filters = {} # {col_id: text}

    def set_dataframe(self, df):
        self.beginResetModel()
        self.df = df.copy()
        # 不足カラムの補完
        for c in self.col_ids:
            if c not in self.df.columns:
                self.df[c] = ''
        self.reapply_filters() # ビューの再構築
        self.endResetModel()

    def get_dataframe(self):
        return self.df

    def set_column_filter(self, col_id, text):
        self.column_filters[col_id] = text
        self.apply_filters()

    def apply_filters(self):
        """フィルタを適用してViewを更新する"""
        self.beginResetModel()
        self.reapply_filters()
        self.endResetModel()
        self.layoutChangedSignal.emit()

    def reapply_filters(self):
        """df から _view_df を再生成するロジックのみ"""
        df = self.df.copy()
        
        # Column Filters (AND検索)
        for col_id, text in self.column_filters.items():
            if text:
                df = df[df[col_id].astype(str).str.contains(text, case=False, na=False)]
        
        self._view_df = df

    def rowCount(self, parent=QModelIndex()):
        return len(self._view_df)

    def columnCount(self, parent=QModelIndex()):
        return len(self.columns_def)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        row, col = index.row(), index.column()
        col_id = self.col_ids[col]
        
        if role == Qt.DisplayRole or role == Qt.EditRole:
            val = self._view_df.iloc[row][col_id]
            return str(val) if pd.notna(val) else ""

        if role == Qt.ToolTipRole:
            val = self._view_df.iloc[row][col_id]
            return str(val) if pd.notna(val) else ""
            
        if role == Qt.BackgroundRole:
            if self.columns_def[col].get('readonly'):
                return QColor(35, 35, 35)
            return QColor(45, 45, 45)

        if role == Qt.ForegroundRole:
            if self.columns_def[col].get('readonly'):
                return QColor(150, 150, 150)
            return QColor(230, 230, 230)
            
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return None

    def flags(self, index):
        if not index.isValid(): return Qt.NoItemFlags
        col_def = self.columns_def[index.column()]
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if not col_def.get('readonly'):
            flags |= Qt.ItemIsEditable
        return flags

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or role != Qt.EditRole: return False
        
        row = index.row()
        col = index.column()
        col_id = self.col_ids[col]
        
        # 表示用DFのindexから実体DFのindexを特定
        try:
            real_idx = self._view_df.index[row]
            self.df.at[real_idx, col_id] = value
            self._view_df.at[real_idx, col_id] = value
            
            self.dataChanged.emit(index, index, [role])
            self.dataChangedSignal.emit()
            return True
        except Exception as e:
            print(f"Error setting data: {e}")
            return False

    def add_row(self, default_data={}):
        self.beginInsertRows(QModelIndex(), len(self._view_df), len(self._view_df))
        new_row = pd.DataFrame([default_data])
        # 不足カラムを空文字で埋める
        for c in self.col_ids:
            if c not in new_row.columns:
                new_row[c] = ''
        
        self.df = pd.concat([self.df, new_row], ignore_index=True)
        self.reapply_filters()
        self.endResetModel()
        self.dataChangedSignal.emit()

    def remove_row(self, row_index):
        if row_index < 0 or row_index >= len(self._view_df): return
        self.beginRemoveRows(QModelIndex(), row_index, row_index)
        real_idx = self._view_df.index[row_index]
        self.df = self.df.drop(real_idx).reset_index(drop=True)
        self.reapply_filters()
        self.endResetModel()
        self.dataChangedSignal.emit()

# -----------------------------------------------------------------------------
# 2段ヘッダー (カラム名 + フィルタ行)
# -----------------------------------------------------------------------------
class FilterHeaderView(QHeaderView):
    """水平ヘッダーの下にフィルタ用の QLineEdit 行を追加するヘッダー。

    - 1行目: 既存のヘッダー描画 (カラム名)
    - 2行目: フィルタ入力欄
    """
    filterChanged = Signal(str, str)  # (col_id, text)

    def __init__(self, columns_def, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self.columns_def = columns_def
        self.col_ids = [c['id'] for c in columns_def]

        self.filter_row_height = 26
        self._base_height = super().sizeHint().height()

        self._editors = {}  # {col_id: QLineEdit}

        # フィルタ欄を生成
        for col_def in columns_def:
            col_id = col_def['id']
            le = QLineEdit(self)
            le.setPlaceholderText(f"Filter {col_def['label']}...")
            le.setClearButtonEnabled(True)
            le.setStyleSheet("""
                QLineEdit {
                    background-color: #2a2a2a;
                    color: #ffffff;
                    border: 1px solid #555;
                    padding: 1px 4px;
                    border-radius: 0px;
                    font-size: 11px;
                }
                QLineEdit:focus { border: 1px solid #4a90e2; }
            """)
            le.textChanged.connect(lambda text, cid=col_id: self.filterChanged.emit(cid, text))
            self._editors[col_id] = le

        # 位置更新のトリガ
        self.sectionResized.connect(lambda *_: self.updateEditorGeometries())
        self.sectionMoved.connect(lambda *_: self.updateEditorGeometries())
        # geometriesChanged はスクロールなどでも発火する
        try:
            self.geometriesChanged.connect(self.updateEditorGeometries)
        except Exception:
            pass

        QTimer.singleShot(0, self.updateEditorGeometries)

    def sizeHint(self):
        base = super().sizeHint()
        self._base_height = base.height()
        return QSize(base.width(), base.height() + self.filter_row_height)

    def minimumSizeHint(self):
        base = super().minimumSizeHint()
        # base height は sizeHint() から取得しておく
        if self._base_height <= 0:
            self._base_height = super().sizeHint().height()
        return QSize(base.width(), self._base_height + self.filter_row_height)

    def paintSection(self, painter, rect, logicalIndex):
        # カラム名は上段だけに描画
        base_h = self._base_height if self._base_height > 0 else super().sizeHint().height()
        label_rect = QRect(rect.x(), rect.y(), rect.width(), base_h)
        super().paintSection(painter, label_rect, logicalIndex)

        # 下段（フィルタ行）の背景
        filter_rect = QRect(rect.x(), rect.y() + base_h, rect.width(), self.filter_row_height)
        painter.fillRect(filter_rect, self.palette().window())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.updateEditorGeometries()

    def updateEditorGeometries(self):
        base_h = self._base_height if self._base_height > 0 else super().sizeHint().height()
        y = base_h
        h = self.filter_row_height

        for logical_index, col_def in enumerate(self.columns_def):
            col_id = col_def['id']
            editor = self._editors.get(col_id)
            if editor is None:
                continue

            if self.isSectionHidden(logical_index):
                editor.hide()
                continue

            x = self.sectionViewportPosition(logical_index)
            w = self.sectionSize(logical_index)

            # 罫線分の余白を少し取る
            editor.setGeometry(int(x) + 1, int(y) + 1, max(1, int(w) - 2), max(1, int(h) - 2))
            editor.show()
            editor.raise_()

# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# メインウィンドウ
# -----------------------------------------------------------------------------
class ScenarioEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scenario Scene Editor (Scene-Centric)")
        self.resize(1400, 900)
        
        self.current_db_path = None
        self.current_scene_uid = None

        # DataFrames (Master)
        self.df_scenes = pd.DataFrame()
        self.df_choices = pd.DataFrame()
        self.df_spots = pd.DataFrame()
        
        # Filter Management
        self.scene_filter_widgets = {}
        self.filter_row_height = 25
        self.filter_debounce_timer = QTimer()
        self.filter_debounce_timer.setSingleShot(True)
        self.filter_debounce_timer.setInterval(300)
        self.filter_debounce_timer.timeout.connect(self.process_filters)
        self.pending_filters = {} # {col_id: text}

        # UI構築
        self.setup_ui()
        self.setup_models()
        self.apply_stylesheet()
        
        # ショートカット
        self.save_shortcut = QAction("Save", self)
        self.save_shortcut.setShortcut(QKeySequence("Ctrl+S"))
        self.save_shortcut.triggered.connect(self.save_to_db)
        self.addAction(self.save_shortcut)

    def setup_models(self):
        # Scene List Model (Left Panel)
        self.scene_model = PandasTableModel(COLS_SCENE)
        self.scene_table.setModel(self.scene_model)
        
        # Column width setting (after model set)
        for i, col_def in enumerate(COLS_SCENE):
            if 'width' in col_def:
                self.scene_table.setColumnWidth(i, col_def['width'])
        
        # Sub Models (Right Panel)
        self.choice_model = PandasTableModel(COLS_CHOICE)
        self.choice_table.setModel(self.choice_model)
        for i, col_def in enumerate(COLS_CHOICE):
            if 'width' in col_def:
                self.choice_table.setColumnWidth(i, col_def['width'])
        
        self.spot_model = PandasTableModel(COLS_SPOT)
        self.spot_table.setModel(self.spot_model)
        self.spot_table.selectionModel().currentRowChanged.connect(self.on_spot_row_changed)
        for i, col_def in enumerate(COLS_SPOT):
            if 'width' in col_def:
                self.spot_table.setColumnWidth(i, col_def['width'])

        # Selection Handling
        self.scene_table.selectionModel().currentRowChanged.connect(self.on_scene_selected)
        
        # Setup Column Filters logic for Scene Table (Header embedded filters)
        self.filter_header.filterChanged.connect(self.on_column_filter_change)
        self.scene_table.horizontalScrollBar().valueChanged.connect(self.filter_header.updateEditorGeometries)
        QTimer.singleShot(0, self.filter_header.updateEditorGeometries)

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Toolbar
        toolbar = QToolBar()
        self.addToolBar(toolbar)
        
        # Menu Bar
        menubar = self.menuBar()
        
        # File Menu
        file_menu = menubar.addMenu("&File")

        act_new = QAction("New DB...", self)
        act_new.triggered.connect(self.create_new_db)
        file_menu.addAction(act_new)

        act_open = QAction("Open DB...", self)
        act_open.triggered.connect(self.open_db)
        file_menu.addAction(act_open)
        toolbar.addAction(act_open)

        act_save = QAction("Save DB", self)
        act_save.triggered.connect(self.save_to_db)
        file_menu.addAction(act_save)
        toolbar.addAction(act_save)
        
        file_menu.addSeparator()

        act_import = QAction("Import Data from DB...", self)
        act_import.triggered.connect(self.import_from_db)
        file_menu.addAction(act_import)

        file_menu.addSeparator()
        
        act_exit = QAction("Exit", self)
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # Tools Menu
        tools_menu = menubar.addMenu("&Tools")
        
        act_autolink = QAction("Auto-Link Next Scenes", self)
        act_autolink.triggered.connect(self.auto_link_scenes)
        tools_menu.addAction(act_autolink)

        act_gen_choices = QAction("Generate Choices from Text", self)
        act_gen_choices.triggered.connect(self.generate_choices_from_text)
        tools_menu.addAction(act_gen_choices)

        tools_menu.addSeparator()

        act_gen_testimony = QAction("Generate Testimony Spots/Branches/Choices", self)
        act_gen_testimony.triggered.connect(self.generate_testimony_spots_branches_choices)
        tools_menu.addAction(act_gen_testimony)

        act_resolve_next = QAction("Auto-Resolve Choice Next Scenes", self)
        act_resolve_next.triggered.connect(self.auto_resolve_choice_next_scenes)
        tools_menu.addAction(act_resolve_next)

        act_resolve_next_pick = QAction("Pick Unresolved Choice Next Scenes...", self)
        act_resolve_next_pick.triggered.connect(self.pick_unresolved_choice_next_scenes)
        tools_menu.addAction(act_resolve_next_pick)

        # Splitter (Left: Scene List, Right: Detail Editors)
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # --- Left Panel: Scene List ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0,0,0,0)
        
        # Find Box (Search & Jump)
        h_search = QHBoxLayout()
        h_search.setContentsMargins(5, 5, 5, 0)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Find text (Enter to find next)...")
        self.search_edit.returnPressed.connect(self.find_next_scene)
        h_search.addWidget(QLabel("Find:"))
        h_search.addWidget(self.search_edit)
        btn_find = QPushButton("Next")
        btn_find.clicked.connect(self.find_next_scene)
        h_search.addWidget(btn_find)
        left_layout.addLayout(h_search)

        # Table (Scene list)
        self.scene_table = QTableView()
        # 2段ヘッダー（カラム名 + フィルタ）
        self.filter_header = FilterHeaderView(COLS_SCENE, self.scene_table)
        self.scene_table.setHorizontalHeader(self.filter_header)
        self.scene_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.scene_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.scene_table.setAlternatingRowColors(True)
        # 行番号ヘッダーを表示（フィルタの位置合わせのため幅が必要）
        self.scene_table.verticalHeader().setVisible(True) 
        self.scene_table.verticalHeader().setDefaultSectionSize(28)
        
        # 右クリックメニュー（Scene Table）
        self.scene_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.scene_table.customContextMenuRequested.connect(self.show_scene_table_context_menu)

        left_layout.addWidget(self.scene_table)
        
        splitter.addWidget(left_widget)
        splitter.setStretchFactor(0, 1)

        # --- Right Panel: Details ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # 1. Scene Properties Editor
        grp_scene = QGroupBox("Selected Scene Properties")
        form_layout = QFormLayout(grp_scene)
        
        self.edit_uid = QLineEdit()
        self.edit_uid.setReadOnly(True)
        self.edit_uid.setStyleSheet("color: #aaa;")
        
        self.combo_type = QComboBox()
        self.combo_type.addItems([e.value for e in SceneType])
        self.combo_type.currentTextChanged.connect(self.on_scene_data_changed)

        self.edit_next = QLineEdit()
        self.edit_next.setPlaceholderText("Next Scene UID (for Linear/Terminal)")
        self.edit_next.textChanged.connect(self.on_scene_data_changed)
        
        self.edit_text = QPlainTextEdit()
        self.edit_text.setMaximumHeight(100)
        self.edit_text.setContextMenuPolicy(Qt.CustomContextMenu)
        self.edit_text.customContextMenuRequested.connect(self.show_text_context_menu)
        self.edit_text.textChanged.connect(self.on_scene_text_changed)

        form_layout.addRow("Scene ID:", self.edit_uid)
        form_layout.addRow("Type:", self.combo_type)
        form_layout.addRow("Next Scene:", self.edit_next)
        form_layout.addRow("Text:", self.edit_text)
        self.lbl_spot_match = QLabel("")
        self.lbl_spot_match.setWordWrap(True)
        form_layout.addRow("Spot Match:", self.lbl_spot_match)
        
        right_layout.addWidget(grp_scene)

        # 2. Choices Editor
        grp_choices = QGroupBox("Branch Choices (scenario_choice)")
        v_choices = QVBoxLayout(grp_choices)
        
        h_choices_tools = QHBoxLayout()
        btn_add_choice = QPushButton("Add Choice")
        btn_add_choice.clicked.connect(self.add_choice)
        btn_del_choice = QPushButton("Delete Choice")
        btn_del_choice.clicked.connect(self.del_choice)
        h_choices_tools.addWidget(btn_add_choice)
        h_choices_tools.addWidget(btn_del_choice)
        h_choices_tools.addStretch()
        v_choices.addLayout(h_choices_tools)
        
        self.choice_table = QTableView()
        self.choice_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.choice_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.choice_table.customContextMenuRequested.connect(self.show_choice_table_context_menu)
        self.choice_table.verticalHeader().setDefaultSectionSize(24)
        v_choices.addWidget(self.choice_table)
        
        right_layout.addWidget(grp_choices)

        # 3. Click Spots Editor
        grp_spots = QGroupBox("Click Spots (scenario_click_spot) - For Testimony")
        v_spots = QVBoxLayout(grp_spots)
        
        h_spots_tools = QHBoxLayout()
        btn_add_spot = QPushButton("Add Spot")
        btn_add_spot.clicked.connect(self.add_spot)
        btn_del_spot = QPushButton("Delete Spot")
        btn_del_spot.clicked.connect(self.del_spot)
        h_spots_tools.addWidget(btn_add_spot)
        h_spots_tools.addWidget(btn_del_spot)
        h_spots_tools.addStretch()
        v_spots.addLayout(h_spots_tools)
        
        self.spot_table = QTableView()
        self.spot_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.spot_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.spot_table.customContextMenuRequested.connect(self.show_spot_table_context_menu)
        self.spot_table.verticalHeader().setDefaultSectionSize(24)
        v_spots.addWidget(self.spot_table)
        
        right_layout.addWidget(grp_spots)
        
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(1, 2)

        # Flag to prevent loop
        self.updating_ui = False

    def on_column_filter_change(self, col_id, text):
        self.pending_filters[col_id] = text
        self.filter_debounce_timer.start()

    def process_filters(self):
        for col_id, text in self.pending_filters.items():
            self.scene_model.column_filters[col_id] = text
        self.pending_filters.clear()
        self.scene_model.apply_filters()

    def find_next_scene(self):
        text = self.search_edit.text()
        if not text: return

        df = self.scene_model._view_df
        rows_count = len(df)
        if rows_count == 0: return

        current_index = self.scene_table.currentIndex()
        start_row = (current_index.row() + 1) if current_index.isValid() else 0
        
        found_idx = -1
        for i in range(rows_count):
            row = (start_row + i) % rows_count
            match = False
            for col_id in self.scene_model.col_ids:
                val = str(df.iloc[row][col_id])
                if text.lower() in val.lower():
                    match = True
                    break
            if match:
                found_idx = row
                break
        
        if found_idx != -1:
            idx = self.scene_model.index(found_idx, 0)
            self.scene_table.setCurrentIndex(idx)
            self.scene_table.scrollTo(idx, QAbstractItemView.PositionAtCenter)
            self.statusBar().showMessage(f"Found at row {found_idx + 1}", 2000)
        else:
            self.statusBar().showMessage(f"Not found: '{text}'", 2000)

    # -------------------------------------------------------------------------
    # Context Menu: Scene Table (scenario_text)
    # -------------------------------------------------------------------------
    def show_scene_table_context_menu(self, pos):
        """Scene一覧テーブル用の右クリックメニュー"""
        idx = self.scene_table.indexAt(pos)
        if idx.isValid():
            self.scene_table.setCurrentIndex(idx)
            self.scene_table.selectRow(idx.row())

        menu = QMenu(self)

        act_rename = QAction("Rename Scene UID...", self)
        act_rename.triggered.connect(lambda: self.prompt_rename_scene_uid(idx))
        menu.addAction(act_rename)

        menu.addSeparator()

        act_add_after = QAction("Add Scene (after selected)", self)
        act_add_after.triggered.connect(lambda: self.add_scene_record(relative="after", view_row=idx.row() if idx.isValid() else None))
        menu.addAction(act_add_after)

        act_add_before = QAction("Add Scene (before selected)", self)
        act_add_before.triggered.connect(lambda: self.add_scene_record(relative="before", view_row=idx.row() if idx.isValid() else None))
        menu.addAction(act_add_before)

        menu.addSeparator()

        act_add_end = QAction("Add Scene (append to end)", self)
        act_add_end.triggered.connect(lambda: self.add_scene_record(relative="end", view_row=None))
        menu.addAction(act_add_end)

        menu.exec(self.scene_table.viewport().mapToGlobal(pos))

    def add_scene_record(self, relative="after", view_row=None):
        """scenario_text に新規レコードを追加する（Scene一覧の右クリックから呼ばれる）"""
        # 現在の右ペイン編集内容（choice/spot）を取りこぼさない
        self.save_current_sub_tables()

        # 必要カラムの確保
        required_cols = [c['id'] for c in COLS_SCENE]
        if self.scene_model.df is None or self.scene_model.df.empty:
            self.scene_model.df = pd.DataFrame(columns=required_cols)
        else:
            for c in required_cols:
                if c not in self.scene_model.df.columns:
                    self.scene_model.df[c] = ''
        # 追加するUIDは「選択行のUID + '_NEW'」を基本にする
        ref_uid = None
        try:
            # 優先: 右クリックされた行（view_row）
            if view_row is not None and view_row >= 0 and view_row < len(self.scene_model._view_df):
                real_idx_for_uid = int(self.scene_model._view_df.index[view_row])
                ref_uid = str(self.scene_model.df.at[real_idx_for_uid, 'uid'])
            else:
                # 次点: 現在選択されている行
                cur = self.scene_table.currentIndex()
                if cur.isValid() and cur.row() >= 0 and cur.row() < len(self.scene_model._view_df):
                    real_idx_for_uid = int(self.scene_model._view_df.index[cur.row()])
                    ref_uid = str(self.scene_model.df.at[real_idx_for_uid, 'uid'])
        except Exception:
            ref_uid = None

        if ref_uid:
            base_uid = f"{ref_uid}_NEW"
            # 既存UIDと衝突する場合は末尾に連番を付ける（_NEW2, _NEW3, ...）
            existing = set(self.scene_model.df['uid'].astype(str).tolist()) if 'uid' in self.scene_model.df.columns else set()
            new_uid = base_uid
            n = 2
            while new_uid in existing:
                new_uid = f"{base_uid}{n}"
                n += 1
        else:
            new_uid = str(uuid.uuid4())

        new_row = {
            'uid': new_uid,
            'scene_type': 'linear',
            'next_scene_uid': '',
            'actor': '',
            'text': ''
        }

        insert_at = len(self.scene_model.df)  # default: append

        # フィルタ適用中でも「表示行 -> 実体DFのindex」を辿って挿入位置を決める
        if view_row is not None and view_row >= 0 and view_row < len(self.scene_model._view_df):
            try:
                real_idx = int(self.scene_model._view_df.index[view_row])
                if relative == "before":
                    insert_at = max(0, real_idx)
                elif relative == "after":
                    insert_at = min(len(self.scene_model.df), real_idx + 1)
            except Exception:
                insert_at = len(self.scene_model.df)

        if relative == "end":
            insert_at = len(self.scene_model.df)

        # pandas で挿入（順序維持）
        top = self.scene_model.df.iloc[:insert_at].copy()
        bottom = self.scene_model.df.iloc[insert_at:].copy()
        self.scene_model.df = pd.concat([top, pd.DataFrame([new_row]), bottom], ignore_index=True)

        # モデル更新（フィルタも再適用）
        self.scene_model.set_dataframe(self.scene_model.df)

        # 追加した行にジャンプ（フィルタで見えない可能性はある）
        try:
            view_match = self.scene_model._view_df[self.scene_model._view_df['uid'].astype(str) == str(new_uid)]
            if not view_match.empty:
                # _view_df はフィルタで index が飛ぶことがあるため「位置（0..）」に変換してから model.index() を作る
                idx_label = view_match.index[0]
                view_row_new = int(self.scene_model._view_df.index.get_loc(idx_label))
                idx_new = self.scene_model.index(view_row_new, 0)
                self.scene_table.setCurrentIndex(idx_new)
                self.scene_table.selectRow(view_row_new)
                self.scene_table.scrollTo(idx_new, QAbstractItemView.PositionAtCenter)
                self.on_scene_selected(idx_new, QModelIndex())
            else:
                self.statusBar().showMessage("Scene added, but it may be hidden by current filters.", 4000)
        except Exception as e:
            print(f"Failed to select new scene: {e}")
            self.statusBar().showMessage("Scene added.", 2000)


    def apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #202020; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; }
            QGroupBox { font-weight: bold; border: 1px solid #444; margin-top: 6px; padding-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; }
            QTableView { background-color: #252525; gridline-color: #444; border: 1px solid #333; }
            QHeaderView::section { background-color: #333; padding: 4px; border: 1px solid #444; }
            QLineEdit, QPlainTextEdit, QComboBox { background-color: #303030; border: 1px solid #555; color: #fff; padding: 4px; }
            QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #4a90e2; }
            QPushButton { background-color: #3c3c3c; border: 1px solid #555; padding: 5px 10px; }
            QPushButton:hover { background-color: #505050; }
            QSplitter::handle { background-color: #444; width: 2px; }
            
            /* Menu Styles */
            QMenuBar { background-color: #2d2d2d; }
            QMenuBar::item { background: transparent; padding: 4px 10px; }
            QMenuBar::item:selected { background-color: #505050; }
            QMenu { background-color: #2d2d2d; border: 1px solid #444; }
            QMenu::item { padding: 5px 20px 5px 10px; }
            QMenu::item:selected { background-color: #505050; }
        """)

    # -------------------------------------------------------------------------
    # Tools Logic
    # -------------------------------------------------------------------------
    def auto_link_scenes(self):
        reply = QMessageBox.question(self, "Confirm", "全ての'linear'シーンの Next Scene を上から順に連番で上書きしますか？", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes: return

        df = self.scene_model.df
        uids = df['uid'].tolist()
        
        # DataFrameを直接更新
        for i in range(len(uids) - 1):
            if df.at[i, 'scene_type'] == 'linear':
                df.at[i, 'next_scene_uid'] = uids[i+1]
        
        # 最後は空に (linearの場合)
        if len(uids) > 0 and df.at[len(uids)-1, 'scene_type'] == 'linear':
            df.at[len(uids)-1, 'next_scene_uid'] = ''

        # モデルに反映
        self.scene_model.set_dataframe(df)
        
        # UI更新（選択中の行があれば詳細ビューも更新）
        if self.current_scene_uid:
            self.on_scene_selected(self.scene_table.currentIndex(), QModelIndex())
            
        self.statusBar().showMessage("Auto-linked 'linear' scenes.")

    def generate_choices_from_text(self):
        reply = QMessageBox.question(self, "Confirm", "テキスト内の 'Choice' を含むUID（'trial'を含むものは除く）を検出し、以下の処理を一括で行いますか？\n\n1. scenario_choice テーブルへ選択肢データの生成・追加\n2. 該当する親シーンのTypeを 'branch' に変更しNextを空に\n3. 選択肢シーンのTypeを 'choice_text' に変更しNextを空に", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes: return

        new_choices = []
        last_non_choice_uid = None
        last_non_choice_idx = None # 親のインデックスを保持
        
        # 既存の choice_text_uid セットを作っておく（重複回避のため）
        existing_keys = set()
        if not self.df_choices.empty:
            for _, row in self.df_choices.iterrows():
                existing_keys.add((row['scene_id'], row['choice_text_uid']))

        count = 0
        updates_scene_count = 0

        # シーン走査
        for index, row in self.scene_model.df.iterrows():
            uid = str(row['uid'])
            
            if "Choice" in uid and "trial" not in uid:
                # 選択肢行のTypeを 'choice_text' に更新
                is_updated = False
                if self.scene_model.df.at[index, 'scene_type'] != 'choice_text':
                    self.scene_model.df.at[index, 'scene_type'] = 'choice_text'
                    is_updated = True
                
                # 選択肢テキストの next_scene_uid を空にする
                if self.scene_model.df.at[index, 'next_scene_uid'] != '':
                    self.scene_model.df.at[index, 'next_scene_uid'] = ''
                    is_updated = True
                
                if is_updated:
                    updates_scene_count += 1

                if last_non_choice_uid:
                    # 親シーンのTypeを 'branch' に更新
                    if last_non_choice_idx is not None:
                        is_updated_parent = False
                        if self.scene_model.df.at[last_non_choice_idx, 'scene_type'] != 'branch':
                            self.scene_model.df.at[last_non_choice_idx, 'scene_type'] = 'branch'
                            is_updated_parent = True
                        
                        # 親シーンの next_scene_uid を空にする
                        if self.scene_model.df.at[last_non_choice_idx, 'next_scene_uid'] != '':
                            self.scene_model.df.at[last_non_choice_idx, 'next_scene_uid'] = ''
                            is_updated_parent = True
                        
                        if is_updated_parent:
                            updates_scene_count += 1
                    
                    # scenario_choice 生成
                    if (last_non_choice_uid, uid) not in existing_keys:
                        new_choice = {
                            'choice_id': str(uuid.uuid4())[:8],
                            'scene_id': last_non_choice_uid,
                            'choice_text_uid': uid,
                            'axis': 'progression',
                            'next_scene_id': '',
                            'correct': 0, # Added default correct value
                            'disp_order': 0
                        }
                        new_choices.append(new_choice)
                        existing_keys.add((last_non_choice_uid, uid))
                        count += 1
            else:
                last_non_choice_uid = uid
                last_non_choice_idx = index
        
        # 選択肢データの更新
        if new_choices:
            new_df = pd.DataFrame(new_choices)
            for c in [col['id'] for col in COLS_CHOICE]:
                if c not in new_df.columns:
                    new_df[c] = ''
            self.df_choices = pd.concat([self.df_choices, new_df], ignore_index=True)
            
            # 現在表示中のシーンがあれば更新
            if self.current_scene_uid:
                choices_subset = self.df_choices[self.df_choices['scene_id'] == self.current_scene_uid].copy()
                self.choice_model.set_dataframe(self._choices_with_texts(choices_subset))
            
            QMessageBox.information(self, "Success", f"{count} choices generated. {updates_scene_count} scenes updated.")
        elif updates_scene_count > 0:
            QMessageBox.information(self, "Success", f"No new choices found, but {updates_scene_count} scenes updated.")
        else:
            QMessageBox.information(self, "Result", "No changes made.")

        # シーン情報の変更もUIに反映
        if updates_scene_count > 0:
            self.scene_model.set_dataframe(self.scene_model.df)
            self.scene_model.reapply_filters()
            # 選択中の行のプロパティも更新する
            if self.current_scene_uid:
                 self.on_scene_selected(self.scene_table.currentIndex(), QModelIndex())

    # -------------------------------------------------------------------------
    # Tools: Testimony automation (click spot + branch + choice)
    # -------------------------------------------------------------------------
    def _extract_link_tags(self, text: str):
        s = text or ""
        links = []
        for m in re.finditer(r'<link="([^"]+)">(.*?)</link>', s, flags=re.IGNORECASE | re.DOTALL):
            link_id = (m.group(1) or "").strip()
            label = (m.group(2) or "").strip()
            if link_id and label:
                links.append((link_id, label))
        return links

    def _parse_objection_id(self, link_id: str):
        m = re.fullmatch(r"Objection_(\d{2})_(\d{2})_(\d{2})_(\d{2})", (link_id or "").strip())
        if not m:
            return None
        a = int(m.group(1))
        b = int(m.group(2))
        c = int(m.group(3))
        d = int(m.group(4))
        return a, b, c, d

    def _choice_uid_from_objection_id(self, link_id: str):
        parsed = self._parse_objection_id(link_id)
        if not parsed:
            return None
        a, b, c, d = parsed
        return f"{a:02}{b:02}Trial{c:02}_Choice{d:03}"

    def _trial_prefix_from_uid(self, uid: str):
        m = re.match(r"^(\d{4}Trial\d{2})_", (uid or "").strip())
        return m.group(1) if m else None

    def _ensure_scene_row(self, uid: str, scene_type: str, text: str = "", actor: str = "", next_scene_uid: str = ""):
        uid = (uid or "").strip()
        if uid == "":
            return False
        existing = set(self.scene_model.df["uid"].astype(str)) if "uid" in self.scene_model.df.columns else set()
        if uid in existing:
            return False
        new_row = {
            "uid": uid,
            "text": text or "",
            "actor": actor or "",
            "scene_type": scene_type or "linear",
            "next_scene_uid": next_scene_uid or "",
        }
        self.scene_model.df = pd.concat([self.scene_model.df, pd.DataFrame([new_row])], ignore_index=True)
        return True

    def _ensure_choice_row(self, scene_id: str, choice_text_uid: str, disp_order: int, axis: str = "progression"):
        scene_id = str(scene_id or "")
        choice_text_uid = str(choice_text_uid or "")
        if scene_id == "" or choice_text_uid == "":
            return False

        if self.df_choices is None or self.df_choices.empty:
            cols = [c['id'] for c in COLS_CHOICE] + ["scene_id"]
            self.df_choices = pd.DataFrame(columns=cols)

        if "scene_id" not in self.df_choices.columns:
            self.df_choices["scene_id"] = ""

        existing_keys = set()
        if not self.df_choices.empty and "choice_text_uid" in self.df_choices.columns:
            for _, row in self.df_choices.iterrows():
                existing_keys.add((str(row.get("scene_id", "")), str(row.get("choice_text_uid", ""))))

        if (scene_id, choice_text_uid) in existing_keys:
            return False

        existing_ids = set(self.df_choices["choice_id"].astype(str)) if "choice_id" in self.df_choices.columns else set()
        choice_id = str(uuid.uuid4())[:8]
        while choice_id in existing_ids:
            choice_id = str(uuid.uuid4())[:8]

        new_row = {
            "choice_id": choice_id,
            "scene_id": scene_id,
            "choice_text_uid": choice_text_uid,
            "axis": axis,
            "next_scene_id": "",
            "correct": 0,
            "disp_order": int(disp_order) if disp_order is not None else 0,
        }
        self.df_choices = pd.concat([self.df_choices, pd.DataFrame([new_row])], ignore_index=True)
        return True

    def _upsert_spot_row(self, scene_id: str, target_text: str, next_scene_id: str, disp_order: int, spot_id: str):
        scene_id = str(scene_id or "")
        target_text = str(target_text or "")
        next_scene_id = str(next_scene_id or "")
        spot_id = str(spot_id or "")
        if scene_id == "" or target_text == "" or spot_id == "":
            return False, False

        if self.df_spots is None or self.df_spots.empty:
            cols = [c['id'] for c in COLS_SPOT] + ["scene_id"]
            self.df_spots = pd.DataFrame(columns=cols)

        if "scene_id" not in self.df_spots.columns:
            self.df_spots["scene_id"] = ""

        if "spot_id" in self.df_spots.columns:
            mask = self.df_spots["spot_id"].astype(str) == spot_id
            if mask.any():
                # 既存spot_idがあれば更新（testimony再生成時の修正用途）
                idx = self.df_spots.index[mask][0]
                self.df_spots.at[idx, "scene_id"] = scene_id
                self.df_spots.at[idx, "target_text"] = target_text
                self.df_spots.at[idx, "next_scene_id"] = next_scene_id
                try:
                    cur = self.df_spots.at[idx, "disp_order"]
                    if cur is None or (isinstance(cur, str) and cur.strip() == ""):
                        self.df_spots.at[idx, "disp_order"] = int(disp_order) if disp_order is not None else 0
                except Exception:
                    self.df_spots.at[idx, "disp_order"] = int(disp_order) if disp_order is not None else 0
                return False, True

        # spot_id が無い場合のみ新規追加（重複回避のため suffix は付けない）
        new_row = {
            "spot_id": spot_id,
            "scene_id": scene_id,
            "target_text": target_text,
            "next_scene_id": next_scene_id,
            "correct": 0,
            "disp_order": int(disp_order) if disp_order is not None else 0,
        }
        self.df_spots = pd.concat([self.df_spots, pd.DataFrame([new_row])], ignore_index=True)
        return True, False

    def generate_testimony_spots_branches_choices(self):
        msg = (
            "testimony シーンの本文から <link=\"Objection_..\">..</link> を抽出し、以下を一括生成します。\n\n"
            "1) scenario_click_spot: scene_id=testimony, target_text=リンク文字列, next_scene_id=自動作成branch\n"
            "2) scenario_text: branch シーン（存在しない場合）\n"
            "3) scenario_text: choice_text シーン（存在しない場合）\n"
            "4) scenario_choice: branch -> choice_text の紐付け（存在しない場合）\n\n"
            "注意: next_scene_id(Choice) の自動設定は精度が落ちるため、別ツールで推定します。"
        )
        reply = QMessageBox.question(self, "Confirm", msg, QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        if self.scene_model.df is None or self.scene_model.df.empty:
            QMessageBox.information(self, "No Data", "No scene data loaded.")
            return

        created_spots = 0
        updated_spots = 0
        created_branches = 0
        created_choices_scene = 0
        created_choice_links = 0
        skipped_invalid = 0

        df = self.scene_model.df

        # disp_order の採番を scene_id 単位で継続する
        next_spot_order = {}
        if self.df_spots is not None and not self.df_spots.empty and "scene_id" in self.df_spots.columns:
            for sid, sub in self.df_spots.groupby("scene_id"):
                try:
                    mx = int(pd.to_numeric(sub.get("disp_order", pd.Series([0])), errors="coerce").fillna(0).max())
                except Exception:
                    mx = 0
                next_spot_order[str(sid)] = mx + 1

        for _, row in df.iterrows():
            uid = str(row.get("uid", ""))
            st = str(row.get("scene_type", ""))
            if st != "testimony":
                continue

            links = self._extract_link_tags(str(row.get("text", "")))
            if not links:
                continue

            for link_id, label in links:
                choice_uid = self._choice_uid_from_objection_id(link_id)
                parsed = self._parse_objection_id(link_id)
                if not choice_uid or not parsed:
                    skipped_invalid += 1
                    continue

                _, _, _, d = parsed
                branch_uid = f"{uid}_Branch{d:03}"

                if self._ensure_scene_row(branch_uid, "branch", text=f"[AUTO] {link_id}"):
                    created_branches += 1

                # choice_text シーンが無ければ作る（本文は空のまま）
                if self._ensure_scene_row(choice_uid, "choice_text", text=""):
                    created_choices_scene += 1

                # choice link: branch -> choice_text
                if self._ensure_choice_row(branch_uid, choice_uid, disp_order=d):
                    created_choice_links += 1

                # click spot: testimony -> branch
                order = next_spot_order.get(uid, 1)
                spot_id = f"{uid}__{link_id}"
                created, updated = self._upsert_spot_row(uid, label, branch_uid, disp_order=order, spot_id=spot_id)
                if created:
                    created_spots += 1
                    next_spot_order[uid] = order + 1
                elif updated:
                    updated_spots += 1

        # UI反映
        self.scene_model.set_dataframe(self.scene_model.df)
        if self.current_scene_uid:
            self.on_scene_selected(self.scene_table.currentIndex(), QModelIndex())

        QMessageBox.information(
            self,
            "Done",
            f"Created spots: {created_spots}\n"
            f"Updated spots: {updated_spots}\n"
            f"Created branch scenes: {created_branches}\n"
            f"Created choice_text scenes: {created_choices_scene}\n"
            f"Created scenario_choice links: {created_choice_links}\n"
            f"Skipped (invalid link_id): {skipped_invalid}",
        )

    def _normalize_text_for_match(self, s: str):
        s = s or ""
        # ruby/link 等のタグは雑に除去（完全なHTMLパーサは不要）
        s = re.sub(r"<[^>]+>", "", s)
        s = s.replace("\u3000", " ")
        s = s.replace("\n", " ")
        s = s.replace("\r", " ")
        return s

    def _text_preview(self, s: str, limit: int = 80):
        s = self._normalize_text_for_match(s)
        s = re.sub(r"\s+", " ", s).strip()
        if limit and len(s) > limit:
            return s[:limit] + "..."
        return s

    def _choices_with_texts(self, df_choices: pd.DataFrame):
        df = df_choices.copy() if df_choices is not None else pd.DataFrame(columns=[c["id"] for c in COLS_CHOICE] + ["scene_id"])
        if df.empty:
            for c in ("choice_text", "next_scene_text"):
                if c not in df.columns:
                    df[c] = ""
            return df

        scene_text_map = {}
        if self.scene_model.df is not None and not self.scene_model.df.empty and "uid" in self.scene_model.df.columns:
            try:
                scene_text_map = dict(zip(self.scene_model.df["uid"].astype(str), self.scene_model.df.get("text", "").astype(str)))
            except Exception:
                scene_text_map = {}

        def map_choice_text(uid):
            return self._text_preview(scene_text_map.get(str(uid or ""), ""))

        def map_next_text(uid):
            return self._text_preview(scene_text_map.get(str(uid or ""), ""))

        df["choice_text"] = df.get("choice_text_uid", "").apply(map_choice_text)
        df["next_scene_text"] = df.get("next_scene_id", "").apply(map_next_text)
        return df

    def _spots_with_texts(self, df_spots: pd.DataFrame):
        df = df_spots.copy() if df_spots is not None else pd.DataFrame(columns=[c["id"] for c in COLS_SPOT] + ["scene_id"])
        if df.empty:
            if "next_scene_text" not in df.columns:
                df["next_scene_text"] = ""
            return df

        scene_text_map = {}
        if self.scene_model.df is not None and not self.scene_model.df.empty and "uid" in self.scene_model.df.columns:
            try:
                scene_text_map = dict(zip(self.scene_model.df["uid"].astype(str), self.scene_model.df.get("text", "").astype(str)))
            except Exception:
                scene_text_map = {}

        def map_next_text(uid):
            return self._text_preview(scene_text_map.get(str(uid or ""), ""))

        df["next_scene_text"] = df.get("next_scene_id", "").apply(map_next_text)
        return df

    def _keywords_from_text(self, s: str):
        s = self._normalize_text_for_match(s)
        # 日本語は分かち書きが難しいので、漢字/カタカナ/英数の連続をキーワードにする
        toks = re.findall(r"[A-Za-z0-9_]+|[ァ-ヶー]{2,}|[一-龠]{1,}", s)
        # 1文字漢字はノイズも多いので、数を絞る（ただし「血」「筆」みたいな重要語もある）
        keep = []
        for t in toks:
            t = t.strip()
            if t == "":
                continue
            if len(t) == 1 and t not in ("血", "筆", "矢", "鍵"):
                continue
            keep.append(t)
        # 重複除去（順序維持）
        seen = set()
        out = []
        for t in keep:
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out[:12]

    def auto_resolve_choice_next_scenes(self):
        reply = QMessageBox.question(
            self,
            "Confirm",
            "scenario_choice.next_scene_id が空の行について、テキストの簡易一致で遷移先UIDを推定して自動設定しますか？\n"
            "（候補が見つからない/曖昧な場合は未設定のままです）",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        if self.df_choices is None or self.df_choices.empty:
            QMessageBox.information(self, "No Choices", "No scenario_choice data loaded.")
            return

        df_scenes = self.scene_model.df
        if df_scenes is None or df_scenes.empty:
            QMessageBox.information(self, "No Scenes", "No scene data loaded.")
            return

        # uid -> (index, text, scene_type)
        scene_index = {}
        for i, r in df_scenes.iterrows():
            uid = str(r.get("uid", ""))
            if uid:
                scene_index[uid] = (i, str(r.get("text", "")), str(r.get("scene_type", "")))

        # prefix -> indices
        prefix_to_indices = {}
        for uid, (i, _, _) in scene_index.items():
            prefix = self._trial_prefix_from_uid(uid)
            if not prefix:
                continue
            prefix_to_indices.setdefault(prefix, []).append(i)
        for p in prefix_to_indices:
            prefix_to_indices[p] = sorted(prefix_to_indices[p])

        updated = 0
        unresolved = 0

        for idx, row in self.df_choices.iterrows():
            cur_next = str(row.get("next_scene_id", "") or "")
            if cur_next.strip() != "":
                continue

            choice_uid = str(row.get("choice_text_uid", "") or "")
            if choice_uid not in scene_index:
                unresolved += 1
                continue

            choice_i, choice_text, _ = scene_index[choice_uid]
            prefix = self._trial_prefix_from_uid(choice_uid)
            if not prefix or prefix not in prefix_to_indices:
                unresolved += 1
                continue

            # choice_text の連続ブロックの末尾を探す
            indices = prefix_to_indices[prefix]
            try:
                pos = indices.index(choice_i)
            except ValueError:
                unresolved += 1
                continue

            block_end = choice_i
            for j in indices[pos + 1:]:
                uid2 = str(df_scenes.at[j, "uid"])
                if str(df_scenes.at[j, "scene_type"]) != "choice_text":
                    break
                block_end = j

            # マッチ用キーワード
            kw = self._keywords_from_text(choice_text)
            if not kw:
                unresolved += 1
                continue

            best_uid = None
            best_score = -1
            best_idx = None

            # ブロック末尾以降で探す（同一prefix内）
            for j in indices:
                if j <= block_end:
                    continue
                uid2 = str(df_scenes.at[j, "uid"])
                st2 = str(df_scenes.at[j, "scene_type"])
                if st2 == "choice_text":
                    continue
                t2 = self._normalize_text_for_match(str(df_scenes.at[j, "text"]))
                if t2.strip() == "":
                    continue

                score = 0
                for k in kw:
                    if k in t2:
                        # 長い語ほど重くする
                        score += 3 if len(k) >= 3 else 1
                if score <= 0:
                    continue

                # 早い出現を軽く優先
                score2 = score * 1000 - int(j)
                if score2 > best_score:
                    best_score = score2
                    best_uid = uid2
                    best_idx = j

            if best_uid:
                self.df_choices.at[idx, "next_scene_id"] = best_uid
                updated += 1
            else:
                unresolved += 1

        if self.current_scene_uid:
            subset = self.df_choices[self.df_choices["scene_id"] == self.current_scene_uid].copy()
            self.choice_model.set_dataframe(self._choices_with_texts(subset))

        QMessageBox.information(self, "Done", f"Updated: {updated}\nUnresolved: {unresolved}")

    # -------------------------------------------------------------------------
    # Tools: Interactive Next Scene picker (choice)
    # -------------------------------------------------------------------------
    def pick_unresolved_choice_next_scenes(self):
        reply = QMessageBox.question(
            self,
            "Confirm",
            "next_scene_id が未設定の scenario_choice について、候補UIDを絞り込んだ一覧から順に選択しますか？\n"
            "（キャンセルで途中終了）",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        if self.df_choices is None or self.df_choices.empty:
            QMessageBox.information(self, "No Choices", "No scenario_choice data loaded.")
            return

        df_scenes = self.scene_model.df
        if df_scenes is None or df_scenes.empty:
            QMessageBox.information(self, "No Scenes", "No scene data loaded.")
            return

        uid_to_idx = {}
        uid_to_text = {}
        for i, r in df_scenes.iterrows():
            uid = str(r.get("uid", ""))
            if uid:
                uid_to_idx[uid] = i
                uid_to_text[uid] = str(r.get("text", ""))

        prefix_to_indices = {}
        for uid, i in uid_to_idx.items():
            prefix = self._trial_prefix_from_uid(uid)
            if not prefix:
                continue
            prefix_to_indices.setdefault(prefix, []).append(i)
        for p in prefix_to_indices:
            prefix_to_indices[p] = sorted(prefix_to_indices[p])

        self.save_current_sub_tables()

        updated = 0
        skipped = 0
        total_unresolved = 0

        for df_idx, row in self.df_choices.iterrows():
            cur_next = str(row.get("next_scene_id", "") or "").strip()
            if cur_next != "":
                continue

            total_unresolved += 1

            choice_uid = str(row.get("choice_text_uid", "") or "")
            if choice_uid == "" or choice_uid not in uid_to_idx:
                skipped += 1
                continue

            prefix = self._trial_prefix_from_uid(choice_uid)
            if not prefix or prefix not in prefix_to_indices:
                skipped += 1
                continue

            choice_i = uid_to_idx[choice_uid]
            indices = prefix_to_indices[prefix]

            try:
                pos = indices.index(choice_i)
            except ValueError:
                skipped += 1
                continue

            block_end = choice_i
            for j in indices[pos + 1:]:
                if str(df_scenes.at[j, "scene_type"]) != "choice_text":
                    break
                block_end = j

            candidates = []
            for j in indices:
                if j <= block_end:
                    continue
                uid2 = str(df_scenes.at[j, "uid"])
                st2 = str(df_scenes.at[j, "scene_type"])
                if st2 == "choice_text":
                    continue
                candidates.append(uid2)

            if not candidates:
                skipped += 1
                continue

            choice_text = self._normalize_text_for_match(uid_to_text.get(choice_uid, ""))
            prompt = (
                f"choice_text_uid: {choice_uid}\n"
                f"text: {choice_text[:120]}\n\n"
                "Select Next UID:"
            )
            picked = self._pick_scene_uid_from_candidates("Pick Next Scene (Choice)", prompt, candidates)
            if picked is None:
                break

            self.df_choices.at[df_idx, "next_scene_id"] = picked
            updated += 1

        if self.current_scene_uid:
            subset = self.df_choices[self.df_choices["scene_id"] == self.current_scene_uid].copy()
            self.choice_model.set_dataframe(self._choices_with_texts(subset))

        QMessageBox.information(
            self,
            "Done",
            f"Updated: {updated}\nSkipped: {skipped}\nUnresolved (initial): {total_unresolved}",
        )

    # -------------------------------------------------------------------------
    # DB & Data Handling (New/Import/Open/Save)
    # -------------------------------------------------------------------------
    def create_new_db(self):
        path, _ = QFileDialog.getSaveFileName(self, "Create New DB", "new_scenario.db", "SQLite DB (*.db *.sqlite *.sqlite3)")
        if not path: return

        try:
            # スキーマのみ作成
            self.migrate_schema(path)
            # ロード
            self.load_data(path)
            self.current_db_path = path
            self.statusBar().showMessage(f"Created new DB: {path}")
            self.setWindowTitle(f"Scenario Scene Editor - {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create DB:\n{e}")

    def import_from_db(self):
        """外部DBからデータをインポートする（現在のデータに追加/マージ）"""
        path, _ = QFileDialog.getOpenFileName(self, "Import Data from DB", "", "SQLite DB (*.db *.sqlite *.sqlite3);;All Files (*)")
        if not path: return

        try:
            conn = sqlite3.connect(path)
            # 外部DBのテーブル一覧を取得して、scenario_text的なものを探す
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]
            
            target_table = None
            if 'scenario_text' in tables:
                target_table = 'scenario_text'
            elif 'text_data' in tables:
                target_table = 'text_data'
            
            if not target_table:
                # ユーザーに確認などの複雑なUIは省略し、今回はscenario_text必須とするか、
                # 強引に読むトライをする
                QMessageBox.warning(self, "Import Error", "Source DB does not have 'scenario_text' table.")
                conn.close()
                return

            # データを読み込む
            source_df = pd.read_sql_query(f"SELECT * FROM {target_table}", conn)
            conn.close()
            
            if source_df.empty:
                QMessageBox.information(self, "Import", "Source table is empty.")
                return

            # カラムマッピング（あるものだけコピー）
            # 現在のモデルに必要なカラム
            required_cols = [c['id'] for c in COLS_SCENE]
            
            # インポートデータ用の辞書リスト作成
            import_data = []
            for _, row in source_df.iterrows():
                new_row = {}
                for col in required_cols:
                    if col in row:
                        new_row[col] = row[col]
                    else:
                        # デフォルト値
                        if col == 'scene_type': new_row[col] = 'linear'
                        elif col == 'uid': new_row[col] = str(uuid.uuid4()) # uidがない場合は生成
                        else: new_row[col] = ''
                import_data.append(new_row)
            
            new_df = pd.DataFrame(import_data)
            
            # 現在のDFにマージ
            # uidが重複する場合はどうするか？ -> 今回は「インポートしたもので上書き」または「追加」
            # シンプルに concat して uid で drop_duplicates (keep='last') して上書き扱いにする
            combined_df = pd.concat([self.scene_model.df, new_df], ignore_index=True)
            combined_df = combined_df.drop_duplicates(subset=['uid'], keep='last').reset_index(drop=True)
            
            self.scene_model.df = combined_df
            
            # UI更新
            self.scene_model.set_dataframe(self.scene_model.df)
            self.scene_model.reapply_filters()
            
            QMessageBox.information(self, "Success", f"Imported {len(new_df)} rows from {target_table}.")
            self.statusBar().showMessage("Data imported. Remember to Save.")

        except Exception as e:
            QMessageBox.critical(self, "Import Error", str(e))

    def open_db(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open SQLite DB", "", "SQLite DB (*.db *.sqlite *.sqlite3)")
        if not path: return
        
        self.current_db_path = path
        try:
            self.migrate_schema(path)
            self.load_data(path)
            self.statusBar().showMessage(f"Loaded: {path}")
            self.setWindowTitle(f"Scenario Scene Editor - {path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def migrate_schema(self, db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scenario_text (
                uid TEXT PRIMARY KEY,
                text TEXT,
                actor TEXT,
                scene_type TEXT DEFAULT 'linear',
                next_scene_uid TEXT DEFAULT ''
            )
        """)
        
        # 既存テーブルのカラム不足チェック
        cursor.execute("PRAGMA table_info(scenario_text)")
        cols = [info[1] for info in cursor.fetchall()]
        if 'scene_type' not in cols:
            cursor.execute("ALTER TABLE scenario_text ADD COLUMN scene_type TEXT DEFAULT 'linear'")
        if 'next_scene_uid' not in cols:
            cursor.execute("ALTER TABLE scenario_text ADD COLUMN next_scene_uid TEXT DEFAULT ''")
            
        # 変更: label を choice_text_uid に変更し、FKを追加
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scenario_choice (
                choice_id TEXT PRIMARY KEY,
                scene_id TEXT NOT NULL,
                choice_text_uid TEXT NOT NULL,
                axis TEXT NOT NULL DEFAULT 'progression',
                next_scene_id TEXT,
                correct INTEGER DEFAULT 0,
                disp_order INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(scene_id) REFERENCES scenario_text(uid),
                FOREIGN KEY(choice_text_uid) REFERENCES scenario_text(uid),
                FOREIGN KEY(next_scene_id) REFERENCES scenario_text(uid)
            )
        """)
        
        # 既存テーブルへのカラム追加チェック (scenario_choice)
        try:
            cursor.execute("PRAGMA table_info(scenario_choice)")
            cols = [info[1] for info in cursor.fetchall()]
            if cols: # テーブルが存在する場合
                if 'choice_text_uid' not in cols:
                    cursor.execute("ALTER TABLE scenario_choice ADD COLUMN choice_text_uid TEXT NOT NULL DEFAULT ''")
                if 'correct' not in cols:
                    cursor.execute("ALTER TABLE scenario_choice ADD COLUMN correct INTEGER DEFAULT 0")
        except Exception as e:
            print(f"Migration warning: {e}")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scenario_click_spot (
                spot_id TEXT PRIMARY KEY,
                scene_id TEXT,
                target_text TEXT,
                next_scene_id TEXT,
                correct INTEGER DEFAULT 0,
                disp_order INTEGER DEFAULT 0
            )
        """)
        
        conn.commit()
        conn.close()

    def load_data(self, db_path):
        conn = sqlite3.connect(db_path)
        
        self.scene_model.df = pd.read_sql_query("SELECT * FROM scenario_text", conn)
        for col in ['scene_type', 'next_scene_uid']:
            if col not in self.scene_model.df.columns:
                self.scene_model.df[col] = ''
        self.scene_model.df['scene_type'].replace('', 'linear', inplace=True)
        self.scene_model.df.fillna('', inplace=True)

        try:
            self.df_choices = pd.read_sql_query("SELECT * FROM scenario_choice", conn)
        except:
            self.df_choices = pd.DataFrame(columns=[c['id'] for c in COLS_CHOICE] + ['scene_id'])

        try:
            self.df_spots = pd.read_sql_query("SELECT * FROM scenario_click_spot", conn)
        except:
            self.df_spots = pd.DataFrame(columns=[c['id'] for c in COLS_SPOT] + ['scene_id'])
            
        conn.close()
        
        self.scene_model.set_dataframe(self.scene_model.df)
        QTimer.singleShot(100, self.filter_header.updateEditorGeometries) # Use filter header update

    def save_to_db(self):
        if not self.current_db_path:
            self.create_new_db()
            if not self.current_db_path:
                return

        # 取りこぼし防止
        self.save_current_sub_tables()

        # スキーマを確実に用意（PK/FK/カラム不足を補う）
        try:
            self.migrate_schema(self.current_db_path)
        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"Failed to migrate schema:\n{e}")
            return

        conn = sqlite3.connect(self.current_db_path)
        try:
            conn.execute("BEGIN")
            self._overwrite_table(conn, "scenario_text", self.scene_model.df)
            self._overwrite_table(conn, "scenario_choice", self.df_choices)
            self._overwrite_table(conn, "scenario_click_spot", self.df_spots)
            conn.commit()
            self.statusBar().showMessage(f"Saved successfully at {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            conn.rollback()
            QMessageBox.critical(self, "Save Error", str(e))
        finally:
            conn.close()

    def _overwrite_table(self, conn: sqlite3.Connection, table: str, df: pd.DataFrame):
        """既存テーブルのスキーマを保ったまま、全件入れ替えで保存する（to_sql replace禁止）"""
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        cols = [r[1] for r in cur.fetchall()]
        if not cols:
            raise RuntimeError(f"Table not found: {table}")

        df2 = df.copy() if df is not None else pd.DataFrame(columns=cols)
        for c in cols:
            if c not in df2.columns:
                if c in ("correct", "disp_order"):
                    df2[c] = 0
                elif c == "scene_type":
                    df2[c] = "linear"
                else:
                    df2[c] = ""

        df2 = df2[cols]

        cur.execute(f"DELETE FROM {table}")
        placeholders = ",".join(["?"] * len(cols))
        col_sql = ",".join(cols)
        sql = f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})"
        rows = [tuple("" if pd.isna(v) else v for v in r) for r in df2.itertuples(index=False, name=None)]
        if rows:
            cur.executemany(sql, rows)

    # -------------------------------------------------------------------------
    # Logic: Scene Selection & Filtering
    # -------------------------------------------------------------------------
    def on_scene_selected(self, current_idx, previous_idx):
        if not current_idx.isValid(): return
        
        if previous_idx.isValid():
            self.save_current_sub_tables()

        row = current_idx.row()
        scene_row = self.scene_model._view_df.iloc[row]
        self.current_scene_uid = scene_row['uid']
        
        self.updating_ui = True
        
        self.edit_uid.setText(self.current_scene_uid)
        self.combo_type.setCurrentText(str(scene_row['scene_type']))
        self.edit_next.setText(str(scene_row['next_scene_uid']))
        self.edit_text.setPlainText(str(scene_row['text']))
        
        choices_subset = self.df_choices[self.df_choices['scene_id'] == self.current_scene_uid].copy()
        self.choice_model.set_dataframe(self._choices_with_texts(choices_subset))
        
        spots_subset = self.df_spots[self.df_spots['scene_id'] == self.current_scene_uid].copy()
        self.spot_model.set_dataframe(self._spots_with_texts(spots_subset))
        
        self.updating_ui = False

    def save_current_sub_tables(self):
        if not self.current_scene_uid: return
        
        current_choices = self.choice_model.get_dataframe().drop(columns=["choice_text", "next_scene_text"], errors="ignore")
        other_choices = self.df_choices[self.df_choices['scene_id'] != self.current_scene_uid].drop(columns=["choice_text", "next_scene_text"], errors="ignore")
        if not current_choices.empty:
            current_choices['scene_id'] = self.current_scene_uid
        self.df_choices = pd.concat([other_choices, current_choices], ignore_index=True)
        
        current_spots = self.spot_model.get_dataframe().drop(columns=["next_scene_text"], errors="ignore")
        other_spots = self.df_spots[self.df_spots['scene_id'] != self.current_scene_uid].drop(columns=["next_scene_text"], errors="ignore")
        if not current_spots.empty:
            current_spots['scene_id'] = self.current_scene_uid
        self.df_spots = pd.concat([other_spots, current_spots], ignore_index=True)

    # -------------------------------------------------------------------------
    # Logic: Scene Property Editing
    # -------------------------------------------------------------------------
    def on_scene_data_changed(self):
        if self.updating_ui or not self.current_scene_uid: return
        
        target_idx = self.scene_model.df[self.scene_model.df['uid'] == self.current_scene_uid].index
        if len(target_idx) == 0: return
        idx = target_idx[0]
        
        self.scene_model.df.at[idx, 'scene_type'] = self.combo_type.currentText()
        self.scene_model.df.at[idx, 'next_scene_uid'] = self.edit_next.text()
        
        self.scene_model.reapply_filters()
        self.scene_model.layoutChanged.emit()

    def on_scene_text_changed(self):
        if self.updating_ui or not self.current_scene_uid: return
        
        target_idx = self.scene_model.df[self.scene_model.df['uid'] == self.current_scene_uid].index
        if len(target_idx) == 0: return
        idx = target_idx[0]
        
        self.scene_model.df.at[idx, 'text'] = self.edit_text.toPlainText()

    # -------------------------------------------------------------------------
    # Logic: Sub Table Actions
    # -------------------------------------------------------------------------
    def add_choice(self):
        if not self.current_scene_uid: return
        new_id = str(uuid.uuid4())[:8]
        self.choice_model.add_row({
            'choice_id': new_id, 
            'scene_id': self.current_scene_uid,
            'choice_text_uid': '', # 変更: label -> choice_text_uid
            'axis': 'progression', # Default値指定
            'next_scene_id': '',
            'correct': 0, # Added default correct value
            'disp_order': 0
        })

    def del_choice(self):
        idx = self.choice_table.currentIndex()
        if idx.isValid():
            self.choice_model.remove_row(idx.row())

    def add_spot(self):
        if not self.current_scene_uid: return
        new_id = str(uuid.uuid4())[:8]
        self.spot_model.add_row({
            'spot_id': new_id,
            'scene_id': self.current_scene_uid,
            'target_text': 'Target',
            'next_scene_id': '',
            'correct': 0,
            'disp_order': 0
        })
    
    def del_spot(self):
        idx = self.spot_table.currentIndex()
        if idx.isValid():
            self.spot_model.remove_row(idx.row())

    # -------------------------------------------------------------------------
    # Context Menus: Choice / Spot / Text
    # -------------------------------------------------------------------------
    def show_choice_table_context_menu(self, pos):
        idx = self.choice_table.indexAt(pos)
        if idx.isValid():
            self.choice_table.setCurrentIndex(idx)
            self.choice_table.selectRow(idx.row())

        menu = QMenu(self)
        act_rename = QAction("Rename Choice ID...", self)
        act_rename.triggered.connect(lambda: self.prompt_rename_choice_id(idx))
        menu.addAction(act_rename)

        act_set_next = QAction("Set Next Scene...", self)
        act_set_next.triggered.connect(lambda: self.prompt_set_next_scene_for_choice(idx))
        menu.addAction(act_set_next)

        menu.exec(self.choice_table.viewport().mapToGlobal(pos))

    def show_spot_table_context_menu(self, pos):
        idx = self.spot_table.indexAt(pos)
        if idx.isValid():
            self.spot_table.setCurrentIndex(idx)
            self.spot_table.selectRow(idx.row())

        menu = QMenu(self)
        act_rename = QAction("Rename Spot ID...", self)
        act_rename.triggered.connect(lambda: self.prompt_rename_spot_id(idx))
        menu.addAction(act_rename)

        act_set_next = QAction("Set Next Scene...", self)
        act_set_next.triggered.connect(lambda: self.prompt_set_next_scene_for_spot(idx))
        menu.addAction(act_set_next)

        menu.exec(self.spot_table.viewport().mapToGlobal(pos))

    def show_text_context_menu(self, pos):
        menu = self.edit_text.createStandardContextMenu()
        menu.addSeparator()
        act_create_spot = QAction("Create Click Spot from Selection", self)
        act_create_spot.triggered.connect(self.create_spot_from_text_selection)
        menu.addAction(act_create_spot)
        menu.exec(self.edit_text.mapToGlobal(pos))

    # -------------------------------------------------------------------------
    # Rename (ID) utilities
    # -------------------------------------------------------------------------
    def _unique_id(self, base: str, existing: set):
        base = (base or "").strip()
        if base == "":
            base = "NEW_ID"
        if base not in existing:
            return base
        i = 2
        while True:
            cand = f"{base}{i}"
            if cand not in existing:
                return cand
            i += 1

    def prompt_rename_scene_uid(self, idx: QModelIndex):
        if not idx.isValid():
            return
        row = idx.row()
        try:
            old_uid = str(self.scene_model._view_df.iloc[row]["uid"])
        except Exception:
            return

        new_uid, ok = QInputDialog.getText(self, "Rename Scene UID", "New UID:", text=old_uid)
        if not ok:
            return
        new_uid = (new_uid or "").strip()
        if new_uid == "" or new_uid == old_uid:
            return

        self.rename_scene_uid(old_uid, new_uid)

    def rename_scene_uid(self, old_uid: str, new_uid: str):
        self.save_current_sub_tables()

        existing = set(self.scene_model.df["uid"].astype(str)) if "uid" in self.scene_model.df.columns else set()
        if new_uid in existing:
            QMessageBox.warning(self, "Rename Error", f"UID already exists: {new_uid}")
            return
        if old_uid not in existing:
            QMessageBox.warning(self, "Rename Error", f"UID not found: {old_uid}")
            return

        self.scene_model.df.loc[self.scene_model.df["uid"] == old_uid, "uid"] = new_uid
        if "next_scene_uid" in self.scene_model.df.columns:
            self.scene_model.df.loc[self.scene_model.df["next_scene_uid"] == old_uid, "next_scene_uid"] = new_uid

        for col in ("scene_id", "choice_text_uid", "next_scene_id"):
            if col in self.df_choices.columns:
                self.df_choices.loc[self.df_choices[col] == old_uid, col] = new_uid

        for col in ("scene_id", "next_scene_id"):
            if col in self.df_spots.columns:
                self.df_spots.loc[self.df_spots[col] == old_uid, col] = new_uid

        if self.current_scene_uid == old_uid:
            self.current_scene_uid = new_uid

        self.scene_model.reapply_filters()
        self.scene_model.layoutChanged.emit()

        # 右ペインを更新
        self.on_scene_selected(self.scene_table.currentIndex(), QModelIndex())

        QMessageBox.information(self, "Renamed", f"Renamed UID:\n{old_uid} -> {new_uid}")

    def prompt_rename_choice_id(self, idx: QModelIndex):
        if not idx.isValid():
            return
        row = idx.row()
        try:
            old_id = str(self.choice_model._view_df.iloc[row]["choice_id"])
        except Exception:
            return

        new_id, ok = QInputDialog.getText(self, "Rename Choice ID", "New choice_id:", text=old_id)
        if not ok:
            return
        new_id = (new_id or "").strip()
        if new_id == "" or new_id == old_id:
            return

        self.save_current_sub_tables()
        existing = set(self.df_choices["choice_id"].astype(str)) if "choice_id" in self.df_choices.columns else set()
        if new_id in existing:
            QMessageBox.warning(self, "Rename Error", f"choice_id already exists: {new_id}")
            return

        self.df_choices.loc[self.df_choices["choice_id"] == old_id, "choice_id"] = new_id

        if self.current_scene_uid:
            subset = self.df_choices[self.df_choices["scene_id"] == self.current_scene_uid].copy()
            self.choice_model.set_dataframe(self._choices_with_texts(subset))

        QMessageBox.information(self, "Renamed", f"Renamed choice_id:\n{old_id} -> {new_id}")

    def prompt_rename_spot_id(self, idx: QModelIndex):
        if not idx.isValid():
            return
        row = idx.row()
        try:
            old_id = str(self.spot_model._view_df.iloc[row]["spot_id"])
        except Exception:
            return

        new_id, ok = QInputDialog.getText(self, "Rename Spot ID", "New spot_id:", text=old_id)
        if not ok:
            return
        new_id = (new_id or "").strip()
        if new_id == "" or new_id == old_id:
            return

        self.save_current_sub_tables()
        existing = set(self.df_spots["spot_id"].astype(str)) if "spot_id" in self.df_spots.columns else set()
        if new_id in existing:
            QMessageBox.warning(self, "Rename Error", f"spot_id already exists: {new_id}")
            return

        self.df_spots.loc[self.df_spots["spot_id"] == old_id, "spot_id"] = new_id

        if self.current_scene_uid:
            subset = self.df_spots[self.df_spots["scene_id"] == self.current_scene_uid].copy()
            self.spot_model.set_dataframe(self._spots_with_texts(subset))

        QMessageBox.information(self, "Renamed", f"Renamed spot_id:\n{old_id} -> {new_id}")

    # -------------------------------------------------------------------------
    # Next Scene picker (choice/spot)
    # -------------------------------------------------------------------------
    def _pick_scene_uid(self, title: str):
        uids = sorted(self.scene_model.df["uid"].astype(str).tolist()) if "uid" in self.scene_model.df.columns else []
        if not uids:
            QMessageBox.warning(self, "No Scenes", "No scene UIDs available.")
            return None
        picked, ok = QInputDialog.getItem(self, title, "Select UID:", uids, 0, False)
        if not ok:
            return None
        return picked

    def _pick_scene_uid_from_candidates(self, title: str, prompt: str, candidates):
        uids = [str(u) for u in (candidates or []) if str(u).strip() != ""]
        if not uids:
            QMessageBox.warning(self, "No Candidates", "No candidate UIDs available.")
            return None
        picked, ok = QInputDialog.getItem(self, title, prompt, uids, 0, False)
        if not ok:
            return None
        return picked

    def prompt_set_next_scene_for_choice(self, idx: QModelIndex):
        if not idx.isValid():
            return
        picked = self._pick_scene_uid("Set Next Scene (Choice)")
        if picked is None:
            return
        row = idx.row()
        try:
            choice_id = str(self.choice_model._view_df.iloc[row]["choice_id"])
        except Exception:
            return
        self.save_current_sub_tables()
        self.df_choices.loc[self.df_choices["choice_id"] == choice_id, "next_scene_id"] = picked
        subset = self.df_choices[self.df_choices["scene_id"] == self.current_scene_uid].copy()
        self.choice_model.set_dataframe(self._choices_with_texts(subset))

    def prompt_set_next_scene_for_spot(self, idx: QModelIndex):
        if not idx.isValid():
            return
        picked = self._pick_scene_uid("Set Next Scene (Spot)")
        if picked is None:
            return
        row = idx.row()
        try:
            spot_id = str(self.spot_model._view_df.iloc[row]["spot_id"])
        except Exception:
            return
        self.save_current_sub_tables()
        self.df_spots.loc[self.df_spots["spot_id"] == spot_id, "next_scene_id"] = picked
        subset = self.df_spots[self.df_spots["scene_id"] == self.current_scene_uid].copy()
        self.spot_model.set_dataframe(self._spots_with_texts(subset))

    # -------------------------------------------------------------------------
    # Spot from selection + highlight preview
    # -------------------------------------------------------------------------
    def create_spot_from_text_selection(self):
        if not self.current_scene_uid:
            return
        cursor = self.edit_text.textCursor()
        sel = cursor.selectedText()
        sel = (sel or "").strip()
        if sel == "":
            QMessageBox.information(self, "No Selection", "Please select target text in the scene text first.")
            return

        self.save_current_sub_tables()

        existing = set(self.df_spots["spot_id"].astype(str)) if "spot_id" in self.df_spots.columns else set()
        base = f"{self.current_scene_uid}_SPOT_NEW"
        spot_id = self._unique_id(base, existing)

        sub = self.df_spots[self.df_spots["scene_id"] == self.current_scene_uid]
        try:
            max_order = int(pd.to_numeric(sub.get("disp_order", pd.Series([0])), errors="coerce").fillna(0).max())
        except Exception:
            max_order = 0

        new_row = {
            "spot_id": spot_id,
            "scene_id": self.current_scene_uid,
            "target_text": sel,
            "next_scene_id": "",
            "correct": 0,
            "disp_order": max_order + 1,
        }
        self.df_spots = pd.concat([self.df_spots, pd.DataFrame([new_row])], ignore_index=True)

        subset = self.df_spots[self.df_spots["scene_id"] == self.current_scene_uid].copy()
        self.spot_model.set_dataframe(self._spots_with_texts(subset))

        for r in range(self.spot_model.rowCount()):
            if str(self.spot_model._view_df.iloc[r]["spot_id"]) == spot_id:
                self.spot_table.selectRow(r)
                self.spot_table.setCurrentIndex(self.spot_model.index(r, 0))
                break

        self.update_spot_match_preview(sel)

    def on_spot_row_changed(self, current: QModelIndex, previous: QModelIndex):
        try:
            if not current.isValid():
                self.update_spot_match_preview("")
                return
            row = current.row()
            target = str(self.spot_model._view_df.iloc[row].get("target_text", ""))
            self.update_spot_match_preview(target)
        except Exception:
            self.update_spot_match_preview("")

    def update_spot_match_preview(self, target_text: str):
        text = self.edit_text.toPlainText()
        target = (target_text or "").strip()

        self.edit_text.setExtraSelections([])

        if target == "":
            self.lbl_spot_match.setText("")
            return

        matches = []
        start = 0
        while True:
            i = text.find(target, start)
            if i == -1:
                break
            matches.append((i, len(target)))
            start = i + len(target) if len(target) > 0 else i + 1

        if len(matches) == 0:
            self.lbl_spot_match.setText(f"'{target}' : 0 match (WARNING)")
        elif len(matches) == 1:
            self.lbl_spot_match.setText(f"'{target}' : 1 match")
        else:
            self.lbl_spot_match.setText(f"'{target}' : {len(matches)} matches (WARNING: ambiguous)")

        fmt = QTextCharFormat()
        fmt.setBackground(QColor(255, 255, 0, 120))

        extra = []
        doc = self.edit_text.document()
        for pos, ln in matches[:200]:
            sel = QTextEdit.ExtraSelection()
            c = QTextCursor(doc)
            c.setPosition(pos)
            c.setPosition(pos + ln, QTextCursor.KeepAnchor)
            sel.cursor = c
            sel.format = fmt
            extra.append(sel)
        self.edit_text.setExtraSelections(extra)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ScenarioEditor()
    window.show()
    sys.exit(app.exec())
