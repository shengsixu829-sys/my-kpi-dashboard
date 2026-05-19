# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
import requests
import os
import re
import base64

# --- 1. ページ基本設定 ---
st.set_page_config(page_title="ストアカルテ", layout="wide")

# 画像保存用のフォルダを自動作成
IMG_DIR = "saved_captures"
if not os.path.exists(IMG_DIR):
    os.makedirs(IMG_DIR)

# --- タイトル用ロゴ画像の読み込み ---
def get_logo():
    logo_path = "logo.png" 
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            data = base64.b64encode(f.read()).decode()
            return f"data:image/png;base64,{data}"
    return None

LOGO_DATA = get_logo()

# --- 2. Googleスプレッドシート接続設定 ---
@st.cache_resource
def get_gspread_auth():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return creds
    except Exception as e:
        st.error(f"認証エラー: {e}")
        return None

auth_creds = get_gspread_auth()
gc = gspread.authorize(auth_creds)

# データソースID
SPREADSHEET_ID = "1KlZevjH2IbsV0kWQZxw1QjHy3EmsjG9vTKGtvVVTni8"
SAVE_SHEET_ID = "1_8XbvigwRRIR-HxT5OEDlrKdpW8J9AjYYtjEk33LPIk"
TENPO_DATA_SP_ID = "1jJcIVOFTICCPr3YnoqkO-NxRzwTcvr_HfwgZunS0vdY"  # 店舗データ
WEEKLY_DATA_SP_ID = "1_lEdGhSnGzEIgMFn2Q_qUbCVIL35MVHQBxW0M_2TcyI" # KPI｜Weekly

# --- 3. シート自動検知ロジック ---
@st.cache_data(ttl=0)
def get_dynamic_month_config():
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheets = sh.worksheets()
        config = {}
        for ws in worksheets:
            title = ws.title.strip()
            if title.startswith("26"):
                nums = re.findall(r'\d+', title)
                if nums and len(nums[0]) >= 4:
                    month_num = int(nums[0][2:])
                    month_name = f"{month_num}月"
                    config[month_name] = str(ws.id)
        sorted_keys = sorted(config.keys(), key=lambda x: int(x.replace("月","")))
        return {k: config[k] for k in sorted_keys}
    except Exception as e:
        st.error(f"シート構成の取得に失敗しました: {e}")
        return {"3月": "1502960872", "4月": "166364340"}

DYNAMIC_MONTH_CONFIG = get_dynamic_month_config()

@st.cache_data(ttl=5)
def load_raw_data_auth(gid):
    try:
        import google.auth.transport.requests
        request = google.auth.transport.requests.Request()
        auth_creds.refresh(request)
        token = auth_creds.token
        export_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={gid}"
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(export_url, headers=headers)
        if response.status_code == 200:
            return pd.read_csv(io.BytesIO(response.content), header=None)
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# 新データソース読み込み関数
@st.cache_data(ttl=5)
def load_mall_mapping_and_weekly_data():
    try:
        # 1. 店舗データからマスターを取得 (C列:店舗名, S列:業態別)
        sh_tenpo = gc.open_by_key(TENPO_DATA_SP_ID)
        ws_tenpo = sh_tenpo.worksheet("店舗データ")
        df_tenpo = pd.DataFrame(ws_tenpo.get_all_values())
        
        mapping = {}
        for _, row in df_tenpo.iterrows():
            if len(row) > 18:
                store_name = str(row[2]).strip() # C列
                gyotai = str(row[18]).strip()    # S列
                if store_name and gyotai and "店舗名" not in store_name:
                    mapping[store_name] = gyotai

        # 2. KPI｜Weekly の Dataシートを取得
        sh_weekly = gc.open_by_key(WEEKLY_DATA_SP_ID)
        ws_weekly = sh_weekly.worksheet("Data")
        df_weekly = pd.DataFrame(ws_weekly.get_all_values())
        
        return mapping, df_weekly
    except Exception as e:
        st.error(f"新規データソースの読み込みに失敗しました: {e}")
        return {}, pd.DataFrame()

