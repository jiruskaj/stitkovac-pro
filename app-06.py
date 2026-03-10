import streamlit as st
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
import io
import textwrap
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

st.set_page_config(page_title="Štítkovač PRO v 2.4.2", layout="wide")

# --- CSS PRO ŠEDÉ POZADÍ A RÁMEČEK NÁHLEDU ---
st.markdown("""
    <style>
    .stApp { background-color: #f0f2f6; }
    .stImage img { border: 2px solid #000000; box-shadow: 5px 5px 15px rgba(0,0,0,0.1); }
    </style>
    """, unsafe_allow_html=True)

# --- NAČTÁNÍ FONTU ---
def get_working_font(size):
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "arial.ttf"
    ]
    for path in font_paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    
    # Pokud nejsou systémové fonty, zkusíme stáhnout Roboto (který umí měnit velikost)
    try:
        import requests
        url = "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf"
        r = requests.get(url, timeout=5)
        return ImageFont.truetype(io.BytesIO(r.content), size)
    except:
        # Poslední záchrana (bohužel u load_default nejde měnit velikost)
        return ImageFont.load_default()

DPI = 300
MM_TO_PX = DPI / 25.4

def get_wrapped_text_lines(text, font, max_width):
    lines = []
    # Odhad šířky znaku pro zalamování
    try:
        avg_char_width = font.getlength("W")
    except:
        avg_char_width = font.size * 0.6
        
    char_limit = max(1, int(max_width / avg_char_width))
    for line in text.split('\n'):
        wrapped = textwrap.wrap(line, width=char_limit)
        lines.extend(wrapped if wrapped else [" "])
    return lines

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Nastavení")
    volba_velikosti = st.selectbox("Velikost archu / štítku", [
        "Velké štítky 2x2 (4 ks)",
        "Střední štítky 3x8 (24 ks)",
        "Malé štítky 5x13 (65 ks)",
        "Vlastní velikost (1 ks)"
    ])

    layout_map = {
        "Velké štítky 2x2 (4 ks)": (105, 148.5, 2, 2, 0),
        "Střední štítky 3x8 (24 ks)": (70, 37.125, 3, 8, 0),
        "Malé štítky 5x13 (65 ks)": (38, 21.2, 5, 13, 10),
        "Vlastní velikost (1 ks)": (100, 100, 1, 1, 0)
    }

    if volba_velikosti == "Vlastní velikost (1 ks)":
        s_mm = st.number_input("Šířka štítku (mm)", value=100.0)
        v_mm = st.number_input("Výška štítku (mm)", value=50.0)
        cols, rows, margin_a4 = 1, 1, 0
    else:
        s_mm, v_mm, cols, rows, margin_a4 = layout_map[volba_velikosti]

    st.divider()
    vlastni_text = st.text_area("Text na štítku", "NÁZEV PRODUKTU", height=100)
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        barva_textu = st.color_picker("Písmo", "#000000")
    with col_c2:
        barva_pozadi = st.color_picker("Štítek", "#FFFFFF")

    odsazeni_mm = st.slider("Odsazení obsahu (mm)", 0, 20, 5)
    velikost_fontu = st.slider("Velikost písma", 10, 300, 80)
    velikost_eanu = st.slider("Velikost EANu (%)", 10, 100, 45)
    radkovani = st.slider("Dodatečné řádkování", 0, 100, 10)

    st.divider()
    typ_kodu = st.selectbox("Typ kódu", ["ean13", "ean8", "itf"])
    data_kodu = st.text_input("Data kódu", "123456789012")

# --- HLAVNÍ PLOCHA ---
st.title("🚀 Štítkovač PRO v 2.4.2")

