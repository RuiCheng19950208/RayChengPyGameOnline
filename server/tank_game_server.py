#!/usr/bin/env python3
"""
实现 WebSocket 服务器，处理所有游戏消息，管理游戏状态
"""

import asyncio
import json
import os
import sys
import time
import uuid
import socket
from typing import Dict, List, Optional, Set
import websockets
from websockets.server import WebSocketServerProtocol
from dataclasses import asdict
from dotenv import load_dotenv
from http.server import HTTPServer, SimpleHTTPRequestHandler
import threading

# 添加共享目录到 Python 路径 - 必须在导入自定义模块之前
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from tank_game_messages import (
    GameMessage, GameMessageType, parse_message,
    PlayerMoveMessage, PlayerStopMessage, PlayerShootMessage,
    PlayerJoinMessage, PlayerLeaveMessage, GameStateUpdateMessage,
    PlayerPositionUpdateMessage, BulletFiredMessage, BulletHitMessage,
    PlayerHitMessage, PlayerDestroyedMessage, ConnectionAckMessage,
    PingMessage, PongMessage, ErrorMessage, DebugMessage,
    create_error_message, create_debug_message,
    BulletDestroyedMessage, CollisionMessage, PlayerDeathMessage,
    SlotChangeRequestMessage, SlotChangedMessage, RoomStartGameMessage,
    CreateRoomRequestMessage, RoomCreatedMessage, RoomListRequestMessage,
    RoomListMessage, RoomDisbandedMessage
)

# 导入共享的实体类
from tank_game_entities import Player, Bullet, GameRoom

# 加载环境变量 - 使用项目根目录的共享 .env 文件
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# 游戏配置 - 与客户端保持一致
SCREEN_WIDTH = int(os.getenv('SCREEN_WIDTH', 800))
SCREEN_HEIGHT = int(os.getenv('SCREEN_HEIGHT', 600))
FPS = int(os.getenv('FPS', 60))
TANK_SPEED = int(os.getenv('TANK_SPEED', 300))  # 关键：与客户端相同的速度
BULLET_SPEED = int(os.getenv('BULLET_SPEED', 300))
BULLET_DAMAGE = int(os.getenv('BULLET_DAMAGE', 25))
BULLET_LIFETIME = float(os.getenv('BULLET_LIFETIME', 5.0))


SERVER_HOST = '0.0.0.0'  # 默认监听所有接口
SERVER_PORT = int(os.getenv('SERVER_PORT', 8765))
MAX_PLAYERS_PER_ROOM = int(os.getenv('MAX_PLAYERS_PER_ROOM', 8))

