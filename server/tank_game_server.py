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

# 添加共享目录到 Python 路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from tank_game_messages import (
    GameMessage, GameMessageType, parse_message,
    PlayerMoveMessage, PlayerStopMessage, PlayerShootMessage,
    PlayerJoinMessage, PlayerLeaveMessage, GameStateUpdateMessage,
    PlayerPositionUpdateMessage, BulletFiredMessage, BulletHitMessage,
    PlayerHitMessage, PlayerDestroyedMessage, ConnectionAckMessage,
    PingMessage, PongMessage, ErrorMessage, DebugMessage,
    create_error_message, create_debug_message,
    BulletDestroyedMessage, CollisionMessage, PlayerDeathMessage
)

# 导入共享的实体类
from tank_game_entities import Player, Bullet

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

class GameRoom:
    """游戏房间"""
    
    def __init__(self, room_id: str, name: str, max_players: int = None):
        self.room_id = room_id
        self.name = name
        self.max_players = max_players if max_players is not None else MAX_PLAYERS_PER_ROOM
        self.players: Dict[str, Player] = {}
        self.bullets: Dict[str, Bullet] = {}
        self.game_time = 0.0
        self.frame_id = 0
        self.last_update = time.time()
        # 事件驱动相关
        self.pending_events: List[GameMessage] = []
        self.state_changed = False
        
    def add_player(self, player: Player) -> bool:
        """添加玩家到房间"""
        if len(self.players) >= self.max_players:
            return False
        
        self.players[player.player_id] = player
        self.state_changed = True
        return True
        
    def remove_player(self, player_id: str) -> bool:
        """从房间移除玩家"""
        if player_id in self.players:
            del self.players[player_id]
            self.state_changed = True
            return True
        return False
        
    def add_bullet(self, bullet: Bullet):
        """添加子弹"""
        self.bullets[bullet.bullet_id] = bullet
        self.state_changed = True
        
    def update_physics(self, dt: float) -> List[GameMessage]:
        """更新游戏物理，返回需要广播的事件消息"""
        self.game_time += dt
        self.frame_id += 1
        events = []
        
        # 更新玩家位置 - 修复：不覆盖客户端位置
        for player in self.players.values():
            if player.is_alive:
                # 检查是否有最近的客户端更新
                time_since_client_update = time.time() - player.last_client_update
                
                # 如果客户端更新太久（超过100ms），服务器接管位置计算
                if time_since_client_update > 0.1 and player.use_client_position:
                    print(f"⚠️ No recent client update for {player.name}, server taking over")
                    player.use_client_position = False
                
                # 只有在服务器接管时才更新位置
                if not player.use_client_position:
                    # 根据移动方向更新速度
                    speed = TANK_SPEED  # 使用环境变量
                    old_position = player.position.copy()
                    player.velocity = {"x": 0.0, "y": 0.0}
                    
                    if player.moving_directions["w"]:
                        player.velocity["y"] -= speed
                    if player.moving_directions["s"]:
                        player.velocity["y"] += speed
                    if player.moving_directions["a"]:
                        player.velocity["x"] -= speed
                    if player.moving_directions["d"]:
                        player.velocity["x"] += speed
                    
                    # 更新位置
                    player.position["x"] += player.velocity["x"] * dt
                    player.position["y"] += player.velocity["y"] * dt
                    
                    # 边界检查
                    player.position["x"] = max(0, min(SCREEN_WIDTH, player.position["x"]))
                    player.position["y"] = max(0, min(SCREEN_HEIGHT, player.position["y"]))
                    
                    # 检查位置是否发生变化
                    if (abs(old_position["x"] - player.position["x"]) > 1.0 or 
                        abs(old_position["y"] - player.position["y"]) > 1.0):
                        self.state_changed = True
        
        # 更新子弹
        bullets_to_remove = []
        for bullet_id, bullet in self.bullets.items():
            if not bullet.update(dt):
                bullets_to_remove.append(bullet_id)
        
        # 移除无效子弹并广播销毁事件
        for bullet_id in bullets_to_remove:
            if bullet_id in self.bullets:
                bullet = self.bullets[bullet_id]
                # 创建子弹销毁事件
                destroy_event = BulletDestroyedMessage(
                    bullet_id=bullet_id,
                    reason="expired" if time.time() - bullet.created_time > bullet.max_lifetime else "boundary"
                )
                events.append(destroy_event)
                del self.bullets[bullet_id]
                self.state_changed = True
        
        # 碰撞检测
        collision_events = self.check_collisions()
        events.extend(collision_events)
        
        return events
    
    def check_collisions(self) -> List[GameMessage]:
        """检查碰撞，返回碰撞事件"""
        events = []
        bullets_to_remove = []
        
        for bullet_id, bullet in self.bullets.items():
            for player_id, player in self.players.items():
                if (player.is_alive and 
                    player_id != bullet.owner_id and
                    self.is_collision(bullet.position, player.position, 20)):
                    
                    # 记录碰撞前的血量
                    old_health = player.health
                    
                    # 处理碰撞
                    player.health -= bullet.damage
                    bullets_to_remove.append(bullet_id)
                    
                    # 创建碰撞事件
                    collision_event = CollisionMessage(
                        bullet_id=bullet_id,
                        target_player_id=player_id,
                        damage_dealt=bullet.damage,
                        new_health=player.health,
                        collision_position=bullet.position.copy()
                    )
                    events.append(collision_event)
                    
                    # 创建子弹销毁事件
                    destroy_event = BulletDestroyedMessage(
                        bullet_id=bullet_id,
                        reason="collision"
                    )
                    events.append(destroy_event)
                    
                    # 检查玩家是否死亡
                    if player.health <= 0:
                        player.is_alive = False
                        player.health = 0
                        
                        # 创建玩家死亡事件
                        death_event = PlayerDeathMessage(
                            player_id=player_id,
                            killer_id=bullet.owner_id,
                            death_position=player.position.copy()
                        )
                        events.append(death_event)
                    
                    self.state_changed = True
                    break
        
        # 移除碰撞的子弹
        for bullet_id in bullets_to_remove:
            if bullet_id in self.bullets:
                del self.bullets[bullet_id]
        
        return events
    
    def is_collision(self, pos1: Dict[str, float], pos2: Dict[str, float], radius: float) -> bool:
        """检查两个位置是否碰撞"""
        dx = pos1["x"] - pos2["x"]
        dy = pos1["y"] - pos2["y"]
        distance = (dx * dx + dy * dy) ** 0.5
        return distance < radius
    
    def get_state_if_changed(self) -> Optional[GameStateUpdateMessage]:
        """如果状态发生变化，返回状态更新消息"""
        if self.state_changed:
            self.state_changed = False
            return GameStateUpdateMessage(
                players=[p.to_dict() for p in self.players.values()],
                bullets=[b.to_dict() for b in self.bullets.values()],
                game_time=self.game_time,
                frame_id=self.frame_id
            )
        return None
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "room_id": self.room_id,
            "name": self.name,
            "max_players": self.max_players,
            "current_players": len(self.players),
            "players": [player.to_dict() for player in self.players.values()],
            "bullets": [bullet.to_dict() for bullet in self.bullets.values()],
            "game_time": self.game_time,
            "frame_id": self.frame_id
        }


