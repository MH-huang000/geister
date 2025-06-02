import json
import random
import threading

from common import constants


class Room:
    def __init__(self, room_id, p1_conn, p1_gid, p2_conn, p2_gid, server):
        # 初始化房間，儲存玩家 socket、ID、server
        self.id = room_id
        self.server = server
        self.players = {1: p1_conn, 2: p2_conn}  # 兩位玩家的 socket
        self.global_ids = {1: p1_gid, 2: p2_gid}  # 兩位玩家的全域 ID
        self.threads = {}  # 玩家 thread
        self.setups = {}   # 玩家佈局資料
        self.turn = None   # 當前回合
        self.over = False  # 遊戲是否結束
        self.lock = threading.Lock()  # 多執行緒同步鎖
        self.board = [[None for _ in range(6)] for _ in range(6)]
        self.captured = {1: {"good": 0, "bad": 0}, 2: {"good": 0, "bad": 0}}  # 各玩家吃掉的鬼
        self.nicknames = {}
        print(f"[Room {self.id}] Created: {p1_gid}(P1) vs {p2_gid}(P2)")

    def start(self):
        # 房間啟動，分配 ID、廣播開始佈局、啟動玩家 thread
        for player_id in (1, 2):
            opp_id = 2 if player_id == 1 else 1
            self.send(
                player_id,
                {
                    "type": constants.MSG_TYPE_ASSIGN_ID,
                    "player_id": player_id,
                    "global_player_id": self.global_ids[player_id],
                    "my_nickname": self.nicknames.get(player_id, f"玩家{player_id}"),
                    "opponent_nickname": self.nicknames.get(opp_id, f"玩家{opp_id}"),
                },
            )
        self.broadcast({"type": constants.MSG_TYPE_START_SETUP})
        for player_id in (1, 2):
            t = threading.Thread(target=self.player_loop, args=(self.players[player_id], player_id))
            self.threads[player_id] = t
            t.start()

    def send(self, player_id, data):
        # 傳送訊息給指定玩家
        try:
            conn = self.players.get(player_id)
            if conn:
                conn.sendall(json.dumps(data).encode("utf-8") + b"\n")
        except Exception as e:
            print(f"[Room {self.id}] Send to {self.global_ids[player_id]} failed: {e}")

    def broadcast(self, data):
        # 廣播訊息給所有玩家
        for pid in self.players:
            self.send(pid, data)

    def player_loop(self, conn, player_id):
        # 處理單一玩家的訊息收發 (threaded)
        global_player_id = self.global_ids[player_id]
        try:
            buffer = ""
            while not self.over:
                chunk = conn.recv(1024).decode("utf-8")
                if not chunk:
                    print(f"[Room {self.id}] Player {global_player_id} disconnected.")
                    self.on_disconnect(player_id)
                    break
                buffer += chunk
                while "\n" in buffer:
                    msg_str, buffer = buffer.split("\n", 1)
                    try:
                        print(f"[DEBUG][Room {self.id}] 收到玩家 {global_player_id} 訊息: {msg_str}")
                        msg = json.loads(msg_str)
                        # 新增處理 nickname
                        if msg.get("type") == "nickname":
                            self.nicknames[player_id] = msg.get("nickname", f"玩家{player_id}")
                            # 兩邊都送過來才廣播
                            if len(self.nicknames) == 2:
                                for pid in (1, 2):
                                    opp_id = 2 if pid == 1 else 1
                                    self.send(
                                        pid,
                                        {
                                            "type": constants.MSG_TYPE_ASSIGN_ID,
                                            "player_id": pid,
                                            "global_player_id": self.global_ids[pid],
                                            "my_nickname": self.nicknames[pid],
                                            "opponent_nickname": self.nicknames[opp_id],
                                        },
                                    )
                            continue
                        self.on_message(player_id, msg)
                    except json.JSONDecodeError:
                        print(f"[Room {self.id}] 玩家 {global_player_id} 傳送無效 JSON。")
        except (ConnectionResetError, OSError) as e:
            if not self.over:
                print(f"[Room {self.id}] 玩家 {global_player_id} 連線錯誤: {e}")
                self.on_disconnect(player_id)
        finally:
            print(f"[Room {self.id}] 玩家 {global_player_id} 的 thread 結束。")

    def on_disconnect(self, player_id):
        # 處理玩家斷線，通知對手並清理房間
        with self.lock:
            if self.over:
                return
            self.over = True
            global_player_id = self.global_ids[player_id]
            print(f"[Room {self.id}] 玩家 {global_player_id} 中斷連線。")
            opp_id = 2 if player_id == 1 else 1
            if opp_id in self.players:
                self.send(
                    opp_id,
                    {
                        "type": constants.MSG_TYPE_GAME_OVER,
                        "winner": opp_id,
                        "reason": f"對手玩家 {global_player_id} 斷線。",
                    },
                )
                print(
                    f"[Room {self.id}] 因為斷線而結束。玩家 {self.global_ids[opp_id]} 獲勝。"
                )
            self.cleanup()

    def cleanup(self):
        # 關閉所有 socket 並通知 server 移除房間
        print(f"[Room {self.id}] 正在清理房間...")
        for pid, conn in self.players.items():
            try:
                conn.close()
            except Exception as e:
                print(f"[Room {self.id}] 關閉玩家 {self.global_ids[pid]} 的連線時發生錯誤: {e}")
        self.players.clear()
        if self.server:
            self.server.remove_room(self.id)

    def on_message(self, player_id, msg):
        # 處理玩家傳來的各種訊息 (佈局/移動)
        msg_type = msg.get("type")
        with self.lock:
            if self.over:
                if msg_type == constants.MSG_TYPE_MOVE:
                    self.send(
                        player_id,
                        {"type": constants.MSG_TYPE_INVALID_MOVE, "message": "遊戲已結束。"},
                    )
                return
            if msg_type == constants.MSG_TYPE_SETUP_DATA:
                self.on_setup(player_id, msg.get("placements"))
            elif msg_type == constants.MSG_TYPE_MOVE:
                if self.turn == player_id:
                    self.on_move(player_id, msg.get("from_sq"), msg.get("to_sq"))
                else:
                    self.send(
                        player_id,
                        {"type": constants.MSG_TYPE_INVALID_MOVE, "message": "現在不是你的回合。"},
                    )

    def on_setup(self, player_id, placements):
        # 處理玩家佈局資料，檢查合法性
        if not placements or len(placements) != 8:
            self.send(
                player_id,
                {
                    "type": constants.MSG_TYPE_SETUP_INVALID,
                    "message": f"你需要放置 8 個棋子。",
                },
            )
            return
        good = sum(1 for p in placements if p["ghost_type"] == "G")
        bad = sum(1 for p in placements if p["ghost_type"] == "B")
        if good != 4 or bad != 4:
            self.send(
                player_id,
                {
                    "type": constants.MSG_TYPE_SETUP_INVALID,
                    "message": f"你需要放置 4 個好鬼和 4 個壞鬼。",
                },
            )
            return
        valid_rows = constants.P1_SETUP_ROWS if player_id == 1 else constants.P2_SETUP_ROWS
        valid_cols = [1, 2, 3, 4]
        temp_board = [[None for _ in range(6)] for _ in range(6)]
        for p in placements:
            r, c, t = p["row"], p["col"], p["ghost_type"]
            if not (0 <= r < 6 and 0 <= c < 6 and r in valid_rows and c in valid_cols):
                self.send(
                    player_id,
                    {
                        "type": constants.MSG_TYPE_SETUP_INVALID,
                        "message": f"棋子位置 ({r},{c}) 無效。必須在列 {valid_rows} 且行 {valid_cols} 的範圍內。",
                    },
                )
                return
            if temp_board[r][c] is not None:
                self.send(
                    player_id,
                    {
                        "type": constants.MSG_TYPE_SETUP_INVALID,
                        "message": f"位置 ({r},{c}) 上不能重複放置棋子。",
                    },
                )
                return
            temp_board[r][c] = (player_id, t)
        self.setups[player_id] = placements
        for p in placements:
            self.board[p["row"]][p["col"]] = (player_id, p["ghost_type"])
        self.send(player_id, {"type": constants.MSG_TYPE_INFO, "message": "佈局完成，等待對手..."})
        if len(self.setups) == 2:
            self.start_game()

    def start_game(self):
        # 遊戲正式開始，隨機決定先手
        self.turn = random.choice([1, 2])
        print(f"[Room {self.id}] 遊戲正式開始！先手玩家: {self.turn}")
        for pid in self.players:
            self.send_state(pid, "遊戲開始！")

    def board_view(self, player_id):
        # 產生給指定玩家的棋盤視角 (隱藏對手資訊)
        view = [[constants.EMPTY_SQUARE_CHAR for _ in range(6)] for _ in range(6)]
        for r in range(6):
            for c in range(6):
                piece = self.board[r][c]
                if piece:
                    owner, t = piece
                    if owner == player_id:
                        view[r][c] = (
                            constants.P1_GOOD_CHAR
                            if (player_id == 1 and t == "G")
                            else (
                                constants.P1_BAD_CHAR
                                if (player_id == 1)
                                else (constants.P2_GOOD_CHAR if t == "G" else constants.P2_BAD_CHAR)
                            )
                        )
                    else:
                        view[r][c] = constants.OPPONENT_GHOST_CHAR
        return view

    def send_state(self, player_id, last_action_desc=""):
        # 傳送遊戲狀態給玩家
        if self.over:
            return
        opp = 2 if player_id == 1 else 1
        state = {
            "type": constants.MSG_TYPE_UPDATE_STATE,
            "board": self.board_view(player_id),
            "current_player": self.turn,
            "my_player_id": player_id,
            "my_good_captured_by_opponent": self.captured[opp]["good"],
            "my_bad_captured_by_opponent": self.captured[opp]["bad"],
            "opponent_good_captured_by_me": self.captured[player_id]["good"],
            "opponent_bad_captured_by_me": self.captured[player_id]["bad"],
            "last_action_desc": last_action_desc,
            "my_nickname": self.nicknames.get(player_id, f"玩家{player_id}"),
            "opponent_nickname": self.nicknames.get(opp, f"玩家{opp}"),
        }
        self.send(player_id, state)
        self.send(
            player_id,
            {
                "type": (
                    constants.MSG_TYPE_YOUR_TURN
                    if self.turn == player_id
                    else constants.MSG_TYPE_OPPONENT_TURN
                )
            },
        )

    def on_move(self, player_id, from_sq, to_sq):
        # 處理玩家移動，檢查規則、吃子、勝負判斷
        from_r, from_c = from_sq
        to_r, to_c = to_sq
        if not (0 <= from_r < 6 and 0 <= from_c < 6 and 0 <= to_r < 6 and 0 <= to_c < 6):
            self.send(
                player_id, {"type": constants.MSG_TYPE_INVALID_MOVE, "message": "無效的座標。"}
            )
            self.send(player_id, {"type": constants.MSG_TYPE_YOUR_TURN})
            return
        moving_piece = self.board[from_r][from_c]
        if not moving_piece or moving_piece[0] != player_id:
            self.send(
                player_id,
                {"type": constants.MSG_TYPE_INVALID_MOVE, "message": "你不能移動該位置的棋子。"},
            )
            self.send(player_id, {"type": constants.MSG_TYPE_YOUR_TURN})
            return
        if not (
            (abs(from_r - to_r) == 1 and from_c == to_c)
            or (abs(from_c - to_c) == 1 and from_r == to_r)
        ):
            self.send(
                player_id,
                {
                    "type": constants.MSG_TYPE_INVALID_MOVE,
                    "message": "無效的移動方式，只能前後左右移動一格。",
                },
            )
            self.send(player_id, {"type": constants.MSG_TYPE_YOUR_TURN})
            return
        target = self.board[to_r][to_c]
        action_desc = (
            f"玩家 {self.global_ids[player_id]} 從 ({from_r},{from_c}) 移動到 ({to_r},{to_c})"
        )
        if target and target[0] == player_id:
            self.send(
                player_id,
                {"type": constants.MSG_TYPE_INVALID_MOVE, "message": "目標位置有你自己的棋子。"},
            )
            self.send(player_id, {"type": constants.MSG_TYPE_YOUR_TURN})
            return
        self.board[to_r][to_c] = moving_piece
        self.board[from_r][from_c] = None
        if target:
            opp_id, captured_type = target
            if captured_type == "G":
                self.captured[player_id]["good"] += 1
            else:
                self.captured[player_id]["bad"] += 1
            action_desc += f"，吃掉了玩家 {self.global_ids[opp_id]} 的{'好鬼' if captured_type == 'G' else '壞鬼'}！"
        winner, reason = self.check_win(player_id, moving_piece[1], (to_r, to_c))
        if winner:
            self.over = True
            for notify_pid in self.players:
                self.send_state(notify_pid, action_desc)
            print(f"[Room {self.id}] {reason}")
            self.broadcast(
                {"type": constants.MSG_TYPE_GAME_OVER, "winner": winner, "reason": reason}
            )
            self.cleanup()
            return
        self.turn = 2 if player_id == 1 else 1
        for notify_pid in self.players:
            self.send_state(notify_pid, action_desc)

    def check_win(self, player_id, moved_type, to_pos):
        # 勝負判斷邏輯
        opp = 2 if player_id == 1 else 1
        pid_str = self.global_ids[player_id]
        opp_str = self.global_ids[opp]
        if self.captured[player_id]["good"] >= 4:
            return player_id, f"玩家 {pid_str} 吃掉了對手所有好鬼！"
        if self.captured[opp]["bad"] >= 4:
            return (
                player_id,
                f"玩家 {pid_str} 的所有壞鬼被對手玩家 {opp_str} 吃掉，玩家 {pid_str} 獲勝！",
            )
        if self.captured[player_id]["bad"] >= 4:
            return opp, f"玩家 {opp_str} 的所有壞鬼被對手玩家 {pid_str} 吃掉，玩家 {opp_str} 獲勝！"
        if moved_type == "G":
            corners = constants.P1_ESCAPE_CORNERS if player_id == 1 else constants.P2_ESCAPE_CORNERS
            if to_pos in corners:
                return player_id, f"玩家 {pid_str} 的好鬼成功逃脫！"
        return None, ""
