import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest

from config import ADMIN_ID, logger
from helpers import format_welcome_message


class MessageHandlers:
    def __init__(self, db_manager):
        self.db = db_manager
        self.waiting_for_input = {}

    def _build_keyboard_from_node(self, node: dict):
        """Construye el teclado inline desde un nodo"""
        rows = []
        try:
            buttons = node.get('buttons', [])
            if isinstance(buttons, str):
                buttons = json.loads(buttons)
        except Exception:
            buttons = []
            
        for row in buttons:
            rb = []
            for b in row:
                if b.get('type') == 'url' and b.get('url'):
                    rb.append(InlineKeyboardButton(b.get('text', 'Abrir'), url=b['url']))
                elif b.get('type') == 'node' and b.get('node_id'):
                    rb.append(InlineKeyboardButton(b.get('text', 'Ver'), callback_data=f"wb_{b['node_id']}"))
            if rb:
                rows.append(rb)
                
        # Botones de navegación
        if node.get('parent_id'):
            rows.append([
                InlineKeyboardButton("◀️ Atrás", callback_data=f"wb_{node['parent_id']}"),
                InlineKeyboardButton("🏠 Inicio", callback_data=f"wb_home_{node['chat_id']}")
            ])
        elif rows:
            rows.append([InlineKeyboardButton("🏠 Inicio", callback_data=f"wb_home_{node['chat_id']}")])
            
        return InlineKeyboardMarkup(rows) if rows else None

    def _normalize_parse_mode(self, pm: str | None) -> str:
        """Normaliza el modo de parseo"""
        if not pm:
            return "HTML"
        if pm.lower().startswith("markdown"):
            return "MarkdownV2"
        return "HTML" if pm.upper() == "HTML" else pm

    async def handle_new_chat_member(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja cuando nuevos miembros se unen al grupo"""
        logger.info("🔄 Procesando nuevos miembros del chat...")
        
        if not update.message or not update.message.new_chat_members:
            logger.warning("⚠️ No hay nuevos miembros en el mensaje")
            return
            
        # Verificar si el bot fue añadido
        bot_added = False
        for member in update.message.new_chat_members:
            if member.id == context.bot.id:
                await self.bot_added_to_group(update, context)
                bot_added = True
                break

        # Si el bot fue añadido, no procesar otros usuarios en el mismo evento
        if bot_added:
            logger.info("🤖 Bot añadido al grupo, omitiendo bienvenidas de otros usuarios")
            return

        # Procesar bienvenidas para usuarios reales
        await self.send_welcome_message(update, context)

    async def bot_added_to_group(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja cuando el bot es añadido a un grupo"""
        chat = update.effective_chat
        user = update.effective_user

        if not chat:
            logger.error("❌ No se pudo obtener información del chat")
            return

        logger.info(f"🤖 Bot añadido al grupo: {chat.title} (ID: {chat.id})")

        try:
            # Obtener información en vivo del chat
            chat_live = await context.bot.get_chat(chat.id)
            member_count = await context.bot.get_chat_member_count(chat.id)
            is_forum = getattr(chat_live, "is_forum", False)
            title = chat_live.title or chat.title
            
            logger.info(f"📊 Miembros: {member_count}, Foro: {is_forum}")
        except Exception as e:
            logger.warning(f"⚠️ Error obteniendo info del chat: {e}")
            is_forum = getattr(chat, "is_forum", False)
            title = chat.title
            try:
                member_count = await context.bot.get_chat_member_count(chat.id)
            except:
                member_count = 0

        # Registrar grupo en la base de datos
        try:
            await self.db.add_group(
                chat.id, 
                title, 
                chat.type, 
                user.id if user else None,
                (user.username if user else None), 
                (f"{user.first_name} {user.last_name or ''}".strip() if user else "Desconocido"),
                member_count, 
                is_forum
            )
            logger.info(f"✅ Grupo {chat.id} registrado en la base de datos")
        except Exception as e:
            logger.error(f"❌ Error registrando grupo {chat.id}: {e}")

        # Notificar al administrador
        keyboard = [[InlineKeyboardButton("⚙️ Configurar Grupo", callback_data=f"config_group_{chat.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        notification_text = (
            f"🆕 **Nuevo Grupo Añadido**\n\n"
            f"📍 **Grupo:** {title}\n"
            f"🆔 **ID:** `{chat.id}`\n"
            f"👤 **Añadido por:** {user.first_name if user else 'Desconocido'}\n"
            f"📱 **Username:** @{user.username or 'Sin username' if user else '-'}\n"
            f"👥 **Miembros:** {member_count}\n"
            f"💬 **Temas habilitados:** {'✅ Sí' if is_forum else '❌ No'}\n"
            f"📅 **Fecha:** {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=notification_text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info("📬 Notificación enviada al administrador")
        except Exception as e:
            logger.error(f"❌ Error enviando notificación al admin: {e}")

        # Mensaje de bienvenida del bot en el grupo
        try:
            welcome_text = (
                "🎉 **¡Hola! Soy tu nuevo Bot Administrador**\n\n"
                "**¿Qué puedo hacer?**\n"
                "• Mensajes de bienvenida personalizados\n"
                "• Botones y menús interactivos\n"
                "• Configuración avanzada por grupo\n"
                "• Soporte para temas/hilos\n\n"
                "**Para comenzar:**\n"
                "Los administradores pueden usar `/admin` para configurarme.\n\n"
                "¡Gracias por añadirme al grupo! 🤖"
            )
            
            await update.message.reply_text(
                welcome_text,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info("✅ Mensaje de bienvenida del bot enviado")
        except Exception as e:
            logger.error(f"❌ Error enviando mensaje de bienvenida del bot: {e}")

    async def send_welcome_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Envía mensajes de bienvenida a nuevos miembros"""
        if not update.message or not update.message.new_chat_members:
            return

        chat_id = update.effective_chat.id
        chat_title = update.effective_chat.title or "el grupo"

        logger.info(f"🎉 Procesando bienvenidas para grupo {chat_id}")

        # Verificar configuración de bienvenida
        welcome_cfg = await self.db.get_welcome_settings(chat_id)
        if not welcome_cfg or not welcome_cfg[1]:
            logger.info(f"⏸️ Bienvenida desactivada para grupo {chat_id}")
            return

        # Obtener modo de bienvenida
        welcome_mode = await self.db.get_welcome_mode(chat_id)
        logger.info(f"🔧 Modo de bienvenida para grupo {chat_id}: {welcome_mode}")

        # Obtener nodo raíz (mensaje de bienvenida)
        await self.db.ensure_root_node(chat_id)
        root = await self.db.get_root_node(chat_id)
        if not root:
            logger.error(f"❌ No se pudo obtener nodo raíz para grupo {chat_id}")
            return

        parse_mode = self._normalize_parse_mode(root.get("parse_mode") or "HTML")

        # Determinar hilo/tema destino
        configured_thread = await self.db.get_group_welcome_thread(chat_id)
        event_thread = getattr(update.message, "message_thread_id", None)
        thread_id = configured_thread if configured_thread is not None else event_thread

        if thread_id:
            logger.info(f"📍 Enviando bienvenidas al hilo {thread_id}")

        # Procesar cada nuevo miembro
        for new_member in update.message.new_chat_members:
            if new_member.id == context.bot.id:
                continue  # Ignorar el bot

            logger.info(f"👤 Procesando bienvenida para {new_member.first_name} (ID: {new_member.id})")

            # Verificar modo de bienvenida
            if welcome_mode == "new_only":
                is_new = await self.db.is_new_member(chat_id, new_member.id)
                if not is_new:
                    logger.info(f"👤 Usuario {new_member.id} ya conocido, omitiendo bienvenida")
                    continue
                await self.db.mark_member_as_seen(chat_id, new_member.id)
            elif welcome_mode == "always":
                await self.db.mark_member_as_seen(chat_id, new_member.id)

            # Formatear mensaje de bienvenida
            msg_text = format_welcome_message(
                root.get("text") or "",
                new_member,
                chat_title,
                parse_mode=parse_mode
            )
            reply_kb = self._build_keyboard_from_node(root)

            # Enviar mensaje de bienvenida
            try:
                if root.get("image_url"):
                    logger.info(f"📷 Enviando bienvenida con imagen")
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=root["image_url"],
                        caption=msg_text,
                        reply_markup=reply_kb,
                        parse_mode=parse_mode,
                        message_thread_id=thread_id
                    )
                else:
                    logger.info(f"📝 Enviando bienvenida de texto")
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=msg_text,
                        reply_markup=reply_kb,
                        parse_mode=parse_mode,
                        message_thread_id=thread_id
                    )
                
                # Actualizar estadísticas
                await self.db.update_welcome_stats(chat_id)
                logger.info(f"✅ Bienvenida enviada a {new_member.first_name}")

            except BadRequest as e:
                error_msg = str(e).lower()
                if "can't parse entities" in error_msg:
                    logger.warning(f"⚠️ Error de parseo, reenviando sin formato: {e}")
                    # Reenviar sin formato
                    safe_text = format_welcome_message(
                        root.get("text") or "",
                        new_member,
                        chat_title,
                        parse_mode=None
                    )
                    try:
                        if root.get("image_url"):
                            await context.bot.send_photo(
                                chat_id=chat_id,
                                photo=root["image_url"],
                                caption=safe_text,
                                reply_markup=reply_kb,
                                parse_mode=None,
                                message_thread_id=thread_id
                            )
                        else:
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=safe_text,
                                reply_markup=reply_kb,
                                parse_mode=None,
                                message_thread_id=thread_id
                            )
                        await self.db.update_welcome_stats(chat_id)
                        logger.info(f"✅ Bienvenida enviada (sin formato) a {new_member.first_name}")
                    except Exception as e2:
                        logger.error(f"❌ Error enviando bienvenida sin formato: {e2}")
                else:
                    logger.error(f"❌ Error BadRequest enviando bienvenida: {e}")
            except Exception as e:
                logger.error(f"❌ Error inesperado enviando bienvenida: {e}")

    async def handle_text_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja entrada de texto para configuraciones"""
        user_id = update.effective_user.id if update.effective_user else None
        if not user_id or user_id not in self.waiting_for_input:
            return

        data = self.waiting_for_input[user_id]
        action = data['action']
        text_input = update.message.text.strip()

        logger.info(f"📝 Procesando entrada de texto para acción: {action}")

        try:
            if action == "welcome_message":
                await self._handle_welcome_message_input(update, data, text_input)
            elif action == "button_text" and data.get('button_type') == 'url':
                await self._handle_button_text_input(update, data, text_input)
            elif action == "button_url":
                await self._handle_button_url_input(update, data, text_input)
            elif action == "button_sub_text":
                await self._handle_submenu_button_text_input(update, data, text_input)
            elif action == "child_node_text":
                await self._handle_child_node_text_input(update, data, text_input)
            elif action == "node_image":
                await self._handle_node_image_text_input(update, data, text_input)
            elif action == "node_rename":
                await self._handle_node_rename_input(update, data, text_input)
        except Exception as e:
            logger.error(f"❌ Error procesando entrada de texto: {e}")
            await update.message.reply_text("❌ Error procesando la entrada. Inténtalo de nuevo.")
            if user_id in self.waiting_for_input:
                del self.waiting_for_input[user_id]

    async def _handle_welcome_message_input(self, update, data, text_input):
        """Maneja entrada del mensaje de bienvenida"""
        chat_id = data['chat_id']
        await self.db.update_welcome_message(chat_id, text_input)
        root_id = await self.db.ensure_root_node(chat_id)
        await self.db.update_node_text(root_id, text_input)
        
        keyboard = [
            [InlineKeyboardButton("➕ Añadir Botón URL", callback_data=f"node_add_url_{root_id}")],
            [InlineKeyboardButton("➕ Añadir Submenú", callback_data=f"node_add_sub_{root_id}")],
            [InlineKeyboardButton("✅ Finalizar", callback_data=f"config_welcome_{chat_id}")]
        ]
        
        await update.message.reply_text(
            "✅ **Mensaje de bienvenida actualizado**\n\n"
            "¿Deseas añadir botones interactivos?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        del self.waiting_for_input[update.effective_user.id]

    async def _handle_button_text_input(self, update, data, text_input):
        """Maneja entrada del texto del botón URL"""
        self.waiting_for_input[update.effective_user.id]['button_text'] = text_input
        self.waiting_for_input[update.effective_user.id]['action'] = 'button_url'
        await update.message.reply_text(
            "🔗 **Configurar URL del Botón**\n\n"
            "Ahora envía la URL completa (debe comenzar con http:// o https://)\n\n"
            "Escribe 'cancelar' para cancelar la operación."
        )

    async def _handle_button_url_input(self, update, data, text_input):
        """Maneja entrada de la URL del botón"""
        if text_input.lower() in ['cancelar', 'cancel']:
            await update.message.reply_text("❌ Operación cancelada.")
            del self.waiting_for_input[update.effective_user.id]
            return

        node_id = data['node_id']
        button_text = data.get('button_text', 'Abrir')
        
        # Validar URL básicamente
        if not text_input.startswith(('http://', 'https://')):
            await update.message.reply_text(
                "⚠️ **URL inválida**\n\n"
                "La URL debe comenzar con http:// o https://\n"
                "Inténtalo de nuevo o escribe 'cancelar'."
            )
            return

        # Añadir botón
        rows = await self.db.get_node_buttons(node_id)
        rows.append([{"text": button_text, "type": "url", "url": text_input}])
        await self.db.set_node_buttons(node_id, rows)
        
        await update.message.reply_text(
            f"✅ **Botón URL añadido**\n\n"
            f"**Texto:** {button_text}\n"
            f"**URL:** {text_input}"
        )
        del self.waiting_for_input[update.effective_user.id]

    async def _handle_submenu_button_text_input(self, update, data, text_input):
        """Maneja entrada del texto del botón de submenú"""
        self.waiting_for_input[update.effective_user.id]['submenu_button_text'] = text_input
        self.waiting_for_input[update.effective_user.id]['action'] = 'child_node_text'
        await update.message.reply_text(
            "📝 **Contenido del Submenú**\n\n"
            "Ahora envía el texto que se mostrará cuando se abra este submenú.\n\n"
            "Puedes usar las mismas variables que en el mensaje de bienvenida:\n"
            "• `{mention}` - menciona al usuario\n"
            "• `{name}` - nombre del usuario\n"
            "• `{username}` - @usuario\n"
            "• `{group_name}` - nombre del grupo",
            parse_mode=ParseMode.MARKDOWN
        )

    async def _handle_child_node_text_input(self, update, data, text_input):
        """Maneja entrada del texto del nodo hijo"""
        parent_node_id = data['node_id']
        btn_text = data.get('submenu_button_text', 'Ver más')
        
        parent_node = await self.db.get_node(parent_node_id)
        chat_id = parent_node['chat_id']
        
        # Crear nodo hijo
        child_id = await self.db.add_child_node(
            chat_id, 
            parent_node_id, 
            text_input, 
            parent_node.get('parse_mode') or 'HTML'
        )

        # Añadir botón al padre
        rows = await self.db.get_node_buttons(parent_node_id)
        rows.append([{"text": btn_text, "type": "node", "node_id": child_id}])
        await self.db.set_node_buttons(parent_node_id, rows)

        keyboard = [
            [InlineKeyboardButton("➕ Añadir Botón URL", callback_data=f"node_add_url_{child_id}")],
            [InlineKeyboardButton("➕ Añadir Submenú", callback_data=f"node_add_sub_{child_id}")],
            [InlineKeyboardButton("⚙️ Gestionar Submenú", callback_data=f"node_mgr_{chat_id}_{child_id}")],
            [InlineKeyboardButton("✅ Finalizar", callback_data=f"node_mgr_{chat_id}_{parent_node_id}")]
        ]

        await update.message.reply_text(
            f"✅ **Submenú creado exitosamente**\n\n"
            f"**Botón:** {btn_text}\n"
            f"**Contenido:** {text_input[:100]}{'...' if len(text_input) > 100 else ''}\n\n"
            "¿Deseas configurar este submenú?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        del self.waiting_for_input[update.effective_user.id]

    async def _handle_node_image_text_input(self, update, data, text_input):
        """Maneja entrada de URL de imagen para nodo"""
        node_id = data['node_id']
        
        if text_input.lower() in ['remove', 'quitar', 'eliminar']:
            await self.db.update_node_image(node_id, None)
            await update.message.reply_text("✅ **Imagen eliminada** del nodo.")
        else:
            await self.db.update_node_image(node_id, text_input)
            await update.message.reply_text("✅ **Imagen actualizada** para el nodo.")
        
        del self.waiting_for_input[update.effective_user.id]

    async def _handle_node_rename_input(self, update, data, text_input):
        """Maneja entrada de renombrado de nodo"""
        node_id = data['node_id']
        await self.db.update_node_text(node_id, text_input)
        await update.message.reply_text(
            f"✅ **Texto del nodo actualizado**\n\n"
            f"**Nuevo contenido:** {text_input[:200]}{'...' if len(text_input) > 200 else ''}"
        )
        del self.waiting_for_input[update.effective_user.id]

    async def handle_photo_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Maneja entrada de fotos para configuración de imágenes"""
        user_id = update.effective_user.id if update.effective_user else None
        if not user_id or user_id not in self.waiting_for_input:
            return
            
        data = self.waiting_for_input[user_id]
        if data.get('action') != 'node_image':
            return

        node_id = data['node_id']
        
        try:
            # Obtener el file_id de la foto más grande
            file_id = update.message.photo[-1].file_id
            await self.db.update_node_image(node_id, file_id)
            
            await update.message.reply_text(
                "✅ **Imagen actualizada**\n\n"
                "La imagen se ha guardado correctamente y se mostrará en el nodo."
            )
            logger.info(f"📷 Imagen actualizada para nodo {node_id}")
            
        except Exception as e:
            logger.error(f"❌ Error guardando imagen de nodo: {e}")
            await update.message.reply_text(
                "❌ **Error guardando imagen**\n\n"
                "No se pudo guardar la imagen. Inténtalo de nuevo."
            )
        finally:
            del self.waiting_for_input[user_id]
