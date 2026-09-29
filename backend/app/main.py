from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Session

from app.api.v1.endpoints import admin, auth, chapters, settings, ai, ai_providers, memory, knowledge, finetune, presets, users
from app.api.v1.endpoints import books as books_ep, conversations as conversations_ep
from app.db.session import engine
from app.db.migration import run_startup_migration
from app.core.config import settings as app_settings
from app.core.access import access_token_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时创建所有数据库表
    SQLModel.metadata.create_all(engine)
    # 执行启动迁移（幂等：创建默认书籍 & 归并孤立章节）
    with Session(engine) as session:
        run_startup_migration(session)
    yield
    # 关闭时可以做一些清理工作


app = FastAPI(
    title=app_settings.PROJECT_NAME,
    version=app_settings.VERSION,
    description="小说 IDE 后端 API",
    lifespan=lifespan
)

app.middleware("http")(access_token_middleware)

# 添加 CORS 中间件，允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册认证路由
app.include_router(
    auth.router,
    prefix=f"{app_settings.API_V1_STR}/auth",
    tags=["auth"]
)

app.include_router(
    admin.router,
    prefix=f"{app_settings.API_V1_STR}/admin",
    tags=["admin"]
)

# 注册用户资料和轻量互动路由
app.include_router(
    users.router,
    prefix=f"{app_settings.API_V1_STR}/users",
    tags=["users"]
)

# 注册章节路由
app.include_router(
    chapters.router,
    prefix=f"{app_settings.API_V1_STR}/chapters",
    tags=["chapters"]
)

# 注册设置路由
app.include_router(
    settings.router,
    prefix=f"{app_settings.API_V1_STR}/settings",
    tags=["settings"]
)

# 注册 AI 路由
app.include_router(
    ai_providers.router,
    prefix=f"{app_settings.API_V1_STR}/ai/providers",
    tags=["ai-providers"]
)

app.include_router(
    ai.router,
    prefix=f"{app_settings.API_V1_STR}/ai",
    tags=["ai"]
)

# 注册记忆/提示词路由
app.include_router(
    memory.router,
    prefix=f"{app_settings.API_V1_STR}/memory",
    tags=["memory"]
)

# 注册知识库路由
app.include_router(
    knowledge.router,
    prefix=f"{app_settings.API_V1_STR}/knowledge",
    tags=["knowledge"]
)

# 注册微调占位路由
app.include_router(
    finetune.router,
    prefix=f"{app_settings.API_V1_STR}/finetune",
    tags=["finetune"]
)

# 注册预设路由
app.include_router(
    presets.router,
    prefix=f"{app_settings.API_V1_STR}/presets",
    tags=["presets"]
)

# 注册书籍路由（含章节子路由）
app.include_router(
    books_ep.router,
    prefix=f"{app_settings.API_V1_STR}/books",
    tags=["books"]
)

# 注册对话记录路由
app.include_router(
    conversations_ep.router,
    prefix=f"{app_settings.API_V1_STR}/conversations",
    tags=["conversations"]
)


@app.get("/")
def root():
    return {
        "message": "Welcome to NovelCat Backend",
        "docs": "/docs",
        "redoc": "/redoc",
        "api": app_settings.API_V1_STR,
    }
