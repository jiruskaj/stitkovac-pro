import streamlit as st
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
import io
import textwrap
import os
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm

st.set_page_config(page_title="Štítkovač PRO v 2.5", layout="wide")

# --- CSS STYLY PRO VZHLED ---
st.markdown("""
    <style>
    .stApp { background-color: #31333F; }
    .main h1, .main h2, .main h3, .main p { color: #000000 !important; }
    img { border: 2px solid #000000; }
    </style>
    """, unsafe_allow_html=True)

# --- POMOCNÁ FUNKCE PRO FONT ---
def get_working_font(size):
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "arial.ttf"
    ]
    for path in font_paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()

DPI = 300
MM_TO_PX = DPI / 25.4

def get_wrapped_text_height(text, font, max_width, spacing):
    lines = []
    avg_char_w = font.getlength("W") if hasattr(font, "getlength") else font.size * 0.5
    char_limit = max(1, int(max_width / avg_char_w))
    for line in text.split('\n'):
        wrapped = textwrap.wrap(line, width=char_limit)
        lines.extend(wrapped if wrapped else [" "])
    try:
        line_heights = [font.getbbox(l)[3] - font.getbbox(l)[1] for l in lines]
    except:
        line_heights = [font.size for l in lines]
    return lines, sum(line_heights) + (len(lines) - 1) * spacing

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Nastavení")
    volba_velikosti = st.selectbox("Velikost archu / štítku", [
        "Velké štítky 2x2 (4 ks)",
        "Střední štítky 3x8 (24 ks)",
        "Malé štítky 5x13 (65 ks)",
        "Vlastní velikost (1 ks)"
    ])

    orientace_2x2 = "Na výšku"
    if volba_velikosti == "Velké štítky 2x2 (4 ks)":
        orientace_2x2 = st.radio("Orientace štítků 2x2", ["Na výšku", "Na šířku"])

    layout_map = {
        "Velké štítky 2x2 (4 ks)": (105, 148.5, 2, 2, 0) if orientace_2x2 == "Na výšku" else (148.5, 105, 2, 2, 0),
        "Střední štítky 3x8 (24 ks)": (70, 37.125, 3, 8, 0),
        "Malé štítky 5x13 (65 ks)": (38, 21.2, 5, 13, 10),
        "Vlastní velikost (1 ks)": (100, 100, 1, 1, 0)
    }

    s_mm, v_mm, cols, rows, margin_a4 = layout_map[volba_velikosti]
    
    if volba_velikosti == "Vlastní velikost (1 ks)":
        s_mm = st.number_input("Šířka (mm)", value=100.0)
        v_mm = st.number_input("Výška (mm)", value=50.0)

    st.divider()
    vlastni_text = st.text_area("Text na štítku", "NÁZEV PRODUKTU", height=100)
    col_c1, col_c2 = st.columns(2)
    with col_c1: barva_textu = st.color_picker("Písmo", "#000000")
    with col_c2: barva_pozadi = st.color_picker("Štítek", "#FFFFFF")

    odsazeni_mm = st.slider("Odsazení obsahu (mm)", 0, 20, 5)
    velikost_fontu = st.slider("Velikost písma", 10, 200, 80)
    velikost_eanu = st.slider("Velikost EANu (%)", 10, 100, 45)
    radkovani = st.slider("Řádkování", 0, 50, 5)
    
    st.divider()
    typ_kodu = st.selectbox("Typ kódu", ["ean13", "ean8", "itf"])
    data_kodu = st.text_input("Data kódu", "123456789012")

# --- HLAVNÍ PLOCHA ---
st.title("🚀 Štítkovač PRO v 2.5")

