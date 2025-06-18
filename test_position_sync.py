#!/usr/bin/env python3
"""
位置同步测试脚本
用于验证多客户端位置同步的一致性和流畅性
"""

import time
import sys
import os
import json
from typing import Dict, List

# Add shared directory to Python path
sys.path.append(os.path.join(os.path.dirname(__file__), 'shared'))

from tank_game_entities import Player


class PositionSyncTester:
    """位置同步测试器"""
    
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.test_results = {
            'corrections': [],
            'jitter_events': [],
            'sync_accuracy': []
        }
        
    def create_test_player(self, player_id: str, name: str, is_local: bool = False) -> Player:
        """创建测试玩家"""
        player_data = {
            'player_id': player_id,
            'name': name,
            'position': {"x": 400.0, "y": 300.0},
            'moving_directions': {"w": False, "a": False, "s": False, "d": False}
        }
        
        player = Player(player_data)
        if is_local:
            player.is_local_player = True
        
        self.players[player_id] = player
        return player
    
    def simulate_server_position_update(self, player_id: str, server_pos: Dict[str, float], 
                                      directions: Dict[str, bool] = None):
        """模拟服务器位置更新"""
        if player_id in self.players:
            player = self.players[player_id]
            old_pos = player.position.copy()
            
            # 记录校正前的位置
            if hasattr(player, 'correction_history'):
                old_correction_count = len(player.correction_history)
            else:
                old_correction_count = 0
            
            # 执行位置更新
            player.update_from_server(server_pos, directions)
            
            # 记录校正后的位置
            new_correction_count = len(player.correction_history) if hasattr(player, 'correction_history') else 0
            
            # 计算位置变化
            dx = player.position["x"] - old_pos["x"]
            dy = player.position["y"] - old_pos["y"]
            position_change = (dx * dx + dy * dy) ** 0.5
            
            # 记录测试结果
            if new_correction_count > old_correction_count:
                self.test_results['corrections'].append({
                    'player_id': player_id,
                    'time': time.time(),
                    'position_change': position_change,
                    'server_pos': server_pos.copy(),
                    'client_pos': old_pos.copy()
                })
            
            return position_change
        return 0.0
    
    def test_movement_scenario(self):
        """测试移动场景"""
        print("🧪 Testing movement scenario...")
        
        # 创建测试玩家
        remote_player = self.create_test_player("remote_1", "RemotePlayer")
        
        # 模拟移动序列
        test_positions = [
            {"x": 400.0, "y": 300.0},  # 起始位置
            {"x": 410.0, "y": 300.0},  # 向右移动
            {"x": 420.0, "y": 300.0},  # 继续向右
            {"x": 425.0, "y": 305.0},  # 稍微偏移（模拟网络延迟）
            {"x": 430.0, "y": 300.0},  # 继续移动
            {"x": 440.0, "y": 300.0},  # 最终位置
        ]
        
        directions = {"w": False, "a": False, "s": False, "d": True}  # 向右移动
        
        corrections_count = 0
        total_jitter = 0.0
        
        for i, pos in enumerate(test_positions):
            print(f"Step {i+1}: Server position {pos}")
            
            # 模拟客户端预测（移动10px）
            if i > 0:
                remote_player.position["x"] += 10.0
            
            # 应用服务器位置更新
            change = self.simulate_server_position_update("remote_1", pos, directions)
            
            if change > 5.0:  # 显著的位置校正
                corrections_count += 1
                total_jitter += change
                print(f"  📍 Position correction: {change:.1f}px")
            
            print(f"  Client position: ({remote_player.position['x']:.1f}, {remote_player.position['y']:.1f})")
            
            # 模拟时间流逝
            time.sleep(0.016)  # 60 FPS
        
        print(f"\n📊 Movement test results:")
        print(f"  Total corrections: {corrections_count}")
        print(f"  Average jitter per correction: {total_jitter/max(corrections_count, 1):.1f}px")
        print(f"  Correction rate: {corrections_count/len(test_positions)*100:.1f}%")
        
        return corrections_count <= 2  # 成功标准：最多2次校正
    
    def test_oscillation_prevention(self):
        """测试振荡防护"""
        print("\n🧪 Testing oscillation prevention...")
        
        remote_player = self.create_test_player("remote_2", "OscillationTest")
        
        # 模拟可能导致振荡的位置序列
        base_pos = {"x": 400.0, "y": 300.0}
        oscillating_positions = [
            {"x": 405.0, "y": 300.0},  # 偏移5px
            {"x": 395.0, "y": 300.0},  # 偏移-5px
            {"x": 405.0, "y": 300.0},  # 再次偏移5px
            {"x": 395.0, "y": 300.0},  # 再次偏移-5px
            {"x": 405.0, "y": 300.0},  # 继续振荡
        ]
        
        initial_corrections = 0
        
        for i, pos in enumerate(oscillating_positions):
            change = self.simulate_server_position_update("remote_2", pos)
            
            if i < 2:  # 前两次更新的校正次数
                if change > 1.0:
                    initial_corrections += 1
            
            time.sleep(0.016)
        
        # 检查是否启动了防振荡机制
        final_corrections = len(self.test_results['corrections'])
        
        print(f"📊 Oscillation test results:")
        print(f"  Initial corrections: {initial_corrections}")
        print(f"  Total corrections: {final_corrections}")
        
        # 成功标准：防振荡机制应该限制后续校正
        oscillation_prevented = final_corrections <= initial_corrections + 2
        
        if oscillation_prevented:
            print("  ✅ Oscillation prevention active")
        else:
            print("  ❌ Oscillation prevention failed")
        
        return oscillation_prevented
    
    def run_all_tests(self):
        """运行所有测试"""
        print("🚀 Starting position sync optimization tests...\n")
        
        results = {}
        
        # 测试1：移动场景
        results['movement'] = self.test_movement_scenario()
        
        # 测试2：振荡防护
        results['oscillation'] = self.test_oscillation_prevention()
        
        # 总结结果
        print(f"\n📋 Test Summary:")
        passed_tests = sum(results.values())
        total_tests = len(results)
        
        for test_name, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"  {test_name.capitalize()}: {status}")
        
        print(f"\nOverall: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests == total_tests:
            print("🎉 All position sync optimizations working correctly!")
        else:
            print("⚠️ Some optimizations need adjustment")
        
        return results


def main():
    """主函数"""
    tester = PositionSyncTester()
    results = tester.run_all_tests()
    
    # 导出测试结果
    output_file = "position_sync_test_results.json"
    with open(output_file, 'w') as f:
        json.dump({
            'test_results': results,
            'detailed_data': tester.test_results,
            'timestamp': time.time()
        }, f, indent=2)
    
    print(f"\n📄 Detailed results saved to {output_file}")


if __name__ == "__main__":
    main() 