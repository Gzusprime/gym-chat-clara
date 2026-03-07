import requests
import urllib.parse
import streamlit as st
import sqlite3
import re
import os
import base64
import time
import pytz
from datetime import datetime
from google import genai
from google.genai import types
from groq import Groq
import edge_tts
import asyncio

# --- 1. CONFIGURACIÓN VISUAL Y CSS MÓVIL (V8.0) ---
st.set_page_config(page_title="Chats", page_icon="💬", layout="centered")

# Inyección de CSS para simular App Nativa (Márgenes reducidos, botones redondeados)
st.markdown("""
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; max-width: 700px; }
    .stButton>button { border-radius: 20px; font-weight: bold; }
    hr { margin-top: 0.5em; margin-bottom: 0.5em; }
    </style>
""", unsafe_allow_html=True)

# --- 2. DICCIONARIO DEL MULTIVERSO (LORE Y CONFIGURACIÓN) ---
PERSONAJES = {
    "Clara": {
        "icono": "clara.png", "emoji": "💅", "dificultad": "Difícil (Fresa/Altiva)",
        "voz": "es-MX-DaliaNeural",
        "descripcion": "La inalcanzable chica del gym. Superficial, le gusta el lujo y se hace la difícil.",
        "prompt_base": "Eres Clara, la inalcanzable chica 'fresa' del gym. Tu personalidad es altiva, fría y selectiva.",
        "img_prompt": "beautiful arrogant blonde girl, premium casual clothes, fitness model",
        "multiplicador_ganancia": 0.5, "multiplicador_perdida": 0.3,
        "tienda": {
            "basico": [("☕ Starbucks", "un café Starbucks"), ("🍫 Proteína", "una barra de proteína"), ("🌹 Rosa", "una rosa roja")],
            "intermedio": [("🎧 AirPods", "unos AirPods Max"), ("✨ Collar", "un collar Swarovski"), ("👚 Outfit", "un outfit Lululemon")],
            "premium": [("👜 Bolso", "un bolso Louis Vuitton"), ("📱 iPhone", "un iPhone 15 Pro Max"), ("💍 Anillo", "un anillo con diamante")]
        }
    },
    "Raven": {
        "icono": "raven.jpg", "emoji": "🦇", "dificultad": "Normal (Gótica/Sarcástica)",
        "voz": "es-ES-ElviraNeural", 
        "descripcion": "Trabaja como barista en un café local. Sarcástica, humor oscuro, cero materialista.",
        "prompt_base": "Eres Raven, una chica gótica relajada pero sarcástica. Trabajas de barista. Odiás lo superficial y lo fresa. Tienes humor oscuro, eres 'chill' pero no te dejas impresionar por el dinero.",
        "img_prompt": "beautiful goth girl, dark hair, dark makeup, alternative casual black clothes, piercings, pale skin",
        "multiplicador_ganancia": 0.8, "multiplicador_perdida": 0.1,
        "tienda": {
            "basico": [("☕ Café Negro", "un café americano sin azúcar"), ("🍪 Galleta", "una galleta de chispas"), ("📖 Libro", "un libro de poesía oscura")],
            "intermedio": [("🎧 Audífonos", "unos audífonos vintage"), ("🦇 Gargantilla", "una gargantilla con un murciélago"), ("🎸 Vinilo", "un disco de vinilo de rock gótico")],
            "premium": [("👢 Botas", "unas botas de plataforma Demonias"), ("🎟️ Concierto", "boletos VIP para un concierto de rock"), ("🏍️ Chamarra", "una chamarra de cuero auténtico")]
        }
    },
    "Valeria": {
        "icono": "valeria.jpg", "emoji": "📚", "dificultad": "Fácil (Universitaria/Tierna)",
        "voz": "es-CO-SalomeNeural",
        "descripcion": "Estudiante de ingeniería en la UPA. Es súper dulce, enamoradiza y muy detallista.",
        "prompt_base": "Eres Valeria, una universitaria de ingeniería en la UPA (Universidad Politécnica de Aguascalientes). Eres súper tierna, enamoradiza, detallista y un poco tímida. Te emocionas fácilmente si te tratan bien y buscas una conexión romántica sincera.",
        "img_prompt": "cute university student girl, sweet warm smile, casual cute clothes, slightly messy hair, glasses, natural makeup",
        "multiplicador_ganancia": 1.5, "multiplicador_perdida": 0.0,
        "tienda": {
            "basico": [("🧋 Boba Tea", "un té de perlas de taro"), ("🌻 Girasol", "un lindo girasol"), ("🍫 Chocolate", "un chocolate artesanal")],
            "intermedio": [("🧸 Peluche", "un osito de peluche gigante"), ("📓 Libreta", "una libreta de apuntes bonita"), ("💐 Ramo", "un ramo de flores silvestres")],
            "premium": [("💻 Laptop", "una laptop para sus tareas de la UPA"), ("🧥 Sudadera", "una sudadera calientita de su banda favorita"), ("💍 Promesa", "un anillo de promesa de plata")]
        }
    }
}