class TankGameServer:
    """坦克游戏服务器"""
    def __init__(self, host: str = None, port: int = None):
        self.host = host if host is not None else SERVER_HOST
        self.port = port if port is not None else SERVER_PORT
        self.clients: Dict[WebSocketServerProtocol, str] = {}  # websocket -> client_id
        self.players: Dict[str, Player] = {}  # player_id -> Player
        self.rooms: Dict[str, GameRoom] = {}  # room_id -> GameRoom
        self.default_room_id = "default"
        self.running = False
        self.game_loop_task: Optional[asyncio.Task] = None
        
        # 创建默认房间
        self.rooms[self.default_room_id] = GameRoom(
            self.default_room_id, "Default Room"
        )
        
        print(f"🎮 TankGameServer initialized on {self.host}:{self.port}")
        print(f"🎯 Game config: {SCREEN_WIDTH}x{SCREEN_HEIGHT}, Speed: {TANK_SPEED}")
    
    async def start(self):
        """启动服务器"""
        self.running = True
        
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
        # 移除玩家
        if client_id in self.players:
            player = self.players[client_id]
            
            # 从房间中移除
            for room in self.rooms.values():
                room.remove_player(client_id)
            
            # 广播玩家离开消息
            leave_message = PlayerLeaveMessage(
                player_id=client_id,
                reason="disconnected"
            )
            await self.broadcast_to_room(self.default_room_id, leave_message, exclude=client_id)
            
            del self.players[client_id]
        
        # 移除客户端
        if websocket in self.clients:
            del self.clients[websocket]
        
        print(f"🚪 Client {client_id} fully disconnected")
    
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
            GameMessageType.PLAYER_MOVE: self.handle_player_move,
            GameMessageType.PLAYER_STOP: self.handle_player_stop,
            GameMessageType.PLAYER_SHOOT: self.handle_player_shoot,
            GameMessageType.PING: self.handle_ping,
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
        
        # 加入默认房间
        room = self.rooms[self.default_room_id]
        if room.add_player(player):
            print(f"👤 Player {message.player_name} ({client_id}) joined")
            
            # 广播玩家加入消息给房间内其他玩家
            await self.broadcast_to_room(self.default_room_id, message, exclude=client_id)
            
            # 发送当前游戏状态给新玩家
            state_message = GameStateUpdateMessage(
                players=[p.to_dict() for p in room.players.values()],
                bullets=[b.to_dict() for b in room.bullets.values()],
                game_time=room.game_time,
                frame_id=room.frame_id
            )
            await self.send_message(websocket, state_message)
        else:
            error_msg = create_error_message("ROOM_FULL", "Room is full")
            await self.send_message(websocket, error_msg)
    
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
            room = self.rooms[self.default_room_id]
            
            # 创建子弹 - 使用共享实体类的新接口
            bullet_data = {
                'bullet_id': message.bullet_id,
                'owner_id': client_id,
                'position': message.position,
                'velocity': {"x": message.direction["x"] * BULLET_SPEED, "y": message.direction["y"] * BULLET_SPEED},
                'damage': 25
            }
            bullet = Bullet(bullet_data)
            room.add_bullet(bullet)
            
            # 立即广播子弹发射消息（事件驱动）
            bullet_message = BulletFiredMessage(
                bullet_id=bullet.bullet_id,
                owner_id=bullet.owner_id,
                start_position=bullet.position,
                velocity=bullet.velocity,
                damage=bullet.damage
            )
            await self.broadcast_to_room(self.default_room_id, bullet_message)
            print(f"💥 Player {client_id} shoot event broadcasted")
    
    async def handle_ping(self, websocket: WebSocketServerProtocol, client_id: str, message: PingMessage):
        """处理 Ping"""
        pong_message = PongMessage(
            client_id=client_id,
            sequence=message.sequence,
            server_timestamp=time.time()
        )
        await self.send_message(websocket, pong_message)
    
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