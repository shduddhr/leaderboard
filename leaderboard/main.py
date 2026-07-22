import os
import shutil
import uuid
import pandas as pd
from fastapi import FastAPI, Request, Form, File, UploadFile, Depends, HTTPException, status, Response, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sklearn.metrics import f1_score
from typing import Optional
from datetime import datetime

import database

# DB 초기화
database.init_db()

app = FastAPI(title="D&A ML Session Leaderboard")

# 설정 변수 (사용자가 제출 횟수 제한을 쉽게 조절 가능)
MAX_DAILY_SUBMISSIONS = 5
ADMIN_PASSWORD = "dna_ml_admin_secret_2026" # 관리자용 비밀키

# 업로드 폴더 생성
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 템플릿 및 정적 파일 설정
templates = Jinja2Templates(directory="templates")
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# 정답(Solution) 데이터 로드 및 검증용
SOLUTION_PATH = "data/solution.csv"
if not os.path.exists(SOLUTION_PATH):
    raise FileNotFoundError(f"정답 파일 {SOLUTION_PATH}이 존재하지 않습니다. 먼저 generate_data.py를 실행하세요.")

solution_df = pd.read_csv(SOLUTION_PATH)
solution_df = solution_df.sort_values(by="Customer_ID").reset_index(drop=True)

# 인메모리 세션 스토어 (간이 세션)
SESSIONS = {}

def get_current_team(session_id: Optional[str] = Cookie(None)) -> Optional[str]:
    if session_id and session_id in SESSIONS:
        return SESSIONS[session_id]
    return None

def calculate_scores(submitted_df: pd.DataFrame) -> tuple[float, float]:
    """
    제출된 데이터프레임과 정답 데이터프레임을 비교하여 Public/Private F1-Score를 계산합니다.
    """
    # 컬럼 표준화
    submitted_df.columns = [c.strip() for c in submitted_df.columns]
    
    # Target 컬럼 찾기 (Churn, Predict, target 등 유연하게 대처)
    predict_col = None
    for col in ["Churn", "Predict", "target", "predict"]:
        if col in submitted_df.columns:
            predict_col = col
            break
            
    if not predict_col:
        # 첫 번째 컬럼이 Customer_ID일 확률이 높으므로 두 번째 컬럼을 예측값으로 간주
        predict_col = submitted_df.columns[1]
        
    # Customer_ID 기준으로 정렬 및 조인
    submitted_df = submitted_df.sort_values(by="Customer_ID").reset_index(drop=True)
    
    # 필요한 컬럼만 추출하여 안전하게 병합
    sub_subset = submitted_df[["Customer_ID", predict_col]].copy()
    sub_subset.columns = ["Customer_ID", "Churn_pred"]
    
    merged = pd.merge(solution_df, sub_subset, on="Customer_ID")
    
    # F1-Score는 Macro F1-Score를 사용
    # Public 스코어 계산
    public_mask = merged["Usage"] == "public"
    public_true = merged.loc[public_mask, "Churn"].astype(int)
    public_pred = merged.loc[public_mask, "Churn_pred"].astype(int)
    public_f1 = f1_score(public_true, public_pred, average="macro")
    
    # Private 스코어 계산
    private_mask = merged["Usage"] == "private"
    private_true = merged.loc[private_mask, "Churn"].astype(int)
    private_pred = merged.loc[private_mask, "Churn_pred"].astype(int)
    private_f1 = f1_score(private_true, private_pred, average="macro")
    
    return float(public_f1), float(private_f1)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, team_name: Optional[str] = Depends(get_current_team)):
    show_private_str = database.get_setting("show_private")
    show_private = show_private_str == "true"
    
    # 리더보드 데이터 가져오기
    leaderboard_data = database.get_leaderboard(show_private=show_private)
    
    # 로그인된 팀의 남은 제출 횟수 계산
    remaining_submissions = None
    team_submissions = []
    if team_name:
        daily_count = database.get_daily_submission_count(team_name)
        remaining_submissions = max(0, MAX_DAILY_SUBMISSIONS - daily_count)
        team_submissions = database.get_team_submissions(team_name)
        
    return templates.TemplateResponse("index.html", {
        "request": request,
        "team_name": team_name,
        "leaderboard": leaderboard_data,
        "remaining_submissions": remaining_submissions,
        "max_submissions": MAX_DAILY_SUBMISSIONS,
        "submissions": team_submissions,
        "show_private": show_private
    })

