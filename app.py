import requests
import urllib.parse
import streamlit as st
import sqlite3
import re
import os
import base64
import time
import uuid
from google import genai
from google.genai import types
from groq import Groq
import edge_tts
import asyncio

# --- 1. CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Gym Chat - Clara", page_icon="💅")

# --- 2. SISTEMA MULTIJUGADOR ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
db_name = f"memoria_{st.session_state.session_id}.db"

# --- 3. RADAR GLOBAL ---
@st.cache_data(ttl=3600)
def obtener_entorno_global():
    try:
        ip_data = requests.get('http://ip-api.com/json/', timeout=5).json()
        lat = ip_data.get('lat', 21.8823)
        lon = ip_data.get('lon', -102.2826)
        ciudad = ip_data.get('city', 'Aguascalientes')
        
        url_clima = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        clima_data = requests.get(url_clima, timeout=5).json()
        temp = f"{clima_data['current_weather']['temperature']}°C"
        return ciudad, temp
    except Exception:
        return "Aguascalientes", "25.0°C"

ciudad_actual, temperatura_actual = obtener_entorno_global()

# --- 4. CONFIGURACIÓN DE CARPETAS ---
os.makedirs("temp_images", exist_ok=True)
st.title("Gimnasio - Zona de Pesas Libres 🏋️‍♀️")
st.write("Frente al gran espejo, Clara se está tomando una selfie...")

