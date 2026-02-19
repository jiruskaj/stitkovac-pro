import streamlit as st
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
import io
import textwrap
import requests
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm

st.set_page_config(page_title="Štítkovač PRO v 2.4", layout="wide")

# --- OPRAVA PRO CLOUD: Načtení fontu, který lze zvětšovat ---
@st.cache_resource
def get_font_resource(size):
    try:
        # Stáhneme Roboto (náhrada za Arial), aby posuvník fungoval
        url = "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf"
        r = requests.get(url)
        return ImageFont.truetype(io.BytesIO(r.content), size)
    except:
        return ImageFont.load_default()

# --- KONSTANTY ---
DPI = 300
MM_TO_PX = DPI / 25.4

def get_wrapped_text_height(text, font, max_width, spacing):
    lines = []
    # Bezpečný odhad šířky znaku pro zalamování
    for line in text.split('\n'):
        wrapped = textwrap.wrap(line, width=max(1, int(max_width / (font.size * 0.5)))) 
        lines.extend(wrapped if wrapped else [" "])
    
    # Výpočet výšky (ošetření pro defaultní font i TrueType)
    try:
        line_heights = [font.getbbox(l)[3] - font.getbbox(l)[1] for l in lines]
    except:
        line_heights = [font.size for l in lines] # fallback
        
    total_height = sum(line_heights) + (len(lines) - 1) * spacing
    return lines, total_height

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
    velikost_fontu = st.slider("Velikost písma", 5, 200, 60) # Zvýšen rozsah pro lepší čitelnost
    velikost_eanu = st.slider("Velikost EANu (%)", 10, 100, 45)
    radkovani = st.slider("Řádkování", 0, 50, 5)

    st.divider()
    typ_kodu = st.selectbox("Typ kódu", ["ean13", "ean8", "itf"])
    data_kodu = st.text_input("Data kódu", "123456789012")

# --- HLAVNÍ PLOCHA ---
st.title("🚀 Štítkovač PRO v 2.1")

def vytvor_stitek_img(s_mm, v_mm):
    px_w, px_h = int(s_mm * MM_TO_PX), int(v_mm * MM_TO_PX)
    padding_px = int(odsazeni_mm * MM_TO_PX)
    inner_w = px_w - (2 * padding_px)
    inner_h = px_h - (2 * padding_px)
    
    img = Image.new("RGB", (px_w, px_h), barva_pozadi)
    draw = ImageDraw.Draw(img)
    
    # Použití naší funkce pro font, která funguje na Cloudu
    font_main = get_font_resource(int(velikost_fontu))
    
    lines, text_h = get_wrapped_text_height(vlastni_text, font_main, inner_w, radkovani)

    bc_img_final = None
    bc_total_h = 0
    
    if data_kodu.strip():
        try:
            BC = barcode.get_barcode_class(typ_kodu)
            writer_options = {
                "module_color": "black", 
                "background": barva_pozadi, 
                "write_text": False, 
                "quiet_zone": 2
            }
            bc_obj = BC(data_kodu, writer=ImageWriter())
            raw_bc_img = bc_obj.render(writer_options)
            
            target_block_h = inner_h * (velikost_eanu / 100)
            bar_height_ratio = 0.75 
            bars_h = int(target_block_h * bar_height_ratio)
            
            ratio = bars_h / raw_bc_img.size[1]
            if (raw_bc_img.size[0] * ratio) > inner_w:
                ratio = inner_w / raw_bc_img.size[0]
            
            bars_img = raw_bc_img.resize((int(raw_bc_img.size[0] * ratio), bars_h), Image.Resampling.LANCZOS)
            
            full_code = bc_obj.get_fullcode()
            ean_font_size = max(10, int(bars_img.size[0] * 0.1))
            font_ean = get_font_resource(ean_font_size)
            
            tw, th = draw.textbbox((0, 0), full_code, font=font_ean)[2:]
            
            bc_block_w = bars_img.size[0]
            bc_block_h = bars_img.size[1] + th + 5
            bc_combined = Image.new("RGB", (bc_block_w, bc_block_h), barva_pozadi)
            bc_combined.paste(bars_img, (0, 0))
            
            d_bc = ImageDraw.Draw(bc_combined)
            d_bc.text(((bc_block_w - tw) / 2, bars_img.size[1] + 2), full_code, fill="black", font=font_ean)
            
            bc_img_final = bc_combined
            bc_total_h = bc_block_h + 15 
        except Exception as e:
            st.error(f"Chyba EAN: {e}")

    celkova_vyska_obsahu = text_h + bc_total_h
    start_y = padding_px + (inner_h - celkova_vyska_obsahu) / 2

    curr_y = start_y
    rgb_textu = tuple(int(barva_textu.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font_main)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        draw.text(((px_w - w) / 2, curr_y), line, fill=rgb_textu, font=font_main)
        curr_y += h + radkovani

    if bc_img_final:
        img.paste(bc_img_final, (int((px_w - bc_img_final.size[0])/2), int(curr_y + 10)))
        
    return img

col_preview, col_actions = st.columns([3, 1])

with col_preview:
    st.subheader("👁️ Živý náhled 1:1")
    final_img = vytvor_stitek_img(s_mm, v_mm)
    st.image(final_img, use_column_width=False, width=int(s_mm * 3.78)) 
    st.caption(f"Přesná velikost štítku: {s_mm} x {v_mm} mm")

with col_actions:
    st.subheader("ℹ️ Export")
    if st.button("📄 Vygenerovat PDF", use_container_width=True):
        buffer_pdf = io.BytesIO()
        c = canvas.Canvas(buffer_pdf, pagesize=A4)
        pw, ph = A4
        grid_w = cols * s_mm * mm
        grid_h = rows * v_mm * mm
        start_x = (pw - grid_w) / 2
        start_y = (ph - grid_h) / 2
        img_byte_arr = io.BytesIO()
        final_img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        from reportlab.lib.utils import ImageReader
        ir = ImageReader(img_byte_arr)
        for r in range(rows):
            for col in range(cols):
                x = start_x + (col * s_mm * mm)
                y = ph - (start_y + (r + 1) * v_mm * mm)
                c.drawImage(ir, x, y, width=s_mm*mm, height=v_mm*mm)
        c.showPage()
        c.save()
        st.download_button("⬇️ Stáhnout PDF", buffer_pdf.getvalue(), "stitky.pdf", "application/pdf", use_container_width=True)

st.markdown("<br><br><br>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align: right; color: gray; font-size: 0.8rem;'>"
    "Štítkovač PRO v 2.1 pro Vás připravil Jakub Jiruška v roce 2026"
    "</p>", 
    unsafe_allow_html=True
)
