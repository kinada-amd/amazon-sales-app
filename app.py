import streamlit as st
import pandas as pd
from datetime import datetime
import io
import requests
import plotly.graph_objects as go

# 1. ページ設定
st.set_page_config(page_title="Amazon Analytics Pro", layout="wide", initial_sidebar_state="expanded")

# --- 【URL設定】 ---
URL_MASTER = "http://gigaplus.makeshop.jp/aimedia/data/master.xlsx"
URL_SALES = "http://gigaplus.makeshop.jp/aimedia/data/sales.xlsx"

# 2. スタイル設定（Amazonスタイル：ライトモード強制固定）
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');
    
    /* 背景と文字色を白・黒に完全固定（ダークモード無効化） */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #FFFFFF !important;
        color: #131921 !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    /* サイドバー */
    [data-testid="stSidebar"] {
        background-color: #131921 !important;
    }
    [data-testid="stSidebar"] * {
        color: #FFFFFF !important;
    }

    /* 入力エリア（セレクトボックス等）の視認性向上 */
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #131921 !important;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] div {
        color: #131921 !important;
        font-weight: 600 !important;
    }

    /* メトリック（大きな数字） */
    div[data-testid="stMetricValue"] {
        color: #131921 !important;
        font-weight: 800 !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    h1, h2, h3 {
        color: #131921 !important;
        font-weight: 700 !important;
    }

    /* データフレームのヘッダー色 */
    .stDataFrame thead tr th {
        background-color: #F3F3F3 !important;
        color: #131921 !important;
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=300)
def load_data_from_url(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return io.BytesIO(response.content)

try:
    with st.spinner('データを同期中...'):
        df_master = pd.read_excel(load_data_from_url(URL_MASTER))
        df_sales = pd.read_excel(load_data_from_url(URL_SALES))

    # クレンジング
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

    # --- サイドバー ---
    st.sidebar.title("Amazon Analytics")
    st.sidebar.markdown("---")
    
    mode = st.sidebar.radio("表示モードを選択", ["通常モード（期間集計）", "比較モード（MoM / YoY）"])
    
    st.sidebar.markdown("---")
    
    if mode == "通常モード（期間集計）":
        st.sidebar.subheader("集計期間の設定")
        start_month = st.sidebar.selectbox("開始月", all_months, index=len(all_months)-1, key="s1")
        end_month = st.sidebar.selectbox("終了月", all_months, index=0, key="e1")
        is_compare = False
    else:
        st.sidebar.subheader("ベース期間（現在）")
        start_month = st.sidebar.selectbox("開始月", all_months, index=0, key="s2")
        end_month = st.sidebar.selectbox("終了月", all_months, index=0, key="e2")
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("比較対象期間（過去）")
        compare_start = st.sidebar.selectbox("比較開始月", all_months, index=min(1, len(all_months)-1), key="cs")
        compare_end = st.sidebar.selectbox("比較終了月", all_months, index=min(1, len(all_months)-1), key="ce")
        is_compare = True

    # --- データ処理 ---
    df_combined = pd.merge(df_sales, df_master, on='ASIN', how='left').fillna({'コード':'N/A', '正式品名':'不明', '規格':'-'})
    
    def get_summary(df, s, e):
        temp = df[(df['年月'] >= s) & (df['年月'] <= e)]
        return temp.groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()

    main_summary = get_summary(df_combined, start_month, end_month)

    # --- メインエリア ---
    st.title("Sales Performance Dashboard")
    
    m1, m2, m3 = st.columns(3)
    total_sales = main_summary['売上'].sum()
    total_qty = main_summary['数量'].sum()

    if is_compare:
        comp_summary = get_summary(df_combined, compare_start, compare_end)
        total_sales_comp = comp_summary['売上'].sum()
        growth = ((total_sales / total_sales_comp) - 1) * 100 if total_sales_comp > 0 else 0
        
        m1.metric("Selected Sales", f"¥{int(total_sales):,}", f"{growth:+.1f}%")
        m2.metric("Comparison Sales", f"¥{int(total_sales_comp):,}")
        st.info(f"比較対象: {compare_start} 〜 {compare_end}")
    else:
        m1.metric("Total Sales", f"¥{int(total_sales):,}")
        m2.metric("Total Units", f"{int(total_qty):,}")
    
    m3.metric("Product Count", f"{len(main_summary):,}")

    # --- 売上推移グラフ ---
    st.subheader("Revenue Trend")
    # グラフ用データは常にメインの期間を表示
    trend_data = df_combined[(df_combined['年月'] >= start_month) & (df_combined['年月'] <= end_month)].groupby('年月')['売上'].sum().reset_index()
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=trend_data['年月'], y=trend_data['売上'],
        marker_color='#FF9900',
        hovertemplate='売上: ¥%{y:,.0f}<extra></extra>'
    ))
    fig.update_layout(
        plot_bgcolor='white', paper_bgcolor='white',
        margin=dict(l=0, r=0, t=20, b=0), height=300,
        font=dict(family="Inter, sans-serif", size=12, color="#131921"),
        xaxis=dict(showline=True, showgrid=False, linecolor='#D5D9D9'),
        yaxis=dict(showline=True, showgrid=True, gridcolor='#F3F3F3', linecolor='#D5D9D9')
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- 詳細テーブル ---
    st.subheader("売上詳細")
    search = st.text_input("クイック検索 (商品名, コード, ASIN)", "").lower()
    
    display_df = main_summary.copy()
    if search:
        display_df = display_df[
            display_df['正式品名'].str.lower().str.contains(search, na=False) | 
            display_df['コード'].astype(str).str.contains(search, na=False) | 
            display_df['ASIN'].str.lower().str.contains(search, na=False)
        ]

    display_df.columns = ['ASIN', 'コード', '正式品名', '規格', 'Sales', 'Qty']
    st.dataframe(
        display_df.style.format({'Sales': '¥{:,.0f}', 'Qty': '{:,.0f}'}),
        use_container_width=True, height=500
    )

except Exception as e:
    st.error(f"システムエラー: {e}")