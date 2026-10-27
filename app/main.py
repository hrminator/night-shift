from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="Night Shift")


@app.get("/", response_class=HTMLResponse)
def hello() -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return (
        "<!doctype html><html><head><title>Night Shift</title></head>"
        f"<body><h1>Night Shift</h1><p>{now}</p></body></html>"
    )
