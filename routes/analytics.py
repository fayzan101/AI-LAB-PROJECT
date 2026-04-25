from fastapi import APIRouter
from services.ai_engine import (
    calculate_productivity,
    detect_burnout,
    predict_delay,
    generate_summary
)

router = APIRouter()


@router.post("/analytics/report")
def full_report(data: dict):

    productivity = calculate_productivity(data)
    burnout = detect_burnout(data)
    delay = predict_delay(data)
    summary = generate_summary(productivity, burnout, delay)

    return {
        "productivity_score": productivity,
        "burnout_risk": burnout,
        "task_delay_risk": delay,
        "summary": summary
    }