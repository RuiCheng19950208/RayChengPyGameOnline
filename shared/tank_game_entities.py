#!/usr/bin/env python3
"""
坦克游戏共享实体类

包含 Player 和 Bullet 类的定义，供服务器和客户端共同使用
确保前后端数据结构的一致性
"""

import time
import os
from typing import Dict, Optional, List
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
MAX_PLAYERS_PER_ROOM = int(os.getenv('MAX_PLAYERS_PER_ROOM', 8))


class Player:
    """玩家状态类 - 供服务器和客户端共享使用"""
    
    def __init__(self, player_data: Dict, websocket = None):
        self.player_id = player_data['player_id']
        self.name = player_data['name']
        self.health = player_data.get('health', 100)
        self.max_health = player_data.get('max_health', 100)
        self.is_alive = player_data.get('is_alive', True)
        self.slot_index = player_data.get('slot_index', 0)  # 玩家槽位索引
        
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
            "moving_directions": self.moving_directions,
            "slot_index": getattr(self, 'slot_index', 0)
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


class GameRoom:
    """游戏房间 - 供服务器和客户端共享使用"""
    
    def __init__(self, room_id: str, name: str, host_player_id: str, max_players: int = None):
        self.room_id = room_id
        self.name = name
        self.host_player_id = host_player_id  # 房主玩家ID
        self.max_players = max_players if max_players is not None else MAX_PLAYERS_PER_ROOM
        self.players: Dict[str, Player] = {}
        self.bullets: Dict[str, Bullet] = {}
        self.game_time = 0.0
        self.frame_id = 0
        self.last_update = time.time()
        
        # 房间状态
        self.room_state = "waiting"  # waiting, playing, finished
        self.created_time = time.time()
        
        # 事件驱动相关（主要用于服务器）
        self.pending_events = []
        self.state_changed = False
        
    def add_player(self, player: Player) -> bool:
        """添加玩家到房间"""
        if len(self.players) >= self.max_players:
            return False
        
        # 计算玩家的槽位索引
        slot_index = len(self.players)
        player.slot_index = slot_index
        
        # 根据槽位计算生成位置
        spawn_position = self._calculate_spawn_position(slot_index)
        player.position = spawn_position
        
        self.players[player.player_id] = player
        self.state_changed = True
        return True
    
    def _calculate_spawn_position(self, slot_index: int) -> Dict[str, float]:
        """根据槽位索引计算生成位置"""
        # 定义生成位置（围绕地图边缘分布）
        positions = [
            {"x": 100, "y": 100},    # 左上
            {"x": SCREEN_WIDTH - 100, "y": 100},    # 右上
            {"x": 100, "y": SCREEN_HEIGHT - 100},   # 左下
            {"x": SCREEN_WIDTH - 100, "y": SCREEN_HEIGHT - 100},  # 右下
            {"x": SCREEN_WIDTH // 2, "y": 100},     # 上中
            {"x": SCREEN_WIDTH // 2, "y": SCREEN_HEIGHT - 100},  # 下中
            {"x": 100, "y": SCREEN_HEIGHT // 2},    # 左中
            {"x": SCREEN_WIDTH - 100, "y": SCREEN_HEIGHT // 2},  # 右中
        ]
        
        # 如果槽位索引超出预定义位置，使用随机位置
        if slot_index < len(positions):
            return positions[slot_index].copy()
        else:
            # 随机位置（避免重叠）
            import random
            return {
                "x": random.randint(50, SCREEN_WIDTH - 50),
                "y": random.randint(50, SCREEN_HEIGHT - 50)
            }
        
    def remove_player(self, player_id: str) -> bool:
        """从房间移除玩家"""
        if player_id in self.players:
            del self.players[player_id]
            self.state_changed = True
            
            # 如果房主离开，选择新房主或关闭房间
            if player_id == self.host_player_id:
                remaining_players = list(self.players.keys())
                if remaining_players:
                    self.host_player_id = remaining_players[0]
                    print(f"🔄 New room host: {self.host_player_id}")
                else:
                    # 房间空了，标记为可删除
                    return "delete_room"
            
            return True
        return False
    
    def add_bullet(self, bullet: Bullet):
        """添加子弹"""
        self.bullets[bullet.bullet_id] = bullet
        self.state_changed = True
    
    def start_game(self) -> bool:
        """开始游戏（仅房主可调用）"""
        if self.room_state == "waiting" and len(self.players) > 0:
            self.room_state = "playing"
            self.state_changed = True
            return True
        return False
    
    def end_game(self):
        """结束游戏"""
        self.room_state = "finished"
        self.state_changed = True
    
    def reset_for_new_game(self):
        """重置房间准备新游戏"""
        self.room_state = "waiting"
        self.bullets.clear()
        self.game_time = 0.0
        self.frame_id = 0
        
        # 重置所有玩家状态
        for player in self.players.values():
            player.health = player.max_health
            player.is_alive = True
            player.position = {"x": SCREEN_WIDTH/2, "y": SCREEN_HEIGHT/2}
            player.moving_directions = {"w": False, "a": False, "s": False, "d": False}
        
        self.state_changed = True
    
    def get_available_slots(self) -> List[int]:
        """获取可用的玩家位置槽"""
        occupied_slots = [i for i in range(len(self.players))]
        all_slots = list(range(self.max_players))
        return [slot for slot in all_slots if slot not in occupied_slots]
    
    def is_host(self, player_id: str) -> bool:
        """检查玩家是否为房主"""
        return player_id == self.host_player_id
    
    def can_start_game(self) -> bool:
        """检查是否可以开始游戏"""
        return (self.room_state == "waiting" and 
                len(self.players) >= 1 and  # 至少需要1个玩家
                len(self.players) <= self.max_players)
    
    def to_dict(self) -> Dict:
        """转换为字典 - 用于网络传输和UI显示"""
        return {
            "room_id": self.room_id,
            "name": self.name,
            "host_player_id": self.host_player_id,
            "max_players": self.max_players,
            "current_players": len(self.players),
            "players": [player.to_dict() for player in self.players.values()],
            "bullets": [bullet.to_dict() for bullet in self.bullets.values()] if self.room_state == "playing" else [],
            "game_time": self.game_time,
            "frame_id": self.frame_id,
            "room_state": self.room_state,
            "created_time": self.created_time,
            "available_slots": self.get_available_slots()
        }

    def change_player_slot(self, player_id: str, target_slot: int) -> bool:
        """切换玩家槽位"""
        if player_id not in self.players:
            return False
        
        # 检查目标槽位是否有效
        if target_slot < 0 or target_slot >= self.max_players:
            return False
        
        # 检查目标槽位是否已被占用
        for pid, player in self.players.items():
            if pid != player_id and player.slot_index == target_slot:
                return False  # 槽位已被占用
        
        # 执行槽位切换
        player = self.players[player_id]
        old_slot = player.slot_index
        player.slot_index = target_slot
        
        # 根据新槽位更新生成位置
        new_position = self._calculate_spawn_position(target_slot)
        player.position = new_position
        
        self.state_changed = True
        print(f"🔄 Player {player_id} moved from slot {old_slot} to slot {target_slot}")
        return True
    
    def get_occupied_slots(self) -> List[int]:
        """获取已占用的槽位列表"""
        return [player.slot_index for player in self.players.values()]
    
    def is_slot_available(self, slot_index: int) -> bool:
        """检查槽位是否可用"""
        if slot_index < 0 or slot_index >= self.max_players:
            return False
        
        occupied_slots = self.get_occupied_slots()
        return slot_index not in occupied_slots
    
    def update_physics(self, dt: float) -> List:
        """更新物理状态并返回事件列表"""
        events = []
        
        # 更新帧ID和游戏时间
        self.frame_id += 1
        self.game_time += dt
        
        # 如果房间不在游戏状态，不进行物理更新
        if self.room_state != "playing":
            return events
        
        # 更新子弹位置
        bullets_to_remove = []
        for bullet_id, bullet in self.bullets.items():
            if not bullet.update(dt):
                bullets_to_remove.append(bullet_id)
                # 创建子弹销毁事件
                from tank_game_messages import BulletDestroyedMessage
                bullet_destroyed_event = BulletDestroyedMessage(
                    bullet_id=bullet_id,
                    reason="expired"
                )
                events.append(bullet_destroyed_event)
        
        # 移除无效子弹
        for bullet_id in bullets_to_remove:
            del self.bullets[bullet_id]
        
        # 碰撞检测
        collision_events = self._check_collisions()
        events.extend(collision_events)
        
        # 标记状态已更改
        if events:
            self.state_changed = True
        
        return events
    
    def _check_collisions(self) -> List:
        """检测碰撞并返回碰撞事件"""
        events = []
        bullets_to_remove = []
        
        for bullet_id, bullet in self.bullets.items():
            for player_id, player in self.players.items():
                # 跳过子弹拥有者
                if bullet.owner_id == player_id or not player.is_alive:
                    continue
                
                # 简单的碰撞检测（圆形碰撞）
                dx = bullet.position['x'] - player.position['x']
                dy = bullet.position['y'] - player.position['y']
                distance = (dx * dx + dy * dy) ** 0.5
                
                if distance < 25:  # 碰撞半径
                    # 创建碰撞事件
                    player.health -= bullet.damage
                    
                    from tank_game_messages import CollisionMessage
                    collision_event = CollisionMessage(
                        bullet_id=bullet_id,
                        target_player_id=player_id,
                        damage_dealt=bullet.damage,
                        new_health=player.health,
                        collision_position=bullet.position.copy()
                    )
                    events.append(collision_event)
                    
                    # 标记子弹待删除
                    bullets_to_remove.append(bullet_id)
                    
                    # 检查玩家是否死亡
                    if player.health <= 0:
                        player.is_alive = False
                        from tank_game_messages import PlayerDeathMessage
                        death_event = PlayerDeathMessage(
                            player_id=player_id,
                            killer_id=bullet.owner_id,
                            death_position=player.position.copy()
                        )
                        events.append(death_event)
                    
                    break  # 子弹只能击中一个目标
        
        # 移除碰撞的子弹
        for bullet_id in bullets_to_remove:
            if bullet_id in self.bullets:
                del self.bullets[bullet_id]
                # 创建子弹销毁事件
                from tank_game_messages import BulletDestroyedMessage
                bullet_destroyed_event = BulletDestroyedMessage(
                    bullet_id=bullet_id,
                    reason="collision"
                )
                events.append(bullet_destroyed_event)
        
        return events
    
    def get_state_if_changed(self):
        """如果状态有变化，返回状态更新消息"""
        if not self.state_changed:
            return None
        
        self.state_changed = False
        
        from tank_game_messages import GameStateUpdateMessage
        return GameStateUpdateMessage(
            players=[player.to_dict() for player in self.players.values()],
            bullets=[bullet.to_dict() for bullet in self.bullets.values()],
            game_time=self.game_time,
            frame_id=self.frame_id
        )

