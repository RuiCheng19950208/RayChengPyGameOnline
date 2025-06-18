#!/usr/bin/env python3
"""
游戏状态机系统

管理游戏的不同状态：主菜单、房间大厅、游戏中等
"""

from enum import Enum
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import pygame


class GameStateType(Enum):
    """游戏状态类型"""
    MAIN_MENU = "main_menu"
    ROOM_LOBBY = "room_lobby"
    IN_GAME = "in_game"
    SETTINGS = "settings"
    SERVER_BROWSER = "server_browser"


class GameState(ABC):
    """游戏状态基类"""
    
    def __init__(self, state_manager):
        self.state_manager = state_manager
        self.initialized = False
    
    @abstractmethod
    def enter(self, previous_state: Optional['GameState'] = None, **kwargs):
        """进入状态时调用"""
        pass
    
    @abstractmethod
    def exit(self, next_state: Optional['GameState'] = None):
        """离开状态时调用"""
        pass
    
    @abstractmethod
    def update(self, dt: float):
        """更新状态逻辑"""
        pass
    
    @abstractmethod
    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理事件，返回是否消费了该事件"""
        pass
    
    @abstractmethod
    def render(self, surface: pygame.Surface):
        """渲染状态"""
        pass


class GameStateManager:
    """游戏状态管理器"""
    
    def __init__(self):
        self.states: Dict[GameStateType, GameState] = {}
        self.current_state: Optional[GameState] = None
        self.state_stack = []  # 用于支持状态栈（如暂停菜单）
        self.transition_data: Dict[str, Any] = {}
    
    def register_state(self, state_type: GameStateType, state: GameState):
        """注册状态"""
        self.states[state_type] = state
    
    def change_state(self, state_type: GameStateType, **kwargs):
        """切换到指定状态"""
        if state_type not in self.states:
            print(f"❌ State {state_type} not registered")
            return
        
        new_state = self.states[state_type]
        previous_state = self.current_state
        
        # 退出当前状态
        if self.current_state:
            self.current_state.exit(new_state)
        
        # 进入新状态
        self.current_state = new_state
        self.current_state.enter(previous_state, **kwargs)
        
        print(f"🔄 State changed to: {state_type.value}")
    
    def push_state(self, state_type: GameStateType, **kwargs):
        """推入新状态到栈顶（如弹出菜单）"""
        if self.current_state:
            self.state_stack.append(self.current_state)
        
        self.change_state(state_type, **kwargs)
    
    def pop_state(self):
        """弹出当前状态，返回到栈中前一个状态"""
        if not self.state_stack:
            print("⚠️ No states to pop")
            return
        
        previous_state = self.state_stack.pop()
        if self.current_state:
            self.current_state.exit(previous_state)
        
        self.current_state = previous_state
        print(f"🔄 State popped, returned to previous state")
    
    def update(self, dt: float):
        """更新当前状态"""
        if self.current_state:
            self.current_state.update(dt)
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理事件"""
        if self.current_state:
            return self.current_state.handle_event(event)
        return False
    
    def render(self, surface: pygame.Surface):
        """渲染当前状态"""
        if self.current_state:
            self.current_state.render(surface)
    
    def get_current_state_type(self) -> Optional[GameStateType]:
        """获取当前状态类型"""
        for state_type, state in self.states.items():
            if state == self.current_state:
                return state_type
        return None
    
    def set_transition_data(self, **kwargs):
        """设置状态转换数据"""
        self.transition_data.update(kwargs)
    
    def get_transition_data(self, key: str, default=None):
        """获取状态转换数据"""
        return self.transition_data.get(key, default)
    
    def clear_transition_data(self):
        """清除状态转换数据"""
        self.transition_data.clear() 