def vytvor_stitek_img(s_mm, v_mm):
    px_w, px_h = int(s_mm * MM_TO_PX), int(v_mm * MM_TO_PX)
    padding_px = int(odsazeni_mm * MM_TO_PX)
    inner_w = px_w - (2 * padding_px)
    inner_h = px_h - (2 * padding_px)
    
    img = Image.new("RGB", (px_w, px_h), barva_pozadi)
    draw = ImageDraw.Draw(img)
    
    # Načtení fontu podle aktuálního slideru
    font_main = get_working_font(int(velikost_fontu))
    
    # Příprava textu a výpočet výšky (1.2 je standardní koeficient řádku)
    lines = get_wrapped_text_lines(vlastni_text, font_main, inner_w)
    single_line_h = int(velikost_fontu * 1.2)
    total_text_h = len(lines) * single_line_h + (len(lines) - 1) * radkovani

    bc_img_final = None
    bc_total_h = 0
    
    # Příprava čárového kódu
    if data_kodu.strip():
        try:
            BC = barcode.get_barcode_class(typ_kodu)
            writer_options = {"module_color": "black", "background": barva_pozadi, "write_text": False, "quiet_zone": 2}
            bc_obj = BC(data_kodu, writer=ImageWriter())
            raw_bc_img = bc_obj.render(writer_options)
            
            target_block_h = inner_h * (velikost_eanu / 100)
            bars_h = int(target_block_h * 0.75)
            
            ratio = bars_h / raw_bc_img.size[1]
            if (raw_bc_img.size[0] * ratio) > inner_w:
                ratio = inner_w / raw_bc_img.size[0]
            
            bars_img = raw_bc_img.resize((int(raw_bc_img.size[0] * ratio), bars_h), Image.Resampling.LANCZOS)
            font_ean = get_working_font(max(15, int(bars_img.size[0] * 0.1)))
            full_code = bc_obj.get_fullcode()
            
            try:
                # Zjištění šířky a výšky textu pod kódem
                bbox = draw.textbbox((0, 0), full_code, font=font_ean)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except:
                tw, th = len(full_code) * 10, 20

            bc_combined = Image.new("RGB", (bars_img.size[0], bars_img.size[1] + th + 10), barva_pozadi)
            bc_combined.paste(bars_img, (0, 0))
            d_bc = ImageDraw.Draw(bc_combined)
            d_bc.text(((bc_combined.size[0] - tw) / 2, bars_img.size[1] + 5), full_code, fill="black", font=font_ean)
            
            bc_img_final = bc_combined
            bc_total_h = bc_combined.size[1] + 20 
        except Exception as e:
            st.error(f"EAN Error: {e}")

    # Vystředění celého bloku (text + kód) vertikálně
    celkova_vyska_vseho = total_text_h + bc_total_h
    curr_y = padding_px + (inner_h - celkova_vyska_vseho) / 2
    
    rgb_textu = tuple(int(barva_textu.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    
    # Vykreslení řádků textu
    for line in lines:
        try:
            w = draw.textlength(line, font=font_main)
        except:
            w = len(line) * (velikost_fontu * 0.5)
            
        draw.text(((px_w - w) / 2, curr_y), line, fill=rgb_textu, font=font_main)
        curr_y += single_line_h + radkovani

    # Vykreslení EANu pod text
    if bc_img_final:
        img.paste(bc_img_final, (int((px_w - bc_img_final.size[0])/2), int(curr_y + 10)))
        
    return img

col_preview, col_actions = st.columns([3, 1])

with col_preview:
    st.subheader("👁️ Živý náhled")
    final_img = vytvor_stitek_img(s_mm, v_mm)
    st.image(final_img, use_container_width=False, width=int(s_mm * 3.78)) 

with col_actions:
    st.subheader("ℹ️ Export")
    if st.button("📄 Vygenerovat PDF", use_container_width=True):
        buffer_pdf = io.BytesIO()
        c = canvas.Canvas(buffer_pdf, pagesize=A4)
        pw, ph = A4
        grid_w, grid_h = cols * s_mm * mm, rows * v_mm * mm
        sx, sy = (pw - grid_w) / 2, (ph - grid_h) / 2
        img_io = io.BytesIO()
        final_img.save(img_io, format='PNG')
        from reportlab.lib.utils import ImageReader
        ir = ImageReader(img_io)
        for r in range(rows):
            for col in range(cols):
                c.drawImage(ir, sx + (col * s_mm * mm), ph - (sy + (r + 1) * v_mm * mm), width=s_mm*mm, height=v_mm*mm)
        c.showPage()
        c.save()
        st.download_button("⬇️ Stáhnout PDF", buffer_pdf.getvalue(), "stitky.pdf", use_container_width=True)

st.caption("Verze 2.4.2 | Opravena dynamická velikost fontu")
