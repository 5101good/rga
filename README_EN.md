# Remote GUI Automation

<p align="center">
  <img src="frontend/public/logo.png" alt="Remote GUI Automation Logo" width="200">
</p>

<p align="center">
  <strong>AI-Driven Remote GUI Automation Platform based on AgentBay Cloud Phones</strong>
</p>

<p align="center">
  English | <a href="./README.md">中文</a>
</p>

<p align="center">
  🌐 <a href="https://rga.ai-web.ai"><strong>Live Demo</strong></a>
</p>

---

Supporting streaming conversations, human takeover, and real-time screen display.

## Tech Stack

- **Backend**: FastAPI + Python 3.11+
- **Frontend**: React 19 + TypeScript + Vite
- **UI Library**: Ant Design X (@ant-design/x)
- **Authentication**: Supabase Auth (Google/GitHub OAuth)
- **Database**: Supabase PostgreSQL
- **Communication**: REST API + SSE (Server-Sent Events)

## Project Structure

```
project/
├── backend/          # FastAPI backend
│   ├── app/
│   │   ├── api/      # REST + SSE endpoints
│   │   ├── agents/   # AI Agent implementations (GLM/GELab)
│   │   ├── core/     # Configuration and Supabase integration
│   │   ├── models/   # Pydantic models
│   │   └── services/ # Business logic
│   └── migrations/   # Database migrations
├── frontend/         # React + Vite frontend
│   └── src/
│       ├── components/  # UI components
│       ├── services/    # API client
│       ├── store/       # Zustand state management
│       └── types/       # TypeScript types
├── package.json      # Monorepo configuration
└── README.md
```

## Quick Start

### 1. Prerequisites

- Python 3.11+
- Node.js 18+
- npm 9+
- ADB (Android Debug Bridge)

### 2. AgentBay Configuration

This project uses [AgentBay](https://www.aliyun.com/product/agentbay) for cloud phone services.

#### 2.1 Obtain API Key

1. Register an AgentBay account
2. Get your API Key from the [AgentBay Console](https://agentbay.console.aliyun.com/service-management)
3. Configure the API Key in `backend/.env`

#### 2.2 ADB Configuration

AgentBay requires an ADB public key for device authentication:

```bash
# Ensure ADB is installed
adb version

# Generate ADB key pair (if not exists)
adb devices

# Verify the key file exists
ls ~/.android/adbkey.pub
```

#### 2.3 Image Configuration

Optionally customize the cloud phone image. Configure the AgentBay image ID (default: `mobile-use-android-12`):

```env
AGENTBAY_IMAGE_ID=mobile-use-android-12
```

### 3. Supabase Configuration

1. Create a project on [Supabase](https://supabase.com)
2. Enable OAuth:
   - Go to Authentication > Providers
   - Enable Google/GitHub provider
   - Configure OAuth credentials
3. Run database migrations:
   - Open SQL Editor
   - Copy and execute the contents of `backend/migrations/001_init.sql`

### 4. Environment Variables

Backend configuration `backend/.env`:

```env
# Supabase Configuration
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key

# AgentBay Configuration
AGENTBAY_API_KEY=your-agentbay-api-key
AGENTBAY_IMAGE_ID=mobile-use-android-12  # Optional

# Model API Configuration (default)
MODEL_BASE_URL=http://localhost:8000/v1
MODEL_NAME=autoglm-phone-9b
MODEL_API_KEY=EMPTY

# GLM Agent Model Configuration
GLM_MODEL_BASE_URL=
GLM_MODEL_NAME=
GLM_MODEL_API_KEY=

# GELab Agent (StepFun) Model Configuration
GELAB_MODEL_BASE_URL=
GELAB_MODEL_NAME=gelab-zero-4b-preview
GELAB_MODEL_API_KEY=

# Session Limits
MAX_SESSIONS_PER_DAY=30
MAX_ACTIVE_SESSIONS=10

# Server Configuration
HOST=0.0.0.0
PORT=8080
DEBUG=true

# CORS Origins (comma-separated)
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

Frontend configuration `frontend/.env`:

```env
VITE_SUPABASE_URL=https://xxx.supabase.co
VITE_SUPABASE_ANON_KEY=xxx
VITE_API_URL=http://localhost:8080
```

### 5. Install Dependencies

```bash
# Install all dependencies
npm run install:all
```

### 6. Start Development Server

```bash
# Start both frontend and backend
npm run dev

# Or start separately
npm run dev:backend   # Backend at http://localhost:8080
npm run dev:frontend  # Frontend at http://localhost:5173
```

## Features

- 🔐 **Multiple Login Options** - Google and GitHub OAuth authentication
- 💬 **Streaming Conversations** - Real-time display of AI thinking process and actions
- 📱 **Cloud Phone Control** - Remote Android device control via AgentBay
- 🖥️ **Real-time Display** - Embedded phone screen display and interaction
- 🤝 **Human Takeover** - Manual intervention for login, captcha, and other scenarios
- 🤖 **Multi-Agent Support** - Support for GLM and GELab AI agents

## API Endpoints

### Agent API

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/agent/{sessionId}/task` | Execute task (SSE streaming response) |
| POST | `/api/agent/{sessionId}/stop` | Stop current task |
| POST | `/api/agent/{sessionId}/takeover/complete` | Complete human takeover |
| GET | `/api/agent/{sessionId}/status` | Get session status |

### SSE Event Types

| Event | Description |
|-------|-------------|
| `ready` | Connection ready |
| `thinking` | Agent is thinking |
| `action` | Action executed |
| `screenshot` | Screenshot updated |
| `takeover` | Human takeover required |
| `completed` | Task completed |
| `error` | Error occurred |
| `stopped` | Task stopped |

## API Documentation

After starting the backend, visit http://localhost:8080/docs for OpenAPI documentation.

## License

Apache 2.0 License

## Acknowledgments

Thanks to the excellent work of the following open source projects and the strong support from the AgentBay team for this project:

- [AgentBay SDK](https://github.com/aliyun/wuying-agentbay-sdk)
- [Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM)
- [GELab-Zero](https://github.com/stepfun-ai/gelab-zero)
