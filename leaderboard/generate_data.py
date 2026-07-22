import os
import numpy as np
import pandas as pd

def generate_churn_dataset(n_samples=100000, seed=42):
    np.random.seed(seed)
    
    # 1. 고유 ID 생성
    customer_ids = [f"C{i:06d}" for i in range(1, n_samples + 1)]
    
    # 2. 기초 피처 생성
    # 나이: 18~75세 (평균 40, 표준편차 12)
    age = np.random.normal(loc=40, scale=12, size=n_samples).astype(int)
    age = np.clip(age, 18, 75)
    
    # 성별
    gender = np.random.choice(["Male", "Female"], size=n_samples, p=[0.49, 0.51])
    
    # 구독 유형: Basic(50%), Standard(35%), Premium(15%)
    sub_types = ["Basic", "Standard", "Premium"]
    subscription_type = np.random.choice(sub_types, size=n_samples, p=[0.50, 0.35, 0.15])
    
    # 계약 기간: Month-to-month(55%), One_year(30%), Two_year(15%)
    contract_lengths = ["Month-to-month", "One_year", "Two_year"]
    contract_length = np.random.choice(contract_lengths, size=n_samples, p=[0.55, 0.30, 0.15])
    
    # 결제 수단
    pay_methods = ["Credit_card", "Bank_transfer", "Paypal"]
    payment_method = np.random.choice(pay_methods, size=n_samples, p=[0.40, 0.35, 0.25])
    
    # 데이터 사용량 (GB): 요금제에 따른 차이 부여
    total_usage_gb = np.zeros(n_samples)
    for i, sub in enumerate(subscription_type):
        if sub == "Basic":
            total_usage_gb[i] = np.random.gamma(shape=3, scale=50) # 평균 150GB
        elif sub == "Standard":
            total_usage_gb[i] = np.random.gamma(shape=5, scale=80) # 평균 400GB
        else: # Premium
            total_usage_gb[i] = np.random.gamma(shape=8, scale=100) # 평균 800GB
    total_usage_gb = np.clip(total_usage_gb, 10, 1500).astype(int)
    
    # 고객 센터 문의 횟수 (Poisson 분포, 평균 1.8회)
    support_calls = np.random.poisson(lam=1.8, size=n_samples)
    support_calls = np.clip(support_calls, 0, 10)
    
    # 마지막 활성 경과 일수
    last_active_days_ago = np.random.exponential(scale=7, size=n_samples).astype(int)
    last_active_days_ago = np.clip(last_active_days_ago, 0, 30)
    
    # 월 요금 (Monthly Bill): 요금제별 기본료 + 사용량 비례 + 노이즈
    monthly_bill = np.zeros(n_samples)
    for i, sub in enumerate(subscription_type):
        if sub == "Basic":
            base = 15.0
            usage_coeff = 0.05
        elif sub == "Standard":
            base = 40.0
            usage_coeff = 0.03
        else: # Premium
            base = 80.0
            usage_coeff = 0.015
        monthly_bill[i] = base + (total_usage_gb[i] * usage_coeff) + np.random.normal(0, 3)
    monthly_bill = np.round(np.clip(monthly_bill, 10, 150), 2)
    
    # 3. Churn (해지 여부, Target) 생성 로직
    # 로지스틱 함수에 들어갈 선형 조합 z 계산 (현실적인 요인 반영)
    z = -1.8 # 기본 절편 (해지율 조절용)
    
    # Month-to-month 계약은 해지 위험이 높음
    z += 1.2 * (contract_length == "Month-to-month")
    z -= 0.8 * (contract_length == "Two_year")
    
    # 고객센터 문의가 많을수록 불만족으로 해지 확률 증가
    z += 0.45 * support_calls
    
    # 오랫동안 접속하지 않았을수록 해지 확률 증가
    z += 0.06 * last_active_days_ago
    
    # 나이가 많을수록 락인(Lock-in) 효과로 해지 확률 약간 감소
    z -= 0.015 * age
    
    # 프리미엄 요금제를 쓰는데 사용량이 너무 적으면 가성비 불만족으로 해지 확률 증가
    z += 0.8 * ((subscription_type == "Premium") & (total_usage_gb < 250))
    
    # 요금 납부액이 비쌀수록 해지 확률 약간 증가
    z += 0.005 * monthly_bill
    
    # 시그모이드 함수를 거쳐 확률 계산
    churn_prob = 1 / (1 + np.exp(-z))
    
    # 이항 분포를 통해 최종 Churn 라벨링 (0 또는 1)
    churn = np.random.binomial(1, churn_prob)
    
    # 데이터프레임 구축
    df = pd.DataFrame({
        "Customer_ID": customer_ids,
        "Age": age,
        "Gender": gender,
        "Subscription_Type": subscription_type,
        "Contract_Length": contract_length,
        "Payment_Method": payment_method,
        "Monthly_Bill": monthly_bill,
        "Total_Usage_GB": total_usage_gb,
        "Support_Calls": support_calls,
        "Last_Active_Days_Ago": last_active_days_ago,
        "Churn": churn
    })
    
    return df

def main():
    print("합성 데이터 생성을 시작합니다...")
    df = generate_churn_dataset(n_samples=100000, seed=42)
    
    churn_rate = df["Churn"].mean() * 100
    print(f"전체 해지율(Churn Rate): {churn_rate:.2f}%")
    print(df["Churn"].value_counts())
    
    # 데이터 폴더 생성
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    
    # 70,000행을 Train 셋으로
    train_df = df.iloc[:70000].copy()
    # 30,000행을 Test 셋으로 (참가자용: Target Churn 제외)
    test_df = df.iloc[70000:].copy()
    test_features = test_df.drop(columns=["Churn"]).copy()
    
    # 서버 채점용 Solution 셋 (Target Churn 포함 + Public/Private 구분)
    solution_df = test_df[["Customer_ID", "Churn"]].copy()
    
    # 30%를 public, 70%를 private으로 무작위 배정
    np.random.seed(2026) # 구분용 시드 고정
    usages = np.random.choice(["public", "private"], size=len(solution_df), p=[0.30, 0.70])
    solution_df["Usage"] = usages
    
    # 파일 저장
    train_path = os.path.join(data_dir, "train.csv")
    test_path = os.path.join(data_dir, "test.csv")
    solution_path = os.path.join(data_dir, "solution.csv")
    
    train_df.to_csv(train_path, index=False)
    test_features.to_csv(test_path, index=False)
    solution_df.to_csv(solution_path, index=False)
    
    print(f"데이터셋 저장 완료:")
    print(f"  - Train: {train_path} ({len(train_df)} rows)")
    print(f"  - Test: {test_path} ({len(test_features)} rows)")
    print(f"  - Solution: {solution_path} ({len(solution_df)} rows)")
    print(f"    (Public: {sum(usages == 'public')}행, Private: {sum(usages == 'private')}행)")

if __name__ == "__main__":
    main()
