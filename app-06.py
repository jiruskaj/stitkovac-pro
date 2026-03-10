import streamlit as st
import barcode
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
import io
import textwrap
import os
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm

st.set_page_config(page_title="Štítkovač PRO v 2.6.9", layout="wide")

# --- CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #31333F; }
    .main h1, .main h2, .main h3, .main p { color: #FFFFFF !important; }
    img { background-color: white; border-radius: 2px; }
    /* Styl pro tlačítka s ikonami */
    div[data-testid="stVerticalBlock"] button {
        height: auto !important;
        padding: 2px !important;
        border: 1px solid #555 !important;
    }
    div.stButton > button:hover { border-color: #ff4b4b !important; }
    </style>
    """, unsafe_allow_html=True)

# --- FONT ---
def get_font(size):
    font_path = "font.ttf"
    if os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()

DPI = 300
MM_TO_PX = DPI / 25.4

def wrap_text(text, font, max_width_px):
    lines = []
    try:
        avg_char_w = font.getlength("W")
    except:
        avg_char_w = font.size * 0.5
    char_limit = max(1, int(max_width_px / avg_char_w))
    for p in text.split('\n'):
        if not p:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(p, width=char_limit))
    return lines

# --- SESSION STATE ---
if 'selected_icon' not in st.session_state:
    st.session_state.selected_icon = "Žádná"

# --- SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Nastavení")
    
    volba_velikosti = st.selectbox("Velikost archu", [
        "Velké štítky 2x2 (4 ks)", "Střední štítky 3x8 (24 ks)", 
        "Malé štítky 5x13 (65 ks)", "Vlastní velikost (1 ks)"
    ])
    
    if volba_velikosti == "Vlastní velikost (1 ks)":
        s_mm = st.number_input("Šířka (mm)", value=100.0)
        v_mm = st.number_input("Výška (mm)", value=50.0)
        cols, rows = 1, 1
    else:
        layout_map = {
            "Velké štítky 2x2 (4 ks)": (105, 148.5, 2, 2),
            "Střední štítky 3x8 (24 ks)": (70, 37.125, 3, 8),
            "Malé štítky 5x13 (65 ks)": (38, 21.2, 5, 13)
        }
        s_mm, v_mm, cols, rows = layout_map[volba_velikosti]

    st.divider()
    vlastni_text = st.text_area("Text", "Příliš žluťoučký kůň", height=80)
    
    col_c1, col_c2 = st.columns(2)
    with col_c1: barva_textu = st.color_picker("Písmo", "#000000")
    with col_c2: barva_pozadi = st.color_picker("Štítek", "#FFFFFF")

    velikost_fontu = st.slider("Velikost písma", 10, 300, 80)
    radkovani = st.slider("Mezery v textu", 0, 50, 5)
    odsazeni_mm = st.slider("Odsazení obsahu (mm)", 0, 30, 0)
    velikost_eanu = st.slider("Velikost EANu (%)", 5, 100, 40)

    st.divider()
    typ_kodu = st.selectbox("Typ kódu", ["ean13", "ean8", "itf"])
    data_kodu = st.text_input("Data kódu", "123456789012")

    st.divider()
    uploaded_file = st.file_uploader("Vlastní logo (PNG/JPG)", type=["png", "jpg", "jpeg"])
    
    pozice_loga = st.selectbox("Umístění loga", [
        "Bez obrázku", "Střed nahoru", "Střed dolů", 
        "Levý horní", "Pravý horní", "Levý dolní", "Pravý dolní"
    ])

    icon_folder = "assets"
    if os.path.exists(icon_folder):
        available_icons = [f for f in os.listdir(icon_folder) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if available_icons:
            st.write("🖼️ Galerie ikon (kliknutím vyber):")
            grid = st.columns(3)
            for i, icon_name in enumerate(available_icons):
                with grid[i % 3]:
                    if st.button(icon_name, key=f"btn_{icon_name}"):
                        st.session_state.selected_icon = icon_name
                    st.image(os.path.join(icon_folder, icon_name), use_container_width=True)

            if st.button("Vymazat výběr ikony"):
                st.session_state.selected_icon = "Žádná"

# --- GENERÁTOR ---
def vytvor_stitek():
    px_w, px_h = int(s_mm * MM_TO_PX), int(v_mm * MM_TO_PX)
    padding_px = int(odsazeni_mm * MM_TO_PX)
    
    img = Image.new("RGB", (px_w, px_h), barva_pozadi)
    draw = ImageDraw.Draw(img)
    fnt = get_font(int(velikost_fontu))
    
    # 1. Logo/Ikona
    logo_h_px = 0
    l_img = None
    if uploaded_file:
        l_img = Image.open(uploaded_file).convert("RGBA")
    elif st.session_state.selected_icon != "Žádná":
        p = os.path.join("assets", st.session_state.selected_icon)
        if os.path.exists(p): l_img = Image.open(p).convert("RGBA")
    
    if l_img and pozice_loga != "Bez obrázku":
        l_size = int(v_mm * 0.25 * MM_TO_PX) 
        l_img.thumbnail((l_size, l_size), Image.Resampling.LANCZOS)
        lw, lh = l_img.size
        logo_h_px = lh + 10
        if "Střed nahoru" in pozice_loga: pos = ((px_w-lw)//2, padding_px)
        elif "Střed dolů" in pozice_loga: pos = ((px_w-lw)//2, px_h-lh-padding_px)
        elif "Levý horní" in pozice_loga: pos = (padding_px, padding_px)
        elif "Pravý horní" in pozice_loga: pos = (px_w-lw-padding_px, padding_px)
        else: pos = (padding_px, px_h-lh-padding_px)
        img.paste(l_img, pos, l_img if l_img.mode == 'RGBA' else None)

    # 2. EAN (připravíme dříve pro výpočet rozvržení)
    bc_img, bc_h = None, 0
    if data_kodu.strip():
        try:
            BC = barcode.get_barcode_class(typ_kodu)
            bc_obj = BC(data_kodu, writer=ImageWriter())
            # Vypneme quiet_zone, aby mohl být EAN přes celou šířku
            raw_bc = bc_obj.render({"background": barva_pozadi, "write_text": False, "quiet_zone": 0.1})
            
            target_h = int(px_h * (velikost_eanu / 100))
            # Šířka EANu: Pokud je padding 0 a velikost 100%, využije celé px_w
            target_w = int((px_w - 2*padding_px))
            
            bc_img = raw_bc.resize((target_w, target_h), Image.Resampling.LANCZOS)
            
            f_ean = get_font(max(12, int(bc_img.size[1]*0.18)))
            full_c = bc_obj.get_fullcode()
            tw = draw.textlength(full_c, font=f_ean)
            
            comb = Image.new("RGB", (bc_img.size[0], bc_img.size[1] + int(f_ean.size*1.2)), barva_pozadi)
            comb.paste(bc_img, (0,0))
            ImageDraw.Draw(comb).text(((comb.size[0]-tw)/2, bc_img.size[1]), full_c, fill="black", font=f_ean)
            bc_img, bc_h = comb, comb.size[1] + 10
        except: pass

    # 3. Text
    lines = wrap_text(vlastni_text, fnt, px_w - 2*padding_px)
    line_h = int(velikost_fontu * 1.0)
    total_text_h = len(lines) * line_h + (max(0, len(lines)-1) * radkovani)

    # 4. Sestavení
    curr_y = padding_px + (px_h - 2*padding_px - (total_text_h + bc_h)) // 2
    if "nahoru" in pozice_loga.lower() or "horní" in pozice_loga.lower():
        curr_y = max(curr_y, padding_px + logo_h_px)

    rgb = tuple(int(barva_textu.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    for l in lines:
        tw = draw.textlength(l, font=fnt)
        draw.text(((px_w - tw)//2, curr_y), l, fill=rgb, font=fnt)
        curr_y += line_h + radkovani
    
    if bc_img:
        # EAN se vloží na střed šířky (respektuje padding)
        img.paste(bc_img, (padding_px, int(px_h - bc_h - padding_px)))
        
    return img

# --- ZOBRAZENÍ ---
st.title("🚀 Štítkovač PRO v 2.6.9")
c1, c2 = st.columns([3, 1])

with c1:
    img_preview = vytvor_stitek()
    st.image(img_preview, use_container_width=True)

with c2:
    st.subheader("💾 Export")
    if st.button("📄 Uložit PDF", use_container_width=True):
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        img_io = io.BytesIO()
        img_preview.save(img_io, format='PNG')
        from reportlab.lib.utils import ImageReader
        ir = ImageReader(img_io)
        sx, sy = (A4[0] - cols*s_mm*mm)/2, (A4[1] - rows*v_mm*mm)/2
        for r in range(rows):
            for col in range(cols):
                c.drawImage(ir, sx + col*s_mm*mm, A4[1] - (sy + (r+1)*v_mm*mm), width=s_mm*mm, height=v_mm*mm)
        c.save()
        st.download_button("⬇️ Stáhnout", buf.getvalue(), "stitky.pdf", use_container_width=True)
