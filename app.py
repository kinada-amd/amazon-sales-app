import streamlit as st
import pandas as pd
from datetime import datetime
import io
import requests
import plotly.graph_objects as go

# 1. ページ設定（ライトモード固定のための設定含む）
st.set_page_config(page_title="Amazon Analytics Pro", layout="wide", initial_sidebar_state="expanded")

# --- 【URL設定】 ---
URL_MASTER = "http://gigaplus.makeshop.jp/aimedia/data/master.xlsx"
URL_SALES = "http://gigaplus.makeshop.jp/aimedia/data/sales.xlsx"

# 2. スタイル設定（Amazonトーン＆マナー）
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    .stApp { background-color: #FFFFFF !important; color: #131921 !important; font-family: 'Inter', sans-serif !important; }
    [data-testid="stSidebar"] { background-color: #131921 !important; border-right: 1px solid #232f3e !important; }
    [data-testid="stSidebar"] * { color: #FFFFFF !important; }
    div[data-testid="stMetricValue"] { color: #131921 !important; font-weight: 800 !important; font-size: 2.2rem !important; }
    .stDataFrame { border: 1px solid #D5D9D9 !important; border-radius: 4px !important; }
    h1, h2, h3 { color: #131921 !important; font-weight: 700 !important; }
    /* 比較モード時のアクセント */
    .compare-label { color: #FF9900 !important; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=300)
def load_data_from_url(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return io.BytesIO(response.content)

try:
    with st.spinner('Synchronizing with Amazon Performance Data...'):
        df_master = pd.read_excel(load_data_from_url(URL_MASTER))
        df_sales = pd.read_excel(load_data_from_url(URL_SALES))

    # --- データ処理 ---
    df_sales.columns = df_sales.columns.str.strip()
    df_master.columns = df_master.columns.str.strip()
    for col in ['売上', '数量']:
        if col in df_sales.columns:
            df_sales[col] = pd.to_numeric(df_sales[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    df_sales['日付_dt'] = pd.to_datetime(df_sales['日付'], format='%Y年%m月', errors='coerce').fillna(
        pd.to_datetime(df_sales['日付'], errors='coerce')
    )
    df_sales['年月'] = df_sales['日付_dt'].dt.strftime('%Y-%m')
    all_months = sorted(df_sales['年月'].dropna().unique(), reverse=True)

    # --- サイドバー設定 ---
    st.sidebar.title("Amazon Analytics")
    st.sidebar.markdown("---")
    
    st.sidebar.subheader("Period Selection")
    start_month = st.sidebar.selectbox("Start Month", all_months, index=len(all_months)-1)
    end_month = st.sidebar.selectbox("End Month", all_months, index=0)
    
    # 期間フィルタリング
    target_period = df_sales[(df_sales['年月'] >= start_month) & (df_sales['年月'] <= end_month)]

    st.sidebar.markdown("---")
    is_compare = st.sidebar.checkbox("Enable Comparison Mode", value=False)
    
    if is_compare:
        st.sidebar.subheader("Comparison Settings")
        compare_start = st.sidebar.selectbox("Comp Start", all_months, index=min(1, len(all_months)-1))
        compare_end = st.sidebar.selectbox("Comp End", all_months, index=min(1, len(all_months)-1))
        comp_period = df_sales[(df_sales['年月'] >= compare_start) & (df_sales['年月'] <= compare_end)]

    # --- 分析ロジック ---
    df_combined = pd.merge(df_sales, df_master, on='ASIN', how='left').fillna({'コード':'N/A', '正式品名':'不明', '規格':'-'})
    
    def get_period_summary(df_base, start, end):
        temp = df_base[(df_base['年月'] >= start) & (df_base['年月'] <= end)]
        return temp.groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()

    main_summary = get_period_summary(df_combined, start_month, end_month)

    # --- 表示 ---
    st.title("Sales Performance Dashboard")
    
    # メトリック行
    m1, m2, m3 = st.columns(3)
    total_sales = main_summary['売上'].sum()
    total_qty = main_summary['数量'].sum()

    if is_compare:
        comp_summary = get_period_summary(df_combined, compare_start, compare_end)
        total_sales_comp = comp_summary['売上'].sum()
        growth = ((total_sales / total_sales_comp) - 1) * 100 if total_sales_comp > 0 else 0
        m1.metric("Selected Period Sales", f"¥{int(total_sales):,}", f"{growth:+.1f}% vs Comp")
        m2.metric("Comparison Period Sales", f"¥{int(total_sales_comp):,}")
    else:
        m1.metric("Total Sales", f"¥{int(total_sales):,}")
        m2.metric("Total Units", f"{int(total_qty):,}")
    
    m3.metric("Product Count", f"{len(main_summary):,}")

    # --- グラフセクション ---
    st.subheader("Revenue Trend")
    trend_data = target_period.groupby('年月')['売上'].sum().reset_index()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=trend_data['年月'], y=trend_data['売上'],
        marker_color='#FF9900', name='Sales'
    ))
    fig.update_layout(
        plot_bgcolor='white', paper_bgcolor='white',
        margin=dict(l=20, r=20, t=20, b=20), height=300,
        xaxis=dict(showline=True, showgrid=False, linecolor='#D5D9D9'),
        yaxis=dict(showline=True, showgrid=True, gridcolor='#F3F3F3', linecolor='#D5D9D9')
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- データ詳細 ---
    st.subheader("Inventory & Sales Details")
    search = st.text_input("Quick Search (Name, Code, or ASIN)", "").lower()
    
    display_df = main_summary.copy()
    if search:
        display_df = display_df[
            display_df['正式品名'].str.lower().str.contains(search, na=False) | 
            display_df['コード'].astype(str).str.contains(search, na=False) | 
            display_df['ASIN'].str.lower().str.contains(search, na=False)
        ]

    # カラム名の整理
    display_df.columns = ['ASIN', 'Code', 'Product Name', 'Spec', 'Sales', 'Qty']
    st.dataframe(
        display_df.style.format({'Sales': '¥{:,.0f}', 'Qty': '{:,.0f}'}),
        use_container_width=True, height=500
    )

except Exception as e:
    st.error(f"System Error: {e}")