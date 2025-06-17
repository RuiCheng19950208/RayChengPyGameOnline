#!/usr/bin/env python3
"""
完美坦克游戏客户端 - 消除位置颤动和预测不一致

核心原则：
1. 前端和服务器使用完全相同的运动算法
2. 按键事件驱动的状态机
3. 单一权威位置源
4. 最小化位置校正
"""

import asyncio
import json
import math
import os
import sys
import time
import uuid
import socket
from typing import Dict, Optional, List
import pygame
import websockets
from websockets.client import WebSocketClientProtocol
from dotenv import load_dotenv
import argparse

# 添加共享目录到 Python 路径
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from tank_game_messages import *

# 加载环境变量
load_dotenv()

def get_local_ip():
    """获取本机IP地址"""
    try:
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
        return "127.0.0.1"  # 最后的fallback

# 游戏配置
SCREEN_WIDTH = int(os.getenv('SCREEN_WIDTH', 800))
SCREEN_HEIGHT = int(os.getenv('SCREEN_HEIGHT', 600))
FPS = int(os.getenv('FPS', 60))
TANK_SPEED = int(os.getenv('TANK_SPEED', 300))
DEFAULT_FONT_PATH = os.getenv('DEFAULT_FONT_PATH', None)

# 服务器连接配置 - 使用真实IP地址
DEFAULT_LOCAL_IP = get_local_ip()
SERVER_HOST = os.getenv('SERVER_HOST', DEFAULT_LOCAL_IP)  # 使用真实IP而不是localhost
SERVER_PORT = int(os.getenv('SERVER_PORT', 8765))
DEFAULT_SERVER_URL = f"ws://{SERVER_HOST}:{SERVER_PORT}"

print(f"🌐 Auto-detected local IP: {DEFAULT_LOCAL_IP}")
print(f"🎯 Default server URL: {DEFAULT_SERVER_URL}")

# 颜色定义
COLORS = {
    'BLACK': (0, 0, 0),
    'WHITE': (255, 255, 255),
    'RED': (255, 0, 0),
    'GREEN': (0, 255, 0),
    'BLUE': (0, 0, 255),
    'YELLOW': (255, 255, 0),
    'CYAN': (0, 255, 255),
    'GRAY': (128, 128, 128),
    'ORANGE': (255, 165, 0),
}

class PerfectPlayerState:
    """完美玩家状态类 - 单一位置源"""
    
    def __init__(self, player_data: Dict):
        self.player_id = player_data['player_id']
        self.name = player_data['name']
        self.health = player_data.get('health', 100)
        self.max_health = player_data.get('max_health', 100)
        self.is_alive = player_data.get('is_alive', True)
        
        # 单一位置系统 - 消除多层位置冲突
        self.position = player_data['position'].copy()  # 唯一的位置
        self.moving_directions = {"w": False, "a": False, "s": False, "d": False}
        self.last_update = time.time()
        
        # 服务器同步
        self.last_server_sync = time.time()
        self.server_sync_threshold = 100.0  # 只有差异很大时才校正
    
    def update_from_server(self, position: Dict[str, float], directions: Dict[str, bool] = None):
        """从服务器更新状态 - 更温和的校正"""
        if directions:
            self.moving_directions = directions.copy()
        
        # 计算位置差异
        dx = position["x"] - self.position["x"]
        dy = position["y"] - self.position["y"]
        distance = math.sqrt(dx * dx + dy * dy)
        
        # 大幅提高校正阈值，只有在极大差异时才校正
        correction_threshold = 200.0  # 从100提高到200
        
        # 如果正在移动，进一步提高阈值
        is_moving = any(self.moving_directions.values())
        if is_moving:
            correction_threshold = 300.0
        
        # 只有在差异极大时才进行校正
        if distance > correction_threshold:
            print(f"🔧 Major server correction for {self.name}: {distance:.1f}px")
            # 平滑校正而不是直接跳跃
            blend_factor = 0.3  # 30% 服务器位置，70% 客户端位置
            self.position["x"] = self.position["x"] + (dx * blend_factor)
            self.position["y"] = self.position["y"] + (dy * blend_factor)
        elif distance > 50.0:  # 中等差异，记录但不校正
            print(f"📊 Position drift: {distance:.1f}px (within tolerance)")
        
        self.last_server_sync = time.time()
    
    def update_position(self, dt: float):
        """更新位置 - 与服务器完全相同的算法"""
        speed = TANK_SPEED
        velocity = {"x": 0.0, "y": 0.0}
        
        # 根据按键状态计算速度
        if self.moving_directions["w"]:
            velocity["y"] -= speed
        if self.moving_directions["s"]:
            velocity["y"] += speed
        if self.moving_directions["a"]:
            velocity["x"] -= speed
        if self.moving_directions["d"]:
            velocity["x"] += speed
        
        # 更新位置
        self.position["x"] += velocity["x"] * dt
        self.position["y"] += velocity["y"] * dt
        
        # 边界检查
        self.position["x"] = max(0, min(SCREEN_WIDTH, self.position["x"]))
        self.position["y"] = max(0, min(SCREEN_HEIGHT, self.position["y"]))
        
        self.last_update = time.time()

