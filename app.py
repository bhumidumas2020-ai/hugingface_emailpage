from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from transformers import pipeline
import sqlite3
import valkey
import json
import time
from multiprocessing import Process
import os
import hashlib

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_workers()   # runs on startup
    yield             # app runs here
    # anything after yield runs on shutdown

app = FastAPI(lifespan=lifespan)

# VALKEY
redis_client = valkey.Valkey(host="localhost", port=6379)
QUEUE = "review_queue"

# RATE LIMIT SETTINGS
RATE_LIMIT = 5
WINDOW = 5  # seconds


# HASH EMAIL
def hash_email(email: str):
    return hashlib.sha256(email.encode()).hexdigest()


# RATE LIMIT WITH PROXY SUPPORT
def check_rate_limit(request: Request):

    forwarded = request.headers.get("x-forwarded-for")

    if forwarded:
        ip = forwarded.split(",")[0].strip()
    else:
        ip = request.client.host

    print("Client IP:", ip)

    key = f"rate_limit:{ip}"
    block_key = f"blocked:{ip}"

    if redis_client.exists(block_key):
        raise HTTPException(
            status_code=429,
            detail="You are temporarily blocked. Try again later."
        )

    count = redis_client.incr(key)

    if count == 1:
        redis_client.expire(key, WINDOW)

    if count > RATE_LIMIT:
        redis_client.setex(block_key, WINDOW, "blocked")

        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. You are blocked for {WINDOW} seconds."
        )


# DATABASE
def get_db():
    conn = sqlite3.connect("stars_reviews.db", check_same_thread=False)
    return conn


# Create table if not exists
conn = get_db()
conn.execute("""
CREATE TABLE IF NOT EXISTS reviews (
id TEXT PRIMARY KEY,
emoji TEXT
)
""")
conn.commit()
conn.close()


def save_review(hashed_email, emoji):

    conn = get_db()

    conn.execute(
        "INSERT OR REPLACE INTO reviews (id, emoji) VALUES (?, ?)",
        (hashed_email, emoji)
    )

    conn.commit()
    conn.close()


# REQUEST MODEL
class Review(BaseModel):
    email: str
    review: str


# API
@app.post("/review")
def add_review(data: Review, request: Request):

    print("Incoming request from IP:", request.client.host)

    check_rate_limit(request)

    hashed_email = hash_email(data.email)

    job = {
        "email": hashed_email,
        "review": data.review
    }

    redis_client.rpush(QUEUE, json.dumps(job))

    return {"status": "queued for processing"}


@app.get("/reviews")
def get_reviews():

    conn = get_db()

    rows = conn.execute("SELECT * FROM reviews ORDER BY id DESC").fetchall()

    conn.close()

    result = []

    for r in rows:
        result.append({
            "id": r[0],
            "emoji": r[1]
        })

    return result


# WORKER
def worker():

    print("Worker started with PID:", os.getpid())

    # load model inside worker
    classifier = pipeline(
        "sentiment-analysis",
        model="nlptown/bert-base-multilingual-uncased-sentiment"
    )

    while True:

        jobs = []

        for _ in range(8):  # batch size

            job = redis_client.lpop(QUEUE)

            if not job:
                break

            jobs.append(json.loads(job))

        if len(jobs) == 0:
            time.sleep(1)
            continue

        reviews = [j["review"] for j in jobs]

        results = classifier(reviews)

        for job, res in zip(jobs, results):

            stars_count = int(res["label"][0])
            confidence = round(res["score"] * 100, 2)

            print("\n================ NEW REVIEW =================")
            print("Hashed Email:", job["email"])
            print("Review:", job["review"])
            print("Raw Model Output:", res)

            print("Predicted Stars:", stars_count)
            print("Confidence Score:", confidence, "%")

            if stars_count == 5:
                emoji = "😍"
            elif stars_count == 4:
                emoji = "😄"
            elif stars_count == 3:
                emoji = "😶"
            elif stars_count == 2:
                emoji = "😕"
            else:
                emoji = "😡"

            print("Emoji from Stars:", emoji)

            if confidence < 50:
                print("Low Confidence Detected → Showing Uncertainty")
                emoji = "❓"

            print("Final Emoji Displayed:", emoji)

            save_review(job["email"], emoji)

        print("Batch processed:", len(jobs))


# START WORKERS
def start_workers():

    for _ in range(6):  # 6 parallel workers
        p = Process(target=worker)
        p.start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

