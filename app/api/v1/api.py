from fastapi import APIRouter

from app.api.v1 import auth, machines, orders

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(machines.router)
api_router.include_router(orders.router)
