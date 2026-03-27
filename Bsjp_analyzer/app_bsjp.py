import streamlit as st
import yfinance as yf
import pandas as pd
import pandas_ta as ta

# --- KONFIGURASI HALAMAN WEB ---
# Mengatur judul tab browser, ikon, dan layout lebar agar sedap dipandang
st.set_page_config(page_title="AI BSJP Analyzer", page_icon="📈", layout="wide")

# --- HEADER UI ---
st.title("📈 AI BSJP ANALYZER")
st.markdown("**Mesin Kuantitatif Pencari *True Breakout* (SOP Koko Cuan) - 3 Tahun Data**")
st.markdown("---")

# --- KOTAK INPUT SAHAM ---
# Membuat dua kolom: kolom kiri sempit untuk input, kolom kanan kosong untuk spacing
# PERBAIKAN BUG: di bawah ini memperbaiki error 'missing positional argument: spec'
col_search, _ = st.columns(2)
with col_search:
    ticker_input = st.text_input("🔍 Masukkan kode emiten (contoh: DSNG, APLN):", "").upper()

# Hanya eksekusi analisa jika user sudah mengetikkan kode saham
if ticker_input:
    daftar_saham = [s.strip() for s in ticker_input.split(',')]
    
    # Loop jika user memasukkan banyak saham sekaligus (dipisah koma)
    for t in daftar_saham:
        if not t: continue
        
        # Menambahkan akhiran .JK otomatis jika belum ada
        ticker = t if t.endswith(".JK") else t + ".JK"
        nama_saham = ticker.replace('.JK', '')
        
        st.header(f"📊 Analisa Saham: {nama_saham}")
        
        # Animasi spinner loading selama proses berlangsung
        with st.spinner(f"Membedah anatomi bandar {nama_saham} selama 3 tahun terakhir..."):
            try:
                # 1. TARIK DATA DARI YAHOO FINANCE
                stock = yf.Ticker(ticker)
                df = stock.history(period="3y") # Menarik 3 tahun riwayat
                
                if df.empty or len(df) < 60:
                    st.error("⚠️ Data tidak cukup (butuh minimal 60 hari trading).")
                    continue

                # 2. HITUNG INDIKATOR TEKNIKAL (pandas_ta)
                df['MA20'] = ta.sma(df['Close'], length=20)
                df['MA50'] = ta.sma(df['Close'], length=50) # MA50 sebagai opsional tambahan
                df['Vol_MA20'] = ta.sma(df['Volume'], length=20)
                
                # Stochastic RSI
                stoch = ta.stochrsi(df['Close'], length=14, rsi_length=14, k=3, d=3)
                if stoch is not None and not stoch.empty:
                    df['stoch_k'] = stoch.iloc[:, 0]
                    df['stoch_d'] = stoch.iloc[:, 1]
                else:
                    # Fallback jika Stochastic RSI gagal dihitung (rare case)
                    df['stoch_k'] = 50; df['stoch_d'] = 50
                    
                # Ekstrak Data Besok (H+1) secara lengkap untuk backtest
                df['Next_Open'] = df['Open'].shift(-1)
                df['Next_High'] = df['High'].shift(-1)
                df['Next_Close'] = df['Close'].shift(-1)
                # Mengambil tanggal besoknya untuk laporan rincian
                df['Next_Date'] = df.index.to_series().shift(-1)
                
                # Hapus baris kosong (pemanasan indikator)
                df = df.dropna(subset=['MA50'])

                # 3. SNAPSHOT HARGA HARI INI
                now = df.iloc[-1]
                prev = df.iloc[-2]
                
                current_price = now['Close']
                # Kalkulasi persentase perubahan dari Prev. Close
                change_pct = ((current_price - prev['Close']) / prev['Close']) * 100
                
                # UI: Metric Cards (Widget modern Streamlit untuk harga)
                st.subheader("🏷️ Snapshot Harga Hari Ini")
                m1, m2, m3, m4, m5 = st.columns(5)
                m1.metric("Harga Saat Ini", f"Rp {int(current_price):,}", f"{change_pct:+.2f}%")
                m2.metric("Open", f"Rp {int(now['Open']):,}")
                m3.metric("High", f"Rp {int(now['High']):,}")
                m4.metric("Low", f"Rp {int(now['Low']):,}")
                m5.metric("Volume (Lot)", f"{int(now['Volume']):,}")
                st.write("") # Spacing

                # 4. LOGIKA "CLEAR SKIES" (Mencari Resisten Terdekat)
                df_history = df.iloc[:-1].copy() # Pisahkan data hari ini
                
                # Deteksi Gunung (Swing High) lokal dalam rentang 5 hari
                df_history['Rolling_Max_5'] = df_history['High'].rolling(5, center=True).max()
                peaks = df_history[df_history['High'] == df_history['Rolling_Max_5']]
                higher_peaks = peaks[peaks['High'] > current_price]
                
                if not higher_peaks.empty:
                    # Ambil gunung terbaru di sebelah kiri
                    atap_terdekat = higher_peaks.iloc[-1]['High']
                    jarak_atap = ((atap_terdekat - current_price) / current_price) * 100
                    # SOP: Jarak atap minimal 5%
                    c_clear = jarak_atap > 5.0
                    atap_text = f"Rp {int(atap_terdekat):,} (Jarak: {jarak_atap:.1f}%)"
                else:
                    c_clear = True
                    atap_text = "All Time High (Tidak ada atap!)"

                # 5. FUNGSI HISTORI BREAKOUT (Internal Generator)
                # Kita gunakan fungsi internal agar tidak ada kode yang berulang untuk MA20 & MA50
                def get_breakout_history(ma_line, ma_name):
                    kondisi = (
                        (df_history['Close'] > df_history['Open']) & 
                        (df_history['Close'] > df_history[ma_line]) & 
                        # LOGIKA TRUE BREAKOUT: Low harus memotong/menyentuh MA20 (ada toleransi 1%)
                        (df_history['Low'] <= (df_history[ma_line] * 1.01)) & 
                        (df_history['Volume'] >= (1.5 * df_history['Vol_MA20'])) & 
                        (df_history['Close'] >= (0.97 * df_history['High']))
                    )
                    df_trig = df_history[kondisi]
                    
                    if len(df_trig) == 0:
                        return 0, 0, 0, 0, f"Belum ada sejarah True Breakout {ma_name} selama 3 tahun terakhir."
                        
                    pos_count = neg_count = neu_count = 0
                    text = ""
                    
                    for date, row in df_trig.iterrows():
                        close_sore = row['Close']
                        
                        # Kalkulasi Persentase H+1, dibulatkan ke 2 desimal
                        gap_open_pct = round(((row['Next_Open'] - close_sore) / close_sore) * 100, 2)
                        max_high_pct = round(((row['Next_High'] - close_sore) / close_sore) * 100, 2)
                        close_besok_pct = round(((row['Next_Close'] - close_sore) / close_sore) * 100, 2)
                        
                        # Klasifikasi Status (Strict Rule: Target 2% untuk BSJP)
                        if gap_open_pct >= 2.0:
                            status = "🔥 SUKSES"
                            pos_count += 1
                        elif gap_open_pct <= -1.0:
                            status = "❌ GAGAL PHP"
                            neg_count += 1
                        elif gap_open_pct >= 0.0 and close_besok_pct >= 1.0:
                            status = "✅ WATCHOUT POSITIVE"
                            pos_count += 1
                        elif gap_open_pct == 0.0 and close_besok_pct == 0.0:
                            status = "➖ WATCHOUT NETRAL"
                            neu_count += 1
                        elif gap_open_pct == 0.0 and close_besok_pct < 0.0:
                            status = "⚠️ WATCHOUT NEGATIF"
                            neg_count += 1
                        else:
                            # Generic Fallback jika angka ada di antara kriteria di atas
                            if close_besok_pct > 0:
                                status = "✅ WATCHOUT POSITIVE"; pos_count += 1
                            elif close_besok_pct < 0:
                                status = "⚠️ WATCHOUT NEGATIF"; neg_count += 1
                            else:
                                status = "➖ WATCHOUT NETRAL"; neu_count += 1
                            
                        # Format Tanggal
                        date_str = date.strftime('%d %b %Y')
                        if pd.notnull(row['Next_Date']):
                            next_date_str = row['Next_Date'].strftime('%d %b %Y')
                        else:
                            next_date_str = "N/A"
                        
                        # Padding status agar sejajar rapi (penting untuk st.code)
                        status_padded = status.ljust(19)
                        text += f"- {date_str} ➔ {next_date_str} : {status_padded} | Buka: {gap_open_pct:+.1f}% | Max: {max_high_pct:+.1f}% | Tutup: {close_besok_pct:+.1f}%\n"

                    win_rt = (pos_count / len(df_trig)) * 100
                    # Header text untuk Expander
                    header = f"Positif **{pos_count}x** | Netral **{neu_count}x** | Negatif **{neg_count}x** (Win Rate: **{win_rt:.1f}%**)"
                    return pos_count, neg_count, neu_count, win_rt, header, text

                # 6. PROSES HISTORI (Mengeksekusi Fungsi di Atas)
                pos_ma20, neg_ma20, neu_ma20, win_rt_ma20, header_ma20, detail_ma20 = get_breakout_history('MA20', 'MA20')
                # MA50 hanya untuk informasi tambahan (opsional)
                _, _, _, win_rt_ma50, header_ma50, detail_ma50 = get_breakout_history('MA50', 'MA50')

                # 7. CEK KONDISI HARI INI (SOP Lapis 2)
                c_wajar = change_pct < 30.0
                c_candle = current_price >= (0.97 * now['High'])
                c_vol = now['Volume'] >= (1.5 * now['Vol_MA20'])
                c_stoch = now['stoch_k'] > now['stoch_d']
                
                # Update Trend Hari ini: Wajib True Breakout/Pantul (Low menyentuh MA20)
                c_break_ma20 = (current_price > now['MA20']) and (now['Low'] <= (now['MA20'] * 1.01))
                
                # Logika Trend Hari Ini (Wajib True Breakout + Probabilitas Positif)
                if c_break_ma20:
                    if pos_ma20 > neg_ma20:
                        trend_status_str = "✅ PASS (Mayoritas Historis Positif)"
                        c_trend_pass = True
                    elif neg_ma20 > pos_ma20:
                        trend_status_str = "❌ FAIL (Mayoritas Historis Negatif)"
                        c_trend_pass = False
                    else:
                        trend_status_str = "➖ NETRAL (Historis Seimbang)"
                        c_trend_pass = True
                else:
                    trend_status_str = "❌ FAIL (Bukan True Breakout MA20 Hari Ini)"
                    c_trend_pass = False

                # UI: PEMBAGIAN 2 KOLOM RAPI UNTUK SOP
                st.subheader("📋 CEK SOP FINAL (LAPIS 2)")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("**1. Cek Candle & Kenaikan:**")
                    st.write(f"{'✅' if c_wajar else '❌'} Kenaikan Wajar (<30%)")
                    st.write(f"{'✅' if c_candle else '❌'} Close dekat High (Tanpa ekor panjang)")
                    st.markdown("**2. Cek 'Clear Skies':**")
                    st.write(f"{'✅' if c_clear else '❌'} Jarak Atap > 5% *(Resistensi: {atap_text})*")
                    
                with col2:
                    st.markdown("**3. Sinyal Pendukung Tambahan:**")
                    st.write(f"Trend Saat Ini: **{trend_status_str}**")
                    st.write(f"{'✅' if c_vol else '❌'} Volume Spike (>1.5x)")
                    st.write(f"{'✅' if c_stoch else '❌'} Momentum (StochRSI Golden Cross)")

                # UI: EXPANDER UNTUK RIWAYAT (Untuk merapikan layout yang padat)
                st.markdown("---")
                st.subheader("🕰️ Track Record Bandar (Sejarah 3 Tahun)")
                
                # Expander MA20 (Kita set expanded=True agar user langsung melihatnya)
                with st.expander(f"📊 Buka Histori MA20 - Skor: {header_ma20}", expanded=True):
                    if detail_ma20:
                        # Menggunakan st.code agar spacing ljust(19) tetap rapi sejajar
                        st.code(detail_ma20, language='text')
                    else:
                        st.info("Belum ada riwayat breakout MA20.")
                        
                # Expander MA50 (Kita set expanded=False agar layarnya tidak menuhin scroll)
                with st.expander(f"📊 Buka Histori MA50 - Skor: {header_ma50}", expanded=False):
                    if detail_ma50:
                        st.code(detail_ma50, language='text')
                    else:
                        st.info("Belum ada riwayat breakout MA50.")

                # 8. UI: KESIMPULAN EKSEKUSI (Lebih menonjol)
                st.markdown("---")
                syarat_utama = c_wajar and c_candle and c_clear and c_trend_pass and c_vol
                
                # Menampilkan kesimpulan dengan blok warna yang jelas (Success/Warning/Error)
                if syarat_utama and win_rt_ma20 >= 60:
                    st.success(f"### 🚀 BUNGKUS! (HAKA di IEP + 5 Tick)\nSyarat utama terpenuhi dan probabilitas True Breakout historis MA20 sangat bagus ({win_rt_ma20:.1f}%). Eksekusi sore ini!")
                elif syarat_utama and win_rt_ma20 < 60:
                    st.warning(f"### 👍 HATI-HATI (MODERATE)\nTeknikal hari ini bagus, tapi riwayat bandar MA20 kurang meyakinkan (Probabilitas: {win_rt_ma20:.1f}%). Pasang porsi kecil.")
                else:
                    st.error("### 🛑 ABAIKAN (SKIP)\nAda syarat utama yang gagal. Jangan paksakan masuk. Lindungi modalmu untuk peluang besok.")
                    
                st.markdown("<br><br>", unsafe_allow_html=True) # Extra spacing

            except Exception as e:
                st.error(f"Terjadi kesalahan saat memproses data: {e}")
