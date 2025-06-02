import json
import socket
import threading

from common import constants
from room import Room


class GhostChessServer:
    def __init__(self, host, port):
        # 初始化伺服器 socket，設定監聽 host/port
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.clients = {}  # 儲存所有連線中的 client
        self.next_player_id = 1
        self.next_room_id = 1
        self.matching_queue = []  # 等待配對的玩家
        self.active_rooms = {}  # 活動中的房間
        self.server_lock = threading.Lock()

    def start(self):
        # 啟動伺服器，開始接受 client 連線
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        print(f"伺服器已啟動於 {self.host}:{self.port}，等待玩家連線...")
        self.server_socket.settimeout(1.0)
        while True:
            try:
                conn, addr = self.server_socket.accept()
                print(f"來自 {addr} 的新連線。")
                with self.server_lock:
                    pid = self.next_player_id
                    self.next_player_id += 1
                    self.clients[pid] = conn
                    self.matching_queue.append((conn, pid))
                    print(f"玩家 {pid} 加入匹配隊伍。等待人數: {len(self.matching_queue)}")

                    if len(self.matching_queue) >= 2:
                        # 當有兩位玩家時，配對進入新房間
                        p1 = self.matching_queue.pop(0)
                        p2 = self.matching_queue.pop(0)

                        room_id = self.next_room_id
                        self.next_room_id += 1
                        print(f"匹配成功！玩家 {p1[1]} 和玩家 {p2[1]} 進入房間 {room_id}")
                        print(f"[DEBUG] 建立 Room: id={room_id}, 玩家={p1[1]},{p2[1]}")
                        room = Room(room_id, p1[0], p1[1], p2[0], p2[1], self)
                        self.active_rooms[room_id] = room

                        # 為每個房間開新 thread 處理遊戲流程 (concurrent/threaded)
                        threading.Thread(target=room.start, daemon=True).start()
                    else:
                        try:
                            # 若尚未配對，通知 client 等待對手
                            conn.sendall(
                                json.dumps({"type": constants.MSG_TYPE_WAIT_OPPONENT}).encode(
                                    "utf-8"
                                )
                                + b"\n"
                            )
                        except Exception as e:
                            print(f"向等待中的玩家 {pid} 發送消息失敗: {e}")
                            if pid in self.clients:
                                del self.clients[pid]
                            self.matching_queue = [p for p in self.matching_queue if p[1] != pid]
                            try:
                                conn.close()
                            except:
                                pass
            except socket.timeout:
                continue
            except KeyboardInterrupt:
                print("伺服器正在關閉...")
                self.shutdown_server()

    def remove_room(self, room_id):
        # 移除已結束的房間
        with self.server_lock:
            if room_id in self.active_rooms:
                print(f"移除已結束的房間 {room_id}。")
                del self.active_rooms[room_id]
            else:
                print(f"嘗試移除不存在的房間 {room_id}。")

    def remove_client(self, pid):
        # 移除離線或中斷連線的 client
        with self.server_lock:
            if pid in self.clients:
                print(f"從伺服器移除客戶端 {pid}。")
                try:
                    self.clients[pid].close()
                except Exception:
                    pass
                del self.clients[pid]
            self.matching_queue = [p for p in self.matching_queue if p[1] != pid]

    def shutdown_server(self):
        # 關閉伺服器，通知所有 client 並釋放資源
        print("正在關閉所有活動房間和客戶端連接...")
        with self.server_lock:
            for room_id, room in list(self.active_rooms.items()):
                room.over = True
                room.broadcast(
                    {"type": constants.MSG_TYPE_GAME_OVER, "winner": None, "reason": "伺服器關閉。"}
                )
                room.cleanup()
            self.active_rooms.clear()
            for conn, pid in self.matching_queue:
                try:
                    conn.sendall(
                        json.dumps(
                            {"type": constants.MSG_TYPE_ERROR, "message": "伺服器正在關閉。"}
                        ).encode("utf-8")
                        + b"\n"
                    )
                    conn.close()
                except Exception:
                    pass
            self.matching_queue.clear()
            for pid, conn in self.clients.items():
                try:
                    conn.close()
                except Exception:
                    pass
            self.clients.clear()
        if self.server_socket:
            self.server_socket.close()
        print("伺服器已關閉。")


if __name__ == "__main__":
    # 啟動伺服器主程式
    server = GhostChessServer(constants.SERVER_HOST, constants.SERVER_PORT)
    server.start()
