#!/usr/bin/env python3
"""
UI 组件库

包含按钮、面板等 UI 组件，供游戏客户端使用
"""

import pygame
from typing import Tuple, Callable, Optional, Dict, Any
from enum import Enum


class ButtonState(Enum):
    """按钮状态"""
    NORMAL = "normal"
    HOVER = "hover"
    PRESSED = "pressed"
    DISABLED = "disabled"


class Button:
    """游戏按钮类"""
    
    def __init__(self, x: int, y: int, width: int, height: int, text: str, 
                 font: pygame.font.Font, on_click: Optional[Callable] = None):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.font = font
        self.on_click = on_click
        self.state = ButtonState.NORMAL
        self.enabled = True
        
        # 颜色配置
        self.colors = {
            ButtonState.NORMAL: {
                'bg': (70, 70, 70),
                'border': (100, 100, 100),
                'text': (255, 255, 255)
            },
            ButtonState.HOVER: {
                'bg': (90, 90, 90),
                'border': (150, 150, 150),
                'text': (255, 255, 255)
            },
            ButtonState.PRESSED: {
                'bg': (50, 50, 50),
                'border': (80, 80, 80),
                'text': (200, 200, 200)
            },
            ButtonState.DISABLED: {
                'bg': (40, 40, 40),
                'border': (60, 60, 60),
                'text': (100, 100, 100)
            }
        }
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理事件，返回是否被点击"""
        if not self.enabled:
            self.state = ButtonState.DISABLED
            return False
        
        mouse_pos = pygame.mouse.get_pos()
        
        if event.type == pygame.MOUSEMOTION:
            if self.rect.collidepoint(mouse_pos):
                if self.state != ButtonState.PRESSED:
                    self.state = ButtonState.HOVER
            else:
                self.state = ButtonState.NORMAL
        
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1 and self.rect.collidepoint(mouse_pos):
                self.state = ButtonState.PRESSED
                return False
        
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.rect.collidepoint(mouse_pos):
                if self.state == ButtonState.PRESSED:
                    self.state = ButtonState.HOVER
                    if self.on_click:
                        self.on_click()
                    return True
            else:
                if self.rect.collidepoint(mouse_pos):
                    self.state = ButtonState.HOVER
                else:
                    self.state = ButtonState.NORMAL
        
        return False
    
    def draw(self, surface: pygame.Surface):
        """绘制按钮"""
        colors = self.colors[self.state]
        
        # 绘制背景
        pygame.draw.rect(surface, colors['bg'], self.rect)
        
        # 绘制边框
        pygame.draw.rect(surface, colors['border'], self.rect, 2)
        
        # 绘制文本
        text_surface = self.font.render(self.text, True, colors['text'])
        text_rect = text_surface.get_rect(center=self.rect.center)
        surface.blit(text_surface, text_rect)
    
    def set_enabled(self, enabled: bool):
        """设置按钮是否可用"""
        self.enabled = enabled
        if not enabled:
            self.state = ButtonState.DISABLED


class PlayerSlot:
    """玩家位置槽组件"""
    
    def __init__(self, x: int, y: int, width: int, height: int, slot_id: int, 
                 font: pygame.font.Font, on_click: Optional[Callable] = None):
        self.rect = pygame.Rect(x, y, width, height)
        self.slot_id = slot_id
        self.font = font
        self.on_click = on_click
        self.player_data: Optional[Dict[str, Any]] = None
        self.is_occupied = False
        self.is_local_player = False
        
        # 颜色配置
        self.colors = {
            'empty': {
                'bg': (50, 50, 50),
                'border': (100, 100, 100),
                'text': (150, 150, 150)
            },
            'occupied': {
                'bg': (70, 120, 70),
                'border': (100, 150, 100),
                'text': (255, 255, 255)
            },
            'local_player': {
                'bg': (120, 70, 70),
                'border': (150, 100, 100),
                'text': (255, 255, 255)
            },
            'hover': {
                'bg': (80, 80, 80),
                'border': (120, 120, 120),
                'text': (255, 255, 255)
            }
        }
        
        self.hovered = False
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理事件"""
        mouse_pos = pygame.mouse.get_pos()
        
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(mouse_pos)
        
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.rect.collidepoint(mouse_pos):
                if self.on_click:
                    self.on_click(self.slot_id)
                return True
        
        return False
    
    def set_player(self, player_data: Optional[Dict[str, Any]], is_local: bool = False):
        """设置玩家数据"""
        self.player_data = player_data
        self.is_occupied = player_data is not None
        self.is_local_player = is_local
    
    def draw(self, surface: pygame.Surface):
        """绘制玩家槽"""
        # 选择颜色
        if self.is_local_player:
            colors = self.colors['local_player']
        elif self.is_occupied:
            colors = self.colors['occupied']
        elif self.hovered and not self.is_occupied:
            colors = self.colors['hover']
        else:
            colors = self.colors['empty']
        
        # 绘制背景
        pygame.draw.rect(surface, colors['bg'], self.rect)
        
        # 绘制边框
        pygame.draw.rect(surface, colors['border'], self.rect, 2)
        
        # 绘制文本
        if self.is_occupied and self.player_data:
            text = self.player_data.get('name', f'Player {self.slot_id + 1}')
            # 如果是本地玩家，添加标识
            if self.is_local_player:
                text += " (You)"
        else:
            text = f"Slot {self.slot_id + 1}"
        
        text_surface = self.font.render(text, True, colors['text'])
        text_rect = text_surface.get_rect(center=self.rect.center)
        surface.blit(text_surface, text_rect)


class Panel:
    """面板组件"""
    
    def __init__(self, x: int, y: int, width: int, height: int, title: str = "", 
                 font: Optional[pygame.font.Font] = None):
        self.rect = pygame.Rect(x, y, width, height)
        self.title = title
        self.font = font
        self.children = []
        
        # 颜色配置
        self.bg_color = (40, 40, 40)
        self.border_color = (80, 80, 80)
        self.title_color = (255, 255, 255)
    
    def add_child(self, child):
        """添加子组件"""
        self.children.append(child)
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """处理事件"""
        for child in self.children:
            if hasattr(child, 'handle_event'):
                if child.handle_event(event):
                    return True
        return False
    
    def draw(self, surface: pygame.Surface):
        """绘制面板"""
        # 绘制背景
        pygame.draw.rect(surface, self.bg_color, self.rect)
        
        # 绘制边框
        pygame.draw.rect(surface, self.border_color, self.rect, 3)
        
        # 绘制标题
        if self.title and self.font:
            title_surface = self.font.render(self.title, True, self.title_color)
            title_rect = title_surface.get_rect()
            title_rect.centerx = self.rect.centerx
            title_rect.y = self.rect.y + 10
            surface.blit(title_surface, title_rect)
        
        # 绘制子组件
        for child in self.children:
            if hasattr(child, 'draw'):
                child.draw(surface)


class TextLabel:
    """文本标签组件"""
    
    def __init__(self, x: int, y: int, text: str, font: pygame.font.Font, 
                 color: Tuple[int, int, int] = (255, 255, 255), centered: bool = False):
        self.x = x
        self.y = y
        self.text = text
        self.font = font
        self.color = color
        self.centered = centered
    
    def set_text(self, text: str):
        """设置文本"""
        self.text = text
    
    def draw(self, surface: pygame.Surface):
        """绘制文本标签"""
        text_surface = self.font.render(self.text, True, self.color)
        if self.centered:
            text_rect = text_surface.get_rect(center=(self.x, self.y))
            surface.blit(text_surface, text_rect)
        else:
            surface.blit(text_surface, (self.x, self.y)) 