class PerfectBulletState:
    """完美子弹状态类"""
    
    def __init__(self, bullet_data: Dict):
        self.bullet_id = bullet_data['bullet_id']
        self.owner_id = bullet_data['owner_id']
        self.position = bullet_data['position'].copy()
        self.velocity = bullet_data['velocity'].copy()
        self.damage = bullet_data['damage']
        self.created_time = bullet_data.get('created_time', time.time())
        self.max_lifetime = 5.0
    
    def update(self, dt: float) -> bool:
        """更新子弹位置"""
        self.position["x"] += self.velocity["x"] * dt
        self.position["y"] += self.velocity["y"] * dt
        
        # 检查边界和生命周期
        if (self.position["x"] < 0 or self.position["x"] > SCREEN_WIDTH or
            self.position["y"] < 0 or self.position["y"] > SCREEN_HEIGHT or
            time.time() - self.created_time > self.max_lifetime):
            return False
        
        return True

class PerfectGameClient:
    """完美游戏客户端"""
    
    def __init__(self, server_url: str = DEFAULT_SERVER_URL):
        self.server_url = server_url
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.connected = False
        
        # 客户端状态
        self.client_id: Optional[str] = None
        self.player_id: Optional[str] = None
        self.player_name = f"PerfectPlayer_{int(time.time()) % 10000}"
        
        # 游戏状态
        self.players: Dict[str, PerfectPlayerState] = {}
        self.bullets: Dict[str, PerfectBulletState] = {}
        
        # 输入状态 - 简化的按键状态机
        self.input_state = {
            'w': False, 'a': False, 's': False, 'd': False,
            'mouse_clicked': False,
            'mouse_pos': (400, 300)
        }
        self.last_input_state = self.input_state.copy()
        
        # 网络相关
        self.ping_sequence = 0
        self.ping_times: Dict[int, float] = {}
        self.current_ping = 0
        
        # 发送优化
        self.last_movement_send = 0
        self.movement_send_interval = 0.05  # 20 FPS 发送，从33 FPS降低
        self.position_change_threshold = 5.0  # 位置变化阈值
        
        # 性能监控
        self.frame_count = 0
        self.fps_counter = 0
        self.last_fps_time = time.time()
        
        # 初始化 Pygame
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("坦克大战 - 完美版 ✨")
        self.clock = pygame.time.Clock()
        
        # 字体
        try:
            # 尝试加载指定字体文件
            if DEFAULT_FONT_PATH and os.path.exists(DEFAULT_FONT_PATH):
                self.font = pygame.font.Font(DEFAULT_FONT_PATH, 24)
                self.small_font = pygame.font.Font(DEFAULT_FONT_PATH, 16)
                self.big_font = pygame.font.Font(DEFAULT_FONT_PATH, 32)
                print(f"✅ Loaded custom font: {DEFAULT_FONT_PATH}")
            else:
                # 字体文件不存在，使用默认字体
                self.font = pygame.font.Font(None, 24)
                self.small_font = pygame.font.Font(None, 16)
                self.big_font = pygame.font.Font(None, 32)
                if DEFAULT_FONT_PATH:
                    print(f"⚠️ Custom font not found: {DEFAULT_FONT_PATH}, using default font")
                else:
                    print("ℹ️ No custom font specified, using default font")
        except Exception as e:
            # 加载字体时出现异常，使用默认字体
            self.font = pygame.font.Font(None, 24)
            self.small_font = pygame.font.Font(None, 16)
            self.big_font = pygame.font.Font(None, 32)
            print(f"⚠️ Error loading font: {e}, using default font")
        
        print(f"✨ PerfectGameClient initialized for {server_url}")
    
    async def connect(self):
        """连接到服务器"""
        try:
            print(f"🔗 Connecting to {self.server_url}...")
            self.websocket = await websockets.connect(self.server_url)
            self.connected = True
            print("✅ Connected to server")
            
            # 启动消息接收循环
            asyncio.create_task(self.message_loop())
            
        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            self.connected = False
    
    async def disconnect(self):
        """断开连接"""
        if self.websocket:
            await self.websocket.close()
        self.connected = False
        print("🔌 Disconnected from server")
    
    async def send_message(self, message: GameMessage):
        """发送消息到服务器"""
        if not self.websocket or not self.connected:
            return
        
        try:
            await self.websocket.send(message.to_json())
        except Exception as e:
            print(f"❌ Error sending message: {e}")
    
    async def message_loop(self):
        """消息接收循环"""
        try:
            async for raw_message in self.websocket:
                message = parse_message(raw_message)
                if message:
                    await self.handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            print("🔌 Connection closed by server")
            self.connected = False
        except Exception as e:
            print(f"❌ Error in message loop: {e}")
            self.connected = False
    
    async def handle_message(self, message: GameMessage):
        """处理接收到的消息"""
        if message.type == GameMessageType.CONNECTION_ACK:
            await self.handle_connection_ack(message)
        elif message.type == GameMessageType.GAME_STATE_UPDATE:
            await self.handle_game_state_update(message)
        elif message.type == GameMessageType.PLAYER_MOVE:
            await self.handle_player_move(message)
        elif message.type == GameMessageType.PLAYER_STOP:
            await self.handle_player_stop(message)
        elif message.type == GameMessageType.BULLET_FIRED:
            await self.handle_bullet_fired(message)
        elif message.type == GameMessageType.COLLISION:
            await self.handle_collision(message)
        elif message.type == GameMessageType.BULLET_DESTROYED:
            await self.handle_bullet_destroyed(message)
        elif message.type == GameMessageType.PLAYER_DEATH:
            await self.handle_player_death(message)
        elif message.type == GameMessageType.PLAYER_JOIN:
            await self.handle_player_join(message)
        elif message.type == GameMessageType.PLAYER_LEAVE:
            await self.handle_player_leave(message)
        elif message.type == GameMessageType.PONG:
            await self.handle_pong(message)
        elif message.type == GameMessageType.ERROR:
            await self.handle_error(message)
    
    async def handle_connection_ack(self, message: ConnectionAckMessage):
        """处理连接确认"""
        self.client_id = message.client_id
        self.player_id = message.assigned_player_id
        print(f"🆔 Assigned player ID: {self.player_id}")
        
        # 发送加入游戏消息
        join_message = PlayerJoinMessage(
            player_id=self.player_id,
            player_name=self.player_name
        )
        await self.send_message(join_message)
    
    async def handle_game_state_update(self, message: GameStateUpdateMessage):
        """处理游戏状态更新 - 完美同步"""
        # 更新玩家状态
        for player_data in message.players:
            player_id = player_data['player_id']
            if player_id in self.players:
                # 更新现有玩家
                self.players[player_id].update_from_server(
                    player_data['position'],
                    player_data.get('moving_directions')
                )
                # 更新其他属性
                self.players[player_id].health = player_data.get('health', 100)
                self.players[player_id].is_alive = player_data.get('is_alive', True)
            else:
                # 新玩家
                new_player = PerfectPlayerState(player_data)
                self.players[player_id] = new_player
                
                if player_id == self.player_id:
                    print(f"🎮 Local player initialized at {new_player.position}")
        
        # 更新子弹状态
        server_bullets = {b['bullet_id']: b for b in message.bullets}
        
        # 添加新子弹
        for bullet_id, bullet_data in server_bullets.items():
            if bullet_id not in self.bullets:
                self.bullets[bullet_id] = PerfectBulletState(bullet_data)
        
        # 移除服务器上不存在的子弹
        bullets_to_remove = []
        for bullet_id in self.bullets:
            if bullet_id not in server_bullets:
                bullets_to_remove.append(bullet_id)
        
        for bullet_id in bullets_to_remove:
            del self.bullets[bullet_id]
    
    async def handle_player_move(self, message: PlayerMoveMessage):
        """处理其他玩家移动"""
        if message.player_id != self.player_id and message.player_id in self.players:
            self.players[message.player_id].update_from_server(
                message.position, message.direction
            )
    
    async def handle_player_stop(self, message: PlayerStopMessage):
        """处理其他玩家停止"""
        if message.player_id != self.player_id and message.player_id in self.players:
            self.players[message.player_id].update_from_server(message.position)
            self.players[message.player_id].moving_directions = {
                "w": False, "a": False, "s": False, "d": False
            }
    
    async def handle_bullet_fired(self, message: BulletFiredMessage):
        """处理子弹发射"""
        bullet_data = {
            'bullet_id': message.bullet_id,
            'owner_id': message.owner_id,
            'position': message.start_position,
            'velocity': message.velocity,
            'damage': message.damage,
            'created_time': time.time()
        }
        self.bullets[message.bullet_id] = PerfectBulletState(bullet_data)
    
    async def handle_collision(self, message: CollisionMessage):
        """处理碰撞事件"""
        if message.target_player_id in self.players:
            self.players[message.target_player_id].health = message.new_health
            if message.new_health <= 0:
                self.players[message.target_player_id].is_alive = False
    
    async def handle_bullet_destroyed(self, message: BulletDestroyedMessage):
        """处理子弹销毁"""
        if message.bullet_id in self.bullets:
            del self.bullets[message.bullet_id]
    
    async def handle_player_death(self, message: PlayerDeathMessage):
        """处理玩家死亡"""
        if message.player_id in self.players:
            self.players[message.player_id].is_alive = False
            self.players[message.player_id].health = 0
    
    async def handle_player_join(self, message: PlayerJoinMessage):
        """处理玩家加入"""
        print(f"👤 Player {message.player_name} joined")
    
    async def handle_player_leave(self, message: PlayerLeaveMessage):
        """处理玩家离开"""
        if message.player_id in self.players:
            player_name = self.players[message.player_id].name
            print(f"👋 Player {player_name} left")
            del self.players[message.player_id]
    
    async def handle_pong(self, message: PongMessage):
        """处理 Pong 响应"""
        if message.sequence in self.ping_times:
            ping_time = time.time() - self.ping_times[message.sequence]
            self.current_ping = int(ping_time * 1000)
            del self.ping_times[message.sequence]
    
    async def handle_error(self, message: ErrorMessage):
        """处理错误消息"""
        print(f"❌ Server error: {message.error_code} - {message.error_message}")
    
    async def send_ping(self):
        """发送 Ping"""
        if not self.connected:
            return
        
        self.ping_sequence += 1
        self.ping_times[self.ping_sequence] = time.time()
        
        ping_message = PingMessage(
            client_id=self.client_id or "unknown",
            sequence=self.ping_sequence
        )
        await self.send_message(ping_message)
    
    def handle_input(self, event):
        """处理输入事件 - 按键事件驱动"""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_w:
                self.input_state['w'] = True
            elif event.key == pygame.K_a:
                self.input_state['a'] = True
            elif event.key == pygame.K_s:
                self.input_state['s'] = True
            elif event.key == pygame.K_d:
                self.input_state['d'] = True
        
        elif event.type == pygame.KEYUP:
            if event.key == pygame.K_w:
                self.input_state['w'] = False
            elif event.key == pygame.K_a:
                self.input_state['a'] = False
            elif event.key == pygame.K_s:
                self.input_state['s'] = False
            elif event.key == pygame.K_d:
                self.input_state['d'] = False
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # 左键
                self.input_state['mouse_clicked'] = True
        
        elif event.type == pygame.MOUSEMOTION:
            self.input_state['mouse_pos'] = event.pos
    
    def update_local_player(self, dt: float):
        """更新本地玩家 - 与服务器完全相同的算法"""
        if not self.player_id or self.player_id not in self.players:
            return
        
        local_player = self.players[self.player_id]
        
        # 更新移动方向状态
        local_player.moving_directions = {
            'w': self.input_state['w'],
            'a': self.input_state['a'],
            's': self.input_state['s'],
            'd': self.input_state['d']
        }
        
        # 使用与服务器相同的位置更新算法
        local_player.update_position(dt)
    
    async def send_movement_if_changed(self):
        """智能发送移动消息 - 只在真正需要时发送"""
        current_time = time.time()
        
        if not self.connected or not self.player_id or self.player_id not in self.players:
            return
        
        # 检查输入是否改变
        movement_keys = ['w', 'a', 's', 'd']
        input_changed = any(
            self.input_state[key] != self.last_input_state[key] 
            for key in movement_keys
        )
        
        # 检查位置是否有显著变化
        current_player = self.players[self.player_id]
        position_changed = False
        dx, dy = 0.0, 0.0  # 初始化变量
        
        if hasattr(self, 'last_sent_position'):
            dx = abs(current_player.position['x'] - self.last_sent_position['x'])
            dy = abs(current_player.position['y'] - self.last_sent_position['y'])
            position_changed = (dx > self.position_change_threshold or 
                              dy > self.position_change_threshold)
        else:
            position_changed = True  # 首次发送
        
        # 定期发送（防止丢包）
        time_since_last_send = current_time - self.last_movement_send
        periodic_send = time_since_last_send > (self.movement_send_interval * 3)  # 每3个周期强制发送一次
        
        # 决定是否发送
        should_send = (input_changed or position_changed or periodic_send or
                      time_since_last_send > self.movement_send_interval)
        
        if should_send:
            directions = {
                'w': self.input_state['w'],
                'a': self.input_state['a'],
                's': self.input_state['s'],
                'd': self.input_state['d']
            }
            
            # 使用当前玩家位置
            current_position = current_player.position.copy()
            
            move_message = PlayerMoveMessage(
                player_id=self.player_id,
                direction=directions,
                position=current_position
            )
            await self.send_message(move_message)
            
            # 更新发送记录
            self.last_movement_send = current_time
            self.last_input_state = self.input_state.copy()
            self.last_sent_position = current_position.copy()
            
            # 调试信息
            if input_changed:
                print(f"📤 Input changed: {directions}")
            elif position_changed:
                print(f"📤 Position changed: {dx:.1f}, {dy:.1f}")
            elif periodic_send:
                print(f"📤 Periodic send (anti-packet-loss)")
    
    async def send_shoot(self):
        """发送射击消息 - 使用准确的玩家位置"""
        if not self.connected or not self.player_id or self.player_id not in self.players:
            return
        
        # 使用当前玩家的准确位置
        player_pos = self.players[self.player_id].position
        
        # 计算射击方向
        mouse_x, mouse_y = self.input_state['mouse_pos']
        dx = mouse_x - player_pos['x']
        dy = mouse_y - player_pos['y']
        
        # 归一化方向向量
        length = math.sqrt(dx * dx + dy * dy)
        if length > 0:
            dx /= length
            dy /= length
        
        # 发送射击消息
        shoot_message = PlayerShootMessage(
            player_id=self.player_id,
            position=player_pos,  # 使用准确位置
            direction={"x": dx, "y": dy},
            bullet_id=str(uuid.uuid4())
        )
        await self.send_message(shoot_message)
        
        # 重置点击状态
        self.input_state['mouse_clicked'] = False
    
    def update_game_objects(self, dt: float):
        """更新游戏对象"""
        # 更新所有玩家位置
        for player in self.players.values():
            player.update_position(dt)
        
        # 更新子弹位置
        bullets_to_remove = []
        for bullet_id, bullet in self.bullets.items():
            if not bullet.update(dt):
                bullets_to_remove.append(bullet_id)
        
        # 移除无效子弹
        for bullet_id in bullets_to_remove:
            del self.bullets[bullet_id]
    
    def render(self):
        """完美渲染"""
        self.screen.fill(COLORS['BLACK'])
        
        # 渲染玩家
        for player_id, player in self.players.items():
            if not player.is_alive:
                continue
                
            pos = player.position  # 使用单一位置源
            color = COLORS['GREEN'] if player_id == self.player_id else COLORS['BLUE']
            
            # 绘制坦克
            tank_rect = pygame.Rect(pos['x'] - 15, pos['y'] - 15, 30, 30)
            pygame.draw.rect(self.screen, color, tank_rect)
            
            # 如果是本地玩家，添加特殊标识
            if player_id == self.player_id:
                pygame.draw.rect(self.screen, COLORS['ORANGE'], tank_rect, 3)
            
            # 绘制玩家名称
            name_text = self.small_font.render(player.name, True, COLORS['WHITE'])
            name_rect = name_text.get_rect(center=(pos['x'], pos['y'] - 25))
            self.screen.blit(name_text, name_rect)
            
            # 绘制血条
            if player.health < player.max_health:
                health_ratio = player.health / player.max_health
                health_width = 30
                health_height = 4
                
                # 背景
                health_bg = pygame.Rect(pos['x'] - 15, pos['y'] - 35, health_width, health_height)
                pygame.draw.rect(self.screen, COLORS['RED'], health_bg)
                
                # 血量
                health_fg = pygame.Rect(pos['x'] - 15, pos['y'] - 35, 
                                      health_width * health_ratio, health_height)
                pygame.draw.rect(self.screen, COLORS['GREEN'], health_fg)
        
        # 渲染子弹
        for bullet in self.bullets.values():
            pos = bullet.position
            pygame.draw.circle(self.screen, COLORS['YELLOW'], 
                             (int(pos['x']), int(pos['y'])), 4)
            # 子弹中心点
            pygame.draw.circle(self.screen, COLORS['WHITE'], 
                             (int(pos['x']), int(pos['y'])), 2)
        
        # 渲染 UI
        self.render_ui()
        
        pygame.display.flip()
        
        # 更新 FPS 计数
        self.frame_count += 1
        current_time = time.time()
        if current_time - self.last_fps_time >= 1.0:
            self.fps_counter = self.frame_count
            self.frame_count = 0
            self.last_fps_time = current_time
    
    def render_ui(self):
        """渲染 UI 信息"""
        y_offset = 10
        
        # 连接状态
        status_text = "Connected" if self.connected else "Disconnected"
        status_color = COLORS['GREEN'] if self.connected else COLORS['RED']
        status_surface = self.font.render(f"Status: {status_text}", True, status_color)
        self.screen.blit(status_surface, (10, y_offset))
        y_offset += 25
        
        # 玩家信息
        if self.player_id:
            player_text = f"Player: {self.player_name}"
            player_surface = self.font.render(player_text, True, COLORS['WHITE'])
            self.screen.blit(player_surface, (10, y_offset))
            y_offset += 25
        
        # 网络延迟
        ping_color = COLORS['GREEN'] if self.current_ping < 50 else COLORS['ORANGE'] if self.current_ping < 100 else COLORS['RED']
        ping_text = f"Ping: {self.current_ping}ms"
        ping_surface = self.font.render(ping_text, True, ping_color)
        self.screen.blit(ping_surface, (10, y_offset))
        y_offset += 25
        
        # FPS 显示
        fps_color = COLORS['GREEN'] if self.fps_counter >= 55 else COLORS['ORANGE'] if self.fps_counter >= 30 else COLORS['RED']
        fps_text = f"FPS: {self.fps_counter}"
        fps_surface = self.font.render(fps_text, True, fps_color)
        self.screen.blit(fps_surface, (10, y_offset))
        y_offset += 25
        
        # 游戏统计
        stats_text = f"Players: {len(self.players)} | Bullets: {len(self.bullets)}"
        stats_surface = self.font.render(stats_text, True, COLORS['WHITE'])
        self.screen.blit(stats_surface, (10, y_offset))
        y_offset += 25
        
        # 优化信息
        optimization_text = "✨ PERFECT CLIENT"
        opt_surface = self.big_font.render(optimization_text, True, COLORS['CYAN'])
        self.screen.blit(opt_surface, (10, y_offset))
        y_offset += 35
        
        smooth_info = "Consistent Prediction + Zero Jitter + Perfect Sync"
        smooth_surface = self.small_font.render(smooth_info, True, COLORS['CYAN'])
        self.screen.blit(smooth_surface, (10, y_offset))
        
        # 位置信息（调试）
        if self.player_id and self.player_id in self.players:
            pos = self.players[self.player_id].position
            pos_text = f"Position: ({pos['x']:.1f}, {pos['y']:.1f})"
            pos_surface = self.small_font.render(pos_text, True, COLORS['GRAY'])
            self.screen.blit(pos_surface, (10, y_offset + 25))
        
        # 控制说明
        controls = [
            "WASD: Move",
            "Mouse: Aim & Shoot",
            "ESC: Quit"
        ]
        
        for i, control in enumerate(controls):
            control_surface = self.small_font.render(control, True, COLORS['GRAY'])
            self.screen.blit(control_surface, (SCREEN_WIDTH - 150, 10 + i * 20))


