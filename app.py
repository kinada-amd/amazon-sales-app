import streamlit as st
import pandas as pd
from datetime import datetime
import io
import requests

# ページ設定
st.set_page_config(page_title="Amazon Analytics Pro", layout="wide")

# --- 【設定】外部サーバーのデータURL ---
URL_MASTER = "http://gigaplus.makeshop.jp/aimedia/data/master.xlsx"
URL_SALES = "http://gigaplus.makeshop.jp/aimedia/data/sales.xlsx"

# スタイリッシュなAmazonブランドカラーUI (視認性確保)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    /* 基本背景とテキスト */
    .stApp {
        background-color: #FFFFFF !important;
        color: #131921 !important;
        font-family: 'Inter', sans-serif !important;
    }

    /* サイドバー: Amazonダークネイビー */
    [data-testid="stSidebar"] {
        background-color: #131921 !important;
        border-right: 1px solid #232f3e !important;
    }

    /* メトリック（数字） */
    div[data-testid="stMetricValue"] {
        color: #131921 !important;
        font-size: 2.8rem !important;
        font-weight: 800 !important;
    }

    /* 検索ボックス */
    .stTextInput input {
        border-radius: 8px !important;
        border: 1px solid #888888 !important;
        padding: 10px 16px !important;
        color: #131921 !important;
    }
    
    /* 見出し類 */
    h1, h2, h3, p, label {
        color: #131921 !important;
    }
    
    .st-emotion-cache-1h1td79 h1 {
    color: #fff !important;
    }
    .st-emotion-cache-1h1td79 h3 {
    color: #fff !important;
    }
    </style>
    """, unsafe_allow_html=True)

# データ読み込み関数（キャッシュを活用して高速化）
@st.cache_data(ttl=300)  # 5分間キャッシュ
def load_data_from_url(url):
    response = requests.get(url)
    response.raise_for_status() # エラーがあれば停止
    return io.BytesIO(response.content)

try:
    # 自動読み込みの開始
    with st.spinner('Syncing latest performance data...'):
        master_data = load_data_from_url(URL_MASTER)
        sales_data = load_data_from_url(URL_SALES)
        
        df_master = pd.read_excel(master_data)
        df_sales = pd.read_excel(sales_data)

    # クレンジング処理
    df_sales.columns = df_sales.columns.str.strip()
    df_master.columns = df_master.columns.str.strip()
    for col in ['売上', '数量']:
        if col in df_sales.columns:
            df_sales[col] = pd.to_numeric(df_sales[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    # 日付の解釈
    df_sales['日付_dt'] = pd.to_datetime(df_sales['日付'], format='%Y年%m月', errors='coerce').fillna(
        pd.to_datetime(df_sales['日付'], errors='coerce')
    )
    df_sales['年月'] = df_sales['日付_dt'].dt.strftime('%Y-%m')

    # --- サイドバー操作パネル ---
    st.sidebar.title("Amazon Analytics Pro")
    all_months = sorted(df_sales['年月'].dropna().unique(), reverse=True)
    
    st.sidebar.subheader("Analytics Settings")
    month_a = st.sidebar.selectbox("分析対象月 (A)", all_months, index=0)
    month_b = st.sidebar.selectbox("比較対象月 (B)", all_months, index=min(1, len(all_months)-1))

    # マスタ結合と集計
    df_combined = pd.merge(df_sales, df_master, on='ASIN', how='left').fillna({'コード':'N/A', '正式品名':'不明', '規格':'-'})
    
    def get_summary(m):
        return df_combined[df_combined['年月'] == m].groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()

    df_sum_a = get_summary(month_a)
    df_sum_b = get_summary(month_b)

    # 比較用マージ
    comp_df = pd.merge(df_sum_a, df_sum_b[['ASIN', '売上', '数量']], on='ASIN', how='left', suffixes=('', '_b')).fillna(0)
    comp_df['増減率 (%)'] = ((comp_df['売上'] / comp_df['売上_b']) - 1) * 100
    comp_df.loc[comp_df['売上_b'] == 0, '増減率 (%)'] = 100.0

    # --- メインダッシュボード ---
    st.title("Sales Performance Overview")
    st.caption(f"Connected to Cloud Data | Comparing {month_a} vs {month_b}")

    # 検索・絞り込み機能
    search = st.text_input("Search by Product Name, Code, or ASIN", "").lower()
    if search:
        comp_df = comp_df[
            comp_df['正式品名'].str.lower().str.contains(search, na=False) | 
            comp_df['コード'].astype(str).str.contains(search, na=False) | 
            comp_df['ASIN'].str.lower().str.contains(search, na=False)
        ]

    # メトリック表示 (KPI)
    total_a, total_b = comp_df['売上'].sum(), comp_df['売上_b'].sum()
    growth_total = ((total_a / total_b) - 1) * 100 if total_b > 0 else 0

    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric(f"{month_a} Sales", f"¥{int(total_a):,}", f"{growth_total:+.1f}%")
    with m2:
        st.metric(f"{month_b} Sales", f"¥{int(total_b):,}")
    with m3:
        st.metric(f"{month_a} Units", f"{int(comp_df['数量'].sum()):,}")

    # データ詳細テーブル
    st.markdown("---")
    col_a, col_b = f"{month_a} Sales (A)", f"{month_b} Sales (B)"
    final = comp_df[['コード', '正式品名', '規格', '売上', '売上_b', '増減率 (%)', '数量', 'ASIN']]
    final.columns = ['コード', '正式品名', '規格', col_a, col_b, '増減率 (%)', '数量', 'ASIN']
    
    st.dataframe(
        final.style.format({
            col_a: '¥{:,.0f}', 
            col_b: '¥{:,.0f}', 
            '増減率 (%)': '{:+.1f}%', 
            '数量': '{:,.0f}'
        }),
        use_container_width=True, 
        height=650
    )

except Exception as e:
    st.error(f"Data Sync Error: {e}")
    st.info("Check if the URLs are accessible and the Excel format is correct.")