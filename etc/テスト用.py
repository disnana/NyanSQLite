from pydantic import BaseModel
from nyansqlite import NyanSQLite, Indexed, Searchable
import os
from datetime import datetime

class Player(BaseModel):
    __nyan_primary_key__ = "player_id"   # id以外を主キーにするときに指定
    player_id: int
    username: Indexed[str]
    level: Indexed[int]
    score: int = 0
    created_at: datetime

if os.path.exists("../game.db"):
    os.remove("../game.db")

db = NyanSQLite("../game.db")
db.register(Player)

players = [
    Player(player_id=i, username=f"player_{i}", level=i % 50, score=i * 100, created_at=datetime.now())
    for i in range(1, 100001)
]

import time
start = time.time()
db.insert_many(players)
print(f"Inserted in {time.time() - start:.4f}s")
# 結果: 0.3456s 程度