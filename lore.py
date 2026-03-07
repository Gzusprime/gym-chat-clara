import streamlit as st
import requests
import pytz
from datetime import datetime

# --- DICCIONARIO DEL MULTIVERSO ---
PERSONAJES = {
    "Clara": {
        "icono": "clara.png", "emoji": "💅", "dificultad": "Difícil (Fresa/Altiva)",
        "voz": "es-MX-DaliaNeural",
        "descripcion": "La inalcanzable chica del gym. Superficial, le gusta el lujo y se hace la difícil.",
        "prompt_base": "Eres Clara, la inalcanzable chica 'fresa' del gym. Tu personalidad es altiva, fría y selectiva.",
        "img_prompt": "beautiful arrogant blonde girl, premium casual clothes, fitness model",
        "multiplicador_ganancia": 0.5, "multiplicador_perdida": 0.3,
        "tienda": {
            "basico": [("☕ Starbucks", "un café Starbucks", 50), ("🍫 Proteína", "una barra de proteína", 50), ("🌹 Rosa", "una rosa roja", 50)],
            "intermedio": [("🎧 AirPods", "unos AirPods Max", 300), ("✨ Collar", "un collar Swarovski", 300), ("👚 Outfit", "un outfit Lululemon", 300)],
            "premium": [("👜 Bolso", "un bolso Louis Vuitton", 1000), ("📱 iPhone", "un iPhone 15 Pro Max", 1000), ("💍 Anillo", "un anillo con diamante", 1000)]
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
            "basico": [("☕ Café Negro", "un café americano sin azúcar", 50), ("🍪 Galleta", "una galleta de chispas", 50), ("📖 Libro", "un libro de poesía oscura", 50)],
            "intermedio": [("🎧 Audífonos", "unos audífonos vintage", 300), ("🦇 Gargantilla", "una gargantilla con un murciélago", 300), ("🎸 Vinilo", "un disco de vinilo de rock gótico", 300)],
            "premium": [("👢 Botas", "unas botas de plataforma Demonias", 1000), ("🎟️ Concierto", "boletos VIP para un concierto de rock", 1000), ("🏍️ Chamarra", "una chamarra de cuero auténtico", 1000)]
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
            "basico": [("🧋 Boba Tea", "un té de perlas de taro", 50), ("🌻 Girasol", "un lindo girasol", 50), ("🍫 Chocolate", "un chocolate artesanal", 50)],
            "intermedio": [("🧸 Peluche", "un osito de peluche gigante", 300), ("📓 Libreta", "una libreta de apuntes bonita", 300), ("💐 Ramo", "un ramo de flores silvestres", 300)],
            "premium": [("💻 Laptop", "una laptop para sus tareas de la UPA", 1000), ("🧥 Sudadera", "una sudadera calientita de su banda favorita", 1000), ("💍 Promesa", "un anillo de promesa de plata", 1000)]
        }
    }
}

# --- RADARES Y RELOJES ---
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
        if 6 <= hora < 10: return "En su casa", "WhatsApp", "Tomando desayuno fit.", "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?q=80&w=1475"
        elif 10 <= hora < 14: return "De compras / Spa", "WhatsApp", "Consintiéndose.", "https://images.unsplash.com/photo-1540555700478-4be289fbecef?q=80&w=1470"
        elif 14 <= hora < 17: return "Restaurante", "WhatsApp", "Comiendo ensalada.", "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?q=80&w=1470"
        elif 17 <= hora < 20: return "Gimnasio", "En Persona", "Entrenando frente al espejo. Estás ahí.", "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?q=80&w=1470"
        elif 20 <= hora < 23: return "En su casa", "WhatsApp", "Haciendo skincare.", "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?q=80&w=1475"
        else: return "Cama", "WhatsApp", "Durmiendo furiosa.", "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?q=80&w=1470"
        
    elif personaje == "Raven":
        if 6 <= hora < 14: return "Cama", "WhatsApp", "Durmiendo hasta tarde.", "https://images.unsplash.com/photo-1555041469-a586c61ea9bc?q=80&w=1470"
        elif 14 <= hora < 21: return "Cafetería", "En Persona", "Trabajando de barista. Estás pidiendo café.", "https://images.unsplash.com/photo-1554118811-1e0d58224f24?q=80&w=1447"
        elif 21 <= hora < 24: return "En un bar/toque", "WhatsApp", "Escuchando música.", "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?q=80&w=1374"
        else: return "Madrugada oscura", "WhatsApp", "Viendo cosas raras.", "https://images.unsplash.com/photo-1559588501-8b3684a1e941?q=80&w=1470"
        
    elif personaje == "Valeria":
        if 7 <= hora < 15: return "UPA (Universidad)", "En Persona", "En el campus de la UPA. Estás ahí.", "https://images.unsplash.com/photo-1541339907198-e08756dedf3f?q=80&w=1470"
        elif 15 <= hora < 18: return "Biblioteca", "WhatsApp", "Haciendo tareas de ingeniería.", "https://images.unsplash.com/photo-1568667256549-094345857637?q=80&w=1415"
        elif 18 <= hora < 23: return "Casa", "WhatsApp", "Relajándose y viendo series.", "https://images.unsplash.com/photo-1513694203232-719a280e022f?q=80&w=1469"
        else: return "Cama", "WhatsApp", "Durmiendo dulcemente.", "https://images.unsplash.com/photo-1505693314120-0d443867891c?q=80&w=1511"