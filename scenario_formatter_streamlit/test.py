"""
SQLite Viewer アプリケーション

【概要】
このスクリプトは、Streamlitフレームワークを使用して作成された、ブラウザベースのSQLiteデータベース閲覧ツールです。
ユーザーはローカルのSQLiteファイル（.db, .sqlite, .sqlite3）をアップロードするだけで、
SQLを書くことなくテーブルの中身を確認、検索、フィルタリングすることができます。

【主な機能】
1. SQLiteファイルのアップロード機能
   - Streamlitのアップローダーを使用し、ブラウザからファイルをドラッグ＆ドロップ可能。
   - tempfileモジュールを使用し、アップロードされたバイナリデータを一時ファイルとして安全に処理。

2. データの読み込みとパフォーマンス最適化
   - @st.cache_data デコレータにより、同一ファイルの読み込み結果をキャッシュ。
   - 行数制限オプション（1,000行、10,000行、50,000行、全件）により、巨大なファイルによるブラウザクラッシュを防止。

3. インタラクティブなデータ表示 (AgGrid)
   - streamlit-aggridライブラリを採用し、Excelのような操作感を実現。
   - 各カラムに対するテキスト検索、ソート、列幅の自動調整機能。
   - ページネーション（ページ送り）機能の実装。

4. データのエクスポート
   - グリッド上でフィルタリングやソートを行った後の状態を、CSVファイルとしてダウンロード可能。

5. 状態管理
   - st.session_stateを使用し、再描画（Rerun）時にもロード済みのデータや接続状態を保持。

【依存ライブラリ】
- streamlit: Webアプリケーションの構築
- pandas: データの構造化と操作
- st_aggrid: 高機能なデータグリッドコンポーネント
- sqlite3: SQLiteデータベースへの接続
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import sqlite3
import tempfile
import os

# --- ライブラリのインポートと依存関係チェック ---
# st_aggridは高機能なデータグリッドを表示するための外部ライブラリです。
# インストールされていない場合に備えて try-except ブロックで囲み、
# エラー時には親切なインストール手順を表示するようにしています。
try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, JsCode
except ImportError:
    st.error("⚠️ ライブラリ 'streamlit-aggrid' が見つかりません。")
    st.info("以下のコマンドを実行してインストールしてください: \n\n `pip install streamlit-aggrid`")
    st.stop() # 実行をここで停止

# --- ページ基本設定 ---
# layout="wide" にすることで、ブラウザの横幅いっぱいを使ってデータを表示します。
st.set_page_config(page_title="SQLite Viewer", layout="wide", page_icon="🗄️")

# --- 1. データロードロジック (バックエンド処理) ---

# @st.cache_data デコレータ:
# Streamlitのキャッシュ機能です。同じファイル(file_info)と同じ設定(row_limit)で呼び出された場合、
# 関数の実行をスキップして前回の結果を返します。これにより、再描画時のパフォーマンスが劇的に向上します。
@st.cache_data(show_spinner=False)
def load_data(file_info, row_limit=1000):
    """
    SQLiteファイルを読み込み、Pandas DataFrameに変換する関数。
    
    Args:
        file_info (tuple): (ファイル名, ファイルのバイナリデータ) のタプル。
        row_limit (int): 読み込む最大行数。0の場合は全件読み込み。
        
    Returns:
        tuple: (データフレーム, データソース情報の文字列) または (エラー情報DF, エラーメッセージ)
    """
    # file_infoを展開 (タプルにすることでハッシュ化可能になり、キャッシュが効くようになります)
    file_name, file_bytes = file_info
    
    # SQLiteはファイルパスを必要とするため、アップロードされたバイナリデータを
    # 一時ファイル(tempfile)としてディスクに書き出します。
    try:
        # delete=Falseにして、接続中にファイルが消えないようにします（後で手動削除）
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_file:
            tmp_file.write(file_bytes)
            tmp_path = tmp_file.name
        
        # SQLiteデータベースへ接続
        conn = sqlite3.connect(tmp_path)
        cursor = conn.cursor()
        
        # データベース内のテーブル一覧を取得するSQL
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        # テーブルが存在しない場合のハンドリング
        if not tables:
            conn.close()
            os.remove(tmp_path)
            return pd.DataFrame({"Info": ["テーブルが見つかりませんでした"]}), "No Tables"
        
        # 現在の仕様では最初のテーブルのみを対象としています
        target_table = tables[0][0]
        
        # クエリ構築: ユーザー設定に基づいて読み込み行数を制限
        # 大量データの読み込みによるメモリ不足やフリーズを防ぐための処理です
        if row_limit > 0:
            query = f"SELECT * FROM {target_table} LIMIT {row_limit}"
            source_msg = f"Table: '{target_table}' (First {row_limit:,} rows)"
        else:
            # 全件取得モード
            query = f"SELECT * FROM {target_table}"
            source_msg = f"Table: '{target_table}' (All rows)"
        
        # Pandasの機能を使ってSQL結果をデータフレームに一括変換
        df = pd.read_sql_query(query, conn)
        
        # 接続を閉じ、一時ファイルを削除してクリーンアップ
        conn.close()
        os.remove(tmp_path) 
        
        return df, source_msg
        
    except Exception as e:
        # エラー発生時も一時ファイルが残らないようにクリーンアップを試みる
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)
        # エラー内容を画面に表示できるようにデータフレームに入れて返す
        return pd.DataFrame({"Error": [str(e)]}), "Read Error"


# --- 2. アプリケーションの状態管理 (Session State) ---
# Streamlitは操作のたびにスクリプト全体が再実行されるため、
# 変数の値を保持するために st.session_state を使用します。

if 'data' not in st.session_state:
    st.session_state.data = None # ロードしたデータフレーム
if 'file_name' not in st.session_state:
    st.session_state.file_name = None # ファイル名
if 'db_status' not in st.session_state:
    st.session_state.db_status = "未接続" # 接続ステータス表示用
if 'data_source' not in st.session_state:
    st.session_state.data_source = "" # 読み込んだテーブル情報など
if 'row_limit' not in st.session_state:
    st.session_state.row_limit = 1000 # 現在の行数制限設定

# --- 3. UI構築 (フロントエンド表示) ---

# カスタムCSSの注入: UIの微調整を行います
st.markdown("""
<style>
    .css-1d391kg {padding-top: 1rem;} /* コンテナの上部パディング調整 */
