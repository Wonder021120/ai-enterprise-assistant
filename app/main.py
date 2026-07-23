from fastapi import FastAPI


app = FastAPI(
    title="CareerPilot AI",
    description="An AI job analysis assistant for graduate job seekers.",
    version="0.1.0",
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "CareerPilot AI",
    }