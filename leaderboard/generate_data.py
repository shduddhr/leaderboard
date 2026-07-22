import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

def generate_hardcore_churn_dataset(n_samples=100000, seed=42):
    np.random.seed(seed)
    
    # 1. Base ID
    customer_ids = [f"C{i:06d}" for i in range(1, n_samples + 1)]
    
    # 2. Base Features
    age = np.random.normal(40, 15, n_samples)
    age = np.clip(age, 18, 90).astype(int)
    
    # [Hardcore 1] MCAR Missing Value on Age (5%)
    mcar_mask = np.random.rand(n_samples) < 0.05
    age_float = age.astype(float)
    age_float[mcar_mask] = np.nan
    
    # [Hardcore 3] Temporal Features
    start_date = datetime(2018, 1, 1)
    end_date = datetime(2025, 12, 31)
    total_days = (end_date - start_date).days
    
    signup_days_offset = np.random.randint(0, total_days, n_samples)
    signup_dates = [start_date + timedelta(days=int(d)) for d in signup_days_offset]
    
    # Last_Login_Date (between signup and 2026-07-20)
    eval_date = datetime(2026, 7, 20)
    last_login_dates = []
    tenure_days = []
    
    for sd in signup_dates:
        t_days = (eval_date - sd).days
        tenure_days.append(t_days)
        
        # Generate days since last login (exponential distribution)
        dsl = int(np.random.exponential(scale=60))
        dsl = min(dsl, t_days) # Can't be before signup
        
        lld = eval_date - timedelta(days=dsl)
        last_login_dates.append(lld.strftime("%Y-%m-%d"))
        
    signup_dates_str = [d.strftime("%Y-%m-%d") for d in signup_dates]
    tenure_days = np.array(tenure_days)
    
    # [Hardcore 2] Dirty Categorical Data: Payment Method
    base_payment = np.random.choice(['Credit Card', 'Bank Transfer', 'E-Wallet'], p=[0.5, 0.3, 0.2], size=n_samples)
    
    dirty_payment = []
    for p in base_payment:
        if p == 'Credit Card':
            dirty_payment.append(np.random.choice(['Credit Card', 'credit_card', 'CreditCard', 'CREDIT CARD'], p=[0.7, 0.1, 0.1, 0.1]))
        elif p == 'Bank Transfer':
            dirty_payment.append(np.random.choice(['Bank Transfer', 'bank transfer', 'BankTransfer'], p=[0.8, 0.1, 0.1]))
        else:
            dirty_payment.append(p)
            
    # [Hardcore 1 & 4] Monthly Bill (MAR) & Outliers
    monthly_bill = np.random.normal(70, 20, n_samples)
    monthly_bill = np.clip(monthly_bill, 10, 250)
    
    # Inject MAR: 'Bank Transfer' has higher chance of missing Monthly_Bill
    mar_mask = (base_payment == 'Bank Transfer') & (np.random.rand(n_samples) < 0.15)
    mar_mask |= (np.random.rand(n_samples) < 0.02) # random baseline missing
    monthly_bill[mar_mask] = np.nan
    
    # Outliers for Monthly Bill
    outlier_mask = np.random.rand(n_samples) < 0.005
    monthly_bill[outlier_mask] = 9999.99
    
    # [Hardcore 4] Total Usage GB with Outliers
    total_usage = np.random.normal(300, 150, n_samples)
    total_usage = np.clip(total_usage, 0, 2000)
    outlier_usage_mask = np.random.rand(n_samples) < 0.005
    total_usage[outlier_usage_mask] = -999.0
    
    # Device Type
    device_type = np.random.choice(['iOS', 'Android', 'PC'], p=[0.4, 0.5, 0.1], size=n_samples)
    
    # Discount Applied
    discount_applied = np.random.rand(n_samples) < 0.3
    
    # Support Calls
    support_calls = np.random.poisson(lam=1.5, size=n_samples)
    
    # Customer Satisfaction (Base 1-5)
    satisfaction_base = 5.0 - (support_calls * 0.5) - (device_type == 'PC') * 1.0 + np.random.normal(0, 0.5, n_samples)
    satisfaction = np.clip(np.round(satisfaction_base), 1, 5).astype(int)
    
    # 3. [Hardcore 5] Calculate Churn Probability (Non-linear & Complex)
    # Base logit for low churn rate (~8%)
    logits = -2.5 
    
    # Age factor: young users churn slightly more
    logits += (40 - age) / 50.0 
    
    # PC users hate the service (bad UX)
    logits += (device_type == 'PC') * 1.2
    
    # Support calls increase churn
    logits += (support_calls * 0.3)
    
    # INTERACTION 1: Discount Cliff
    # If discount applied, churn drops. BUT if tenure is around 365 days, churn spikes.
    logits -= discount_applied * 1.5 
    cliff_mask = discount_applied & (tenure_days >= 330) & (tenure_days <= 390)
    logits += cliff_mask * 4.0 # Huge spike
    
    # INTERACTION 2: Lock-in Effect
    # If tenure > 3 years (1095 days), support calls don't matter as much
    lockin_mask = (tenure_days > 1095)
    logits -= lockin_mask * (support_calls * 0.25) 
    
    # Frustrated newbie effect
    frustrated_newbie = (tenure_days < 180) & (support_calls >= 2)
    logits += frustrated_newbie * 2.0
    
    # Add random noise
    logits += np.random.normal(0, 0.8, n_samples)
    
    # Convert to probabilities
    probs = 1 / (1 + np.exp(-logits))
    
    # Calculate binary churn
    churn = (np.random.rand(n_samples) < probs).astype(int)
    
    # [Hardcore 1] MNAR: Satisfaction is Missing Not At Random
    # People who are highly dissatisfied OR actually churned often don't respond to surveys
    mnar_mask = (churn == 1) & (np.random.rand(n_samples) < 0.6)
    mnar_mask |= (satisfaction <= 2) & (np.random.rand(n_samples) < 0.3)
    satisfaction_float = satisfaction.astype(float)
    satisfaction_float[mnar_mask] = np.nan
    
    # Create DataFrame
    df = pd.DataFrame({
        'Customer_ID': customer_ids,
        'Age': age_float,
        'Signup_Date': signup_dates_str,
        'Last_Login_Date': last_login_dates,
        'Payment_Method': dirty_payment,
        'Monthly_Bill': monthly_bill,
        'Total_Usage_GB': total_usage,
        'Customer_Satisfaction': satisfaction_float,
        'Device_Type': device_type,
        'Discount_Applied': discount_applied,
        'Support_Calls': support_calls,
        'Churn': churn
    })
    
    print(f"Dataset generated. Shape: {df.shape}")
    print(f"Overall Churn Rate: {df['Churn'].mean():.4f}")
    print(f"Missing Values:\n{df.isnull().sum()}")
    
    # 4. Split data
    # Test set gets 30% of data randomly
    test_mask = np.random.rand(n_samples) < 0.3
    
    train_df = df[~test_mask].copy()
    
    # test_df는 Churn 정답 제거
    test_df = df[test_mask].drop(columns=['Churn']).copy()
    
    # solution_df는 test_mask에 해당하는 행만 가지고, Churn 정답 유지
    solution_df = df[test_mask][['Customer_ID', 'Churn']].copy()
    
    # Public 30%, Private 70% 비율로 Usage 컬럼 부여
    usage_mask = np.random.rand(len(solution_df)) < 0.3
    solution_df['Usage'] = np.where(usage_mask, 'public', 'private')
    
    print(f"Train size: {len(train_df)}")
    print(f"Test size: {len(test_df)}")
    print(f"Train Churn Rate: {train_df['Churn'].mean():.4f}")
    print(f"Solution Public ratio: {(solution_df['Usage'] == 'public').mean():.4f}")
    
    # 5. Save to CSV
    os.makedirs('data', exist_ok=True)
    train_df.to_csv('data/train.csv', index=False)
    test_df.to_csv('data/test.csv', index=False)
    solution_df.to_csv('data/solution.csv', index=False)
    print("Files saved successfully to 'data/' directory.")

if __name__ == "__main__":
    generate_hardcore_churn_dataset(100000)
