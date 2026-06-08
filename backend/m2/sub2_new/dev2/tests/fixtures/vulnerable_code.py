import sqlite3

def get_user(username):
    conn = sqlite3.connect("test.db")
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE name = '" + username + "'"  # SQL Injection
    cursor.execute(query)
    return cursor.fetchall()
