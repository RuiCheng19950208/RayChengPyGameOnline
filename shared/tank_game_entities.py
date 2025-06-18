#!/usr/bin/env python3
"""
Tank game shared entity classes

Contains Player and Bullet class definitions for shared use between server and client
Ensures consistency of data structures between frontend and backend
"""

import time
import os
from typing import Dict, Optional, List
from websockets.server import WebSocketServerProtocol
from dotenv import load_dotenv

# Load environment variables
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Game configuration
SCREEN_WIDTH = int(os.getenv('SCREEN_WIDTH', 800))
SCREEN_HEIGHT = int(os.getenv('SCREEN_HEIGHT', 600))
TANK_SPEED = int(os.getenv('TANK_SPEED', 300))
BULLET_SPEED = int(os.getenv('BULLET_SPEED', 300))
BULLET_DAMAGE = int(os.getenv('BULLET_DAMAGE', 25))
BULLET_LIFETIME = float(os.getenv('BULLET_LIFETIME', 5.0))
MAX_PLAYERS_PER_ROOM = int(os.getenv('MAX_PLAYERS_PER_ROOM', 8))


class Player:
    """Player state class - shared between server and client"""
    
    def __init__(self, player_data: Dict, websocket = None):
        self.player_id = player_data['player_id']
        self.name = player_data['name']
        self.health = player_data.get('health', 100)
        self.max_health = player_data.get('max_health', 100)
        self.is_alive = player_data.get('is_alive', True)
        self.slot_index = player_data.get('slot_index', 0)  # Player slot index
        
        # Position and movement
        self.position = player_data.get('position', {"x": SCREEN_WIDTH/2, "y": SCREEN_HEIGHT/2}).copy()
        self.velocity = player_data.get('velocity', {"x": 0.0, "y": 0.0}).copy()
        self.rotation = player_data.get('rotation', 0.0)
        self.moving_directions = player_data.get('moving_directions', {"w": False, "a": False, "s": False, "d": False}).copy()
        
        # Timestamp
        self.last_update = time.time()
        
        # Server-specific attributes (only used on server side)
        self.websocket = websocket
        if websocket:
            self.last_client_update = time.time()
            self.use_client_position = True
            
        # Client-specific attributes (only used on client side)
        if not websocket:
            self.last_server_sync = time.time()
            self.server_sync_threshold = 100.0
            
            # Enhanced client-side prediction and smoothing
            self.server_position = {"x": 0.0, "y": 0.0}  # Last known server position
            self.target_position = {"x": 0.0, "y": 0.0}   # Target position for interpolation
            self.interpolation_speed = 8.0  # Higher = faster correction
            self.prediction_time = 0.0  # How far ahead we're predicting
            self.last_correction_time = 0.0
            self.correction_threshold_base = 50.0  # Base threshold for corrections
            self.correction_history = []  # Track recent corrections to avoid oscillation
    
    def update_from_server(self, position: Dict[str, float], directions: Dict[str, bool] = None):
        """优化的服务器位置更新 - 减少颤动，提高一致性"""
        current_time = time.time()
        
        if directions:
            self.moving_directions = directions.copy()
        
        # 计算位置差异
        dx = position["x"] - self.position["x"]
        dy = position["y"] - self.position["y"]
        distance = (dx * dx + dy * dy) ** 0.5
        
        # 区分不同类型的玩家处理逻辑
        if hasattr(self, 'websocket') and self.websocket:
            # 服务器端玩家 - 保持原有的服务器逻辑
            correction_threshold = 100.0
            if any(self.moving_directions.values()):
                correction_threshold = 150.0
            
            if distance > correction_threshold:
                print(f"🔧 Server correction for {self.name}: {distance:.1f}px")
                blend_factor = 0.1
                self.position["x"] = self.position["x"] + (dx * blend_factor)
                self.position["y"] = self.position["y"] + (dy * blend_factor)
                
        elif hasattr(self, 'is_local_player') and self.is_local_player:
            # 本地玩家 - 不进行位置校正，完全信任客户端预测
            pass
            
        else:
            # 远程玩家 - 使用优化的平滑同步算法
            self._update_remote_player_position(position, distance, current_time)
        
        self.last_server_sync = current_time
    
    def _update_remote_player_position(self, server_position: Dict[str, float], distance: float, current_time: float):
        """优化的远程玩家位置更新算法"""
        # 更新服务器位置记录
        self.server_position = server_position.copy()
        
        # 计算位置差异
        dx = server_position["x"] - self.position["x"]
        dy = server_position["y"] - self.position["y"]
        
        # 动态调整校正阈值
        is_moving = any(self.moving_directions.values())
        time_since_last_correction = current_time - self.last_correction_time
        
        # 基础阈值：静止时更严格，移动时更宽松
        if is_moving:
            base_threshold = self.correction_threshold_base * 1.5  # 75px when moving
        else:
            base_threshold = self.correction_threshold_base * 0.6  # 30px when stopped
        
        # 如果最近有过多校正，提高阈值避免振荡
        recent_corrections = [c for c in self.correction_history if current_time - c < 1.0]
        if len(recent_corrections) > 3:  # 1秒内超过3次校正
            base_threshold *= 2.0
            print(f"🔄 Anti-oscillation: raised threshold to {base_threshold:.1f}px for {self.name}")
        
        # 清理旧的校正记录
        self.correction_history = [c for c in self.correction_history if current_time - c < 2.0]
        
        if distance > base_threshold:
            # 需要进行位置校正
            print(f"🔧 Remote player correction for {self.name}: {distance:.1f}px (threshold: {base_threshold:.1f}px)")
            
            # 记录校正时间
            self.last_correction_time = current_time
            self.correction_history.append(current_time)
            
            # 使用插值而不是直接跳跃
            if distance > base_threshold * 3:
                # 差异太大，直接校正
                self.position = server_position.copy()
                print(f"📍 Major correction: teleported {self.name} to server position")
            else:
                # 平滑校正：设置目标位置，逐步移动
                self.target_position = server_position.copy()
                
                # 立即进行部分校正，剩余的通过插值完成
                correction_factor = min(0.3, base_threshold / distance)
                self.position["x"] += dx * correction_factor
                self.position["y"] += dy * correction_factor
                
        elif distance > 5.0:
            # 小幅偏差，使用温和的插值
            self.target_position = server_position.copy()
        else:
            # 位置差异很小，不需要校正
            self.target_position = self.position.copy()
    
    def _smooth_interpolate_position(self, dt: float):
        """平滑插值到目标位置"""
        if not hasattr(self, 'target_position'):
            return
            
        dx = self.target_position["x"] - self.position["x"]
        dy = self.target_position["y"] - self.position["y"]
        distance = (dx * dx + dy * dy) ** 0.5
        
        if distance > 1.0:  # 只有在距离大于1px时才进行插值
            # 计算插值步长
            interpolation_step = self.interpolation_speed * dt
            move_distance = min(distance, interpolation_step)
            
            # 移动到目标位置
            if distance > 0:
                move_factor = move_distance / distance
                self.position["x"] += dx * move_factor
                self.position["y"] += dy * move_factor

    def update_position(self, dt: float):
        """Update position - exactly same algorithm as server"""
        speed = TANK_SPEED
        velocity = {"x": 0.0, "y": 0.0}
        
        # Calculate velocity based on key states
        if self.moving_directions["w"]:
            velocity["y"] -= speed
        if self.moving_directions["s"]:
            velocity["y"] += speed
        if self.moving_directions["a"]:
            velocity["x"] -= speed
        if self.moving_directions["d"]:
            velocity["x"] += speed
        
        # Update position
        self.position["x"] += velocity["x"] * dt
        self.position["y"] += velocity["y"] * dt
        
        # Boundary check
        self.position["x"] = max(0, min(SCREEN_WIDTH, self.position["x"]))
        self.position["y"] = max(0, min(SCREEN_HEIGHT, self.position["y"]))
        
        # 对于远程玩家，在位置更新后进行平滑插值
        if not hasattr(self, 'websocket') and not hasattr(self, 'is_local_player'):
            self._smooth_interpolate_position(dt)
        
        self.last_update = time.time()
    
    def to_dict(self) -> Dict:
        """Convert to dictionary - for network transmission"""
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
    """Bullet state class - shared between server and client"""
    
    def __init__(self, bullet_data: Dict):
        self.bullet_id = bullet_data['bullet_id']
        self.owner_id = bullet_data['owner_id']
        self.position = bullet_data['position'].copy()
        
        # Handle velocity parameter - compatible with different input formats
        if 'velocity' in bullet_data:
            self.velocity = bullet_data['velocity'].copy()
        else:
            # Calculate velocity from direction and speed
            direction = bullet_data.get('direction', {"x": 1.0, "y": 0.0})
            speed = bullet_data.get('speed', BULLET_SPEED)
            self.velocity = {"x": direction["x"] * speed, "y": direction["y"] * speed}
        
        self.damage = bullet_data.get('damage', BULLET_DAMAGE)
        self.created_time = bullet_data.get('created_time', time.time())
        self.max_lifetime = BULLET_LIFETIME
    
    def update(self, dt: float) -> bool:
        """Update bullet position, return whether still valid"""
        self.position["x"] += self.velocity["x"] * dt
        self.position["y"] += self.velocity["y"] * dt
        
        # Check boundaries and lifetime
        if (self.position["x"] < 0 or self.position["x"] > SCREEN_WIDTH or
            self.position["y"] < 0 or self.position["y"] > SCREEN_HEIGHT or
            time.time() - self.created_time > self.max_lifetime):
            return False
        
        return True
    
    def to_dict(self) -> Dict:
        """Convert to dictionary - for network transmission"""
        return {
            "bullet_id": self.bullet_id,
            "owner_id": self.owner_id,
            "position": self.position,
            "velocity": self.velocity,
            "damage": self.damage,
            "created_time": self.created_time
        }


