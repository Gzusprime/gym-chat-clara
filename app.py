import streamlit as st
import sqlite3
import re
import os
import base64
import time
from google import genai
from groq import Groq
import edge_tts
import asyncio
import requests
from PIL import Image
from io import BytesIO
from datetime import datetime
import pytz

# 🚀 IMPORTAMOS NUESTRO MÓDULO ESTÁTICO (No se toca)
from lore import PERSONAJES, obtener_entorno_global, obtener_rutina

# --- 1. CONFIGURACIÓN VISUAL Y CSS MÓVIL ---
st.set_page_config(page_title="Chats", page_icon="💬", layout="centered")

st.markdown("""
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 700px; }
    .stButton>button { border-radius: 20px; font-weight: bold; }
    hr { margin-top: 0.5em; margin-bottom: 0.5em; }
    header { background: transparent !important; }
    </style>
""", unsafe_allow_html=True)

# Motor de Fondos Dinámicos
def inyectar_fondo(url_imagen):
    st.markdown(f"""
        <style>
        .stApp {{
            background: linear-gradient(rgba(15, 18, 20, 0.88), rgba(15, 18, 20, 0.95)), url('{url_imagen}') no-repeat center center fixed !important;
            background-size: cover !important;
        }}
        </style>
    """, unsafe_allow_html=True)

# --- CONFIGURACIÓN DE RUTAS ---
DIRECTORIO_AVATARS_PERSISTENTES = "avatars_personalizados"
os.makedirs(DIRECTORIO_AVATARS_PERSISTENTES, exist_ok=True)
os.makedirs("temp_images", exist_ok=True)

# --- 2. SISTEMA DE LOGIN Y BILLETERA ---
if "usuario_valido" not in st.session_state: st.session_state.usuario_valido = False
if "personaje_seleccionado" not in st.session_state: st.session_state.personaje_seleccionado = None
if "creando_personaje" not in st.session_state: st.session_state.creando_personaje = False

if not st.session_state.usuario_valido:
    inyectar_fondo("https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=1364") 
    st.title("Hub Principal 🌐")
    st.write("Inicia sesión para acceder a tus chats.")
    nombre_usuario = st.text_input("¿Cuál es tu nombre?")
    if st.button("Iniciar Sesión", use_container_width=True):
        if nombre_usuario.strip():
            st.session_state.usuario_id = re.sub(r'\W+', '', nombre_usuario.lower())
            st.session_state.nombre_real = nombre_usuario.strip()
            st.session_state.usuario_valido = True
            st.rerun()
    st.stop()

db_billetera = f"billetera_{st.session_state.usuario_id}.db"
con_bill = sqlite3.connect(db_billetera, check_same_thread=False)
cur_bill = con_bill.cursor()
cur_bill.execute('CREATE TABLE IF NOT EXISTS economia (id INTEGER PRIMARY KEY, monedas INTEGER)')
cur_bill.execute("SELECT monedas FROM economia WHERE id=1")
row_bill = cur_bill.fetchone()
if not row_bill:
    cur_bill.execute("INSERT INTO economia (id, monedas) VALUES (1, 500)")
    con_bill.commit()
    st.session_state.monedas = 500
else:
    st.session_state.monedas = row_bill[0]
con_bill.close()

def actualizar_monedas(cantidad):
    st.session_state.monedas = cantidad
    con_b = sqlite3.connect(db_billetera)
    con_b.execute("UPDATE economia SET monedas = ? WHERE id = 1", (cantidad,))
    con_b.commit()
    con_b.close()

# --- TIENDA GENÉRICA ESTANDARIZADA (V9.1) ---
TIENDA_UNIVERSAL = {
    "basico": [("☕ Bebida", "una bebida refrescante", 50), ("🍱 Comida", "un enorme banquete de comida deliciosa", 50), ("🎁 Detalle", "un pequeño regalo", 50)],
    "intermedio": [("🎧 Entretenimiento", "algo genial para pasar el rato", 300), ("👕 Atuendo", "ropa nueva", 300), ("🎟️ Pase", "un pase para un evento especial", 300)],
    "premium": [("📱 Tecnología", "un dispositivo de alta tecnología", 1000), ("✈️ Viaje", "un viaje épico a un lugar lejano", 1000), ("💎 Reliquia", "un objeto de valor incalculable", 1000)]
}

