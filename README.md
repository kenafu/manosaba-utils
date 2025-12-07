# Setup & Usage Guide
このリポジトリには、ゲームアセット（テキスト、音声、立ち絵）を解析・統合し、データセット化（Style-Bert-VITS2学習用など）や閲覧を行うためのツール群が含まれています。

📋 Prerequisites (前提条件)
Python 3.8+

以下のライブラリが必要です。

🛠 Installation
推奨: 仮想環境（venv）を作成してからインストールを行ってください。

Bash

# 仮想環境の作成と有効化 (Windows)
python -m venv venv
.\venv\Scripts\activate

# 必要なライブラリの一括インストール
pip install pygame Pillow numpy
Note: tkinter と sqlite3 はPython標準ライブラリに含まれていますが、Linux環境などで含まれていない場合は別途インストール（例: sudo apt-get install python3-tk）が必要になる場合があります。

🚀 Usage Workflow
各ツールの使用手順は以下の通りです。

1. テキストデータのデータベース化 (import_text_to_db.py)
シナリオテキスト（.bytes 形式などを想定）を読み込み、SQLiteデータベース (scenario_data.db) を構築します。音声抽出ツールを使用する前に必ず実行してください。

import_text_to_db.py をテキストエディタで開きます。

TARGET_DIR 変数を、対象のテキストファイルが格納されているディレクトリパスに書き換えてください。

Python

TARGET_DIR = r'C:\Path\To\Your\GameAssets\text' 
スクリプトを実行します。

Bash

python import_text_to_db.py
成功すると、同階層に scenario_data.db が作成されます。

2. 音声データの選別と抽出 (voice_extractor_gui.py)
作成されたデータベースをもとに、音声データの検索・試聴・タグ付け・データセット出力を行います。

準備: 音声ファイル（.ogg, .wav 等）が入ったフォルダを用意してください（デフォルトでは ./voice_assets を参照します）。

スクリプトを実行します。

Bash

python voice_extractor_gui.py
GUI操作:

Search Filters: キャラクター名やテキストで絞り込みます。

Voice Settings: 学習除外設定 (Exclude) やスタイル (Style) を指定し、DBに保存できます。

Export: フィルタリングされた結果を esd.list 形式（Style-Bert-VITS2互換）で一括出力します。

3. 立ち絵アセンブラー (GUI版) (sprite_assembler_normal.py)
分割されたパーツ（アトラス画像 + JSON定義）を組み合わせて立ち絵を構築するGUIツールです。

スクリプトを実行します。

Bash

python sprite_assembler_normal.py
GUI操作:

「JSONフォルダを選択」から、スプライト定義JSONがあるフォルダを読み込みます。

「アトラス画像を選択」から、ベースとなるテクスチャ画像を読み込みます。

左側のレイヤー操作パネルでパーツを選択・座標調整を行い、「画像を保存」で書き出します。

4. 立ち絵メッシュ復元 (バッチ版) (sprite_assembler_witch.py)
Naninovel形式などの、メッシュ変形（頂点データとUV情報を含むJSON）を利用した複雑な立ち絵を復元・結合するバッチスクリプトです。

sprite_assembler_witch.py をテキストエディタで開きます。

以下のパス設定をお使いの環境に合わせて修正してください。

Python

# ターゲットフォルダ（キャラクターごとのフォルダなど）が格納されているルート
BASE_DIR = r"C:\Path\To\GameData\StreamingAssets\characters"

# 各ターゲットフォルダ内での 相対パス
REL_PNG_PATH = r"Assets\Texture2D"
REL_JSON_PATH = r"Assets\Textures\Json"
スクリプトを実行します。

Bash

python sprite_assembler_witch.py
./output フォルダにレンダリングされた画像が保存されます。

⚠️ Troubleshooting
Database not found: voice_extractor_gui.py を起動してエラーが出る場合は、先に import_text_to_db.py を実行して scenario_data.db を生成してください。

FileNotFoundError: 各スクリプト内のパス設定（TARGET_DIR や BASE_DIR）が正しいか確認してください。Windowsのパスを記述する場合、 r"C:\Path\..." のように r を付けることを推奨します。
