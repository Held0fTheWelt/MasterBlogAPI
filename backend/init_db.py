#!/usr/bin/env python3
"""
Create the database in the data/ folder and fill it with test data.
Standalone – uses only the standard library (sqlite3, os).

- Creates data/ if it does not exist.
- Creates the posts table (schema as expected by the backend).
- Deletes existing post rows and inserts the default test posts.

Run from project root: python init_db.py
"""

import os
import sqlite3

# Database path: project_root/data/masterblog.db
script_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(script_dir, "data")
db_path = os.path.join(data_dir, "masterblog.db")

# Schema as expected by the backend Post model
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    author VARCHAR(200) DEFAULT '',
    date VARCHAR(10) NOT NULL,
    category_ids TEXT DEFAULT '[]',
    tag_ids TEXT DEFAULT '[]'
);
"""

TEST_POSTS = [
    ("First post", "This is the first post.", "Admin", "2023-06-07", "[1]", "[1, 2]"),
    ("Second post", "This is the second post.", "Admin", "2023-06-08", "[2]", "[2]"),
]


def main():
    os.makedirs(data_dir, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(CREATE_TABLE)
        conn.execute("DELETE FROM posts")
        for row in TEST_POSTS:
            conn.execute(
                "INSERT INTO posts (title, content, author, date, category_ids, tag_ids) VALUES (?, ?, ?, ?, ?, ?)",
                row,
            )
        conn.commit()
    finally:
        conn.close()
    print(f"Database ready: {db_path}")


if __name__ == "__main__":
    main()
