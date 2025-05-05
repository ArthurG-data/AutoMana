from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, 
import httpx
import os

app = FastAPI(title="API Gateway")

@app.api_route("/api/v1/{path:path}", methods=["GET", "POST", "UPDATE", "DELETE"],include_in_schema=False)
async def v1_gateway(request : Request, path :str, api_router: APIRouter = Depends(APIRouter)):
    try:
        response = await api_router.route(request=request)
        return response
    except RouteNotFoundException as rnfe:
        return {
            "unquthorized" : "No such route"
        }
    except MethodNotAllowedException as mnae:
        return {
            "unauthorized" : "Method not allowed"
        }
