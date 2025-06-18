#!/usr/bin/env python3
"""
Tank game message system - based on Kable project's message-driven architecture

All frontend-backend interactions are done through standardized WebSocket messages,
ensuring type safety and extensibility.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import json


class GameMessageType(str, Enum):
    """All possible game message types"""
    
    # Player action messages
    PLAYER_MOVE = "player_move"
    PLAYER_STOP = "player_stop"
    PLAYER_SHOOT = "player_shoot"
    PLAYER_JOIN = "player_join"
    PLAYER_LEAVE = "player_leave"
    
    # Game state messages
    GAME_STATE_UPDATE = "game_state_update"
    PLAYER_POSITION_UPDATE = "player_position_update"
    BULLET_FIRED = "bullet_fired"
    BULLET_HIT = "bullet_hit"
    BULLET_DESTROYED = "bullet_destroyed"
    PLAYER_HIT = "player_hit"
    PLAYER_DESTROYED = "player_destroyed"
    PLAYER_DEATH = "player_death"
    COLLISION = "collision"
    GAME_VICTORY = "game_victory"
    GAME_DEFEAT = "game_defeat"
    
    # Room management messages
    ROOM_JOIN = "room_join"
    ROOM_LEAVE = "room_leave"
    ROOM_LIST = "room_list"
    ROOM_LIST_REQUEST = "room_list_request"
    ROOM_CREATED = "room_created"
    ROOM_START_GAME = "room_start_game"
    ROOM_END_GAME = "room_end_game"
    ROOM_UPDATE = "room_update"
    ROOM_DELETED = "room_deleted"
    ROOM_DISBANDED = "room_disbanded"
    SERVER_LIST = "server_list"
    CREATE_ROOM_REQUEST = "create_room_request"
    SLOT_CHANGE_REQUEST = "slot_change_request"
    SLOT_CHANGED = "slot_changed"
    
    # System messages
    CONNECTION_ACK = "connection_ack"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    DEBUG = "debug"


@dataclass
class BaseGameMessage(ABC):
    """Base class for all game messages"""
    
    def __post_init__(self):
        """Initialize timestamp"""
        if not hasattr(self, "timestamp") or self.timestamp is None:
            self.timestamp = time.time()
    
    @property
    @abstractmethod
    def type(self) -> GameMessageType:
        """Return message type"""
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for transmission"""
        data = asdict(self)
        data["type"] = self.type.value
        return data
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())


# ===============================
# Player action messages
# ===============================

@dataclass
class PlayerMoveMessage(BaseGameMessage):
    """Player movement message"""
    
    player_id: str
    direction: Dict[str, bool]  # {"w": True, "a": False, "s": False, "d": True}
    position: Dict[str, float]  # {"x": 100.0, "y": 200.0}
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_MOVE


@dataclass
class PlayerStopMessage(BaseGameMessage):
    """Player stop movement message"""
    
    player_id: str
    position: Dict[str, float]  # Final position
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_STOP


@dataclass
class PlayerShootMessage(BaseGameMessage):
    """Player shooting message"""
    
    player_id: str
    position: Dict[str, float]  # Shooting start position
    direction: Dict[str, float]  # Shooting direction vector
    bullet_id: str
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_SHOOT


@dataclass
class PlayerJoinMessage(BaseGameMessage):
    """Player join game message"""
    
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
    """Player leave game message"""
    
    player_id: str
    reason: str = "normal"  # "normal", "timeout", "kicked"
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_LEAVE


# ===============================
# Game state messages
# ===============================

@dataclass
class GameStateUpdateMessage(BaseGameMessage):
    """Complete game state update message"""
    
    players: List[Dict[str, Any]]  # All player states
    bullets: List[Dict[str, Any]]  # All bullet states
    game_time: float
    frame_id: int
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.GAME_STATE_UPDATE


@dataclass
class PlayerPositionUpdateMessage(BaseGameMessage):
    """Player position update message (lightweight)"""
    
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
    """Bullet fired message"""
    
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
    """Bullet hit message"""
    
    bullet_id: str
    target_id: str  # Hit player ID
    hit_position: Dict[str, float]
    damage_dealt: int
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.BULLET_HIT


