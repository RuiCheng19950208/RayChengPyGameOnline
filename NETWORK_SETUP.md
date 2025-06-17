# 多台电脑联机对战配置指南

## 第一步：创建 .env 文件

在项目根目录创建 `.env` 文件，内容如下：

```bash
# 游戏配置
SCREEN_WIDTH=800
SCREEN_HEIGHT=600
FPS=60
TANK_SPEED=300

# 服务器网络配置 - 多台电脑联机
SERVER_HOST=0.0.0.0
SERVER_PORT=8765
MAX_PLAYERS_PER_ROOM=8

# 子弹配置
BULLET_SPEED=300
BULLET_DAMAGE=25
BULLET_LIFETIME=5.0

# 字体配置
DEFAULT_FONT_PATH=assets/STHeiti Light.ttc
```

## 第二步：配置服务器电脑

1. **确保防火墙允许端口 8765**
   - macOS: `系统偏好设置 > 安全性与隐私 > 防火墙`
   - Windows: `控制面板 > 系统和安全 > Windows Defender 防火墙`

2. **获取服务器电脑的IP地址**
   ```bash
   # macOS/Linux
   ifconfig | grep "inet " | grep -v 127.0.0.1
   
   # Windows
   ipconfig
   ```

3. **启动服务器**
   ```bash
   cd RayChengPyGameOnline
   python server/tank_game_server.py
   ```

## 第三步：配置客户端电脑

修改客户端连接地址，有两种方法：

### 方法1：修改客户端代码（推荐）

编辑 `home/tank_game_client.py`，找到这一行：
```python
def __init__(self, server_url: str = "ws://localhost:8765"):
```

修改为：
```python
def __init__(self, server_url: str = "ws://[服务器IP]:8765"):
```

例如，如果服务器IP是 `192.168.1.100`：
```python
def __init__(self, server_url: str = "ws://192.168.1.100:8765"):
```

### 方法2：运行时指定服务器地址

修改客户端启动方式：
```python
# 在 main() 函数中修改
client = PerfectGameClient("ws://192.168.1.100:8765")
```

## 第四步：测试连接

1. **在服务器电脑上启动服务器**
   ```bash
   python server/tank_game_server.py
   ```

2. **在客户端电脑上启动游戏**
   ```bash
   python home/tank_game_client.py
   ```

3. **验证连接**
   - 客户端应该显示 "✅ Connected to server"
   - 服务器应该显示新玩家连接信息

## 常见问题解决

### 连接失败
1. 检查网络连通性：`ping [服务器IP]`
2. 检查端口是否开放：`telnet [服务器IP] 8765`
3. 确认防火墙设置
4. 确认两台电脑在同一网络中

### 游戏卡顿
1. 检查网络延迟：客户端会显示 Ping 值
2. 确保网络稳定
3. 关闭其他占用网络的程序

## 网络架构说明

```
服务器电脑 (192.168.1.100:8765)
    ↕️ WebSocket 连接
客户端电脑1 (192.168.1.101) ←→ 游戏同步 ←→ 客户端电脑2 (192.168.1.102)
```

- 服务器负责游戏状态管理和物理计算
- 客户端负责渲染和输入处理
- 所有游戏数据通过服务器中转同步 