def get_score(df, row, col):
    try:
        val = df.iloc[row-1, col-1]
        if pd.isna(val): return 0
        s_val = str(val).replace(',','').replace('%','').replace('¥','').replace('円','').strip()
        return pd.to_numeric(s_val, errors='coerce') if s_val else 0
    except: return 0

# --- 4. テキストの読み書き ---
def fetch_sheet_text_live(search_key):
    try:
        sh = gc.open_by_key(SAVE_SHEET_ID)
        ws = sh.worksheet("シート1")
        all_data = ws.get_all_values()
        res = {"zasu": "", "tanka": "", "cvr": "", "kyaku": "", "summary": ""}
        search_key_clean = str(search_key).strip()
        for row in all_data:
            if row and str(row[0]).strip() == search_key_clean:
                res["zasu"] = str(row[1]) if len(row) > 1 else ""
                res["tanka"] = str(row[2]) if len(row) > 2 else ""
                res["cvr"] = str(row[3]) if len(row) > 3 else ""
                res["kyaku"] = row[4] if len(row) > 4 else ""
                res["summary"] = row[5] if len(row) > 5 else ""
                return res
        return res
    except:
        return {"zasu": "", "tanka": "", "cvr": "", "kyaku": "", "summary": ""}

def save_to_sheet_live(search_key, data_list):
    try:
        sh = gc.open_by_key(SAVE_SHEET_ID)
        ws = sh.worksheet("シート1")
        all_values = ws.get_all_values()
        target_row = -1
        search_key_clean = str(search_key).strip()
        for i, row in enumerate(all_values):
            if row and str(row[0]).strip() == search_key_clean:
                target_row = i + 1
                break
        final_row = [search_key_clean] + [str(d) for d in data_list]
        if target_row != -1:
            ws.update(range_name=f"A{target_row}:F{target_row}", values=[final_row])
        else:
            ws.append_row(final_row)
        return True
    except: return False

# ローカル環境への画像保存・取得用ヘルパー関数
def save_local_image(key, suffix, uploaded_file):
    if uploaded_file is not None:
        file_path = os.path.join(IMG_DIR, f"{key}_{suffix}.png")
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

def get_local_image_path(key, suffix):
    file_path = os.path.join(IMG_DIR, f"{key}_{suffix}.png")
    return file_path if os.path.exists(file_path) else None

# --- 5. サイドバー UI ---
st.sidebar.header("📅 期間選択")
sel_year = "2026"
sel_month = st.sidebar.selectbox("月", list(DYNAMIC_MONTH_CONFIG.keys()), index=len(DYNAMIC_MONTH_CONFIG)-1)

week_row_map = {"W1": 57, "W2": 58, "W3": 59, "W4": 60, "W5": 61, "W6": 62}

sel_week = st.sidebar.selectbox("週", list(week_row_map.keys()))
current_key = f"{sel_year}-{sel_month}-{sel_week}"
current_txt = fetch_sheet_text_live(current_key)

with st.sidebar.form("input_form"):
    st.info(f"📍 読込中キー: {current_key}" )
    r_zasu = st.text_area("座数の理由", value=current_txt["zasu"])
    r_tanka = st.text_area("客単価の理由", value=current_txt["tanka"])
    r_cvr = st.text_area("CVRの理由", value=current_txt["cvr"])
    r_kyaku = st.text_area("客数の理由", value=current_txt["kyaku"])
    
    st.markdown("<p style='font-size:0.85em; font-weight:bold; margin-bottom:-5px;'>📸 キャプチャ（画像）の添付</p>", unsafe_allow_html=True)
    img_juchu = st.file_uploader("1. 受注額のキャプチャ", type=["png", "jpg", "jpeg"])
    img_zasu = st.file_uploader("2. 座数のキャプチャ", type=["png", "jpg", "jpeg"])
    img_tanka = st.file_uploader("3. 客単価のキャプチャ", type=["png", "jpg", "jpeg"])
    img_cvr = st.file_uploader("4. CVRのキャプチャ", type=["png", "jpg", "jpeg"])
    img_kyaku = st.file_uploader("5. 客数のキャプチャ", type=["png", "jpg", "jpeg"])
    img_sonota = st.file_uploader("6. その他のキャプチャ", type=["png", "jpg", "jpeg"])
    
    sum_text = st.text_area("■総評 / 今週のアクション", value=current_txt["summary"], height=150)
    if st.form_submit_button("全ユーザーに共有保存"):
        if save_to_sheet_live(current_key, [r_zasu, r_tanka, r_cvr, r_kyaku, sum_text]):
            save_local_image(current_key, "juchu", img_juchu)
            save_local_image(current_key, "zasu", img_zasu)
            save_local_image(current_key, "tanka", img_tanka)
            save_local_image(current_key, "cvr", img_cvr)
            save_local_image(current_key, "kyaku", img_kyaku)
            save_local_image(current_key, "sonota", img_sonota)
            
            st.success("テキストおよび画像を保存しました！")
            st.cache_data.clear()
            st.rerun()

