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

st.set_page_config(page_title="Štítkovač PRO v 2.6.3", layout="wide")

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
@st.cache_data
def get_working_font(size):
    # Cesty pro Linux/Streamlit Cloud
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    ]
    for path in font_paths:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    
    # ZÁCHRANA: Stažení škálovatelného fontu z internetu
    try:
        url = "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf"
        r = requests.get(url, timeout=5)
        return ImageFont.truetype(io.BytesIO(r.content), size)
    except:
        # Default font v Pillow NEUMÍ měnit velikost, proto je to až poslední možnost
        return ImageFont.load_default()

DPI = 300
MM_TO_PX = DPI / 25.4

def get_wrapped_text_lines(text, font, max_width):
    lines = []
    # Odhad šířky znaku pro zalamování
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

    # --- OBRÁZKY A IKONY ---
    st.divider()
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
                st.write("🖼️ Galerie ikon:")
                grid = st.columns(4)
                for idx, icon_name in enumerate(available_icons):
                    with grid[idx % 4]:
                        st.image(os.path.join(icon_folder, icon_name), use_container_width=True)
                        if st.button("Vybrat", key=f"btn_{icon_name}"):
                            st.session_state.selected_icon = icon_name
                
                st.info(f"Vybráno: **{st.session_state.selected_icon}**")
                if st.button("Zrušit výběr"):
                    st.session_state.selected_icon = "Žádná"

        uploaded_file = st.file_uploader("Nahrát vlastní PNG", type=["png"])

# --- GENERÁTOR ŠTÍTKU ---
def vytvor_stitek_img(s_mm, v_mm):
    px_w, px_h = int(s_mm * MM_TO_PX), int(v_mm * MM_TO_PX)
    padding_px = int(odsazeni_mm * MM_TO_PX)
    logo_padding_px = int((odsazeni_mm + (odsazeni_loga_extra if pozice_loga != "Bez obrázku" else 0)) * MM_TO_PX)
    
    img = Image.new("RGB", (px_w, px_h), barva_pozadi)
    draw = ImageDraw.Draw(img)
    
    # 1. Logo
    logo_img = None
    if uploaded_file:
        logo_img = Image.open(uploaded_file).convert("RGBA")
    elif st.session_state.selected_icon != "Žádná":
        logo_img = Image.open(os.path.join("assets", st.session_state.selected_icon)).convert("RGBA")

    lw, lh = 0, 0
    if logo_img and pozice_loga != "Bez obrázku":
        l_size = int(velikost_loga_mm * MM_TO_PX)
        logo_img.thumbnail((l_size, l_size), Image.Resampling.LANCZOS)
        lw, lh = logo_img.size
        
        if pozice_loga == "Zarovnat na střed nahoru": pos = ((px_w - lw)//2, logo_padding_px)
        elif pozice_loga == "Zarovnat na střed dolů": pos = ((px_w - lw)//2, px_h - lh - logo_padding_px)
        elif pozice_loga == "Levý horní roh": pos = (logo_padding_px, logo_padding_px)
        elif pozice_loga == "Pravý horní roh": pos = (px_w - lw - logo_padding_px, logo_padding_px)
        elif pozice_loga == "Levý spodní roh": pos = (logo_padding_px, px_h - lh - logo_padding_px)
        elif pozice_loga == "Pravý spodní roh": pos = (px_w - lw - logo_padding_px, px_h - lh - logo_padding_px)
        
        img.paste(logo_img, pos, logo_img)

    # 2. Načtení fontu a textu
    fnt = get_working_font(int(velikost_fontu))
    inner_w = px_w - (2 * padding_px)
    lines = get_wrapped_text_lines(vlastni_text, fnt, inner_w)
    
    # OPRAVA: Fixní výška řádku pro spolehlivost
    single_line_h = int(velikost_fontu * 1.2)
    total_text_h = len(lines) * single_line_h + (len(lines) - 1) * radkovani

    # 3. Čárový kód
    bc_img_final, bc_total_h = None, 0
    if data_kodu.strip():
        try:
            BC = barcode.get_barcode_class(typ_kodu)
            bc_obj = BC(data_kodu, writer=ImageWriter())
            raw_bc_img = bc_obj.render({"module_color": "black", "background": barva_pozadi, "write_text": False})
            
            target_h = (px_h - (2 * padding_px)) * (velikost_eanu / 100)
            bars_h = int(target_h * 0.75)
            ratio = min(bars_h / raw_bc_img.size[1], inner_w / raw_bc_img.size[0])
            bars_img = raw_bc_img.resize((int(raw_bc_img.size[0] * ratio), bars_h), Image.Resampling.LANCZOS)
            
            font_ean = get_working_font(max(15, int(bars_img.size[0] * 0.1)))
            full_code = bc_obj.get_fullcode()
            tw = draw.textlength(full_code, font=font_ean)
            th = int(font_ean.size * 1.2)
            
            bc_combined = Image.new("RGB", (bars_img.size[0], bars_img.size[1] + th + 5), barva_pozadi)
            bc_combined.paste(bars_img, (0, 0))
            ImageDraw.Draw(bc_combined).text(((bc_combined.size[0] - tw) / 2, bars_img.size[1] + 2), full_code, fill="black", font=font_ean)
            bc_img_final, bc_total_h = bc_combined, bc_combined.size[1] + 20
        except: pass

    # 4. Výpočet vertikální pozice (vyhýbání se logu)
    t_mar, b_mar = padding_px, padding_px
    if pozice_loga == "Zarovnat na střed nahoru" and logo_img: t_mar = lh + logo_padding_px + 10
    if pozice_loga == "Zarovnat na střed dolů" and logo_img: b_mar = lh + logo_padding_px + 10

    curr_y = t_mar + (px_h - t_mar - b_mar - (total_text_h + bc_total_h)) / 2
    rgb_textu = tuple(int(barva_textu.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    
    for line in lines:
        w = draw.textlength(line, font=fnt)
        draw.text(((px_w - w) / 2, curr_y), line, fill=rgb_textu, font=fnt)
        curr_y += single_line_h + radkovani
        
    if bc_img_final: 
        img.paste(bc_img_final, (int((px_w - bc_img_final.size[0])/2), int(curr_y + 10)))
        
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
    orient_pdf = landscape(A4) if (volba_velikosti == "Velké štítky 2x2 (4 ks)" and orientace_2x2 == "Na šířku") else A4
    c = canvas.Canvas(buffer, pagesize=orient_pdf)
    pw, ph = orient_pdf
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

st.markdown(f"<div style='margin-top:50px; text-align:right;'><p style='color:#000; font-weight:bold;'>Aktuální rozměr: {s_mm} x {v_mm} mm</p></div>", unsafe_allow_html=True)
