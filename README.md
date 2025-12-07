# Game Asset Extraction & Dataset Tools

ゲームアセット（シナリオテキスト、音声、立ち絵）を解析・統合し、データセット化（Style-Bert-VITS2学習用など）や閲覧を行うためのPythonツール群です。

## 📦 機能一覧

| ファイル名 | 機能 |
| --- | --- |
| `import_text_to_db.py` | シナリオテキストを解析し、SQLiteデータベース(`scenario_data.db`)を作成します。 |
| `voice_extractor_gui.py` | データベースを元に音声を検索・試聴・タグ付けし、データセット(esd.list)を出力します。 |
| `sprite_assembler_normal.py` | 立ち絵パーツとアトラス画像を組み合わせて保存するGUIツールです。 |
| `sprite_assembler_witch.py` | メッシュ変形（頂点データ）を含む複雑な立ち絵を復元・結合するバッチスクリプトです。 |

## 🛠 前提条件 (Prerequisites)

* **Python 3.8+**
* 以下のライブラリが必要です。

## ⚙️ インストール (Installation)

仮想環境（venv）の使用を推奨します。

```bash
# 1. 仮想環境の作成 (Windows)
python -m venv venv
.\venv\Scripts\activate

# 1. 仮想環境の作成 (Mac/Linux)
# python3 -m venv venv
# source venv/bin/activate

# 2. 依存ライブラリのインストール
pip install pygame Pillow numpy
