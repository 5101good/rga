# Remote GUI Automation

<p align="center">
  <img src="frontend/public/logo.png" alt="Remote GUI Automation Logo" width="200">
</p>

<p align="center">
  <strong>基于 AgentBay 云手机的 AI 驱动远程 GUI 自动化平台</strong>
</p>

<p align="center">
  <a href="./README_EN.md">English</a> | 中文
</p>

<p align="center">
  🌐 <a href="https://rga.ai-web.ai"><strong>在线体验 Demo</strong></a>
</p>

---

支持流式对话、人工接管和实时画面显示。

## 技术栈

- **后端**: FastAPI + Python 3.11+
- **前端**: React 19 + TypeScript + Vite
- **UI 库**: Ant Design X (@ant-design/x)
- **认证**: Supabase Auth (Google/GitHub OAuth)
- **数据库**: Supabase PostgreSQL
- **通信**: REST API + SSE (Server-Sent Events)

## 项目结构

```
project/
├── backend/          # FastAPI 后端
│   ├── app/
│   │   ├── api/      # REST + SSE 端点
│   │   ├── agents/   # AI Agent 实现 (GLM/GELab)
│   │   ├── core/     # 配置和 Supabase 集成
│   │   ├── models/   # Pydantic 模型
│   │   └── services/ # 业务逻辑
│   └── migrations/   # 数据库迁移
├── frontend/         # React + Vite 前端
│   └── src/
│       ├── components/  # UI 组件
│       ├── services/    # API 客户端
│       ├── store/       # Zustand 状态管理
│       └── types/       # TypeScript 类型
├── package.json      # Monorepo 配置
└── README.md
```

## 快速开始

### 1. 环境要求

- Python 3.11+
- Node.js 18+
- npm 9+
- ADB (Android Debug Bridge)

### 2. AgentBay 配置

本项目使用 [AgentBay](https://www.aliyun.com/product/agentbay) 提供云手机服务。

#### 2.1 获取 API Key

1. 注册 AgentBay 账号
2. 在 [AgentBay控制台](https://agentbay.console.aliyun.com/service-management) 获取 API Key
3. 将 API Key 配置到 `backend/.env` 中

#### 2.2 ADB 配置

AgentBay 需要 ADB 公钥进行设备认证：

```bash
# 确保已安装 ADB
adb version

# 生成 ADB 密钥对（如果不存在）
adb devices

# 确认密钥文件存在
ls ~/.android/adbkey.pub
```

#### 2.3 镜像配置

可选自定义云手机镜像，自定义后配置 AgentBay 镜像 ID（默认 `mobile-use-android-12`）：

```env
AGENTBAY_IMAGE_ID=mobile-use-android-12
```

### 3. Supabase 配置

1. 在 [Supabase](https://supabase.com) 创建项目
2. 启用 OAuth:
   - 进入 Authentication > Providers
   - 启用 Google/GitHub provider
   - 配置 OAuth credentials
3. 运行数据库迁移:
   - 打开 SQL Editor
   - 复制 `backend/migrations/001_init.sql` 内容并执行

### 4. 配置环境变量

后端配置 `backend/.env`:

```env
# Supabase Configuration
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key

# AgentBay Configuration
AGENTBAY_API_KEY=your-agentbay-api-key
AGENTBAY_IMAGE_ID=mobile-use-android-12  # 可选

# Model API Configuration (默认配置)
MODEL_BASE_URL=http://localhost:8000/v1
MODEL_NAME=autoglm-phone-9b
MODEL_API_KEY=EMPTY

# GLM Agent 模型配置 
GLM_MODEL_BASE_URL=
GLM_MODEL_NAME=
GLM_MODEL_API_KEY=

# GELab Agent（StepFun）模型配置 
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

# CORS Origins (逗号分隔)
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
```

前端配置 `frontend/.env`:

```env
VITE_SUPABASE_URL=https://xxx.supabase.co
VITE_SUPABASE_ANON_KEY=xxx
VITE_API_URL=http://localhost:8080
```

### 5. 安装依赖

```bash
# 安装所有依赖
npm run install:all
```

### 6. 启动开发服务器

```bash
# 同时启动前后端
npm run dev

# 或分别启动
npm run dev:backend   # 后端 http://localhost:8080
npm run dev:frontend  # 前端 http://localhost:5173
```

## 功能特性

- 🔐 **多种登录方式** - 支持 Google 和 GitHub OAuth 登录
- 💬 **流式对话** - 实时显示 AI 思考过程和执行动作
- 📱 **云手机控制** - 通过 AgentBay 远程控制 Android 设备
- 🖥️ **实时画面** - 嵌入式手机画面显示和交互
- 🤝 **人工接管** - 支持登录、验证码等场景的人工介入
- 🤖 **多 Agent 支持** - 支持 GLM 和 GELab 两种 AI Agent

## API 端点

### Agent API

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/agent/{sessionId}/task` | 执行任务 (SSE 流式响应) |
| POST | `/api/agent/{sessionId}/stop` | 停止当前任务 |
| POST | `/api/agent/{sessionId}/takeover/complete` | 完成人工接管 |
| GET | `/api/agent/{sessionId}/status` | 获取会话状态 |

### SSE 事件类型

| 事件 | 说明 |
|------|------|
| `ready` | 连接就绪 |
| `thinking` | Agent 思考中 |
| `action` | 执行动作 |
| `screenshot` | 屏幕截图更新 |
| `takeover` | 需要人工接管 |
| `completed` | 任务完成 |
| `error` | 错误 |
| `stopped` | 任务被停止 |

## API 文档

启动后端后，访问 http://localhost:8080/docs 查看 OpenAPI 文档。

## 许可证

Apache 2.0 License

## 致谢

感谢以下开源项目的优秀工作以及 AgentBay 团队对本项目的大力支持：

- [AgentBay SDK](https://github.com/aliyun/wuying-agentbay-sdk)
- [Open-AutoGLM](https://github.com/zai-org/Open-AutoGLM)
- [GELab-Zero](https://github.com/stepfun-ai/gelab-zero)
