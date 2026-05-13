from src.nyansqlite import NyanSQLite, SQLMetadata
from pydantic import BaseModel, EmailStr
from typing import Annotated, List
import time

# メタデータの定義
PK = SQLMetadata(primary_key=True)
Index = SQLMetadata(index=True)

# 1. データの構造を定義
class Player(BaseModel):
    # IDを主キーに設定
    player_id: Annotated[int, PK]
    # ユーザー名をインデックス対象に
    username: Annotated[str, Index]
    email: EmailStr
    # レベルでソートや絞り込みをすることを想定してインデックスを貼る
    level: Annotated[int, Index]

# 2. データベースの初期化
db = NyanSQLite("game_data.db")
db.create_table(Player)

# 3. 単発の挿入 (insert)
# ユーザー登録など、発生の都度書き込む場合に適しています
new_player = Player(
    player_id=1,
    username="nyan_master",
    email="admin@example.com",
    level=99
)
db.insert(new_player)
print(f"Single insert: {new_player.username}")

# 4. 大量データの挿入 (bulk_insert)
# ループ内でinsertを回すより圧倒的に高速です
print("Preparing bulk data...")
players_data = [
    Player(
        player_id=i,
        username=f"bot_{i}",
        email=f"bot_{i}@example.com",
        level=i % 50
    )
    for i in range(10, 10010)  # 1万件のデータ
]

print(f"Inserting {len(players_data)} rows via bulk_insert...")
start_time = time.perf_counter()

# ライブラリ側で実装した executemany + transaction を利用
db.bulk_insert(players_data)

end_time = time.perf_counter()
print(f"Bulk insert finished in {end_time - start_time:.4f} seconds.")

# 5. データの整合性チェック
# 実際にインデックスが効いているかなどは SQLite 側で確認可能
print("Database processing completed.")