import streamlit as st
import pandas as pd
from datetime import datetime
import io
import requests

# 1. ページ設定：ライトモード強制・メニュー非表示
st.set_page_config(page_title="Amazon Analytics Pro", layout="wide", initial_sidebar_state="expanded")

# --- 【URL設定】 ---
URL_MASTER = "http://gigaplus.makeshop.jp/aimedia/data/master.xlsx"
URL_SALES = "http://gigaplus.makeshop.jp/aimedia/data/sales.xlsx"

# 2. CSS：Amazonデザイン・ダークモード遮断・テキストカラー修正
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');
    
    /* 背景と文字色：白背景・濃紺文字に強制固定 */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #FFFFFF !important;
        color: #131921 !important;
        font-family: 'Inter', -apple-system, sans-serif !important;
    }

    /* 右上の三本線メニューとDark/Light切替を完全に隠す */
    #MainMenu, footer, [data-testid="stHeader"] { visibility: hidden !important; }

    /* サイドバー：Amazonネイビー */
    [data-testid="stSidebar"] { background-color: #131921 !important; }
    [data-testid="stSidebar"] * { color: #FFFFFF !important; }

    /* 期間選択ボックス：白背景に濃紺文字（確実に見えるように修正） */
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #131921 !important;
        border: 1px solid #D5D9D9 !important;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] div {
        color: #131921 !important; /* 選択済みの文字色 */
    }

    /* メトリクスと英数字フォント */
    div[data-testid="stMetricValue"] {
        color: #131921 !important;
        font-weight: 800 !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    /* 見出し */
    h1, h2, h3 { color: #131921 !important; font-family: 'Inter', sans-serif !important; }
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=300)
def load_data(url):
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    return io.BytesIO(res.content)

try:
    # データ読み込み
    df_m = pd.read_excel(load_data(URL_MASTER))
    df_s = pd.read_excel(load_data(URL_SALES))

    # クレンジング
    df_s.columns = df_s.columns.str.strip()
    df_m.columns = df_m.columns.str.strip()
    for c in ['売上', '数量']:
        if c in df_s.columns:
            df_s[c] = pd.to_numeric(df_s[c].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    df_s['年月'] = pd.to_datetime(df_s['日付'], format='%Y年%m月', errors='coerce').dt.strftime('%Y-%m')
    all_m = sorted(df_s['年月'].dropna().unique(), reverse=True)

    # --- サイドバー ---
    st.sidebar.title("Amazon Analytics")
    mode = st.sidebar.radio("Mode", ["Standard", "Comparison"])
    
    if mode == "Standard":
        s_m = st.sidebar.selectbox("Start Month", all_m, index=len(all_m)-1, key="s1")
        e_m = st.sidebar.selectbox("End Month", all_m, index=0, key="e1")
    else:
        st.sidebar.subheader("Current Period")
        s_m = st.sidebar.selectbox("Start", all_m, index=0, key="s2")
        e_m = st.sidebar.selectbox("End", all_m, index=0, key="e2")
        st.sidebar.subheader("Comparison Period")
        cs_m = st.sidebar.selectbox("Comp Start", all_m, index=min(1, len(all_m)-1))
        ce_m = st.sidebar.selectbox("Comp End", all_m, index=min(1, len(all_m)-1))

    # --- 集計ロジック ---
    df_f = pd.merge(df_s, df_m, on='ASIN', how='left').fillna({'コード':'N/A', '正式品名':'Unknown', '規格':'-'})
    
    def get_summary(df, start, end):
        mask = (df['年月'] >= start) & (df['年月'] <= end)
        return df[mask].groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()

    main_res = get_summary(df_f, s_m, e_m)

    # --- メイン表示 ---
    st.title("Sales Performance Dashboard")
    
    m1, m2, m3 = st.columns(3)
    val_now = main_res['売上'].sum()

    if mode == "Comparison":
        comp_res = get_summary(df_f, cs_m, ce_m)
        val_prev = comp_res['売上'].sum()
        pct = ((val_now / val_prev) - 1) * 100 if val_prev > 0 else 0
        m1.metric("Current Sales", f"¥{int(val_now):,}", f"{pct:+.1f}%")
        m2.metric("Comparison Sales", f"¥{int(val_prev):,}")
        
        # 比較表の作成
        disp = pd.merge(main_res, comp_res[['ASIN', '売上', '数量']], on='ASIN', how='left', suffixes=('', '_Prev')).fillna(0)
        disp['Growth (%)'] = ((disp['売上'] / disp['売上_Prev']) - 1) * 100
        disp.loc[disp['売上_Prev'] == 0, 'Growth (%)'] = 0
        disp = disp[['ASIN', 'コード', '正式品名', '売上', '売上_Prev', 'Growth (%)', '数量']]
        disp.columns = ['ASIN', 'Code', 'Product Name', 'Sales (Now)', 'Sales (Comp)', 'Growth (%)', 'Qty']
        fmt = {'Sales (Now)': '¥{:,.0f}', 'Sales (Comp)': '¥{:,.0f}', 'Growth (%)': '{:+.1f}%', 'Qty': '{:,.0f}'}
    else:
        m1.metric("Total Sales", f"¥{int(val_now):,}")
        m2.metric("Total Units", f"{int(main_res['数量'].sum()):,}")
        disp = main_res[['ASIN', 'コード', '正式品名', '売上', '数量']]
        disp.columns = ['ASIN', 'Code', 'Product Name', 'Sales', 'Qty']
        fmt = {'Sales': '¥{:,.0f}', 'Qty': '{:,.0f}'}

    m3.metric("Products", f"{len(main_res):,}")
    
    st.markdown("---")
    st.subheader("Sales Details")
    
    search = st.text_input("Search (Product Name, Code, or ASIN)", "").lower()
    if search:
        disp = disp[disp['Product Name'].str.lower().str.contains(search, na=False) | 
                    disp['Code'].astype(str).str.contains(search, na=False) | 
                    disp['ASIN'].str.lower().str.contains(search, na=False)]

    st.dataframe(disp.style.format(fmt), use_container_width=True, height=600)

except Exception as e:
    st.error(f"System Error: {e}")