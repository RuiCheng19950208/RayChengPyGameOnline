#!/usr/bin/env python3
"""
Specific game state implementations

Contains main menu, room lobby, server browser and in-game state implementations
"""

import pygame
import asyncio
import socket
import time
from typing import Dict, List, Optional, Any, Callable
from game_states import GameState, GameStateType
from ui_components import Button, PlayerSlot, Panel, TextLabel
from tank_game_entities import GameRoom, Player, MAX_PLAYERS_PER_ROOM
from tank_game_messages import *


class MainMenuState(GameState):
    """Main menu state"""
    
    def __init__(self, state_manager):
        super().__init__(state_manager)
        self.screen_width = 800
        self.screen_height = 600
        self.buttons = []
        self.title_font = None
        self.button_font = None
        
    def enter(self, previous_state=None, **kwargs):
        """Enter main menu"""
        if not self.initialized:
            self._initialize_ui()
            self.initialized = True
        print("🏠 Entered Main Menu")
    
    def exit(self, next_state=None):
        """Leave main menu"""
        pass
    
    def _initialize_ui(self):
        """Initialize UI components"""
        # Create fonts
        try:
            self.title_font = pygame.font.Font(None, 72)
            self.button_font = pygame.font.Font(None, 36)
        except:
            self.title_font = pygame.font.Font(None, 72)
            self.button_font = pygame.font.Font(None, 36)
        
        # Create buttons
        button_width = 250
        button_height = 60
        button_spacing = 20
        start_y = 350
        
        center_x = self.screen_width // 2 - button_width // 2
        
        # Create a Game button
        create_button = Button(
            center_x, start_y,
            button_width, button_height,
            "Create a Game",
            self.button_font,
            self._on_create_game
        )
        
        # Join a Game button
        join_button = Button(
            center_x, start_y + button_height + button_spacing,
            button_width, button_height,
            "Join a Game",
            self.button_font,
            self._on_join_game
        )
        
        # Exit button
        exit_button = Button(
            center_x, start_y + 2 * (button_height + button_spacing),
            button_width, button_height,
            "Exit",
            self.button_font,
            self._on_exit
        )
        
        self.buttons = [create_button, join_button, exit_button]
    
    def _on_create_game(self):
        """Create game"""
        print("🎮 Creating new game...")
        
        # Generate unique room ID
        import uuid
        room_id = f"room_{int(time.time())}_{str(uuid.uuid4())[:8]}"
        room_name = f"Game Room {int(time.time()) % 10000}"
        
        print(f"🏠 Creating room: {room_name} (ID: {room_id})")
        
        self.state_manager.change_state(
            GameStateType.ROOM_LOBBY,
            is_host=True,
            room_id=room_id,
            room_name=room_name
        )
    
    def _on_join_game(self):
        """Join game"""
        print("🔍 Looking for games...")
        self.state_manager.change_state(GameStateType.SERVER_BROWSER)
    
    def _on_exit(self):
        """Exit game"""
        print("👋 Exiting game...")
        pygame.event.post(pygame.event.Event(pygame.QUIT))
    
    def update(self, dt: float):
        """Update main menu"""
        pass
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle events"""
        for button in self.buttons:
            if button.handle_event(event):
                return True
        return False
    
    def render(self, surface: pygame.Surface):
        """Render main menu"""
        # Clear screen
        surface.fill((20, 20, 30))
        
        # Draw title
        title_text = self.title_font.render("TANK WARS", True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(self.screen_width // 2, 200))
        surface.blit(title_text, title_rect)
        
        # Draw subtitle
        subtitle_text = self.button_font.render("Multiplayer Tank Battle", True, (200, 200, 200))
        subtitle_rect = subtitle_text.get_rect(center=(self.screen_width // 2, 250))
        surface.blit(subtitle_text, subtitle_rect)
        
        # Draw buttons
        for button in self.buttons:
            button.draw(surface)


class ServerBrowserState(GameState):
    """Server browser state - now displays room list"""
    
    def __init__(self, state_manager):
        super().__init__(state_manager)
        self.screen_width = 800
        self.screen_height = 600
        self.rooms = []
        self.scanning = False
        self.room_buttons = []
        self.back_button = None
        self.refresh_button = None
        self.status_text = "Click Refresh to scan for rooms"
        
    def enter(self, previous_state=None, **kwargs):
        """Enter server browser"""
        if not self.initialized:
            self._initialize_ui()
            self.initialized = True
        
        # Auto-start scanning
        self._start_scan()
        print("🔍 Entered Room Browser")
    
    def exit(self, next_state=None):
        """Leave server browser"""
        pass
    
    def _initialize_ui(self):
        """Initialize UI"""
        try:
            self.font = pygame.font.Font(None, 24)
            self.title_font = pygame.font.Font(None, 36)
        except:
            self.font = pygame.font.Font(None, 24)
            self.title_font = pygame.font.Font(None, 36)
        
        # Back button
        self.back_button = Button(
            50, 50, 100, 40,
            "Back", self.font,
            self._on_back
        )
        
        # Refresh button
        self.refresh_button = Button(
            200, 50, 100, 40,
            "Refresh", self.font,
            self._start_scan
        )
    
    def _start_scan(self):
        """Start scanning for rooms"""
        if self.scanning:
            return
        
        self.scanning = True
        self.status_text = "Scanning for rooms..."
        self.rooms = []
        self.room_buttons = []
        
        # Async scan
        asyncio.create_task(self._scan_rooms())
    
    async def _scan_rooms(self):
        """Scan available rooms"""
        try:
            client = self.state_manager.client_ref
            if not client or not client.connected:
                self.status_text = "Not connected to server"
                self.scanning = False
                return
            
            # Request room list
            from tank_game_messages import RoomListRequestMessage
            list_request = RoomListRequestMessage(client_id=client.client_id)
            await client.send_message(list_request)
            
            # Wait for response
            await asyncio.sleep(1.0)  # Give server time to respond
            
            # Check if room list was received
            if hasattr(client, 'room_list') and client.room_list:
                self.rooms = client.room_list
                self._create_room_buttons()
                
                if self.rooms:
                    self.status_text = f"Found {len(self.rooms)} active room(s)"
                else:
                    self.status_text = "No active rooms found"
            else:
                self.status_text = "No rooms available"
        
        except Exception as e:
            print(f"❌ Room scan error: {e}")
            self.status_text = f"Scan error: {e}"
        
        finally:
            self.scanning = False
    
    def _create_room_buttons(self):
        """Create room buttons"""
        self.room_buttons = []
        start_y = 150
        button_height = 60
        button_spacing = 10
        
        for i, room in enumerate(self.rooms):
            y = start_y + i * (button_height + button_spacing)
            
            # Room info text
            room_text = f"🏠 {room['name']} (ID: {room['room_id']}) - {room['current_players']}/{room['max_players']} players"
            if room.get('room_state') == 'playing':
                room_text += " [IN GAME]"
            
            button = Button(
                100, y, 600, button_height,
                room_text, self.font,
                lambda r=room: self._join_room(r)
            )
            self.room_buttons.append(button)
    
    def _join_room(self, room_info):
        """Join room"""
        if room_info.get('room_state') == 'playing':
            print("⚠️ Cannot join room - game in progress")
            return
        
        print(f"🔗 Joining room {room_info['room_id']}: {room_info['name']}")
        
        self.state_manager.change_state(
            GameStateType.ROOM_LOBBY,
            is_host=False,
            room_id=room_info['room_id'],
            room_name=room_info['name']
        )
    
    def _on_back(self):
        """Return to main menu"""
        self.state_manager.change_state(GameStateType.MAIN_MENU)
    
    def update(self, dt: float):
        """Update server browser"""
        pass
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle events"""
        if self.back_button.handle_event(event):
            return True
        if self.refresh_button.handle_event(event):
            return True
        
        for button in self.room_buttons:
            if button.handle_event(event):
                return True
        
        return False
    
    def render(self, surface: pygame.Surface):
        """Render server browser"""
        surface.fill((25, 25, 35))
        
        # Title
        title_text = self.title_font.render("Available Rooms", True, (255, 255, 255))
        surface.blit(title_text, (50, 10))
        
        # Status text
        status_surface = self.font.render(self.status_text, True, (200, 200, 200))
        surface.blit(status_surface, (50, 110))
        
        # Buttons
        self.back_button.draw(surface)
        self.refresh_button.draw(surface)
        
        # Room list
        for button in self.room_buttons:
            button.draw(surface)
        
        # Scanning indicator
        if self.scanning:
            dots = "." * ((int(time.time() * 3) % 3) + 1)
            scan_text = self.font.render(f"Scanning{dots}", True, (100, 255, 100))
            surface.blit(scan_text, (320, 50))