# --- 3. MOTOR DE PERSONAJES PERSONALIZADOS (V9.2) ---
todos_los_personajes = dict(PERSONAJES) 

# Adaptamos a Goku existente de la V9.0 a la V9.1 (para que no crashee con la tienda)
for p_nom, p_datos in todos_los_personajes.items():
    if p_nom not in PERSONAJES: # Es personalizado de V9.0
        p_datos["tienda"] = TIENDA_UNIVERSAL

db_bots = f"bots_custom_{st.session_state.usuario_id}.db"
con_bots = sqlite3.connect(db_bots, check_same_thread=False)
cur_bots = con_bots.cursor()

# Actualización de esquema (Sprint 9.2: Añadir ruta_avatar para persistencia)
try: cur_bots.execute("ALTER TABLE mis_bots ADD COLUMN ruta_avatar TEXT")
except: pass # Si ya existe la columna, ignora el error

cur_bots.execute('''CREATE TABLE IF NOT EXISTS mis_bots 
    (nombre TEXT, emoji TEXT, descripcion TEXT, prompt TEXT, img_prompt TEXT, voz TEXT, ruta_avatar TEXT)''')
cur_bots.execute("SELECT * FROM mis_bots")

for row in cur_bots.fetchall():
    nom, emo, desc, p_base, p_img, voz, ruta_av = row
    todos_los_personajes[nom] = {
        "icono": ruta_av if ruta_av and os.path.exists(ruta_av) else "sin_foto.png", 
        "emoji": emo,
        "dificultad": "Personalizado 🧠",
        "voz": voz,
        "descripcion": desc,
        "prompt_base": p_base,
        "img_prompt": p_img,
        "multiplicador_ganancia": 1.0, 
        "multiplicador_perdida": 0.1,
        "tienda": TIENDA_UNIVERSAL 
    }
con_bots.close()

# --- 4. FORMULARIO DE CREACIÓN DE PERSONAJE CON AVATAR PERSISTENTE ---
if st.session_state.creando_personaje:
    inyectar_fondo("https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=1364")
    st.title("🛠️ Fábrica de Personajes")
    st.write("Diseña el cerebro y la apariencia de tu propia IA.")
    
    with st.form("form_nuevo_bot", clear_on_submit=False):
        c1, c2 = st.columns([4, 1])
        n_nombre = c1.text_input("Nombre de la IA", placeholder="Ej. Sofía, Goku, etc.")
        n_emoji = c2.text_input("Emoji", value="🤖", max_chars=2)
        
        n_desc = st.text_input("Descripción Corta", placeholder="Ej. Guerrero Saiyajin legendario.")
        n_prompt = st.text_area("Prompt Maestro (Su alma)", placeholder="Eres [Nombre], tienes una personalidad...", height=100)
        n_img = st.text_area("Prompt Visual (En inglés, para sus fotos y avatar)", placeholder="goku super saiyan, photorealistic, cinematic lighting, 8k...", height=80)
        n_voz = st.selectbox("Acento de Voz", [
            "es-MX-DaliaNeural", # Mexicana
            "es-ES-ElviraNeural", # Española
            "es-CO-SalomeNeural", # Colombiana
            "es-AR-ElenaNeural", # Argentina
            "es-MX-JorgeNeural"  # Mexicano (Hombre)
        ])
        
        st.write("🔒 *Al crear el bot, se le asignará una economía universal.*")
        
        btn_crear = st.form_submit_button("🧪 Darle Vida (Crear)")
        
        if btn_crear and n_nombre and n_prompt:
            ruta_avatar_guardado = None
            if n_img: # Generamos avatar persistente
                with st.spinner(f"📸 Generando avatar permanente para {n_nombre} (esto tarda 30s)..."):
                    try:
                        # Usamos SDXL para la foto de perfil permanente
                        resp_img_av = requests.post(
                            "https://router.huggingface.co/hf-inference/models/stabilityai/stable-diffusion-xl-base-1.0", 
                            headers={"Authorization": f"Bearer {st.secrets['HF_KEY']}"}, 
                            json={"inputs": f"highly detailed 1:1 square profile picture of {n_img}. 8k, photorealistic, looking at camera."}, 
                            timeout=60
                        )
                        if resp_img_av.status_code == 200:
                            # Recortar y guardar permanentemente en formato cuadrado
                            imagen_av = Image.open(BytesIO(resp_img_av.content))
                            # Forzar 1:1
                            width, height = imagen_av.size
                            min_dim = min(width, height)
                            left = (width - min_dim)/2
                            top = (height - min_dim)/2
                            right = (width + min_dim)/2
                            bottom = (height + min_dim)/2
                            imagen_recortada = imagen_av.crop((left, top, right, bottom))
                            
                            nombre_archivo_av = f"{re.sub(r'\W+', '', n_nombre.lower())}_{int(time.time())}.png"
                            ruta_avatar_guardado = os.path.join(DIRECTORIO_AVATARS_PERSISTENTES, nombre_archivo_av)
                            imagen_recortada.save(ruta_avatar_guardado, format="PNG")
                    except: pass

            con_b2 = sqlite3.connect(db_bots)
            con_b2.execute("INSERT INTO mis_bots VALUES (?, ?, ?, ?, ?, ?, ?)", 
                          (n_nombre.strip(), n_emoji, n_desc, n_prompt, n_img, n_voz, ruta_avatar_guardado))
            con_b2.commit()
            con_b2.close()
            st.session_state.creando_personaje = False
            st.toast(f"¡{n_nombre} ha nacido!", icon="🎉")
            st.rerun()

    if st.button("❌ Cancelar", use_container_width=True):
        st.session_state.creando_personaje = False
        st.rerun()
    st.stop()

