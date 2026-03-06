import requests
import urllib.parse
import streamlit as st
import sqlite3
import re
import os
import base64
import time
from google import genai
from google.genai import types
from groq import Groq
import edge_tts
import asyncio

# --- 1. SENSOR DE CLIMA Y ESTADOS INICIALES ---
@st.cache_data(ttl=3600)
def obtener_clima():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=21.8823&longitude=-102.2826&current_weather=true"
        respuesta = requests.get(url, timeout=5).json()
        return f"{respuesta['current_weather']['temperature']}°C"
    except Exception as e:
        return "25.0°C"

temperatura_actual = obtener_clima()

# --- 2. CONFIGURACIÓN DE CARPETAS Y PROMPTS ---
os.makedirs("temp_images", exist_ok=True)
PROMPT_BASE_IMAGEN = "Fotografía realista de una chica rubia platino en un gimnasio moderno, usando ropa deportiva casual premium. Alta calidad, retrato."

# --- 3. CONFIGURACIÓN VISUAL DE LA PÁGINA ---
st.set_page_config(page_title="Gym Chat - Clara", page_icon="💅")
st.title("Gimnasio - Zona de Pesas Libres 🏋️‍♀️")
st.write("Frente al gran espejo, Clara se está tomando una selfie...")

# --- 4. BASE DE DATOS SQLITE ---
conexion = sqlite3.connect("memoria_clara.db", check_same_thread=False)
cursor = conexion.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS mensajes (id INTEGER PRIMARY KEY AUTOINCREMENT, rol TEXT NOT NULL, contenido TEXT NOT NULL, ruta_imagen TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS memoria_clara (id INTEGER PRIMARY KEY AUTOINCREMENT, dato TEXT NOT NULL)''')

# Tabla para guardar sus sentimientos permanentemente
cursor.execute('''CREATE TABLE IF NOT EXISTS estado_personaje (id INTEGER PRIMARY KEY, afinidad INTEGER, emocion TEXT)''')

# Revisamos si ya tiene sentimientos guardados. Si no, le insertamos los de fábrica.
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

# Inicializamos la memoria RAM leyendo lo que sacamos del Disco Duro
if "estado_clara" not in st.session_state:
    st.session_state.estado_clara = emocion_inicial
if "afinidad" not in st.session_state:
    st.session_state.afinidad = afinidad_inicial

conexion.commit()

# --- 5. PANEL LATERAL (SIDEBAR MULTIMEDIA) ---
with st.sidebar:
    st.image("clara.png", caption="Clara 💅") 
    st.markdown("### Ficha del Personaje")
    st.markdown("**Personalidad:** Altiva, fría, fresa.")
    
    # BARRA DE AFINIDAD (GAMIFICACIÓN)
    st.progress(st.session_state.afinidad / 100.0, text=f"Nivel de Afinidad: {st.session_state.afinidad}%")
    st.markdown(f"**Estado actual:** {st.session_state.estado_clara}") 
    
    if os.path.exists("ultimo_audio.mp3"):
        st.audio("ultimo_audio.mp3", format='audio/mp3')
        
    # SISTEMA DE REGALOS (Microtransacciones)
    with st.expander("🎁 Enviar un Detalle"):
        st.caption("Intenta comprar su atención:")
        c1, c2, c3 = st.columns(3)
        if c1.button("☕ Latte"): st.session_state.regalo_pendiente = "un Matcha Latte helado"
        if c2.button("🌹 Rosa"): st.session_state.regalo_pendiente = "una rosa roja"
        if c3.button("🎧 Audífonos"): st.session_state.regalo_pendiente = "unos AirPods Max nuevos"
        
    # El Instagram Interactivo
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
            
    with st.expander("🛠️ Debug: Memoria SQLite"):
        cursor.execute("SELECT dato FROM memoria_clara")
        datos = cursor.fetchall()
        if datos:
            for d in datos: st.code(d[0])
        else:
            st.caption("Vacío.")

# --- 6. INICIALIZAR LA IA Y EL CEREBRO ---
cursor.execute("SELECT dato FROM memoria_clara")
recuerdos_bd = cursor.fetchall()
texto_recuerdos = "\n".join([f"- {r[0]}" for r in recuerdos_bd]) if recuerdos_bd else "Aún no sabes nada de él."

# Lógica dinámica: Si la afinidad es alta, se vuelve más dócil
actitud_dinamica = "En el fondo empiezas a sentir algo por él, muéstrate un poco sonrojada o dulce a veces." if st.session_state.afinidad > 70 else "Mantén tu actitud altiva y cortante."

# PROMPT MAESTRO ACTUALIZADO (Cura del Elefante Rosa)
instrucciones_clara = f"""Eres Clara, la inalcanzable chica 'fresa' del gym. 
Tu personalidad es altiva, fría y selectiva. {actitud_dinamica}

REGLA DE FOTOS: Si decides enviar una foto tuya, incluye la etiqueta: [ENVIAR FOTO].
REGLA DE ESTADO: Al final de cada respuesta, escribe tu emoción en corchetes: [ESTADO: tu estado]. 
REGLA DE ENTORNO Y EXCUSAS: Estás entrenando. ESTÁ TOTALMENTE PROHIBIDO decir "no tengo tiempo" o "estoy ocupada" en cada mensaje. Sé más natural y creativa. El clima actual es {temperatura_actual}, pero IGNORA este dato por completo y NO lo menciones NUNCA a menos que el usuario te pregunte explícitamente por el calor o el clima.
REGLA DE MEMORIA: Aquí tienes la información confirmada del usuario:
{texto_recuerdos}
¡INSTRUCCIÓN CRÍTICA! Si el usuario menciona un dato nuevo sobre él, extraelo y agrega la etiqueta [RECORDAR: dato].
REGLA DE CITAS: Si el usuario te invita a salir y aceptas, exige ir a un lugar caro de Aguascalientes (ej. Punto 45, San Telmo) usando [UBICACION: Nombre del lugar].
REGLA DE SUGERENCIAS: Genera 3 opciones de lo que el usuario podría contestarte, usando [SUGERENCIA: opcion 1] [SUGERENCIA: opcion 2] [SUGERENCIA: opcion 3]."""

# --- INYECCIÓN SEGURA DE LLAVES (st.secrets) ---
if "client" not in st.session_state: st.session_state.client = genai.Client(api_key=st.secrets["GEMINI_KEY"])
if "client_groq" not in st.session_state: st.session_state.client_groq = Groq(api_key=st.secrets["GROQ_KEY"])
    
# --- 7. DIBUJAR EL CHAT ---
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

# --- 8. ZONA DE CONTROLES E INPUTS ---
if "sugerencias_actuales" in st.session_state and st.session_state.sugerencias_actuales:
    st.write("💡 *Respuestas rápidas:*")
    cols = st.columns(len(st.session_state.sugerencias_actuales))
    for i, opcion in enumerate(st.session_state.sugerencias_actuales):
        if cols[i].button(opcion, use_container_width=True):
            st.session_state.mensaje_boton = opcion
            st.rerun()

# 1. El Micrófono 
audio_usuario = None
with st.popover("🎙️ Audio"):
    audio_usuario_temp = st.audio_input("Grabar nota de voz")
    if audio_usuario_temp:
        audio_usuario = audio_usuario_temp

# 2. La Barra de Texto y Fotos 
entrada_usuario = st.chat_input("Escríbele algo a Clara...", accept_file=True, file_type=["png", "jpg", "jpeg"])

# --- ENRUTADOR PRINCIPAL ---
mensaje_final = None
foto_final = None

if "regalo_pendiente" in st.session_state:
    mensaje_final = f"*(Le entrego sorpresivamente {st.session_state.regalo_pendiente} para llamar su atención)*"
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

# --- 9. PROCESAMIENTO DEL MENSAJE Y LLAMADAS A LA IA ---
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

    # Llamada a Groq Llama 3.3
    respuesta = st.session_state.client_groq.chat.completions.create(messages=mensajes_api, model="llama-3.3-70b-versatile", temperature=0.6)
    texto_clara = respuesta.choices[0].message.content
    st.session_state.memoria_groq.append({"role": "assistant", "content": texto_clara})

    # --- EXTRACCIÓN MAGICA DE ETIQUETAS Y GAMIFICACIÓN ---
    match_estado = re.search(r'\[ESTADO:\s*(.*?)\]', texto_clara, flags=re.IGNORECASE)
    if match_estado:
        nuevo_estado = match_estado.group(1).strip()
        st.session_state.estado_clara = nuevo_estado
        texto_clara = re.sub(r'\[ESTADO:\s*.*?\]', '', texto_clara, flags=re.IGNORECASE).strip()
        
        # LÓGICA DE AFINIDAD
        estado_lower = nuevo_estado.lower()
        positivos = ["divertida", "feliz", "halagada", "sonrojada", "interesada", "impresionada", "curiosa", "animada", "sorprendida"]
        negativos = ["irritada", "aburrida", "ofendida", "asco", "indiferente", "molesta", "harta", "desinteresada", "enojada"]
        
        if any(p in estado_lower for p in positivos):
            st.session_state.afinidad = min(100, st.session_state.afinidad + 5)
        elif any(n in estado_lower for n in negativos):
            st.session_state.afinidad = max(0, st.session_state.afinidad - 2)

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
        texto_clara += f"\n\n🗺️ **Exigió verte en:** [{lugar}](https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(f'{lugar} Aguascalientes')})"

    sugerencias_extraidas = re.findall(r'\[SUGERENCIA:\s*(.*?)\]', texto_clara, flags=re.IGNORECASE)
    st.session_state.sugerencias_actuales = sugerencias_extraidas if sugerencias_extraidas else []
    texto_clara = re.sub(r'\[SUGERENCIA:\s*.*?\]', '', texto_clara, flags=re.IGNORECASE).strip()

    # Generación Visual (Inyección segura de Hugging Face)
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

    # Generación de Voz
    texto_hablado = re.sub(r'\*.*?\*|\(.*?\)', '', texto_clara_limpio).strip()
    if texto_hablado:
        try:
            async def generar_voz():
                await edge_tts.Communicate(texto_hablado, "es-MX-DaliaNeural").save("ultimo_audio.mp3")
            asyncio.run(generar_voz())
        except: pass

    conexion.commit()
    st.rerun()

conexion.close()