class RoomLobbyState(GameState):
    """Room lobby state"""
    
    def __init__(self, state_manager):
        super().__init__(state_manager)
        self.screen_width = 800
        self.screen_height = 600
        self.is_host = False
        self.current_room: Optional[GameRoom] = None
        self.player_slots: List[PlayerSlot] = []
        self.buttons = []
        self.client = None  # Game client reference
        self.room_id = "default"
        self.room_name = "Game Room"
        
    def enter(self, previous_state=None, **kwargs):
        """Enter room lobby"""
        self.is_host = kwargs.get('is_host', False)
        self.room_id = kwargs.get('room_id', 'default')
        self.room_name = kwargs.get('room_name', 'Game Room')
        
        print(f"🏠 Entering Room Lobby (Host: {self.is_host}, Room: {self.room_id})")
        
        if not self.initialized:
            self._initialize_ui()
            self.initialized = True
        
        # Update button states
        self._update_button_states()
        
        # If client is already connected, handle room logic directly
        if self.client and self.client.connected:
            if self.is_host:
                # Host creates room
                print(f"🔗 Host creating room: {self.room_name}")
                asyncio.create_task(self._create_room())
            else:
                # Joiner joins existing room
                print(f"🔗 Joining existing room: {self.room_id}")
                asyncio.create_task(self._join_room())
        else:
            print("⚠️ No client connection available")
    
    def exit(self, next_state=None):
        """Leave room lobby"""
        pass
    
    def _initialize_ui(self):
        """Initialize UI"""
        try:
            self.font = pygame.font.Font(None, 24)
            self.title_font = pygame.font.Font(None, 36)
        except:
            self.font = pygame.font.Font(None, 24)
            self.title_font = pygame.font.Font(None, 36)
        
        # Create player slots
        self._create_player_slots()
        
        # Create buttons
        self._create_buttons()
    
    def _create_player_slots(self):
        """Create player slots"""
        self.player_slots = []
        
        slot_width = 180
        slot_height = 80
        slots_per_row = 4
        rows = 2
        
        start_x = (self.screen_width - slots_per_row * slot_width - (slots_per_row - 1) * 10) // 2
        start_y = 200
        
        for row in range(rows):
            for col in range(slots_per_row):
                slot_id = row * slots_per_row + col
                if slot_id >= MAX_PLAYERS_PER_ROOM:
                    break
                
                x = start_x + col * (slot_width + 10)
                y = start_y + row * (slot_height + 20)
                
                slot = PlayerSlot(
                    x, y, slot_width, slot_height,
                    slot_id, self.font,
                    self._on_slot_click
                )
                self.player_slots.append(slot)
    
    def _create_buttons(self):
        """Create buttons"""
        # Start Game button (only visible to host)
        self.start_button = Button(
            50, 500, 150, 50,
            "Start Game", self.font,
            self._on_start_game
        )
        
        # Quit Game button
        self.quit_button = Button(
            250, 500, 150, 50,
            "Quit Game", self.font,
            self._on_quit_game
        )
        
        self.buttons = [self.start_button, self.quit_button]
    
    def _update_button_states(self):
        """Update button states"""
        if hasattr(self, 'start_button'):
            self.start_button.set_enabled(self.is_host)
    
    def _on_slot_click(self, slot_id: int):
        """Player slot click"""
        print(f"🎯 Slot {slot_id + 1} clicked")
        
        if not self.client or not self.client.connected:
            print("⚠️ Not connected to server")
            return
        
        # Check if slot is available
        slot = self.player_slots[slot_id]
        if slot.is_occupied:
            print(f"⚠️ Slot {slot_id + 1} is already occupied")
            return
        
        # Send slot change request
        slot_change_request = SlotChangeRequestMessage(
            player_id=self.client.player_id,
            target_slot=slot_id,
            room_id=self.room_id  # Use current room ID
        )
        
        # Send message asynchronously
        asyncio.create_task(self._send_slot_change_request(slot_change_request))
    
    async def _send_slot_change_request(self, message: SlotChangeRequestMessage):
        """Send slot change request"""
        if self.client and self.client.connected:
            await self.client.send_message(message)
            print(f"📤 Requested to move to slot {message.target_slot + 1}")
    
    def _on_start_game(self):
        """Start game"""
        if not self.is_host:
            return
        
        print("🚀 Starting game...")
        
        # Send start game message to server
        if self.client and self.client.connected:
            start_game_message = RoomStartGameMessage(
                room_id=self.room_id,  # Use current room ID
                host_player_id=self.client.player_id
            )
            asyncio.create_task(self._send_start_game_message(start_game_message))
        
        # Switch to game state
        self.state_manager.change_state(GameStateType.IN_GAME)
    
    async def _send_start_game_message(self, message: RoomStartGameMessage):
        """Send start game message"""
        if self.client and self.client.connected:
            await self.client.send_message(message)
            print(f"📤 Sent start game message for room {message.room_id}")
    
    def _on_quit_game(self):
        """Quit game"""
        print("🚪 Quitting game...")
        
        if self.client and self.client.connected:
            if self.is_host:
                # Host quits, disband room
                print("🗑️ Host dissolving room...")
                from tank_game_messages import RoomDisbandedMessage
                disband_message = RoomDisbandedMessage(
                    room_id=self.room_id,
                    disbanded_by=self.client.player_id,
                    reason="host_quit"
                )
                asyncio.create_task(self.client.send_message(disband_message))
            else:
                # Regular player quits, send leave message
                print("👋 Leaving room...")
                from tank_game_messages import PlayerLeaveMessage
                leave_message = PlayerLeaveMessage(
                    player_id=self.client.player_id,
                    reason="quit"
                )
                asyncio.create_task(self.client.send_message(leave_message))
        
        self.state_manager.change_state(GameStateType.MAIN_MENU)
    
    def update_room(self, room_data: Dict[str, Any]):
        """Update room data"""
        # Update player slot display
        players = room_data.get('players', [])
        
        # Clear all slots
        for slot in self.player_slots:
            slot.set_player(None)
        
        # Set player data based on player's slot_index
        for player_data in players:
            slot_index = player_data.get('slot_index', 0)
            if 0 <= slot_index < len(self.player_slots):
                # Determine if local player
                is_local = (self.client and 
                           player_data.get('player_id') == self.client.player_id)
                self.player_slots[slot_index].set_player(player_data, is_local)
    
    def set_client(self, client):
        """Set client reference"""
        self.client = client
        # If there's already room data, re-update display
        if hasattr(self, 'current_room') and self.current_room:
            self.update_room(self.current_room.to_dict())
    
    async def _create_room(self):
        """Create room"""
        if not self.client or not self.client.connected:
            return
        
        try:
            # Send create room request
            create_room_message = CreateRoomRequestMessage(
                room_name=self.room_name,
                max_players=8,
                creator_id=self.client.player_id,
                game_mode="classic"
            )
            await self.client.send_message(create_room_message)
            print(f"📤 Sent room creation request for {self.room_name}")
        except Exception as e:
            print(f"❌ Failed to create room: {e}")
            # Creation failed, return to main menu
            self.state_manager.change_state(GameStateType.MAIN_MENU)
    
    async def _join_room(self):
        """Join existing room"""
        if not self.client or not self.client.connected:
            return
        
        try:
            # Send join room message
            join_message = PlayerJoinMessage(
                player_id=self.client.player_id,
                player_name=self.client.player_name,
                room_id=self.room_id
            )
            await self.client.send_message(join_message)
            print(f"📤 Sent join message for room {self.room_id}")
        except Exception as e:
            print(f"❌ Failed to join room: {e}")
            # Join failed, return to server browser
            self.state_manager.change_state(GameStateType.SERVER_BROWSER)
    
    def update(self, dt: float):
        """Update room lobby"""
        pass
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle events"""
        # Handle slot clicks
        for slot in self.player_slots:
            if slot.handle_event(event):
                return True
        
        # Handle button clicks
        for button in self.buttons:
            if button.handle_event(event):
                return True
        
        return False
    
    def render(self, surface: pygame.Surface):
        """Render room lobby"""
        surface.fill((30, 30, 40))
        
        # Title
        title_text = self.title_font.render("Game Room", True, (255, 255, 255))
        surface.blit(title_text, (50, 50))
        
        # Host indicator
        if self.is_host:
            host_text = self.font.render("You are the host", True, (100, 255, 100))
            surface.blit(host_text, (50, 90))
        
        # Room information
        player_count = sum(1 for slot in self.player_slots if slot.is_occupied)
        info_text = self.font.render(f"Players: {player_count}/{MAX_PLAYERS_PER_ROOM} - Click empty slots to join", True, (200, 200, 200))
        surface.blit(info_text, (50, 120))
        
        # Connection status
        if self.client:
            if self.client.connected:
                status_text = self.font.render("Connected to server", True, (100, 255, 100))
            else:
                status_text = self.font.render("Not connected", True, (255, 100, 100))
            surface.blit(status_text, (50, 150))
        
        # Player slots
        for slot in self.player_slots:
            slot.draw(surface)
        
        # Buttons
        for button in self.buttons:
            button.draw(surface)


class InGameState(GameState):
    """In-game state"""
    
    def __init__(self, state_manager):
        super().__init__(state_manager)
        self.client = None  # Game client reference
        
    def enter(self, previous_state=None, **kwargs):
        """Enter game"""
        print("🎮 Entered In-Game State")
        
        # Reset game result state
        if self.client:
            self.client.game_result = None
            self.client.game_result_data = None
        
        # Clear residual data from previous game state
        if self.client:
            # Keep player data, only clear bullets
            self.client.bullets.clear()
            print("🧹 Cleared bullets from previous game state")
    
    def exit(self, next_state=None):
        """Leave game"""
        print("🚪 Exiting game state")
    
    def update(self, dt: float):
        """Update game"""
        # Game logic updates are handled in the main loop
        pass
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle game events"""
        # Check if game has ended (victory/defeat)
        if self.client and (self.client.game_result == "victory" or self.client.game_result == "defeat"):
            # Any key pressed - exit to main menu
            if event.type == pygame.KEYDOWN:
                print("🚪 Game ended, returning to main menu...")
                
                # Reset game result state
                self.client.game_result = None
                self.client.game_result_data = None
                
                # Send leave room message
                if self.client.connected:
                    leave_message = PlayerLeaveMessage(
                        player_id=self.client.player_id,
                        reason="game_ended"
                    )
                    asyncio.create_task(self.client.send_message(leave_message))
                
                # Clear game state
                if self.client:
                    self.client.bullets.clear()
                    self.client.players.clear()
                
                # Return to main menu
                self.state_manager.change_state(GameStateType.MAIN_MENU)
                return True
            return True  # Consume all events when game has ended
        
        # Normal game event handling
        # ESC key returns to main menu
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                print("🚪 ESC pressed in game, returning to main menu...")
                
                # Send leave room message
                if self.client and self.client.connected:
                    # Send player leave message
                    leave_message = PlayerLeaveMessage(
                        player_id=self.client.player_id,
                        reason="exit_game"
                    )
                    asyncio.create_task(self.client.send_message(leave_message))
                
                # Clear game state
                if self.client:
                    self.client.bullets.clear()
                    self.client.players.clear()
                
                # Return to main menu
                self.state_manager.change_state(GameStateType.MAIN_MENU)
                return True
        
        # Other game events are handled in the main loop
        return False
    
    def render(self, surface: pygame.Surface):
        """Render game"""
        if not self.client:
            # If no client, display error message
            surface.fill((50, 0, 0))
            font = pygame.font.Font(None, 36)
            text = font.render("Game Client Not Available", True, (255, 255, 255))
            text_rect = text.get_rect(center=(400, 300))
            surface.blit(text, text_rect)
            return
        
        # Clear screen
        surface.fill((0, 0, 0))  # Black background
        
        if self.client.connected and self.client.players:
            # Render game world
            self.client.render_game_world()
        else:
            # Display connection status
            font = pygame.font.Font(None, 36)
            if not self.client.connected:
                text = font.render("Not connected to server", True, (255, 255, 100))
            else:
                text = font.render("Waiting for players...", True, (255, 255, 100))
            
            text_rect = text.get_rect(center=(400, 300))
            surface.blit(text, text_rect)
            
            # Display return hint
            small_font = pygame.font.Font(None, 24)
            hint_text = small_font.render("Press ESC to return to main menu", True, (200, 200, 200))
            hint_rect = hint_text.get_rect(center=(400, 350))
            surface.blit(hint_text, hint_rect)
        
        # Render victory/defeat banners if game has ended
        if self.client.game_result == "victory":
            self._render_victory_banner(surface)
        elif self.client.game_result == "defeat":
            self._render_defeat_banner(surface)
    
    def _render_victory_banner(self, surface: pygame.Surface):
        """Render victory banner"""
        # Semi-transparent overlay
        overlay = pygame.Surface((800, 600))
        overlay.set_alpha(180)
        overlay.fill((0, 50, 0))  # Dark green overlay
        surface.blit(overlay, (0, 0))
        
        # Victory text
        big_font = pygame.font.Font(None, 72)
        victory_text = big_font.render("YOU WIN!", True, (0, 255, 0))
        victory_rect = victory_text.get_rect(center=(400, 250))
        surface.blit(victory_text, victory_rect)
        
        # Game details
        if self.client.game_result_data:
            data = self.client.game_result_data
            medium_font = pygame.font.Font(None, 36)
            
            duration_text = medium_font.render(f"Game Duration: {data.game_duration:.1f}s", True, (200, 255, 200))
            duration_rect = duration_text.get_rect(center=(400, 320))
            surface.blit(duration_text, duration_rect)
            
            players_text = medium_font.render(f"Total Players: {data.total_players}", True, (200, 255, 200))
            players_rect = players_text.get_rect(center=(400, 360))
            surface.blit(players_text, players_rect)
        
        # Exit instruction
        small_font = pygame.font.Font(None, 24)
        exit_text = small_font.render("Press any key to return to main menu", True, (255, 255, 255))
        exit_rect = exit_text.get_rect(center=(400, 450))
        surface.blit(exit_text, exit_rect)
    
    def _render_defeat_banner(self, surface: pygame.Surface):
        """Render defeat banner"""
        # Semi-transparent overlay
        overlay = pygame.Surface((800, 600))
        overlay.set_alpha(180)
        overlay.fill((50, 0, 0))  # Dark red overlay
        surface.blit(overlay, (0, 0))
        
        # Defeat text
        big_font = pygame.font.Font(None, 72)
        defeat_text = big_font.render("YOU LOSE", True, (255, 0, 0))
        defeat_rect = defeat_text.get_rect(center=(400, 250))
        surface.blit(defeat_text, defeat_rect)
        
        # Game details
        if self.client.game_result_data:
            data = self.client.game_result_data
            medium_font = pygame.font.Font(None, 36)
            
            killer_text = medium_font.render(f"Eliminated by: {data.killer_name}", True, (255, 200, 200))
            killer_rect = killer_text.get_rect(center=(400, 320))
            surface.blit(killer_text, killer_rect)
            
            survival_text = medium_font.render(f"Survival Time: {data.survival_time:.1f}s", True, (255, 200, 200))
            survival_rect = survival_text.get_rect(center=(400, 360))
            surface.blit(survival_text, survival_rect)
        
        # Exit instruction
        small_font = pygame.font.Font(None, 24)
        exit_text = small_font.render("Press any key to return to main menu", True, (255, 255, 255))
        exit_rect = exit_text.get_rect(center=(400, 450))
        surface.blit(exit_text, exit_rect) 