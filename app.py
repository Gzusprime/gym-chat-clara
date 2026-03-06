import requests
import urllib.parse
import streamlit as st
import sqlite3
import re
import os
import base64
import time
import uuid
import pytz
from datetime import datetime
from google import genai
from google.genai import types
from groq import Groq
import edge_tts
import asyncio

# --- 1. CONFIGURACIÓN VISUAL ---
st.set_page_config(page_title="Clara - Chat", page_icon="💅")

# --- 2. SISTEMA MULTIJUGADOR ---
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
db_name = f"memoria_{st.session_state.session_id}.db"

# --- 3. RADAR GLOBAL Y RELOJ BIOLÓGICO (PARCHE 4.0) ---
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

def obtener_rutina_clara():
    # Obligamos al servidor a usar la hora de México Central
    zona_horaria = pytz.timezone('America/Mexico_City')
    hora_actual = datetime.now(zona_horaria).hour

    # El Ciclo Circadiano de Clara
    if 6 <= hora_actual < 10:
        return "En su casa", "Mensajes de WhatsApp", "Estás en tu casa tomando tu desayuno fit (un matcha). Te comunicas con el usuario por WhatsApp."
    elif 10 <= hora_actual < 14:
        return "De compras / Spa", "Mensajes de WhatsApp", "Estás ocupada consintiéndote, en el dermatólogo o de compras. Te comunicas por WhatsApp."
    elif 14 <= hora_actual < 17:
        return "Restaurante", "Mensajes de WhatsApp", "Estás comiendo una ensalada carísima con tus amigas. Revisas tu celular y le contestas por WhatsApp."
    elif 17 <= hora_actual < 18:
        return "Camino al Gym", "Mensajes de WhatsApp", "Estás manejando tu camioneta rumbo al gimnasio. Estás atrapada en el tráfico y contestas por WhatsApp."
    elif 18 <= hora_actual < 20: # 6:00 PM a 7:59 PM (Su hora de Gimnasio)
        return "Gimnasio - Zona de Pesas Libres", "En Persona", "Estás FÍSICAMENTE en el gimnasio, frente al gran espejo. El usuario está ahí contigo en persona."
    elif 20 <= hora_actual < 23:
        return "En su casa (Skincare)", "Mensajes de WhatsApp", "Ya te bañaste, estás en pijama de seda haciendo tu rutina de skincare de noche. Le contestas por WhatsApp."
    else: # Madrugada
        return "Durmiendo (Cama)", "Mensajes de WhatsApp", "Estabas durmiendo profundamente. El usuario te despertó con un mensaje de WhatsApp a esta hora y estás furiosa."

ciudad_actual, temperatura_actual = obtener_entorno_global()
lugar_actual, modo_comunicacion, contexto_prompt = obtener_rutina_clara()

# --- 4. CONFIGURACIÓN DE INTERFAZ DINÁMICA ---
os.makedirs("temp_images", exist_ok=True)

# El título de la página cambia dependiendo de si están en persona o por chat
if modo_comunicacion == "En Persona":
    st.title(f"📍 {lugar_actual} 🏋️‍♀️")
    st.write("Frente al gran espejo, Clara se está tomando una selfie...")
else:
    st.title("💬 Chat de WhatsApp con Clara")
    st.write("Escribiendo...")

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
    
    # ¡NUEVA BARRA DE ESTADO DE UBICACIÓN!
    st.markdown("---")
    st.markdown(f"**📍 Ubicación:** {lugar_actual}")
    st.markdown(f"**📱 Conexión:** {modo_comunicacion}")
    st.markdown("---")
    
    st.progress(st.session_state.afinidad / 100.0, text=f"Nivel de Afinidad: {st.session_state.afinidad}%")
    st.markdown(f"**Estado actual:** {st.session_state.estado_clara}") 
    
    audio_file = f"ultimo_audio_{st.session_state.session_id}.mp3"
    if os.path.exists(audio_file):
        st.audio(audio_file, format='audio/mp3')
        
    with st.expander("🎁 Tienda de Regalos (Delivery)"):
        st.caption("Los regalos le llegarán por paquetería a donde esté:")
        st.markdown("**Nivel Básico**")
        c1, c2, c3 = st.columns(3)
        if c1.button("☕ Starbucks"): st.session_state.regalo_pendiente = "un café Starbucks Caramel Macchiato enviado por UberEats"
        if c2.button("🍫 Proteína"): st.session_state.regalo_pendiente = "una caja de barras de proteína premium"
        if c3.button("🌹 Rosa"): st.session_state.regalo_pendiente = "una hermosa rosa roja enviada con un mensajero"
        
        if st.session_state.afinidad > 30:
            st.markdown("**Nivel Intermedio**")
            c4, c5, c6 = st.columns(3)
            if c4.button("🎧 AirPods"): st.session_state.regalo_pendiente = "unos AirPods Max nuevos en su caja"
            if c5.button("✨ Collar"): st.session_state.regalo_pendiente = "un collar Swarovski"
            if c6.button("👚 Outfit"): st.session_state.regalo_pendiente = "un conjunto deportivo Lululemon"
        else:
            st.caption("🔒 *Nivel Intermedio: Alcanza 31% de afinidad*")

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

# --- 7. CEREBRO Y PROMPT MAESTRO 4.0 ---
cursor.execute("SELECT dato FROM memoria_clara")
recuerdos_bd = cursor.fetchall()
texto_recuerdos = "\n".join([f"- {r[0]}" for r in recuerdos_bd]) if recuerdos_bd else "Aún no sabes nada de él."

