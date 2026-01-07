import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sports_store.db")

products = [
    ("Football", 499, "Outdoor", "football.jpeg"),
    ("Cricket Bat", 1299, "Outdoor", "cricket_bat.jpeg"),
    ("Tennis Racket", 999, "Indoor", "tennis_racket.jpeg"),
    ("Dumbbells", 999, "Fitness", "dumbbells.jpeg"),
    ("Yoga Mat", 699, "Fitness", "yoga_mat.jpeg"),
]

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

for product in products:
    try:
        cursor.execute(
            "INSERT INTO products (name, price, category, image) VALUES (?, ?, ?, ?)",
            product
        )
    except sqlite3.IntegrityError:
        pass

conn.commit()
conn.close()

print("Products seeded into:", DB_PATH)