@dataclass
class BulletDestroyedMessage(BaseGameMessage):
    """Bullet destroyed message"""
    
    bullet_id: str
    reason: str  # "expired", "collision", "boundary"
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.BULLET_DESTROYED


@dataclass
class CollisionMessage(BaseGameMessage):
    """Collision event message"""
    
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
    """Player death event message"""
    
    player_id: str
    killer_id: str
    death_position: Dict[str, float]
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_DEATH


@dataclass
class GameVictoryMessage(BaseGameMessage):
    """Game victory message - sent to the winner"""
    
    winner_player_id: str
    winner_player_name: str
    room_id: str
    game_duration: float
    total_players: int
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.GAME_VICTORY


@dataclass
class GameDefeatMessage(BaseGameMessage):
    """Game defeat message - sent to eliminated players"""
    
    eliminated_player_id: str
    eliminated_player_name: str
    killer_id: str
    killer_name: str
    room_id: str
    survival_time: float
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.GAME_DEFEAT


@dataclass
class PlayerHitMessage(BaseGameMessage):
    """Player hit message"""
    
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
    """Player destroyed message"""
    
    player_id: str
    killer_id: str
    final_position: Dict[str, float]
    respawn_time: float
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PLAYER_DESTROYED


# ===============================
# Room management messages
# ===============================

@dataclass
class RoomJoinMessage(BaseGameMessage):
    """Join room message"""
    
    player_id: str
    room_id: str
    password: Optional[str] = None
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ROOM_JOIN


@dataclass
class RoomLeaveMessage(BaseGameMessage):
    """Leave room message"""
    
    player_id: str
    room_id: str
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ROOM_LEAVE


@dataclass
class RoomListMessage(BaseGameMessage):
    """Room list message"""
    
    rooms: List[Dict[str, Any]]  # Room information list
    total_players: int
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ROOM_LIST


@dataclass
class RoomListRequestMessage(BaseGameMessage):
    """Request room list message"""
    
    client_id: str
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ROOM_LIST_REQUEST


@dataclass
class RoomCreatedMessage(BaseGameMessage):
    """Room created message"""
    
    room_id: str
    room_name: str
    creator_id: str
    max_players: int
    game_mode: str
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ROOM_CREATED


@dataclass
class CreateRoomRequestMessage(BaseGameMessage):
    """Create room request message"""
    
    room_name: str
    max_players: int
    creator_id: str
    game_mode: str = "classic"
    password: Optional[str] = None
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.CREATE_ROOM_REQUEST


@dataclass
class RoomStartGameMessage(BaseGameMessage):
    """Room start game message"""
    
    room_id: str
    host_player_id: str
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ROOM_START_GAME


@dataclass
class RoomEndGameMessage(BaseGameMessage):
    """Room end game message"""
    
    room_id: str
    reason: str = "host_ended"  # "host_ended", "all_players_dead", "timeout"
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ROOM_END_GAME


@dataclass
class RoomUpdateMessage(BaseGameMessage):
    """Room state update message"""
    
    room_data: Dict[str, Any]  # Complete room data
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ROOM_UPDATE


@dataclass
class RoomDeletedMessage(BaseGameMessage):
    """Room deleted message"""
    
    room_id: str
    reason: str = "host_left"  # "host_left", "empty", "expired"
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ROOM_DELETED


@dataclass
class RoomDisbandedMessage(BaseGameMessage):
    """Room disbanded message - host actively disbands room"""
    
    room_id: str
    disbanded_by: str  # player_id of disbander
    reason: str = "host_quit"  # "host_quit", "host_disconnected"
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ROOM_DISBANDED


@dataclass
class ServerListMessage(BaseGameMessage):
    """Server list message"""
    
    servers: List[Dict[str, Any]]  # Server information list
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.SERVER_LIST


@dataclass
class SlotChangeRequestMessage(BaseGameMessage):
    """Slot change request message"""
    
    player_id: str
    target_slot: int
    room_id: str = "default"
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.SLOT_CHANGE_REQUEST


