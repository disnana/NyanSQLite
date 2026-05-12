# tests/bench.py

from __future__ import annotations

import orjson as json
import random
import sqlite3
import string

import apsw
import pytest

from nyansqlite import NyanSQLite


# =========================================================
# CONFIG
# =========================================================

ROW_COUNT = 100_000


# =========================================================
# HELPERS
# =========================================================

def rand_name():
    return "".join(random.choices(string.ascii_lowercase, k=12))


def make_profile(i: int):
    return {
        "id": i,
        "profile": {
            "name": rand_name(),
            "stats": {
                "logins": i,
                "score": i * 10,
            },
            "online": bool(i % 2),
        },
    }


# =========================================================
# FIXTURES
# =========================================================

@pytest.fixture()
def sqlite3_db(tmp_path):
    path = tmp_path / "sqlite3.db"

    conn = sqlite3.connect(path)

    conn.execute("""
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        profile TEXT
    )
    """)

    yield conn

    conn.close()


@pytest.fixture()
def apsw_db(tmp_path):
    path = tmp_path / "apsw.db"

    conn = apsw.Connection(str(path))

    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        profile TEXT
    )
    """)

    yield conn


@pytest.fixture()
def nyan_db(tmp_path):
    path = tmp_path / "nyan.db"

    db = NyanSQLite(str(path))

    db.execute("""
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        profile TEXT
    )
    """)

    yield db


# =========================================================
# SHARED DATA
# =========================================================

SQLITE_ROWS = [
    (
        i,
        json.dumps(make_profile(i)),
    )
    for i in range(ROW_COUNT)
]

NYAN_ROWS = [
    {
        "id": i,
        "profile": make_profile(i),
    }
    for i in range(ROW_COUNT)
]


# =========================================================
# INSERT
# =========================================================

@pytest.mark.benchmark(group="insert")
def test_sqlite3_insert(benchmark, sqlite3_db):

    def setup():
        sqlite3_db.execute("DELETE FROM users")
        sqlite3_db.commit()

    def run():
        sqlite3_db.executemany(
            "INSERT INTO users VALUES (?, ?)",
            SQLITE_ROWS,
        )
        sqlite3_db.commit()

    benchmark.pedantic(
        run,
        setup=setup,
        rounds=5,
        iterations=1,
    )


@pytest.mark.benchmark(group="insert")
def test_apsw_insert(benchmark, apsw_db):

    def setup():
        apsw_db.cursor().execute("DELETE FROM users")

    def run():
        with apsw_db:
            apsw_db.cursor().executemany(
                "INSERT INTO users VALUES (?, ?)",
                SQLITE_ROWS,
            )

    benchmark.pedantic(
        run,
        setup=setup,
        rounds=5,
        iterations=1,
    )


@pytest.mark.benchmark(group="insert")
def test_nyan_insert(benchmark, nyan_db):

    def setup():
        nyan_db.execute("DELETE FROM users")

    def run():
        nyan_db.users.insert_many(NYAN_ROWS)

    benchmark.pedantic(
        run,
        setup=setup,
        rounds=5,
        iterations=1,
    )


# =========================================================
# FETCH
# =========================================================

@pytest.mark.benchmark(group="fetch")
def test_sqlite3_fetch(benchmark, sqlite3_db):
    sqlite3_db.executemany(
        "INSERT INTO users VALUES (?, ?)",
        SQLITE_ROWS,
    )
    sqlite3_db.commit()

    def run():
        cur = sqlite3_db.execute(
            "SELECT * FROM users"
        )

        return cur.fetchall()

    benchmark(run)


@pytest.mark.benchmark(group="fetch")
def test_apsw_fetch(benchmark, apsw_db):
    with apsw_db:
        apsw_db.cursor().executemany(
            "INSERT INTO users VALUES (?, ?)",
            SQLITE_ROWS,
        )

    def run():
        return list(
            apsw_db.cursor().execute(
                "SELECT * FROM users"
            )
        )

    benchmark(run)


@pytest.mark.benchmark(group="fetch")
def test_nyan_fetch(benchmark, nyan_db):
    nyan_db.users.insert_many(NYAN_ROWS)

    def run():
        return nyan_db.users.all()

    benchmark(run)


# =========================================================
# JSON PATCH
# =========================================================

@pytest.mark.benchmark(group="json_patch")
def test_python_json_patch(benchmark, sqlite3_db):
    sqlite3_db.execute(
        "INSERT INTO users VALUES (?, ?)",
        (
            1,
            json.dumps(make_profile(1)),
        ),
    )

    sqlite3_db.commit()

    def run():
        cur = sqlite3_db.execute(
            "SELECT profile FROM users WHERE id=1"
        )

        profile = json.loads(cur.fetchone()[0])

        profile["profile"]["stats"]["logins"] += 1

        sqlite3_db.execute(
            "UPDATE users SET profile=? WHERE id=1",
            [json.dumps(profile)],
        )

        sqlite3_db.commit()

    benchmark(run)


@pytest.mark.benchmark(group="json_patch")
def test_nyan_json_patch(benchmark, nyan_db):
    nyan_db.users.insert({
        "id": 1,
        "profile": make_profile(1),
    })

    def run():
        nyan_db.users.json_set(
            "profile",
            "profile.stats.logins",
            999,
            where={"id": 1},
        )

    benchmark(run)