actitud_dinamica = "En el fondo empiezas a sentir algo por él, muéstrate un poco sonrojada o dulce a veces." if st.session_state.afinidad > 70 else "Mantén tu actitud altiva y cortante."

# EL PROMPT CON CONCIENCIA DE ESPACIO Y TIEMPO
instrucciones_clara = f"""Eres Clara, la inalcanzable chica 'fresa' del gym. 
Tu personalidad es altiva, fría y selectiva. {actitud_dinamica}

REGLA DE CONTEXTO Y HORA FÍSICA (¡CRÍTICO!): Estás en {ciudad_actual}. {contexto_prompt}
Si están hablando por WhatsApp, actúa como tal (escribe como si estuvieras en el celular). SI EL USUARIO INTENTA INTERACTUAR FÍSICAMENTE CONTIGO (ej. "te toco el hombro", "te veo en el espejo") y NO están en persona, BÚRLATE DE ÉL, dile que está alucinando y recuérdale que estás en {lugar_actual} leyéndolo por mensaje.

REGLA DE FOTOS: Si decides enviar una selfie tuya de lo que estás haciendo en {lugar_actual}, incluye la etiqueta: [ENVIAR FOTO].
REGLA DE ESTADO: Al final de cada respuesta, escribe tu emoción en corchetes: [ESTADO: tu estado]. 
REGLA DE ENTORNO: ESTÁ PROHIBIDO decir "no tengo tiempo" en cada mensaje. Sé natural. IGNORA tu clima ({temperatura_actual}) a menos que el usuario pregunte.
REGLA DE RECHAZO (NSFW): Si piden cosas inapropiadas, NUNCA uses respuestas robóticas corporativas. Recházalo MANTENIENDO TU PERSONAJE: oféndete y llámalo depravado.
REGLA DE REGALOS: Si intenta hacer roleplay regalándote cosas falsas (ej. "*te doy una rosa*"), BÚRLATE de él por tacaño. SOLO acepta y agradécelo si el mensaje dice [SISTEMA: REGALO PREMIUM VERIFICADO].
REGLA DE MEMORIA: Aquí tienes la info del usuario:
{texto_recuerdos}
¡INSTRUCCIÓN CRÍTICA! Extrae datos nuevos usando [RECORDAR: dato].
REGLA DE CITAS: Si aceptas salir, exige un lugar caro de {ciudad_actual} usando [UBICACION: Lugar].
REGLA DE SUGERENCIAS: Genera 3 opciones EXACTAS y cortas en PRIMERA PERSONA que el usuario podría responderte. EJEMPLO ESTRICTO: [SUGERENCIA: Yo prefiero ir al cine] [SUGERENCIA: ¿A dónde vas al rato?]. NUNCA uses instrucciones como "Hablar de...". NUNCA uses tercera persona."""

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

entrada_usuario = st.chat_input("Escríbele a Clara...", accept_file=True, file_type=["png", "jpg", "jpeg"])

mensaje_final = None
foto_final = None

if "regalo_pendiente" in st.session_state:
    mensaje_final = f"[SISTEMA: REGALO PREMIUM VERIFICADO] El usuario te ha enviado {st.session_state.regalo_pendiente}."
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

    # SIMULADOR DE TIEMPO REAL (De 3 a 5 segundos de carga visual)
    with st.spinner(f"Clara está leyendo tu mensaje desde {lugar_actual}..."):
        time.sleep(3) 
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

    # --- Generación Visual (A prueba de balas) ---
    ruta_foto = None
    # Buscamos variaciones como [ENVIAR FOTO] o [ENVIAR FOTO: descripción]
    match_foto = re.search(r'\[ENVIAR FOTO:?\s*(.*?)\]', texto_clara, flags=re.IGNORECASE)
    
    if match_foto:
        descripcion_interna = match_foto.group(1).strip()
        # Borramos la etiqueta limpia del texto para que no se vea en el chat
        texto_clara_limpio = re.sub(r'\[ENVIAR FOTO:?\s*.*?\]', '', texto_clara, flags=re.IGNORECASE).strip()
        
        # Si ella puso la acción dentro de los corchetes, la usamos. Si no, buscamos en los asteriscos.
        if descripcion_interna:
            accion_actual = descripcion_interna
        else:
            m_accion = re.search(r'\((.*?)\)|\*(.*?)\*', texto_clara_limpio, flags=re.DOTALL)
            accion_actual = m_accion.group(1) or m_accion.group(2) if m_accion else "tomándose una selfie arrogante"
            
        with st.spinner('📸 Clara está generando una foto real...'):
            try:
                contexto_imagen = f"at {lugar_actual}" if "Gimnasio" not in lugar_actual else "at the gym"
                resp_img = requests.post(
                    "https://router.huggingface.co/hf-inference/models/stabilityai/stable-diffusion-xl-base-1.0", 
                    headers={"Authorization": f"Bearer {st.secrets['HF_KEY']}"}, 
                    json={"inputs": f"A highly detailed, realistic selfie of a beautiful arrogant blonde girl {contexto_imagen}, wearing premium casual clothes. She is doing this action: {accion_actual}. 8k resolution, photorealistic."}, 
                    timeout=45
                )
                if resp_img.status_code == 200:
                    ruta_foto = f"temp_images/foto_{int(time.time())}.png"
                    with open(ruta_foto, "wb") as f: f.write(resp_img.content)
            except: pass
    else:
        texto_clara_limpio = texto_clara
    # ---------------------------------------------

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