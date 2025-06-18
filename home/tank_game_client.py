#!/usr/bin/env python3
"""
Perfect tank game client - eliminates position jitter and prediction inconsistencies

Core principles:
1. Frontend and server use exactly the same movement algorithms
2. Key event-driven state machine
3. Single authoritative position source
4. Minimize position corrections
"""

import asyncio
import json
import math
import os
import sys
import time
import uuid
import socket
from typing import Dict, Optional, List, Any
import pygame
import websockets
from websockets.client import WebSocketClientProtocol
from dotenv import load_dotenv
import argparse

# Add shared directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'shared'))

from tank_game_messages import *
# Import shared entity classes
from tank_game_entities import Player, Bullet
# Import state machine system
from game_states import GameStateManager, GameStateType
from game_state_implementations import MainMenuState, ServerBrowserState, RoomLobbyState, InGameState

# Load environment variables - use shared .env file from project root
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

def get_local_ip():
    """Get local machine IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # Create a fake UDP connection to Google DNS
        s.connect(("8.8.8.8", 80)) #Google DNS, safe and reliable
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
        return "127.0.0.1"  # Final fallback

# Game configuration
SCREEN_WIDTH = int(os.getenv('SCREEN_WIDTH', 800))
SCREEN_HEIGHT = int(os.getenv('SCREEN_HEIGHT', 600))
FPS = int(os.getenv('FPS', 60))
TANK_SPEED = int(os.getenv('TANK_SPEED', 300))
DEFAULT_FONT_PATH = os.getenv('DEFAULT_FONT_PATH', None)

# Server connection configuration - use real IP address
DEFAULT_LOCAL_IP = get_local_ip()
SERVER_PORT = int(os.getenv('SERVER_PORT', 8765))
DEFAULT_SERVER_URL = f"ws://{DEFAULT_LOCAL_IP}:{SERVER_PORT}"


print(f"🌐 Auto-detected local IP: {DEFAULT_LOCAL_IP}")

# Color definitions
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

class GameClient:
    """Perfect game client - now uses state machine system"""
    
    def __init__(self, server_url: str = None):
        self.server_url = server_url or DEFAULT_SERVER_URL
        self.websocket: Optional[WebSocketClientProtocol] = None
        self.connected = False
        
        # Client state
        self.client_id: Optional[str] = None
        self.player_id: Optional[str] = None
        self.player_name = f"Player_{int(time.time()) % 10000}"
        
        # Game state
        self.players: Dict[str, Player] = {}
        self.bullets: Dict[str, Bullet] = {}
        
        # Room list (for server browser)
        self.room_list: List[Dict[str, Any]] = []
        
        # Game result state
        self.game_result = None  # None, "victory", "defeat"
        self.game_result_data = None  # Store victory/defeat message data
        
        # Input state - simplified key state machine
        self.input_state = {
            'w': False, 'a': False, 's': False, 'd': False,
            'mouse_clicked': False,
            'mouse_pos': (400, 300)
        }
        self.last_input_state = self.input_state.copy()
        
        # Ping related
        self.ping_sequence = 0
        self.ping_times: Dict[int, float] = {}
        self.current_ping = 0
        
        # Send optimization
        self.last_movement_send = 0
        self.movement_send_interval = 0.05  # 20 FPS send, reduced from 33 FPS
        self.position_change_threshold = 5.0  # Position change threshold
        
        # Performance monitoring
        self.frame_count = 0
        self.fps_counter = 0
        self.last_fps_time = time.time()
        
        # Initialize Pygame
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption(f"Tank Wars - Perfect Edition ✨ ({SCREEN_WIDTH}x{SCREEN_HEIGHT})")
        self.clock = pygame.time.Clock()
        
        # Fonts
        try:
            # Try to load specified font file
            if DEFAULT_FONT_PATH and os.path.exists(DEFAULT_FONT_PATH):
                self.font = pygame.font.Font(DEFAULT_FONT_PATH, 24)
                self.small_font = pygame.font.Font(DEFAULT_FONT_PATH, 16)
                self.big_font = pygame.font.Font(DEFAULT_FONT_PATH, 32)
                print(f"✅ Loaded custom font: {DEFAULT_FONT_PATH}")
            else:
                # Font file doesn't exist, use default font
                self.font = pygame.font.Font(None, 24)
                self.small_font = pygame.font.Font(None, 16)
                self.big_font = pygame.font.Font(None, 32)
        except Exception as e:
            print(f"⚠️ Error loading font: {e}, using default font")
        
        # Initialize state machine
        self.state_manager = GameStateManager()
        self._register_states()
        
        # Auto-connect to server
        asyncio.create_task(self.connect())
        
        print(f"✨ GameClient initialized for {self.server_url}")
    
    def _register_states(self):
        """Register game states"""
        # Set client reference for state manager, used for cleanup operations between states
        self.state_manager.client_ref = self
        
        # Register all states
        self.state_manager.register_state(GameStateType.MAIN_MENU, MainMenuState(self.state_manager))
        self.state_manager.register_state(GameStateType.SERVER_BROWSER, ServerBrowserState(self.state_manager))
        
        # Room lobby state needs special handling
        room_lobby_state = RoomLobbyState(self.state_manager)
        room_lobby_state.set_client(self)
        self.state_manager.register_state(GameStateType.ROOM_LOBBY, room_lobby_state)
        
        # Game state needs client reference
        in_game_state = InGameState(self.state_manager)
        in_game_state.client = self
        self.state_manager.register_state(GameStateType.IN_GAME, in_game_state)
        
        # Start by entering main menu
        self.state_manager.change_state(GameStateType.MAIN_MENU)
    
    def set_server_url(self, server_url: str):
        """Set server URL"""
        self.server_url = server_url
        print(f"🔄 Server URL changed to: {server_url}")
    
    async def connect(self):
        """Connect to server - auto-connect during initialization"""
        try:
            print(f"🔗 Connecting to {self.server_url}...")
            self.websocket = await websockets.connect(self.server_url)
            self.connected = True
            print("✅ Connected to server")
            
            # Start message receiving loop
            asyncio.create_task(self.message_loop())
            
        except Exception as e:
            print(f"❌ Failed to connect: {e}")
            self.connected = False
    
    async def disconnect(self):
        """Disconnect"""
        if self.connected and self.websocket and self.player_id:
            try:
                # Send leave message
                leave_message = PlayerLeaveMessage(
                    player_id=self.player_id,
                    reason="normal"
                )
                await self.send_message(leave_message)
                print(f"📤 Sent leave message for player {self.player_id}")
                
                # Wait briefly to ensure message is sent
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"⚠️ Error sending leave message: {e}")
        
        if self.websocket:
            await self.websocket.close()
        self.connected = False
        print("🔌 Disconnected from server")
    
    async def send_message(self, message: GameMessage):
        """Send message to server"""
        if not self.websocket or not self.connected:
            return
        
        try:
            await self.websocket.send(message.to_json())
        except Exception as e:
            print(f"❌ Error sending message: {e}")
    
    async def message_loop(self):
        """Message receiving loop"""
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
        """Handle received messages"""
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
        elif message.type == GameMessageType.GAME_VICTORY:
            await self.handle_game_victory(message)
        elif message.type == GameMessageType.GAME_DEFEAT:
            await self.handle_game_defeat(message)
        elif message.type == GameMessageType.PLAYER_JOIN:
            await self.handle_player_join(message)
        elif message.type == GameMessageType.PLAYER_LEAVE:
            await self.handle_player_leave(message)
        elif message.type == GameMessageType.ROOM_CREATED:
            await self.handle_room_created(message)
        elif message.type == GameMessageType.ROOM_START_GAME:
            await self.handle_room_start_game(message)
        elif message.type == GameMessageType.ROOM_LIST:
            await self.handle_room_list(message)
        elif message.type == GameMessageType.ROOM_DISBANDED:
            await self.handle_room_disbanded(message)
        elif message.type == GameMessageType.SLOT_CHANGED:
            await self.handle_slot_changed(message)
        elif message.type == GameMessageType.PONG:
            await self.handle_pong(message)
        elif message.type == GameMessageType.ERROR:
            await self.handle_error(message)
        else:
            print(f"⚠️ Unhandled message type: {message.type}")
    
    async def handle_connection_ack(self, message: ConnectionAckMessage):
        """Handle connection acknowledgment"""
        self.client_id = message.client_id
        self.player_id = message.assigned_player_id
        print(f"🆔 Assigned player ID: {self.player_id}")
        
        # Check if auto-join is needed (for non-host clients)
        current_state = self.state_manager.get_current_state_type()
        if current_state == GameStateType.ROOM_LOBBY:
            room_lobby_state = self.state_manager.states.get(GameStateType.ROOM_LOBBY)
            if room_lobby_state and not room_lobby_state.is_host:
                # Non-host client, join default room
                join_message = PlayerJoinMessage(
                    player_id=self.player_id,
                    player_name=self.player_name,
                    room_id="default"  # Join default room
                )
                await self.send_message(join_message)
                print(f"📤 Sent join message for default room")
        # Host client doesn't send join message here, waits for room creation success
    
    async def handle_game_state_update(self, message: GameStateUpdateMessage):
        """Handle game state update - perfect sync"""
        # Update player states
        for player_data in message.players:
            player_id = player_data['player_id']
            if player_id in self.players:
                # 区分本地玩家和远程玩家的更新逻辑
                if player_id == self.player_id:
                    # 本地玩家：只更新非位置属性，避免与客户端预测冲突
                    self.players[player_id].health = player_data.get('health', 100)
                    self.players[player_id].is_alive = player_data.get('is_alive', True)
                    self.players[player_id].slot_index = player_data.get('slot_index', 0)
                    # 不更新本地玩家的位置或移动方向
                else:
                    # 远程玩家：更新所有属性，包括位置校正
                    self.players[player_id].update_from_server(
                        player_data['position'],
                        player_data.get('moving_directions')
                    )
                    # 更新其他属性
                    self.players[player_id].health = player_data.get('health', 100)
                    self.players[player_id].is_alive = player_data.get('is_alive', True)
                    self.players[player_id].slot_index = player_data.get('slot_index', 0)
            else:
                # 新玩家
                new_player = Player(player_data)
                # 为新玩家设置客户端引用，用于区分本地/远程玩家
                if player_id == self.player_id:
                    new_player.is_local_player = True
                else:
                    new_player.is_local_player = False
                
                self.players[player_id] = new_player
                
                if player_id == self.player_id:
                    print(f"🎮 Local player initialized at slot {new_player.slot_index}, position {new_player.position}")
        
        # Update bullet states
        server_bullets = {b['bullet_id']: b for b in message.bullets}
        
        # Add new bullets
        for bullet_id, bullet_data in server_bullets.items():
            if bullet_id not in self.bullets:
                self.bullets[bullet_id] = Bullet(bullet_data)
        
        # Remove bullets that don't exist on server
        bullets_to_remove = []
        for bullet_id in self.bullets:
            if bullet_id not in server_bullets:
                bullets_to_remove.append(bullet_id)
        
        for bullet_id in bullets_to_remove:
            del self.bullets[bullet_id]
        
        # If currently in room lobby state, update room display
        current_state = self.state_manager.get_current_state_type()
        if current_state == GameStateType.ROOM_LOBBY:
            room_data = {
                'players': message.players,
                'game_time': message.game_time,
                'frame_id': message.frame_id
            }
            self.update_room_display(room_data)
    
    async def handle_player_move(self, message: PlayerMoveMessage):
        """Handle other player movement"""
        if message.player_id != self.player_id and message.player_id in self.players:
            # Always update movement directions for immediate response
            self.players[message.player_id].moving_directions = message.direction
            
            # Use server position as a reference for correction, but allow smooth movement
            if message.position:
                self.players[message.player_id].update_from_server(message.position, message.direction)
            
            # 为了调试，记录远程玩家的移动
            if any(message.direction.values()):
                moving_keys = [k for k, v in message.direction.items() if v]
                print(f"🎮 Remote player {message.player_id} moving: {moving_keys}")
    
    async def handle_player_stop(self, message: PlayerStopMessage):
        """Handle other player stop"""
        if message.player_id != self.player_id and message.player_id in self.players:
            # Use server position for final stop position
            if message.position:
                self.players[message.player_id].update_from_server(message.position)
            
            # Immediately stop movement
            self.players[message.player_id].moving_directions = {
                "w": False, "a": False, "s": False, "d": False
            }
            
            print(f"🛑 Remote player {message.player_id} stopped")
    
    async def handle_bullet_fired(self, message: BulletFiredMessage):
        """Handle bullet fired"""
        bullet_data = {
            'bullet_id': message.bullet_id,
            'owner_id': message.owner_id,
            'position': message.start_position,
            'velocity': message.velocity,
            'damage': message.damage,
            'created_time': time.time()
        }
        self.bullets[message.bullet_id] = Bullet(bullet_data)
    
    async def handle_collision(self, message: CollisionMessage):
        """Handle collision events"""
        if message.target_player_id in self.players:
            self.players[message.target_player_id].health = message.new_health
            if message.new_health <= 0:
                self.players[message.target_player_id].is_alive = False
    
    async def handle_bullet_destroyed(self, message: BulletDestroyedMessage):
        """Handle bullet destruction"""
        if message.bullet_id in self.bullets:
            del self.bullets[message.bullet_id]
    
    async def handle_player_death(self, message: PlayerDeathMessage):
        """Handle player death"""
        if message.player_id in self.players:
            self.players[message.player_id].is_alive = False
            self.players[message.player_id].health = 0
    
    async def handle_game_victory(self, message):
        """Handle game victory"""
        from tank_game_messages import GameVictoryMessage
        if isinstance(message, GameVictoryMessage):
            print(f"🏆 Victory! {message.winner_player_name} won the game!")
            
            # Set victory state for local player
            if message.winner_player_id == self.player_id:
                self.game_result = "victory"
                self.game_result_data = message
                print(f"🎉 You won! Game duration: {message.game_duration:.1f}s")
        else:
            print(f"⚠️ Unexpected game victory message type: {type(message)}")
    
    async def handle_game_defeat(self, message):
        """Handle game defeat"""
        from tank_game_messages import GameDefeatMessage
        if isinstance(message, GameDefeatMessage):
            print(f"💔 Defeat! {message.eliminated_player_name} was eliminated by {message.killer_name}")
            
            # Set defeat state for local player
            if message.eliminated_player_id == self.player_id:
                self.game_result = "defeat"
                self.game_result_data = message
                print(f"😵 You were eliminated! Survival time: {message.survival_time:.1f}s")
        else:
            print(f"⚠️ Unexpected game defeat message type: {type(message)}")
    
    async def handle_player_join(self, message: PlayerJoinMessage):
        """Handle player join"""
        print(f"👤 Player {message.player_name} joined")
    
    async def handle_player_leave(self, message: PlayerLeaveMessage):
        """Handle player leave"""
        if message.player_id in self.players:
            player_name = self.players[message.player_id].name
            print(f"👋 Player {player_name} left")
            del self.players[message.player_id]
    
    async def handle_room_created(self, message: RoomCreatedMessage):
        """Handle room creation success"""
        print(f"🏠 Room created successfully: {message.room_name} (ID: {message.room_id})")
        
        # Update room lobby state's room ID
        room_lobby_state = self.state_manager.states.get(GameStateType.ROOM_LOBBY)
        if room_lobby_state:
            room_lobby_state.room_id = message.room_id
            print(f"🔄 Updated room lobby state with room ID: {message.room_id}")
        
        # Send join game message, specify room ID
        join_message = PlayerJoinMessage(
            player_id=self.player_id,
            player_name=self.player_name,
            room_id=message.room_id
        )
        await self.send_message(join_message)
        print(f"📤 Sent join message for room {message.room_id}")
    
    async def handle_room_start_game(self, message):
        """Handle room start game"""
        from tank_game_messages import RoomStartGameMessage
        if isinstance(message, RoomStartGameMessage):
            print(f"🚀 Game starting in room {message.room_id} by host {message.host_player_id}")
            
            # Clear previous game state
            self.bullets.clear()
            
            # Switch to game state
            current_state = self.state_manager.get_current_state_type()
            if current_state == GameStateType.ROOM_LOBBY:
                print("🎮 Switching to IN_GAME state")
                self.state_manager.change_state(GameStateType.IN_GAME)
            else:
                print(f"⚠️ Received game start while in unexpected state: {current_state}")
        else:
            print(f"⚠️ Unexpected room start game message type: {type(message)}")
    
    async def handle_room_list(self, message):
        """Handle room list response"""
        from tank_game_messages import RoomListMessage
        if isinstance(message, RoomListMessage):
            self.room_list = message.rooms
            print(f"📋 Received room list: {len(self.room_list)} rooms")
            for room in self.room_list:
                print(f"   • {room['name']} (ID: {room['room_id']}) - {room['current_players']}/{room['max_players']} players")
        else:
            print(f"⚠️ Unexpected room list message type: {type(message)}")
    
    async def handle_room_disbanded(self, message):
        """Handle room disbanded"""
        from tank_game_messages import RoomDisbandedMessage
        if isinstance(message, RoomDisbandedMessage):
            print(f"🏠 Room {message.room_id} disbanded by {message.disbanded_by} (reason: {message.reason})")
            
            # Clear game state
            self.players.clear()
            self.bullets.clear()
            
            # If currently in room lobby state, auto-return to main menu
            current_state = self.state_manager.get_current_state_type()
            if current_state in [GameStateType.ROOM_LOBBY, GameStateType.IN_GAME]:
                print("🔄 Room disbanded - returning to main menu")
                self.state_manager.change_state(GameStateType.MAIN_MENU)
        else:
            print(f"⚠️ Unexpected room disbanded message type: {type(message)}")
    
    async def handle_slot_changed(self, message: SlotChangedMessage):
        """Handle player slot change"""
        if message.player_id in self.players:
            self.players[message.player_id].slot_index = message.new_slot
            print(f"🎮 Player {message.player_id} moved to slot {message.new_slot + 1}")
        
        # If it's local player's slot change, give feedback
        if message.player_id == self.player_id:
            print(f"✅ You moved to slot {message.new_slot + 1}")
    
    async def handle_pong(self, message: PongMessage):
        """Handle Pong response"""
        if message.sequence in self.ping_times:
            ping_time = time.time() - self.ping_times[message.sequence]
            self.current_ping = int(ping_time * 1000)
            del self.ping_times[message.sequence]
    
    async def handle_error(self, message: ErrorMessage):
        """Handle error messages"""
        print(f"❌ Server error: {message.error_code} - {message.error_message}")
    
    async def send_ping(self):
        """Send Ping"""
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
        """Handle input events - key event driven"""
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
            if event.button == 1:  # Left click
                self.input_state['mouse_clicked'] = True
                print(f"🖱️ Mouse clicked at {event.pos}, state: connected={self.connected}, player_id={self.player_id}")
        
        elif event.type == pygame.MOUSEMOTION:
            # Directly use mouse coordinates
            self.input_state['mouse_pos'] = event.pos
    
    def update_fps_counter(self):
        """Update FPS counter"""
        self.frame_count += 1
        current_time = time.time()
        if current_time - self.last_fps_time >= 1.0:
            self.fps_counter = self.frame_count
            self.frame_count = 0
            self.last_fps_time = current_time

    def update_local_player(self, dt: float):
        """Update local player - exactly same algorithm as server"""
        if not self.player_id or self.player_id not in self.players:
            return
        
        local_player = self.players[self.player_id]
        
        # Update movement direction state
        local_player.moving_directions = {
            'w': self.input_state['w'],
            'a': self.input_state['a'],
            's': self.input_state['s'],
            'd': self.input_state['d']
        }
        
        # Use same position update algorithm as server
        local_player.update_position(dt)
    
    async def send_movement_if_changed(self):
        """Smart send movement messages - only send when truly needed"""
        current_time = time.time()
        
        if not self.connected or not self.player_id or self.player_id not in self.players:
            return
        
        # Check if input changed
        movement_keys = ['w', 'a', 's', 'd']
        input_changed = any(
            self.input_state[key] != self.last_input_state[key] 
            for key in movement_keys
        )
        
        # Check if position has significant change
        current_player = self.players[self.player_id]
        position_changed = False
        dx, dy = 0.0, 0.0  # Initialize variables
        
        if hasattr(self, 'last_sent_position'):
            dx = abs(current_player.position['x'] - self.last_sent_position['x'])
            dy = abs(current_player.position['y'] - self.last_sent_position['y'])
            position_changed = (dx > self.position_change_threshold or 
                              dy > self.position_change_threshold)
        else:
            position_changed = True  # First send
        
        # Periodic send (prevent packet loss) - increased interval
        time_since_last_send = current_time - self.last_movement_send
        periodic_send = time_since_last_send > (self.movement_send_interval * 5)  # Force send every 5 cycles instead of 3
        
        # More conservative sending - only send on input changes or significant position changes
        should_send = (input_changed or 
                      (position_changed and time_since_last_send > self.movement_send_interval) or
                      periodic_send)
        
        if should_send:
            directions = {
                'w': self.input_state['w'],
                'a': self.input_state['a'],
                's': self.input_state['s'],
                'd': self.input_state['d']
            }
            
            # Use current player position
            current_position = current_player.position.copy()
            
            move_message = PlayerMoveMessage(
                player_id=self.player_id,
                direction=directions,
                position=current_position
            )
            await self.send_message(move_message)
            
            # Update send records
            self.last_movement_send = current_time
            self.last_input_state = self.input_state.copy()
            self.last_sent_position = current_position.copy()
            
            # Reduced debug info
            if input_changed:
                print(f"📤 Input changed: {directions}")
            elif periodic_send:
                print(f"📤 Periodic send (anti-packet-loss)")
    
    async def send_shoot(self):
        """Send shoot message - use accurate player position"""
        if not self.connected or not self.player_id or self.player_id not in self.players:
            print(f"🚫 Cannot shoot: connected={self.connected}, player_id={self.player_id}, in_players={self.player_id in self.players if self.player_id else False}")
            return
        
        # Use current player's accurate position
        player_pos = self.players[self.player_id].position
        
        # Calculate shooting direction
        mouse_x, mouse_y = self.input_state['mouse_pos']
        dx = mouse_x - player_pos['x']
        dy = mouse_y - player_pos['y']
        
        # Normalize direction vector
        length = math.sqrt(dx * dx + dy * dy)
        if length > 0:
            dx /= length
            dy /= length
        
        # Send shoot message
        shoot_message = PlayerShootMessage(
            player_id=self.player_id,
            position=player_pos,  # Use accurate position
            direction={"x": dx, "y": dy},
            bullet_id=str(uuid.uuid4())
        )
        await self.send_message(shoot_message)
        print(f"💥 Sent shoot message: pos=({player_pos['x']:.1f}, {player_pos['y']:.1f}), dir=({dx:.2f}, {dy:.2f})")
        
        # Reset click state
        self.input_state['mouse_clicked'] = False
    
    def update_game_objects(self, dt: float):
        """Update game objects - 为远程玩家使用与本地玩家相同的移动算法"""
        # Use the same movement algorithm for remote players as local players
        # This ensures smooth movement while maintaining consistency
        
        # Update remote players using the same movement algorithm as local player
        for player_id, player in self.players.items():
            if player_id != self.player_id:  # Only update remote players
                # Use the same position update algorithm as local player
                # This provides smooth movement based on direction states from server
                player.update_position(dt)
        
        # Update bullet positions
        bullets_to_remove = []
        for bullet_id, bullet in self.bullets.items():
            if not bullet.update(dt):
                bullets_to_remove.append(bullet_id)
        
        # Remove invalid bullets
        for bullet_id in bullets_to_remove:
            del self.bullets[bullet_id]
    
    def render(self):
        """Perfect render - draw directly on screen"""
        # Draw directly on screen
        self.screen.fill(COLORS['BLACK'])
        
        # Render players
        for player_id, player in self.players.items():
            if not player.is_alive:
                continue
                
            pos = player.position  # Use single position source
            color = COLORS['GREEN'] if player_id == self.player_id else COLORS['BLUE']
            
            # Draw tank
            tank_rect = pygame.Rect(pos['x'] - 15, pos['y'] - 15, 30, 30)
            pygame.draw.rect(self.screen, color, tank_rect)
            
            # If local player, add special marker
            if player_id == self.player_id:
                pygame.draw.rect(self.screen, COLORS['ORANGE'], tank_rect, 3)
            
            # Draw player name
            name_text = self.small_font.render(player.name, True, COLORS['WHITE'])
            name_rect = name_text.get_rect(center=(pos['x'], pos['y'] - 25))
            self.screen.blit(name_text, name_rect)
            
            # Draw health bar
            if player.health < player.max_health:
                health_ratio = player.health / player.max_health
                health_width = 30
                health_height = 4
                
                # Background
                health_bg = pygame.Rect(pos['x'] - 15, pos['y'] - 35, health_width, health_height)
                pygame.draw.rect(self.screen, COLORS['RED'], health_bg)
                
                # Health
                health_fg = pygame.Rect(pos['x'] - 15, pos['y'] - 35, 
                                      health_width * health_ratio, health_height)
                pygame.draw.rect(self.screen, COLORS['GREEN'], health_fg)
        
        # Render bullets
        for bullet in self.bullets.values():
            pos = bullet.position
            pygame.draw.circle(self.screen, COLORS['YELLOW'], 
                             (int(pos['x']), int(pos['y'])), 4)
            # Bullet center point
            pygame.draw.circle(self.screen, COLORS['WHITE'], 
                             (int(pos['x']), int(pos['y'])), 2)
        
        # Render UI
        self.render_ui()
        
        pygame.display.flip()
        
        # Update FPS count
        self.update_fps_counter()
    
    def render_ui(self):
        """Render UI information"""
        y_offset = 10
        
        # Connection status
        status_text = "Connected" if self.connected else "Disconnected"
        status_color = COLORS['GREEN'] if self.connected else COLORS['RED']
        status_surface = self.font.render(f"Status: {status_text}", True, status_color)
        self.screen.blit(status_surface, (10, y_offset))
        y_offset += 25
        
        # Player info
        if self.player_id:
            player_text = f"Player: {self.player_name}"
            player_surface = self.font.render(player_text, True, COLORS['WHITE'])
            self.screen.blit(player_surface, (10, y_offset))
            y_offset += 25
        
        # Network latency
        ping_color = COLORS['GREEN'] if self.current_ping < 50 else COLORS['ORANGE'] if self.current_ping < 100 else COLORS['RED']
        ping_text = f"Ping: {self.current_ping}ms"
        ping_surface = self.font.render(ping_text, True, ping_color)
        self.screen.blit(ping_surface, (10, y_offset))
        y_offset += 25
        
        # FPS display
        fps_color = COLORS['GREEN'] if self.fps_counter >= 55 else COLORS['ORANGE'] if self.fps_counter >= 30 else COLORS['RED']
        fps_text = f"FPS: {self.fps_counter}"
        fps_surface = self.font.render(fps_text, True, fps_color)
        self.screen.blit(fps_surface, (10, y_offset))
        y_offset += 25
        
        # Game statistics
        stats_text = f"Players: {len(self.players)} | Bullets: {len(self.bullets)}"
        stats_surface = self.font.render(stats_text, True, COLORS['WHITE'])
        self.screen.blit(stats_surface, (10, y_offset))
        y_offset += 25
        
        # Optimization info
        optimization_text = "✨ PERFECT CLIENT"
        opt_surface = self.big_font.render(optimization_text, True, COLORS['CYAN'])
        self.screen.blit(opt_surface, (10, y_offset))
        y_offset += 35
        
        smooth_info = "Fixed Window + Zero Jitter + Perfect Sync"
        smooth_surface = self.small_font.render(smooth_info, True, COLORS['CYAN'])
        self.screen.blit(smooth_surface, (10, y_offset))
        
        # Position info (debug)
        if self.player_id and self.player_id in self.players:
            pos = self.players[self.player_id].position
            pos_text = f"Position: ({pos['x']:.1f}, {pos['y']:.1f})"
            pos_surface = self.small_font.render(pos_text, True, COLORS['GRAY'])
            self.screen.blit(pos_surface, (10, y_offset + 25))
        
        # Control instructions
        controls = [
            "WASD: Move",
            "Mouse: Aim & Shoot",
            "ESC: Quit"
        ]
        
        for i, control in enumerate(controls):
            control_surface = self.small_font.render(control, True, COLORS['GRAY'])
            self.screen.blit(control_surface, (SCREEN_WIDTH - 150, 10 + i * 20))

    def render_in_game_ui(self):
        """Render in-game UI information"""
        y_offset = 10
        
        # Connection status
        status_text = "Connected" if self.connected else "Disconnected"
        status_color = COLORS['GREEN'] if self.connected else COLORS['RED']
        status_surface = self.font.render(f"Status: {status_text}", True, status_color)
        self.screen.blit(status_surface, (10, y_offset))
        y_offset += 25
        
        # Player info
        if self.player_id:
            player_text = f"Player: {self.player_name}"
            player_surface = self.font.render(player_text, True, COLORS['WHITE'])
            self.screen.blit(player_surface, (10, y_offset))
            y_offset += 25
        
        # Network latency
        ping_color = COLORS['GREEN'] if self.current_ping < 50 else COLORS['ORANGE'] if self.current_ping < 100 else COLORS['RED']
        ping_text = f"Ping: {self.current_ping}ms"
        ping_surface = self.font.render(ping_text, True, ping_color)
        self.screen.blit(ping_surface, (10, y_offset))
        y_offset += 25
        
        # FPS display
        fps_color = COLORS['GREEN'] if self.fps_counter >= 55 else COLORS['ORANGE'] if self.fps_counter >= 30 else COLORS['RED']
        fps_text = f"FPS: {self.fps_counter}"
        fps_surface = self.font.render(fps_text, True, fps_color)
        self.screen.blit(fps_surface, (10, y_offset))
        y_offset += 25
        
        # Game statistics
        stats_text = f"Players: {len(self.players)} | Bullets: {len(self.bullets)}"
        stats_surface = self.font.render(stats_text, True, COLORS['WHITE'])
        self.screen.blit(stats_surface, (10, y_offset))
        y_offset += 25
        
        # Position info (debug)
        if self.player_id and self.player_id in self.players:
            pos = self.players[self.player_id].position
            pos_text = f"Position: ({pos['x']:.1f}, {pos['y']:.1f})"
            pos_surface = self.small_font.render(pos_text, True, COLORS['GRAY'])
            self.screen.blit(pos_surface, (10, y_offset))
        
        # Control instructions
        controls = [
            "WASD: Move",
            "Mouse: Aim & Shoot",
            "ESC: Back to Room"
        ]
        
        for i, control in enumerate(controls):
            control_surface = self.small_font.render(control, True, COLORS['GRAY'])
            self.screen.blit(control_surface, (SCREEN_WIDTH - 150, 10 + i * 20))
    
    def render_game_world(self):
        """Render game world (tanks, bullets, etc.)"""
        # Render players
        for player_id, player in self.players.items():
            if not player.is_alive:
                continue
                
            pos = player.position  # Use single position source
            color = COLORS['GREEN'] if player_id == self.player_id else COLORS['BLUE']
            
            # Draw tank
            tank_rect = pygame.Rect(pos['x'] - 15, pos['y'] - 15, 30, 30)
            pygame.draw.rect(self.screen, color, tank_rect)
            
            # If local player, add special marker
            if player_id == self.player_id:
                pygame.draw.rect(self.screen, COLORS['ORANGE'], tank_rect, 3)
            
            # Draw player name
            name_text = self.small_font.render(player.name, True, COLORS['WHITE'])
            name_rect = name_text.get_rect(center=(pos['x'], pos['y'] - 25))
            self.screen.blit(name_text, name_rect)
            
            # Draw health bar
            if player.health < player.max_health:
                health_ratio = player.health / player.max_health
                health_width = 30
                health_height = 4
                
                # Background
                health_bg = pygame.Rect(pos['x'] - 15, pos['y'] - 35, health_width, health_height)
                pygame.draw.rect(self.screen, COLORS['RED'], health_bg)
                
                # Health
                health_fg = pygame.Rect(pos['x'] - 15, pos['y'] - 35, 
                                      health_width * health_ratio, health_height)
                pygame.draw.rect(self.screen, COLORS['GREEN'], health_fg)
        
        # Render bullets
        for bullet in self.bullets.values():
            pos = bullet.position
            pygame.draw.circle(self.screen, COLORS['YELLOW'], 
                             (int(pos['x']), int(pos['y'])), 4)
            # Bullet center point
            pygame.draw.circle(self.screen, COLORS['WHITE'], 
                             (int(pos['x']), int(pos['y'])), 2)

    def update_room_display(self, room_data: Dict[str, Any]):
        """Update room display (called by message handlers)"""
        room_lobby_state = self.state_manager.states.get(GameStateType.ROOM_LOBBY)
        if room_lobby_state and hasattr(room_lobby_state, 'update_room'):
            room_lobby_state.update_room(room_data)


async def game_loop(client: GameClient):
    """Perfect game main loop - now uses state machine"""
    last_ping_time = 0
    ping_interval = 2.0
    
    running = True
    
    print("✨ Perfect Game Loop Started with State Machine!")
    print("🎯 Starting at Main Menu")
    
    while running:
        current_time = time.time()
        dt = client.clock.get_time() / 1000.0  # Convert to seconds
        
        # Handle PyGame events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # ESC key handling delegated to state machine
                    if not client.state_manager.handle_event(event):
                        # If state machine didn't handle it, exit game
                        running = False
                else:
                    # Other key events delegated to state machine
                    client.state_manager.handle_event(event)
                    # If in game state, also handle traditional input
                    current_state = client.state_manager.get_current_state_type()
                    if current_state == GameStateType.IN_GAME:
                        client.handle_input(event)
            elif event.type == pygame.KEYUP:
                # Key release events
                client.state_manager.handle_event(event)
                current_state = client.state_manager.get_current_state_type()
                if current_state == GameStateType.IN_GAME:
                    client.handle_input(event)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                # Mouse click events
                client.state_manager.handle_event(event)
                current_state = client.state_manager.get_current_state_type()
                if current_state == GameStateType.IN_GAME:
                    client.handle_input(event)
            elif event.type == pygame.MOUSEMOTION:
                # Mouse movement events
                client.state_manager.handle_event(event)
                current_state = client.state_manager.get_current_state_type()
                if current_state == GameStateType.IN_GAME:
                    client.handle_input(event)
            else:
                # All other events delegated to state machine
                client.state_manager.handle_event(event)
        
        # Update state machine
        client.state_manager.update(dt)
        
        # Only handle network and game logic when in game state
        current_state = client.state_manager.get_current_state_type()
        if current_state == GameStateType.IN_GAME and client.connected:
            # Update local player (same algorithm as server)
            client.update_local_player(dt)
            
            # Send movement updates (smart send)
            await client.send_movement_if_changed()
            
            # Handle shooting
            if client.input_state['mouse_clicked']:
                await client.send_shoot()
            
            # Send ping
            if current_time - last_ping_time > ping_interval:
                await client.send_ping()
                last_ping_time = current_time
            
            # Update game objects
            client.update_game_objects(dt)
        
        # Render current state
        client.state_manager.render(client.screen)
        
        # Render additional UI info in game state
        if current_state == GameStateType.IN_GAME:
            client.render_in_game_ui()
        
        pygame.display.flip()
        client.clock.tick(FPS)
        
        # Update FPS count
        client.update_fps_counter()
        
        # Yield control to other coroutines
        await asyncio.sleep(0.001)
    
    # Disconnect
    await client.disconnect()
    pygame.quit()


def determine_server_url():
    """Determine server URL - parse command line arguments and intelligently choose server"""
    # Parse command line arguments
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
    
    # If user requests network scan
    if args.scan:
        display_connection_help()
        return None  # Indicates program should exit
    
    # Determine server URL
    if args.server:
        server_url = args.server
    elif args.host:
        port = args.port or SERVER_PORT
        server_url = f"ws://{args.host}:{port}"
    else:
        # Smart default connection: first scan network for servers
        print("🔍 No server specified, scanning for available servers...")
        available_servers = scan_local_servers()
        
        if available_servers:
            # Prioritize non-local servers
            remote_servers = [s for s in available_servers if s != DEFAULT_LOCAL_IP]
            if remote_servers:
                chosen_server = remote_servers[0]
                server_url = f"ws://{chosen_server}:{SERVER_PORT}"
                print(f"🎯 Auto-selected remote server: {chosen_server}")
            else:
                # Only local server available
                server_url = f"ws://{available_servers[0]}:{SERVER_PORT}"
                print(f"🏠 Auto-selected local server: {available_servers[0]}")
        else:
            # No servers found, use local IP as fallback
            server_url = DEFAULT_SERVER_URL
            print(f"⚠️ No servers found, trying local server: {DEFAULT_LOCAL_IP}")
            print("💡 If this fails, make sure server is running or use --host [SERVER_IP]")
    
    return server_url


def scan_local_servers(port: int = 8765) -> List[str]:
    """Scan game servers in local network"""
    local_ip = get_local_ip()
    if local_ip == "127.0.0.1":
        return []
    
    # Get network segment
    ip_parts = local_ip.split('.')
    network_base = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}"
    
    available_servers = []
    
    print(f"🔍 Scanning network {network_base}.x for game servers...")
    
    # Scan common IP ranges (simplified version, only scan some IPs)
    scan_ips = [
        f"{network_base}.1",    # Router
        f"{network_base}.100",  # Common server IP
        f"{network_base}.101", 
        f"{network_base}.102",
        f"{network_base}.110",
        f"{network_base}.200",
        local_ip,  # Local machine
    ]
    
    for ip in scan_ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.5)  # 500ms timeout
            result = s.connect_ex((ip, port))
            s.close()
            
            if result == 0:
                available_servers.append(ip)
                print(f"✅ Found server at {ip}:{port}")
        except Exception:
            pass
    
    return available_servers

def display_connection_help():
    """Display connection help information"""
    local_ip = get_local_ip()
    print("=" * 40)
    print(f"📍 Your machine IP: {local_ip}")

    
    servers = scan_local_servers()
    
    if servers:
        print(f"✅ Found {len(servers)} server(s):")
        for server_ip in servers:
            print(f"   • {server_ip}:8765")
        print("💻 Connection commands:")
        for server_ip in servers:
            if server_ip == local_ip:
                print(f"   • Local server:  python home/tank_game_client.py")
            else:
                print(f"   • Remote server: python home/tank_game_client.py --host {server_ip}")
    else:
        print("❌ No servers found on local network")

    
    print("=" * 40)



async def main():
    """Main function - now starts state machine instead of directly connecting to server"""
    print("✨ Starting Perfect Tank Game Client with State Machine...")
    print("=" * 50)
    print(f"  • Fixed window size ({SCREEN_WIDTH}x{SCREEN_HEIGHT})")
    print(f"  • State machine enabled")
    print("=" * 50)
    server_url = determine_server_url()
    if server_url:
        print(f"🔗 Connecting to server: {server_url}")
    else:
        print("❌ No server found, exiting...")
        return
    
    # Create client (but don't connect immediately)
    client = GameClient(server_url)
    
    try:
        # Start state machine game loop
        await game_loop(client)
    
    except KeyboardInterrupt:
        print("\n🛑 Client shutting down...")
    
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main()) 