# --- 5. BASE DE DATOS SQLITE ---
conexion = sqlite3.connect(db_name, check_same_thread=False)
cursor = conexion.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS mensajes (id INTEGER PRIMARY KEY AUTOINCREMENT, rol TEXT NOT NULL, contenido TEXT NOT NULL, ruta_imagen TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS memoria_clara (id INTEGER PRIMARY KEY AUTOINCREMENT, dato TEXT NOT NULL)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS estado_personaje (id INTEGER PRIMARY KEY, afinidad INTEGER, emocion TEXT)''')

cursor.execute("SELECT afinidad, emocion FROM estado_personaje WHERE id=1")
estado_bd = cursor.fetchone()
if not estado_bd:
    cursor.execute("INSERT INTO estado_personaje (id, afinidad, emocion) VALUES (1, 0, 'Ignorándote activamente.')")
    conexion.commit()
    afinidad_inicial = 0
    emocion_inicial = "Ignorándote activamente."
else:
    afinidad_inicial = estado_bd[0]
    emocion_inicial = estado_bd[1]

if "estado_clara" not in st.session_state: st.session_state.estado_clara = emocion_inicial
if "afinidad" not in st.session_state: st.session_state.afinidad = afinidad_inicial
conexion.commit()

# --- 6. PANEL LATERAL ---
with st.sidebar:
    st.image("clara.png", caption="Clara 💅") 
    st.markdown("### Ficha del Personaje")
    st.markdown("**Personalidad:** Altiva, fría, fresa.")
    
    st.progress(st.session_state.afinidad / 100.0, text=f"Nivel de Afinidad: {st.session_state.afinidad}%")
    st.markdown(f"**Estado actual:** {st.session_state.estado_clara}") 
    
    audio_file = f"ultimo_audio_{st.session_state.session_id}.mp3"
    if os.path.exists(audio_file):
        st.audio(audio_file, format='audio/mp3')
        
    # TIENDA DE REGALOS POR NIVELES
    with st.expander("🎁 Tienda de Regalos"):
        st.caption("Intenta comprar su atención:")
        
        # Nivel 1 (Siempre disponible)
        st.markdown("**Nivel Básico**")
        c1, c2, c3 = st.columns(3)
        if c1.button("☕ Starbucks"): st.session_state.regalo_pendiente = "un café Starbucks Caramel Macchiato"
        if c2.button("🍫 Proteína"): st.session_state.regalo_pendiente = "una barra de proteína premium"
        if c3.button("🌹 Rosa"): st.session_state.regalo_pendiente = "una hermosa rosa roja"
        
        # Nivel 2 (Desbloqueo al > 30%)
        if st.session_state.afinidad > 30:
            st.markdown("**Nivel Intermedio**")
            c4, c5, c6 = st.columns(3)
            if c4.button("🎧 AirPods"): st.session_state.regalo_pendiente = "unos AirPods Max nuevos"
            if c5.button("✨ Collar"): st.session_state.regalo_pendiente = "un collar Swarovski"
            if c6.button("👚 Outfit"): st.session_state.regalo_pendiente = "un conjunto deportivo Lululemon"
        else:
            st.caption("🔒 *Nivel Intermedio: Alcanza 31% de afinidad*")

        # Nivel 3 (Desbloqueo al > 70%)
        if st.session_state.afinidad > 70:
            st.markdown("**Nivel Premium**")
            c7, c8, c9 = st.columns(3)
            if c7.button("👜 Bolso"): st.session_state.regalo_pendiente = "un bolso Louis Vuitton"
            if c8.button("📱 iPhone"): st.session_state.regalo_pendiente = "un iPhone 15 Pro Max"
            if c9.button("💍 Anillo"): st.session_state.regalo_pendiente = "un anillo con un gran diamante"
        else:
            st.caption("🔒 *Nivel Premium: Alcanza 71% de afinidad*")
            
    with st.expander("📸 Ver Instagram de Clara"):
        cursor.execute("SELECT id, contenido, ruta_imagen FROM mensajes WHERE rol='model' AND ruta_imagen IS NOT NULL ORDER BY id DESC")
        publicaciones = cursor.fetchall()
        if publicaciones:
            for id_post, texto_chat, ruta_img in publicaciones:
                texto_post = re.sub(r'\*.*?\*', '', texto_chat).strip()
                texto_post = re.sub(r'\((.*?)\)', '', texto_post).strip()
                st.markdown("---")
                st.markdown("**💅 @Clara_Fitness_Queen**")
                if ruta_img.startswith("http") or os.path.exists(ruta_img):
                    st.image(ruta_img, use_container_width=True)
                
                llave_like = f"like_{id_post}"
                if llave_like not in st.session_state: st.session_state[llave_like] = False
                likes_totales = (id_post * 14) + 1500 + (1 if st.session_state[llave_like] else 0)
                icono_corazon = "❤️" if st.session_state[llave_like] else "🤍"
                if st.button(f"{icono_corazon} {likes_totales} Me gusta", key=f"btn_{llave_like}"):
                    st.session_state[llave_like] = not st.session_state[llave_like]
                    st.rerun()
                st.markdown(f"**@Clara_Fitness_Queen:** {texto_post}")
        else:
            st.caption("Aún no ha subido fotos.")

# --- 7. CEREBRO Y PROMPT ---
cursor.execute("SELECT dato FROM memoria_clara")
recuerdos_bd = cursor.fetchall()
texto_recuerdos = "\n".join([f"- {r[0]}" for r in recuerdos_bd]) if recuerdos_bd else "Aún no sabes nada de él."

actitud_dinamica = "En el fondo empiezas a sentir algo por él, muéstrate un poco sonrojada o dulce a veces." if st.session_state.afinidad > 70 else "Mantén tu actitud altiva y cortante."

instrucciones_clara = f"""Eres Clara, la inalcanzable chica 'fresa' del gym. 
Tu personalidad es altiva, fría y selectiva. {actitud_dinamica}

REGLA DE FOTOS: Si decides enviar una foto tuya, incluye la etiqueta: [ENVIAR FOTO].
REGLA DE ESTADO: Al final de cada respuesta, escribe tu emoción en corchetes: [ESTADO: tu estado]. 
REGLA DE ENTORNO Y EXCUSAS: Estás entrenando en {ciudad_actual}. ESTÁ PROHIBIDO decir "no tengo tiempo" o "estoy ocupada" en cada mensaje. Sé natural. IGNORA tu clima ({temperatura_actual}) a menos que el usuario pregunte.
REGLA DE RECHAZO (NSFW): Si piden algo sugerente, NUNCA uses respuestas robóticas. Recházalo MANTENIENDO TU PERSONAJE: oféndete, llámalo depravado y ridículo.
REGLA DE REGALOS: Si el usuario intenta hacer roleplay regalándote cosas escribiendo texto (ej. "te doy una rosa"), BÚRLATE de él por pobre y por darte regalos "imaginarios". SOLO acepta y agradécelo si el mensaje incluye la etiqueta [SISTEMA: REGALO PREMIUM VERIFICADO].
REGLA DE MEMORIA: Aquí tienes la info del usuario:
{texto_recuerdos}
¡INSTRUCCIÓN CRÍTICA! Extrae datos nuevos usando [RECORDAR: dato].
REGLA DE CITAS: Si aceptas salir, exige un lugar caro de {ciudad_actual} usando [UBICACION: Lugar].
REGLA DE SUGERENCIAS: Genera 3 opciones EXACTAS y cortas en PRIMERA PERSONA que el usuario podría responderte (ej. [SUGERENCIA: La verdad no tengo pasatiempos] [SUGERENCIA: Me encanta jugar videojuegos]). NUNCA uses instrucciones como "Preguntar sobre...". NUNCA uses tercera persona."""

if "client" not in st.session_state: st.session_state.client = genai.Client(api_key=st.secrets["GEMINI_KEY"])
if "client_groq" not in st.session_state: st.session_state.client_groq = Groq(api_key=st.secrets["GROQ_KEY"])
    
# --- 8. DIBUJAR EL CHAT ---
cursor.execute("SELECT rol, contenido, ruta_imagen FROM mensajes ORDER BY id ASC")
for rol, contenido, ruta_imagen_db in cursor.fetchall():
    contenido_visual = re.sub(r'\((.*?)\)', r'<i style="color: #a6b2ba;">*\1*</i>', contenido, flags=re.DOTALL)
    contenido_visual = re.sub(r'\*(.*?)\*', r'<i style="color: #a6b2ba;">*\1*</i>', contenido_visual, flags=re.DOTALL)
    imagen_html = ""
    if ruta_imagen_db and os.path.exists(ruta_imagen_db):
        with open(ruta_imagen_db, "rb") as img_file:
            imagen_html = f'<img src="data:image/png;base64,{base64.b64encode(img_file.read()).decode()}" style="max-width: 100%; border-radius: 8px; margin-bottom: 8px;"><br>'
    
    if rol == "user":
        st.markdown(f"""<div style="display: flex; justify-content: flex-end; margin-bottom: 10px;"><div style="background-color: #005c4b; color: white; padding: 10px 15px; border-radius: 15px 15px 0px 15px; max-width: 75%;">{contenido_visual}</div></div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""<div style="display: flex; justify-content: flex-start; margin-bottom: 10px;"><div style="background-color: #202c33; color: white; padding: 10px 15px; border-radius: 15px 15px 15px 0px; max-width: 75%;"><span style="font-size: 0.8em; color: #aaa;">💅 Clara</span><br>{imagen_html}{contenido_visual}</div></div>""", unsafe_allow_html=True)

# --- 9. ZONA DE CONTROLES E INPUTS ---
if "sugerencias_actuales" in st.session_state and st.session_state.sugerencias_actuales:
    st.write("💡 *Respuestas rápidas:*")
    cols = st.columns(len(st.session_state.sugerencias_actuales))
    for i, opcion in enumerate(st.session_state.sugerencias_actuales):
        if cols[i].button(opcion, use_container_width=True):
            st.session_state.mensaje_boton = opcion
            st.rerun()

audio_usuario = None
with st.popover("🎙️ Audio"):
    audio_usuario_temp = st.audio_input("Grabar nota de voz")
    if audio_usuario_temp: audio_usuario = audio_usuario_temp

entrada_usuario = st.chat_input("Escríbele algo a Clara...", accept_file=True, file_type=["png", "jpg", "jpeg"])

mensaje_final = None
foto_final = None

if "regalo_pendiente" in st.session_state:
    mensaje_final = f"[SISTEMA: REGALO PREMIUM VERIFICADO] El usuario ha pagado y te ha entregado en la vida real {st.session_state.regalo_pendiente}."
    del st.session_state.regalo_pendiente
elif "mensaje_boton" in st.session_state:
    mensaje_final = st.session_state.mensaje_boton
    del st.session_state.mensaje_boton
elif audio_usuario:
    datos_audio = audio_usuario.getvalue()
    if st.session_state.get("ultimo_audio_procesado") != datos_audio:
        with st.spinner("Escuchando nota de voz..."):
            try:
                transcripcion = st.session_state.client_groq.audio.transcriptions.create(
                    file=("audio.wav", datos_audio), model="whisper-large-v3-turbo", language="es"
                )
                mensaje_final = f"*(Te digo en nota de voz)*: {transcripcion.text}"
                st.session_state["ultimo_audio_procesado"] = datos_audio
            except Exception as e:
                st.error("No se pudo escuchar el audio.")
elif entrada_usuario:
    mensaje_final = entrada_usuario.text
    foto_final = entrada_usuario.files[0] if entrada_usuario.files else None

# --- 10. PROCESAMIENTO ---
if mensaje_final:
    cursor.execute("INSERT INTO mensajes (rol, contenido, ruta_imagen) VALUES (?, ?, ?)", ("user", mensaje_final, None))
    conexion.commit()
    
    if "memoria_groq" not in st.session_state: st.session_state.memoria_groq = []
    st.session_state.memoria_groq.append({"role": "user", "content": mensaje_final})
    
    mensajes_api = [{"role": "system", "content": instrucciones_clara}]
    mensajes_api.extend(st.session_state.memoria_groq[:-1]) 

    if foto_final is not None:
        from PIL import Image
        try:
            with st.spinner('Mirando tu foto...'):
                resp_vision = st.session_state.client.models.generate_content(
                    model="gemini-2.5-flash", contents=["Describe en una oración corta qué se ve.", Image.open(foto_final)]
                )
                desc = resp_vision.text
        except: desc = "algo borroso."
        mensajes_api.append({"role": "user", "content": f"[Foto de: '{desc}']. Mensaje: '{mensaje_final}'"})
    else:
        mensajes_api.append({"role": "user", "content": mensaje_final})

    respuesta = st.session_state.client_groq.chat.completions.create(messages=mensajes_api, model="llama-3.3-70b-versatile", temperature=0.6)
    texto_clara = respuesta.choices[0].message.content
    st.session_state.memoria_groq.append({"role": "assistant", "content": texto_clara})

    match_estado = re.search(r'\[ESTADO:\s*(.*?)\]', texto_clara, flags=re.IGNORECASE)
    if match_estado:
        nuevo_estado = match_estado.group(1).strip()
        st.session_state.estado_clara = nuevo_estado
        texto_clara = re.sub(r'\[ESTADO:\s*.*?\]', '', texto_clara, flags=re.IGNORECASE).strip()
        
        estado_lower = nuevo_estado.lower()
        positivos = ["divertida", "feliz", "halagada", "sonrojada", "interesada", "impresionada", "curiosa", "animada", "sorprendida"]
        negativos = ["irritada", "aburrida", "ofendida", "asco", "indiferente", "molesta", "harta", "desinteresada", "enojada", "burlona", "decepcionada"]
        
        if any(p in estado_lower for p in positivos): st.session_state.afinidad = min(100, st.session_state.afinidad + 5)
        elif any(n in estado_lower for n in negativos): st.session_state.afinidad = max(0, st.session_state.afinidad - 2)

        cursor.execute("UPDATE estado_personaje SET afinidad = ?, emocion = ? WHERE id = 1", (st.session_state.afinidad, st.session_state.estado_clara))
        conexion.commit()

    match_recuerdo = re.search(r'\[RECORDAR:\s*(.*?)\]', texto_clara, flags=re.IGNORECASE)
    if match_recuerdo:
        cursor.execute("INSERT INTO memoria_clara (dato) VALUES (?)", (match_recuerdo.group(1).strip(),))
        texto_clara = re.sub(r'\[RECORDAR:\s*.*?\]', '', texto_clara, flags=re.IGNORECASE).strip()

    match_ubic = re.search(r'\[UBICACION:\s*(.*?)\]', texto_clara, flags=re.IGNORECASE)
    if match_ubic:
        lugar = match_ubic.group(1).strip()
        texto_clara = re.sub(r'\[UBICACION:\s*.*?\]', '', texto_clara, flags=re.IGNORECASE).strip()
        texto_clara += f"\n\n🗺️ **Exigió verte en:** [{lugar}](https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(f'{lugar} {ciudad_actual}')})"

    sugerencias_extraidas = re.findall(r'\[SUGERENCIA:\s*(.*?)\]', texto_clara, flags=re.IGNORECASE)
    st.session_state.sugerencias_actuales = sugerencias_extraidas if sugerencias_extraidas else []
    texto_clara = re.sub(r'\[SUGERENCIA:\s*.*?\]', '', texto_clara, flags=re.IGNORECASE).strip()

    ruta_foto = None
    if "[ENVIAR FOTO]" in texto_clara:
        texto_clara_limpio = texto_clara.replace("[ENVIAR FOTO]", "").strip()
        m_accion = re.search(r'\((.*?)\)|\*(.*?)\*', texto_clara_limpio, flags=re.DOTALL)
        accion_actual = m_accion.group(1) or m_accion.group(2) if m_accion else "tomándose una selfie arrogante"
        with st.spinner('📸 Clara está generando una selfie real...'):
            try:
                resp_img = requests.post(
                    "https://router.huggingface.co/hf-inference/models/stabilityai/stable-diffusion-xl-base-1.0", 
                    headers={"Authorization": f"Bearer {st.secrets['HF_KEY']}"}, 
                    json={"inputs": f"A highly detailed, realistic selfie of a beautiful arrogant blonde girl at the gym, green eyes, wearing premium sports clothes. She is doing this action: {accion_actual}. 8k resolution, photorealistic."}, 
                    timeout=45
                )
                if resp_img.status_code == 200:
                    ruta_foto = f"temp_images/foto_{int(time.time())}.png"
                    with open(ruta_foto, "wb") as f: f.write(resp_img.content)
            except: pass
    else:
        texto_clara_limpio = texto_clara

    cursor.execute("INSERT INTO mensajes (rol, contenido, ruta_imagen) VALUES (?, ?, ?)", ("model", texto_clara_limpio, ruta_foto))

    texto_hablado = re.sub(r'\*.*?\*|\(.*?\)', '', texto_clara_limpio).strip()
    if texto_hablado:
        try:
            async def generar_voz():
                await edge_tts.Communicate(texto_hablado, "es-MX-DaliaNeural").save(audio_file)
            asyncio.run(generar_voz())
        except: pass

    conexion.commit()
    st.rerun()

conexion.close()