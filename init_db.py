#!/usr/bin/env python3
"""
Erzeugt die Datenbank im Ordner data/ und befüllt sie mit Testdaten.
- Legt data/ an, falls nicht vorhanden.
- Erstellt die Tabelle(n) (create_all).
- Setzt die Post-Daten zurück und fügt die Standard-Testposts ein.

Aufruf (aus Projektroot): python init_db.py
Die App nutzt die DB in data/, wenn DATABASE_URI auf data/masterblog.db zeigt
(z. B. vor dem Start gesetzt oder in .env).
"""

import os
import sys

# Projektroot = Verzeichnis dieses Scripts
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# data/ anlegen
data_dir = os.path.join(project_root, "data")
os.makedirs(data_dir, exist_ok=True)
db_path = os.path.join(data_dir, "masterblog.db")
uri = "sqlite:///" + os.path.abspath(db_path).replace("\\", "/")
os.environ["DATABASE_URI"] = uri

from backend.backend_app import app, db, Post


def seed_posts():
    """Zwei Standard-Testposts einfügen."""
    db.session.add(Post(
        title="First post",
        content="This is the first post.",
        author="Admin",
        date="2023-06-07",
        category_ids="[1]",
        tag_ids="[1, 2]",
    ))
    db.session.add(Post(
        title="Second post",
        content="This is the second post.",
        author="Admin",
        date="2023-06-08",
        category_ids="[2]",
        tag_ids="[2]",
    ))


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        Post.query.delete()
        seed_posts()
        db.session.commit()
    print(f"Database ready: {db_path}")
