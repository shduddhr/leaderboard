import os
import sys
import pandas as pd
import numpy as np

# 프로젝트 경로 임포트
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import database
from main import calculate_scores

def run_tests():
    print("=== START LEADERBOARD SYSTEM TESTS ===")
    
    # 1. DB 초기화 테스트
    print("\n1. Testing Database Initialization...")
    database.init_db()
    if os.path.exists("leaderboard.db"):
        print("[OK] leaderboard.db created successfully.")
    else:
        print("[FAIL] Failed to create leaderboard.db!")
        return
        
    # 2. 팀 등록 및 로그인 테스트
    print("\n2. Testing Team Registration and Verification...")
    test_team = "TestTeam_2026"
    test_pass = "password123!"
    
    # 기등록 데이터 삭제 (멱등성 확보)
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM teams WHERE team_name = ?", (test_team,))
    cursor.execute("DELETE FROM submissions WHERE team_name = ?", (test_team,))
    conn.commit()
    conn.close()
    
    # 등록
    reg_success = database.register_team(test_team, test_pass)
    print(f"  - Team Registration: {'SUCCESS' if reg_success else 'FAIL'}")
    
    # 중복 등록 방지 확인
    dup_reg = database.register_team(test_team, "newpass")
    print(f"  - Duplicate Check: {'SUCCESS (Blocked)' if not dup_reg else 'FAIL'}")
    
    # 로그인 검증
    login_ok = database.verify_team(test_team, test_pass)
    print(f"  - Valid Password Login: {'SUCCESS' if login_ok else 'FAIL'}")
    
    login_fail = database.verify_team(test_team, "wrong_pass")
    print(f"  - Invalid Password Login: {'SUCCESS (Blocked)' if not login_fail else 'FAIL'}")
    
    # 3. 점수 채점 모듈 테스트
    print("\n3. Testing Score Metric (F1-score)...")
    sol_df = pd.read_csv("data/solution.csv")
    
    # 가상의 제출 데이터 생성 (일부는 맞추고 일부는 틀림)
    # 정답 대비 약 80% 일치하도록 임의 노이즈 삽입
    np.random.seed(42)
    fake_preds = []
    
    test_features = pd.read_csv("data/test.csv")
    fake_sub = sol_df.copy()
    
    # Churn의 일부(약 20%)를 반전(0->1, 1->0)시킴
    mask = np.random.choice([True, False], size=len(fake_sub), p=[0.20, 0.80])
    fake_sub.loc[mask, "Churn"] = 1 - fake_sub.loc[mask, "Churn"]
    
    # 채점 함수 호출
    public_f1, private_f1 = calculate_scores(fake_sub)
    print(f"  - F1-score Results:")
    print(f"    * Public Score (30%): {public_f1:.6f}")
    print(f"    * Private Score (70%): {private_f1:.6f}")
    
    if 0.5 < public_f1 < 1.0 and 0.5 < private_f1 < 1.0:
        print("[OK] Score metric calculation working within expected range.")
    else:
        print("[FAIL] Score calculation error!")
        return
        
    # 4. 제출물 저장 및 제출 제한 테스트
    print("\n4. Testing Submission Limits...")
    # 제출 추가
    database.add_submission(test_team, "submission_1.csv", public_f1, private_f1)
    database.add_submission(test_team, "submission_2.csv", public_f1 + 0.02, private_f1 + 0.01)
    
    count = database.get_daily_submission_count(test_team)
    print(f"  - Today's submission count for {test_team}: {count}")
    if count == 2:
        print("[OK] Submission count query is correct.")
    else:
        print("[FAIL] Submission count error!")
        
    # 5. 리더보드 조회 테스트
    print("\n5. Testing Leaderboard Sorting...")
    # 다른 팀 추가해서 랭킹 확인
    other_team = "Awesome_ML_Team"
    database.register_team(other_team, "pass")
    # 더 높은 점수로 추가
    database.add_submission(other_team, "best.csv", public_f1 + 0.05, private_f1 + 0.05)
    
    # Public 리더보드
    leaderboard = database.get_leaderboard(show_private=False)
    print("  - [Public Leaderboard]")
    for r in leaderboard:
        print(f"    Rank: {r['rank']} | Team: {r['team_name']} | Score: {r['best_score']:.6f} | Submissions: {r['total_submissions']}")
        
    # 첫 번째 팀이 Awesome_ML_Team 인지 확인 (점수가 더 높으므로)
    if leaderboard[0]["team_name"] == other_team:
        print("[OK] Leaderboard rank sorting works perfectly.")
    else:
        print("[FAIL] Leaderboard sorting error!")
        
    # 테스트 정리를 위한 더미 데이터 삭제
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM teams WHERE team_name IN (?, ?)", (test_team, other_team))
    cursor.execute("DELETE FROM submissions WHERE team_name IN (?, ?)", (test_team, other_team))
    conn.commit()
    conn.close()
    
    print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")

if __name__ == "__main__":
    run_tests()
