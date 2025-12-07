import json
import base64
import math
import os
import glob
import numpy as np
from PIL import Image

# ==== ここを環境に合わせて書き換えてください ==================
# 例：
# data/targetA/json
# data/targetA/png
# data/targetB/json
# data/targetB/png
#
# のような構成を想定しています。

BASE_DIR = r"E:\SteamLibrary\steamapps\common\manosaba_game\manosaba_Data\StreamingAssets\aa\StandaloneWindows64\naninovel-characters_assets_naninovel\characters\block" # targetA, targetB... が入っているルート
REL_PNG_PATH = r"Assets\Texture2D" # 各 target からの PNG ディレクトリの相対パス
REL_JSON_PATH  = r"Assets\#WitchTrials\Textures\Naninovel\Characters\DicedSpriteAtlases" # 各 target からの JSON ディレクトリの相対パス

OUTPUT_ROOT = r"./output" # 出力のルートディレクトリ
# ==========================================================


def load_sprite_mesh(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        jd = json.load(f)

    rd = jd["m_RD"]
    vdata = rd["m_VertexData"]

    vertex_count = vdata["m_VertexCount"]

    floats = np.frombuffer(
        base64.b64decode(vdata["m_Data"]), dtype="<f4"
    )

    # 先頭が position(x,y,z)、後ろが uv(u,v) という前提
    pos = floats[: vertex_count * 3].reshape(vertex_count, 3)
    uv = floats[vertex_count * 3:].reshape(vertex_count, 2)

    indices = np.frombuffer(
        base64.b64decode(rd["m_IndexBuffer"]), dtype="<u2"
    )

    pixels_to_units = jd.get("m_PixelsToUnits", 100)

    return pos, uv, indices, pixels_to_units


def render_mesh_subpixel(pos, uv, indices, texture, pixels_to_units=100):
    """三角形ラスタライズ + bilinear テクスチャサンプリング"""

    tex_np = np.array(texture).astype(np.float32)
    tex_h, tex_w = tex_np.shape[:2]

    # 出力範囲
    minx, maxx = pos[:, 0].min(), pos[:, 0].max()
    miny, maxy = pos[:, 1].min(), pos[:, 1].max()

    scale = float(pixels_to_units)
    out_w = int(math.ceil((maxx - minx) * scale))
    out_h = int(math.ceil((maxy - miny) * scale))

    out = np.zeros((out_h, out_w, 4), dtype=np.float32)

    # 頂点位置 → ピクセル座標
    vx = (pos[:, 0] - minx) * scale
    vy = (maxy - pos[:, 1]) * scale  # 上下反転

    tris = indices.reshape(-1, 3)

    for t in tris:
        i0, i1, i2 = t

        x0, y0 = vx[i0], vy[i0]
        x1, y1 = vx[i1], vy[i1]
        x2, y2 = vx[i2], vy[i2]

        # --- 1px 拡張バウンディングボックス（隙間防止） ---
        xmin = max(int(math.floor(min(x0, x1, x2))) - 1, 0)
        xmax = min(int(math.ceil(max(x0, x1, x2))) + 1, out_w - 1)
        ymin = max(int(math.floor(min(y0, y1, y2))) - 1, 0)
        ymax = min(int(math.ceil(max(y0, y1, y2))) + 1, out_h - 1)

        if xmax < xmin or ymax < ymin:
            continue

        xs = np.arange(xmin, xmax + 1, dtype=np.float32)
        ys = np.arange(ymin, ymax + 1, dtype=np.float32)
        X, Y = np.meshgrid(xs, ys)  # (h, w)

        denom = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(denom) < 1e-6:
            continue

        # barycentric
        w1 = ((y1 - y2) * (X - x2) + (x2 - x1) * (Y - y2)) / denom
        w2 = ((y2 - y0) * (X - x2) + (x0 - x2) * (Y - y2)) / denom
        w3 = 1.0 - w1 - w2

        mask = (w1 >= -0.01) & (w2 >= -0.01) & (w3 >= -0.01)
        if not mask.any():
            continue

        # UV 補間
        uv0, uv1, uv2 = uv[i0], uv[i1], uv[i2]
        uvx = w1 * uv0[0] + w2 * uv1[0] + w3 * uv2[0]
        uvy = w1 * uv0[1] + w2 * uv1[1] + w3 * uv2[1]

        # --- subpixel / bilinear サンプリング ---
        sx_f = uvx * (tex_w - 1)
        sy_f = (1.0 - uvy) * (tex_h - 1)

        x0t = np.floor(sx_f).astype(np.int32)
        y0t = np.floor(sy_f).astype(np.int32)
        x1t = np.clip(x0t + 1, 0, tex_w - 1)
        y1t = np.clip(y0t + 1, 0, tex_h - 1)

        wx = sx_f - x0t
        wy = sy_f - y0t

        c00 = tex_np[y0t, x0t]
        c10 = tex_np[y0t, x1t]
        c01 = tex_np[y1t, x0t]
        c11 = tex_np[y1t, x1t]

        c0 = c00 * (1 - wx)[..., None] + c10 * wx[..., None]
        c1 = c01 * (1 - wx)[..., None] + c11 * wx[..., None]
        c = c0 * (1 - wy)[..., None] + c1 * wy[..., None]

        ox = X.astype(np.int32)
        oy = Y.astype(np.int32)
        out[oy[mask], ox[mask]] = c[mask]

    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def process_target(target_root):
    """1つの target (例: data/targetA) を処理"""

    target_name = os.path.basename(target_root.rstrip("/\\"))

    json_dir = os.path.join(target_root, REL_JSON_PATH)
    png_dir = os.path.join(target_root, REL_PNG_PATH)

    if not os.path.isdir(json_dir):
        raise FileNotFoundError(f"JSON ディレクトリが見つかりません: {json_dir}")
    if not os.path.isdir(png_dir):
        raise FileNotFoundError(f"PNG ディレクトリが見つかりません: {png_dir}")

    # PNG は target 内で 1枚だけ使用
    png_files = sorted(
        f for f in os.listdir(png_dir)
        if f.lower().endswith(".png")
    )
    if not png_files:
        raise FileNotFoundError(f"PNG が見つかりません: {png_dir}")

    png_file = png_files[0]
    png_path = os.path.join(png_dir, png_file)
    png_base = os.path.splitext(png_file)[0]

    print(f"[{target_name}] 使用するテクスチャ: {png_path}")
    texture = Image.open(png_path).convert("RGBA")

    # JSON は target 内のすべてを処理
    json_paths = sorted(glob.glob(os.path.join(json_dir, "*.json")))
    if not json_paths:
        raise FileNotFoundError(f"JSON が見つかりません: {json_dir}")

    # 出力先: OUTPUT_ROOT/targetA のように target ごとに作成
    target_out_dir = os.path.join(OUTPUT_ROOT, target_name)
    os.makedirs(target_out_dir, exist_ok=True)

    for json_path in json_paths:
        json_name = os.path.basename(json_path)
        json_base = os.path.splitext(json_name)[0]

        print(f"[{target_name}] 処理中: {json_path}")

        pos, uv, indices, ppu = load_sprite_mesh(json_path)
        img = render_mesh_subpixel(pos, uv, indices, texture, pixels_to_units=ppu)

        # 出力ファイル名: {png名}_{json名}.png
        out_name = f"{target_name}_{json_base}.png"
        out_path = os.path.join(target_out_dir, out_name)

        img.save(out_path)
        print(f"  -> saved: {out_path} {img.size}")


def main():
    os.makedirs(OUTPUT_ROOT, exist_ok=True)

    # BASE_DIR 配下のディレクトリを targetA, targetB... とみなして順次処理
    for entry in sorted(os.scandir(BASE_DIR), key=lambda e: e.name):
        if not entry.is_dir():
            continue
        target_root = entry.path
        print(f"=== Target: {target_root} ===")
        process_target(target_root)


if __name__ == "__main__":
    main()