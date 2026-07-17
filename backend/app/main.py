from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.agent import router as agent_router
from app.api.evaluation import router as evaluation_router
from app.api.knowledge import router as knowledge_router
from app.api.tickets import router as tickets_router
from app.api.tools import router as tools_router

app = FastAPI(title="Kefu Agent Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(agent_router)
app.include_router(admin_router)
app.include_router(tools_router)
app.include_router(tickets_router)
app.include_router(knowledge_router)
app.include_router(evaluation_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "kefu-agent-backend"}
