import time
from pydantic import BaseModel
from datetime import datetime
from typing import List
from nyansqlite import NyanSQLite, Indexed
import os

class Player(BaseModel):
    __nyan_primary_key__ = "player_id"
    player_id: int
    username: Indexed[str]
    level: Indexed[int]
    score: int = 0
    created_at: datetime

def benchmark():
    db_path = "bench.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    
    db = NyanSQLite(db_path)
    db.register(Player)
    
    count = 100000
    print(f"Generating {count} objects...")
    players = [
        Player(player_id=i, username=f"player_{i}", level=i % 50, score=i * 100, created_at=datetime.now())
        for i in range(1, count + 1)
    ]
    
    print("Starting insert_many...")
    start = time.time()
    db.insert_many(players)
    end = time.time()
    
    duration = end - start
    print(f"Inserted {count} rows in {duration:.4f}s ({count/duration:.2f} rows/s)")
    
    db.close()
    if os.path.exists(db_path):
        os.remove(db_path)

if __name__ == "__main__":
    for _ in range(3):
        benchmark()
