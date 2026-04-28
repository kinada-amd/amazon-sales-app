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

# 2. スタイル設定（Amazonトーン＆マナー：ライトモード固定・Amazon Ember風フォント）
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');
    
    /* 全体フォントとライトモード固定 */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #FFFFFF !important;
        color: #131921 !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }
    
    /* サイドバー：Amazon濃紺 */
    [data-testid="stSidebar"] {
        background-color: #131921 !important;
    }
    [data-testid="stSidebar"] * {
        color: #FFFFFF !important;
    }

    /* セレクトボックス内の視認性（黒文字） */
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #131921 !important;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] div {
        color: #131921 !important;
        font-weight: 600 !important;
    }

    /* メインエリアの英数字（Amazon風タイポグラフィ） */
    div[data-testid="stMetricValue"] {
        color: #131921 !important;
        font-weight: 800 !important;
        font-family: 'Inter', sans-serif !important;
        letter-spacing: -1px;
    }
    
    h1, h2, h3 {
        color: #131921 !important;
        font-weight: 700 !important;
    }
    
    /* 比較モード有効時の強調色 */
    .compare-text {
        color: #FF9900 !important;
        font-weight: bold;
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

    # データクレンジング
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

    # --- サイドバー：設定の切り分け ---
    st.sidebar.title("Amazon Analytics")
    st.sidebar.markdown("---")
    
    # モード選択
    mode = st.sidebar.radio("表示モードを選択", ["通常モード（期間集計）", "比較モード（MoM / YoY）"])
    
    st.sidebar.markdown("---")
    
    if mode == "通常モード（期間集計）":
        st.sidebar.subheader("📅 集計期間の設定")
        start_month = st.sidebar.selectbox("開始月", all_months, index=len(all_months)-1, key="s1")
        end_month = st.sidebar.selectbox("終了月", all_months, index=0, key="e1")
        is_compare = False
    else:
        st.sidebar.subheader("📅 ベース期間（現在）")
        start_month = st.sidebar.selectbox("開始月", all_months, index=0, key="s2")
        end_month = st.sidebar.selectbox("終了月", all_months, index=0, key="e2")
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("📅 比較対象期間（過去）")
        compare_start = st.sidebar.selectbox("比較開始月", all_months, index=min(1, len(all_months)-1), key="cs")
        compare_end = st.sidebar.selectbox("比較終了月", all_months, index=min(1, len(all_months)-1), key="ce")
        is_compare = True

    # --- 共通データ処理 ---
    df_combined = pd.merge(df_sales, df_master, on='ASIN', how='left').fillna({'コード':'N/A', '正式品名':'不明', '規格':'-'})
    
    def get_period_data(df, s, e):
        return df[(df['年月'] >= s) & (df['年月'] <= e)]

    main_data = get_period_data(df_combined, start_month, end_month)
    main_summary = main_data.groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()

    # --- メインエリア ---
    st.title("Sales Performance Dashboard")
    
    m1, m2, m3 = st.columns(3)
    total_sales = main_summary['売上'].sum()
    total_qty = main_summary['数量'].sum()

    if is_compare:
        comp_data = get_period_data(df_combined, compare_start, compare_end)
        comp_summary = comp_data.groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()
        total_sales_comp = comp_summary['売上'].sum()
        
        growth = ((total_sales / total_sales_comp) - 1) * 100 if total_sales_comp > 0 else 0
        
        m1.metric("Selected Sales", f"¥{int(total_sales):,}", f"{growth:+.1f}%")
        m2.metric("Comparison Sales", f"¥{int(total_sales_comp):,}")
        st.info(f"比較中: **{start_month}〜{end_month}** VS **{compare_start}〜{compare_end}**")
    else:
        m1.metric("Total Sales", f"¥{int(total_sales):,}")
        m2.metric("Total Units", f"{int(total_qty):,}")
    
    m3.metric("Product Count", f"{len(main_summary):,}")

    # --- 売上推移グラフ ---
    st.subheader("Revenue Trend")
    trend_data = main_data.groupby('年月')['売上'].sum().reset_index()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=trend_data['年月'], y=trend_data['売上'],
        marker_color='#FF9900',
        hovertemplate='売上: ¥%{y:,.0f}<extra></extra>'
    ))
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=0, r=0, t=20, b=0), height=300,
        font=dict(family="Inter, sans-serif", size=12, color="#131921"),
        xaxis=dict(showline=True, showgrid=False, linecolor='#D5D9D9'),
        yaxis=dict(showline=True, showgrid=True, gridcolor='#F3F3F3', linecolor='#D5D9D9')
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- 詳細テーブル ---
    st.subheader("在庫・売上詳細")
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