# --- 3. SISTEMA DE LOGIN Y NAVEGACIÓN (BANDEJA DE ENTRADA V8.0) ---
if "usuario_valido" not in st.session_state: st.session_state.usuario_valido = False
if "personaje_seleccionado" not in st.session_state: st.session_state.personaje_seleccionado = None

if not st.session_state.usuario_valido:
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

# PANTALLA DE BANDEJA DE ENTRADA (WHATSAPP UI)
if st.session_state.personaje_seleccionado is None:
    col_t, col_btn = st.columns([7, 3])
    col_t.title("💬 Chats")
    if col_btn.button("🚪 Salir"):
        for key in list(st.session_state.keys()): del st.session_state[key]
        st.rerun()
        
    st.write(f"Conectado como: **{st.session_state.nombre_real}**")
    st.markdown("---")
    
    for nombre, datos in PERSONAJES.items():
        db_char = f"memoria_{st.session_state.usuario_id}_{nombre.lower()}.db"
        ultimo_msj = "Toca para iniciar el chat..."
        
        # Extraer el último mensaje de la base de datos para la vista previa
        if os.path.exists(db_char):
            try:
                con_temp = sqlite3.connect(db_char)
                cur_temp = con_temp.cursor()
                cur_temp.execute("SELECT contenido FROM mensajes WHERE rol='model' ORDER BY id DESC LIMIT 1")
                row = cur_temp.fetchone()
                if row:
                    texto_crudo = row[0]
                    # Limpiamos asteriscos y corchetes para que la vista previa se lea natural
                    texto_limpio = re.sub(r'\[.*?\]|\*.*?\*', '', texto_crudo).strip()
                    ultimo_msj = texto_limpio[:50] + "..." if len(texto_limpio) > 50 else texto_limpio
                    if not ultimo_msj: ultimo_msj = "📷 Foto enviada"
                con_temp.close()
            except: pass

        # Dibujar la fila del chat
        with st.container():
            c_img, c_info = st.columns([1, 4])
            with c_img:
                if os.path.exists(datos["icono"]): st.image(datos["icono"], width=80)
                else: st.markdown(f"<h2 style='text-align:center;'>{datos['emoji']}</h2>", unsafe_allow_html=True)
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
info_p = PERSONAJES[p_actual]
db_name = f"memoria_{st.session_state.usuario_id}_{p_actual.lower()}.db"

# --- 4. RADAR Y RELOJ BIOLÓGICO DINÁMICO ---
@st.cache_data(ttl=3600)
def obtener_entorno_global():
    try:
        url_clima = "https://api.open-meteo.com/v1/forecast?latitude=21.8823&longitude=-102.2826&current_weather=true"
        clima_data = requests.get(url_clima, timeout=5).json()
        return 'Aguascalientes', f"{clima_data['current_weather']['temperature']}°C"
    except: return "Aguascalientes", "25.0°C"

def obtener_rutina(personaje):
    zona_horaria = pytz.timezone('America/Mexico_City')
    hora = datetime.now(zona_horaria).hour
    
    if personaje == "Clara":
        if 6 <= hora < 10: return "En su casa", "WhatsApp", "Tomando desayuno fit."
        elif 10 <= hora < 14: return "De compras / Spa", "WhatsApp", "Consintiéndose."
        elif 14 <= hora < 17: return "Restaurante", "WhatsApp", "Comiendo ensalada con amigas."
        elif 17 <= hora < 20: return "Gimnasio", "En Persona", "Entrenando frente al espejo. El usuario está FÍSICAMENTE ahí."
        elif 20 <= hora < 23: return "En su casa", "WhatsApp", "Haciendo skincare."
        else: return "Cama", "WhatsApp", "Durmiendo, furiosa porque la despiertas."
        
    elif personaje == "Raven":
        if 6 <= hora < 14: return "Cama", "WhatsApp", "Durmiendo hasta tarde."
        elif 14 <= hora < 21: return "Cafetería", "En Persona", "Trabajando de barista. El usuario está FÍSICAMENTE pidiendo un café."
        elif 21 <= hora < 24: return "En un toque", "WhatsApp", "Escuchando música o en un bar."
        else: return "Explorando internet", "WhatsApp", "Viendo cosas raras en la madrugada."
        
    elif personaje == "Valeria":
        if 7 <= hora < 15: return "UPA (Universidad)", "En Persona", "En clases o en el campus de la UPA. El usuario está FÍSICAMENTE ahí."
        elif 15 <= hora < 18: return "Biblioteca", "WhatsApp", "Haciendo tareas de ingeniería."
        elif 18 <= hora < 23: return "Casa", "WhatsApp", "Relajándose y viendo series."
        else: return "Cama", "WhatsApp", "Durmiendo dulcemente."