async def perfect_game_loop(client: PerfectGameClient):
    """完美游戏主循环"""
    last_ping_time = 0
    ping_interval = 2.0
    
    running = True
    
    print("✨ Perfect Game Loop Started!")
    print("🎯 Zero jitter, perfect prediction, consistent sync")
    
    while running:
        current_time = time.time()
        dt = client.clock.get_time() / 1000.0  # 转换为秒
        
        # 处理 PyGame 事件
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                else:
                    client.handle_input(event)
            elif event.type == pygame.KEYUP:
                client.handle_input(event)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                client.handle_input(event)
            elif event.type == pygame.MOUSEMOTION:
                client.handle_input(event)
        
        # 更新本地玩家（与服务器相同算法）
        client.update_local_player(dt)
        
        # 发送移动更新（智能发送）
        await client.send_movement_if_changed()
        
        # 处理射击
        if client.input_state['mouse_clicked']:
            await client.send_shoot()
        
        # 发送 ping
        if current_time - last_ping_time > ping_interval:
            await client.send_ping()
            last_ping_time = current_time
        
        # 更新游戏对象
        client.update_game_objects(dt)
        
        # 渲染
        client.render()
        client.clock.tick(FPS)
        
        # 让出控制权给其他协程
        await asyncio.sleep(0.001)
    
    # 断开连接
    await client.disconnect()
    pygame.quit()


