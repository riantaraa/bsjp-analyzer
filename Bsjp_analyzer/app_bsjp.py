import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta
from datetime import datetime

# --- KONFIGURASI HALAMAN ---
st.set_page_config(page_title="AI BSJP Analyzer", page_icon="📈", layout="wide")

# --- INISIALISASI SESSION STATE ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

# --- FUNGSI UTAMA APLIKASI BSJP ---
def main_app():
    st.title("📈 AI BSJP ANALYZER")
    st.markdown("**Mesin Kuantitatif Pencari *True Breakout* (SOP Koko Cuan) - 3 Tahun Data**")
    
    st.info(f"👤 Selamat datang, **{st.session_state.username}**! Masa aktif langganan diverifikasi.")
    st.markdown("---")

    col_search, _ = st.columns()
    with col_search:
        ticker_input = st.text_input("🔍 Masukkan kode emiten (contoh: DSNG, APLN):", "").upper()

    if ticker_input:
        daftar_saham = [s.strip() for s in ticker_input.split(',')]
        
        for t in daftar_saham:
            if not t: continue
            ticker = t if t.endswith(".JK") else t + ".JK"
            nama_saham = ticker.replace('.JK', '')
            
            st.header(f"📊 Analisa Saham: {nama_saham}")
            
            with st.spinner(f"Membedah anatomi bandar {nama_saham}..."):
                try:
                    stock = yf.Ticker(ticker)
                    df = stock.history(period="3y")
                    if df.empty or len(df) < 60:
                        st.error("⚠️ Data tidak cukup.")
                        continue

                    df['MA20'] = ta.sma(df['Close'], length=20)
                    df['MA50'] = ta.sma(df['Close'], length=50)
                    df['Vol_MA20'] = ta.sma(df['Volume'], length=20)
                    stoch = ta.stochrsi(df['Close'], length=14, rsi_length=14, k=3, d=3)
                    if stoch is not None and not stoch.empty:
                        df['stoch_k'] = stoch.iloc[:, 0]; df['stoch_d'] = stoch.iloc[:, 1]
                    else:
                        df['stoch_k'] = 50; df['stoch_d'] = 50
                        
                    df['Next_Open'] = df['Open'].shift(-1)
                    df['Next_High'] = df['High'].shift(-1)
                    df['Next_Close'] = df['Close'].shift(-1)
                    df['Next_Date'] = df.index.to_series().shift(-1)
                    df = df.dropna(subset=['MA50'])

                    now = df.iloc[-1]
                    prev = df.iloc[-2]
                    current_price = now['Close']
                    change_pct = ((current_price - prev['Close']) / prev['Close']) * 100
                    
                    st.subheader("🏷️ Snapshot Harga Hari Ini")
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Harga Saat Ini", f"Rp {int(current_price):,}", f"{change_pct:+.2f}%")
                    m2.metric("Open", f"Rp {int(now['Open']):,}")
                    m3.metric("High", f"Rp {int(now['High']):,}")
                    m4.metric("Low", f"Rp {int(now['Low']):,}")
                    m5.metric("Volume (Lot)", f"{int(now['Volume']):,}")

                    df_history = df.iloc[:-1].copy()
                    df_history['Rolling_Max_5'] = df_history['High'].rolling(5, center=True).max()
                    peaks = df_history[df_history['High'] == df_history['Rolling_Max_5']]
                    higher_peaks = peaks[peaks['High'] > current_price]
                    if not higher_peaks.empty:
                        atap_terdekat = higher_peaks.iloc[-1]['High']
                        jarak_atap = ((atap_terdekat - current_price) / current_price) * 100
                        c_clear = jarak_atap > 5.0
                        atap_text = f"Rp {int(atap_terdekat):,} (Jarak: {jarak_atap:.1f}%)"
                    else:
                        c_clear = True
                        atap_text = "All Time High"

                    def get_breakout_history(ma_line, ma_name):
                        kondisi = (
                            (df_history['Close'] > df_history['Open']) & 
                            (df_history['Close'] > df_history[ma_line]) & 
                            (df_history['Low'] <= (df_history[ma_line] * 1.01)) & 
                            (df_history['Volume'] >= (1.5 * df_history['Vol_MA20'])) & 
                            (df_history['Close'] >= (0.97 * df_history['High']))
                        )
                        df_trig = df_history[kondisi]
                        if len(df_trig) == 0: return 0, 0, 0, 0, f"Belum ada sejarah.", ""
                        
                        pos_count = neg_count = neu_count = 0
                        text = ""
                        for date, row in df_trig.iterrows():
                            close_sore = row['Close']
                            gap_open_pct = round(((row['Next_Open'] - close_sore) / close_sore) * 100, 2)
                            max_high_pct = round(((row['Next_High'] - close_sore) / close_sore) * 100, 2)
                            close_besok_pct = round(((row['Next_Close'] - close_sore) / close_sore) * 100, 2)
                            
                            if gap_open_pct >= 2.0: status = "🔥 SUKSES"; pos_count += 1
                            elif gap_open_pct <= -1.0: status = "❌ GAGAL PHP"; neg_count += 1
                            elif gap_open_pct >= 0.0 and close_besok_pct >= 1.0: status = "✅ WATCHOUT POSITIVE"; pos_count += 1
                            elif gap_open_pct == 0.0 and close_besok_pct == 0.0: status = "➖ WATCHOUT NETRAL"; neu_count += 1
                            elif gap_open_pct == 0.0 and close_besok_pct < 0.0: status = "⚠️ WATCHOUT NEGATIF"; neg_count += 1
                            else:
                                if close_besok_pct > 0: status = "✅ WATCHOUT POSITIVE"; pos_count += 1
                                elif close_besok_pct < 0: status = "⚠️ WATCHOUT NEGATIF"; neg_count += 1
                                else: status = "➖ WATCHOUT NETRAL"; neu_count += 1
                                
                            date_str = date.strftime('%d %b %Y')
                            next_date_str = row['Next_Date'].strftime('%d %b %Y') if pd.notnull(row['Next_Date']) else "N/A"
                            status_padded = status.ljust(19)
                            text += f"- {date_str} ➔ {next_date_str} : {status_padded} | Buka: {gap_open_pct:+.1f}% | Max: {max_high_pct:+.1f}% | Tutup: {close_besok_pct:+.1f}%\n"

                        win_rt = (pos_count / len(df_trig)) * 100
                        header = f"Positif **{pos_count}x** | Netral **{neu_count}x** | Negatif **{neg_count}x** (Win Rate: **{win_rt:.1f}%**)"
                        return pos_count, neg_count, neu_count, win_rt, header, text

                    pos_ma20, neg_ma20, neu_ma20, win_rt_ma20, header_ma20, detail_ma20 = get_breakout_history('MA20', 'MA20')
                    _, _, _, win_rt_ma50, header_ma50, detail_ma50 = get_breakout_history('MA50', 'MA50')

                    c_wajar = change_pct < 30.0
                    c_candle = current_price >= (0.97 * now['High'])
                    c_vol = now['Volume'] >= (1.5 * now['Vol_MA20'])
                    c_stoch = now['stoch_k'] > now['stoch_d']
                    c_break_ma20 = (current_price > now['MA20']) and (now['Low'] <= (now['MA20'] * 1.01))
                    
                    if c_break_ma20:
                        if pos_ma20 > neg_ma20: trend_status_str = "✅ PASS (Mayoritas Historis Positif)"; c_trend_pass = True
                        elif neg_ma20 > pos_ma20: trend_status_str = "❌ FAIL (Mayoritas Historis Negatif)"; c_trend_pass = False
                        else: trend_status_str = "➖ NETRAL (Historis Seimbang)"; c_trend_pass = True
                    else:
                        trend_status_str = "❌ FAIL (Bukan True Breakout MA20 Hari Ini)"
                        c_trend_pass = False

                    st.subheader("📋 CEK SOP FINAL (LAPIS 2)")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("**1. Cek Candle & Kenaikan:**")
                        st.write(f"{'✅' if c_wajar else '❌'} Kenaikan Wajar (<30%)")
                        st.write(f"{'✅' if c_candle else '❌'} Close dekat High")
                        st.markdown("**2. Cek 'Clear Skies':**")
                        st.write(f"{'✅' if c_clear else '❌'} Jarak Atap > 5% *(Resist: {atap_text})*")
                    with col2:
                        st.markdown("**3. Sinyal Pendukung Tambahan:**")
                        st.write(f"Trend Saat Ini: **{trend_status_str}**")
                        st.write(f"{'✅' if c_vol else '❌'} Volume Spike (>1.5x)")
                        st.write(f"{'✅' if c_stoch else '❌'} Momentum (StochRSI Golden)")

                    st.markdown("---")
                    st.subheader("🕰️ Track Record Bandar (3 Tahun)")
                    with st.expander(f"📊 Buka Histori MA20 - Skor: {header_ma20}", expanded=True):
                        if detail_ma20: st.code(detail_ma20, language='text')
                        else: st.info("Belum ada riwayat breakout MA20.")
                    with st.expander(f"📊 Buka Histori MA50 - Skor: {header_ma50}", expanded=False):
                        if detail_ma50: st.code(detail_ma50, language='text')
                        else: st.info("Belum ada riwayat breakout MA50.")

                    st.markdown("---")
                    syarat_utama = c_wajar and c_candle and c_clear and c_trend_pass and c_vol
                    if syarat_utama and win_rt_ma20 >= 60:
                        st.success(f"### 🚀 BUNGKUS! (HAKA di IEP + 5 Tick)\nProbabilitas: {win_rt_ma20:.1f}%.")
                    elif syarat_utama and win_rt_ma20 < 60:
                        st.warning(f"### 👍 HATI-HATI (MODERATE)\nProbabilitas: {win_rt_ma20:.1f}%.")
                    else:
                        st.error("### 🛑 ABAIKAN (SKIP)\nSyarat utama gagal.")

                except Exception as e:
                    st.error(f"Error: {e}")
                    
    # Tombol Logout
    st.sidebar.title("Navigasi")
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.rerun()

