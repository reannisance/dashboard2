import streamlit as st
import pandas as pd
import numpy as np
import datetime as dt
import matplotlib.pyplot as plt
import plotly.express as px

def load_excel(file):
    xls = pd.ExcelFile(file)
    sheet = st.selectbox("Pilih sheet:", xls.sheet_names)
    df = pd.read_excel(xls, sheet_name=sheet)
    return df

def parse_tmt(tmt):
    if pd.isna(tmt): return None
    if isinstance(tmt, str):
        try:
            return pd.to_datetime(tmt, dayfirst=True)
        except:
            return None
    return pd.to_datetime(tmt, errors='coerce')

def generate_month_range(start_date, end_date):
    return pd.date_range(start=start_date, end=end_date, freq='MS')

def calculate_kepatuhan(row, pembayaran_bulan):
    bulan_tmt = row['TMT']
    tahun_pajak = int(row['TAHUN']) if 'TAHUN' in row else dt.datetime.now().year
    if pd.isna(bulan_tmt): return 0

    mulai = pd.Timestamp(bulan_tmt)
    akhir = pd.Timestamp(f"{tahun_pajak}-12-01")
    bulan_aktif = generate_month_range(mulai, akhir)
    bayar = pembayaran_bulan.get(row['NAMA OP'], [])

    if not bayar:
        return 0

    bayar_set = set(pd.to_datetime(bayar).to_period("M"))
    gap = 0
    max_gap = 0
    for bulan in bulan_aktif:
        if bulan.to_period("M") not in bayar_set:
            gap += 1
            max_gap = max(max_gap, gap)
        else:
            gap = 0
    return 0 if max_gap >= 3 else 100

def format_number(val):
    return f"{val:,.2f}" if pd.notna(val) else ""

st.set_page_config(layout="wide")
st.title("Dashboard Kepatuhan Pajak")

st.markdown("Silakan upload file Excel berisi data setoran masa pajak.")

uploaded_file = st.file_uploader("Upload File Excel", type=["xlsx"])

if uploaded_file:
    df = load_excel(uploaded_file)

    # Normalisasi kolom
    df.columns = [str(c).strip().upper() for c in df.columns]

# Definisikan alias kolom
    alias_columns = {
        'UPPPD': ['UPPPD', 'NAMA UNIT', 'NM UNIT'],
        'STATUS': ['STATUS'],
        'TMT': ['TMT'],
        'NAMA OP' : ['NAMA OP', 'OP', 'OBJEK PAJAK', 'NAMA OBJEK'],
        'KLASIFIKASI' : ['KATEGORI', 'KLASIFIKASI']
}

# Kolom wajib (harus ada)
    required_fields = ['UPPPD', 'STATUS', 'TMT']

# Buat mapping nama kolom sebenarnya dari df
    column_mapping = {}

    for standar, aliases in alias_columns.items():
        for alias in aliases:
            if alias in df.columns:
                column_mapping[standar] = alias
                break
        if standar not in column_mapping:
            st.error(f"Kolom untuk '{standar}' tidak ditemukan. Cek apakah nama kolomnya sesuai.")
            st.stop()

# Gunakan kolom standar
    df = df.rename(columns=column_mapping)

    jenis_pajak = st.selectbox("Pilih Jenis Pajak", ["MAKAN MINUM", "JASA KESENIAN DAN HIBURAN"])

    if jenis_pajak == "JASA KESENIAN DAN HIBURAN" and 'KLASIFIKASI' not in df.columns:
        st.error("Kolom 'KLASIFIKASI' wajib untuk jenis pajak HIBURAN.")
        st.stop()

    df['TMT'] = df['TMT'].apply(parse_tmt)
    df['TAHUN'] = df['TMT'].dt.year.fillna(dt.datetime.now().year).astype(int)

    pembayaran_cols = [c for c in df.columns if str(c).startswith("PEMBAYARAN")]
    df['TOTAL PEMBAYARAN'] = df[pembayaran_cols].fillna(0).sum(axis=1)

    # Simulasi histori pembayaran
    pembayaran_bulan = {}
    for _, row in df.iterrows():
        nama = row['NAMA OP']
        histori = []
        for col in pembayaran_cols:
            bulan = col.replace("PEMBAYARAN ", "")
            try:
                tanggal = pd.to_datetime(f"{bulan} 01", format="%B %Y %d", errors='coerce')
                if row[col] > 0:
                    histori.append(tanggal)
            except:
                pass
        pembayaran_bulan[nama] = histori

    df['KEPATUHAN (%)'] = df.apply(lambda row: calculate_kepatuhan(row, pembayaran_bulan), axis=1)

    # Format angka
    df['TOTAL PEMBAYARAN'] = df['TOTAL PEMBAYARAN'].apply(format_number)
    df['KEPATUHAN (%)'] = df['KEPATUHAN (%)'].map(lambda x: f"{x:.2f}%")

    with st.expander("Filter"):
        selected_upppd = st.multiselect("Filter UPPPD", options=df['UPPPD'].unique(), default=df['UPPPD'].unique())
        selected_status = st.multiselect("Filter STATUS", options=df['STATUS'].unique(), default=df['STATUS'].unique())
        if jenis_pajak == "JASA KESENIAN DAN HIBURAN":
            selected_KLASIFIKASI = st.multiselect("Filter KLASIFIKASI", options=df['KLASIFIKASI'].unique(), default=df['KLASIFIKASI'].unique())
        else:
            selected_KLASIFIKASI = None

    df_filtered = df[df['UPPPD'].isin(selected_upppd) & df['STATUS'].isin(selected_status)]
    if jenis_pajak == "JASA KESENIAN DAN HIBURAN" and selected_KLASIFIKASI is not None:
        df_filtered = df_filtered[df_filtered['KLASIFIKASI'].isin(selected_KLASIFIKASI)]

    st.dataframe(df_filtered)

    # Visualisasi Top 20 Pembayar
    df_vis = df.copy()
    df_vis['TOTAL PEMBAYARAN'] = df[pembayaran_cols].fillna(0).sum(axis=1)
    top20 = df_vis.sort_values("TOTAL PEMBAYARAN", ascending=False).head(20)
    fig1 = px.bar(top20, x="NAMA OP", y="TOTAL PEMBAYARAN", title="Top 20 WP berdasarkan Total Pembayaran")
    st.plotly_chart(fig1, use_container_width=True)

    # Visualisasi jumlah WP per klasifikasi kepatuhan
    df_kep = df.copy()
    df_kep['TINGKAT KEPATUHAN'] = df_kep['KEPATUHAN (%)'].str.replace('%','').astype(float).apply(
        lambda x: 'PATUH' if x == 100 else 'TIDAK PATUH')
    fig2 = px.bar(df_kep['TINGKAT KEPATUHAN'].value_counts().reset_index(), 
                 x='index', y='count', labels={'index':'Klasifikasi', 'count':'Jumlah WP'},
                 title="Jumlah WP per Tingkat Kepatuhan")
    st.plotly_chart(fig2, use_container_width=True)