class GameRoom:
    """Game room - shared between server and client"""
    
    def __init__(self, room_id: str, name: str, host_player_id: str, max_players: int = None):
        self.room_id = room_id
        self.name = name
        self.host_player_id = host_player_id  # Host player ID
        self.max_players = max_players if max_players is not None else MAX_PLAYERS_PER_ROOM
        self.players: Dict[str, Player] = {}
        self.bullets: Dict[str, Bullet] = {}
        self.game_time = 0.0
        self.frame_id = 0
        self.last_update = time.time()
        
        # Room state
        self.room_state = "waiting"  # waiting, playing, finished
        self.created_time = time.time()
        self.game_start_time = None  # Track when game actually started
        
        # Event-driven related (mainly used by server)
        self.pending_events = []
        self.state_changed = False
        
    def add_player(self, player: Player) -> bool:
        """Add player to room"""
        if len(self.players) >= self.max_players:
            return False
        
        # Find lowest available slot index
        occupied_slots = [p.slot_index for p in self.players.values()]
        available_slot = None
        for i in range(self.max_players):
            if i not in occupied_slots:
                available_slot = i
                break
        
        if available_slot is None:
            print(f"⚠️ No available slots found in room with {len(self.players)} players")
            return False
        
        # Set player's slot index
        player.slot_index = available_slot
        
        # Calculate spawn position based on slot
        spawn_position = self._calculate_spawn_position(available_slot)
        player.position = spawn_position
        
        self.players[player.player_id] = player
        self.state_changed = True
        
        print(f"🎮 Player {player.player_id} assigned to slot {available_slot}")
        return True
    
    def _calculate_spawn_position(self, slot_index: int) -> Dict[str, float]:
        """Calculate spawn position based on slot index"""
        # Define spawn positions (distributed around map edges)
        positions = [
            {"x": 100, "y": 100},    # Top-left
            {"x": SCREEN_WIDTH - 100, "y": 100},    # Top-right
            {"x": 100, "y": SCREEN_HEIGHT - 100},   # Bottom-left
            {"x": SCREEN_WIDTH - 100, "y": SCREEN_HEIGHT - 100},  # Bottom-right
            {"x": SCREEN_WIDTH // 2, "y": 100},     # Top-center
            {"x": SCREEN_WIDTH // 2, "y": SCREEN_HEIGHT - 100},  # Bottom-center
            {"x": 100, "y": SCREEN_HEIGHT // 2},    # Left-center
            {"x": SCREEN_WIDTH - 100, "y": SCREEN_HEIGHT // 2},  # Right-center
        ]
        
        # If slot index exceeds predefined positions, use random position
        if slot_index < len(positions):
            return positions[slot_index].copy()
        else:
            # Random position (avoid overlap)
            import random
            return {
                "x": random.randint(50, SCREEN_WIDTH - 50),
                "y": random.randint(50, SCREEN_HEIGHT - 50)
            }
        
    def remove_player(self, player_id: str) -> bool:
        """Remove player from room"""
        if player_id in self.players:
            del self.players[player_id]
            self.state_changed = True
            
            # If host leaves, select new host or close room
            if player_id == self.host_player_id:
                remaining_players = list(self.players.keys())
                if remaining_players:
                    self.host_player_id = remaining_players[0]
                    print(f"🔄 New room host: {self.host_player_id}")
                else:
                    # Room is empty, mark for deletion
                    return "delete_room"
            
            return True
        return False
    
    def add_bullet(self, bullet: Bullet):
        """Add bullet"""
        self.bullets[bullet.bullet_id] = bullet
        self.state_changed = True
    
    def start_game(self) -> bool:
        """Start game (only host can call)"""
        if self.room_state == "waiting" and len(self.players) > 0:
            self.room_state = "playing"
            self.game_start_time = time.time()  # Record game start time
            self.state_changed = True
            
            # Special case: if only one player, they win immediately
            if len(self.players) == 1:
                winner = list(self.players.values())[0]
                from tank_game_messages import GameVictoryMessage
                victory_event = GameVictoryMessage(
                    winner_player_id=winner.player_id,
                    winner_player_name=winner.name,
                    room_id=self.room_id,
                    game_duration=0.0,
                    total_players=1
                )
                self.pending_events.append(victory_event)
                self.end_game()
            
            return True
        return False
    
    def end_game(self):
        """End game"""
        self.room_state = "finished"
        self.state_changed = True
    
    def reset_for_new_game(self):
        """Reset room for new game"""
        self.room_state = "waiting"
        self.bullets.clear()
        self.game_time = 0.0
        self.frame_id = 0
        
        # Reset all player states
        for player in self.players.values():
            player.health = player.max_health
            player.is_alive = True
            player.position = {"x": SCREEN_WIDTH/2, "y": SCREEN_HEIGHT/2}
            player.moving_directions = {"w": False, "a": False, "s": False, "d": False}
        
        self.state_changed = True
    
    def get_available_slots(self) -> List[int]:
        """Get available player position slots"""
        occupied_slots = [i for i in range(len(self.players))]
        all_slots = list(range(self.max_players))
        return [slot for slot in all_slots if slot not in occupied_slots]
    
    def is_host(self, player_id: str) -> bool:
        """Check if player is host"""
        return player_id == self.host_player_id
    
    def can_start_game(self) -> bool:
        """Check if game can be started"""
        return (self.room_state == "waiting" and 
                len(self.players) >= 1 and  # At least 1 player needed
                len(self.players) <= self.max_players)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary - for network transmission and UI display"""
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
        """Change player slot"""
        if player_id not in self.players:
            return False
        
        # Check if target slot is valid
        if target_slot < 0 or target_slot >= self.max_players:
            return False
        
        # Check if target slot is already occupied
        for pid, player in self.players.items():
            if pid != player_id and player.slot_index == target_slot:
                return False  # Slot already occupied
        
        # Execute slot change
        player = self.players[player_id]
        old_slot = player.slot_index
        player.slot_index = target_slot
        
        # Update spawn position based on new slot
        new_position = self._calculate_spawn_position(target_slot)
        player.position = new_position
        
        self.state_changed = True
        print(f"🔄 Player {player_id} moved from slot {old_slot} to slot {target_slot}")
        return True
    
    def get_occupied_slots(self) -> List[int]:
        """Get list of occupied slots"""
        return [player.slot_index for player in self.players.values()]
    
    def is_slot_available(self, slot_index: int) -> bool:
        """Check if slot is available"""
        if slot_index < 0 or slot_index >= self.max_players:
            return False
        
        occupied_slots = self.get_occupied_slots()
        return slot_index not in occupied_slots
    
    def update_physics(self, dt: float) -> List:
        """Update physics state and return event list"""
        events = []
        
        # Add any pending events first
        if self.pending_events:
            events.extend(self.pending_events)
            self.pending_events.clear()
        
        # Update frame ID and game time
        self.frame_id += 1
        self.game_time += dt
        
        # If room is not in playing state, don't update physics
        if self.room_state != "playing":
            return events
        
        # Update bullet positions
        bullets_to_remove = []
        for bullet_id, bullet in self.bullets.items():
            if not bullet.update(dt):
                bullets_to_remove.append(bullet_id)
                # Create bullet destruction event
                from tank_game_messages import BulletDestroyedMessage
                bullet_destroyed_event = BulletDestroyedMessage(
                    bullet_id=bullet_id,
                    reason="expired"
                )
                events.append(bullet_destroyed_event)
        
        # Remove invalid bullets
        for bullet_id in bullets_to_remove:
            del self.bullets[bullet_id]
        
        # Collision detection
        collision_events = self._check_collisions()
        events.extend(collision_events)
        
        # Mark state as changed
        if events:
            self.state_changed = True
        
        return events
    
    def _check_collisions(self) -> List:
        """Detect collisions and return collision events"""
        events = []
        bullets_to_remove = []
        
        for bullet_id, bullet in self.bullets.items():
            for player_id, player in self.players.items():
                # Skip bullet owner
                if bullet.owner_id == player_id or not player.is_alive:
                    continue
                
                # Simple collision detection (circular collision)
                dx = bullet.position['x'] - player.position['x']
                dy = bullet.position['y'] - player.position['y']
                distance = (dx * dx + dy * dy) ** 0.5
                
                if distance < 25:  # Collision radius
                    # Create collision event
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
                    
                    # Mark bullet for removal
                    bullets_to_remove.append(bullet_id)
                    
                    # Check if player died
                    if player.health <= 0:
                        player.is_alive = False
                        from tank_game_messages import PlayerDeathMessage
                        death_event = PlayerDeathMessage(
                            player_id=player_id,
                            killer_id=bullet.owner_id,
                            death_position=player.position.copy()
                        )
                        events.append(death_event)
                        
                        # Check for victory/defeat conditions
                        victory_events = self._check_victory_conditions(player_id, bullet.owner_id)
                        events.extend(victory_events)
                    
                    break  # Bullet can only hit one target
        
        # Remove collided bullets
        for bullet_id in bullets_to_remove:
            if bullet_id in self.bullets:
                del self.bullets[bullet_id]
                # Create bullet destruction event
                from tank_game_messages import BulletDestroyedMessage
                bullet_destroyed_event = BulletDestroyedMessage(
                    bullet_id=bullet_id,
                    reason="collision"
                )
                events.append(bullet_destroyed_event)
        
        return events
    
    def _check_victory_conditions(self, eliminated_player_id: str, killer_id: str) -> List:
        """Check if game should end due to victory/defeat conditions"""
        events = []
        
        # Count alive players
        alive_players = [p for p in self.players.values() if p.is_alive]
        
        # Send defeat message to eliminated player
        if eliminated_player_id in self.players:
            eliminated_player = self.players[eliminated_player_id]
            killer_player = self.players.get(killer_id)
            
            current_time = time.time()
            survival_time = current_time - self.game_start_time if self.game_start_time else 0.0
            
            from tank_game_messages import GameDefeatMessage
            defeat_event = GameDefeatMessage(
                eliminated_player_id=eliminated_player_id,
                eliminated_player_name=eliminated_player.name,
                killer_id=killer_id,
                killer_name=killer_player.name if killer_player else "Unknown",
                room_id=self.room_id,
                survival_time=survival_time
            )
            events.append(defeat_event)
        
        # Check if only one player remains alive (victory condition)
        if len(alive_players) == 1:
            winner = alive_players[0]
            current_time = time.time()
            game_duration = current_time - self.game_start_time if self.game_start_time else 0.0
            
            from tank_game_messages import GameVictoryMessage
            victory_event = GameVictoryMessage(
                winner_player_id=winner.player_id,
                winner_player_name=winner.name,
                room_id=self.room_id,
                game_duration=game_duration,
                total_players=len(self.players)
            )
            events.append(victory_event)
            
            # End the game
            self.end_game()
        
        return events
    
    def get_state_if_changed(self):
        """如果状态已更改，返回状态更新消息 - 增强版本"""
        # 对于游戏中的房间，总是返回状态更新以确保位置同步
        # 对于等待中的房间，只在状态真正改变时返回
        if self.room_state == "playing":
            # 游戏进行中，定期同步所有玩家位置确保一致性
            from tank_game_messages import GameStateUpdateMessage
            return GameStateUpdateMessage(
                players=[player.to_dict() for player in self.players.values()],
                bullets=[bullet.to_dict() for bullet in self.bullets.values()],
                game_time=self.game_time,
                frame_id=self.frame_id
            )
        elif self.state_changed:
            # 等待状态，只在状态变更时同步
            self.state_changed = False
            
            from tank_game_messages import GameStateUpdateMessage
            return GameStateUpdateMessage(
                players=[player.to_dict() for player in self.players.values()],
                bullets=[bullet.to_dict() for bullet in self.bullets.values()],
                game_time=self.game_time,
                frame_id=self.frame_id
            )
        
        return None