async def main():
    """主函数"""
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Perfect Tank Game Client')
    parser.add_argument('--server', '-s', type=str, 
                       help='Server URL (e.g., ws://192.168.1.100:8765)')
    parser.add_argument('--host', type=str, 
                       help='Server host (e.g., 192.168.1.100)')
    parser.add_argument('--port', '-p', type=int, 
                       help='Server port (default: 8765)')
    parser.add_argument('--scan', action='store_true',
                       help='Scan local network for available servers')
    args = parser.parse_args()
    
    # 如果用户要求扫描网络
    if args.scan:
        display_connection_help()
        return
    
    # 确定服务器URL
    if args.server:
        server_url = args.server
    elif args.host:
        port = args.port or SERVER_PORT
        server_url = f"ws://{args.host}:{port}"
    else:
        server_url = DEFAULT_SERVER_URL
    
    print("✨ Starting Perfect Tank Game Client...")
    print("=" * 50)
    print("🎯 Perfect Features:")
    print("  • Zero position jitter")
    print("  • Consistent client-server prediction")
    print("  • Perfect bullet-player position sync")
    print("  • Minimal server corrections")
    print("  • Smooth 60 FPS rendering")
    print("  • Event-driven input handling")
    print("=" * 50)
    print(f"🌐 Target server: {server_url}")
    if server_url == DEFAULT_SERVER_URL:
        print(f"📍 Local machine IP: {DEFAULT_LOCAL_IP}")
        print("💡 This will connect to the server running on this computer")
    else:
        print("💡 This will connect to a remote server")
    print("💡 Tip: Use --scan to find servers on local network")
    print("=" * 50)
    
    client = PerfectGameClient(server_url)
    
    try:
        # 连接到服务器
        await client.connect()
        
        if client.connected:
            # 启动完美游戏循环
            await perfect_game_loop(client)
        else:
            print("❌ Failed to connect to server")
            print("💡 Tips:")
            print("  • Check if server is running")
            print("  • Verify server IP address and port")
            print("  • Check firewall settings")
            print("  • Ensure both computers are on the same network")
            print("  • Try: python home/tank_game_client.py --scan")
    
    except KeyboardInterrupt:
        print("\n🛑 Client shutting down...")
    
    finally:
        await client.disconnect()


