# 🎮 坦克大战游戏 Tank Battle Game

一个基于 WebSocket 的实时多人坦克对战游戏，具有完美的客户端-服务器同步和零位置颤动。

A real-time multiplayer tank battle game based on WebSocket with perfect client-server synchronization and zero position jitter.

## ✨ 特性 Features

- 🎯 **零位置颤动** - Zero position jitter
- 🔄 **完美客户端-服务器预测** - Perfect client-server prediction
- 🎮 **事件驱动输入处理** - Event-driven input handling
- 🚀 **60 FPS 流畅渲染** - Smooth 60 FPS rendering
- 🌐 **实时多人对战** - Real-time multiplayer battles
- 🔫 **精确子弹-玩家同步** - Accurate bullet-player synchronization

## 📁 项目结构 Project Structure

```
RayCheng_Python_TankGame_ONLINE/
├── shared/                     # 共享组件 Shared Components
│   └── tank_game_messages.py   # 通信协议 Communication Protocol
├── server/                     # 后端 Backend
│   ├── tank_game_server.py     # 游戏服务器 Game Server
│   └── .env                    # 服务器配置 Server Config
├── home/                       # 前端 Frontend
│   ├── tank_game_client.py     # 游戏客户端 Game Client
│   └── .env                    # 客户端配置 Client Config
├── assets/                     # 资源文件 Assets
│   └── STHeiti Light.ttc       # 中文字体 Chinese Font
├── requirements.txt            # 依赖列表 Dependencies
└── README.md                   # 说明文档 Documentation
```

## 🚀 安装和运行 Installation & Running

### 1. 安装依赖 Install Dependencies

```bash
# 创建虚拟环境 Create virtual environment
python -m venv venv311

# 激活虚拟环境 Activate virtual environment
# macOS/Linux:
source venv311/bin/activate
# Windows:
# venv311\Scripts\activate

# 安装依赖 Install dependencies
pip install -r requirements.txt
```

### 2. 配置环境变量 Configure Environment Variables

创建以下 `.env` 文件 Create the following `.env` files:

**server/.env:**
```env
SCREEN_WIDTH=800
SCREEN_HEIGHT=600
FPS=60
TANK_SPEED=300
SERVER_HOST=localhost
SERVER_PORT=8765
MAX_PLAYERS_PER_ROOM=8
BULLET_SPEED=300
BULLET_DAMAGE=25
BULLET_LIFETIME=5.0
```

**home/.env:**
```env
SCREEN_WIDTH=800
SCREEN_HEIGHT=600
FPS=60
TANK_SPEED=300
SERVER_URL=ws://localhost:8765
DEFAULT_FONT_PATH=../assets/STHeiti Light.ttc
MOVEMENT_SEND_INTERVAL=0.05
POSITION_CHANGE_THRESHOLD=5.0
PING_INTERVAL=2.0
```

### 3. 启动游戏 Start Game

**启动服务器 Start Server:**
```bash
cd server
python tank_game_server.py
```

**启动客户端 Start Client:**
```bash
cd home
python tank_game_client.py
```

## 🎮 游戏控制 Game Controls

- **WASD** - 移动坦克 Move tank
- **鼠标移动** - 瞄准 Aim
- **鼠标左键** - 射击 Shoot
- **ESC** - 退出游戏 Quit game

## 🔧 技术架构 Technical Architecture

- **前端** Frontend: Python + Pygame + WebSocket Client
- **后端** Backend: Python + WebSocket Server + AsyncIO
- **通信协议** Communication: JSON-based message protocol
- **同步策略** Sync Strategy: Client authority with server validation
- **渲染优化** Rendering: Event-driven updates with minimal corrections

## 📊 性能特性 Performance Features

- **智能网络发送** - Smart network transmission (20 FPS)
- **位置预测一致性** - Consistent position prediction
- **最小服务器校正** - Minimal server corrections (200px+ threshold)
- **事件驱动架构** - Event-driven architecture
- **60 FPS 渲染** - Smooth 60 FPS rendering

## 🛠️ 开发说明 Development Notes

- 客户端和服务器使用相同的 `TANK_SPEED` 确保位置预测一致性
- 服务器信任客户端位置，只在极大差异时进行校正
- 使用事件驱动的消息广播减少网络流量
- 字体文件支持中文显示

## 📝 许可证 License

本项目仅供学习和研究使用。
This project is for educational and research purposes only. 