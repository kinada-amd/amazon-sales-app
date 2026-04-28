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

# 2. デザイン修正（Amazonトーン＆マナー / ライトモード強制）
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
    }
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
    # モード切り替え。indexを変えることでリセットに近い挙動を実現
    mode = st.sidebar.radio("表示モードを選択", ["通常モード", "比較モード"], key="mode_selector")
    
    st.sidebar.markdown("---")

    if mode == "通常モード":
        st.sidebar.subheader("期間選択")
        s_m = st.sidebar.selectbox("開始月", all_m, index=len(all_m)-1, key="reg_start")
        e_m = st.sidebar.selectbox("終了月", all_m, index=0, key="reg_end")
        # 比較用変数を初期化
        cs_m, ce_m = None, None
    else:
        # 比較モード：各窓を独立して表示
        st.sidebar.subheader("現在の期間（現在）")
        s_m = st.sidebar.selectbox("開始月(現在)", all_m, index=0, key="comp_now_start")
        e_m = st.sidebar.selectbox("終了月(現在)", all_m, index=0, key="comp_now_end")
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("比較対象の期間（比較）")
        cs_m = st.sidebar.selectbox("開始月(比較)", all_m, index=min(1, len(all_m)-1), key="comp_prev_start")
        ce_m = st.sidebar.selectbox("終了月(比較)", all_m, index=min(1, len(all_m)-1), key="comp_prev_end")

    # --- 集計ロジック ---
    df_f = pd.merge(df_s, df_m, on='ASIN', how='left').fillna({'コード':'N/A', '正式品名':'不明', '規格':'-'})
    
    def get_summary(df, start, end):
        mask = (df['年月'] >= start) & (df['年月'] <= end)
        return df[mask].groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()

    # 「現在」の集計
    main_res = get_summary(df_f, s_m, e_m)

    # --- メイン表示 ---
    st.title("Sales Performance Dashboard")
    
    val_now = main_res['売上'].sum()
    m1, m2, m3 = st.columns(3)

    if mode == "比較モード":
        # 「比較」の集計
        comp_res = get_summary(df_f, cs_m, ce_m)
        val_prev = comp_res['売上'].sum()
        pct = ((val_now / val_prev) - 1) * 100 if val_prev > 0 else 0
        
        m1.metric(f"売上 (現在: {s_m}〜{e_m})", f"¥{int(val_now):,}", f"{pct:+.1f}%")
        m2.metric(f"売上 (比較: {cs_m}〜{ce_m})", f"¥{int(val_prev):,}")
        
        # 比較表の作成
        disp = pd.merge(
            main_res, 
            comp_res[['ASIN', '売上', '数量']], 
            on='ASIN', 
            how='outer', 
            suffixes=('', '_比較')
        ).fillna(0)
        
        # 名前・コード・規格が消えないよう補完（outer join対策）
        # ※本来はmain_resにあるはずだが、比較対象にしか存在しない商品があった場合のため
        
        disp['MoM/YoY (%)'] = ((disp['売上'] / disp['売上_比較']) - 1) * 100
        disp.loc[disp['売上_比較'] == 0, 'MoM/YoY (%)'] = 0
        
        # 列名に年月を反映
        label_now = f"売上({s_m}〜{e_m})"
        label_comp = f"売上({cs_m}〜{ce_m})"
        
        disp = disp[['ASIN', 'コード', '正式品名', '規格', '売上', '売上_比較', 'MoM/YoY (%)', '数量']]
        disp.columns = ['ASIN', 'コード', '正式品名', '規格', label_now, label_comp, 'MoM/YoY (%)', '数量']
        fmt = {label_now: '¥{:,.0f}', label_comp: '¥{:,.0f}', 'MoM/YoY (%)': '{:+.1f}%', '数量': '{:,.0f}'}
    else:
        m1.metric(f"合計売上 ({s_m}〜{e_m})", f"¥{int(val_now):,}")
        m2.metric("合計数量", f"{int(main_res['数量'].sum()):,}")
        disp = main_res[['ASIN', 'コード', '正式品名', '規格', '売上', '数量']]
        disp.columns = ['ASIN', 'コード', '正式品名', '規格', '売上', '数量']
        fmt = {'売上': '¥{:,.0f}', '数量': '{:,.0f}'}

    m3.metric("商品数", f"{len(main_res):,}")
    
    st.markdown("---")
    st.subheader("売上詳細")
    
    search = st.text_input("クイック検索 (正式品名, コード, ASIN)", "").lower()
    if search:
        # 検索対象列の特定（モードによって列名が変わるため商品名などで固定）
        disp = disp[disp['正式品名'].str.lower().str.contains(search, na=False) | 
                    disp['コード'].astype(str).str.contains(search, na=False) | 
                    disp['ASIN'].str.lower().str.contains(search, na=False)]

    st.dataframe(disp.style.format(fmt), use_container_width=True, height=650)

except Exception as e:
    st.error(f"エラーが発生しました: {e}")