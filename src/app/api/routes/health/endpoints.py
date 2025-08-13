from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/")
@router.get("/health")
async def predict() -> dict[str, str]:
    return {
        "status": "healthy",
        "message": "The API is running smoothly.",
    }