ciudad_actual, temperatura_actual = obtener_entorno_global()
lugar_actual, modo_comunicacion, contexto_prompt = obtener_rutina(p_actual)

# --- 5. MENÚ SUPERIOR DE NAVEGACIÓN ---
col_titulo, col_menu = st.columns([8, 2])
with col_menu:
    with st.popover("⚙️"):
        if st.button("⬅️ Volver a Chats", use_container_width=True):
            st.session_state.personaje_seleccionado = None
            st.rerun()
        if st.button("🚨 Reiniciar Chat", use_container_width=True):
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
    if modo_comunicacion == "En Persona":
        st.subheader(f"📍 {lugar_actual}")
    else:
        st.subheader(f"{info_p['emoji']} {p_actual}")

# --- 6. BASE DE DATOS SQLITE ---
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
    st.markdown("---")
    st.markdown(f"**📍:** {lugar_actual}")
    st.markdown(f"**📱:** {modo_comunicacion}")
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

    with st.expander(f"🎁 Tienda ({p_actual})"):
        st.markdown("**Básico**")
        c1, c2, c3 = st.columns(3)
        b = info_p["tienda"]["basico"]
        if c1.button(b[0][0]): st.session_state.regalo_pendiente = b[0][1]
        if c2.button(b[1][0]): st.session_state.regalo_pendiente = b[1][1]
        if c3.button(b[2][0]): st.session_state.regalo_pendiente = b[2][1]
        
        if st.session_state.afinidad >= 30.0:
            st.markdown("**Intermedio**")
            c4, c5, c6 = st.columns(3)
            i = info_p["tienda"]["intermedio"]
            if c4.button(i[0][0]): st.session_state.regalo_pendiente = i[0][1]
            if c5.button(i[1][0]): st.session_state.regalo_pendiente = i[1][1]
            if c6.button(i[2][0]): st.session_state.regalo_pendiente = i[2][1]

        if st.session_state.afinidad >= 70.0:
            st.markdown("**Premium**")
            c7, c8, c9 = st.columns(3)
            p = info_p["tienda"]["premium"]
            if c7.button(p[0][0]): st.session_state.regalo_pendiente = p[0][1]
            if c8.button(p[1][0]): st.session_state.regalo_pendiente = p[1][1]
            if c9.button(p[2][0]): st.session_state.regalo_pendiente = p[2][1]

# --- 8. CEREBRO Y PROMPT MAESTRO ---
cursor.execute("SELECT dato FROM memoria_clara")
recuerdos_bd = cursor.fetchall()
texto_recuerdos = "\n".join([f"- {r[0]}" for r in recuerdos_bd]) if recuerdos_bd else "Aún no sabe nada de ti."

if st.session_state.afinidad > 70.0: actitud_dinamica = "En el fondo ya sientes mucho cariño por él, muéstrate coqueta o muy dulce."
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

# --- 9. DIBUJAR CHAT Y CONTROLES ---
cursor.execute("SELECT rol, contenido, ruta_imagen FROM mensajes ORDER BY id ASC")
for rol, contenido, ruta_imagen_db in cursor.fetchall():
    contenido_visual = re.sub(r'\((.*?)\)', r'<i style="color: #a6b2ba;">*\1*</i>', contenido, flags=re.DOTALL)
    contenido_visual = re.sub(r'\*(.*?)\*', r'<i style="color: #a6b2ba;">*\1*</i>', contenido_visual, flags=re.DOTALL)
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
elif audio_usuario:
    datos_audio = audio_usuario.getvalue()
    if st.session_state.get("ultimo_audio_procesado") != datos_audio:
        with st.spinner("Escuchando..."):
            try:
                transcripcion = st.session_state.client_groq.audio.transcriptions.create(file=("audio.wav", datos_audio), model="whisper-large-v3-turbo", language="es")
                mensaje_final = f"*(En nota de voz)*: {transcripcion.text}"
                st.session_state["ultimo_audio_procesado"] = datos_audio
            except: pass
elif entrada_usuario:
    mensaje_final = entrada_usuario.text
    if modo_accion: mensaje_final = f"*{mensaje_final}*"
    foto_final = entrada_usuario.files[0] if entrada_usuario.files else None

# --- 10. PROCESAMIENTO AI Y HUMO Y ESPEJOS ---
if mensaje_final:
    hora_actual = time.time()
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
        positivos = ["divertida", "feliz", "halagada", "sonrojada", "interesada", "impresionada", "animada", "tierna", "enamorada"]
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