@app.post("/register")
async def register(team_name: str = Form(...), password: str = Form(...)):
    team_name = team_name.strip()
    if not team_name or not password:
        return RedirectResponse(url="/?error=invalid_input", status_code=status.HTTP_303_SEE_OTHER)
        
    if len(team_name) < 2 or len(team_name) > 20:
        return RedirectResponse(url="/?error=name_length", status_code=status.HTTP_303_SEE_OTHER)
        
    success = database.register_team(team_name, password)
    if success:
        # 자동 로그인 처리
        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = team_name
        response = RedirectResponse(url="/?msg=registered", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="session_id", value=session_id, max_age=7*24*3600, httponly=True)
        return response
    else:
        return RedirectResponse(url="/?error=exists", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/login")
async def login(team_name: str = Form(...), password: str = Form(...)):
    team_name = team_name.strip()
    success = database.verify_team(team_name, password)
    if success:
        session_id = str(uuid.uuid4())
        SESSIONS[session_id] = team_name
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="session_id", value=session_id, max_age=7*24*3600, httponly=True)
        return response
    else:
        return RedirectResponse(url="/?error=login_failed", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
async def logout(response: Response, session_id: Optional[str] = Cookie(None)):
    if session_id and session_id in SESSIONS:
        del SESSIONS[session_id]
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="session_id")
    return response

@app.post("/submit")
async def submit(
    request: Request,
    file: UploadFile = File(...),
    team_name: Optional[str] = Depends(get_current_team)
):
    if not team_name:
        return RedirectResponse(url="/?error=unauthorized", status_code=status.HTTP_303_SEE_OTHER)
        
    # 제출 횟수 제한 체크
    daily_count = database.get_daily_submission_count(team_name)
    if daily_count >= MAX_DAILY_SUBMISSIONS:
        return RedirectResponse(url="/?error=limit_exceeded", status_code=status.HTTP_303_SEE_OTHER)
        
    if not file.filename.endswith('.csv'):
        return RedirectResponse(url="/?error=not_csv", status_code=status.HTTP_303_SEE_OTHER)
        
    # 파일 임시 저장 및 검증
    temp_filename = f"{team_name}_{int(datetime.now().timestamp())}_{file.filename}"
    temp_path = os.path.join(UPLOAD_DIR, temp_filename)
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 판다스로 파일 읽기
        sub_df = pd.read_csv(temp_path)
        
        # 기본 형식 검증
        if "Customer_ID" not in sub_df.columns:
            os.remove(temp_path)
            return RedirectResponse(url="/?error=missing_id", status_code=status.HTTP_303_SEE_OTHER)
            
        if len(sub_df) != len(solution_df):
            os.remove(temp_path)
            return RedirectResponse(url="/?error=row_count_mismatch", status_code=status.HTTP_303_SEE_OTHER)
            
        # Customer_ID 집합 일치 여부 체크
        sub_ids = set(sub_df["Customer_ID"])
        sol_ids = set(solution_df["Customer_ID"])
        if sub_ids != sol_ids:
            os.remove(temp_path)
            return RedirectResponse(url="/?error=id_mismatch", status_code=status.HTTP_303_SEE_OTHER)
            
        # 점수 계산
        public_f1, private_f1 = calculate_scores(sub_df)
        
        # DB에 저장
        database.add_submission(team_name, file.filename, public_f1, private_f1)
        return RedirectResponse(url="/?msg=submitted", status_code=status.HTTP_303_SEE_OTHER)
        
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        print(f"제출 중 오류 발생: {e}")
        return RedirectResponse(url="/?error=invalid_file", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/admin/toggle-private")
async def toggle_private(admin_pass: str = Form(...)):
    if admin_pass != ADMIN_PASSWORD:
        return RedirectResponse(url="/?error=admin_failed", status_code=status.HTTP_303_SEE_OTHER)
        
    current = database.get_setting("show_private")
    new_val = "true" if current == "false" else "false"
    database.set_setting("show_private", new_val)
    
    return RedirectResponse(url="/?msg=admin_success", status_code=status.HTTP_303_SEE_OTHER)

# 에러 메시지 맵핑을 위한 전역 컨텍스트를 프론트엔드가 참고할 수 있도록 함
@app.get("/leaderboard/data")
async def get_raw_leaderboard():
    show_private = database.get_setting("show_private") == "true"
    return JSONResponse(content={
        "show_private": show_private,
        "leaderboard": database.get_leaderboard(show_private=show_private)
    })
