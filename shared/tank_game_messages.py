#!/usr/bin/env python3
"""
坦克游戏消息系统 - 基于 Kable 项目的消息驱动架构

所有前后端交互都通过标准化的 WebSocket 消息进行，
确保类型安全和可扩展性。
"""

import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import json


class GameMessageType(str, Enum):
    """所有可能的游戏消息类型"""
    
    # 玩家动作消息
    PLAYER_MOVE = "player_move"
    PLAYER_STOP = "player_stop"
    PLAYER_SHOOT = "player_shoot"
    PLAYER_JOIN = "player_join"
    PLAYER_LEAVE = "player_leave"
    
    # 游戏状态消息
    GAME_STATE_UPDATE = "game_state_update"
    PLAYER_POSITION_UPDATE = "player_position_update"
    BULLET_FIRED = "bullet_fired"
    BULLET_HIT = "bullet_hit"
    BULLET_DESTROYED = "bullet_destroyed"
    PLAYER_HIT = "player_hit"
    PLAYER_DESTROYED = "player_destroyed"
    PLAYER_DEATH = "player_death"
    COLLISION = "collision"
    
    # 房间管理消息
    ROOM_JOIN = "room_join"
    ROOM_LEAVE = "room_leave"
    ROOM_LIST = "room_list"
    ROOM_CREATED = "room_created"
    
    # 系统消息
    CONNECTION_ACK = "connection_ack"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    DEBUG = "debug"


