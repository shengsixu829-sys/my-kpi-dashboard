# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import io
import requests
import os
import re

# --- 1. ページ基本設定 ---
st.set_page_config(page_title="ストアカルテ", layout="wide")

# --- タイトル用ロゴ画像の読み込み ---
def get_logo():
    logo_path = "logo.png" 
    if os.path.exists(logo_path):
        import base64
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

# 既存のデータソースID
SPREADSHEET_ID = "1KlZevjH2IbsV0kWQZxw1QjHy3EmsjG9vTKGtvVVTni8"
SAVE_SHEET_ID = "1_8XbvigwRRIR-HxT5OEDlrKdpW8J9AjYYtjEk33LPIk"

# 🌟 新規データソースID
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

# 🌟 新データソース読み込み関数
@st.cache_data(ttl=10)
def load_mall_mapping_and_weekly_data():
    try:
        # 1. 店舗データからマスターを取得 (C列:店舗名, S列:業態別)
        sh_tenpo = gc.open_by_key(TENPO_DATA_SP_ID)
        ws_tenpo = sh_tenpo.worksheet("店舗データ")
        df_tenpo = pd.DataFrame(ws_tenpo.get_all_values())
        
        # ヘッダー判定とマッピング作成
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

# --- 4. テキスト読み書き ---
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

# --- 5. サイドバー UI ---
st.sidebar.header("📅 期間選択")
sel_year = "2026"
sel_month = st.sidebar.selectbox("月", list(DYNAMIC_MONTH_CONFIG.keys()), index=len(DYNAMIC_MONTH_CONFIG)-1)

