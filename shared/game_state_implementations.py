#!/usr/bin/env python3
"""
具体游戏状态实现

包含主菜单、房间大厅、服务器浏览器和游戏中的状态实现
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
    """主菜单状态"""
    
    def __init__(self, state_manager):
        super().__init__(state_manager)
        self.screen_width = 800
        self.screen_height = 600
        self.buttons = []
        self.title_font = None
        self.button_font = None
        
    def enter(self, previous_state=None, **kwargs):
        """进入主菜单"""
        if not self.initialized:
            self._initialize_ui()
            self.initialized = True
        print("🏠 Entered Main Menu")
    
    def exit(self, next_state=None):
        """离开主菜单"""
        pass
    
    def _initialize_ui(self):
        """初始化UI组件"""
        # 创建字体
        try:
            self.title_font = pygame.font.Font(None, 72)
            self.button_font = pygame.font.Font(None, 36)
        except:
            self.title_font = pygame.font.Font(None, 72)
            self.button_font = pygame.font.Font(None, 36)
        
        # 创建按钮
        button_width = 250
        button_height = 60
        button_spacing = 20
        start_y = 350
        
        center_x = self.screen_width // 2 - button_width // 2
        
        # Create a Game 按钮
        create_button = Button(
            center_x, start_y,
            button_width, button_height,
            "Create a Game",
            self.button_font,
            self._on_create_game
        )
        
        # Join a Game 按钮
        join_button = Button(
            center_x, start_y + button_height + button_spacing,
            button_width, button_height,
            "Join a Game",
            self.button_font,
            self._on_join_game
        )
        
        # Exit 按钮
        exit_button = Button(
            center_x, start_y + 2 * (button_height + button_spacing),
            button_width, button_height,
            "Exit",
            self.button_font,
            self._on_exit
        )
        
        self.buttons = [create_button, join_button, exit_button]
    
    def _on_create_game(self):
        """创建游戏"""
        print("🎮 Creating new game...")
        
        # 生成唯一的房间ID
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
        """加入游戏"""
        print("🔍 Looking for games...")
        self.state_manager.change_state(GameStateType.SERVER_BROWSER)
    
    def _on_exit(self):
        """退出游戏"""
        print("👋 Exiting game...")
        pygame.event.post(pygame.event.Event(pygame.QUIT))
    
    def update(self, dt: float):
        """更新主菜单"""
        pass
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理事件"""
        for button in self.buttons:
            if button.handle_event(event):
                return True
        return False
    
    def render(self, surface: pygame.Surface):
        """渲染主菜单"""
        # 清屏
        surface.fill((20, 20, 30))
        
        # 绘制标题
        title_text = self.title_font.render("TANK WARS", True, (255, 255, 255))
        title_rect = title_text.get_rect(center=(self.screen_width // 2, 200))
        surface.blit(title_text, title_rect)
        
        # 绘制副标题
        subtitle_text = self.button_font.render("Multiplayer Tank Battle", True, (200, 200, 200))
        subtitle_rect = subtitle_text.get_rect(center=(self.screen_width // 2, 250))
        surface.blit(subtitle_text, subtitle_rect)
        
        # 绘制按钮
        for button in self.buttons:
            button.draw(surface)


class ServerBrowserState(GameState):
    """服务器浏览器状态 - 现在显示房间列表"""
    
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
        """进入服务器浏览器"""
        if not self.initialized:
            self._initialize_ui()
            self.initialized = True
        
        # 自动开始扫描
        self._start_scan()
        print("🔍 Entered Room Browser")
    
    def exit(self, next_state=None):
        """离开服务器浏览器"""
        pass
    
    def _initialize_ui(self):
        """初始化UI"""
        try:
            self.font = pygame.font.Font(None, 24)
            self.title_font = pygame.font.Font(None, 36)
        except:
            self.font = pygame.font.Font(None, 24)
            self.title_font = pygame.font.Font(None, 36)
        
        # Back 按钮
        self.back_button = Button(
            50, 50, 100, 40,
            "Back", self.font,
            self._on_back
        )
        
        # Refresh 按钮
        self.refresh_button = Button(
            200, 50, 100, 40,
            "Refresh", self.font,
            self._start_scan
        )
    
    def _start_scan(self):
        """开始扫描房间"""
        if self.scanning:
            return
        
        self.scanning = True
        self.status_text = "Scanning for rooms..."
        self.rooms = []
        self.room_buttons = []
        
        # 异步扫描
        asyncio.create_task(self._scan_rooms())
    
    async def _scan_rooms(self):
        """扫描可用房间"""
        try:
            client = self.state_manager.client_ref
            if not client or not client.connected:
                self.status_text = "Not connected to server"
                self.scanning = False
                return
            
            # 请求房间列表
            from tank_game_messages import RoomListRequestMessage
            list_request = RoomListRequestMessage(client_id=client.client_id)
            await client.send_message(list_request)
            
            # 等待响应
            await asyncio.sleep(1.0)  # 给服务器时间响应
            
            # 检查是否收到房间列表
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
        """创建房间按钮"""
        self.room_buttons = []
        start_y = 150
        button_height = 60
        button_spacing = 10
        
        for i, room in enumerate(self.rooms):
            y = start_y + i * (button_height + button_spacing)
            
            # 房间信息文本
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
        """加入房间"""
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
        """返回主菜单"""
        self.state_manager.change_state(GameStateType.MAIN_MENU)
    
    def update(self, dt: float):
        """更新服务器浏览器"""
        pass
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理事件"""
        if self.back_button.handle_event(event):
            return True
        if self.refresh_button.handle_event(event):
            return True
        
        for button in self.room_buttons:
            if button.handle_event(event):
                return True
        
        return False
    
    def render(self, surface: pygame.Surface):
        """渲染服务器浏览器"""
        surface.fill((25, 25, 35))
        
        # 标题
        title_text = self.title_font.render("Available Rooms", True, (255, 255, 255))
        surface.blit(title_text, (50, 10))
        
        # 状态文本
        status_surface = self.font.render(self.status_text, True, (200, 200, 200))
        surface.blit(status_surface, (50, 110))
        
        # 按钮
        self.back_button.draw(surface)
        self.refresh_button.draw(surface)
        
        # 房间列表
        for button in self.room_buttons:
            button.draw(surface)
        
        # 扫描指示器
        if self.scanning:
            dots = "." * ((int(time.time() * 3) % 3) + 1)
            scan_text = self.font.render(f"Scanning{dots}", True, (100, 255, 100))
            surface.blit(scan_text, (320, 50))


class RoomLobbyState(GameState):
    """房间大厅状态"""
    
    def __init__(self, state_manager):
        super().__init__(state_manager)
        self.screen_width = 800
        self.screen_height = 600
        self.is_host = False
        self.current_room: Optional[GameRoom] = None
        self.player_slots: List[PlayerSlot] = []
        self.buttons = []
        self.client = None  # 游戏客户端引用
        self.room_id = "default"
        self.room_name = "Game Room"
        
    def enter(self, previous_state=None, **kwargs):
        """进入房间大厅"""
        self.is_host = kwargs.get('is_host', False)
        self.room_id = kwargs.get('room_id', 'default')
        self.room_name = kwargs.get('room_name', 'Game Room')
        
        print(f"🏠 Entering Room Lobby (Host: {self.is_host}, Room: {self.room_id})")
        
        if not self.initialized:
            self._initialize_ui()
            self.initialized = True
        
        # 更新按钮状态
        self._update_button_states()
        
        # 如果客户端已连接，直接处理房间逻辑
        if self.client and self.client.connected:
            if self.is_host:
                # 房主创建房间
                print(f"🔗 Host creating room: {self.room_name}")
                asyncio.create_task(self._create_room())
            else:
                # 加入者加入现有房间
                print(f"🔗 Joining existing room: {self.room_id}")
                asyncio.create_task(self._join_room())
        else:
            print("⚠️ No client connection available")
    
    def exit(self, next_state=None):
        """离开房间大厅"""
        pass
    
    def _initialize_ui(self):
        """初始化UI"""
        try:
            self.font = pygame.font.Font(None, 24)
            self.title_font = pygame.font.Font(None, 36)
        except:
            self.font = pygame.font.Font(None, 24)
            self.title_font = pygame.font.Font(None, 36)
        
        # 创建玩家槽位
        self._create_player_slots()
        
        # 创建按钮
        self._create_buttons()
    
    def _create_player_slots(self):
        """创建玩家槽位"""
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
        """创建按钮"""
        # Start Game 按钮 (仅房主可见)
        self.start_button = Button(
            50, 500, 150, 50,
            "Start Game", self.font,
            self._on_start_game
        )
        
        # Quit Game 按钮
        self.quit_button = Button(
            250, 500, 150, 50,
            "Quit Game", self.font,
            self._on_quit_game
        )
        
        self.buttons = [self.start_button, self.quit_button]
    
    def _update_button_states(self):
        """更新按钮状态"""
        if hasattr(self, 'start_button'):
            self.start_button.set_enabled(self.is_host)
    
    def _on_slot_click(self, slot_id: int):
        """玩家槽位点击"""
        print(f"🎯 Slot {slot_id + 1} clicked")
        
        if not self.client or not self.client.connected:
            print("⚠️ Not connected to server")
            return
        
        # 检查槽位是否可用
        slot = self.player_slots[slot_id]
        if slot.is_occupied:
            print(f"⚠️ Slot {slot_id + 1} is already occupied")
            return
        
        # 发送槽位切换请求
        slot_change_request = SlotChangeRequestMessage(
            player_id=self.client.player_id,
            target_slot=slot_id,
            room_id=self.room_id  # 使用当前房间ID
        )
        
        # 异步发送消息
        asyncio.create_task(self._send_slot_change_request(slot_change_request))
    
    async def _send_slot_change_request(self, message: SlotChangeRequestMessage):
        """发送槽位切换请求"""
        if self.client and self.client.connected:
            await self.client.send_message(message)
            print(f"📤 Requested to move to slot {message.target_slot + 1}")
    
    def _on_start_game(self):
        """开始游戏"""
        if not self.is_host:
            return
        
        print("🚀 Starting game...")
        
        # 发送开始游戏消息给服务器
        if self.client and self.client.connected:
            start_game_message = RoomStartGameMessage(
                room_id=self.room_id,  # 使用当前房间ID
                host_player_id=self.client.player_id
            )
            asyncio.create_task(self._send_start_game_message(start_game_message))
        
        # 切换到游戏状态
        self.state_manager.change_state(GameStateType.IN_GAME)
    
    async def _send_start_game_message(self, message: RoomStartGameMessage):
        """发送开始游戏消息"""
        if self.client and self.client.connected:
            await self.client.send_message(message)
            print(f"📤 Sent start game message for room {message.room_id}")
    
    def _on_quit_game(self):
        """退出游戏"""
        print("🚪 Quitting game...")
        
        if self.client and self.client.connected:
            if self.is_host:
                # 房主退出，解散房间
                print("🗑️ Host dissolving room...")
                from tank_game_messages import RoomDisbandedMessage
                disband_message = RoomDisbandedMessage(
                    room_id=self.room_id,
                    disbanded_by=self.client.player_id,
                    reason="host_quit"
                )
                asyncio.create_task(self.client.send_message(disband_message))
            else:
                # 普通玩家退出，发送离开消息
                print("👋 Leaving room...")
                from tank_game_messages import PlayerLeaveMessage
                leave_message = PlayerLeaveMessage(
                    player_id=self.client.player_id,
                    reason="quit"
                )
                asyncio.create_task(self.client.send_message(leave_message))
        
        self.state_manager.change_state(GameStateType.MAIN_MENU)
    
    def update_room(self, room_data: Dict[str, Any]):
        """更新房间数据"""
        # 更新玩家槽位显示
        players = room_data.get('players', [])
        
        # 清空所有槽位
        for slot in self.player_slots:
            slot.set_player(None)
        
        # 根据玩家的slot_index设置玩家数据
        for player_data in players:
            slot_index = player_data.get('slot_index', 0)
            if 0 <= slot_index < len(self.player_slots):
                # 判断是否为本地玩家
                is_local = (self.client and 
                           player_data.get('player_id') == self.client.player_id)
                self.player_slots[slot_index].set_player(player_data, is_local)
    
    def set_client(self, client):
        """设置客户端引用"""
        self.client = client
        # 如果已经有房间数据，重新更新显示
        if hasattr(self, 'current_room') and self.current_room:
            self.update_room(self.current_room.to_dict())
    
    async def _create_room(self):
        """创建房间"""
        if not self.client or not self.client.connected:
            return
        
        try:
            # 发送创建房间请求
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
            # 创建失败，返回主菜单
            self.state_manager.change_state(GameStateType.MAIN_MENU)
    
    async def _join_room(self):
        """加入现有房间"""
        if not self.client or not self.client.connected:
            return
        
        try:
            # 发送加入房间消息
            join_message = PlayerJoinMessage(
                player_id=self.client.player_id,
                player_name=self.client.player_name,
                room_id=self.room_id
            )
            await self.client.send_message(join_message)
            print(f"📤 Sent join message for room {self.room_id}")
        except Exception as e:
            print(f"❌ Failed to join room: {e}")
            # 加入失败，返回服务器浏览器
            self.state_manager.change_state(GameStateType.SERVER_BROWSER)
    
    def update(self, dt: float):
        """更新房间大厅"""
        pass
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理事件"""
        # 处理槽位点击
        for slot in self.player_slots:
            if slot.handle_event(event):
                return True
        
        # 处理按钮点击
        for button in self.buttons:
            if button.handle_event(event):
                return True
        
        return False
    
    def render(self, surface: pygame.Surface):
        """渲染房间大厅"""
        surface.fill((30, 30, 40))
        
        # 标题
        title_text = self.title_font.render("Game Room", True, (255, 255, 255))
        surface.blit(title_text, (50, 50))
        
        # 房主标识
        if self.is_host:
            host_text = self.font.render("You are the host", True, (100, 255, 100))
            surface.blit(host_text, (50, 90))
        
        # 房间信息
        player_count = sum(1 for slot in self.player_slots if slot.is_occupied)
        info_text = self.font.render(f"Players: {player_count}/{MAX_PLAYERS_PER_ROOM} - Click empty slots to join", True, (200, 200, 200))
        surface.blit(info_text, (50, 120))
        
        # 连接状态
        if self.client:
            if self.client.connected:
                status_text = self.font.render("Connected to server", True, (100, 255, 100))
            else:
                status_text = self.font.render("Not connected", True, (255, 100, 100))
            surface.blit(status_text, (50, 150))
        
        # 玩家槽位
        for slot in self.player_slots:
            slot.draw(surface)
        
        # 按钮
        for button in self.buttons:
            button.draw(surface)


class InGameState(GameState):
    """游戏中状态"""
    
    def __init__(self, state_manager):
        super().__init__(state_manager)
        self.client = None  # 游戏客户端引用
        
    def enter(self, previous_state=None, **kwargs):
        """进入游戏"""
        print("🎮 Entered In-Game State")
        
        # 清理之前游戏状态的残留数据
        if self.client:
            # 保留玩家数据，只清理子弹
            self.client.bullets.clear()
            print("🧹 Cleared bullets from previous game state")
        
    def exit(self, next_state=None):
        """离开游戏"""
        print("🚪 Exiting game state")
    
    def update(self, dt: float):
        """更新游戏"""
        # 游戏逻辑更新在主循环中处理
        pass
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理游戏事件"""
        # ESC 键返回主菜单
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                print("🚪 ESC pressed in game, returning to main menu...")
                
                # 发送离开房间消息
                if self.client and self.client.connected:
                    # 发送玩家离开消息
                    leave_message = PlayerLeaveMessage(
                        player_id=self.client.player_id,
                        reason="exit_game"
                    )
                    asyncio.create_task(self.client.send_message(leave_message))
                
                # 清理游戏状态
                if self.client:
                    self.client.bullets.clear()
                    self.client.players.clear()
                
                # 返回主菜单
                self.state_manager.change_state(GameStateType.MAIN_MENU)
                return True
        
        # 其他游戏事件在主循环中处理
        return False
    
    def render(self, surface: pygame.Surface):
        """渲染游戏"""
        if not self.client:
            # 如果没有客户端，显示错误信息
            surface.fill((50, 0, 0))
            font = pygame.font.Font(None, 36)
            text = font.render("Game Client Not Available", True, (255, 255, 255))
            text_rect = text.get_rect(center=(400, 300))
            surface.blit(text, text_rect)
            return
        
        # 清屏
        surface.fill((0, 0, 0))  # 黑色背景
        
        if self.client.connected and self.client.players:
            # 渲染游戏世界
            self.client.render_game_world()
        else:
            # 显示连接状态
            font = pygame.font.Font(None, 36)
            if not self.client.connected:
                text = font.render("Not connected to server", True, (255, 255, 100))
            else:
                text = font.render("Waiting for players...", True, (255, 255, 100))
            
            text_rect = text.get_rect(center=(400, 300))
            surface.blit(text, text_rect)
            
            # 显示返回提示
            small_font = pygame.font.Font(None, 24)
            hint_text = small_font.render("Press ESC to return to main menu", True, (200, 200, 200))
            hint_rect = hint_text.get_rect(center=(400, 350))
            surface.blit(hint_text, hint_rect) 