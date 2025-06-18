#!/usr/bin/env python3
"""
坦克游戏共享实体类

包含 Player 和 Bullet 类的定义，供服务器和客户端共同使用
确保前后端数据结构的一致性
"""

import time
import os
from typing import Dict, Optional
from websockets.server import WebSocketServerProtocol
from dotenv import load_dotenv

# 加载环境变量
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# 游戏配置
SCREEN_WIDTH = int(os.getenv('SCREEN_WIDTH', 800))
SCREEN_HEIGHT = int(os.getenv('SCREEN_HEIGHT', 600))
TANK_SPEED = int(os.getenv('TANK_SPEED', 300))
BULLET_SPEED = int(os.getenv('BULLET_SPEED', 300))
BULLET_DAMAGE = int(os.getenv('BULLET_DAMAGE', 25))
BULLET_LIFETIME = float(os.getenv('BULLET_LIFETIME', 5.0))


class Player:
    """玩家状态类 - 供服务器和客户端共享使用"""
    
    def __init__(self, player_data: Dict, websocket = None):
        self.player_id = player_data['player_id']
        self.name = player_data['name']
        self.health = player_data.get('health', 100)
        self.max_health = player_data.get('max_health', 100)
        self.is_alive = player_data.get('is_alive', True)
        
        # 位置和运动
        self.position = player_data.get('position', {"x": SCREEN_WIDTH/2, "y": SCREEN_HEIGHT/2}).copy()
        self.velocity = player_data.get('velocity', {"x": 0.0, "y": 0.0}).copy()
        self.rotation = player_data.get('rotation', 0.0)
        self.moving_directions = player_data.get('moving_directions', {"w": False, "a": False, "s": False, "d": False}).copy()
        
        # 时间戳
        self.last_update = time.time()
        
        # 服务器特有属性（仅在服务器端使用）
        self.websocket = websocket
        if websocket:
            self.last_client_update = time.time()
            self.use_client_position = True
            
        # 客户端特有属性（仅在客户端使用）
        if not websocket:
            self.last_server_sync = time.time()
            self.server_sync_threshold = 100.0
    
    def update_from_server(self, position: Dict[str, float], directions: Dict[str, bool] = None):
        """从服务器更新状态 - 客户端使用"""
        if directions:
            self.moving_directions = directions.copy()
        
        # 计算位置差异
        dx = position["x"] - self.position["x"]
        dy = position["y"] - self.position["y"]
        distance = (dx * dx + dy * dy) ** 0.5
        
        # 大幅提高校正阈值，只有在极大差异时才校正
        correction_threshold = 200.0
        
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
    
    def to_dict(self) -> Dict:
        """转换为字典 - 用于网络传输"""
        return {
            "player_id": self.player_id,
            "name": self.name,
            "position": self.position,
            "velocity": self.velocity,
            "rotation": self.rotation,
            "health": self.health,
            "max_health": self.max_health,
            "is_alive": self.is_alive,
            "moving_directions": self.moving_directions
        }


class Bullet:
    """子弹状态类 - 供服务器和客户端共享使用"""
    
    def __init__(self, bullet_data: Dict):
        self.bullet_id = bullet_data['bullet_id']
        self.owner_id = bullet_data['owner_id']
        self.position = bullet_data['position'].copy()
        
        # 处理速度参数 - 兼容不同的输入格式
        if 'velocity' in bullet_data:
            self.velocity = bullet_data['velocity'].copy()
        else:
            # 从方向和速度计算velocity
            direction = bullet_data.get('direction', {"x": 1.0, "y": 0.0})
            speed = bullet_data.get('speed', BULLET_SPEED)
            self.velocity = {"x": direction["x"] * speed, "y": direction["y"] * speed}
        
        self.damage = bullet_data.get('damage', BULLET_DAMAGE)
        self.created_time = bullet_data.get('created_time', time.time())
        self.max_lifetime = BULLET_LIFETIME
    
    def update(self, dt: float) -> bool:
        """更新子弹位置，返回是否仍然有效"""
        self.position["x"] += self.velocity["x"] * dt
        self.position["y"] += self.velocity["y"] * dt
        
        # 检查边界和生命周期
        if (self.position["x"] < 0 or self.position["x"] > SCREEN_WIDTH or
            self.position["y"] < 0 or self.position["y"] > SCREEN_HEIGHT or
            time.time() - self.created_time > self.max_lifetime):
            return False
        
        return True
    
    def to_dict(self) -> Dict:
        """转换为字典 - 用于网络传输"""
        return {
            "bullet_id": self.bullet_id,
            "owner_id": self.owner_id,
            "position": self.position,
            "velocity": self.velocity,
            "damage": self.damage,
            "created_time": self.created_time
        }

