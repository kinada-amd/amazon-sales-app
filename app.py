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

# 2. スタイル設定（強制ライトモード・視認性特化）
st.markdown("""
    <style>
    /* 1. 全体の背景と文字色を最優先で固定 */
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #FFFFFF !important;
        color: #131921 !important;
    }
    
    /* 2. サイドバーの設定 */
    [data-testid="stSidebar"] {
        background-color: #131921 !important;
    }
    [data-testid="stSidebar"] * {
        color: #FFFFFF !important;
    }

    /* 3. セレクトボックス（入力枠）の中の文字を絶対に見えるようにする */
    /* 枠内の背景を白、文字を濃紺に強制 */
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #131921 !important;
    }
    
    /* 選択されたテキスト自体の色 */
    div[data-testid="stSelectbox"] div[data-baseweb="select"] div {
        color: #131921 !important;
    }

    /* ドロップダウンリストの中身も白背景・黒文字に */
    ul[role="listbox"] {
        background-color: #FFFFFF !important;
    }
    ul[role="listbox"] li {
        color: #131921 !important;
    }

    /* 4. メインエリアの各要素 */
    h1, h2, h3, h4, p, span, label {
        color: #131921 !important;
    }
    
    /* Metric（数字）の色 */
    div[data-testid="stMetricValue"] {
        color: #131921 !important;
    }
    
    /* 5. ダークモード切替ボタンを非表示（CSSで隠す） */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
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
    
    st.sidebar.subheader("期間選択")
    start_month = st.sidebar.selectbox("開始月", all_months, index=len(all_months)-1)
    end_month = st.sidebar.selectbox("終了月", all_months, index=0)
    
    target_period = df_sales[(df_sales['年月'] >= start_month) & (df_sales['年月'] <= end_month)]

    st.sidebar.markdown("---")
    is_compare = st.sidebar.checkbox("比較モードを有効にする", value=False)
    
    if is_compare:
        st.sidebar.subheader("比較対象の設定")
        compare_start = st.sidebar.selectbox("比較開始月", all_months, index=min(1, len(all_months)-1))
        compare_end = st.sidebar.selectbox("比較終了月", all_months, index=min(1, len(all_months)-1))

    # --- 分析 ---
    df_combined = pd.merge(df_sales, df_master, on='ASIN', how='left').fillna({'コード':'N/A', '正式品名':'不明', '規格':'-'})
    
    def get_period_summary(df_base, start, end):
        temp = df_base[(df_base['年月'] >= start) & (df_base['年月'] <= end)]
        return temp.groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()

    main_summary = get_period_summary(df_combined, start_month, end_month)

    # --- 表示 ---
    st.title("Sales Performance Dashboard")
    
    m1, m2, m3 = st.columns(3)
    total_sales = main_summary['売上'].sum()
    total_qty = main_summary['数量'].sum()

    if is_compare:
        comp_summary = get_period_summary(df_combined, compare_start, compare_end)
        total_sales_comp = comp_summary['売上'].sum()
        growth = ((total_sales / total_sales_comp) - 1) * 100 if total_sales_comp > 0 else 0
        m1.metric("選択期間の売上", f"¥{int(total_sales):,}", f"{growth:+.1f}%")
        m2.metric("比較対象の売上", f"¥{int(total_sales_comp):,}")
    else:
        m1.metric("合計売上", f"¥{int(total_sales):,}")
        m2.metric("合計数量", f"{int(total_qty):,}")
    
    m3.metric("商品数", f"{len(main_summary):,}")

    st.subheader("売上推移")
    trend_data = target_period.groupby('年月')['売上'].sum().reset_index()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=trend_data['年月'], 
        y=trend_data['売上'],
        marker_color='#FF9900',
        name='売上',
        hovertemplate='売上: ¥%{y:,.0f}<extra></extra>'
    ))
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        margin=dict(l=20, r=20, t=20, b=20), height=300,
        xaxis=dict(showline=True, showgrid=False, linecolor='#D5D9D9'),
        yaxis=dict(showline=True, showgrid=True, gridcolor='#F3F3F3', linecolor='#D5D9D9')
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("在庫・売上詳細")
    search = st.text_input("クイック検索 (商品名, コード, ASIN)", "").lower()
    
    display_df = main_summary.copy()
    if search:
        display_df = display_df[
            display_df['正式品名'].str.lower().str.contains(search, na=False) | 
            display_df['コード'].astype(str).str.contains(search, na=False) | 
            display_df['ASIN'].str.lower().str.contains(search, na=False)
        ]

    display_df.columns = ['ASIN', 'コード', '正式品名', '規格', '売上', '数量']
    st.dataframe(
        display_df.style.format({'売上': '¥{:,.0f}', '数量': '{:,.0f}'}),
        use_container_width=True, height=500
    )

except Exception as e:
    st.error(f"システムエラー: {e}")