# --- GERBANG LOGIN ---
if not st.session_state.logged_in:
    _, col_login, _ = st.columns([1, 1.5, 1])
    with col_login:
        st.title("🔐 Login Member VIP")
        st.markdown("Silakan masukkan akun berlangganan Anda.")
        
        with st.form("login_form"):
            user_input = st.text_input("Username")
            pass_input = st.text_input("Password", type="password")
            submit_button = st.form_submit_button("Login Sekarang", use_container_width=True)
            
            if submit_button:
                if not user_input or not pass_input:
                    st.warning("Username dan Password harus diisi.")
                else:
                    with st.spinner("Memverifikasi data langganan..."):
                        try:
                            # HACK MEMBACA GOOGLE SHEETS TANPA SECRETS
                            # Mengambil ID dari screenshot kamu
                            sheet_id = "1uBRvNXmDLKo38XPjWpAkd3_ObESaBjc6HFdVKjF34KE"
                            sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
                            
                            # Pandas membaca link tersebut sebagai CSV (Jauh lebih cepat dan stabil)
                            users_df = pd.read_csv(sheet_url)
                            
                            user_data = users_df[users_df['Username'] == user_input]
                            if not user_data.empty:
                                if str(user_data.iloc['Password']) == pass_input:
                                    exp_date_str = str(user_data.iloc['Expired_Date'])
                                    exp_date = pd.to_datetime(exp_date_str).date()
                                    hari_ini = datetime.now().date()
                                    
                                    if hari_ini <= exp_date:
                                        st.session_state.logged_in = True
                                        st.session_state.username = user_input
                                        st.success("Login Berhasil!")
                                        st.rerun() 
                                    else:
                                        st.error(f"❌ Akun kedaluwarsa sejak {exp_date}. Hubungi Admin untuk perpanjang.")
                                else:
                                    st.error("❌ Password salah.")
                            else:
                                st.error("❌ Username tidak terdaftar.")
                        except Exception as e:
                            # Jika error, tampilkan detail kesalahannya
                            st.error(f"Gagal membaca data dari Google Sheets. Detail Error: {e}")
else:
    main_app()
