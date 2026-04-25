from fastapi import FastAPI
from routes import employee, analytics
app = FastAPI(title="AI Employee Analytics System")
app.include_router(employee.router)
app.include_router(analytics.router)
@app.get("/")
def home():
    return {"message": "FastAPI AI System Running"}