def vytvor_stitek_img(s_mm, v_mm):
    px_w, px_h = int(s_mm * MM_TO_PX), int(v_mm * MM_TO_PX)
    padding_px = int(odsazeni_mm * MM_TO_PX)
    inner_w, inner_h = px_w - (2 * padding_px), px_h - (2 * padding_px)
    img = Image.new("RGB", (px_w, px_h), barva_pozadi)
    draw = ImageDraw.Draw(img)
    font_main = get_working_font(int(velikost_fontu))
    lines, text_h = get_wrapped_text_height(vlastni_text, font_main, inner_w, radkovani)

    bc_img_final, bc_total_h = None, 0
    if data_kodu.strip():
        try:
            BC = barcode.get_barcode_class(typ_kodu)
            bc_obj = BC(data_kodu, writer=ImageWriter())
            raw_bc_img = bc_obj.render({"module_color": "black", "background": barva_pozadi, "write_text": False, "quiet_zone": 2})
            target_h = inner_h * (velikost_eanu / 100)
            bars_h = int(target_h * 0.75)
            ratio = min(bars_h / raw_bc_img.size[1], inner_w / raw_bc_img.size[0])
            bars_img = raw_bc_img.resize((int(raw_bc_img.size[0] * ratio), bars_h), Image.Resampling.LANCZOS)
            font_ean = get_working_font(int(bars_img.size[0] * 0.1))
            tw, th = draw.textbbox((0, 0), bc_obj.get_fullcode(), font=font_ean)[2:]
            bc_combined = Image.new("RGB", (bars_img.size[0], bars_img.size[1] + th + 5), barva_pozadi)
            bc_combined.paste(bars_img, (0, 0))
            ImageDraw.Draw(bc_combined).text(((bc_combined.size[0] - tw) / 2, bars_img.size[1] + 2), bc_obj.get_fullcode(), fill="black", font=font_ean)
            bc_img_final, bc_total_h = bc_combined, bc_combined.size[1] + 15
        except: pass

    curr_y = padding_px + (inner_h - (text_h + bc_total_h)) / 2
    rgb_textu = tuple(int(barva_textu.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    for line in lines:
        w, h = draw.textbbox((0, 0), line, font=font_main)[2:]
        draw.text(((px_w - w) / 2, curr_y), line, fill=rgb_textu, font=font_main)
        curr_y += h + radkovani
    if bc_img_final: img.paste(bc_img_final, (int((px_w - bc_img_final.size[0])/2), int(curr_y + 10)))
    return img

col_preview, col_actions = st.columns([3, 1])
with col_preview:
    st.subheader("👁️ Živý náhled")
    final_img = vytvor_stitek_img(s_mm, v_mm)
    st.image(final_img, width=int(s_mm * 3.78))
    st.caption(f"Aktuální rozměr: {s_mm} x {v_mm} mm")

with col_actions:
    st.subheader("📄 Akce")
    # PDF EXPORT
    if st.button("Vygenerovat PDF", use_container_width=True):
        buffer = io.BytesIO()
        orientace_pdf = landscape(A4) if (volba_velikosti == "Velké štítky 2x2 (4 ks)" and orientace_2x2 == "Na šířku") else A4
        c = canvas.Canvas(buffer, pagesize=orientace_pdf)
        pw, ph = orientace_pdf
        sx, sy = (pw - cols * s_mm * mm) / 2, (ph - rows * v_mm * mm) / 2
        img_io = io.BytesIO()
        final_img.save(img_io, format='PNG')
        from reportlab.lib.utils import ImageReader
        ir = ImageReader(img_io)
        for r in range(rows):
            for col in range(cols):
                c.drawImage(ir, sx + col*s_mm*mm, ph - (sy + (r+1)*v_mm*mm), width=s_mm*mm, height=v_mm*mm)
        c.save()
        st.download_button("⬇️ Stáhnout PDF", buffer.getvalue(), "stitky.pdf", use_container_width=True)


# PATIČKA
st.markdown(f"<div style='margin-top:50px; text-align:right;'><p style='color:#000; font-weight:bold;'>Aktuální rozměr: {s_mm} x {v_mm} mm</p></div>", unsafe_allow_html=True)

