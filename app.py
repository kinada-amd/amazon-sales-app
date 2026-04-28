import streamlit as st
import pandas as pd
from datetime import datetime
import io
import requests

# 1. ページ設定
st.set_page_config(page_title="Amazon Analytics Pro", layout="wide", initial_sidebar_state="expanded")

# --- 【URL設定】 ---
URL_MASTER = "http://gigaplus.makeshop.jp/aimedia/data/master.xlsx"
URL_SALES = "http://gigaplus.makeshop.jp/aimedia/data/sales.xlsx"

# 2. デザイン修正（Amazonトーン＆マナー / ライトモード強制 / Amazon Ember風フォント）
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');
    
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #FFFFFF !important;
        color: #131921 !important;
        font-family: 'Inter', sans-serif !important;
    }

    #MainMenu, footer, [data-testid="stHeader"] { visibility: hidden !important; }

    [data-testid="stSidebar"] { background-color: #131921 !important; }
    [data-testid="stSidebar"] * { color: #FFFFFF !important; }

    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #131921 !important;
        border: 1px solid #D5D9D9 !important;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] div {
        color: #131921 !important;
    }

    div[data-testid="stMetricValue"] {
        color: #131921 !important;
        font-weight: 800 !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    h1, h2, h3 { color: #131921 !important; font-family: 'Inter', sans-serif !important; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=300)
def load_data(url):
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    return io.BytesIO(res.content)

try:
    df_m = pd.read_excel(load_data(URL_MASTER))
    df_s = pd.read_excel(load_data(URL_SALES))

    df_s.columns = df_s.columns.str.strip()
    df_m.columns = df_m.columns.str.strip()
    for c in ['売上', '数量']:
        if c in df_s.columns:
            df_s[c] = pd.to_numeric(df_s[c].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    df_s['年月'] = pd.to_datetime(df_s['日付'], format='%Y年%m月', errors='coerce').dt.strftime('%Y-%m')
    all_m = sorted(df_s['年月'].dropna().unique(), reverse=True)

    # --- サイドバー ---
    st.sidebar.title("Amazon Analytics")
    mode = st.sidebar.radio("表示モードを選択", ["通常モード", "比較モード"])
    
    if mode == "通常モード":
        st.sidebar.subheader("期間選択")
        s_m = st.sidebar.selectbox("開始月", all_m, index=len(all_m)-1, key="s1")
        e_m = st.sidebar.selectbox("終了月", all_m, index=0, key="e1")
    else:
        st.sidebar.subheader("現在の期間")
        s_m = st.sidebar.selectbox("開始", all_m, index=0, key="s2")
        e_m = st.sidebar.selectbox("終了", all_m, index=0, key="e2")
        st.sidebar.subheader("比較対象の期間")
        cs_m = st.sidebar.selectbox("比較開始", all_m, index=min(1, len(all_m)-1))
        ce_m = st.sidebar.selectbox("比較終了", all_m, index=min(1, len(all_m)-1))

    # --- 集計ロジック ---
    df_f = pd.merge(df_s, df_m, on='ASIN', how='left').fillna({'コード':'N/A', '正式品名':'不明', '規格':'-'})
    
    def get_summary(df, start, end):
        mask = (df['年月'] >= start) & (df['年月'] <= end)
        return df[mask].groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()

    main_res = get_summary(df_f, s_m, e_m)

    # --- メイン表示 ---
    st.title("Sales Performance Dashboard")
    
    m1, m2, m3 = st.columns(3)
    val_now = main_res['売上'].sum()

    if mode == "比較モード":
        comp_res = get_summary(df_f, cs_m, ce_m)
        val_prev = comp_res['売上'].sum()
        pct = ((val_now / val_prev) - 1) * 100 if val_prev > 0 else 0
        
        m1.metric("現在の期間の売上", f"¥{int(val_now):,}", f"{pct:+.1f}%")
        m2.metric("比較期間の売上", f"¥{int(val_prev):,}")
        
        # 比較表の作成（規格を含む）
        disp = pd.merge(main_res, comp_res[['ASIN', '売上', '数量']], on='ASIN', how='left', suffixes=('', '_過去')).fillna(0)
        disp['MoM/YoY (%)'] = ((disp['売上'] / disp['売上_過去']) - 1) * 100
        disp.loc[disp['売上_過去'] == 0, 'MoM/YoY (%)'] = 0
        disp = disp[['ASIN', 'コード', '正式品名', '規格', '売上', '売上_過去', 'MoM/YoY (%)', '数量']]
        disp.columns = ['ASIN', 'コード', '正式品名', '規格', '売上(現在)', '売上(比較)', 'MoM/YoY (%)', '数量']
        fmt = {'売上(現在)': '¥{:,.0f}', '売上(比較)': '¥{:,.0f}', 'MoM/YoY (%)': '{:+.1f}%', '数量': '{:,.0f}'}
    else:
        m1.metric("合計売上", f"¥{int(val_now):,}")
        m2.metric("合計数量", f"{int(main_res['数量'].sum()):,}")
        disp = main_res[['ASIN', 'コード', '正式品名', '規格', '売上', '数量']]
        disp.columns = ['ASIN', 'コード', '正式品名', '規格', '売上', '数量']
        fmt = {'売上': '¥{:,.0f}', '数量': '{:,.0f}'}

    m3.metric("商品数", f"{len(main_res):,}")
    
    st.markdown("---")
    st.subheader("売上詳細")
    
    search = st.text_input("クイック検索 (正式品名, コード, ASIN)", "").lower()
    if search:
        disp = disp[disp['正式品名'].str.lower().str.contains(search, na=False) | 
                    disp['コード'].astype(str).str.contains(search, na=False) | 
                    disp['ASIN'].str.lower().str.contains(search, na=False)]

    st.dataframe(disp.style.format(fmt), use_container_width=True, height=650)

except Exception as e:
    st.error(f"エラーが発生しました: {e}")