def get_local_ip():
    """自动获取本机局域网IP地址"""
    try:
        # 方法1：连接到远程地址获取本机IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        try:
            # 方法2：获取主机名对应的IP
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            if not local_ip.startswith('127.'):
                return local_ip
        except Exception:
            pass
    
    # 方法3：遍历所有网络接口
    try:
        import subprocess
        import platform
        
        system = platform.system()
        if system in ["Darwin", "Linux"]:  # macOS or Linux
            result = subprocess.run(['ifconfig'], capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'inet ' in line and not '127.0.0.1' in line:
                        parts = line.strip().split()
                        for i, part in enumerate(parts):
                            if part == 'inet' and i + 1 < len(parts):
                                ip = parts[i + 1]
                                if ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
                                    return ip
        elif system == "Windows":
            result = subprocess.run(['ipconfig'], capture_output=True, text=True)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'IPv4' in line:
                        ip = line.split(':')[-1].strip()
                        if ip.startswith('192.168.') or ip.startswith('10.') or ip.startswith('172.'):
                            return ip
    except Exception:
        pass
    
    return 'localhost'

def display_server_info(host: str, port: int):
    """显示服务器连接信息"""
    print("=" * 60)
    print("🎮 Tank Game Server Started Successfully!")
    print("=" * 60)
    
    if host == '0.0.0.0':
        local_ip = get_local_ip()
        print(f"🖥️  Server Host: {host} (listening on all interfaces)")
        print(f"🌐 Local IP: {local_ip}")
        print(f"🔌 Port: {port}")
        print(f"📊 Status Port: {port + 1}")  # HTTP状态端口
        print()
        print("💻 Client Commands:")
        print(f"   • Local: python home/tank_game_client.py")
        print(f"   • Remote: python home/tank_game_client.py --host {local_ip}")
        print(f"   • Custom: python home/tank_game_client.py --server ws://{local_ip}:{port}")
    else:
        print(f"🖥️  Server Host: {host}")
        print(f"🔌 Port: {port}")
        print(f"🌐 Connection URL: ws://{host}:{port}")
    
    print()
    print("🔥 Ready for battle! Waiting for players...")
    print("=" * 60)

class StatusHandler(SimpleHTTPRequestHandler):
    """简单的HTTP状态处理器"""
    
    def __init__(self, server_instance, *args, **kwargs):
        self.server_instance = server_instance
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """处理GET请求"""
        if self.path == '/status':
            # 返回服务器状态JSON - 只计算可加入的房间
            total_players = len(self.server_instance.players)
            
            # 只计算等待状态且有玩家的房间（可加入的房间）
            joinable_rooms = [
                r for r in self.server_instance.rooms.values() 
                if len(r.players) > 0 and r.room_state == "waiting"
            ]
            joinable_players = sum(len(r.players) for r in joinable_rooms)
            
            status = {
                'players': joinable_players,  # 只返回可加入房间的玩家数
                'max_players': MAX_PLAYERS_PER_ROOM * len(self.server_instance.rooms),
                'rooms': len(joinable_rooms),  # 只返回可加入的房间数
                'server_version': '1.0.0',
                'status': 'online'
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')  # 允许跨域
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
            
            # 详细调试信息
            print(f"📊 Status query: {len(joinable_rooms)} joinable rooms, {joinable_players} joinable players")
            print(f"📊 Total rooms: {len(self.server_instance.rooms)}, Total players: {total_players}")
            for room_id, room in self.server_instance.rooms.items():
                print(f"📊   Room {room_id}: {len(room.players)} players, state={room.room_state}, host={room.host_player_id}")
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """禁用HTTP日志输出"""
        pass

class TankGameServer:
    """坦克游戏服务器"""
    def __init__(self, host: str = None, port: int = None):
        self.host = host if host is not None else SERVER_HOST
        self.port = port if port is not None else SERVER_PORT
        self.status_port = self.port + 1  # HTTP状态端口
        self.clients: Dict[WebSocketServerProtocol, str] = {}  # websocket -> client_id
        self.players: Dict[str, Player] = {}  # player_id -> Player
        self.rooms: Dict[str, GameRoom] = {}  # room_id -> GameRoom
        self.running = False
        self.game_loop_task: Optional[asyncio.Task] = None
        self.http_server = None
        self.http_thread = None
        
        # 不创建默认房间 - 房间应该按需创建
        
        print(f"🎮 TankGameServer initialized on {self.host}:{self.port}")
        print(f"🎯 Game config: {SCREEN_WIDTH}x{SCREEN_HEIGHT}, Speed: {TANK_SPEED}")
    
    def start_status_server(self):
        """启动HTTP状态服务器"""
        def create_handler(*args, **kwargs):
            return StatusHandler(self, *args, **kwargs)
        
        try:
            bind_host = '' if self.host == '0.0.0.0' else self.host
            self.http_server = HTTPServer((bind_host, self.status_port), create_handler)
            self.http_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True)
            self.http_thread.start()
            print(f"📊 Status server started on port {self.status_port}")
        except Exception as e:
            print(f"⚠️ Failed to start status server: {e}")
    
    def stop_status_server(self):
        """停止HTTP状态服务器"""
        if self.http_server:
            self.http_server.shutdown()
            self.http_server.server_close()
        if self.http_thread:
            self.http_thread.join(timeout=1.0)
    
    async def start(self):
        """启动服务器"""
        self.running = True
        
        # 启动HTTP状态服务器
        self.start_status_server()
        
        # 启动游戏循环
        self.game_loop_task = asyncio.create_task(self.game_loop())
        
        # 启动 WebSocket 服务器
        async with websockets.serve(self.handle_client, self.host, self.port):
            await asyncio.Future()  # 永远运行
    
    async def stop(self):
        """停止服务器"""
        self.running = False
        if self.game_loop_task:
            self.game_loop_task.cancel()
        self.stop_status_server()
        print("🛑 Server stopped")
    
    async def handle_client(self, websocket: WebSocketServerProtocol):
        """处理客户端连接"""
        client_id = str(uuid.uuid4())
        self.clients[websocket] = client_id
        
        print(f"🔗 Client connected: {client_id}")
        
        # 发送连接确认
        ack_message = ConnectionAckMessage(
            client_id=client_id,
            server_time=time.time(),
            game_version="1.0.0",
            assigned_player_id=client_id
        )
        await self.send_message(websocket, ack_message)
        
        try:
            async for message in websocket:
                await self.handle_message(websocket, client_id, message)
        except websockets.exceptions.ConnectionClosed:
            print(f"🔌 Client disconnected: {client_id}")
        except Exception as e:
            print(f"❌ Error handling client {client_id}: {e}")
        finally:
            await self.disconnect_client(websocket, client_id)
    
    async def disconnect_client(self, websocket: WebSocketServerProtocol, client_id: str):
        """断开客户端连接"""
        print(f"🔌 Disconnecting client {client_id}...")
        
        # 移除玩家
        if client_id in self.players:
            player = self.players[client_id]
            player_name = player.name
            
            # 找到玩家所在的房间并移除
            rooms_to_delete = []
            rooms_to_disband = []
            
            for room_id, room in self.rooms.items():
                if client_id in room.players:
                    print(f"📤 Removing player {player_name} from room {room_id}")
                    
                    # 检查是否为房主
                    if room.is_host(client_id):
                        print(f"🗑️ Host {client_id} disconnected, disbanding room {room_id}")
                        
                        # 创建房间解散消息
                        disband_message = RoomDisbandedMessage(
                            room_id=room_id,
                            disbanded_by=client_id,
                            reason="host_disconnected"
                        )
                        
                        # 广播给房间内其他玩家
                        await self.broadcast_to_room(room_id, disband_message, exclude=client_id)
                        
                        # 标记房间需要解散
                        rooms_to_disband.append(room_id)
                    else:
                        # 普通玩家离开
                        room.remove_player(client_id)
                        
                        # 广播玩家离开消息给房间内其他玩家
                        if len(room.players) > 0:
                            leave_message = PlayerLeaveMessage(
                                player_id=client_id,
                                reason="disconnected"
                            )
                            await self.broadcast_to_room(room_id, leave_message, exclude=client_id)
                        
                        # 如果房间空了，标记为删除
                        if len(room.players) == 0:
                            rooms_to_delete.append(room_id)
                            print(f"🗑️ Room {room_id} is empty, marking for deletion")
            
            # 解散房主离开的房间
            for room_id in rooms_to_disband:
                # 移除房间内所有其他玩家
                if room_id in self.rooms:
                    room = self.rooms[room_id]
                    remaining_players = [pid for pid in room.players.keys() if pid != client_id]
                    for player_id in remaining_players:
                        if player_id in self.players:
                            del self.players[player_id]
                            print(f"📤 Removed player {player_id} due to host disconnect")
                    
                    # 删除房间
                    del self.rooms[room_id]
                    print(f"🗑️ Room {room_id} disbanded due to host disconnect")
            
            # 删除其他空房间
            for room_id in rooms_to_delete:
                if room_id in self.rooms:
                    del self.rooms[room_id]
                    print(f"🗑️ Deleted empty room: {room_id}")
            
            # 从玩家字典中移除
            del self.players[client_id]
            print(f"✅ Player {player_name} ({client_id}) completely removed")
        
        # 移除客户端
        if websocket in self.clients:
            del self.clients[websocket]
        
        print(f"🚪 Client {client_id} fully disconnected")
        
        # 详细的房间状态调试信息
        active_rooms = [r for r in self.rooms.values() if len(r.players) > 0]
        waiting_rooms = [r for r in self.rooms.values() if len(r.players) > 0 and r.room_state == "waiting"]
        print(f"📊 After disconnect - Active rooms: {len(active_rooms)}, Waiting rooms: {len(waiting_rooms)}, Total players: {len(self.players)}")
        
        # 详细显示每个房间的状态（只显示有玩家的房间）
        for room_id, room in self.rooms.items():
            if len(room.players) > 0:
                player_names = [p.name for p in room.players.values()]
                print(f"📊   Room {room_id}: {len(room.players)} players {player_names}, state={room.room_state}, host={room.host_player_id}")
        
        if len(self.rooms) == 0:
            print("📊 No rooms remaining - all rooms cleaned up successfully")
    
    async def handle_message(self, websocket: WebSocketServerProtocol, client_id: str, raw_message: str):
        """处理客户端消息"""
        try:
            message = parse_message(raw_message)
            if not message:
                error_msg = create_error_message("INVALID_MESSAGE", "Failed to parse message")
                await self.send_message(websocket, error_msg)
                return
            
            # 减少日志噪音 - 只记录重要消息
            if message.type not in [GameMessageType.PING, GameMessageType.PLAYER_MOVE]:
                print(f"📨 Received {message.type} from {client_id}")
            
            # 路由消息到对应的处理器
            await self.route_message(websocket, client_id, message)
            
        except Exception as e:
            print(f"❌ Error handling message from {client_id}: {e}")
            error_msg = create_error_message("MESSAGE_ERROR", str(e))
            await self.send_message(websocket, error_msg)
    
    async def route_message(self, websocket: WebSocketServerProtocol, client_id: str, message: GameMessage):
        """路由消息到对应的处理器"""
        handlers = {
            GameMessageType.PLAYER_JOIN: self.handle_player_join,
            GameMessageType.PLAYER_LEAVE: self.handle_player_leave,
            GameMessageType.PLAYER_MOVE: self.handle_player_move,
            GameMessageType.PLAYER_STOP: self.handle_player_stop,
            GameMessageType.PLAYER_SHOOT: self.handle_player_shoot,
            GameMessageType.PING: self.handle_ping,
            GameMessageType.CREATE_ROOM_REQUEST: self.handle_create_room_request,
            GameMessageType.ROOM_LIST_REQUEST: self.handle_room_list_request,
            GameMessageType.ROOM_DISBANDED: self.handle_room_disbanded,
            GameMessageType.SLOT_CHANGE_REQUEST: self.handle_slot_change_request,
            GameMessageType.ROOM_START_GAME: self.handle_room_start_game,
        }
        
        handler = handlers.get(message.type)
        if handler:
            await handler(websocket, client_id, message)
        else:
            print(f"⚠️ No handler for message type: {message.type}")
    
    async def handle_player_join(self, websocket: WebSocketServerProtocol, client_id: str, message: PlayerJoinMessage):
        """处理玩家加入"""
        # 创建玩家 - 使用共享实体类的新接口
        player_data = {
            'player_id': client_id,
            'name': message.player_name
        }
        player = Player(player_data, websocket)
        self.players[client_id] = player
        
        # 确定要加入的房间ID
        target_room_id = message.room_id
        if not target_room_id:
            # 如果没有指定房间ID，拒绝加入
            error_msg = create_error_message("NO_ROOM_SPECIFIED", "No room ID specified")
            await self.send_message(websocket, error_msg)
            return
        
        # 确保目标房间存在
        if target_room_id not in self.rooms:
            error_msg = create_error_message("ROOM_NOT_FOUND", f"Room {target_room_id} not found")
            await self.send_message(websocket, error_msg)
            return
        
        room = self.rooms[target_room_id]
        if room.add_player(player):
            print(f"👤 Player {message.player_name} ({client_id}) joined room {target_room_id} slot {player.slot_index}")
            
            # 广播玩家加入消息给房间内其他玩家
            await self.broadcast_to_room(target_room_id, message, exclude=client_id)
            
            # 发送当前游戏状态给新玩家（包含所有玩家的槽位信息）
            state_message = GameStateUpdateMessage(
                players=[p.to_dict() for p in room.players.values()],
                bullets=[b.to_dict() for b in room.bullets.values()],
                game_time=room.game_time,
                frame_id=room.frame_id
            )
            await self.send_message(websocket, state_message)
            
            # 广播房间更新给所有玩家
            room_update_message = GameStateUpdateMessage(
                players=[p.to_dict() for p in room.players.values()],
                bullets=[],  # 房间大厅不需要子弹信息
                game_time=room.game_time,
                frame_id=room.frame_id
            )
            await self.broadcast_to_room(target_room_id, room_update_message)
        else:
            error_msg = create_error_message("ROOM_FULL", f"Room {target_room_id} is full")
            await self.send_message(websocket, error_msg)
    
    async def handle_player_leave(self, websocket: WebSocketServerProtocol, client_id: str, message: PlayerLeaveMessage):
        """处理玩家主动离开消息"""
        print(f"👋 Player {client_id} is leaving (reason: {message.reason})")
        # 触发断开连接处理逻辑
        await self.disconnect_client(websocket, client_id)
    
    async def handle_player_move(self, websocket: WebSocketServerProtocol, client_id: str, message: PlayerMoveMessage):
        """处理玩家移动 - 修复：信任客户端位置"""
        if client_id in self.players:
            player = self.players[client_id]
            player.moving_directions = message.direction
            player.last_client_update = time.time()
            player.use_client_position = True  # 标记使用客户端位置
            
            # 直接使用客户端发送的位置（信任客户端预测）
            if message.position:
                # 基本的反作弊检查
                new_x = max(0, min(SCREEN_WIDTH, message.position["x"]))
                new_y = max(0, min(SCREEN_HEIGHT, message.position["y"]))
                
                # 更新位置
                player.position = {"x": new_x, "y": new_y}
            
            player.last_update = time.time()
            
            # 立即广播移动消息（事件驱动）
            await self.broadcast_to_room(self.default_room_id, message, exclude=client_id)
    
    async def handle_player_stop(self, websocket: WebSocketServerProtocol, client_id: str, message: PlayerStopMessage):
        """处理玩家停止"""
        if client_id in self.players:
            player = self.players[client_id]
            player.moving_directions = {"w": False, "a": False, "s": False, "d": False}
            player.last_client_update = time.time()
            player.use_client_position = True
            
            # 使用客户端发送的停止位置
            if message.position:
                new_x = max(0, min(SCREEN_WIDTH, message.position["x"]))
                new_y = max(0, min(SCREEN_HEIGHT, message.position["y"]))
                player.position = {"x": new_x, "y": new_y}
            
            # 立即广播停止消息（事件驱动）
            await self.broadcast_to_room(self.default_room_id, message, exclude=client_id)
    
    async def handle_player_shoot(self, websocket: WebSocketServerProtocol, client_id: str, message: PlayerShootMessage):
        """处理玩家射击"""
        if client_id in self.players:
            player = self.players[client_id]
            
            # 找到玩家所在的房间
            player_room = None
            for room in self.rooms.values():
                if client_id in room.players:
                    player_room = room
                    break
            
            if not player_room:
                print(f"⚠️ Player {client_id} not found in any room")
                return
            
            # 创建子弹 - 使用共享实体类的新接口
            bullet_data = {
                'bullet_id': message.bullet_id,
                'owner_id': client_id,
                'position': message.position,
                'velocity': {"x": message.direction["x"] * BULLET_SPEED, "y": message.direction["y"] * BULLET_SPEED},
                'damage': 25
            }
            bullet = Bullet(bullet_data)
            player_room.add_bullet(bullet)
            
            # 立即广播子弹发射消息（事件驱动）
            bullet_message = BulletFiredMessage(
                bullet_id=bullet.bullet_id,
                owner_id=bullet.owner_id,
                start_position=bullet.position,
                velocity=bullet.velocity,
                damage=bullet.damage
            )
            await self.broadcast_to_room(player_room.room_id, bullet_message)
            print(f"💥 Player {client_id} fired bullet in room {player_room.room_id}")
        else:
            print(f"⚠️ Player {client_id} not found for shooting")
    
    async def handle_ping(self, websocket: WebSocketServerProtocol, client_id: str, message: PingMessage):
        """处理 Ping"""
        pong_message = PongMessage(
            client_id=client_id,
            sequence=message.sequence,
            server_timestamp=time.time()
        )
        await self.send_message(websocket, pong_message)
    
    async def handle_create_room_request(self, websocket: WebSocketServerProtocol, client_id: str, message: CreateRoomRequestMessage):
        """处理创建房间请求"""
        # 生成唯一房间ID
        room_id = f"room_{int(time.time())}_{str(uuid.uuid4())[:8]}"
        
        # 创建新房间
        new_room = GameRoom(
            room_id=room_id,
            name=message.room_name,
            host_player_id=client_id,
            max_players=message.max_players
        )
        
        # 添加到房间字典
        self.rooms[room_id] = new_room
        
        print(f"🏠 Created room {room_id} '{message.room_name}' for host {client_id}")
        
        # 发送房间创建成功消息
        room_created_message = RoomCreatedMessage(
            room_id=room_id,
            room_name=message.room_name,
            creator_id=client_id,
            max_players=message.max_players,
            game_mode=message.game_mode
        )
        await self.send_message(websocket, room_created_message)
        
        print(f"📤 Sent room creation confirmation to {client_id}")
        
        # 注意：不在这里移动玩家，等待客户端发送 PlayerJoinMessage
    
    async def handle_room_list_request(self, websocket: WebSocketServerProtocol, client_id: str, message: RoomListRequestMessage):
        """处理房间列表请求"""
        # 只返回有玩家的房间，且排除默认房间如果为空
        room_list = []
        for room_id, room in self.rooms.items():
            if len(room.players) > 0:  # 只显示有玩家的房间
                room_info = {
                    'room_id': room_id,
                    'name': room.name,
                    'current_players': len(room.players),
                    'max_players': room.max_players,
                    'room_state': room.room_state,
                    'host_player_id': room.host_player_id
                }
                room_list.append(room_info)
        
        # 使用RoomListMessage发送响应
        room_list_message = RoomListMessage(
            rooms=room_list,
            total_players=len(self.players)
        )
        await self.send_message(websocket, room_list_message)
        print(f"📋 Sent room list to {client_id}: {len(room_list)} rooms")
    
    async def handle_room_disbanded(self, websocket: WebSocketServerProtocol, client_id: str, message):
        """处理房间解散请求"""

        if not isinstance(message, RoomDisbandedMessage):
            return
        
        room_id = message.room_id
        if room_id not in self.rooms:
            error_msg = create_error_message("ROOM_NOT_FOUND", f"Room {room_id} not found")
            await self.send_message(websocket, error_msg)
            return
        
        room = self.rooms[room_id]
        
        # 验证是否为房主
        if not room.is_host(client_id):
            error_msg = create_error_message("NOT_HOST", "Only the host can disband the room")
            await self.send_message(websocket, error_msg)
            return
        
        print(f"🗑️ Host {client_id} is disbanding room {room_id}")
        
        # 广播房间解散消息给所有房间内的玩家（除房主外）
        await self.broadcast_to_room(room_id, message, exclude=client_id)
        
        # 移除房间内所有玩家
        players_to_remove = list(room.players.keys())
        for player_id in players_to_remove:
            if player_id in self.players:
                del self.players[player_id]
                print(f"📤 Removed player {player_id} due to room disbandment")
        
        # 删除房间
        del self.rooms[room_id]
        print(f"🗑️ Room {room_id} disbanded and deleted")
        
        # 更新连接状态
        print(f"📊 After room disbandment - Remaining rooms: {len(self.rooms)}, Total players: {len(self.players)}")
    
    async def handle_slot_change_request(self, websocket: WebSocketServerProtocol, client_id: str, message: SlotChangeRequestMessage):
        """处理槽位切换请求"""
        if client_id not in self.players:
            error_msg = create_error_message("PLAYER_NOT_FOUND", "Player not found")
            await self.send_message(websocket, error_msg)
            return
        
        # 确保房间存在
        if message.room_id not in self.rooms:
            error_msg = create_error_message("ROOM_NOT_FOUND", f"Room {message.room_id} not found")
            await self.send_message(websocket, error_msg)
            return
        
        room = self.rooms[message.room_id]
        player = self.players[client_id]
        
        # 尝试切换槽位
        old_slot = player.slot_index
        if room.change_player_slot(client_id, message.target_slot):
            # 槽位切换成功
            slot_changed_message = SlotChangedMessage(
                player_id=client_id,
                old_slot=old_slot,
                new_slot=message.target_slot,
                room_id=message.room_id
            )
            
            # 广播槽位变更消息
            await self.broadcast_to_room(message.room_id, slot_changed_message)
            
            # 发送更新的房间状态
            room_update_message = GameStateUpdateMessage(
                players=[p.to_dict() for p in room.players.values()],
                bullets=[],  # 房间大厅不需要子弹信息
                game_time=room.game_time,
                frame_id=room.frame_id
            )
            await self.broadcast_to_room(message.room_id, room_update_message)
            
            print(f"✅ Player {client_id} moved from slot {old_slot} to slot {message.target_slot}")
        else:
            # 槽位切换失败
            error_msg = create_error_message("SLOT_UNAVAILABLE", f"Slot {message.target_slot} is not available")
            await self.send_message(websocket, error_msg)
    
    async def handle_room_start_game(self, websocket: WebSocketServerProtocol, client_id: str, message: RoomStartGameMessage):
        """处理房间开始游戏消息"""
        room_id = message.room_id
        if room_id not in self.rooms:
            error_msg = create_error_message("ROOM_NOT_FOUND", f"Room {room_id} not found")
            await self.send_message(websocket, error_msg)
            return
        
        room = self.rooms[room_id]
        
        # 检查是否为房主
        if not room.is_host(client_id):
            error_msg = create_error_message("NOT_HOST", "Only the host can start the game")
            await self.send_message(websocket, error_msg)
            return
        
        # 启动游戏
        if room.start_game():
            print(f"🚀 Game started in room {room_id} by host {client_id}")
            
            # 广播游戏开始消息给房间内所有玩家
            await self.broadcast_to_room(room_id, message)
        else:
            error_msg = create_error_message("CANNOT_START", "Cannot start game in current room state")
            await self.send_message(websocket, error_msg)
    
    async def send_message(self, websocket: WebSocketServerProtocol, message: GameMessage):
        """发送消息给客户端"""
        try:
            await websocket.send(message.to_json())
        except Exception as e:
            print(f"❌ Error sending message: {e}")
    
    async def broadcast_to_room(self, room_id: str, message: GameMessage, exclude: Optional[str] = None):
        """广播消息给房间内的所有玩家"""
        if room_id not in self.rooms:
            return
        
        room = self.rooms[room_id]
        tasks = []
        
        for player_id, player in room.players.items():
            if exclude and player_id == exclude:
                continue
            
            tasks.append(self.send_message(player.websocket, message))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def broadcast_events(self, room_id: str, events: List[GameMessage]):
        """广播事件列表"""
        if not events:
            return
            
        for event in events:
            await self.broadcast_to_room(room_id, event)
            # 减少事件广播日志
            if event.type != GameMessageType.BULLET_DESTROYED:
                print(f"📡 Event {event.type} broadcasted to room {room_id}")
    
    async def game_loop(self):
        """游戏主循环 - 事件驱动架构"""
        target_fps = 60
        dt = 1.0 / target_fps
        
        print(f"🎮 Game loop started at {target_fps} FPS (Event-driven + Client Authority)")
        
        while self.running:
            loop_start = time.time()
            
            # 更新所有房间的游戏状态
            for room in self.rooms.values():
                if room.players:  # 只更新有玩家的房间
                    # 物理更新，获取事件
                    events = room.update_physics(dt)
                    
                    # 广播事件（碰撞、死亡、子弹销毁等）
                    if events:
                        await self.broadcast_events(room.room_id, events)
                    
                    # 大幅减少状态同步频率 - 每2秒一次兜底同步
                    if room.frame_id % 120 == 0:  # 每2秒检查一次
                        state_update = room.get_state_if_changed()
                        if state_update:
                            await self.broadcast_to_room(room.room_id, state_update)
                            print(f"🔄 Fallback state sync for room {room.room_id} (frame {room.frame_id})")
            
            # 控制帧率
            loop_time = time.time() - loop_start
            sleep_time = max(0, dt - loop_time)
            await asyncio.sleep(sleep_time)


async def main():
    """主函数"""
    server = TankGameServer()
    try:
        display_server_info(SERVER_HOST, SERVER_PORT)
        await server.start()
    except KeyboardInterrupt:
        print("\n🛑 Server shutting down...")
        await server.stop()


if __name__ == "__main__":
    print("🎯 Starting Tank Game Server...")
    asyncio.run(main()) 