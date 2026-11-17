"""POST /api/chat."""

from fastapi import APIRouter, Request

from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest, request: Request) -> ChatResponse:
    return request.app.state.rag.answer(body.question.strip(), body.session_id)
