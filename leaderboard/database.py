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
        conn.commit()
        
        # 컬럼 추가 (기존 테이블 마이그레이션)
        try:
            cursor.execute("ALTER TABLE submissions ADD COLUMN is_selected BOOLEAN DEFAULT FALSE")
            conn.commit()
        except Exception:
            conn.rollback()
            
        cursor.execute("INSERT INTO settings (key, value) VALUES ('show_private', 'false') ON CONFLICT (key) DO NOTHING")
        cursor.execute("INSERT INTO settings (key, value) VALUES ('submissions_frozen', 'false') ON CONFLICT (key) DO NOTHING")
        cursor.execute("INSERT INTO settings (key, value) VALUES ('max_daily_submissions', '5') ON CONFLICT (key) DO NOTHING")
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

def verify_team(team_name: str, password: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("SELECT password_hash FROM teams WHERE team_name = %s", (team_name,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row[0] == hash_password(password):
        return True
    return False

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

def get_leaderboard(show_private: bool = False, is_admin: bool = False):
    conn = get_connection()
    if DATABASE_URL:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
    else:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
    # Get all teams
    cursor.execute("SELECT team_name FROM teams WHERE team_name != 'admin' AND team_name != 'ADMIN'")
    teams = cursor.fetchall()
    
    # Get all submissions
    cursor.execute("SELECT * FROM submissions")
    all_subs = cursor.fetchall()
    
    leaderboard = []
    
    for team in teams:
        tname = team['team_name']
        t_subs = [s for s in all_subs if s['team_name'] == tname]
        
        if not t_subs:
            continue
            
        total_subs = len(t_subs)
        last_sub_time = max(s['submitted_at'] for s in t_subs)
        
        best_public = max(t_subs, key=lambda x: x['public_score'])
        best_private = max(t_subs, key=lambda x: x['private_score'])
        
        if is_admin:
            leaderboard.append({
                'team_name': tname,
                'public_score': best_public['public_score'],
                'public_filename': best_public['filename'],
                'private_score': best_private['private_score'],
                'private_filename': best_private['filename'],
                'total_submissions': total_subs,
                'last_submission': str(last_sub_time)
            })
        elif show_private:
            # Private 모드 (최종 산출)
            selected_subs = [s for s in t_subs if s.get('is_selected')]
            if not selected_subs:
                # 선택된 게 없으면 Public 상위 최대 4개 자동 선택
                t_subs_sorted = sorted(t_subs, key=lambda x: x['public_score'], reverse=True)
                selected_subs = t_subs_sorted[:4]
                
            final_best = max(selected_subs, key=lambda x: x['private_score'])
            leaderboard.append({
                'team_name': tname,
                'best_score': final_best['private_score'],
                'public_score': best_public['public_score'],
                'total_submissions': total_subs,
                'last_submission': str(last_sub_time)
            })
        else:
            # Public 모드 (진행 중)
            leaderboard.append({
                'team_name': tname,
                'best_score': best_public['public_score'],
                'public_score': best_public['public_score'],
                'total_submissions': total_subs,
                'last_submission': str(last_sub_time)
            })
            
    conn.close()
    
    # Public 랭크 사전 계산 (Top 2 뱃지용)
    if not is_admin:
        temp_sort = sorted(leaderboard, key=lambda x: (-x['public_score'], x['total_submissions'], x['last_submission']))
        p_rank = 1
        for i, row in enumerate(temp_sort):
            if i > 0 and row['public_score'] == temp_sort[i-1]['public_score'] and row['total_submissions'] == temp_sort[i-1]['total_submissions']:
                row['public_rank'] = temp_sort[i-1]['public_rank']
            else:
                row['public_rank'] = p_rank
            p_rank += 1
    
    # 최종 정렬 및 랭크 부여
    if is_admin:
        leaderboard.sort(key=lambda x: (-x['private_score'], x['total_submissions']))
    else:
        leaderboard.sort(key=lambda x: (-x['best_score'], x['total_submissions'], x['last_submission']))
        
    rank = 1
    for i, row in enumerate(leaderboard):
        if is_admin:
            if i > 0 and row['private_score'] == leaderboard[i-1]['private_score'] and row['total_submissions'] == leaderboard[i-1]['total_submissions']:
                row['rank'] = leaderboard[i-1]['rank']
            else:
                row['rank'] = rank
        else:
            if i > 0 and row['best_score'] == leaderboard[i-1]['best_score'] and row['total_submissions'] == leaderboard[i-1]['total_submissions']:
                row['rank'] = leaderboard[i-1]['rank']
            else:
                row['rank'] = rank
        rank += 1
        
    return leaderboard

def toggle_submission_selection(team_name: str, sub_id: int) -> tuple[bool, str]:
    conn = get_connection()
    if DATABASE_URL:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
    else:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
    cursor.execute("SELECT * FROM submissions WHERE id = %s AND team_name = %s", (sub_id, team_name))
    sub = cursor.fetchone()
    
    if not sub:
        conn.close()
        return False, "제출 기록을 찾을 수 없습니다."
        
    current_status = sub['is_selected']
    
    if not current_status:
        # 선택하려는 경우 (4개 제한 확인)
        cursor.execute("SELECT COUNT(*) as cnt FROM submissions WHERE team_name = %s AND is_selected = TRUE", (team_name,))
        cnt = cursor.fetchone()['cnt']
        if cnt >= 4:
            conn.close()
            return False, "최대 4개까지만 선택할 수 있습니다."
            
    # 토글 실행
    new_status = not current_status
    cursor.execute("UPDATE submissions SET is_selected = %s WHERE id = %s", (new_status, sub_id))
    conn.commit()
    conn.close()
    return True, "선택이 변경되었습니다."

def get_team_submissions(team_name: str):
    conn = get_connection()
    if DATABASE_URL:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "SELECT id, submitted_at, public_score, private_score, is_selected FROM submissions WHERE team_name = %s ORDER BY submitted_at DESC",
            (team_name,)
        )
    else:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, submitted_at, public_score, private_score, is_selected FROM submissions WHERE team_name = ? ORDER BY submitted_at DESC",
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
        
    # 개인 제출 이력 중 Public 점수가 가장 높은 1위, 2위를 찾아서 뱃지를 달아주기 위함
    # 점수가 높은 순으로 정렬 후 1, 2위에 표시 (동점 처리 포함)
    sorted_subs = sorted(result, key=lambda x: x['public_score'], reverse=True)
    current_rank = 1
    for i, sub in enumerate(sorted_subs):
        if i > 0 and sub['public_score'] < sorted_subs[i-1]['public_score']:
            current_rank = i + 1
            
        if current_rank <= 2:
            sub['personal_public_rank'] = current_rank
            
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

def delete_team_submissions(team_name: str):
    conn = get_connection()
    cursor = conn.cursor()
    if DATABASE_URL:
        cursor.execute("DELETE FROM submissions WHERE team_name = %s", (team_name,))
    conn.commit()
    conn.close()
