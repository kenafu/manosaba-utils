import os
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk

class SpriteAssemblerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("立ち絵アセンブラー (スクロール対応版)")
        self.root.geometry("1650x1280")

        # 状態変数
        self.atlas_image = None
        self.sprite_data_db = {} 
        self.layer_vars = [] 
        self.preview_image_tk = None
        self.generated_image = None

        # GUIの構築
        self._setup_ui()

    def _setup_ui(self):
        # レイアウト: 左側（操作パネル）、右側（プレビュー）
        # tk.PanedWindow -> ttk.PanedWindow (前回の修正を維持)
        paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(paned_window, padding="10")
        right_frame = ttk.Frame(paned_window, padding="0", relief="sunken") # paddingを0にしてスクロールバーを端に寄せる
        
        paned_window.add(left_frame, weight=1)
        paned_window.add(right_frame, weight=3)

        # --- 左側: 操作パネル ---
        self._setup_left_panel(left_frame)

        # --- 右側: プレビューエリア (スクロールバー付き) ---
        self._setup_right_panel(right_frame)

    def _setup_left_panel(self, parent):
        # 1. ファイル読み込み
        file_frame = ttk.LabelFrame(parent, text="1. リソース読み込み", padding="5")
        file_frame.pack(fill=tk.X, pady=5)

        ttk.Button(file_frame, text="JSONフォルダを選択", command=self.load_json_dir).pack(fill=tk.X, pady=2)
        self.lbl_json_count = ttk.Label(file_frame, text="JSON: 未読み込み")
        self.lbl_json_count.pack(anchor="w")

        ttk.Button(file_frame, text="アトラス画像を選択", command=self.load_atlas_image).pack(fill=tk.X, pady=2)
        self.lbl_atlas_status = ttk.Label(file_frame, text="画像: 未読み込み")
        self.lbl_atlas_status.pack(anchor="w")

        # 2. レイヤー設定
        layer_frame = ttk.LabelFrame(parent, text="2. パーツ構成 (奥 -> 手前)", padding="5")
        layer_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        canvas = tk.Canvas(layer_frame)
        scrollbar = ttk.Scrollbar(layer_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # レイヤーコントロール作成
        self.layer_controls = []
        for i in range(10):
            self._create_layer_control(scrollable_frame, i)

        # 3. 保存ボタン
        btn_frame = ttk.Frame(parent, padding="5")
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="画像を保存", command=self.save_image).pack(fill=tk.X, ipady=5)

    def _setup_right_panel(self, parent):
        # Gridレイアウトを使ってCanvasとスクロールバーを配置
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # プレビュー用キャンバス
        self.canvas_preview = tk.Canvas(parent, bg="gray")
        self.canvas_preview.grid(row=0, column=0, sticky="nsew")

        # スクロールバー (縦)
        v_bar = ttk.Scrollbar(parent, orient="vertical", command=self.canvas_preview.yview)
        v_bar.grid(row=0, column=1, sticky="ns")

        # スクロールバー (横)
        h_bar = ttk.Scrollbar(parent, orient="horizontal", command=self.canvas_preview.xview)
        h_bar.grid(row=1, column=0, sticky="ew")

        # キャンバスとスクロールバーの紐づけ
        self.canvas_preview.configure(yscrollcommand=v_bar.set, xscrollcommand=h_bar.set)

        # --- おまけ: マウスドラッグで移動機能 ---
        self.canvas_preview.bind("<ButtonPress-1>", self.on_drag_start)
        self.canvas_preview.bind("<B1-Motion>", self.on_drag_move)

    def on_drag_start(self, event):
        self.canvas_preview.scan_mark(event.x, event.y)

    def on_drag_move(self, event):
        self.canvas_preview.scan_dragto(event.x, event.y, gain=1)

    def _create_layer_control(self, parent, index):
        frame = ttk.Frame(parent, padding="2", relief="groove")
        frame.pack(fill=tk.X, pady=2)

        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X)
        ttk.Label(row1, text=f"Layer {index+1}").pack(side=tk.LEFT)
        
        cb_var = tk.StringVar()
        cb = ttk.Combobox(row1, textvariable=cb_var, state="readonly")
        cb.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=5)
        cb.bind("<<ComboboxSelected>>", self.update_preview)

        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=2)
        
        ttk.Label(row2, text="X:").pack(side=tk.LEFT)
        x_var = tk.DoubleVar(value=0)
        x_spin = ttk.Spinbox(row2, from_=-2000, to=2000, textvariable=x_var, width=5, command=self.update_preview)
        x_spin.bind("<Return>", self.update_preview)
        x_spin.pack(side=tk.LEFT, padx=2)

        ttk.Label(row2, text="Y:").pack(side=tk.LEFT)
        y_var = tk.DoubleVar(value=0)
        y_spin = ttk.Spinbox(row2, from_=-2000, to=2000, textvariable=y_var, width=5, command=self.update_preview)
        y_spin.bind("<Return>", self.update_preview)
        y_spin.pack(side=tk.LEFT, padx=2)

        ttk.Button(row2, text="R", width=2, 
                   command=lambda: [x_var.set(0), y_var.set(0), self.update_preview(None)]).pack(side=tk.RIGHT)

        self.layer_vars.append({
            "name_var": cb_var,
            "combobox": cb,
            "x_var": x_var,
            "y_var": y_var
        })

    def load_json_dir(self):
        directory = filedialog.askdirectory(title="JSONファイルがあるフォルダを選択")
        if not directory:
            return

        self.sprite_data_db = {}
        json_files = [f for f in os.listdir(directory) if f.endswith('.json')]
        
        count = 0
        for f in json_files:
            try:
                with open(os.path.join(directory, f), 'r', encoding='utf-8') as file:
                    data = json.load(file)
                    if "m_Name" in data and "m_RD" in data and "m_TextureRect" in data["m_RD"]:
                        sprite_name = data["m_Name"]
                        rect = data["m_RD"]["m_TextureRect"]
                        self.sprite_data_db[sprite_name] = {"rect": rect}
                        count += 1
            except Exception as e:
                print(f"Skipped {f}: {e}")

        self.lbl_json_count.config(text=f"JSON: {count}個 読み込み完了")
        
        sprite_names = sorted(list(self.sprite_data_db.keys()))
        sprite_names.insert(0, "")
        
        for layer in self.layer_vars:
            layer["combobox"]['values'] = sprite_names
            layer["combobox"].set("")

        messagebox.showinfo("完了", f"{count}個のSprite定義を読み込みました。")

    def load_atlas_image(self):
        file_path = filedialog.askopenfilename(title="アトラス画像を選択", filetypes=[("Image Files", "*.png;*.jpg;*.jpeg")])
        if not file_path:
            return
        
        try:
            self.atlas_image = Image.open(file_path).convert("RGBA")
            self.lbl_atlas_status.config(text=f"画像: {os.path.basename(file_path)} ({self.atlas_image.width}x{self.atlas_image.height})")
            self.update_preview()
        except Exception as e:
            messagebox.showerror("エラー", f"画像の読み込みに失敗しました:\n{e}")

    def get_cropped_sprite(self, sprite_name):
        if not self.atlas_image or sprite_name not in self.sprite_data_db:
            return None
        data = self.sprite_data_db[sprite_name]
        rect = data["rect"]
        
        u_x, u_y = rect["m_X"], rect["m_Y"]
        u_w, u_h = rect["m_Width"], rect["m_Height"]
        img_h = self.atlas_image.height
        
        left = u_x
        top = img_h - (u_y + u_h)
        right = u_x + u_w
        bottom = img_h - u_y
        
        return self.atlas_image.crop((int(left), int(top), int(right), int(bottom)))

    def update_preview(self, event=None):
        if not self.atlas_image:
            return

        # キャンバスサイズ (2048px固定、もしくはアトラスサイズに合わせて大きくする)
        canvas_width = 4096
        canvas_height = 4096
        
        # アルファ合成用のベース
        base_img = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
        center_x = canvas_width // 2
        center_y = canvas_height // 2 

        for layer in self.layer_vars:
            name = layer["name_var"].get()
            if name and name in self.sprite_data_db:
                sprite_img = self.get_cropped_sprite(name)
                if sprite_img:
                    off_x = int(layer["x_var"].get())
                    off_y = int(layer["y_var"].get())
                    
                    # 中心合わせ配置
                    paste_x = center_x - (sprite_img.width // 2) + off_x
                    paste_y = center_y - (sprite_img.height // 2) + (-off_y)
                    
                    base_img.paste(sprite_img, (paste_x, paste_y), sprite_img)

        self.generated_image = base_img

        # --- 変更点: リサイズせずに原寸大で表示する ---
        self.preview_image_tk = ImageTk.PhotoImage(self.generated_image)
        
        self.canvas_preview.delete("all")
        # 左上(nw)を基準に配置 (0, 0)
        self.canvas_preview.create_image(0, 0, image=self.preview_image_tk, anchor="nw")
        
        # スクロール領域(ScrollRegion)を画像のサイズに更新
        self.canvas_preview.config(scrollregion=self.canvas_preview.bbox("all"))

    def save_image(self):
        if not self.generated_image:
            messagebox.showwarning("警告", "保存する画像がありません。")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png")],
            title="画像を保存"
        )
        
        if file_path:
            bbox = self.generated_image.getbbox()
            if bbox:
                save_img = self.generated_image.crop(bbox)
                save_img.save(file_path)
                messagebox.showinfo("成功", "画像を保存しました。")
            else:
                messagebox.showwarning("警告", "画像が空です。")

if __name__ == "__main__":
    root = tk.Tk()
    app = SpriteAssemblerApp(root)
    root.mainloop()