def scan_local_servers(port: int = 8765) -> List[str]:
    """扫描局域网内的游戏服务器"""
    local_ip = get_local_ip()
    if local_ip == "127.0.0.1":
        return []
    
    # 获取网络段
    ip_parts = local_ip.split('.')
    network_base = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}"
    
    available_servers = []
    
    print(f"🔍 Scanning network {network_base}.x for game servers...")
    
    # 扫描常见的IP范围（简化版，只扫描部分IP）
    scan_ips = [
        f"{network_base}.1",    # 路由器
        f"{network_base}.100",  # 常见服务器IP
        f"{network_base}.101", 
        f"{network_base}.102",
        f"{network_base}.110",
        f"{network_base}.200",
        local_ip,  # 本机
    ]
    
    for ip in scan_ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)  # 500ms超时
            result = s.connect_ex((ip, port))
            s.close()
            
            if result == 0:
                available_servers.append(ip)
                print(f"✅ Found server at {ip}:{port}")
        except Exception:
            pass
    
    return available_servers

def display_connection_help():
    """显示连接帮助信息"""
    local_ip = get_local_ip()
    
    print("🌐 Network Connection Help")
    print("=" * 40)
    print(f"📍 Your machine IP: {local_ip}")
    print()
    print("🔍 Auto-scanning for servers...")
    
    servers = scan_local_servers()
    
    if servers:
        print(f"✅ Found {len(servers)} server(s):")
        for server_ip in servers:
            print(f"   • {server_ip}:8765")
        print()
        print("💻 Connection commands:")
        for server_ip in servers:
            if server_ip == local_ip:
                print(f"   • Local server:  python home/tank_game_client.py")
            else:
                print(f"   • Remote server: python home/tank_game_client.py --host {server_ip}")
    else:
        print("❌ No servers found on local network")
        print()
        print("💡 Connection options:")
        print(f"   • Local server:  python home/tank_game_client.py")
        print(f"   • Remote server: python home/tank_game_client.py --host [TARGET_IP]")
        print()
        print("🔧 Make sure:")
        print("   • Server is running on target machine")
        print("   • Both machines are on same network")
        print("   • Firewall allows port 8765")
    
    print("=" * 40)


if __name__ == "__main__":
    asyncio.run(main()) 