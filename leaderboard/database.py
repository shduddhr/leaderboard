import os
import sqlite3
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date
import hashlib

# 환경 변수에서 DATABASE_URL을 가져옵니다. (Render에서 자동으로 주입해줌)
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_connection():
    if DATABASE_URL:
        # Render PostgreSQL 연결
        return psycopg2.connect(DATABASE_URL)
    else:
        # 로컬 테스트용 SQLite 연결 (DB_URL이 없을 때)
        return sqlite3.connect("leaderboard.db")

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    if DATABASE_URL:
        # PostgreSQL 문법
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            team_name VARCHAR(255) PRIMARY KEY,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id SERIAL PRIMARY KEY,
            team_name VARCHAR(255) REFERENCES teams(team_name),
            filename VARCHAR(255) NOT NULL,
            public_score FLOAT NOT NULL,
            private_score FLOAT NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key VARCHAR(255) PRIMARY KEY,
            value VARCHAR(255) NOT NULL
        )
        """)
        cursor.execute("INSERT INTO settings (key, value) VALUES ('show_private', 'false') ON CONFLICT (key) DO NOTHING")
    else:
        pass # 생략

    conn.commit()
    conn.close()

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def register_team(team_name: str, password: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    success = False
    
    if DATABASE_URL:
        cursor.execute("SELECT password_hash FROM teams WHERE team_name = %s", (team_name,))
    
    row = cursor.fetchone()
    
    if row:
        if row[0] == hash_password(password):
            success = True
    else:
        if DATABASE_URL:
            cursor.execute("INSERT INTO teams (team_name, password_hash) VALUES (%s, %s)", 
                           (team_name, hash_password(password)))
        conn.commit()
        success = True
        
    conn.close()
    return success

def add_submission(team_name: str, filename: str, public_score: float, private_score: float):
    conn = get_connection()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute(
            "INSERT INTO submissions (team_name, filename, public_score, private_score) VALUES (%s, %s, %s, %s)",
            (team_name, filename, public_score, private_score)
        )
    conn.commit()
    conn.close()

def get_daily_submission_count(team_name: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    today = date.today().isoformat()
    if DATABASE_URL:
        cursor.execute(
            "SELECT COUNT(*) FROM submissions WHERE team_name = %s AND DATE(submitted_at) = %s",
            (team_name, today)
        )
    row = cursor.fetchone()
    conn.close()
    return row[0]

def get_leaderboard(show_private: bool = False):
    conn = get_connection()
    
    if DATABASE_URL:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if show_private:
            query = """
            SELECT 
                t.team_name, 
                COALESCE(MAX(s.private_score), -1.0) as best_score,
                COALESCE(MAX(s.public_score), -1.0) as matching_public_score,
                COUNT(s.id) as total_submissions,
                MAX(s.submitted_at) as last_submission
            FROM teams t
            LEFT JOIN submissions s ON t.team_name = s.team_name
            GROUP BY t.team_name
            ORDER BY best_score DESC, total_submissions ASC, last_submission ASC
            """
        else:
            query = """
            SELECT 
                t.team_name, 
                COALESCE(MAX(s.public_score), -1.0) as best_score,
                COUNT(s.id) as total_submissions,
                MAX(s.submitted_at) as last_submission
            FROM teams t
            LEFT JOIN submissions s ON t.team_name = s.team_name
            GROUP BY t.team_name
            ORDER BY best_score DESC, total_submissions ASC, last_submission ASC
            """
    
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for idx, row in enumerate(rows):
        item = dict(row)
        if item.get("last_submission"):
            item["last_submission"] = str(item["last_submission"])[:16]
        item["rank"] = idx + 1 if item["best_score"] >= 0 else "-"
        result.append(item)
    return result

def get_team_submissions(team_name: str):
    conn = get_connection()
    if DATABASE_URL:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "SELECT submitted_at, public_score, private_score FROM submissions WHERE team_name = %s ORDER BY submitted_at DESC",
            (team_name,)
        )
    
    rows = cursor.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        item = dict(row)
        if item.get("submitted_at"):
            item["submitted_at"] = str(item["submitted_at"])[:16]
        result.append(item)
    return result

def get_setting(key: str) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("SELECT value FROM settings WHERE key = %s", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("UPDATE settings SET value = %s WHERE key = %s", (value, key))
    conn.commit()
    conn.close()
