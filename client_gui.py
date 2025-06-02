import json
import socket
import threading
import time
import tkinter as tk
from tkinter import font, messagebox, simpledialog

from common import constants

# GUI 顏色和字體
BG_COLOR = "#F0F0F0"
BOARD_COLOR = "#D2B48C"
EMPTY_SQUARE_COLOR = "#FFEBCD"
GOOD_COLOR = "deep sky blue"  # 淺藍
BAD_COLOR = "salmon"  # 淺紅
OPPONENT_HIDDEN_COLOR = "gray"
SELECTED_PIECE_COLOR = "yellow"

MY_GOOD_DISPLAY = "G"
MY_BAD_DISPLAY = "B"
OPPONENT_HIDDEN_DISPLAY = "X"


class GhostChessGUI:
    def __init__(self, host, port):
        # 初始化 client socket，準備連線到 server
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.player_id = None
        self.global_id = None
        self.board = [[constants.EMPTY_SQUARE_CHAR for _ in range(6)] for _ in range(6)]
        self.is_my_turn = False
        self.game_over = False
        self.setup_mode = False
        self.good_ghosts = []
        self.setup_rows = []
        self.setup_cols = []
        self.selected = None
        self.last_action = ""

        # --- Tkinter ---
        self.root = tk.Tk()
        self.root.title("幽靈棋")
        self.root.configure(bg=BG_COLOR)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 取得暱稱
        self.nickname = simpledialog.askstring("暱稱輸入", "請輸入您的暱稱：", parent=self.root)
        if not self.nickname:
            self.nickname = f"玩家"
        self.opponent_nickname = "(未知)"

        self.default_font = font.nametofont("TkDefaultFont")
        self.default_font.configure(size=10)
        self.button_font = font.Font(family="Helvetica", size=12, weight="bold")
        self.info_font = font.Font(family="Helvetica", size=10)
        self.status_font = font.Font(family="Helvetica", size=12, weight="bold")

        main_frame = tk.Frame(self.root, bg=BG_COLOR, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.board_frame = tk.Frame(main_frame, bg=BG_COLOR, relief=tk.FLAT, borderwidth=0)
        self.board_frame.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")

        for i in range(6):
            self.board_frame.grid_rowconfigure(i, weight=1, minsize=0)
            self.board_frame.grid_columnconfigure(i, weight=1, minsize=0)

        self.info_panel = tk.Frame(main_frame, bg=BG_COLOR, padx=10, pady=10)
        self.info_panel.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")
        main_frame.grid_columnconfigure(1, weight=1)

        self.board_btns = [[None for _ in range(6)] for _ in range(6)]
        self._create_board()
        self._create_info()

    def _on_close(self):
        # 關閉 client socket 並結束 GUI
        self.game_over = True
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
        self.root.destroy()

    def _create_board(self):
        # 建立棋盤按鈕
        for r in range(6):
            for c in range(6):
                btn = tk.Button(
                    self.board_frame,
                    text=" ",
                    font=self.button_font,
                    width=3,
                    height=1,
                    bg=EMPTY_SQUARE_COLOR,
                    command=lambda r=r, c=c: self._on_board_click(r, c),
                )
                btn.grid(row=r, column=c, padx=1, pady=1, sticky="nsew")
                self.board_btns[r][c] = btn

    def _create_info(self):
        # 建立右側資訊面板
        row = 0
        self.player_label = tk.Label(
            self.info_panel, text="玩家ID: 未分配", font=self.info_font, bg=BG_COLOR
        )
        self.player_label.grid(row=row, column=0, sticky="w", pady=2)
        row += 1

        self.status_label = tk.Label(
            self.info_panel,
            text="狀態: 等待連線...",
            font=self.status_font,
            bg=BG_COLOR,
        )
        self.status_label.grid(row=row, column=0, sticky="w", pady=5)
        row += 1

        tk.Label(self.info_panel, text="--- 統計資料 ---", font=self.info_font, bg=BG_COLOR).grid(
            row=row, column=0, sticky="w", pady=3
        )
        row += 1
        self.my_stats = tk.Label(
            self.info_panel, text="我方損失:", font=self.info_font, bg=BG_COLOR
        )
        self.my_stats.grid(row=row, column=0, sticky="w")
        row += 1
        self.opp_stats = tk.Label(
            self.info_panel, text="吃掉對手:", font=self.info_font, bg=BG_COLOR
        )
        self.opp_stats.grid(row=row, column=0, sticky="w")
        row += 1

        self.last_action_label = tk.Label(
            self.info_panel,
            text="上一動作:",
            wraplength=250,
            justify=tk.LEFT,
            font=self.info_font,
            bg=BG_COLOR,
        )
        self.last_action_label.grid(row=row, column=0, sticky="w", pady=5)
        row += 1

        self.msg_label = tk.Label(
            self.info_panel,
            text="",
            fg="blue",
            wraplength=250,
            justify=tk.LEFT,
            font=self.info_font,
            bg=BG_COLOR,
        )
        self.msg_label.grid(row=row, column=0, sticky="w", pady=5)
        row += 1

        self.setup_label = tk.Label(
            self.info_panel,
            text="",
            fg="darkgreen",
            wraplength=250,
            justify=tk.LEFT,
            font=self.info_font,
            bg=BG_COLOR,
        )
        self.setup_label.grid(row=row, column=0, sticky="w", pady=3)
        row += 1

        # 顯示自己的暱稱
        self.nickname_label = tk.Label(
            self.info_panel, text=f"暱稱: {self.nickname}", font=self.info_font, bg=BG_COLOR
        )
        self.nickname_label.grid(row=row, column=0, sticky="w", pady=2)
        row += 1
        # 顯示對手暱稱
        self.opponent_nickname_label = tk.Label(
            self.info_panel, text=f"對手暱稱: {self.opponent_nickname}", font=self.info_font, bg=BG_COLOR
        )
        self.opponent_nickname_label.grid(row=row, column=0, sticky="w", pady=2)
        row += 1

    def _update_gui(self, func, *args):
        if self.root.winfo_exists():
            self.root.after(0, func, *args)

    def connect(self):
        # 連線到 server 並啟動接收 thread
        try:
            self.sock.connect((self.host, self.port))
            self._update_gui(lambda: self.status_label.config(text="成功連線，等待ID..."))
            # 連線後立即送出暱稱
            self.send({"type": "nickname", "nickname": self.nickname})
            threading.Thread(target=self._recv, daemon=True).start()

        except Exception as e:
            self._update_gui(lambda: messagebox.showerror("連線錯誤", f"連線失敗: {e}"))
            self._on_close()

    def send(self, data):
        # 傳送資料給 server
        if self.game_over:
            return
        try:
            self.sock.sendall(json.dumps(data).encode("utf-8") + b"\n")
        except OSError as e:
            self._update_gui(lambda: messagebox.showerror("發送錯誤", f"發送訊息時連線錯誤: {e}"))
            self.game_over = True

    def _recv(self):
        # 接收 server 訊息 (threaded)
        buffer = ""
        try:
            while not self.game_over:
                chunk = self.sock.recv(4096)
                if not chunk:
                    self._update_gui(lambda: messagebox.showinfo("連線中斷", "伺服器已關閉連線。"))
                    self.game_over = True
                    break
                buffer += chunk.decode("utf-8")
                while "\n" in buffer:
                    msg_str, buffer = buffer.split("\n", 1)
                    if not self.game_over:
                        try:
                            msg = json.loads(msg_str)
                            print(f"[DEBUG] 收到伺服器訊息: {msg}")
                            self._update_gui(self._on_server_msg, msg)
                        except json.JSONDecodeError:
                            print(f"收到無效的JSON訊息: {msg_str}")
        except Exception as e:
            if not self.game_over:
                self._update_gui(
                    lambda: messagebox.showerror("接收錯誤", f"接收訊息時發生錯誤: {e}")
                )
            self.game_over = True

    def _on_server_msg(self, msg):
        # 處理 server 傳來的各種訊息，更新 GUI 狀態
        if not self.root.winfo_exists():
            return
        if self.game_over and msg.get("type") != constants.MSG_TYPE_GAME_OVER:
            return
        t = msg.get("type")
        if t == constants.MSG_TYPE_ASSIGN_ID:
            self.player_id = msg.get("player_id")
            self.global_id = msg.get("global_player_id")
            self.player_label.config(text=f"你是玩家 {self.global_id}")
            # 顯示暱稱（若 server 有回傳）
            my_nick = msg.get("my_nickname")
            opp_nick = msg.get("opponent_nickname")
            if my_nick:
                self.nickname_label.config(text=f"暱稱: {my_nick}")
            if opp_nick:
                self.opponent_nickname = opp_nick
                self.opponent_nickname_label.config(text=f"對手暱稱: {self.opponent_nickname}")
            self.setup_rows = (
                constants.P1_SETUP_ROWS
                if self.player_id == constants.P1_ID
                else constants.P2_SETUP_ROWS
            )
            self.setup_cols = [1, 2, 3, 4]
            self.status_label.config(text="已分配ID，等待對手...")
        elif t == constants.MSG_TYPE_WAIT_OPPONENT:
            self.status_label.config(text="等待對手連線...")
        elif t == constants.MSG_TYPE_START_SETUP:
            self.setup_mode = True
            self.good_ghosts = []
            self.status_label.config(text="遊戲開始，請佈局棋子")
            cols_disp = ", ".join(map(str, self.setup_cols))
            self.setup_label.config(
                text=f"請點擊 4 個位置放置好鬼 (G)。\n區域: 行 {self.setup_rows}, 列 {cols_disp}"
            )
            self._clear_board_for_setup()
        elif t == constants.MSG_TYPE_SETUP_INVALID:
            messagebox.showerror("佈局無效", msg.get("message"))
            self.good_ghosts = []
            self._clear_board_for_setup()
            self.status_label.config(text="佈局無效，請重新佈局")
        elif t == constants.MSG_TYPE_INFO:
            self.msg_label.config(text=f"[伺服器訊息] {msg.get('message')}")
            if "佈局完成，等待對手" in msg.get("message"):
                self.status_label.config(text="佈局完成，等待對手...")
                self.setup_label.config(text="")
        elif t == constants.MSG_TYPE_UPDATE_STATE:
            self.setup_mode = False
            self.setup_label.config(text="")
            self.board = msg.get("board")
            self.is_my_turn = self.player_id == msg.get("current_player")

            my_good_cap = msg.get("my_good_captured_by_opponent", 0)
            my_bad_cap = msg.get("my_bad_captured_by_opponent", 0)
            opp_good_cap = msg.get("opponent_good_captured_by_me", 0)
            opp_bad_cap = msg.get("opponent_bad_captured_by_me", 0)
            self.my_stats.config(text=f"我方損失: 好鬼 {my_good_cap}/4, 壞鬼 {my_bad_cap}/4")
            self.opp_stats.config(text=f"吃掉對手: 好鬼 {opp_good_cap}/4, 壞鬼 {opp_bad_cap}/4")

            self.last_action = msg.get("last_action_desc", "")
            self.last_action_label.config(text=f"上一個動作: {self.last_action}")

            self._update_board()
            self.msg_label.config(text="")

            if not self.game_over:
                if self.is_my_turn:
                    self.status_label.config(text="輪到你了！", fg="green")
                else:
                    self.status_label.config(text="等待對手移動...", fg="orange red")
        elif t == constants.MSG_TYPE_YOUR_TURN:
            self.is_my_turn = True
            if not self.game_over:
                self.status_label.config(text="輪到你了！", fg="green")
        elif t == constants.MSG_TYPE_OPPONENT_TURN:
            self.is_my_turn = False
            if not self.game_over:
                self.status_label.config(text="等待對手移動...", fg="orange red")
        elif t == constants.MSG_TYPE_INVALID_MOVE:
            messagebox.showerror("無效移動", msg.get("message"))
        elif t == constants.MSG_TYPE_GAME_OVER:
            self.game_over = True
            self.is_my_turn = False
            winner = msg.get("winner")
            reason = msg.get("reason")

            self._update_board()
            self.status_label.config(text="遊戲結束！", fg="black")

            title = "遊戲結束！"
            final_msg = f"{reason}\n"
            if winner == self.player_id:
                final_msg += "恭喜你，你贏了！"
                messagebox.showinfo(title, final_msg)
            elif winner is None:
                final_msg += "遊戲平手！"
                messagebox.showinfo(title, final_msg)
            else:
                final_msg += f"很遺憾，對手獲勝。"
                messagebox.showerror(title, final_msg)
            for r in range(6):
                for c in range(6):
                    if self.root.winfo_exists() and self.board_btns[r][c].winfo_exists():
                        self.board_btns[r][c].config(state=tk.DISABLED)
        elif t == constants.MSG_TYPE_ERROR:
            messagebox.showerror("伺服器錯誤", msg.get("message"))

    def _clear_board_for_setup(self):
        # 佈局模式下清空棋盤
        for r in range(6):
            for c in range(6):
                btn = self.board_btns[r][c]
                if r in self.setup_rows and c in self.setup_cols:
                    btn.config(text=" ", bg=EMPTY_SQUARE_COLOR, state=tk.NORMAL)
                else:
                    btn.config(text=" ", bg=BOARD_COLOR, state=tk.DISABLED)

    def _get_piece_display(self, piece, r, c):
        # 根據棋子種類決定顯示內容與顏色
        text, bg, fg = piece, EMPTY_SQUARE_COLOR, "black"
        if self.player_id == constants.P1_ID:
            if piece == constants.P1_GOOD_CHAR:
                text, bg, fg = MY_GOOD_DISPLAY, GOOD_COLOR, "white"
            elif piece == constants.P1_BAD_CHAR:
                text, bg, fg = MY_BAD_DISPLAY, BAD_COLOR, "white"
            elif piece == constants.OPPONENT_GHOST_CHAR:
                text, bg, fg = OPPONENT_HIDDEN_DISPLAY, OPPONENT_HIDDEN_COLOR, "white"
        elif self.player_id == constants.P2_ID:
            if piece == constants.P2_GOOD_CHAR:
                text, bg = MY_GOOD_DISPLAY, GOOD_COLOR
            elif piece == constants.P2_BAD_CHAR:
                text, bg = MY_BAD_DISPLAY, BAD_COLOR
            elif piece == constants.OPPONENT_GHOST_CHAR:
                text, bg, fg = OPPONENT_HIDDEN_DISPLAY, OPPONENT_HIDDEN_COLOR, "white"
        if piece == constants.EMPTY_SQUARE_CHAR:
            text, bg = " ", EMPTY_SQUARE_COLOR
        if self.selected and self.selected == (r, c):
            bg = SELECTED_PIECE_COLOR
        return text, fg, bg

    def _update_board(self):
        # 更新棋盤按鈕顯示與狀態
        if not self.board or not self.root.winfo_exists():
            return
        for r in range(6):
            for c in range(6):
                if not self.board_btns[r][c].winfo_exists():
                    continue
                btn = self.board_btns[r][c]
                piece = self.board[r][c]
                text, fg, bg = self._get_piece_display(piece, r, c)
                btn.config(text=text, fg=fg, bg=bg)
                if self.is_my_turn and not self.game_over:
                    is_mine = False
                    if self.player_id == constants.P1_ID and (
                        piece == constants.P1_GOOD_CHAR or piece == constants.P1_BAD_CHAR
                    ):
                        is_mine = True
                    elif self.player_id == constants.P2_ID and (
                        piece == constants.P2_GOOD_CHAR or piece == constants.P2_BAD_CHAR
                    ):
                        is_mine = True
                    can_click = False
                    if self.selected:
                        can_click = True
                    elif is_mine:
                        can_click = True
                    btn.config(state=tk.NORMAL if can_click else tk.DISABLED)
                elif (
                    not self.game_over
                    and self.setup_mode
                    and r in self.setup_rows
                    and c in self.setup_cols
                ):
                    btn.config(state=tk.NORMAL)
                else:
                    btn.config(state=tk.DISABLED)

    def _on_board_click(self, r, c):
        # 處理棋盤點擊事件 (佈局/移動)
        if not self.root.winfo_exists() or self.game_over:
            return
        if self.setup_mode:
            if not (r in self.setup_rows and c in self.setup_cols):
                messagebox.showwarning(
                    "佈局",
                    f"只能在你的佈局區域 (行 {self.setup_rows}, 列 {self.setup_cols}) 放置好鬼。",
                )
                return
            coords = [(p["row"], p["col"]) for p in self.good_ghosts]
            if (r, c) in coords:
                self.good_ghosts = [p for p in self.good_ghosts if (p["row"], p["col"]) != (r, c)]
                self.board_btns[r][c].config(text=" ", bg=EMPTY_SQUARE_COLOR)
                self.setup_label.config(text=f"已放置 {len(self.good_ghosts)}/4 個好鬼。")
                return
            if len(self.good_ghosts) < 4:
                self.good_ghosts.append({"row": r, "col": c, "ghost_type": "G"})
                good_bg = GOOD_COLOR if self.player_id == constants.P1_ID else GOOD_COLOR
                self.board_btns[r][c].config(text=MY_GOOD_DISPLAY, bg=good_bg, fg="white")
                self.setup_label.config(text=f"已放置 {len(self.good_ghosts)}/4 個好鬼。")

                if len(self.good_ghosts) == 4:
                    self.setup_label.config(text=f"好鬼佈局完成！自動填充壞鬼並發送...")
                    self._finalize_setup()
            else:
                messagebox.showinfo("佈局", f"已經放置了 4 個好鬼。")
        elif self.is_my_turn:
            piece = self.board[r][c]
            is_mine = False
            if self.player_id == constants.P1_ID:
                is_mine = piece == constants.P1_GOOD_CHAR or piece == constants.P1_BAD_CHAR
            elif self.player_id == constants.P2_ID:
                is_mine = piece == constants.P2_GOOD_CHAR or piece == constants.P2_BAD_CHAR
            if not self.selected:
                if is_mine:
                    self.selected = (r, c)
                    self._update_board()
                else:
                    messagebox.showwarning("選擇棋子", "請選擇你自己的棋子進行移動。")
            else:
                from_sq = self.selected
                to_sq = (r, c)
                if from_sq == to_sq:
                    self.selected = None
                    self._update_board()
                    return
                dr = abs(from_sq[0] - to_sq[0])
                dc = abs(from_sq[1] - to_sq[1])
                if not ((dr == 1 and dc == 0) or (dr == 0 and dc == 1)):
                    messagebox.showerror("無效移動", "只能移動到前後左右相鄰的格子。")
                    self.selected = None
                    self._update_board()
                    return
                if is_mine:
                    messagebox.showerror("無效移動", "不能移動到有自己棋子的位置。")
                    self.selected = None
                    self._update_board()
                    return
                self.send(
                    {
                        "type": constants.MSG_TYPE_MOVE,
                        "from_sq": [from_sq[0], from_sq[1]],
                        "to_sq": [to_sq[0], to_sq[1]],
                    }
                )
                self.selected = None
                self.status_label.config(text="移動已發送，等待回應...", fg="blue")

    def _finalize_setup(self):
        # 佈局完成後自動補齊壞鬼並送出資料
        all_placements = list(self.good_ghosts)
        num_bad = 4
        current = {(p["row"], p["col"]): "G" for p in self.good_ghosts}
        for r in self.setup_rows:
            for c in self.setup_cols:
                if num_bad == 0:
                    break
                if (r, c) not in current:
                    all_placements.append({"row": r, "col": c, "ghost_type": "B"})
                    bad_bg = BAD_COLOR if self.player_id == constants.P1_ID else BAD_COLOR
                    if self.root.winfo_exists() and self.board_btns[r][c].winfo_exists():
                        self.board_btns[r][c].config(text=MY_BAD_DISPLAY, bg=bad_bg, fg="white")
                    num_bad -= 1
            if num_bad == 0:
                break
        if len(all_placements) != 8:
            messagebox.showerror(
                "佈局錯誤",
                f"自動填充壞鬼後棋子總數 ({len(all_placements)}) 不正確。請重試。",
            )
            self.good_ghosts = []
            self._clear_board_for_setup()
            self.status_label.config(text="佈局錯誤，請重新佈局好鬼")
            self.setup_label.config(text=f"請點擊 4 個位置放置好鬼 (G)。")
            return
        self.send({"type": constants.MSG_TYPE_SETUP_DATA, "placements": all_placements})
        self.setup_mode = False
        for r in range(6):
            for c in range(6):
                if self.root.winfo_exists() and self.board_btns[r][c].winfo_exists():
                    self.board_btns[r][c].config(state=tk.DISABLED)

    def start(self):
        # 啟動 client 主程式 (連線+GUI主迴圈)
        self.connect()
        self.root.mainloop()


if __name__ == "__main__":
    # 啟動 client 端
    client = GhostChessGUI(constants.SERVER_HOST, constants.SERVER_PORT)
    client.start()
