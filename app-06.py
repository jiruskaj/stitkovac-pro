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

st.set_page_config(page_title="Štítkovač PRO v 2.6.4", layout="wide")

# --- CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #31333F; }
    .main h1, .main h2, .main h3, .main p { color: #000000 !important; }
    img { border: 2px solid #000000; }
    div.stButton > button { font-size: 10px; height: 1.5rem; padding: 0px 5px; }
    </style>
    """, unsafe_allow_html=True)

# --- OPRAVENÉ NAČÍTÁNÍ FONTU ---
# Používáme cache_resource, protože font je objekt, který nelze snadno "picklovat"
@st.cache_resource
def get_working_font(size):
    # Cesty pro Linux/Streamlit Cloud
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
    ]
    
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    
    # ZÁCHRANA: Stažení škálovatelného fontu z internetu (Roboto)
    try:
        url = "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            # Musíme použít BytesIO, aby Pillow mohl font načíst z paměti
            font_data = io.BytesIO(r.content)
            return ImageFont.truetype(font_data, size)
    except Exception as e:
        st.error(f"Nepodařilo se stáhnout font: {e}")
    
    # Úplně poslední možnost - default font (bohužel u něj nefunguje změna velikosti)
    return ImageFont.load_default()

DPI = 300
MM_TO_PX = DPI / 25.4

def get_wrapped_text_lines(text, font, max_width):
    lines = []
    try:
        avg_char_w = font.getlength("W")
    except:
        avg_char_w = font.size * 0.5
        
    char_limit = max(1, int(max_width / avg_char_w))
    for line in text.split('\n'):
        wrapped = textwrap.wrap(line, width=char_limit)
        lines.extend(wrapped if wrapped else [" "])
    return lines

# --- SESSION STATE PRO IKONY ---
if 'selected_icon' not in st.session_state:
    st.session_state.selected_icon = "Žádná"

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Nastavení")
    volba_velikosti = st.selectbox("Velikost archu / štítku", [
        "Velké štítky 2x2 (4 ks)", 
        "Střední štítky 3x8 (24 ks)", 
        "Malé štítky 5x13 (65 ks)", 
        "Vlastní velikost (1 ks)"
    ])
    
    if volba_velikosti == "Vlastní velikost (1 ks)":
        s_mm = st.number_input("Šířka štítku (mm)", value=100.0)
        v_mm = st.number_input("Výška štítku (mm)", value=50.0)
        cols, rows = 1, 1
    else:
        orientace_2x2 = "Na výšku"
        if volba_velikosti == "Velké štítky 2x2 (4 ks)":
            orientace_2x2 = st.radio("Orientace štítků 2x2", ["Na výšku", "Na šířku"])
        
        layout_map = {
            "Velké štítky 2x2 (4 ks)": (105, 148.5, 2, 2) if orientace_2x2 == "Na výšku" else (148.5, 105, 2, 2),
            "Střední štítky 3x8 (24 ks)": (70, 37.125, 3, 8),
            "Malé štítky 5x13 (65 ks)": (38, 21.2, 5, 13)
        }
        s_mm, v_mm, cols, rows = layout_map[volba_velikosti]

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

    pozice_loga = st.selectbox("Umístění obrázku", [
        "Bez obrázku", "Zarovnat na střed nahoru", "Zarovnat na střed dolů",
        "Levý horní roh", "Pravý horní roh", "Levý spodní roh", "Pravý spodní roh"
    ])

    uploaded_file = None
    if pozice_loga != "Bez obrázku":
        velikost_loga_mm = st.slider("Velikost obrázku (mm)", 10, int(min(s_mm, v_mm)), 20)
        odsazeni_loga_extra = st.slider("Dodatečné odsazení obrázku (mm)", 0, 50, 0)
        
        icon_folder = "assets"
        if os.path.exists(icon_folder):
            available_icons = [f for f in os.listdir(icon_folder) if f.lower().endswith('.png')]
            if available_icons:
                grid = st.columns(4)
                for idx, icon_name in enumerate(available_icons):
                    with grid[idx % 4]:
                        st.image(os.path.join(icon_folder, icon_name), use_container_width=True)
                        if st.button("Vybrat", key=f"btn_{icon_name}"):
                            st.session_state.selected_icon = icon_name
                st.info(f"Vybráno: **{st.session_state.selected_icon}**")

        uploaded_file = st.file_uploader("Nahrát vlastní PNG", type=["png"])

# --- GENERÁTOR ---
def vytvor_stitek_img(s_mm, v_mm):
    px_w, px_h = int(s_mm * MM_TO_PX), int(v_mm * MM_TO_PX)
    padding_px = int(odsazeni_mm * MM_TO_PX)
    logo_p_px = int((odsazeni_mm + (odsazeni_loga_extra if pozice_loga != "Bez obrázku" else 0)) * MM_TO_PX)
    
    img = Image.new("RGB", (px_w, px_h), barva_pozadi)
    draw = ImageDraw.Draw(img)
    
    # Logo
    lh = 0
    if pozice_loga != "Bez obrázku":
        l_img = None
        if uploaded_file: l_img = Image.open(uploaded_file).convert("RGBA")
        elif st.session_state.selected_icon != "Žádná":
            p = os.path.join("assets", st.session_state.selected_icon)
            if os.path.exists(p): l_img = Image.open(p).convert("RGBA")
        
        if l_img:
            l_size = int(velikost_loga_mm * MM_TO_PX)
            l_img.thumbnail((l_size, l_size), Image.Resampling.LANCZOS)
            lw, lh = l_img.size
            if "střed nahoru" in pozice_loga: pos = ((px_w - lw)//2, logo_p_px)
            elif "střed dolů" in pozice_loga: pos = ((px_w - lw)//2, px_h - lh - logo_p_px)
            elif "Levý horní" in pozice_loga: pos = (logo_p_px, logo_p_px)
            elif "Pravý horní" in pozice_loga: pos = (px_w - lw - logo_p_px, logo_p_px)
            elif "Levý spodní" in pozice_loga: pos = (logo_p_px, px_h - lh - logo_p_px)
            else: pos = (px_w - lw - logo_p_px, px_h - lh - logo_p_px)
            img.paste(l_img, pos, l_img)

    # Text a Font
    # ZDE VOLÁME OPRAVENOU FUNKCI
    fnt = get_working_font(int(velikost_fontu))
    i_w = px_w - (2 * padding_px)
    lines = get_wrapped_text_lines(vlastni_text, fnt, i_w)
    line_h = int(velikost_fontu * 1.2)
    t_h = len(lines) * line_h + (len(lines)-1) * radkovani

    # EAN
    bc_img, bc_h = None, 0
    if data_kodu.strip():
        try:
            BC = barcode.get_barcode_class(typ_kodu)
            bc_obj = BC(data_kodu, writer=ImageWriter())
            raw_bc = bc_obj.render({"background": barva_pozadi, "write_text": False})
            target_h = (px_h - (2 * padding_px)) * (velikost_eanu / 100)
            ratio = min(target_h * 0.75 / raw_bc.size[1], i_w / raw_bc.size[0])
            b_img = raw_bc.resize((int(raw_bc.size[0] * ratio), int(raw_bc.size[1] * ratio)), Image.Resampling.LANCZOS)
            
            f_ean = get_working_font(max(15, int(b_img.size[0] * 0.1)))
            full_c = bc_obj.get_fullcode()
            tw = draw.textlength(full_c, font=f_ean)
            combined = Image.new("RGB", (b_img.size[0], b_img.size[1] + int(f_ean.size * 1.3)), barva_pozadi)
            combined.paste(b_img, (0, 0))
            ImageDraw.Draw(combined).text(((combined.size[0] - tw)/2, b_img.size[1] + 2), full_c, fill="black", font=f_ean)
            bc_img, bc_h = combined, combined.size[1] + 20
        except: pass

    # Centrování
    t_m = lh + logo_p_px + 10 if "nahoru" in pozice_loga else padding_px
    b_m = lh + logo_p_px + 10 if "dolů" in pozice_loga else padding_px
    curr_y = t_m + (px_h - t_m - b_m - (t_h + bc_h)) / 2
    rgb = tuple(int(barva_textu.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    
    for l in lines:
        w = draw.textlength(l, font=fnt)
        draw.text(((px_w - w)/2, curr_y), l, fill=rgb, font=fnt)
        curr_y += line_h + radkovani
    if bc_img: img.paste(bc_img, (int((px_w - bc_img.size[0])/2), int(curr_y + 10)))
    return img

# --- VÝSTUP ---
col_preview, col_actions = st.columns([3, 1])
with col_preview:
    st.subheader("👁️ Živý náhled")
    final_img = vytvor_stitek_img(s_mm, v_mm)
    st.image(final_img, width=int(s_mm * 3.78))

with col_actions:
    st.subheader("📄 Export")
    buffer = io.BytesIO()
    orient = landscape(A4) if (volba_velikosti == "Velké štítky 2x2 (4 ks)" and orientace_2x2 == "Na šířku") else A4
    c = canvas.Canvas(buffer, pagesize=orient)
    pw, ph = orient
    sx, sy = (pw - cols*s_mm*mm)/2, (ph - rows*v_mm*mm)/2
    img_io = io.BytesIO()
    final_img.save(img_io, format='PNG')
    from reportlab.lib.utils import ImageReader
    ir = ImageReader(img_io)
    for r in range(rows):
        for col in range(cols):
            c.drawImage(ir, sx + col*s_mm*mm, ph - (sy + (r+1)*v_mm*mm), width=s_mm*mm, height=v_mm*mm)
    c.save()
    st.download_button("⬇️ Stáhnout PDF", buffer.getvalue(), "stitky.pdf", use_container_width=True)