@dataclass
class SlotChangedMessage(BaseGameMessage):
    """Slot change completed message"""
    
    player_id: str
    old_slot: int
    new_slot: int
    room_id: str = "default"
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.SLOT_CHANGED


# ===============================
# System messages
# ===============================

@dataclass
class ConnectionAckMessage(BaseGameMessage):
    """Connection acknowledgment message"""
    
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
    """Ping message"""
    
    client_id: str
    sequence: int
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PING


@dataclass
class PongMessage(BaseGameMessage):
    """Pong message"""
    
    client_id: str
    sequence: int
    server_timestamp: float
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.PONG


@dataclass
class ErrorMessage(BaseGameMessage):
    """Error message"""
    
    error_code: str
    error_message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.ERROR


@dataclass
class DebugMessage(BaseGameMessage):
    """Debug message"""
    
    debug_type: str
    data: Dict[str, Any]
    timestamp: Optional[float] = None
    
    @property
    def type(self) -> GameMessageType:
        return GameMessageType.DEBUG


# ===============================
# Message factory and utility functions
# ===============================

# Message type mapping
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
    GameMessageType.GAME_VICTORY: GameVictoryMessage,
    GameMessageType.GAME_DEFEAT: GameDefeatMessage,
    GameMessageType.PLAYER_HIT: PlayerHitMessage,
    GameMessageType.PLAYER_DESTROYED: PlayerDestroyedMessage,
    GameMessageType.ROOM_JOIN: RoomJoinMessage,
    GameMessageType.ROOM_LEAVE: RoomLeaveMessage,
    GameMessageType.ROOM_LIST: RoomListMessage,
    GameMessageType.ROOM_LIST_REQUEST: RoomListRequestMessage,
    GameMessageType.ROOM_CREATED: RoomCreatedMessage,
    GameMessageType.CREATE_ROOM_REQUEST: CreateRoomRequestMessage,
    GameMessageType.ROOM_START_GAME: RoomStartGameMessage,
    GameMessageType.ROOM_DISBANDED: RoomDisbandedMessage,
    GameMessageType.CONNECTION_ACK: ConnectionAckMessage,
    GameMessageType.PING: PingMessage,
    GameMessageType.PONG: PongMessage,
    GameMessageType.ERROR: ErrorMessage,
    GameMessageType.DEBUG: DebugMessage,
    GameMessageType.SLOT_CHANGE_REQUEST: SlotChangeRequestMessage,
    GameMessageType.SLOT_CHANGED: SlotChangedMessage,
}


def parse_message(message_data: Union[str, Dict[str, Any]]) -> Optional[BaseGameMessage]:
    """Parse message data to message object"""
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
        
        # Remove type field as it's not a dataclass field
        message_dict = {k: v for k, v in data.items() if k != "type"}
        
        return message_class(**message_dict)
    
    except Exception as e:
        print(f"Error parsing message: {e}")
        return None


def create_error_message(error_code: str, error_message: str, details: Optional[Dict] = None) -> ErrorMessage:
    """Convenience function to create error message"""
    return ErrorMessage(
        error_code=error_code,
        error_message=error_message,
        details=details or {}
    )


def create_debug_message(debug_type: str, data: Dict[str, Any]) -> DebugMessage:
    """Convenience function to create debug message"""
    return DebugMessage(
        debug_type=debug_type,
        data=data
    )


# Type alias
GameMessage = Union[
    PlayerMoveMessage, PlayerStopMessage, PlayerShootMessage,
    PlayerJoinMessage, PlayerLeaveMessage, GameStateUpdateMessage,
    PlayerPositionUpdateMessage, BulletFiredMessage, BulletHitMessage,
    BulletDestroyedMessage, CollisionMessage, PlayerDeathMessage,
    GameVictoryMessage, GameDefeatMessage,
    PlayerHitMessage, PlayerDestroyedMessage, RoomJoinMessage,
    RoomLeaveMessage, RoomListMessage, RoomCreatedMessage,
    CreateRoomRequestMessage, RoomStartGameMessage,
    ConnectionAckMessage, PingMessage, PongMessage, ErrorMessage, DebugMessage,
    SlotChangeRequestMessage, SlotChangedMessage
] 