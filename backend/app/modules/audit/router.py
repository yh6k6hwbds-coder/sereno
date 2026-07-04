from fastapi import APIRouter
router = APIRouter(prefix="/audit", tags=["audit"])

@router.get("/_status")
async def status():
    return {"module": "audit", "status": "stub — implementar por fatia vertical"}
