import streamlit as st
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
import io
import textwrap
import os
import requests
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm

# Verze 2.6.5 - Stabilizační verze pro fonty
st.set_page_config(page_title="Štítkovač PRO v 2.6.5", layout="wide")

# --- CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #f0f2f6; }
    img { border: 2px solid #000; box-shadow: 2px 2px 10px rgba(0,0,0,0.2); }
    </style>
    """, unsafe_allow_html=True)

# --- ROBUSTNÍ FUNKCE PRO FONT (BEZ CACHE) ---
def load_font(size):
    """Načte font, který zaručeně podporuje změnu velikosti."""
    # 1. Pokus: Stažení Roboto fontu z Google Fonts (nejjistější v cloudu)
    try:
        url = "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            return ImageFont.truetype(io.BytesIO(r.content), size)
    except:
        pass

    # 2. Pokus: Systémové fonty (Linux/Streamlit Cloud)
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    ]
    for p in paths:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)

    # 3. Poslední záchrana: Default (bohužel neumí měnit velikost, ale aplikace nespadne)
    return ImageFont.load_default()

DPI = 300
MM_TO_PX = DPI / 25.4

# --- POMOCNÉ FUNKCE ---
def wrap_text(text, font, max_px_width):
    try:
        avg_char_w = font.getlength("W")
    except:
        avg_char_w = font.size * 0.5
    
    char_limit = max(1, int(max_px_width / avg_char_w))
    lines = []
    for section in text.split('\n'):
        if not section:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(section, width=char_limit))
    return lines

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Nastavení")
    volba = st.selectbox("Velikost", ["Velké 2x2", "Střední 3x8", "Malé 5x13", "Vlastní"])
    
    if volba == "Vlastní":
        s_mm = st.number_input("Šířka (mm)", value=100.0)
        v_mm = st.number_input("Výška (mm)", value=50.0)
        cols, rows = 1, 1
    else:
        # Zjednodušená logika rozměrů
        m_map = {"Velké 2x2": (105, 148.5, 2, 2), "Střední 3x8": (70, 37.125, 3, 8), "Malé 5x13": (38, 21.2, 5, 13)}
        s_mm, v_mm, cols, rows = m_map[volba]

    vlastni_text = st.text_area("Text na štítku", "NÁZEV PRODUKTU")
    velikost_fontu = st.slider("Velikost písma", 10, 300, 80) # Slider
    radkovani = st.slider("Mezery", 0, 100, 10)
    velikost_eanu = st.slider("EAN (%)", 10, 80, 40)
    
    st.divider()
    typ_kodu = st.selectbox("Typ", ["ean13", "ean8", "itf"])
    data_kodu = st.text_input("Data", "123456789012")
    barva_t = st.color_picker("Písmo", "#000000")
    barva_p = st.color_picker("Pozadí", "#FFFFFF")

# --- GENERÁTOR ---
def generuj_stitek():
    px_w, px_h = int(s_mm * MM_TO_PX), int(v_mm * MM_TO_PX)
    img = Image.new("RGB", (px_w, px_h), barva_p)
    draw = ImageDraw.Draw(img)
    
    # KLÍČOVÝ BOD: Načtení fontu přímo v každém cyklu generování
    fnt = load_font(int(velikost_fontu))
    
    margin = int(5 * MM_TO_PX)
    lines = wrap_text(vlastni_text, fnt, px_w - 2 * margin)
    
    # Výpočet výšek
    line_h = int(velikost_fontu * 1.2)
    total_text_h = len(lines) * line_h + (len(lines) - 1) * radkovani
    
    # EAN blok
    bc_img, bc_h = None, 0
    if data_kodu.strip():
        try:
            BC = barcode.get_barcode_class(typ_kodu)
            bc_obj = BC(data_kodu, writer=ImageWriter())
            raw_bc = bc_obj.render({"background": barva_p, "write_text": False})
            
            target_h = int(px_h * (velikost_eanu / 100))
            ratio = min(target_h / raw_bc.size[1], (px_w - 2*margin) / raw_bc.size[0])
            bc_img = raw_bc.resize((int(raw_bc.size[0]*ratio), int(raw_bc.size[1]*ratio)), Image.Resampling.LANCZOS)
            bc_h = bc_img.size[1] + 20
        except: pass

    # Vykreslení
    y = (px_h - (total_text_h + bc_h)) // 2
    rgb = tuple(int(barva_t.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

    for line in lines:
        try:
            w = draw.textlength(line, font=fnt)
        except:
            w = len(line) * (velikost_fontu * 0.5)
        draw.text(((px_w - w)//2, y), line, font=fnt, fill=rgb)
        y += line_h + radkovani
        
    if bc_img:
        img.paste(bc_img, ((px_w - bc_img.size[0])//2, y + 10))
    
    return img

# --- ZOBRAZENÍ ---
st.title("Štítkovač PRO v 2.6.5")

# Vytvoření obrázku
label = generuj_stitek()

# Zobrazení náhledu - šířka v px pro zobrazení
st.subheader("Živý náhled")
st.image(label, caption=f"Velikost písma: {velikost_fontu}px")

# Export
if st.button("Připravit PDF k tisku"):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    img_io = io.BytesIO()
    label.save(img_io, format='PNG')
    from reportlab.lib.utils import ImageReader
    ir = ImageReader(img_io)
    # Vykreslíme arch
    for r in range(rows):
        for col in range(cols):
            c.drawImage(ir, 10*mm + col*s_mm*mm, 297*mm - (10*mm + (r+1)*v_mm*mm), width=s_mm*mm, height=v_mm*mm)
    c.save()
    st.download_button("Stáhnout PDF", buf.getvalue(), "stitky.pdf")