week_row_map = {"W1": 57, "W2": 58, "W3": 59, "W4": 60, "W5": 61, "W6": 62}
week_juchu_start_map = {"W1": 12, "W2": 19, "W3": 26, "W4": 33, "W5": 40, "W6": 47}

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
            st.success("保存完了！")
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

    # KPIグラフ
    st.markdown("<h4>📋 KPIグラフ(１ストア平均)</h4>", unsafe_allow_html=True)
    row1_col1, row1_col2, row1_col3 = st.columns(3)
    with row1_col1:
        st.markdown('<div class="img-label">受注</div>', unsafe_allow_html=True)
        if img_juchu is not None: st.image(img_juchu, use_container_width=True)
        else: st.markdown('<div class="empty-box">未アップロード</div>', unsafe_allow_html=True)
    with row1_col2:
        st.markdown('<div class="img-label">座数</div>', unsafe_allow_html=True)
        if img_zasu is not None: st.image(img_zasu, use_container_width=True)
        else: st.markdown('<div class="empty-box">未アップロード</div>', unsafe_allow_html=True)
    with row1_col3:
        st.markdown('<div class="img-label">客単価</div>', unsafe_allow_html=True)
        if img_tanka is not None: st.image(img_tanka, use_container_width=True)
        else: st.markdown('<div class="empty-box">未アップロード</div>', unsafe_allow_html=True)
            
    st.write("")
    row2_col1, row2_col2, row2_col3 = st.columns(3)
    with row2_col1:
        st.markdown('<div class="img-label">CVR</div>', unsafe_allow_html=True)
        if img_cvr is not None: st.image(img_cvr, use_container_width=True)
        else: st.markdown('<div class="empty-box">未アップロード</div>', unsafe_allow_html=True)
    with row2_col2:
        st.markdown('<div class="img-label">客数</div>', unsafe_allow_html=True)
        if img_kyaku is not None: st.image(img_kyaku, use_container_width=True)
        else: st.markdown('<div class="empty-box">未アップロード</div>', unsafe_allow_html=True)
    with row2_col3:
        st.markdown('<div class="img-label">その他</div>', unsafe_allow_html=True)
        if img_sonota is not None: st.image(img_sonota, use_container_width=True)
        else: st.markdown('<div class="empty-box">未アップロード</div>', unsafe_allow_html=True)

    # --- 🛠️ 業態別・過去10週マトリクス表の大改修パーツ ---
    st.markdown("<h4>📊 モール別MTD (過去10週推移)</h4>", unsafe_allow_html=True)
    
    # 新データソースの読み込み
    mall_mapping, df_weekly = load_mall_mapping_and_weekly_data()
    
    if not df_weekly.empty and mall_mapping:
        # スプレッドシート側の1行目（日付行）の整形
        header_row = [str(x).strip() for x in df_weekly.iloc[0].tolist()]
        
        # 月次・週次のセレクトボックス状態から基準日(ターゲット)を推測するロジック
        # ※実際のアプリでの日付規則（例: 26/05/11）に合わせてターゲットとなる文字列を作成
        month_digit = str(sel_month).replace("月", "").zfill(2)
        
        # Dataシートの右側（最新日付側）から、選択された月に合う「月曜日の列」を自動サーチ
        target_date_str = f"26/{month_digit}/"
        matched_cols = [i for i, h in enumerate(header_row) if h.startswith(target_date_str)]
        
        # 該当週(W1〜W6)に応じて列をピックアップ（無ければ最新の列を基準にする）
        week_idx = ["W1","W2","W3","W4","W5","W6"].index(sel_week) if sel_week in ["W1","W2","W3","W4","W5","W6"] else 0
        
        if matched_cols:
            # 週の選択に合わせてインデックスを決定（範囲外防御付き）
            base_col_idx = matched_cols[min(week_idx, len(matched_cols)-1)]
        else:
            # マッチしなければ一番右端（最新の日付列）をベースにする
            base_col_idx = len(header_row) - 1
            
        # 基準列から左側に向かって10週分の列インデックスを並べる
        ten_weeks_indices = []
        for step in range(10):
            target_idx = base_col_idx - step
            if target_idx >= 4: # B列(ストア名)より右側であること
                ten_weeks_indices.append(target_idx)
                
        # 表示対象の業態定義（ご指定の並び順）
        target_gyotais = ["全体", "路面店", "イオンモール", "ららぽーと", "アウトレット", "MARK IS", "アミュプラザ", "駅ビル", "ショッピングモール"]
        
        # 集計用コンテナの用意
        # { 業態名: { 'count': ストア数, 'weeks': { 列インデックス: 合計金額, ... } } }
        report_data = {g: {"count": 0, "weeks": {idx: 0 for idx in ten_weeks_indices}} for g in target_gyotais}
        
        # B列(ストア名)をベースにスキャン・集計
        for r_idx in range(1, len(df_weekly)):
            store_name = str(df_weekly.iloc[r_idx, 1]).strip() # B列
            
            if store_name in mall_mapping:
                gyotai = mall_mapping[store_name]
                if gyotai in report_data:
                    # ストア数の加算（重複なしの1ストア分としてカウントするため基準週のみで判断）
                    report_data[gyotai]["count"] += 1
                    report_data["全体"]["count"] += 1
                    
                    # 10週分の受注金額を累積
                    for c_idx in ten_weeks_indices:
                        val_str = str(df_weekly.iloc[r_idx, c_idx]).replace(',','').replace('¥','').strip()
                        val = pd.to_numeric(val_str, errors='coerce') if val_str else 0
                        if not pd.isna(val):
                            report_data[gyotai]["weeks"][c_idx] += val
                            report_data["全体"]["weeks"][c_idx] += val

        # テーブルのヘッダーHTMLの作成
        header_html = "<tr><th>業態</th><th>ストア数</th><th>受注実績</th><th>売上シェア</th>"
        for c_idx in ten_weeks_indices:
            header_html += f"<th>{header_row[c_idx]}</th>"
        header_html += "</tr>"
        
        # テーブルのデータ行の作成
        rows_html = ""
        base_week_col = ten_weeks_indices[0] if ten_weeks_indices else 0
        total_base_juchu = report_data["全体"]["weeks"].get(base_week_col, 0)
        
        for g in target_gyotais:
            g_count = report_data[g]["count"]
            g_base_juchu = report_data[g]["weeks"].get(base_week_col, 0)
            
            # シェア率の算出
            share = (g_base_juchu / total_base_juchu * 100) if total_juchu_all_stores else 0
            if g == "全体": share = 100.0
            
            # 特徴的なスタイル属性
            style_attr = ' style="background-color:#f0f2f6; font-weight:bold;"' if g == "全体" else ""
            
            row_str = f"<tr{style_attr}><td>{g}</td><td>{g_count}</td><td>{g_base_juchu:,.0f}</td><td>{share:.2f}%</td>"
            
            # 残りの過去9週分のシェア推移を横に並べる
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
