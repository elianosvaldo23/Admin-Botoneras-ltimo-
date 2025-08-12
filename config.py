import logging
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuración del bot
BOT_TOKEN = "8063509725:AAHsa32julaJ4fst2OWhgj7lkL_HdA5ALN4"
ADMIN_ID = 1742433244

# MongoDB
MONGO_URI = "mongodb+srv://mundocrypto720:mundocrypto720@adminbotonera.8j9gzam.mongodb.net/adminbotonera?retryWrites=true&w=majority&appName=Adminbotonera"
DB_NAME = "adminbotonera"

# Mensajes por defecto
DEFAULT_WELCOME_MESSAGE = "¡Bienvenido/a {mention} al grupo {group_name}! 🎉\n\nEsperamos que disfrutes tu estancia aquí."

# Configuraciones globales
SETTINGS = {
    'date_format': '%d/%m/%Y %H:%M',
    'language': 'es',
    'max_buttons_per_welcome': 10,
    'max_message_length': 4096
}

# URL para keep-alive
KEEP_ALIVE_URL = "https://tu-app.onrender.com"