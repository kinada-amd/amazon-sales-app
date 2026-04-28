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

# 2. 強制ライトモード & AmazonデザインCSS
st.markdown("""
    <style>
    /* ダークモードを完全に上書きして無効化 */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #FFFFFF !important;
        color: #131921 !important;
    }
    [data-testid="stHeader"] { background-color: rgba(0,0,0,0) !important; }
    
    /* サイドバー */
    [data-testid="stSidebar"] { background-color: #131921 !important; }
    [data-testid="stSidebar"] * { color: #FFFFFF !important; }

    /* セレクトボックスの視認性向上 */
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #131921 !important;
    }
    
    /* メインエリアのテキスト */
    h1, h2, h3, p, span, label { color: #131921 !important; }
    div[data-testid="stMetricValue"] { color: #131921 !important; font-weight: 800 !important; }
    
    /* テーブルのスタイル */
    .stDataFrame { border: 1px solid #D5D9D9 !important; }
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

    # --- サイドバー：設定 ---
    st.sidebar.title("Amazon Analytics")
    st.sidebar.markdown("---")
    
    mode = st.sidebar.radio("表示モードを選択", ["通常モード", "比較モード"])
    
    st.sidebar.markdown("---")
    
    # 期間選択のロジック
    if mode == "通常モード":
        st.sidebar.subheader("集計期間の設定")
        start_m = st.sidebar.selectbox("開始月", all_months, index=len(all_months)-1, key="start_reg")
        end_m = st.sidebar.selectbox("終了月", all_months, index=0, key="end_reg")
        is_compare = False
    else:
        st.sidebar.subheader("ベース期間（現在）")
        start_m = st.sidebar.selectbox("開始月", all_months, index=0, key="start_base")
        end_m = st.sidebar.selectbox("終了月", all_months, index=0, key="end_base")
        st.sidebar.markdown("---")
        st.sidebar.subheader("比較対象期間（過去）")
        comp_start_m = st.sidebar.selectbox("比較開始", all_months, index=min(1, len(all_months)-1), key="start_comp")
        comp_end_m = st.sidebar.selectbox("比較終了", all_months, index=min(1, len(all_months)-1), key="end_comp")
        is_compare = True

    # --- データ集計関数 ---
    def get_summary(df, s, e):
        mask = (df['年月'] >= s) & (df['年月'] <= e)
        return df[mask].groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()

    # マスターと結合
    df_full = pd.merge(df_sales, df_master, on='ASIN', how='left').fillna({'コード':'N/A', '正式品名':'不明', '規格':'-'})
    
    # メインデータの抽出
    main_summary = get_summary(df_full, start_m, end_m)

    # --- メインエリア表示 ---
    st.title("Sales Performance Dashboard")
    
    # メトリック表示
    m1, m2, m3 = st.columns(3)
    total_sales = main_summary['売上'].sum()
    
    if is_compare:
        comp_summary = get_summary(df_full, comp_start_m, comp_end_m)
        total_sales_comp = comp_summary['売上'].sum()
        growth = ((total_sales / total_sales_comp) - 1) * 100 if total_sales_comp > 0 else 0
        
        m1.metric("Selected Sales", f"¥{int(total_sales):,}", f"{growth:+.1f}%")
        m2.metric("Comparison Sales", f"¥{int(total_sales_comp):,}")
    else:
        m1.metric("Total Sales", f"¥{int(total_sales):,}")
        m2.metric("Total Units", f"{int(main_summary['数量'].sum()):,}")
    
    m3.metric("Product Count", f"{len(main_summary):,}")

    # --- 売上推移グラフ ---
    st.subheader("Revenue Trend")
    trend_data = df_full[(df_full['年月'] >= start_m) & (df_full['年月'] <= end_m)].groupby('年月')['売上'].sum().reset_index()
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=trend_data['年月'], y=trend_data['売上'],
        marker_color='#FF9900',
        hovertemplate='売上: ¥%{y:,.0f}<extra></extra>'
    ))
    fig.update_layout(
        plot_bgcolor='white', paper_bgcolor='white',
        margin=dict(l=0, r=0, t=20, b=0), height=300,
        xaxis=dict(showline=True, showgrid=False, linecolor='#D5D9D9'),
        yaxis=dict(showline=True, showgrid=True, gridcolor='#F3F3F3', linecolor='#D5D9D9')
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- 詳細テーブル（比較列の作成） ---
    st.subheader("売上詳細")
    
    if is_compare:
        # 現在と過去をASINでマージ
        merged_df = pd.merge(
            main_summary, 
            comp_summary[['ASIN', '売上', '数量']], 
            on='ASIN', 
            how='left', 
            suffixes=('', '_過去')
        ).fillna(0)
        
        # 伸び率の計算
        merged_df['Diff (%)'] = ((merged_df['売上'] / merged_df['売上_過去']) - 1) * 100
        merged_df.loc[merged_df['売上_過去'] == 0, 'Diff (%)'] = 100.0
        
        display_df = merged_df[['ASIN', 'コード', '正式品名', '売上', '売上_過去', 'Diff (%)', '数量']]
        display_df.columns = ['ASIN', 'コード', '商品名', '売上(現在)', '売上(比較)', '増減率(%)', '数量']
        format_dict = {'売上(現在)': '¥{:,.0f}', '売上(比較)': '¥{:,.0f}', '増減率(%)': '{:+.1f}%', '数量': '{:,.0f}'}
    else:
        display_df = main_summary[['ASIN', 'コード', '正式品名', '売上', '数量']]
        display_df.columns = ['ASIN', 'コード', '商品名', '売上', '数量']
        format_dict = {'売上': '¥{:,.0f}', '数量': '{:,.0f}'}

    # 検索機能
    search = st.text_input("検索 (商品名, コード, ASIN)", "").lower()
    if search:
        display_df = display_df[
            display_df['商品名'].str.lower().str.contains(search, na=False) | 
            display_df['コード'].astype(str).str.contains(search, na=False) | 
            display_df['ASIN'].str.lower().str.contains(search, na=False)
        ]

    st.dataframe(display_df.style.format(format_dict), use_container_width=True, height=500)

except Exception as e:
    st.error(f"システムエラー: {e}")