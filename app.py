import streamlit as st
import pandas as pd
from datetime import datetime
import io
import requests

# 1. ページ設定（ライトモード固定のための設定）
st.set_page_config(page_title="Amazon Analytics Pro", layout="wide", initial_sidebar_state="expanded")

# --- 【URL設定】 ---
URL_MASTER = "http://gigaplus.makeshop.jp/aimedia/data/master.xlsx"
URL_SALES = "http://gigaplus.makeshop.jp/aimedia/data/sales.xlsx"

# 2. デザイン修正（Amazonトーン＆マナー / ダークモード完全排除 / フォントAmazon Ember風）
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');
    
    /* 1. 背景と文字色を強制固定（ブラウザのダークモードを無効化） */
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background-color: #FFFFFF !important;
        color: #131921 !important;
        font-family: 'Inter', -apple-system, sans-serif !important;
    }

    /* 2. サイドバー：Amazonネイビー */
    [data-testid="stSidebar"] {
        background-color: #131921 !important;
    }
    [data-testid="stSidebar"] * {
        color: #FFFFFF !important;
    }

    /* 3. 期間選択枠の視認性修正（枠内は白背景・文字は濃紺で固定） */
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        color: #131921 !important; /* ←ここで選択中の文字が見えるようになります */
        border: 1px solid #D5D9D9 !important;
    }
    
    /* 選択肢リスト（ドロップダウン）も白背景・黒文字 */
    ul[role="listbox"] {
        background-color: #FFFFFF !important;
    }
    ul[role="listbox"] li {
        color: #131921 !important;
    }

    /* 4. 英字・数字のフォントをAmazonのトンマナ（力強くスタイリッシュ）に */
    div[data-testid="stMetricValue"], .stDataFrame, h1, h2, h3, p, span {
        font-family: 'Inter', sans-serif !important;
        letter-spacing: -0.02em !important;
    }
    div[data-testid="stMetricValue"] {
        color: #131921 !important;
        font-weight: 800 !important;
    }

    /* 5. 検索窓のスタイル */
    input {
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

    # --- サイドバー設定 ---
    st.sidebar.title("Amazon Analytics")
    st.sidebar.markdown("---")
    
    mode = st.sidebar.radio("表示モードを選択", ["通常モード", "比較モード"])
    
    if mode == "通常モード":
        st.sidebar.subheader("集計期間の設定")
        start_m = st.sidebar.selectbox("開始月", all_months, index=len(all_months)-1, key="n_s")
        end_m = st.sidebar.selectbox("終了月", all_months, index=0, key="n_e")
    else:
        st.sidebar.subheader("ベース期間（現在）")
        start_m = st.sidebar.selectbox("開始月", all_months, index=0, key="c_s")
        end_m = st.sidebar.selectbox("終了月", all_months, index=0, key="c_e")
        st.sidebar.markdown("---")
        st.sidebar.subheader("比較対象期間（過去）")
        comp_start_m = st.sidebar.selectbox("比較開始", all_months, index=min(1, len(all_months)-1), key="cc_s")
        comp_end_m = st.sidebar.selectbox("比較終了", all_months, index=min(1, len(all_months)-1), key="cc_e")

    # --- データ集計ロジック ---
    df_full = pd.merge(df_sales, df_master, on='ASIN', how='left').fillna({'コード':'N/A', '正式品名':'不明', '規格':'-'})
    
    def get_sum(df, s, e):
        mask = (df['年月'] >= s) & (df['年月'] <= e)
        return df[mask].groupby(['ASIN', 'コード', '正式品名', '規格']).agg({'売上':'sum', '数量':'sum'}).reset_index()

    main_res = get_sum(df_full, start_m, end_m)

    # --- メイン表示 ---
    st.title("Sales Performance Dashboard")
    
    m1, m2, m3 = st.columns(3)
    total_sales = main_res['売上'].sum()

    if mode == "比較モード":
        comp_res = get_sum(df_full, comp_start_m, comp_end_m)
        total_comp = comp_res['売上'].sum()
        growth = ((total_sales / total_comp) - 1) * 100 if total_comp > 0 else 0
        
        m1.metric("Selected Sales", f"¥{int(total_sales):,}", f"{growth:+.1f}%")
        m2.metric("Comparison Sales", f"¥{int(total_comp):,}")
    else:
        m1.metric("Total Sales", f"¥{int(total_sales):,}")
        m2.metric("Total Units", f"{int(main_res['数量'].sum()):,}")
    
    m3.metric("Product Count", f"{len(main_res):,}")

    st.markdown("---")
    st.subheader("売上詳細")

    # テーブル用データ作成
    if mode == "比較モード":
        # ASINを軸に「現在」と「比較」を横に並べる
        display_df = pd.merge(
            main_res, 
            comp_res[['ASIN', '売上', '数量']], 
            on='ASIN', 
            how='left', 
            suffixes=('', '_Comp')
        ).fillna(0)
        
        display_df['YoY/MoM (%)'] = ((display_df['売上'] / display_df['売上_Comp']) - 1) * 100
        display_df.loc[display_df['売上_Comp'] == 0, 'YoY/MoM (%)'] = 0
        
        display_df = display_df[['ASIN', 'コード', '正式品名', '売上', '売上_Comp', 'YoY/MoM (%)', '数量']]
        display_df.columns = ['ASIN', 'Code', 'Product Name', 'Sales (Now)', 'Sales (Comp)', 'Growth (%)', 'Qty']
        fmt = {'Sales (Now)': '¥{:,.0f}', 'Sales (Comp)': '¥{:,.0f}', 'Growth (%)': '{:+.1f}%', 'Qty': '{:,.0f}'}
    else:
        display_df = main_res[['ASIN', 'コード', '正式品名', '売上', '数量']]
        display_df.columns = ['ASIN', 'Code', 'Product Name', 'Sales', 'Qty']
        fmt = {'Sales': '¥{:,.0f}', 'Qty': '{:,.0f}'}

    # 検索機能
    search = st.text_input("Search (Product Name, Code, or ASIN)", "").lower()
    if search:
        display_df = display_df[
            display_df['Product Name'].str.lower().str.contains(search, na=False) | 
            display_df['Code'].astype(str).str.contains(search, na=False) | 
            display_df['ASIN'].str.lower().str.contains(search, na=False)
        ]

    # テーブル表示（確実に反映）
    st.dataframe(display_df.style.format(fmt), use_container_width=True, height=700)

except Exception as e:
    st.error(f"Error: {e}")