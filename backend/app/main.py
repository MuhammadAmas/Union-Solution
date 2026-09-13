from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import ai, announcements, auth, recipients

app = FastAPI(title="CrewLink Member Callout")

# The frontend (localhost:3000) and backend (localhost:8000) are different
# origins, so the browser sends a CORS preflight (OPTIONS) before every
# non-trivial request -- e.g. the login POST with a JSON body. Without this,
# FastAPI has no OPTIONS route at all and the preflight 405s, which is exactly
# what showed up as "not logging in" with a CORS error in the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(announcements.router)
app.include_router(recipients.router)
app.include_router(ai.router)


@app.on_event("startup")
def on_startup() -> None:
    # create_all instead of a migration tool -- see DESIGN.md "what I cut".
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
