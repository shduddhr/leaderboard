import sqlite3
import hashlib
import os
from datetime import datetime, date

DB_PATH = "leaderboard.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str, salt: str = "dna_ml_session_salt_2026") -> str:
    # 간이 비밀번호 해싱 (내장 hashlib 활용)
    return hashlib.sha256((password + salt).encode('utf-8')).hexdigest()

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. 팀 테이블 생성
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS teams (
        team_name TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    # 2. 제출 이력 테이블 생성
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_name TEXT NOT NULL,
        filename TEXT NOT NULL,
        public_score REAL NOT NULL,
        private_score REAL NOT NULL,
        submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (team_name) REFERENCES teams (team_name)
    )
    """)
    
    # 3. 설정 테이블 생성 (Private 공개 여부 등)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """)
    
    # 기본 설정값 입력 (Private 리더보드는 기본 비공개)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('show_private', 'false')")
    
    conn.commit()
    conn.close()
    print("데이터베이스 초기화 완료.")

def register_team(team_name: str, password: str) -> bool:
    team_name = team_name.strip()
    if not team_name or not password:
        return False
        
    conn = get_connection()
    cursor = conn.cursor()
    
    # 중복 체크
    cursor.execute("SELECT 1 FROM teams WHERE team_name = ?", (team_name,))
    if cursor.fetchone():
        conn.close()
        return False
        
    pwd_hash = hash_password(password)
    try:
        cursor.execute("INSERT INTO teams (team_name, password_hash) VALUES (?, ?)", (team_name, pwd_hash))
        conn.commit()
        success = True
    except sqlite3.Error:
        success = False
    finally:
        conn.close()
    return success

def verify_team(team_name: str, password: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    pwd_hash = hash_password(password)
    
    cursor.execute("SELECT 1 FROM teams WHERE team_name = ? AND password_hash = ?", (team_name, pwd_hash))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def add_submission(team_name: str, filename: str, public_score: float, private_score: float) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO submissions (team_name, filename, public_score, private_score) VALUES (?, ?, ?, ?)",
            (team_name, filename, public_score, private_score)
        )
        conn.commit()
        success = True
    except sqlite3.Error:
        success = False
    finally:
        conn.close()
    return success

def get_daily_submission_count(team_name: str) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    
    # 오늘 날짜 구하기 (YYYY-MM-DD)
    today = date.today().isoformat() # UTC 기준이 아닌 로컬 서버 기준
    
    # sqlite date 함수를 이용해 오늘 날짜의 제출물 필터링
    cursor.execute(
        "SELECT COUNT(*) FROM submissions WHERE team_name = ? AND date(submitted_at) = date(?)",
        (team_name, today)
    )
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_leaderboard(show_private: bool = False):
    conn = get_connection()
    cursor = conn.cursor()
    
    if show_private:
        # Private 점수 기준 최고점 및 정렬
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
        # Public 점수 기준 최고점 및 정렬
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
    
    # Row 객체를 일반 딕셔너리로 변환하여 반환
    result = []
    for idx, row in enumerate(rows):
        item = dict(row)
        item["rank"] = idx + 1 if item["best_score"] >= 0 else "-"
        result.append(item)
    return result

def get_team_submissions(team_name: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, filename, public_score, private_score, submitted_at FROM submissions WHERE team_name = ? ORDER BY submitted_at DESC",
        (team_name,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_setting(key: str) -> str:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def set_setting(key: str, value: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
