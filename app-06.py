import streamlit as st
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
import io
import requests
import textwrap
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

st.set_page_config(page_title="Štítkovač PRO v 3.1", layout="wide")

# --- NAČTENÍ KVALITNÍHO FONTU ---
@st.cache_resource
def get_font(size):
    try:
        # Roboto Bold pro profesionální vzhled
        url = "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf"
        r = requests.get(url)
        return ImageFont.truetype(io.BytesIO(r.content), size)
    except:
        # Pokud by GitHub nejel, použije se systémový
        return ImageFont.load_default()

DPI = 300
MM_TO_PX = DPI / 25.4

# --- SIDEBAR NASTAVENÍ ---
with st.sidebar:
    st.header("⚙️ Konfigurace")
    
    volba = st.selectbox("Typ štítku", [
        "Velké (105x148mm)",
        "Střední (70x37mm)",
        "Malé (38x21mm)",
        "Vlastní rozměr"
    ])
    
    layout_map = {
        "Velké (105x148mm)": (105, 148.5, 2, 2),
        "Střední (70x37mm)": (70, 37.125, 3, 8),
        "Malé (38x21mm)": (38, 21.2, 5, 13),
        "Vlastní rozměr": (100, 50, 1, 1)
    }
    
    s_mm, v_mm, cols, rows = layout_map[volba]
    if volba == "Vlastní rozměr":
        s_mm = st.number_input("Šířka (mm)", value=100.0)
        v_mm = st.number_input("Výška (mm)", value=50.0)

    st.divider()
    vlastni_text = st.text_area("Text na štítku", "NÁZEV PRODUKTU")
    
    # KLÍČOVÉ PRVKY PRO VELIKOST
    velikost_fontu = st.slider("Velikost písma", 10, 500, 150)
    odsazeni_mm = st.slider("Okraje (mm)", 0, 30, 10)
    radkovani = st.slider("Mezery mezi řádky", 0, 100, 10)
    
    st.divider()
    data_kodu = st.text_input("EAN kód (volitelně)", "123456789012")
    velikost_eanu = st.slider("Výška EANu (%)", 0, 80, 30)

st.title("🚀 Štítkovač PRO v 3.1")

def vytvor_stitek():
    px_w, px_h = int(s_mm * MM_TO_PX), int(v_mm * MM_TO_PX)
    pad = int(odsazeni_mm * MM_TO_PX)
    
    img = Image.new("RGB", (px_w, px_h), "white")
    draw = ImageDraw.Draw(img)
    
    # Načtení fontu přímo se zvolenou velikostí
    font = get_font(velikost_fontu)
    
    # 1. Zalamování a výpočet textu
    # Odhadneme šířku podle písmene W
    char_w = draw.textbbox((0,0), "W", font=font)[2]
    max_text_w = px_w - (2 * pad)
    char_limit = max(1, int(max_text_w / char_w))
    
    lines = []
    for section in vlastni_text.split('\n'):
        wrapped = textwrap.wrap(section, width=char_limit)
        lines.extend(wrapped if wrapped else [" "])

    # Výpočet celkové výšky textu
    line_heights = []
    total_text_h = 0
    for l in lines:
        bbox = draw.textbbox((0, 0), l, font=font)
        h = bbox[3] - bbox[1]
        line_heights.append(h)
        total_text_h += h + radkovani
    total_text_h -= radkovani

    # 2. EAN blok
    bc_img = None
    bc_h_px = 0
    if data_kodu.strip():
        try:
            BC = barcode.get_barcode_class("ean13")
            bc_obj = BC(data_kodu, writer=ImageWriter())
            raw_bc = bc_obj.render({"write_text": True, "module_height": 10})
            
            target_h = int((px_h - 2*pad) * (velikost_eanu/100))
            if target_h > 10:
                ratio = target_h / raw_bc.size[1]
                new_w = int(raw_bc.size[0] * ratio)
                if new_w > max_text_w:
                    ratio = max_text_w / raw_bc.size[0]
                    new_w = int(raw_bc.size[0] * ratio)
                    target_h = int(raw_bc.size[1] * ratio)
                
                bc_img = raw_bc.resize((new_w, target_h), Image.Resampling.LANCZOS)
                bc_h_px = target_h + 30 # rezerva pod EANem
        except:
            pass

    # 3. Vykreslení (vycentrování na střed)
    current_y = (px_h - (total_text_h + bc_h_px)) / 2
    
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        draw.text(((px_w - w)/2, current_y), line, fill="black", font=font)
        current_y += line_heights[i] + radkovani
        
    if bc_img:
        img.paste(bc_img, (int((px_w - bc_img.size[0])/2), int(current_y + 20)))
        
    return img

# --- ZOBRAZENÍ A EXPORT ---
col_preview, col_actions = st.columns([3, 1])

with col_preview:
    st.subheader("👁️ Živý náhled")
    final_img = vytvor_stitek()
    # Zobrazíme náhled - na Cloudu už use_container_width funguje
    st.image(final_img, use_container_width=True)

with col_actions:
    st.subheader("📄 Export")
    if st.button("Vygenerovat PDF", type="primary", use_container_width=True):
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        pw, ph = A4
        
        # Převod pro ReportLab
        img_io = io.BytesIO()
        final_img.save(img_io, format='PNG')
        from reportlab.lib.utils import ImageReader
        ir = ImageReader(img_io)
        
        # Jednoduchý tisk 1 ks (zatím bez Excelu) na celý arch
        gw, gh = cols * s_mm * mm, rows * v_mm * mm
        sx, sy = (pw - gw) / 2, (ph - gh) / 2
        
        for r in range(rows):
            for col in range(cols):
                c.drawImage(ir, sx + (col * s_mm * mm), ph - (sy + (r + 1) * v_mm * mm), width=s_mm*mm, height=v_mm*mm)
        c.showPage()
        c.save()
        st.download_button("⬇️ Stáhnout PDF", buffer.getvalue(), "stitky.pdf", use_container_width=True)

st.caption("Verze 3.1 | Běží na Streamlit Cloudu s plnou podporou fontů.")
