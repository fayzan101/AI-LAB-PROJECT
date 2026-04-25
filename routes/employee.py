from fastapi import APIRouter
router = APIRouter()
@router.post("/employee/data")
def receive_employee(data: dict):
    return {
        "message": "Data received",
        "data": data
    }