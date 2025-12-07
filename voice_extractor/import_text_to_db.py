# 設定
import os
import glob
import re
import sqlite3

TARGET_DIR = r'F:\05_mytool\manosaba_png\text'  # 対象のテキストファイルがあるディレクトリ

DB_NAME = 'scenario_data.db'
FILE_EXTENSION = '*.bytes'  # 対象ファイルの拡張子（.txtなど必要に応じて変更）

def create_database():
    """データベースとテーブルを作成する"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # テーブル作成
    # ADVカラムをTEXT型に変更（Adv01, Bad01, Trial01などを区別して保存するため）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS scenario_text (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        uid TEXT NOT NULL,
        act INTEGER DEFAULT 0,
        chapter INTEGER DEFAULT 0,
        adv TEXT,
        source_file TEXT,
        actor TEXT,
        voice_file_name TEXT,
        text TEXT,
        data TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        
        CONSTRAINT uq_uid UNIQUE (uid)
    )
    ''')
    
    # パフォーマンス戦略: よく検索されるパターンにインデックスを作成
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_uid ON scenario_text(uid)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_actor ON scenario_text(actor)')
    # 章・ADV単位でのデータ取得を高速化するための複合インデックス
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_act_chapter_adv ON scenario_text(act, chapter, adv)')
    
    conn.commit()
    return conn

def parse_filename_metadata(filename):
    """ファイル名からAct, Chapter, Adv(文字列)を抽出する"""
    basename = os.path.basename(filename)
    
    act_match = re.search(r'Act(\d+)', basename, re.IGNORECASE)
    chapter_match = re.search(r'Chapter(\d+)', basename, re.IGNORECASE)
    
    # AdvまたはBadまたはTrialなどで始まる識別子を文字列として抽出
    # 例: Act01_Chapter01_Adv02.bytes -> Adv02
    # 例: Act01_Chapter01_BadEnd01.bytes -> BadEnd01
    # 例: Act01_Chapter01_Trial01.bytes -> Trial01
    # アンダースコア(_)やドット(.)の直前までを取得
    adv_match = re.search(r'((?:Adv|Bad|Trial)[^_.]+)', basename, re.IGNORECASE)
    
    act = int(act_match.group(1)) if act_match else 0
    chapter = int(chapter_match.group(1)) if chapter_match else 0
    # そのまま文字列として返す（マッチしなければNone）
    adv = adv_match.group(1) if adv_match else None
    
    return act, chapter, adv

def parse_and_insert(conn, filepath):
    """ファイルを解析してDBに挿入する"""
    cursor = conn.cursor()
    act, chapter, adv = parse_filename_metadata(filepath)
    filename_only = os.path.basename(filepath)
    
    print(f"Processing: {filename_only} (Act: {act}, Chapter: {chapter}, Adv: {adv})")

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.splitlines()
    
    current_block = {
        'uid': None,
        'actor': None,
        'voice': None,
        'text_lines': [],
        'raw_lines': []
    }
    
    def save_block(block):
        """ブロックの保存処理"""
        if block['uid']:
            full_text = "\n".join(block['text_lines']).strip()
            raw_data = "\n".join(block['raw_lines']).strip()
            
            # UPSERT処理
            cursor.execute('''
            INSERT OR REPLACE INTO scenario_text 
            (uid, act, chapter, adv, source_file, actor, voice_file_name, text, data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                block['uid'],
                act,
                chapter,
                adv,
                filename_only,
                block['actor'],
                block['voice'],
                full_text,
                raw_data
            ))

    # 行ごとの解析ループ
    for line in lines:
        line_stripped = line.strip()
        
        # 新しいUIDブロックの開始判定
        if line_stripped.startswith('#'):
            save_block(current_block)
            
            # ブロック初期化
            current_block = {
                'uid': line_stripped.lstrip('#').strip(),
                'actor': None,
                'voice': None,
                'text_lines': [],
                'raw_lines': [line]
            }
            continue

        if current_block['uid'] is None:
            continue

        current_block['raw_lines'].append(line)

        # アクター行・メタデータ行の解析
        # 行頭が '; >' または ';>' で始まる場合のみメタデータとして扱う
        if re.match(r'^;\s*>', line_stripped):
            
            # ケース: システムアクター名とボイス (例: ; > Unknown: |#0101Adv02_Unknown001|)
            # 表示名行には ':' が含まれないことが多いと仮定し、':' を持つものをアクター定義とする
            actor_match = re.search(r'>\s*([^:|＠@]+?)\s*:', line_stripped)
            voice_match = re.search(r'\|(.+?)\|', line_stripped)
            
            if actor_match:
                current_block['actor'] = actor_match.group(1).strip()
            
            if voice_match:
                # パイプ内を取得し、先頭の '#' を除去
                raw_voice = voice_match.group(1).strip()
                current_block['voice'] = raw_voice.lstrip('#')
                
        # テキストの解析
        # ; で始まるが、> を含まない行
        elif line_stripped.startswith(';'):
            text_content = line_stripped.lstrip(';').strip()
            if text_content:
                current_block['text_lines'].append(text_content)

    # 最後のブロックを保存
    save_block(current_block)
    conn.commit()

def main():
    # テーブル構造が変わったため、古いDBがある場合は削除するか確認を促すメッセージを出しても良いですが、
    # ここでは既存DBに対して IF NOT EXISTS でテーブルを作るため、
    # カラム不足のエラーが出ないよう「古いDBを削除してください」と案内するのが安全です。
    if os.path.exists(DB_NAME):
        print(f"Note: If the schema of '{DB_NAME}' is old, please delete the file first.")

    conn = create_database()
    
    # 修正: サブディレクトリも再帰的に検索するように変更
    # '**' パターンと recursive=True を使用
    search_path = os.path.join(TARGET_DIR, '**', FILE_EXTENSION)
    print(f"Searching for files in: {search_path}")
    
    files = glob.glob(search_path, recursive=True)
    
    if not files:
        print(f"No files found matching {FILE_EXTENSION} in {TARGET_DIR} (recursive)")
        return

    print(f"Found {len(files)} files.")
    for filepath in files:
        try:
            parse_and_insert(conn, filepath)
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
            
    conn.close()
    print("Import completed.")

if __name__ == '__main__':
    main()