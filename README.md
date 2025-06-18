# 🎮 Tank Battle Game

A real-time multiplayer tank battle game based on WebSocket with perfect client-server synchronization and zero position jitter.

## ✨ Features

- 🎯 **Zero position jitter** - Smooth movement with no visual stuttering
- 🔄 **Perfect client-server prediction** - Consistent position prediction
- 🎮 **Event-driven input handling** - Responsive controls
- 🚀 **60 FPS smooth rendering** - High performance rendering
- 🌐 **Real-time multiplayer battles** - Multiple players support
- 🔫 **Accurate bullet-player synchronization** - Precise collision detection

## 📁 Project Structure

```
RayCheng_Python_TankGame_ONLINE/
├── shared/                     # Shared Components
│   └── tank_game_messages.py   # Communication Protocol
├── server/                     # Backend
│   ├── tank_game_server.py     # Game Server
│   └── .env                    # Server Config
├── home/                       # Frontend
│   ├── tank_game_client.py     # Game Client
│   └── .env                    # Client Config
├── assets/                     # Assets
│   └── STHeiti Light.ttc       # Chinese Font
├── requirements.txt            # Dependencies
└── README.md                   # Documentation
```

## 🚀 Installation & Running

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv venv311

# Activate virtual environment
# macOS/Linux:
source venv311/bin/activate
# Windows:
# venv311\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create the following `.env` files:

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

### 3. Start Game

**Start Server:**
```bash
cd server
python tank_game_server.py
```

**Start Client:**
```bash
cd home
python tank_game_client.py
```

## 🎮 Game Controls

- **WASD** - Move tank
- **Mouse movement** - Aim
- **Left mouse button** - Shoot
- **ESC** - Quit game

## 🔧 Technical Architecture

- **Frontend**: Python + Pygame + WebSocket Client
- **Backend**: Python + WebSocket Server + AsyncIO
- **Communication Protocol**: JSON-based message protocol
- **Sync Strategy**: Client authority with server validation
- **Rendering Optimization**: Event-driven updates with minimal corrections

## 📊 Performance Features

- **Smart network transmission** - Optimized sending (20 FPS)
- **Consistent position prediction** - Same algorithms on client and server
- **Minimal server corrections** - Only correct on large differences (200px+ threshold)
- **Event-driven architecture** - Efficient message broadcasting
- **60 FPS rendering** - Smooth gameplay experience

## 🛠️ Development Notes

- Client and server use the same `TANK_SPEED` to ensure position prediction consistency
- Server trusts client position, only corrects on extreme differences
- Uses event-driven message broadcasting to reduce network traffic
- Font file supports Chinese character display

## 📝 License

This project is for educational and research purposes only. 