from fastapi import APIRouter
router = APIRouter(prefix="/recommendations", tags=["recommender"])

@router.get("/_status")
async def status():
    return {"module": "recommender", "status": "stub — implementar por fatia vertical"}