# --- 6. メイン表示 ---
current_gid = DYNAMIC_MONTH_CONFIG[sel_month]
df_raw = load_raw_data_auth(current_gid)

if not df_raw.empty:
    header_logo = f'<img src="{LOGO_DATA}" style="height: 50px; width: auto; border-radius: 4px; object-fit: contain;">' if LOGO_DATA else ""
    st.markdown(f'''
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 20px;">
        {header_logo}
        <h1 style="margin: 0; padding: 0; color: #3b484e; font-family: 'Meiryo', sans-serif; font-size: 2.2rem;">
            ストアカルテ {sel_year}年{sel_month}
        </h1>
    </div>
    ''', unsafe_allow_html=True)
    
    st.markdown('''
    <style>
        html, body, [class*="css"] { font-family: "Meiryo", sans-serif; color: #3b484e; }
        .reach { color: #58b5ca; font-weight: bold; }
        .unmet { color: #f3a359; font-weight: bold; }
        .base-table { width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 0.85em; background-color: white; }
        .base-table th { background-color: rgba(88, 181, 202, 0.9); color: white; padding: 8px; border: 1px solid #eeece1; text-align: center; }
        .base-table td { border: 1px solid #eeece1; padding: 8px; text-align: center; }
        .kpi-table th { background-color: #3F484F !important; color: #eeece1 !important; }
        .comment-cell { text-align: left !important; background-color: #fdfcf7 !important; white-space: pre-wrap; vertical-align: middle; color: #3b484e; font-size: 0.95em; }
        .summary-box { background-color: #e1f2f7; border: 1px solid #58b5ca; padding: 15px; border-radius: 4px; white-space: pre-wrap; color: #3b484e; min-height: 80px; }
        h4 { color: #3b484e; border-bottom: 2px solid #fcde9c; padding-bottom: 5px; margin-top: 25px; }
        .img-label { font-size: 0.9em; font-weight: bold; color: #3b484e; margin-bottom: 5px; border-left: 3px solid #58b5ca; padding-left: 6px; }
        .empty-box { border: 1px dashed #cccccc; padding: 20px; border-radius: 4px; text-align: center; color: #888888; font-size: 0.8em; background-color: #fafafa; }
    </style>
    ''', unsafe_allow_html=True)

    def fmt_v(val, cond, unit=""):
        cls = "reach" if cond else "unmet"
        t = f"{unit}{abs(val):,.0f}" if abs(val) >= 100 else f"{unit}{abs(val):.2f}"
        return f'<span class="{cls}">{t}</span>'

    def fmt_p(val, cond):
        cls = "reach" if cond else "unmet"
        return f'<span class="{cls}">{val:.1f}%</span>'

    # All Stores 集計
    act = sum([get_score(df_raw, i, 6) for i in range(12, 54)])
    tgt, bgt, ly = get_score(df_raw, 3, 7), get_score(df_raw, 3, 9), get_score(df_raw, 3, 11)
    mt, mb, ml = get_score(df_raw, 6, 7), get_score(df_raw, 6, 9), get_score(df_raw, 6, 11)

    st.markdown("<h4>All Stores ※FC excluded</h4>", unsafe_allow_html=True)
    st.markdown(f'''
    <table class="base-table">
        <tr><th style="background-color:#606970;">月次受注額</th><td colspan="5" style="font-size:1.2em;font-weight:bold;">{act:,.0f}</td></tr>
        <tr><th>月次目標</th><td>{tgt:,.0f}</td><th>月次予算</th><td>{bgt:,.0f}</td><th>前年受注額</th><td>{ly:,.0f}</td></tr>
        <tr><th>目標比</th><td>{fmt_p(act/tgt*100 if tgt else 0, act>=tgt)}</td><th>予算比</th><td>{fmt_p(act/bgt*100 if bgt else 0, act>=bgt)}</td><th>前年比</th><td>{fmt_p(act/ly*100 if ly else 0, act>=ly)}</td></tr>
        <tr><th>差額</th><td>{fmt_v(act-tgt, act>=tgt)}</td><th>差額</th><td>{fmt_v(act-bgt, act>=bgt)}</td><th>差額</th><td>{fmt_v(act-ly, act>=ly)}</td></tr>
        <tr><th>MTD目標</th><td>{mt:,.0f}</td><th>MTD予算</th><td>{mb:,.0f}</td><th>MTD前年</th><td>{ml:,.0f}</td></tr>
        <tr><th>MTD目標%</th><td>{fmt_p(act/mt*100 if mt else 0, act>=mt)}</td><th>MTD予算%</th><td>{fmt_p(act/mb*100 if mb else 0, act>=mb)}</td><th>MTD前年%</th><td>{fmt_p(act/ml*100 if ml else 0, act>=ml)}</td></tr>
        <tr><th>MTD目標 差額</th><td>{fmt_v(act-mt, act>=mt)}</td><th>MTD予算 差額</th><td>{fmt_v(act-mb, act>=mb)}</td><th>MTD前年 差額</th><td>{fmt_v(act-ml, act>=ml)}</td></tr>
    </table>
    ''', unsafe_allow_html=True)

    # Weeklyサマリー
    st.markdown("<h4>WEEKサマリー</h4>", unsafe_allow_html=True)
    w_rows = ""
    for w_n, r_i in week_row_map.items():
        wa, wt, wb, wl = get_score(df_raw, r_i, 6), get_score(df_raw, r_i, 7), get_score(df_raw, r_i, 10), get_score(df_raw, r_i, 13)
        w_rows += f'<tr><td>{w_n}</td><td>{wa:,.0f}</td><td>{wt:,.0f}</td><td>{fmt_v(wa-wt, wa>=wt)}</td><td>{fmt_p(wa/wt*100 if wt else 0, wa>=wt)}</td><td>{wb:,.0f}</td><td>{fmt_v(wa-wb, wa>=wb)}</td><td>{fmt_p(wa/wb*100 if wb else 0, wa>=wb)}</td><td>{wl:,.0f}</td><td>{fmt_p(wa/wl*100 if wl else 0, wa>=wl)}</td></tr>'
    st.markdown(f'<table class="base-table"><tr><th>WEEK</th><th>受注額</th><th>目標</th><th>差額</th><th>達成率</th><th>予算</th><th>差額</th><th>達成率</th><th>前年実績</th><th>前年比</th></tr>{w_rows}</table>', unsafe_allow_html=True)

    # KPI別サマリー
    current_week_row_idx = week_row_map[sel_week]
    st.markdown(f"<h4>KPI別 ({sel_week})</h4>", unsafe_allow_html=True)
    k_data = [("座数", 44, 48, 52, "zasu"), ("客単価", 47, 51, 55, "tanka"), ("CVR", 45, 49, 53, "cvr"), ("客数", 46, 50, 54, "kyaku")]
    k_rows = ""
    for k_n, ac, tc, lc, t_k in k_data:
        av, tv, lv = get_score(df_raw, current_week_row_idx, ac), get_score(df_raw, current_week_row_idx, tc), get_score(df_raw, current_week_row_idx, lc)
        u = "¥" if k_n == "客単価" else ""
        m = "◯" if (av/tv if tv else 0) >= 1 else "△" if (av/tv if tv else 0) >= 0.9 else "✕"
        t_s = f"{u}{tv:,.0f}" if tv >= 100 else f"{u}{tv:.2f}"
        reason = str(current_txt[t_k]).replace("\n", "<br>")
        k_rows += f'<tr><td>{m}</td><td>{k_n}</td><td>{t_s}</td><td>{fmt_v(av, av>=tv, u)}</td><td>{fmt_p(av/tv*100 if tv else 0, av>=tv)}</td><td>{fmt_p(av/lv*100 if lv else 0, av>=lv)}</td><td class="comment-cell">{reason}</td></tr>'
    st.markdown(f'<table class="base-table kpi-table"><tr><th>評</th><th>KPI</th><th>目標</th><th>実績</th><th>目標比</th><th>LY比</th><th>理由</th></tr>{k_rows}</table>', unsafe_allow_html=True)

    # --- KPIグラフ ---
    st.markdown("<h4>📋 KPIグラフ(１ストア平均)</h4>", unsafe_allow_html=True)
    
    p_juchu = get_local_image_path(current_key, "juchu")
    p_zasu = get_local_image_path(current_key, "zasu")
    p_tanka = get_local_image_path(current_key, "tanka")
    p_cvr = get_local_image_path(current_key, "cvr")
    p_kyaku = get_local_image_path(current_key, "kyaku")
    p_sonota = get_local_image_path(current_key, "sonota")

    row1_col1, row1_col2, row1_col3 = st.columns(3)
    with row1_col1:
        st.markdown('<div class="img-label">受注</div>', unsafe_allow_html=True)
        if p_juchu: st.image(p_juchu, use_container_width=True)
        else: st.markdown('<div class="empty-box">未アップロード</div>', unsafe_allow_html=True)
    with row1_col2:
        st.markdown('<div class="img-label">座数</div>', unsafe_allow_html=True)
        if p_zasu: st.image(p_zasu, use_container_width=True)
        else: st.markdown('<div class="empty-box">未アップロード</div>', unsafe_allow_html=True)
    with row1_col3:
        st.markdown('<div class="img-label">客単価</div>', unsafe_allow_html=True)
        if p_tanka: st.image(p_tanka, use_container_width=True)
        else: st.markdown('<div class="empty-box">未アップロード</div>', unsafe_allow_html=True)
            
    st.write("")
    row2_col1, row2_col2, row2_col3 = st.columns(3)
    with row2_col1:
        st.markdown('<div class="img-label">CVR</div>', unsafe_allow_html=True)
        if p_cvr: st.image(p_cvr, use_container_width=True)
        else: st.markdown('<div class="empty-box">未アップロード</div>', unsafe_allow_html=True)
    with row2_col2:
        st.markdown('<div class="img-label">客数</div>', unsafe_allow_html=True)
        if p_kyaku: st.image(p_kyaku, use_container_width=True)
        else: st.markdown('<div class="empty-box">未アップロード</div>', unsafe_allow_html=True)
    with row2_col3:
        st.markdown('<div class="img-label">その他</div>', unsafe_allow_html=True)
        if p_sonota: st.image(p_sonota, use_container_width=True)
        else: st.markdown('<div class="empty-box">未アップロード</div>', unsafe_allow_html=True)

    # --- 📊 モール別MTD (過去10週推移・柔軟検索版) ---
    st.markdown("<h4>📊 モール別MTD (過去10週推移)</h4>", unsafe_allow_html=True)
    
    mall_mapping, df_weekly = load_mall_mapping_and_weekly_data()
    
    if not df_weekly.empty and mall_mapping:
        header_row = [str(x).strip() for x in df_weekly.iloc[0].tolist()]
        
        # 🌟 【修正ポイント】どのような日付の形式（26/05, 2026-05, 5/）でもヒットする柔軟な判定ロジック
        month_digit = str(sel_month).replace("月", "")
        month_digit_z = month_digit.zfill(2)
        
        matched_cols = []
        for i, h in enumerate(header_row):
            # 例: "26/05/", "2026-05-", "/5/" 等を検出
            if f"26/{month_digit_z}/" in h or f"2026-{month_digit_z}-" in h or h.startswith(f"{month_digit}/") or f"/{month_digit}/" in h:
                matched_cols.append(i)
        
        week_idx = ["W1","W2","W3","W4","W5","W6"].index(sel_week) if sel_week in ["W1","W2","W3","W4","W5","W6"] else 0
        
        # マッチする列が見つかった場合の処理。見つからなければ最終列から遡る
        if matched_cols:
            base_col_idx = matched_cols[min(week_idx, len(matched_cols)-1)]
        else:
            base_col_idx = len(header_row) - 1
            
        # 過去10週分の列を安全に抽出
        ten_weeks_indices = []
        for step in range(10):
            target_idx = base_col_idx - step
            if target_idx >= 5:  # F列以降を対象にする
                ten_weeks_indices.append(target_idx)
                
        # 指定の業態順
        target_gyotais = ["全体", "路面店", "イオンモール", "ららぽーと", "アウトレット", "MARK IS", "アミュプラザ", "駅ビル", "ショッピングモール"]
        
        report_data = {g: {"count": 0, "weeks": {idx: 0 for idx in ten_weeks_indices}} for g in target_gyotais}
        unique_stores_by_gyotai = {g: set() for g in target_gyotais}
        
        # クロスチェック合算処理
        for r_idx in range(1, len(df_weekly)):
            store_name = str(df_weekly.iloc[r_idx, 1]).strip() # B列
            kpi_name = str(df_weekly.iloc[r_idx, 4]).strip()   # E列
            
            if store_name in mall_mapping and "受注金額(税抜)" in kpi_name:
                gyotai = mall_mapping[store_name]
                if gyotai in report_data:
                    unique_stores_by_gyotai[gyotai].add(store_name)
                    unique_stores_by_gyotai["全体"].add(store_name)
                    
                    for c_idx in ten_weeks_indices:
                        val_str = str(df_weekly.iloc[r_idx, c_idx]).replace(',','').replace('¥','').strip()
                        val = pd.to_numeric(val_str, errors='coerce') if val_str else 0
                        if not pd.isna(val):
                            report_data[gyotai]["weeks"][c_idx] += val
                            report_data["全体"]["weeks"][c_idx] += val

        for g in target_gyotais:
            report_data[g]["count"] = len(unique_stores_by_gyotai[g])

        header_html = "<tr><th>業態</th><th>ストア数</th><th>受注実績</th><th>売上シェア</th>"
        for c_idx in ten_weeks_indices:
            header_html += f"<th>{header_row[c_idx]}</th>"
        header_html += "</tr>"
        
        rows_html = ""
        base_week_col = ten_weeks_indices[0] if ten_weeks_indices else 0
        total_base_juchu = report_data["全体"]["weeks"].get(base_week_col, 0)
        
        for g in target_gyotais:
            g_count = report_data[g]["count"]
            g_base_juchu = report_data[g]["weeks"].get(base_week_col, 0)
            
            share = (g_base_juchu / total_base_juchu * 100) if total_base_juchu else 0
            if g == "全体": share = 100.0
            
            style_attr = ' style="background-color:#f0f2f6; font-weight:bold;"' if g == "全体" else ""
            row_str = f"<tr{style_attr}><td>{g}</td><td>{g_count}</td><td>{g_base_juchu:,.0f}</td><td>{share:.2f}%</td>"
            
            for c_idx in ten_weeks_indices:
                w_total = report_data["全体"]["weeks"].get(c_idx, 0)
                w_juchu = report_data[g]["weeks"].get(c_idx, 0)
                w_share = (w_juchu / w_total * 100) if w_total else 0
                if g == "全体": w_share = 100.0
                row_str += f"<td>{w_share:.2f}%</td>"
                
            row_str += "</tr>"
            rows_html += row_str
            
        st.markdown(f'<table class="base-table">{header_html}{rows_html}</table>', unsafe_allow_html=True)
    else:
        st.info("KPI｜Weekly からデータを取得中、またはマッピング情報を照合中です...")

    # 総評
    st.markdown("<h4>■総評 / 今週のアクション</h4>", unsafe_allow_html=True)
    st.markdown(f'<div class="summary-box">{str(current_txt["summary"])}</div>', unsafe_allow_html=True)
else:
    st.warning("数値データを読み込めませんでした。")