@dataclass
class BaseGameMessage(ABC):
    """所有游戏消息的基类"""
    
    def __post_init__(self):
        """初始化时间戳"""
        if not hasattr(self, "timestamp") or self.timestamp is None:
            self.timestamp = time.time()
    
    @property
    @abstractmethod
    def type(self) -> GameMessageType:
        """返回消息类型"""
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典用于传输"""
        data = asdict(self)
        data["type"] = self.type.value
        return data
    
    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict())


# ===============================
# 玩家动作消息
# ===============================

@dataclass
class PlayerMoveMessage(BaseGameMessage):
    """玩家移动消息"""
    
    player_id: str
    direction: Dict[str, bool]  # {"w": True, "a": False, "s": False, "d": True}
    position: Dict[str, float]  # {"x": 100.0, "y": 200.0}
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_MOVE


@dataclass
class PlayerStopMessage(BaseGameMessage):
    """玩家停止移动消息"""
    
    player_id: str
    position: Dict[str, float]  # 最终位置
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_STOP


@dataclass
class PlayerShootMessage(BaseGameMessage):
    """玩家射击消息"""
    
    player_id: str
    position: Dict[str, float]  # 射击起始位置
    direction: Dict[str, float]  # 射击方向向量
    bullet_id: str
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_SHOOT


@dataclass
class PlayerJoinMessage(BaseGameMessage):
    """玩家加入游戏消息"""
    
    player_id: str
    player_name: str
    room_id: Optional[str] = None
    spawn_position: Optional[Dict[str, float]] = None
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_JOIN


@dataclass
class PlayerLeaveMessage(BaseGameMessage):
    """玩家离开游戏消息"""
    
    player_id: str
    reason: str = "normal"  # "normal", "timeout", "kicked"
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_LEAVE


# ===============================
# 游戏状态消息
# ===============================

@dataclass
class GameStateUpdateMessage(BaseGameMessage):
    """完整游戏状态更新消息"""
    
    players: List[Dict[str, Any]]  # 所有玩家状态
    bullets: List[Dict[str, Any]]  # 所有子弹状态
    game_time: float
    frame_id: int
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.GAME_STATE_UPDATE


@dataclass
class PlayerPositionUpdateMessage(BaseGameMessage):
    """玩家位置更新消息（轻量级）"""
    
    player_id: str
    position: Dict[str, float]
    velocity: Dict[str, float]
    rotation: float
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_POSITION_UPDATE


@dataclass
class BulletFiredMessage(BaseGameMessage):
    """子弹发射消息"""
    
    bullet_id: str
    owner_id: str
    start_position: Dict[str, float]
    velocity: Dict[str, float]
    damage: int
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.BULLET_FIRED


@dataclass
class BulletHitMessage(BaseGameMessage):
    """子弹击中消息"""
    
    bullet_id: str
    target_id: str  # 被击中的玩家ID
    hit_position: Dict[str, float]
    damage_dealt: int
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.BULLET_HIT


@dataclass
class BulletDestroyedMessage(BaseGameMessage):
    """子弹销毁消息"""
    
    bullet_id: str
    reason: str  # "expired", "collision", "boundary"
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.BULLET_DESTROYED


@dataclass
class CollisionMessage(BaseGameMessage):
    """碰撞事件消息"""
    
    bullet_id: str
    target_player_id: str
    damage_dealt: int
    new_health: int
    collision_position: Dict[str, float]
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.COLLISION


@dataclass
class PlayerDeathMessage(BaseGameMessage):
    """玩家死亡事件消息"""
    
    player_id: str
    killer_id: str
    death_position: Dict[str, float]
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_DEATH


@dataclass
class PlayerHitMessage(BaseGameMessage):
    """玩家被击中消息"""
    
    player_id: str
    attacker_id: str
    damage: int
    remaining_health: int
    hit_position: Dict[str, float]
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_HIT


@dataclass
class PlayerDestroyedMessage(BaseGameMessage):
    """玩家被摧毁消息"""
    
    player_id: str
    killer_id: str
    final_position: Dict[str, float]
    respawn_time: float
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_DESTROYED


# ===============================
# 房间管理消息
# ===============================

@dataclass
class RoomJoinMessage(BaseGameMessage):
    """加入房间消息"""
    
    player_id: str
    room_id: str
    password: Optional[str] = None
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ROOM_JOIN


@dataclass
class RoomLeaveMessage(BaseGameMessage):
    """离开房间消息"""
    
    player_id: str
    room_id: str
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ROOM_LEAVE


@dataclass
class RoomListMessage(BaseGameMessage):
    """房间列表消息"""
    
    rooms: List[Dict[str, Any]]  # 房间信息列表
    total_players: int
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ROOM_LIST


@dataclass
class RoomCreatedMessage(BaseGameMessage):
    """房间创建消息"""
    
    room_id: str
    room_name: str
    creator_id: str
    max_players: int
    game_mode: str
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ROOM_CREATED


# ===============================
# 系统消息
# ===============================

@dataclass
class ConnectionAckMessage(BaseGameMessage):
    """连接确认消息"""
    
    client_id: str
    server_time: float
    game_version: str
    assigned_player_id: str
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.CONNECTION_ACK


@dataclass
class PingMessage(BaseGameMessage):
    """Ping 消息"""
    
    client_id: str
    sequence: int
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PING


@dataclass
class PongMessage(BaseGameMessage):
    """Pong 消息"""
    
    client_id: str
    sequence: int
    server_timestamp: float
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PONG


@dataclass
class ErrorMessage(BaseGameMessage):
    """错误消息"""
    
    error_code: str
    error_message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ERROR


@dataclass
class DebugMessage(BaseGameMessage):
    """调试消息"""
    
    debug_type: str
    data: Dict[str, Any]
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.DEBUG


# ===============================
# 消息工厂和工具函数
# ===============================

# 消息类型映射
MESSAGE_TYPE_MAP = {
    GameMessageType.PLAYER_MOVE: PlayerMoveMessage,
    GameMessageType.PLAYER_STOP: PlayerStopMessage,
    GameMessageType.PLAYER_SHOOT: PlayerShootMessage,
    GameMessageType.PLAYER_JOIN: PlayerJoinMessage,
    GameMessageType.PLAYER_LEAVE: PlayerLeaveMessage,
    GameMessageType.GAME_STATE_UPDATE: GameStateUpdateMessage,
    GameMessageType.PLAYER_POSITION_UPDATE: PlayerPositionUpdateMessage,
    GameMessageType.BULLET_FIRED: BulletFiredMessage,
    GameMessageType.BULLET_HIT: BulletHitMessage,
    GameMessageType.BULLET_DESTROYED: BulletDestroyedMessage,
    GameMessageType.COLLISION: CollisionMessage,
    GameMessageType.PLAYER_DEATH: PlayerDeathMessage,
    GameMessageType.PLAYER_HIT: PlayerHitMessage,
    GameMessageType.PLAYER_DESTROYED: PlayerDestroyedMessage,
    GameMessageType.ROOM_JOIN: RoomJoinMessage,
    GameMessageType.ROOM_LEAVE: RoomLeaveMessage,
    GameMessageType.ROOM_LIST: RoomListMessage,
    GameMessageType.ROOM_CREATED: RoomCreatedMessage,
    GameMessageType.CONNECTION_ACK: ConnectionAckMessage,
    GameMessageType.PING: PingMessage,
    GameMessageType.PONG: PongMessage,
    GameMessageType.ERROR: ErrorMessage,
    GameMessageType.DEBUG: DebugMessage,
}


def parse_message(message_data: Union[str, Dict[str, Any]]) -> Optional[BaseGameMessage]:
    """解析消息数据为消息对象"""
    try:
        if isinstance(message_data, str):
            data = json.loads(message_data)
        else:
            data = message_data
        
        message_type = GameMessageType(data.get("type"))
        message_class = MESSAGE_TYPE_MAP.get(message_type)
        
        if not message_class:
            print(f"Unknown message type: {message_type}")
            return None
        
        # 移除 type 字段，因为它不是数据类的字段
        message_dict = {k: v for k, v in data.items() if k != "type"}
        
        return message_class(**message_dict)
    
    except Exception as e:
        print(f"Error parsing message: {e}")
        return None


def create_error_message(error_code: str, error_message: str, details: Optional[Dict] = None) -> ErrorMessage:
    """创建错误消息的便捷函数"""
    return ErrorMessage(
        error_code=error_code,
        error_message=error_message,
        details=details or {}
    )


def create_debug_message(debug_type: str, data: Dict[str, Any]) -> DebugMessage:
    """创建调试消息的便捷函数"""
    return DebugMessage(
        debug_type=debug_type,
        data=data
    )


# 类型别名
GameMessage = Union[
    PlayerMoveMessage, PlayerStopMessage, PlayerShootMessage,
    PlayerJoinMessage, PlayerLeaveMessage, GameStateUpdateMessage,
    PlayerPositionUpdateMessage, BulletFiredMessage, BulletHitMessage,
    BulletDestroyedMessage, CollisionMessage, PlayerDeathMessage,
    PlayerHitMessage, PlayerDestroyedMessage, RoomJoinMessage,
    RoomLeaveMessage, RoomListMessage, RoomCreatedMessage,
    ConnectionAckMessage, PingMessage, PongMessage, ErrorMessage, DebugMessage
] 