# --- 5. PANTALLA DE BANDEJA DE ENTRADA ---
if st.session_state.personaje_seleccionado is None:
    inyectar_fondo("https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?q=80&w=1364") 
    col_t, col_btn = st.columns([7, 3])
    col_t.title("💬 Chats")
    if col_btn.button("🚪 Salir"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()
        
    st.write(f"Conectado como: **{st.session_state.nombre_real}** | 💳 **{st.session_state.monedas} 🪙**")
    
    if st.button("➕ Diseña tu propio Personaje", use_container_width=True):
        st.session_state.creando_personaje = True
        st.rerun()
        
    st.markdown("---")
    
    for nombre, datos in todos_los_personajes.items():
        db_char = f"memoria_{st.session_state.usuario_id}_{nombre.lower()}.db"
        ultimo_msj = "Toca para iniciar el chat..."
        
        if os.path.exists(db_char):
            try:
                con_temp = sqlite3.connect(db_char)
                cur_temp = con_temp.cursor()
                cur_temp.execute("SELECT contenido FROM mensajes WHERE rol='model' ORDER BY id DESC LIMIT 1")
                row = cur_temp.fetchone()
                if row:
                    texto_crudo = row[0]
                    texto_limpio = re.sub(r'\[.*?\]|\*.*?\*', '', texto_crudo).strip()
                    ultimo_msj = texto_limpio[:50] + "..." if len(texto_limpio) > 50 else texto_limpio
                    if not ultimo_msj: ultimo_msj = "📷 Foto enviada"
                con_temp.close()
            except: pass

        with st.container():
            c_img, c_info = st.columns([1, 4])
            with c_img:
                if os.path.exists(datos["icono"]): st.image(datos["icono"], width=80)
                # Si es personalizado y no tiene foto, usa un emoji gigante
                else: st.markdown(f"<h1 style='text-align:center;'>{datos['emoji']}</h1>", unsafe_allow_html=True)
            with c_info:
                st.markdown(f"**{nombre}** {datos['emoji']}")
                st.caption(f"_{ultimo_msj}_")
                if st.button(f"Abrir chat", key=f"btn_{nombre}", use_container_width=True):
                    st.session_state.personaje_seleccionado = nombre
                    if "memoria_groq" in st.session_state: del st.session_state.memoria_groq
                    if "sugerencias_actuales" in st.session_state: del st.session_state.sugerencias_actuales
                    st.rerun()
            st.markdown("---")
            
    st.stop()

# --- SI LLEGAMOS AQUÍ, YA HAY UN PERSONAJE SELECCIONADO ---
p_actual = st.session_state.personaje_seleccionado
info_p = todos_los_personajes[p_actual]
db_name = f"memoria_{st.session_state.usuario_id}_{p_actual.lower()}.db"

# --- 4. RADAR Y RELOJ BIOLÓGICO ---
ciudad_actual, temperatura_actual = obtener_entorno_global()

# Adaptar el entorno si es bot base o personalizado
if p_actual in PERSONAJES:
    lugar_actual, modo_comunicacion, contexto_prompt, url_fondo_dinamico = obtener_rutina(p_actual)
else:
    # Rutina Genérica para Bots Personalizados (Goku)
    zona_horaria = pytz.timezone('America/Mexico_City')
    hora = datetime.now(zona_horaria).hour
    if 6 <= hora < 18:
        lugar_actual, modo_comunicacion, contexto_prompt, url_fondo_dinamico = "Explorando", "En Persona", "Estás realizando tus actividades.", "https://images.unsplash.com/photo-1506744626753-eda818c24f55?q=80&w=1470"
    elif 18 <= hora < 22:
        lugar_actual, modo_comunicacion, contexto_prompt, url_fondo_dinamico = "Descansando", "WhatsApp", "Estás descansando después de un día activo.", "https://images.unsplash.com/photo-1513694203232-719a280e022f?q=80&w=1469"
    else:
        lugar_actual, modo_comunicacion, contexto_prompt, url_fondo_dinamico = "Base de Operaciones", "WhatsApp", "Es de madrugada.", "https://images.unsplash.com/photo-1534447677768-be436bb09401?q=80&w=1494"

inyectar_fondo(url_fondo_dinamico)

# --- 5. MENÚ SUPERIOR DE NAVEGACIÓN ---
col_titulo, col_menu = st.columns([8, 2])
with col_menu:
    with st.popover("⚙️"):
        if st.button("⬅️ Volver", use_container_width=True):
            st.session_state.personaje_seleccionado = None
            st.rerun()
        if st.button("🚨 Reiniciar", use_container_width=True):
            con = sqlite3.connect(db_name, check_same_thread=False)
            con.execute("DELETE FROM mensajes")
            con.execute("DELETE FROM memoria_clara")
            con.execute("DELETE FROM meta_datos")
            con.execute("UPDATE estado_personaje SET afinidad = 0.0, emocion = 'Indiferente' WHERE id = 1")
            con.commit()
            st.session_state.afinidad = 0.0
            st.session_state.estado_clara = "Indiferente"
            if "memoria_groq" in st.session_state: del st.session_state.memoria_groq
            st.rerun()

with col_titulo:
    if modo_comunicacion == "En Persona": st.subheader(f"📍 {lugar_actual}")
    else: st.subheader(f"{info_p['emoji']} {p_actual}")

# --- 6. BASE DE DATOS SQLITE DE CHAT ---
conexion = sqlite3.connect(db_name, check_same_thread=False)
cursor = conexion.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS mensajes (id INTEGER PRIMARY KEY AUTOINCREMENT, rol TEXT NOT NULL, contenido TEXT NOT NULL, ruta_imagen TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS memoria_clara (id INTEGER PRIMARY KEY AUTOINCREMENT, dato TEXT NOT NULL)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS estado_personaje (id INTEGER PRIMARY KEY, afinidad REAL, emocion TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS meta_datos (clave TEXT PRIMARY KEY, valor TEXT)''')

cursor.execute("SELECT afinidad, emocion FROM estado_personaje WHERE id=1")
estado_bd = cursor.fetchone()
if not estado_bd:
    cursor.execute("INSERT INTO estado_personaje (id, afinidad, emocion) VALUES (1, 0.0, 'Indiferente')")
    conexion.commit()
    afinidad_inicial, emocion_inicial = 0.0, "Indiferente"
else:
    afinidad_inicial, emocion_inicial = float(estado_bd[0]), estado_bd[1]

if "estado_clara" not in st.session_state: st.session_state.estado_clara = emocion_inicial
if "afinidad" not in st.session_state: st.session_state.afinidad = afinidad_inicial

# --- 7. PANEL LATERAL DINÁMICO ---
with st.sidebar:
    if os.path.exists(info_p["icono"]): st.image(info_p["icono"])
    # Si es personalizado y usa el emoji fallback (V9.0)
    else: st.markdown(f"<h1 style='text-align:center; font-size: 80px;'>{info_p['emoji']}</h1>", unsafe_allow_html=True)
    
    st.markdown("---")
    st.markdown(f"**📍 Lugar:** {lugar_actual}")
    st.markdown(f"**📱 Vía:** {modo_comunicacion}")
    st.markdown("---")
    st.markdown(f"### 💳 Billetera: {st.session_state.monedas} 🪙")
    st.markdown("---")
    
    st.progress(min(st.session_state.afinidad / 100.0, 1.0), text=f"Afinidad: {st.session_state.afinidad:.1f}%")
    st.markdown(f"**Estado:** {st.session_state.estado_clara}") 
    
    audio_file = f"ultimo_audio_{st.session_state.usuario_id}_{p_actual}.mp3"
    
    with st.expander("⚙️ Ajustes IA"):
        creatividad_ia = st.slider("Creatividad", 0.1, 1.0, 0.6, 0.1)
        longitud_ia = st.selectbox("Longitud", ["Corta", "Normal", "Detallada"], index=1)
        if longitud_ia == "Corta": regla_longitud = "Responde breve, máximo 2 oraciones."
        elif longitud_ia == "Detallada": regla_longitud = "Responde detallado, con pensamientos en cursiva."
        else: regla_longitud = "Responde natural."

    def procesar_compra(nombre, desc, precio):
        if st.session_state.monedas >= precio:
            actualizar_monedas(st.session_state.monedas - precio)
            st.session_state.regalo_pendiente = desc
            st.rerun()
        else:
            st.toast(f"❌ Necesitas {precio}🪙 para comprar esto.", icon="💸")

    with st.expander(f"🎁 Tienda ({p_actual})"):
        st.markdown("**Básico**")
        c1, c2, c3 = st.columns(3)
        b = info_p["tienda"]["basico"]
        if c1.button(f"{b[0][0]}\n({b[0][2]}🪙)"): procesar_compra(b[0][0], b[0][1], b[0][2])
        if c2.button(f"{b[1][0]}\n({b[1][2]}🪙)"): procesar_compra(b[1][0], b[1][1], b[1][2])
        if c3.button(f"{b[2][0]}\n({b[2][2]}🪙)"): procesar_compra(b[2][0], b[2][1], b[2][2])
        
        if st.session_state.afinidad >= 30.0:
            st.markdown("**Intermedio**")
            c4, c5, c6 = st.columns(3)
            i = info_p["tienda"]["intermedio"]
            if c4.button(f"{i[0][0]}\n({i[0][2]}🪙)"): procesar_compra(i[0][0], i[0][1], i[0][2])
            if c5.button(f"{i[1][0]}\n({i[1][2]}🪙)"): procesar_compra(i[1][0], i[1][1], i[1][2])
            if c6.button(f"{i[2][0]}\n({i[2][2]}🪙)"): procesar_compra(i[2][0], i[2][1], i[2][2])

        if st.session_state.afinidad >= 70.0:
            st.markdown("**Premium**")
            c7, c8, c9 = st.columns(3)
            p = info_p["tienda"]["premium"]
            if c7.button(f"{p[0][0]}\n({p[0][2]}🪙)"): procesar_compra(p[0][0], p[0][1], p[0][2])
            if c8.button(f"{p[1][0]}\n({p[1][2]}🪙)"): procesar_compra(p[1][0], p[1][1], p[1][2])
            if c9.button(f"{p[2][0]}\n({p[2][2]}🪙)"): procesar_compra(p[2][0], p[2][1], p[2][2])

# --- 9. CEREBRO Y PROMPT MAESTRO ---
cursor.execute("SELECT dato FROM memoria_clara")
recuerdos_bd = cursor.fetchall()
texto_recuerdos = "\n".join([f"- {r[0]}" for r in recuerdos_bd]) if recuerdos_bd else "Aún no sabe nada de ti."

if st.session_state.afinidad > 70.0: actitud_dinamica = "En el fondo ya sientes mucho cariño por él, muéstrate amigable."
elif st.session_state.afinidad < 20.0: actitud_dinamica = "Apenas lo conoces, mantén tu distancia y tu personalidad base fuerte."
else: actitud_dinamica = "Empiezas a agarrarle confianza, trátalo con amabilidad pero sin exagerar."

instrucciones_clara = f"""{info_p['prompt_base']}
{actitud_dinamica}

REGLA DE CONTEXTO: Estás en {ciudad_actual}. {contexto_prompt}
Si están por WhatsApp, actúa como tal. SI EL USUARIO INTENTA INTERACTUAR FÍSICAMENTE CONTIGO y NO están en persona, BÚRLATE DE ÉL y recuérdale que estás en {lugar_actual} leyéndolo por mensaje.
REGLA DE LONGITUD: {regla_longitud}
REGLA DE FOTOS: Si decides enviar una foto tuya en {lugar_actual}, usa: [ENVIAR FOTO].
REGLA DE ESTADO: Al final de cada respuesta, escribe tu emoción en corchetes: [ESTADO: tu estado]. 
REGLA DE REGALOS: Si intenta hacer roleplay regalándote cosas falsas de texto, BÚRLATE. SOLO acepta si el mensaje dice [SISTEMA: REGALO PREMIUM VERIFICADO].
REGLA DE MEMORIA: El usuario se llama {st.session_state.nombre_real}. Info sobre él:
{texto_recuerdos}
¡CRÍTICO! Extrae datos nuevos de su vida usando [RECORDAR: dato].
REGLA DE SUGERENCIAS (OBLIGATORIA): Escribe 3 posibles respuestas cortas que EL USUARIO te podría contestar. Usa EXACTAMENTE este formato: [SUGERENCIA: Lo que diría el usuario]. NUNCA agregues explicaciones."""

if "client" not in st.session_state: st.session_state.client = genai.Client(api_key=st.secrets["GEMINI_KEY"])
if "client_groq" not in st.session_state: st.session_state.client_groq = Groq(api_key=st.secrets["GROQ_KEY"])

# --- 10. DIBUJAR CHAT Y CONTROLES ---
cursor.execute("SELECT rol, contenido, ruta_imagen FROM mensajes ORDER BY id ASC")
for rol, contenido, ruta_imagen_db in cursor.fetchall():
    contenido_visual = re.sub(r'\((.*?)\)', r'<i style="color: #a6b2ba;">*\1*</i>', contenido, flags=re.DOTALL)
    contenido_visual = re.sub(r'\*(.*?)\*', r'<i style="color: #a6b2ba;">*\1*</i>', contenido_visual, flags=re.DOTALL)
    
    if "[SISTEMA: REGALO PREMIUM VERIFICADO]" in contenido_visual:
        contenido_visual = contenido_visual.replace("[SISTEMA: REGALO PREMIUM VERIFICADO] El usuario te ha enviado", "🎁 <b>Regalo enviado:</b>")
        
    imagen_html = ""
    if ruta_imagen_db and os.path.exists(ruta_imagen_db):
        with open(ruta_imagen_db, "rb") as img_file:
            imagen_html = f'<img src="data:image/png;base64,{base64.b64encode(img_file.read()).decode()}" style="max-width: 100%; border-radius: 8px; margin-bottom: 8px;"><br>'
    
    if rol == "user":
        st.markdown(f"""<div style="display: flex; justify-content: flex-end; margin-bottom: 10px;"><div style="background-color: #005c4b; color: white; padding: 10px 15px; border-radius: 15px 15px 0px 15px; max-width: 85%;">{contenido_visual}</div></div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""<div style="display: flex; justify-content: flex-start; margin-bottom: 10px;"><div style="background-color: #202c33; color: white; padding: 10px 15px; border-radius: 15px 15px 15px 0px; max-width: 85%;"><span style="font-size: 0.8em; color: #aaa;">{info_p['emoji']} {p_actual}</span><br>{imagen_html}{contenido_visual}</div></div>""", unsafe_allow_html=True)

if os.path.exists(audio_file): st.audio(audio_file, format='audio/mp3')

col_mic, col_sug, col_act = st.columns([2, 3, 4])
audio_usuario = None
with col_mic:
    with st.popover("🎙️ Voz"):
        audio_usuario_temp = st.audio_input("Grabar")
        if audio_usuario_temp: audio_usuario = audio_usuario_temp

with col_sug:
    if "sugerencias_actuales" in st.session_state and st.session_state.sugerencias_actuales:
        with st.popover("✨ Sug"):
            for i, opcion in enumerate(st.session_state.sugerencias_actuales):
                if st.button(opcion, use_container_width=True, key=f"sug_{i}"):
                    st.session_state.mensaje_boton = opcion
                    st.rerun()

with col_act: modo_accion = st.toggle("🎬 Acción")

entrada_usuario = st.chat_input(f"Mensaje para {p_actual}...", accept_file=True, file_type=["png", "jpg", "jpeg"])

mensaje_final, foto_final = None, None

if "regalo_pendiente" in st.session_state:
    mensaje_final = f"[SISTEMA: REGALO PREMIUM VERIFICADO] El usuario te ha enviado {st.session_state.regalo_pendiente}."
    del st.session_state.regalo_pendiente
elif "mensaje_boton" in st.session_state:
    mensaje_final = st.session_state.mensaje_boton
    del st.session_state.mensaje_boton
    actualizar_monedas(st.session_state.monedas + 5)
    st.toast("¡Ganaste +5 🪙 por platicar!", icon="💰")
elif audio_usuario:
    datos_audio = audio_usuario.getvalue()
    if st.session_state.get("ultimo_audio_procesado") != datos_audio:
        with st.spinner("Escuchando..."):
            try:
                transcripcion = st.session_state.client_groq.audio.transcriptions.create(file=("audio.wav", datos_audio), model="whisper-large-v3-turbo", language="es")
                mensaje_final = f"*(En nota de voz)*: {transcripcion.text}"
                st.session_state["ultimo_audio_procesado"] = datos_audio
                actualizar_monedas(st.session_state.monedas + 5)
                st.toast("¡Ganaste +5 🪙 por tu nota de voz!", icon="💰")
            except: pass
elif entrada_usuario:
    mensaje_final = entrada_usuario.text
    if modo_accion: mensaje_final = f"*{mensaje_final}*"
    foto_final = entrada_usuario.files[0] if entrada_usuario.files else None
    actualizar_monedas(st.session_state.monedas + 5)
    st.toast("¡Ganaste +5 🪙 por platicar!", icon="💰")

# --- 11. PROCESAMIENTO AI Y LIMPIEZA AUTOMÁTICA (SPRINT C) ---
if mensaje_final:
    hora_actual = time.time()
    
    # --- Sprint C (Producción): Limpiador de carpeta temp_images ---
    # Eliminar imágenes de chat antiguas (más de 1 hora) para ahorrar espacio en la nube
    with st.spinner("🧹 Limpiando sistema..."):
        ahora = time.time()
        for f in os.listdir("temp_images"):
            if f.endswith(".png"):
                ruta_f = os.path.join("temp_images", f)
                if os.stat(ruta_f).st_mtime < ahora - 3600: # 1 hora
                    try: os.remove(ruta_f)
                    except: pass
                    
    horas_ausente = 0.0
    cursor.execute("SELECT valor FROM meta_datos WHERE clave='ultima_conexion'")
    row = cursor.fetchone()
    if row:
        ultima_conexion = float(row[0])
        horas_ausente = (hora_actual - ultima_conexion) / 3600.0

    cursor.execute("INSERT OR REPLACE INTO meta_datos (clave, valor) VALUES (?, ?)", ("ultima_conexion", str(hora_actual)))
    conexion.commit()

    mensaje_para_api = mensaje_final
    if horas_ausente >= 2.0 and row is not None:
        reclamo = f"[SISTEMA: El usuario te dejó en 'visto' y desapareció por {int(horas_ausente)} horas. Reclámale sutilmente por dejarte esperando antes de contestar.]\n\n"
        mensaje_para_api = reclamo + mensaje_final

    cursor.execute("INSERT INTO mensajes (rol, contenido, ruta_imagen) VALUES (?, ?, ?)", ("user", mensaje_final, None))
    conexion.commit()
    
    if "memoria_groq" not in st.session_state: st.session_state.memoria_groq = []
    st.session_state.memoria_groq.append({"role": "user", "content": mensaje_para_api})
    
    mensajes_api = [{"role": "system", "content": instrucciones_clara}]
    historial_reciente = st.session_state.memoria_groq[-11:-1] if len(st.session_state.memoria_groq) > 10 else st.session_state.memoria_groq[:-1]
    mensajes_api.extend(historial_reciente)

    if foto_final is not None:
        try:
            from PIL import Image
            resp_vision = st.session_state.client.models.generate_content(model="gemini-2.5-flash", contents=["Describe esto corto.", Image.open(foto_final)])
            mensajes_api.append({"role": "user", "content": f"[Foto: '{resp_vision.text}']. Msj: '{mensaje_para_api}'"})
        except: mensajes_api.append({"role": "user", "content": mensaje_para_api})
    else: mensajes_api.append({"role": "user", "content": mensaje_para_api})

    with st.spinner("Escribiendo..."):
        time.sleep(1.5) 
        respuesta = st.session_state.client_groq.chat.completions.create(messages=mensajes_api, model="llama-3.3-70b-versatile", temperature=creatividad_ia)
        
    texto_clara = respuesta.choices[0].message.content
    st.session_state.memoria_groq.append({"role": "assistant", "content": texto_clara})

    match_estado = re.search(r'\[ESTADO:\s*(.*?)\]', texto_clara, flags=re.IGNORECASE)
    if match_estado:
        st.session_state.estado_clara = match_estado.group(1).strip()
        texto_clara = re.sub(r'\[ESTADO:\s*.*?\]', '', texto_clara, flags=re.IGNORECASE).strip()
        
        e_low = st.session_state.estado_clara.lower()
        positivos = ["divertida", "feliz", "halagada", "sonrojada", "interesada", "impresionada", "animada", "tierna", "enamorada", "amigable"]
        negativos = ["irritada", "aburrida", "ofendida", "asco", "indiferente", "molesta", "harta"]
        
        ganancia = info_p["multiplicador_ganancia"]
        perdida = info_p["multiplicador_perdida"]
        if any(p in e_low for p in positivos): st.session_state.afinidad = min(100.0, st.session_state.afinidad + ganancia)
        elif any(n in e_low for n in negativos): st.session_state.afinidad = max(0.0, st.session_state.afinidad - perdida)

        cursor.execute("UPDATE estado_personaje SET afinidad = ?, emocion = ? WHERE id = 1", (st.session_state.afinidad, st.session_state.estado_clara))
        conexion.commit()

    match_recuerdo = re.search(r'\[RECORDAR:\s*(.*?)\]', texto_clara, flags=re.IGNORECASE)
    if match_recuerdo:
        cursor.execute("INSERT INTO memoria_clara (dato) VALUES (?)", (match_recuerdo.group(1).strip(),))
        texto_clara = re.sub(r'\[RECORDAR:\s*.*?\]', '', texto_clara, flags=re.IGNORECASE).strip()

    sugerencias_extraidas = re.findall(r'\[SUGE.*?:\s*(.*?)\]', texto_clara, flags=re.IGNORECASE)
    st.session_state.sugerencias_actuales = sugerencias_extraidas if sugerencias_extraidas else []
    texto_clara = re.sub(r'\[SUGE.*?:\s*.*?\]', '', texto_clara, flags=re.IGNORECASE).strip()

    ruta_foto = None
    match_foto = re.search(r'\[ENVIAR FOTO:?\s*(.*?)\]', texto_clara, flags=re.IGNORECASE)
    if match_foto:
        descripcion_interna = match_foto.group(1).strip()
        texto_clara_limpio = re.sub(r'\[ENVIAR FOTO:?\s*.*?\]', '', texto_clara, flags=re.IGNORECASE).strip()
        
        if descripcion_interna: accion_actual = descripcion_interna
        else:
            m_accion = re.search(r'\((.*?)\)|\*(.*?)\*', texto_clara_limpio, flags=re.DOTALL)
            accion_actual = m_accion.group(1) or m_accion.group(2) if m_accion else "selfie"
            
        if st.session_state.afinidad < 30.0: actitud_visual = "distant, cold expression, looking away"
        elif st.session_state.afinidad < 70.0: actitud_visual = "looking at camera, slight smile"
        else: actitud_visual = "cute pose, warm smile, blushing, flirty"

        with st.spinner('📸 Generando foto...'):
            try:
                resp_img = requests.post(
                    "https://router.huggingface.co/hf-inference/models/stabilityai/stable-diffusion-xl-base-1.0", 
                    headers={"Authorization": f"Bearer {st.secrets['HF_KEY']}"}, 
                    json={"inputs": f"{info_p['img_prompt']} at {lugar_actual}. Action: {accion_actual}. Mood: {actitud_visual}. 8k, photorealistic."}, 
                    timeout=45
                )
                if resp_img.status_code == 200:
                    ruta_foto = f"temp_images/foto_{int(time.time())}.png"
                    with open(ruta_foto, "wb") as f: f.write(resp_img.content)
            except: pass
    else: texto_clara_limpio = texto_clara

    cursor.execute("INSERT INTO mensajes (rol, contenido, ruta_imagen) VALUES (?, ?, ?)", ("model", texto_clara_limpio, ruta_foto))

    texto_hablado = re.sub(r'\*.*?\*|\(.*?\)', '', texto_clara_limpio).strip()
    if texto_hablado:
        try:
            async def generar_voz(): await edge_tts.Communicate(texto_hablado, info_p["voz"]).save(audio_file)
            asyncio.run(generar_voz())
        except: pass

    conexion.commit()
    st.rerun()

conexion.close()