</style>
""", unsafe_allow_html=True)

# ヘッダーエリア: タイトルとステータス表示を2カラムで配置
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.title("🗄️ SQLite Viewer")
with col_h2:
    status_text = st.session_state.db_status
    if "接続中" in status_text:
        st.success(f"Status: {status_text}")
    else:
        st.warning(f"Status: {status_text}")

st.markdown("---")

# --- サイドバー（ファイル選択 & 設定） ---
with st.sidebar:
    st.header("📂 Explorer")
    
    # ファイルアップローダーウィジェット
    uploaded_file = st.file_uploader(
        "DBファイルを選択", 
        type=["db", "sqlite", "sqlite3"],
        help="200MB以上のファイルも読み込めます（設定により全件解析可能）"
    )

    st.markdown("### Settings")

    # 読み込み行数制限の設定（パフォーマンス制御用）
    # 大規模ファイルを開く際にブラウザがクラッシュしないよう、デフォルトで制限をかけます
    row_limit_option = st.selectbox(
        "読み込み行数制限",
        options=[1000, 10000, 50000, 0],
        format_func=lambda x: "全件 (メモリ注意)" if x == 0 else f"{x:,} 行 (推奨)" if x == 1000 else f"{x:,} 行",
        index=0,
        help="大きなファイルの場合、行数を制限することで動作が軽くなります。「全件」を選ぶと全てのデータを読み込みますが、ブラウザが重くなる可能性があります。"
    )

    st.markdown("### Actions")
    
    # ファイルがアップロードされている場合の処理
    if uploaded_file is not None:
        file_name = uploaded_file.name
        file_size_mb = uploaded_file.size / (1024 * 1024)
        
        st.caption(f"選択中: {file_name} ({file_size_mb:.2f} MB)")
        
        # 「ロード」ボタンが押された時の処理
        if st.button("データベースをロード", type="primary", use_container_width=True):
            with st.spinner("Processing..."):
                file_bytes = uploaded_file.getvalue()
                
                # ここでデータロード関数を呼び出し
                df, source_info = load_data(
                    (file_name, file_bytes), 
                    row_limit=row_limit_option
                )
                
                # 結果をセッションステートに保存（再描画後も保持するため）
                st.session_state.data = df
                st.session_state.file_name = file_name
                st.session_state.db_status = f"接続中"
                st.session_state.data_source = source_info
                st.session_state.row_limit = row_limit_option
                
                # アプリを再実行してメインエリアを更新
                st.rerun()
    else:
        st.info("上のボックスからファイルを選択してください。")

    st.divider()
    
    # Streamlitの設定に関するヘルプ情報
    with st.expander("ℹ️ 200MB以上のファイルを扱う場合"):
        st.markdown("""
        Streamlitのデフォルトアップロード制限は200MBです。
        変更するには `.streamlit/config.toml` に以下を記述：
        ```toml
        [server]
        maxUploadSize = 1000
        ```
        """)

# --- メインコンテンツエリア ---

# データがまだロードされていない場合の表示（プレースホルダー）
if st.session_state.data is None:
    st.container().markdown(
        """
        <div style="
            display: flex; 
            flex-direction: column; 
            align-items: center; 
            justify-content: center; 
            height: 400px; 
            border: 2px dashed #ccc; 
            border-radius: 10px; 
            color: #888;
            background-color: #f9f9f9;
        ">
            <h2 style="margin-bottom: 10px;">No Database Loaded</h2>
            <p>サイドバーから .db ファイルを選択してロードしてください。</p>
        </div>
        """,
        unsafe_allow_html=True
    )
else:
    # データが存在する場合の表示処理
    df = st.session_state.data
    
    # ツールバーエリア（検索ボックスとエクスポートボタン）
    col_search, col_export = st.columns([4, 1])
    
    # 1. クイック検索（簡易的なグローバルサーチ）
    with col_search:
        search_query = st.text_input("🔍 クイック検索 (全カラム対象)", placeholder="キーワードを入力してEnter... (例: error, 12345)")
        
    # Pandas側でのフィルタリングロジック
    # 入力されたキーワードが含まれる行を抽出します
    if search_query:
        mask = df.astype(str).apply(lambda x: x.str.contains(search_query, case=False, na=False)).any(axis=1)
        display_df = df[mask]
    else:
        display_df = df

    # 情報表示
    with col_search:
        st.caption(f"Source: {st.session_state.data_source} | Filtered: {len(display_df)} rows")
        if len(display_df) > 10000:
            st.warning("⚠️ データ量が多いため、操作が重くなる可能性があります。")

    # --- AgGrid (高機能テーブル) の設定 ---
    # DataFrameから初期設定を作成
    gb = GridOptionsBuilder.from_dataframe(display_df)
    
    # デフォルトのカラム設定:
    # ユーザーが列幅変更、フィルタ、ソートを行えるように設定
    gb.configure_default_column(
        resizable=True, 
        filterable=True,
        filter='agTextColumnFilter', # テキストフィルタを使用
        filterParams={
            'buttons': ['reset', 'apply'], # フィルタメニューに適用ボタンを表示
            'closeOnApply': True,
        },
        sortable=True, 
        floatingFilter=True, # ヘッダーの下に入力欄を表示
        editable=False,      # 編集不可（閲覧専用）
        minWidth=100
    )

    # カラム幅の自動計算ロジック
    # ヘッダーの文字数とデータの文字数を比較し、適切な幅を設定します
    for col in display_df.columns:
        header_len = len(col)
        
        if not display_df[col].empty:
            # 各列の最大文字数を取得
            max_data_len = display_df[col].astype(str).map(len).max()
        else:
            max_data_len = 0
            
        needed_len = max(header_len, max_data_len)
        calc_width = (needed_len * 12) + 30 # 文字数に応じたピクセル計算
        final_width = min(400, max(100, int(calc_width))) # 最小100px, 最大400pxに制限
        
        gb.configure_column(col, width=final_width)
    
    # 行選択を可能にする設定（チェックボックス表示）
    gb.configure_selection('multiple', use_checkbox=True)
    
    # ページネーション（ページ送り）の設定
    # データ量が多い場合は1ページあたりの表示数を減らして負荷を下げます
    page_size = 50
    if len(display_df) > 10000:
        page_size = 20
        
    gb.configure_pagination(paginationAutoPageSize=False, paginationPageSize=page_size)
    
    gridOptions = gb.build()

    # グリッドの高さ設定
    grid_height = 600
    
    # AgGridコンポーネントの描画
    grid_response = AgGrid(
        display_df,
        gridOptions=gridOptions,
        enable_enterprise_modules=False, # エンタープライズ機能は無効
        height=grid_height,
        width='100%',
        theme='alpine', # グリッドのテーマ
        update_mode=GridUpdateMode.MODEL_CHANGED,
        data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True # JS実行許可（必要に応じて）
    )

    # --- エクスポート機能 ---
    # グリッド上でフィルタリングやソートされた後のデータを取得
    filtered_df = grid_response['data']
    
    with col_export:
        # レイアウト調整用の空行
        st.write("") 
        st.write("") 
        
        # データがある場合のみダウンロードボタンを表示
        if len(filtered_df) > 0:
            csv = filtered_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="⬇️ CSV出力",
                data=csv,
                file_name=f"export_{st.session_state.file_name}_{int(time.time())}.csv",
                mime="text/csv",
                use_container_width=True
            )
    
    st.write(f"表示件数: {len(filtered_df)} 行")

# フッター表示
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: grey; font-size: 0.8em;'>SQLite Viewer v4.0 (Real Data Only)</div>", 
    unsafe_allow_html=True
)