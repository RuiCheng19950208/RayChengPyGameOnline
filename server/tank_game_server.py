#!/usr/bin/env python3
"""
WebSocket server implementation for handling all game messages and managing game state
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

# Add shared directory to Python path - must be before importing custom modules
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
    GameVictoryMessage, GameDefeatMessage,
    SlotChangeRequestMessage, SlotChangedMessage, RoomStartGameMessage,
    CreateRoomRequestMessage, RoomCreatedMessage, RoomListRequestMessage,
    RoomListMessage, RoomDisbandedMessage, KeyStateChangeMessage
)

# Import shared entity classes
from tank_game_entities import Player, Bullet, GameRoom

# Load environment variables - use shared .env file from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Game configuration - keep consistent with client
SCREEN_WIDTH = int(os.getenv('SCREEN_WIDTH', 800))
SCREEN_HEIGHT = int(os.getenv('SCREEN_HEIGHT', 600))
FPS = int(os.getenv('FPS', 60))
TANK_SPEED = int(os.getenv('TANK_SPEED', 300))  # Critical: same speed as client
BULLET_SPEED = int(os.getenv('BULLET_SPEED', 300))
BULLET_DAMAGE = int(os.getenv('BULLET_DAMAGE', 25))
BULLET_LIFETIME = float(os.getenv('BULLET_LIFETIME', 5.0))


SERVER_HOST = '0.0.0.0'  # Default listen on all interfaces
SERVER_PORT = int(os.getenv('SERVER_PORT', 8765))
MAX_PLAYERS_PER_ROOM = int(os.getenv('MAX_PLAYERS_PER_ROOM', 8))

def get_local_ip():
    """Automatically get local LAN IP address"""
    try:
        # Method 1: Connect to remote address to get local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        try:
            # Method 2: Get IP from hostname
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            if not local_ip.startswith('127.'):
                return local_ip
        except Exception:
            pass
    
    # Method 3: Iterate through all network interfaces
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
    """Display server connection information"""
    print("=" * 60)
    print("🎮 Tank Game Server Started Successfully!")
    print("=" * 60)
    
    if host == '0.0.0.0':
        local_ip = get_local_ip()
        print(f"🖥️  Server Host: {host} (listening on all interfaces)")
        print(f"🌐 Local IP: {local_ip}")
        print(f"🔌 Port: {port}")
        print(f"📊 Status Port: {port + 1}")  # HTTP status port
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
    """Simple HTTP status handler"""
    
    def __init__(self, server_instance, *args, **kwargs):
        self.server_instance = server_instance
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests"""
        if self.path == '/status':
            # Return server status JSON - only count joinable rooms
            total_players = len(self.server_instance.players)
            
            # Only count waiting rooms with players (joinable rooms)
            joinable_rooms = [
                r for r in self.server_instance.rooms.values() 
                if len(r.players) > 0 and r.room_state == "waiting"
            ]
            joinable_players = sum(len(r.players) for r in joinable_rooms)
            
            status = {
                'players': joinable_players,  # Only return players in joinable rooms
                'max_players': MAX_PLAYERS_PER_ROOM * len(self.server_instance.rooms),
                'rooms': len(joinable_rooms),  # Only return joinable rooms
                'server_version': '1.0.0',
                'status': 'online'
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')  # Allow CORS
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
            
            # Detailed debug information
            print(f"📊 Status query: {len(joinable_rooms)} joinable rooms, {joinable_players} joinable players")
            print(f"📊 Total rooms: {len(self.server_instance.rooms)}, Total players: {total_players}")
            for room_id, room in self.server_instance.rooms.items():
                print(f"📊   Room {room_id}: {len(room.players)} players, state={room.room_state}, host={room.host_player_id}")
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        """Disable HTTP log output"""
        pass

class TankGameServer:
    """Tank game server"""
    def __init__(self, host: str = None, port: int = None):
        self.host = host if host is not None else SERVER_HOST
        self.port = port if port is not None else SERVER_PORT
        self.status_port = self.port + 1  # HTTP status port
        self.clients: Dict[WebSocketServerProtocol, str] = {}  # websocket -> client_id
        self.players: Dict[str, Player] = {}  # player_id -> Player
        self.rooms: Dict[str, GameRoom] = {}  # room_id -> GameRoom
        self.running = False
        self.game_loop_task: Optional[asyncio.Task] = None
        self.http_server = None
        self.http_thread = None
        
        # Don't create default room - rooms should be created on demand
        
        print(f"🎮 TankGameServer initialized on {self.host}:{self.port}")
        print(f"🎯 Game config: {SCREEN_WIDTH}x{SCREEN_HEIGHT}, Speed: {TANK_SPEED}")
    
    def start_status_server(self):
        """Start HTTP status server"""
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
        """Stop HTTP status server"""
        if self.http_server:
            self.http_server.shutdown()
            self.http_server.server_close()
        if self.http_thread:
            self.http_thread.join(timeout=1.0)
    
    async def start(self):
        """Start server"""
        self.running = True
        
        # Start HTTP status server
        self.start_status_server()
        
        # Start game loop
        self.game_loop_task = asyncio.create_task(self.game_loop())
        
        # Start WebSocket server
        async with websockets.serve(self.handle_client, self.host, self.port):
            await asyncio.Future()  # Run forever
    
    async def stop(self):
        """Stop server"""
        self.running = False
        if self.game_loop_task:
            self.game_loop_task.cancel()
        self.stop_status_server()
        print("🛑 Server stopped")
    
    async def handle_client(self, websocket: WebSocketServerProtocol):
        """Handle client connections"""
        client_id = str(uuid.uuid4())
        self.clients[websocket] = client_id
        
        print(f"🔗 Client connected: {client_id}")
        
        # Send connection acknowledgment
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
        """Disconnect client"""
        print(f"🔌 Disconnecting client {client_id}...")
        
        # Remove player
        if client_id in self.players:
            player = self.players[client_id]
            player_name = player.name
            
            # Find and remove player from rooms
            rooms_to_delete = []
            rooms_to_disband = []
            
            for room_id, room in self.rooms.items():
                if client_id in room.players:
                    print(f"📤 Removing player {player_name} from room {room_id}")
                    
                    # Check if host
                    if room.is_host(client_id):
                        print(f"🗑️ Host {client_id} disconnected, disbanding room {room_id}")
                        
                        # Create room disbanded message
                        disband_message = RoomDisbandedMessage(
                            room_id=room_id,
                            disbanded_by=client_id,
                            reason="host_disconnected"
                        )
                        
                        # Broadcast to other players in room
                        await self.broadcast_to_room(room_id, disband_message, exclude=client_id)
                        
                        # Mark room for disbandment
                        rooms_to_disband.append(room_id)
                    else:
                        # Regular player leaving
                        room.remove_player(client_id)
                        
                        # Broadcast player leave message to other players in room
                        if len(room.players) > 0:
                            leave_message = PlayerLeaveMessage(
                                player_id=client_id,
                                reason="disconnected"
                            )
                            await self.broadcast_to_room(room_id, leave_message, exclude=client_id)
                        
                        # If room is empty, mark for deletion
                        if len(room.players) == 0:
                            rooms_to_delete.append(room_id)
                            print(f"🗑️ Room {room_id} is empty, marking for deletion")
            
            # Disband rooms where host left
            for room_id in rooms_to_disband:
                # Remove all other players from room
                if room_id in self.rooms:
                    room = self.rooms[room_id]
                    remaining_players = [pid for pid in room.players.keys() if pid != client_id]
                    for player_id in remaining_players:
                        if player_id in self.players:
                            del self.players[player_id]
                            print(f"📤 Removed player {player_id} due to host disconnect")
                    
                    # Delete room
                    del self.rooms[room_id]
                    print(f"🗑️ Room {room_id} disbanded due to host disconnect")
            
            # Delete other empty rooms
            for room_id in rooms_to_delete:
                if room_id in self.rooms:
                    del self.rooms[room_id]
                    print(f"🗑️ Deleted empty room: {room_id}")
            
            # Remove from players dictionary
            del self.players[client_id]
            print(f"✅ Player {player_name} ({client_id}) completely removed")
        
        # Remove client
        if websocket in self.clients:
            del self.clients[websocket]
        
        print(f"🚪 Client {client_id} fully disconnected")
        
        # Detailed room status debug info
        active_rooms = [r for r in self.rooms.values() if len(r.players) > 0]
        waiting_rooms = [r for r in self.rooms.values() if len(r.players) > 0 and r.room_state == "waiting"]
        print(f"📊 After disconnect - Active rooms: {len(active_rooms)}, Waiting rooms: {len(waiting_rooms)}, Total players: {len(self.players)}")
        
        # Show status of each room with players
        for room_id, room in self.rooms.items():
            if len(room.players) > 0:
                player_names = [p.name for p in room.players.values()]
                print(f"📊   Room {room_id}: {len(room.players)} players {player_names}, state={room.room_state}, host={room.host_player_id}")
        
        if len(self.rooms) == 0:
            print("📊 No rooms remaining - all rooms cleaned up successfully")
    
    async def handle_message(self, websocket: WebSocketServerProtocol, client_id: str, raw_message: str):
        """Handle client messages"""
        try:
            message = parse_message(raw_message)
            if not message:
                error_msg = create_error_message("INVALID_MESSAGE", "Failed to parse message")
                await self.send_message(websocket, error_msg)
                return
            
            # Reduce log noise - only log important messages
            if message.type not in [GameMessageType.PING, GameMessageType.PLAYER_MOVE]:
                print(f"📨 Received {message.type} from {client_id}")
            
            # Route message to corresponding handler
            await self.route_message(websocket, client_id, message)
            
        except Exception as e:
            print(f"❌ Error handling message from {client_id}: {e}")
            error_msg = create_error_message("MESSAGE_ERROR", str(e))
            await self.send_message(websocket, error_msg)
    
    async def route_message(self, websocket: WebSocketServerProtocol, client_id: str, message: GameMessage):
        """Route messages to corresponding handlers"""
        handlers = {
            GameMessageType.PLAYER_JOIN: self.handle_player_join,
            GameMessageType.PLAYER_LEAVE: self.handle_player_leave,
            GameMessageType.PLAYER_MOVE: self.handle_player_move,
            GameMessageType.PLAYER_STOP: self.handle_player_stop,
            GameMessageType.KEY_STATE_CHANGE: self.handle_key_state_change,  # 新增按键事件处理
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
        """Handle player join"""
        # Create player - using new interface of shared entity class
        player_data = {
            'player_id': client_id,
            'name': message.player_name
        }
        player = Player(player_data, websocket)
        self.players[client_id] = player
        
        # Determine target room ID
        target_room_id = message.room_id
        if not target_room_id:
            # If no room ID specified, reject join
            error_msg = create_error_message("NO_ROOM_SPECIFIED", "No room ID specified")
            await self.send_message(websocket, error_msg)
            return
        
        # Ensure target room exists
        if target_room_id not in self.rooms:
            error_msg = create_error_message("ROOM_NOT_FOUND", f"Room {target_room_id} not found")
            await self.send_message(websocket, error_msg)
            return
        
        room = self.rooms[target_room_id]
        if room.add_player(player):
            print(f"👤 Player {message.player_name} ({client_id}) joined room {target_room_id} slot {player.slot_index}")
            
            # Broadcast player join message to other players in room
            await self.broadcast_to_room(target_room_id, message, exclude=client_id)
            
            # Send current game state to new player (including all players' slot info)
            state_message = GameStateUpdateMessage(
                players=[p.to_dict() for p in room.players.values()],
                bullets=[b.to_dict() for b in room.bullets.values()],
                game_time=room.game_time,
                frame_id=room.frame_id
            )
            await self.send_message(websocket, state_message)
            
            # Broadcast room update to all players
            room_update_message = GameStateUpdateMessage(
                players=[p.to_dict() for p in room.players.values()],
                bullets=[],  # Room lobby doesn't need bullet info
                game_time=room.game_time,
                frame_id=room.frame_id
            )
            await self.broadcast_to_room(target_room_id, room_update_message)
        else:
            error_msg = create_error_message("ROOM_FULL", f"Room {target_room_id} is full")
            await self.send_message(websocket, error_msg)
    
    async def handle_player_leave(self, websocket: WebSocketServerProtocol, client_id: str, message: PlayerLeaveMessage):
        """Handle player active leave message"""
        print(f"👋 Player {client_id} is leaving (reason: {message.reason})")
        # Trigger disconnect handling logic
        await self.disconnect_client(websocket, client_id)
    
    async def handle_player_move(self, websocket: WebSocketServerProtocol, client_id: str, message: PlayerMoveMessage):
        """Handle player movement - 服务器权威位置计算"""
        if client_id in self.players:
            player = self.players[client_id]
            current_time = time.time()
            
            # 检查移动方向是否真的改变了
            directions_changed = player.moving_directions != message.direction
            
            # 更新玩家移动方向（服务器是状态权威）
            player.moving_directions = message.direction
            player.last_client_update = current_time
            
            # 服务器不信任客户端位置，只信任移动方向
            # 服务器基于自己的算法计算位置
            dt = current_time - player.last_update
            if dt > 0.1:  # 限制最大dt，避免大幅跳跃
                dt = 0.1
            
            # 使用服务器端统一的位置算法
            self._update_player_position_server_authoritative(player, dt)
            player.last_update = current_time
            
            # 找到玩家所在房间
            player_room = None
            for room in self.rooms.values():
                if client_id in room.players:
                    player_room = room
                    break
            
            if player_room:
                # 立即广播服务器计算的权威位置
                authoritative_event = PlayerMoveMessage(
                    player_id=client_id,
                    direction=message.direction,
                    position=player.position.copy()  # 使用服务器计算的位置
                )
                
                # 广播给房间内所有玩家（包括发送者，确保位置一致）
                await self.broadcast_to_room(player_room.room_id, authoritative_event)
                
                if directions_changed:
                    moving_keys = [k for k, v in message.direction.items() if v]
                    print(f"🎮 Server authoritative move: {client_id} {moving_keys} at ({player.position['x']:.1f}, {player.position['y']:.1f})")
            else:
                print(f"⚠️ Player {client_id} not found in any room for movement")
    
    def _update_player_position_server_authoritative(self, player: Player, dt: float):
        """服务器权威位置计算 - 确保所有客户端看到相同结果"""
        speed = TANK_SPEED
        velocity = {"x": 0.0, "y": 0.0}
        
        # 基于移动方向计算速度（与客户端完全相同的算法）
        if player.moving_directions["w"]:
            velocity["y"] -= speed
        if player.moving_directions["s"]:
            velocity["y"] += speed
        if player.moving_directions["a"]:
            velocity["x"] -= speed
        if player.moving_directions["d"]:
            velocity["x"] += speed
        
        # 更新位置
        player.position["x"] += velocity["x"] * dt
        player.position["y"] += velocity["y"] * dt
        
        # 边界检查
        player.position["x"] = max(0, min(SCREEN_WIDTH, player.position["x"]))
        player.position["y"] = max(0, min(SCREEN_HEIGHT, player.position["y"]))
    
    async def handle_player_stop(self, websocket: WebSocketServerProtocol, client_id: str, message: PlayerStopMessage):
        """Handle player stop - 服务器权威停止位置"""
        if client_id in self.players:
            player = self.players[client_id]
            current_time = time.time()
            
            # 更新玩家状态
            player.moving_directions = {"w": False, "a": False, "s": False, "d": False}
            player.last_client_update = current_time
            
            # 服务器计算最终停止位置（不信任客户端位置）
            dt = current_time - player.last_update
            if dt > 0.1:
                dt = 0.1
            
            # 使用服务器最后的移动计算最终位置
            self._update_player_position_server_authoritative(player, dt)
            player.last_update = current_time
            
            # 找到玩家所在房间
            player_room = None
            for room in self.rooms.values():
                if client_id in room.players:
                    player_room = room
                    break
            
            if player_room:
                # 广播服务器权威的停止位置
                authoritative_stop = PlayerStopMessage(
                    player_id=client_id,
                    position=player.position.copy()  # 服务器计算的权威位置
                )
                
                # 广播给房间内所有玩家（包括发送者）
                await self.broadcast_to_room(player_room.room_id, authoritative_stop)
                print(f"🛑 Server authoritative stop: {client_id} at ({player.position['x']:.1f}, {player.position['y']:.1f})")
            else:
                print(f"⚠️ Player {client_id} not found in any room for stop")
    
    async def handle_player_shoot(self, websocket: WebSocketServerProtocol, client_id: str, message: PlayerShootMessage):
        """Handle player shooting - 优化：射击不触发位置同步"""
        if client_id in self.players:
            player = self.players[client_id]
            
            # Find player's room
            player_room = None
            for room in self.rooms.values():
                if client_id in room.players:
                    player_room = room
                    break
            
            if not player_room:
                print(f"⚠️ Player {client_id} not found in any room")
                return
            
            # 使用客户端提供的射击位置，不更新玩家位置
            # 这避免了射击时的位置跳跃
            shoot_position = message.position.copy()
            
            # Create bullet - using new interface of shared entity class
            bullet_data = {
                'bullet_id': message.bullet_id,
                'owner_id': client_id,
                'position': shoot_position,  # 使用射击位置，不是玩家当前位置
                'velocity': {"x": message.direction["x"] * BULLET_SPEED, "y": message.direction["y"] * BULLET_SPEED},
                'damage': 25
            }
            bullet = Bullet(bullet_data)
            player_room.add_bullet(bullet)
            
            # Immediately broadcast bullet fired message (event-driven)
            bullet_message = BulletFiredMessage(
                bullet_id=bullet.bullet_id,
                owner_id=bullet.owner_id,
                start_position=bullet.position,
                velocity=bullet.velocity,
                damage=bullet.damage
            )
            await self.broadcast_to_room(player_room.room_id, bullet_message)
            print(f"💥 Player {client_id} fired bullet (no position sync)")
        else:
            print(f"⚠️ Player {client_id} not found for shooting")
    
    async def handle_ping(self, websocket: WebSocketServerProtocol, client_id: str, message: PingMessage):
        """Handle Ping"""
        pong_message = PongMessage(
            client_id=client_id,
            sequence=message.sequence,
            server_timestamp=time.time()
        )
        await self.send_message(websocket, pong_message)
    
    async def handle_create_room_request(self, websocket: WebSocketServerProtocol, client_id: str, message: CreateRoomRequestMessage):
        """Handle create room request"""
        # Generate unique room ID
        room_id = f"room_{int(time.time())}_{str(uuid.uuid4())[:8]}"
        
        # Create new room
        new_room = GameRoom(
            room_id=room_id,
            name=message.room_name,
            host_player_id=client_id,
            max_players=message.max_players
        )
        
        # Add to room dictionary
        self.rooms[room_id] = new_room
        
        print(f"🏠 Created room {room_id} '{message.room_name}' for host {client_id}")
        
        # Send room creation success message
        room_created_message = RoomCreatedMessage(
            room_id=room_id,
            room_name=message.room_name,
            creator_id=client_id,
            max_players=message.max_players,
            game_mode=message.game_mode
        )
        await self.send_message(websocket, room_created_message)
        
        print(f"📤 Sent room creation confirmation to {client_id}")
        
        # Note: Don't move player here, wait for client to send PlayerJoinMessage
    
    async def handle_room_list_request(self, websocket: WebSocketServerProtocol, client_id: str, message: RoomListRequestMessage):
        """Handle room list request"""
        # Only return rooms with players, exclude empty default room
        room_list = []
        for room_id, room in self.rooms.items():
            if len(room.players) > 0:  # Only show rooms with players
                room_info = {
                    'room_id': room_id,
                    'name': room.name,
                    'current_players': len(room.players),
                    'max_players': room.max_players,
                    'room_state': room.room_state,
                    'host_player_id': room.host_player_id
                }
                room_list.append(room_info)
        
        # Send response using RoomListMessage
        room_list_message = RoomListMessage(
            rooms=room_list,
            total_players=len(self.players)
        )
        await self.send_message(websocket, room_list_message)
        print(f"📋 Sent room list to {client_id}: {len(room_list)} rooms")
    
    async def handle_room_disbanded(self, websocket: WebSocketServerProtocol, client_id: str, message):
        """Handle room disband request"""

        if not isinstance(message, RoomDisbandedMessage):
            return
        
        room_id = message.room_id
        if room_id not in self.rooms:
            error_msg = create_error_message("ROOM_NOT_FOUND", f"Room {room_id} not found")
            await self.send_message(websocket, error_msg)
            return
        
        room = self.rooms[room_id]
        
        # Verify if host
        if not room.is_host(client_id):
            error_msg = create_error_message("NOT_HOST", "Only the host can disband the room")
            await self.send_message(websocket, error_msg)
            return
        
        print(f"🗑️ Host {client_id} is disbanding room {room_id}")
        
        # Broadcast room disband message to all players in room (except host)
        await self.broadcast_to_room(room_id, message, exclude=client_id)
        
        # Remove all players from room
        players_to_remove = list(room.players.keys())
        for player_id in players_to_remove:
            if player_id in self.players:
                del self.players[player_id]
                print(f"📤 Removed player {player_id} due to room disbandment")
        
        # Delete room
        del self.rooms[room_id]
        print(f"🗑️ Room {room_id} disbanded and deleted")
        
        # Update connection status
        print(f"📊 After room disbandment - Remaining rooms: {len(self.rooms)}, Total players: {len(self.players)}")
    
    async def handle_slot_change_request(self, websocket: WebSocketServerProtocol, client_id: str, message: SlotChangeRequestMessage):
        """Handle slot change request"""
        if client_id not in self.players:
            error_msg = create_error_message("PLAYER_NOT_FOUND", "Player not found")
            await self.send_message(websocket, error_msg)
            return
        
        # Ensure room exists
        if message.room_id not in self.rooms:
            error_msg = create_error_message("ROOM_NOT_FOUND", f"Room {message.room_id} not found")
            await self.send_message(websocket, error_msg)
            return
        
        room = self.rooms[message.room_id]
        player = self.players[client_id]
        
        # Try to change slot
        old_slot = player.slot_index
        if room.change_player_slot(client_id, message.target_slot):
            # Slot change successful
            slot_changed_message = SlotChangedMessage(
                player_id=client_id,
                old_slot=old_slot,
                new_slot=message.target_slot,
                room_id=message.room_id
            )
            
            # Broadcast slot change message
            await self.broadcast_to_room(message.room_id, slot_changed_message)
            
            # Send updated room state
            room_update_message = GameStateUpdateMessage(
                players=[p.to_dict() for p in room.players.values()],
                bullets=[],  # Room lobby doesn't need bullet info
                game_time=room.game_time,
                frame_id=room.frame_id
            )
            await self.broadcast_to_room(message.room_id, room_update_message)
            
            print(f"✅ Player {client_id} moved from slot {old_slot} to slot {message.target_slot}")
        else:
            # Slot change failed
            error_msg = create_error_message("SLOT_UNAVAILABLE", f"Slot {message.target_slot} is not available")
            await self.send_message(websocket, error_msg)
    
    async def handle_room_start_game(self, websocket: WebSocketServerProtocol, client_id: str, message: RoomStartGameMessage):
        """Handle room start game message"""
        room_id = message.room_id
        if room_id not in self.rooms:
            error_msg = create_error_message("ROOM_NOT_FOUND", f"Room {room_id} not found")
            await self.send_message(websocket, error_msg)
            return
        
        room = self.rooms[room_id]
        
        # Check if host
        if not room.is_host(client_id):
            error_msg = create_error_message("NOT_HOST", "Only the host can start the game")
            await self.send_message(websocket, error_msg)
            return
        
        # Start game
        if room.start_game():
            print(f"🚀 Game started in room {room_id} by host {client_id}")
            
            # Broadcast game start message to all players in room
            await self.broadcast_to_room(room_id, message)
        else:
            error_msg = create_error_message("CANNOT_START", "Cannot start game in current room state")
            await self.send_message(websocket, error_msg)
    
    async def send_message(self, websocket: WebSocketServerProtocol, message: GameMessage):
        """Send message to client"""
        try:
            await websocket.send(message.to_json())
        except Exception as e:
            print(f"❌ Error sending message: {e}")
    
    async def send_message_to_player(self, player_id: str, message: GameMessage):
        """Send message to specific player"""
        if player_id in self.players:
            player = self.players[player_id]
            if player.websocket:
                await self.send_message(player.websocket, message)
    
    async def broadcast_to_room(self, room_id: str, message: GameMessage, exclude: Optional[str] = None):
        """Broadcast message to all players in room"""
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
        """Broadcast event list"""
        if not events:
            return
            
        for event in events:
            # Handle victory/defeat messages - send to specific players
            if event.type == GameMessageType.GAME_VICTORY:
                # Send victory message only to the winner
                await self.send_message_to_player(event.winner_player_id, event)
                print(f"🏆 Victory message sent to {event.winner_player_name}")
            elif event.type == GameMessageType.GAME_DEFEAT:
                # Send defeat message only to the eliminated player
                await self.send_message_to_player(event.eliminated_player_id, event)
                print(f"💔 Defeat message sent to {event.eliminated_player_name}")
            else:
                # Broadcast other events to all players in room
                await self.broadcast_to_room(room_id, event)
                # Reduce event broadcast logs
                if event.type != GameMessageType.BULLET_DESTROYED:
                    print(f"📡 Event {event.type} broadcasted to room {room_id}")
    
    async def handle_key_state_change(self, websocket: WebSocketServerProtocol, client_id: str, message):
        """处理按键状态变化 - 确定性同步的核心"""
        if not isinstance(message, KeyStateChangeMessage):
            return
        
        if client_id in self.players:
            player = self.players[client_id]
            current_time = time.time()
            
            # 更新玩家按键状态
            old_directions = player.moving_directions.copy()
            player.moving_directions = message.key_states.copy()
            player.last_client_update = current_time
            
            # 如果客户端提供了位置，用于校验（不完全信任）
            if message.position:
                # 简单的位置校验和校正
                client_pos = message.position
                server_pos = player.position
                
                dx = abs(client_pos["x"] - server_pos["x"])
                dy = abs(client_pos["y"] - server_pos["y"])
                
                # 如果差异不大，接受客户端位置
                if dx < 30.0 and dy < 30.0:
                    player.position = client_pos.copy()
                else:
                    print(f"⚠️ Position mismatch for {client_id}: client({client_pos['x']:.1f}, {client_pos['y']:.1f}) vs server({server_pos['x']:.1f}, {server_pos['y']:.1f})")
            
            # 找到玩家所在房间
            player_room = None
            for room in self.rooms.values():
                if client_id in room.players:
                    player_room = room
                    break
            
            if player_room:
                # 创建服务器权威的按键事件消息
                authoritative_event = KeyStateChangeMessage(
                    player_id=client_id,
                    key_states=message.key_states.copy(),
                    timestamp=current_time,  # 使用服务器时间戳
                    position=player.position.copy()  # 服务器权威位置
                )
                
                # 广播给房间内所有玩家（包括发送者，确保时间戳一致）
                await self.broadcast_to_room(player_room.room_id, authoritative_event)
                
                # 调试信息
                moving_keys = [k for k, v in message.key_states.items() if v]
                if moving_keys != [k for k, v in old_directions.items() if v]:
                    if moving_keys:
                        print(f"🎮 Key event: {client_id} pressing {moving_keys}")
                    else:
                        print(f"🛑 Key event: {client_id} stopped")
            else:
                print(f"⚠️ Player {client_id} not found in any room for key event")
        else:
            print(f"⚠️ Player {client_id} not found for key event")
    
    async def game_loop(self):
        """Main game loop - 简化的确定性同步版本"""
        target_fps = 60
        dt = 1.0 / target_fps
        
        print(f"🎮 Game loop started at {target_fps} FPS (Deterministic Key-Event Sync)")
        
        while self.running:
            loop_start = time.time()
            
            # Update game state for all rooms
            for room in self.rooms.values():
                if room.players:  # Only update rooms with players
                    # 服务器端确定性位置更新
                    self._update_all_players_deterministic(room, dt)
                    
                    # Physics update, get events
                    events = room.update_physics(dt)
                    
                    # Broadcast events (collisions, deaths, bullet destruction, etc.)
                    if events:
                        await self.broadcast_events(room.room_id, events)
                    
                    # 大幅减少位置同步频率 - 主要依赖按键事件
                    if room.room_state == "playing":
                        # 游戏中：每120帧同步一次位置（每2秒，仅用于防止累积误差）
                        if room.frame_id % 120 == 0:
                            await self._broadcast_position_correction(room)
                    else:
                        # 等待状态：每180帧同步一次（每3秒）
                        if room.frame_id % 180 == 0:
                            state_update = room.get_state_if_changed()
                            if state_update:
                                await self.broadcast_to_room(room.room_id, state_update)
            
            # Control frame rate
            loop_time = time.time() - loop_start
            sleep_time = max(0, dt - loop_time)
            await asyncio.sleep(sleep_time)
    
    def _update_all_players_deterministic(self, room, dt: float):
        """确定性更新所有玩家位置"""
        current_time = time.time()
        
        for player in room.players.values():
            # 基于当前按键状态更新位置
            if any(player.moving_directions.values()):
                actual_dt = current_time - player.last_update
                if actual_dt > 0.01:  # 最小更新间隔10ms
                    if actual_dt > 0.1:  # 限制最大dt
                        actual_dt = 0.1
                    
                    self._update_player_position_server_authoritative(player, actual_dt)
                    player.last_update = current_time
    
    async def _broadcast_position_correction(self, room):
        """广播位置校正 - 仅用于防止累积误差"""
        # 只在有显著位置差异时才发送校正
        corrections_needed = []
        
        for player in room.players.values():
            # 检查是否需要位置校正（这里可以添加更复杂的逻辑）
            if any(player.moving_directions.values()):
                corrections_needed.append(player)
        
        if corrections_needed:
            # 发送轻量级的位置校正消息
            correction_state = GameStateUpdateMessage(
                players=[p.to_dict() for p in corrections_needed],
                bullets=[],  # 位置校正不包含子弹信息
                game_time=room.game_time,
                frame_id=room.frame_id
            )
            
            await self.broadcast_to_room(room.room_id, correction_state)
            print(f"🔧 Position correction: {len(corrections_needed)}/{len(room.players)} players")


async def main():
    """Main function"""
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