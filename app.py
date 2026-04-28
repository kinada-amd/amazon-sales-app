import streamlit as st
import pandas as pd
import io
import requests

# 1. ページ設定
st.set_page_config(page_title="Amazon Analytics Pro", layout="wide", initial_sidebar_state="expanded")

# 2. デザイン修正
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');
    
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #FFFFFF !important;
        color: #131921 !important;
        font-family: 'Inter', sans-serif !important;
    }

    [data-testid="stHeader"] { 
        background-color: rgba(255, 255, 255, 0) !important; 
        color: #131921 !important;
    }
    #MainMenu { visibility: hidden !important; }
    footer { visibility: hidden !important; }

    [data-testid="stSidebar"] { background-color: #131921 !important; }
    [data-testid="stSidebar"] * { color: #FFFFFF !important; }

    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #131921 !important;
        border: 1px solid #D5D9D9 !important;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] div {
        color: #131921 !important;
        font-weight: 700 !important;
    }

    div[data-testid="stMetricValue"] {
        color: #131921 !important;
        font-weight: 800 !important;
        font-family: 'Inter', sans-serif !important;
        letter-spacing: -0.03em !important;
    }

    .stDataFrame { font-family: 'Inter', sans-serif !important; }
    h1, h2, h3 { color: #131921 !important; font-weight: 800 !important; letter-spacing: -0.02em !important; }
    .st-emotion-cache-zy6yx3 {padding: 3rem 5rem 10rem;}
    </style>
    """, unsafe_allow_html=True)

@st.cache_data(ttl=300)
def load_data(url):
    res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    return io.BytesIO(res.content)

try:
    df_m = pd.read_excel(load_data("http://gigaplus.makeshop.jp/aimedia/data/master.xlsx"))
    df_s = pd.read_excel(load_data("http://gigaplus.makeshop.jp/aimedia/data/sales.xlsx"))

    df_s.columns = df_s.columns.str.strip()
    df_m.columns = df_m.columns.str.strip()
    for c in ['売上', '数量']:
        if c in df_s.columns:
            df_s[c] = pd.to_numeric(df_s[c].astype(str).str.replace(',', ''), errors='coerce').fillna(0)

    # 日付データの処理
    df_s['日付_dt'] = pd.to_datetime(df_s['日付'], format='%Y年%m月', errors='coerce')
    df_s['年月'] = df_s['日付_dt'].dt.strftime('%Y-%m')
    
    # 年度計算 (4月開始)
    df_s['年度'] = df_s['日付_dt'].apply(lambda x: f"{str(x.year - 1)[2:]}年度" if x.month <= 3 else f"{str(x.year)[2:]}年度")

    all_months = sorted(df_s['年月'].dropna().unique(), reverse=True)
    all_years = sorted(df_s['年度'].dropna().unique(), reverse=True)
    all_options = all_years + all_months

    # --- サイドバー ---
    st.sidebar.title("Amazon Analytics")
    mode = st.sidebar.radio("表示モードを選択", ["通常モード", "比較モード"], key="mode")
    st.sidebar.markdown("---")

    if mode == "通常モード":
        target_m = st.sidebar.selectbox("表示する期間を選択", all_options, index=0, key="m1")
        comp_m = None
    else:
        target_m = st.sidebar.selectbox("現在の期間（現在）", all_options, index=0, key="m2")
        comp_m = st.sidebar.selectbox("比較する期間（比較）", all_options, index=min(1, len(all_options)-1), key="m3")

    df_f = pd.merge(df_s, df_m, on='ASIN', how='left').fillna({'コード':'N/A', '正式品名':'不明', '規格':'-'})

    def filter_data(df, period):
        if "年度" in period:
            return df[df['年度'] == period]
        else:
            return df[df['年月'] == period]

    main_res_raw = filter_data(df_f, target_m)
    main_res = main_res_raw.groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()

    # --- 表示エリア ---
    st.title("Sales Performance Dashboard")
    m1, m2, m3 = st.columns(3)
    val_now = main_res['売上'].sum()

    if mode == "比較モード":
        prev_res_raw = filter_data(df_f, comp_m)
        prev_res = prev_res_raw.groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()
        
        val_prev = prev_res['売上'].sum()
        pct = ((val_now / val_prev) - 1) * 100 if val_prev > 0 else 0
        m1.metric(f"売上 ({target_m})", f"¥{int(val_now):,}", f"{pct:+.1f}%")
        m2.metric(f"売上 ({comp_m})", f"¥{int(val_prev):,}")
        
        # データのマージ
        disp = pd.merge(main_res, prev_res[['ASIN', '売上', '数量']], on='ASIN', how='outer', suffixes=('', '_比較')).fillna(0)
        
        # 売上の伸長率計算
        disp['売上 MoM/YoY (%)'] = ((disp['売上'] / disp['売上_比較']) - 1) * 100
        disp.loc[disp['売上_比較'] == 0, '売上 MoM/YoY (%)'] = 0
        
        # 数量の伸長率計算
        disp['数量 MoM/YoY (%)'] = ((disp['数量'] / disp['数量_比較']) - 1) * 100
        disp.loc[disp['数量_比較'] == 0, '数量 MoM/YoY (%)'] = 0
        
        # カラム名の動的作成
        col_s_now, col_s_prev = f"売上({target_m})", f"売上({comp_m})"
        col_q_now, col_q_prev = f"数量({target_m})", f"数量({comp_m})"
        
        # カラム順序の整理
        disp = disp[['ASIN', 'コード', '正式品名', '規格', '売上', '売上_比較', '売上 MoM/YoY (%)', '数量', '数量_比較', '数量 MoM/YoY (%)']]
        disp.columns = ['ASIN', 'コード', '正式品名', '規格', col_s_now, col_s_prev, '売上 MoM/YoY (%)', col_q_now, col_q_prev, '数量 MoM/YoY (%)']
        
        fmt = {col_s_now: '¥{:,.0f}', col_s_prev: '¥{:,.0f}', '売上 MoM/YoY (%)': '{:+.1f}%', 
               col_q_now: '{:,.0f}', col_q_prev: '{:,.0f}', '数量 MoM/YoY (%)': '{:+.1f}%'}
    else:
        m1.metric(f"売上 ({target_m})", f"¥{int(val_now):,}")
        m2.metric("合計数量", f"{int(main_res['数量'].sum()):,}")
        disp = main_res[['ASIN', 'コード', '正式品名', '規格', '売上', '数量']]
        disp.columns = ['ASIN', 'コード', '正式品名', '規格', f"売上({target_m})", '数量']
        fmt = {f"売上({target_m})": '¥{:,.0f}', '数量': '{:,.0f}'}

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