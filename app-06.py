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

st.set_page_config(page_title="Štítkovač PRO v 2.6.7", layout="wide")

# --- CSS PRO STYLOVÁNÍ ---
st.markdown("""
    <style>
    .stApp { background-color: #31333F; }
    .main h1, .main h2, .main h3, .main p { color: #FFFFFF !important; }
    img { border: 2px solid #000000; background-color: white; }
    div.stButton > button { font-size: 14px; padding: 5px 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNKCE PRO NAČÍTÁNÍ FONTU (KLÍČ K ÚSPĚCHU) ---
def get_font(size):
    # Hledáme soubor font.ttf přímo v kořenovém adresáři aplikace na GitHubu
    font_path = "font.ttf"
    if os.path.exists(font_path):
        return ImageFont.truetype(font_path, size)
    else:
        # Pokud soubor chybí, vypíšeme varování v sidebar
        st.sidebar.error("❌ Soubor 'font.ttf' nenalezen v repozitáři! Velikost a diakritika nebudou fungovat.")
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

# --- SIDEBAR - NASTAVENÍ ---
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
    vlastni_text = st.text_area("Text na štítku", "Příliš žluťoučký kůň úpěl", height=100)
    
    col_c1, col_c2 = st.columns(2)
    with col_c1: barva_textu = st.color_picker("Barva písma", "#000000")
    with col_c2: barva_pozadi = st.color_picker("Barva štítku", "#FFFFFF")

    velikost_fontu = st.slider("Velikost písma", 10, 300, 80)
    radkovani = st.slider("Mezery mezi řádky", 0, 50, 5)
    odsazeni_mm = st.slider("Odsazení obsahu (mm)", 0, 20, 5)
    
    st.divider()
    typ_kodu = st.selectbox("Typ kódu", ["ean13", "ean8", "itf"])
    data_kodu = st.text_input("Data kódu", "123456789012")
    velikost_eanu = st.slider("Velikost EANu (%)", 10, 100, 45)

    st.divider()
    pozice_loga = st.selectbox("Umístění obrázku", [
        "Bez obrázku", "Střed nahoru", "Střed dolů", 
        "Levý horní", "Pravý horní", "Levý dolní", "Pravý dolní"
    ])

    uploaded_file = st.file_uploader("Nahrát vlastní PNG logo", type=["png"])
    
    icon_folder = "assets"
    if os.path.exists(icon_folder):
        available_icons = [f for f in os.listdir(icon_folder) if f.lower().endswith('.png')]
        if available_icons:
            st.write("🖼️ Ikony v assets:")
            cols_icon = st.columns(3)
            for i, icon in enumerate(available_icons):
                with cols_icon[i % 3]:
                    st.image(os.path.join(icon_folder, icon), width=40)
                    if st.button("Vybrat", key=f"icon_{icon}"):
                        st.session_state.selected_icon = icon

# --- GENERÁTOR OBRÁZKU ---
def vytvor_stitek():
    px_w, px_h = int(s_mm * MM_TO_PX), int(v_mm * MM_TO_PX)
    padding_px = int(odsazeni_mm * MM_TO_PX)
    
    img = Image.new("RGB", (px_w, px_h), barva_pozadi)
    draw = ImageDraw.Draw(img)
    
    # 1. Načtení fontu (Důležité pro velikost a diakritiku)
    fnt = get_font(int(velikost_fontu))
    
    # 2. Logo
    logo_h_px = 0
    l_img = None
    if uploaded_file:
        l_img = Image.open(uploaded_file).convert("RGBA")
    elif st.session_state.selected_icon != "Žádná":
        p = os.path.join("assets", st.session_state.selected_icon)
        if os.path.exists(p): l_img = Image.open(p).convert("RGBA")
    
    if l_img and pozice_loga != "Bez obrázku":
        l_size = int(v_mm * 0.2 * MM_TO_PX) # Automatická velikost loga
        l_img.thumbnail((l_size, l_size), Image.Resampling.LANCZOS)
        lw, lh = l_img.size
        logo_h_px = lh + 10
        
        # Pozice loga
        if "Střed nahoru" in pozice_loga: pos = ((px_w-lw)//2, padding_px)
        elif "Střed dolů" in pozice_loga: pos = ((px_w-lw)//2, px_h-lh-padding_px)
        elif "Levý horní" in pozice_loga: pos = (padding_px, padding_px)
        elif "Pravý horní" in pozice_loga: pos = (px_w-lw-padding_px, padding_px)
        else: pos = (padding_px, px_h-lh-padding_px)
        
        img.paste(l_img, pos, l_img)

    # 3. Text
    lines = wrap_text(vlastni_text, fnt, px_w - 2*padding_px)
    line_h = int(velikost_fontu * 1.2)
    total_text_h = len(lines) * line_h + (len(lines)-1) * radkovani

    # 4. EAN
    bc_img, bc_h = None, 0
    if data_kodu.strip():
        try:
            BC = barcode.get_barcode_class(typ_kodu)
            bc_obj = BC(data_kodu, writer=ImageWriter())
            raw_bc = bc_obj.render({"background": barva_pozadi, "write_text": False})
            
            target_h = int(px_h * (velikost_eanu / 100))
            ratio = min(target_h / raw_bc.size[1], (px_w - 2*padding_px) / raw_bc.size[0])
            bc_img = raw_bc.resize((int(raw_bc.size[0]*ratio), int(raw_bc.size[1]*ratio)), Image.Resampling.LANCZOS)
            
            # Text pod EANem
            f_ean = get_font(max(15, int(bc_img.size[1]*0.2)))
            full_c = bc_obj.get_fullcode()
            tw = draw.textlength(full_c, font=f_ean)
            
            comb = Image.new("RGB", (bc_img.size[0], bc_img.size[1] + int(f_ean.size*1.3)), barva_pozadi)
            comb.paste(bc_img, (0,0))
            ImageDraw.Draw(comb).text(((comb.size[0]-tw)/2, bc_img.size[1]), full_c, fill="black", font=f_ean)
            bc_img, bc_h = comb, comb.size[1] + 20
        except: pass

    # 5. Finální seskládání (Centrování)
    curr_y = (px_h - (total_text_h + bc_h)) // 2
    # Pokud je logo nahoře, posuneme start textu
    if "nahoru" in pozice_loga.lower() or "horní" in pozice_loga.lower():
        curr_y = max(curr_y, logo_h_px + padding_px)

    rgb = tuple(int(barva_textu.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
    for l in lines:
        tw = draw.textlength(l, font=fnt)
        draw.text(((px_w - tw)//2, curr_y), l, fill=rgb, font=fnt)
        curr_y += line_h + radkovani
    
    if bc_img:
        img.paste(bc_img, ((px_w - bc_img.size[0])//2, int(curr_y + 10)))
        
    return img

# --- HLAVNÍ PLOCHA ---
st.title("🚀 Štítkovač PRO v 2.6.7")

col_left, col_right = st.columns([3, 1])

with col_left:
    st.subheader("👁️ Živý náhled")
    img_preview = vytvor_stitek()
    st.image(img_preview, width=int(s_mm * 3.8)) # Zvětšení pro monitor

with col_right:
    st.subheader("💾 Export")
    if st.button("📄 Vygenerovat PDF", use_container_width=True):
        buf = io.BytesIO()
        orient = landscape(A4) if (volba_velikosti == "Velké štítky 2x2 (4 ks)" and orientace_2x2 == "Na šířku") else A4
        c = canvas.Canvas(buf, pagesize=orient)
        pw, ph = orient
        
        img_io = io.BytesIO()
        img_preview.save(img_io, format='PNG')
        from reportlab.lib.utils import ImageReader
        ir = ImageReader(img_io)
        
        sx, sy = (pw - cols*s_mm*mm)/2, (ph - rows*v_mm*mm)/2
        for r in range(rows):
            for col in range(cols):
                c.drawImage(ir, sx + col*s_mm*mm, ph - (sy + (r+1)*v_mm*mm), width=s_mm*mm, height=v_mm*mm)
        c.save()
        st.download_button("⬇️ Stáhnout PDF", buf.getvalue(), "stitky.pdf", use_container_width=True)

st.caption(f"Aktuální rozměr štítku: {s_mm} x {v_mm} mm | Rozlišení: 300 DPI")
