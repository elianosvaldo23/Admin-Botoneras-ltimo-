from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from config import ADMIN_ID, logger
from helpers import is_group_admin

class CommandHandlers:
    def __init__(self, db_manager):
        self.db = db_manager
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja el comando /start"""
        user_id = update.effective_user.id if update.effective_user else None
        chat_type = update.effective_chat.type if update.effective_chat else 'private'
        
        if chat_type == 'private':
            if user_id == ADMIN_ID:
                keyboard = [
                    [InlineKeyboardButton("🏠 Panel de Administración", callback_data="admin_panel")],
                    [InlineKeyboardButton("📊 Ver Grupos", callback_data="view_groups")],
                    [InlineKeyboardButton("🎉 Gestionar Bienvenidas", callback_data="manage_welcomes")],
                    [InlineKeyboardButton("ℹ️ Información del Bot", callback_data="bot_info")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(
                    "🎯 **Panel de Control - Bot Administrador**\n\n"
                    "¡Bienvenido al sistema de administración!\n\n"
                    "**Funciones disponibles:**\n"
                    "• Gestión completa de grupos\n"
                    "• Sistema de bienvenidas avanzado\n"
                    "• Configuración de botones y submenús\n"
                    "• Estadísticas en tiempo real\n"
                    "• Soporte para temas/hilos\n\n"
                    "Selecciona una opción para comenzar:",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text(
                    "🤖 **Bot Administrador de Grupos**\n\n"
                    "¡Hola! Soy un bot especializado en la administración de grupos.\n\n"
                    "**Características principales:**\n"
                    "• Sistema de bienvenidas personalizable\n"
                    "• Botones y submenús interactivos\n"
                    "• Soporte para imágenes y formatos\n"
                    "• Configuración por grupo\n\n"
                    "Para comenzar, añádeme a tu grupo y usa el comando `/admin`",
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            # En un grupo
            await update.message.reply_text(
                "🎉 **¡Bot Administrador activado!**\n\n"
                "Los administradores pueden configurarme usando `/admin`\n\n"
                "**Funciones disponibles:**\n"
                "• Mensajes de bienvenida personalizados\n"
                "• Botones y menús interactivos\n"
                "• Configuración avanzada por grupo",
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja el comando /admin para administradores de grupo"""
        user_id = update.effective_user.id if update.effective_user else None
        chat_id = update.effective_chat.id
        chat_type = update.effective_chat.type

        # Verificar que estamos en un grupo
        if chat_type == 'private':
            await update.message.reply_text(
                "❌ Este comando solo funciona en grupos.\n\n"
                "Si eres el administrador del bot, usa /start para acceder al panel principal."
            )
            return

        # Verificar permisos de administrador
        is_admin = await is_group_admin(context, chat_id, user_id)
        
        if not is_admin:
            await update.message.reply_text(
                "❌ **Acceso Denegado**\n\n"
                "Solo los administradores del grupo pueden usar este comando.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Asegurar que el grupo está registrado
        group_info = await self.db.get_group_info(chat_id)
        if not group_info:
            # Registrar grupo automáticamente
            try:
                chat = update.effective_chat
                member_count = await context.bot.get_chat_member_count(chat_id)
                is_forum = getattr(chat, "is_forum", False)
                
                await self.db.add_group(
                    chat_id, 
                    chat.title, 
                    chat.type, 
                    user_id,
                    update.effective_user.username, 
                    update.effective_user.first_name,
                    member_count, 
                    is_forum
                )
                logger.info(f"Grupo {chat_id} registrado automáticamente por comando /admin")
            except Exception as e:
                logger.error(f"Error registrando grupo {chat_id}: {e}")
        
        keyboard = [
            [InlineKeyboardButton("🎉 Configurar Bienvenida", callback_data=f"config_welcome_{chat_id}")],
            [InlineKeyboardButton("⚙️ Configuraciones del Grupo", callback_data=f"group_settings_{chat_id}")],
            [InlineKeyboardButton("📊 Estadísticas", callback_data=f"group_stats_{chat_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🔧 **Panel de Administración del Grupo**\n\n"
            f"**Grupo:** {update.effective_chat.title}\n"
            f"**ID:** `{chat_id}`\n\n"
            "Selecciona una opción para configurar:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

    async def set_welcome_topic(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Configura el tema/hilo para bienvenidas"""
        chat = update.effective_chat
        user_id = update.effective_user.id if update.effective_user else None

        if not chat or chat.type not in ("supergroup", "group"):
            await update.message.reply_text(
                "❌ Este comando solo funciona dentro de un grupo."
            )
            return

        is_admin = await is_group_admin(context, chat.id, user_id)
        if not is_admin:
            await update.message.reply_text(
                "❌ Solo los administradores pueden configurar el tema de bienvenida."
            )
            return

        is_forum = getattr(chat, "is_forum", False)
        if not is_forum:
            await update.message.reply_text(
                "ℹ️ **Información**\n\n"
                "Este grupo no tiene temas habilitados.\n"
                "No es necesario configurar un tema específico para las bienvenidas."
            )
            return

        thread_id = getattr(update.message, "message_thread_id", None)
        if thread_id is None:
            await update.message.reply_text(
                "📍 **Configurar Tema de Bienvenida**\n\n"
                "Para configurar el tema, ejecuta este comando **dentro del tema/hilo** "
                "donde quieres que se envíen las bienvenidas.\n\n"
                "1. Abre el tema deseado\n"
                "2. Ejecuta `/setwelcometopic` dentro del tema\n"
                "3. ¡Listo!"
            )
            return

        try:
            await self.db.set_group_welcome_thread(chat.id, thread_id)
            await update.message.reply_text(
                f"✅ **Tema Configurado**\n\n"
                f"Las bienvenidas se enviarán en este tema.\n"
                f"**Thread ID:** `{thread_id}`\n\n"
                f"Para deshacer esta configuración, usa `/clearwelcometopic`",
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"Tema de bienvenida configurado para grupo {chat.id}: thread_id={thread_id}")
        except Exception as e:
            logger.error(f"Error configurando tema para grupo {chat.id}: {e}")
            await update.message.reply_text(
                "❌ Error al configurar el tema. Inténtalo de nuevo."
            )

    async def clear_welcome_topic(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Limpia la configuración del tema de bienvenida"""
        chat = update.effective_chat
        user_id = update.effective_user.id if update.effective_user else None

        if not chat or chat.type not in ("supergroup", "group"):
            await update.message.reply_text(
                "❌ Este comando solo funciona dentro de un grupo."
            )
            return

        is_admin = await is_group_admin(context, chat.id, user_id)
        if not is_admin:
            await update.message.reply_text(
                "❌ Solo los administradores pueden usar este comando."
            )
            return

        try:
            await self.db.clear_group_welcome_thread(chat.id)
            await update.message.reply_text(
                "✅ **Configuración Limpiada**\n\n"
                "Se ha eliminado la configuración del tema de bienvenida.\n"
                "Las bienvenidas se enviarán en el chat principal del grupo.",
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info(f"Configuración de tema limpiada para grupo {chat.id}")
        except Exception as e:
            logger.error(f"Error limpiando tema para grupo {chat.id}: {e}")
            await update.message.reply_text(
                "❌ Error al limpiar la configuración. Inténtalo de nuevo."
            )
