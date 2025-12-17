import sys
import sqlite3
import uuid
import pandas as pd
from datetime import datetime
from enum import Enum

try:
    from PySide6.QtWidgets import (QApplication, QMainWindow, QTableView, QVBoxLayout, 
                                   QHBoxLayout, QWidget, QHeaderView, QToolBar, QFileDialog, 
                                   QMessageBox, QAbstractItemView, QMenu, QSplitter,
                                   QLineEdit, QLabel, QFormLayout, QComboBox, QPlainTextEdit,
                                   QPushButton, QGroupBox, QSpacerItem, QSizePolicy, QDialog,
                                   QDialogButtonBox, QVBoxLayout)
    from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal, Slot, QTimer, QSize, QEvent, QRect
    from PySide6.QtGui import QAction, QColor, QKeySequence, QIcon, QFont
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
    {'id': 'axis', 'label': 'Axis', 'readonly': False, 'width': 100},
    {'id': 'next_scene_id', 'label': 'Next Scene', 'readonly': False, 'width': 120},
    {'id': 'correct', 'label': 'Correct', 'readonly': False, 'width': 60}, # Added correct column
    {'id': 'disp_order', 'label': 'Order', 'readonly': False, 'width': 60},
]

# カラム定義: Click Spot (scenario_click_spot)
COLS_SPOT = [
    {'id': 'spot_id', 'label': 'ID', 'readonly': True, 'width': 80},
    {'id': 'target_text', 'label': 'Target Text', 'readonly': False, 'width': 200},
    {'id': 'next_scene_id', 'label': 'Next Scene', 'readonly': False, 'width': 120},
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
        self.edit_text.textChanged.connect(self.on_scene_text_changed)

        form_layout.addRow("Scene ID:", self.edit_uid)
        form_layout.addRow("Type:", self.combo_type)
        form_layout.addRow("Next Scene:", self.edit_next)
        form_layout.addRow("Text:", self.edit_text)
        
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
        self.spot_table.verticalHeader().setDefaultSectionSize(24)
        v_spots.addWidget(self.spot_table)
        
        right_layout.addWidget(grp_spots)
        
        splitter.addWidget(right_widget)
        splitter.setStretchFactor(1, 2)

        # Flag to prevent loop
        self.updating_ui = False

    def setup_scene_filters(self):
        """シーンリストのカラム下フィルタを設定"""
        # マージン設定はFilterTableViewのupdateGeometriesで行うため、ここでは行わない
        
        for w in self.scene_filter_widgets.values():
            w.deleteLater()
        self.scene_filter_widgets = {}

        for col_def in COLS_SCENE:
            col_id = col_def['id']
            line_edit = QLineEdit(self.scene_table)
            line_edit.setPlaceholderText(f"Filter {col_def['label']}...")
            line_edit.setStyleSheet("""
                QLineEdit { 
                    background-color: #2a2a2a; 
                    color: #fff; 
                    border: 1px solid #555; 
                    padding: 1px 4px; 
                    border-radius: 0px;
                    font-size: 11px;
                }
                QLineEdit:focus { border: 1px solid #4a90e2; }
            """)
            line_edit.show()
            line_edit.textChanged.connect(lambda text, cid=col_id: self.on_column_filter_change(cid, text))
            self.scene_filter_widgets[col_id] = line_edit

        self.scene_table.installEventFilter(self)
        self.scene_table.horizontalHeader().sectionResized.connect(self.update_filter_positions)
        self.scene_table.horizontalHeader().sectionMoved.connect(self.update_filter_positions)
        self.scene_table.horizontalScrollBar().valueChanged.connect(self.update_filter_positions)
        
        QTimer.singleShot(0, self.update_filter_positions)

    def eventFilter(self, source, event):
        if source == self.scene_table:
            if event.type() == QEvent.Resize:
                self.update_filter_positions()
            elif event.type() == QEvent.Show:
                self.update_filter_positions()
        return super().eventFilter(source, event)

    def update_filter_positions(self):
        # ウィジェットの位置合わせ
        header = self.scene_table.horizontalHeader()
        if not header:
            return

        # フィルタ行は「水平ヘッダー直下」に固定する
        # header.geometry() が取れるので、それを基準にする（初期タイミングの height=0 問題にも強い）
        hg = header.geometry()
        header_bottom = hg.y() + hg.height()
        if header_bottom <= 0:
            header_bottom = header.sizeHint().height()

        y_pos = int(header_bottom + 1)

        v_header = self.scene_table.verticalHeader()
        v_header_width = v_header.width() if v_header and v_header.isVisible() else 0

        base_x = int(v_header_width + self.scene_table.frameWidth())

        for i, col_def in enumerate(COLS_SCENE):
            col_id = col_def['id']
            if col_id not in self.scene_filter_widgets:
                continue

            widget = self.scene_filter_widgets[col_id]

            if header.isSectionHidden(i):
                widget.hide()
                continue

            x_viewport = self.scene_table.columnViewportPosition(i)
            width = self.scene_table.columnWidth(i)

            x_pos = int(base_x + x_viewport)

            # 画面外なら隠す
            if x_pos + width < 0 or x_pos > self.scene_table.width():
                widget.hide()
            else:
                widget.show()
                widget.setGeometry(x_pos, y_pos, int(width), int(self.filter_row_height - 1))
                widget.raise_()

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

        df = self.df_scenes
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
        for index, row in self.df_scenes.iterrows():
            uid = str(row['uid'])
            
            if "Choice" in uid and "trial" not in uid:
                # 選択肢行のTypeを 'choice_text' に更新
                is_updated = False
                if self.df_scenes.at[index, 'scene_type'] != 'choice_text':
                    self.df_scenes.at[index, 'scene_type'] = 'choice_text'
                    is_updated = True
                
                # 選択肢テキストの next_scene_uid を空にする
                if self.df_scenes.at[index, 'next_scene_uid'] != '':
                    self.df_scenes.at[index, 'next_scene_uid'] = ''
                    is_updated = True
                
                if is_updated:
                    updates_scene_count += 1

                if last_non_choice_uid:
                    # 親シーンのTypeを 'branch' に更新
                    if last_non_choice_idx is not None:
                        is_updated_parent = False
                        if self.df_scenes.at[last_non_choice_idx, 'scene_type'] != 'branch':
                            self.df_scenes.at[last_non_choice_idx, 'scene_type'] = 'branch'
                            is_updated_parent = True
                        
                        # 親シーンの next_scene_uid を空にする
                        if self.df_scenes.at[last_non_choice_idx, 'next_scene_uid'] != '':
                            self.df_scenes.at[last_non_choice_idx, 'next_scene_uid'] = ''
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
                self.choice_model.set_dataframe(choices_subset)
            
            QMessageBox.information(self, "Success", f"{count} choices generated. {updates_scene_count} scenes updated.")
        elif updates_scene_count > 0:
            QMessageBox.information(self, "Success", f"No new choices found, but {updates_scene_count} scenes updated.")
        else:
            QMessageBox.information(self, "Result", "No changes made.")

        # シーン情報の変更もUIに反映
        if updates_scene_count > 0:
            self.scene_model.set_dataframe(self.df_scenes)
            self.scene_model.reapply_filters()
            # 選択中の行のプロパティも更新する
            if self.current_scene_uid:
                 self.on_scene_selected(self.scene_table.currentIndex(), QModelIndex())

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
            combined_df = pd.concat([self.df_scenes, new_df], ignore_index=True)
            combined_df = combined_df.drop_duplicates(subset=['uid'], keep='last').reset_index(drop=True)
            
            self.df_scenes = combined_df
            
            # UI更新
            self.scene_model.set_dataframe(self.df_scenes)
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
        
        self.df_scenes = pd.read_sql_query("SELECT * FROM scenario_text", conn)
        for col in ['scene_type', 'next_scene_uid']:
            if col not in self.df_scenes.columns:
                self.df_scenes[col] = ''
        self.df_scenes['scene_type'].replace('', 'linear', inplace=True)
        self.df_scenes.fillna('', inplace=True)

        try:
            self.df_choices = pd.read_sql_query("SELECT * FROM scenario_choice", conn)
        except:
            self.df_choices = pd.DataFrame(columns=[c['id'] for c in COLS_CHOICE] + ['scene_id'])

        try:
            self.df_spots = pd.read_sql_query("SELECT * FROM scenario_click_spot", conn)
        except:
            self.df_spots = pd.DataFrame(columns=[c['id'] for c in COLS_SPOT] + ['scene_id'])
            
        conn.close()
        
        self.scene_model.set_dataframe(self.df_scenes)
        QTimer.singleShot(100, self.update_filter_positions)

    def save_to_db(self):
        if not self.current_db_path:
            self.create_new_db()
            if not self.current_db_path: return
        
        self.save_current_sub_tables()
        
        conn = sqlite3.connect(self.current_db_path)
        try:
            self.scene_model.df.to_sql("scenario_text", conn, if_exists="replace", index=False)
            self.df_choices.to_sql("scenario_choice", conn, if_exists="replace", index=False)
            self.df_spots.to_sql("scenario_click_spot", conn, if_exists="replace", index=False)
            
            self.statusBar().showMessage(f"Saved successfully at {datetime.now().strftime('%H:%M:%S')}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))
        finally:
            conn.close()

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
        self.choice_model.set_dataframe(choices_subset)
        
        spots_subset = self.df_spots[self.df_spots['scene_id'] == self.current_scene_uid].copy()
        self.spot_model.set_dataframe(spots_subset)
        
        self.updating_ui = False

    def save_current_sub_tables(self):
        if not self.current_scene_uid: return
        
        current_choices = self.choice_model.get_dataframe()
        other_choices = self.df_choices[self.df_choices['scene_id'] != self.current_scene_uid]
        if not current_choices.empty:
            current_choices['scene_id'] = self.current_scene_uid
        self.df_choices = pd.concat([other_choices, current_choices], ignore_index=True)
        
        current_spots = self.spot_model.get_dataframe()
        other_spots = self.df_spots[self.df_spots['scene_id'] != self.current_scene_uid]
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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ScenarioEditor()
    window.show()
    sys.exit(app.exec())