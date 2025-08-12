import json
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest

from helpers import check_admin_permissions, truncate_text, format_date, format_welcome_message
from config import logger


class CallbackHandlers:
    def __init__(self, db_manager, message_handler):
        self.db = db_manager
        self.message_handler = message_handler

    def _is_public_callback(self, data: str) -> bool:
        """Verifica si es un callback público (navegación de bienvenida)"""
        return data.startswith("wb_") or data.startswith("wb_home_")

    async def safe_edit_message_text(self, query, text: str, reply_markup=None, parse_mode=None):
        """Edita mensaje de texto de forma segura"""
        try:
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except BadRequest as e:
            msg = str(e).lower()
            if "message is not modified" in msg:
                try:
                    await query.answer("✅ Contenido ya actualizado")
                except:
                    pass
            elif "can't parse entities" in msg:
                try:
                    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=None)
                    return
                except:
                    pass
                raise
            else:
                raise

    async def safe_edit_message_caption(self, query, caption: str, reply_markup=None, parse_mode=None):
        """Edita caption de mensaje de forma segura"""
        try:
            await query.edit_message_caption(caption=caption, reply_markup=reply_markup, parse_mode=parse_mode)
        except BadRequest as e:
            msg = str(e).lower()
            if "message is not modified" in msg:
                try:
                    await query.answer("✅ Contenido ya actualizado")
                except:
                    pass
            elif "can't parse entities" in msg:
                try:
                    await query.edit_message_caption(caption=caption, reply_markup=reply_markup, parse_mode=None)
                    return
                except:
                    pass
                raise
            else:
                raise

    def _normalize_parse_mode(self, pm: str | None) -> str:
        """Normaliza el modo de parseo"""
        if not pm:
            return "HTML"
        if pm.lower().startswith("markdown"):
            return "MarkdownV2"
        return "HTML" if pm.upper() == "HTML" else pm

    def _buttons_to_list(self, buttons):
        """Normaliza botones a lista de listas"""
        if not buttons:
            return []
        if isinstance(buttons, str):
            try:
                parsed = json.loads(buttons)
                return parsed if isinstance(parsed, list) else []
            except Exception:
                return []
        if isinstance(buttons, list):
            return buttons
        return []

    async def handle_callback_query(self, update, context):
        """Maneja todas las consultas de callback"""
        query = update.callback_query
        await query.answer()
        data = query.data
        user_id = query.from_user.id

        logger.info(f"🔘 Callback recibido: {data} de usuario {user_id}")

        # Verificar permisos para callbacks no públicos
        if not self._is_public_callback(data):
            if not check_admin_permissions(user_id, data):
                await self.safe_edit_message_text(
                    query, 
                    "❌ **Acceso Denegado**\n\nNo tienes permisos para realizar esta acción.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return

        # Navegación pública (sistema de bienvenida)
        if data.startswith("wb_home_"):
            chat_id = int(data.split("_")[-1])
            node = await self.db.get_root_node(chat_id)
            await self.show_node_content(query, node, book_mode=True)
            return
            
        if data.startswith("wb_") and len(data.split("_")) == 2 and data.split("_")[1].isdigit():
            node_id = int(data.split("_")[1])
            node = await self.db.get_node(node_id)
            if node:
                await self.show_node_content(query, node, book_mode=True)
            else:
                await query.answer("❌ Contenido no disponible", show_alert=True)
            return

        # Routing de administración
        await self._handle_admin_callbacks(query, data)

    async def _handle_admin_callbacks(self, query, data):
        """Maneja callbacks de administración"""
        if data == "admin_panel":
            await self.show_admin_panel(query)
        elif data == "view_groups":
            await self.show_groups_list(query)
        elif data == "bot_info":
            await self.show_bot_info(query)
        elif data == "manage_welcomes":
            await self.show_manage_welcomes(query)
        elif data == "global_settings":
            await self.show_global_settings(query)
        elif data == "general_stats":
            await self.show_general_stats(query)
        elif data.startswith("config_welcome_"):
            chat_id = int(data.split("_")[-1])
            await self.show_welcome_config(query, chat_id)
        elif data.startswith("group_settings_"):
            chat_id = int(data.split("_")[-1])
            await self.show_group_settings(query, chat_id)
        elif data.startswith("group_stats_"):
            chat_id = int(data.split("_")[-1])
            await self.show_group_stats(query, chat_id)
        elif data.startswith("config_group_"):
            chat_id = int(data.split("_")[-1])
            await self.show_group_config(query, chat_id)
        elif data.startswith("test_welcome_"):
            chat_id = int(data.split("_")[-1])
            await self.test_welcome_message(query, chat_id)
        else:
            await self._handle_specific_callbacks(query, data)

    async def _handle_specific_callbacks(self, query, data):
        """Maneja callbacks específicos"""
        if data.startswith("edit_welcome_buttons_"):
            chat_id = int(data.split("_")[-1])
            await self.show_node_manager(query, chat_id, None)
        elif data.startswith("node_mgr_"):
            parts = data.split("_")
            node_id = int(parts[-1])
            chat_id = int(parts[-2])
            await self.show_node_manager(query, chat_id, node_id)
        elif data.startswith("node_add_url_"):
            node_id = int(data.split("_")[-1])
            await self.start_add_url_button(query, node_id)
        elif data.startswith("node_add_sub_"):
            node_id = int(data.split("_")[-1])
            await self.start_add_submenu_button(query, node_id)
        elif data.startswith("edit_welcome_message_"):
            chat_id = int(data.split("_")[-1])
            await self.start_welcome_message_edit(query, chat_id)
        elif data.startswith("toggle_welcome_"):
            chat_id = int(data.split("_")[-1])
            await self.toggle_welcome_status(query, chat_id)
        elif data.startswith("welcome_mode_"):
            await self._handle_welcome_mode_callback(query, data)
        elif data.startswith("back_"):
            await self.handle_back_navigation(query, data)

    async def _handle_welcome_mode_callback(self, query, data):
        """Maneja callback de modo de bienvenida"""
        parts = data.split("_")
        if len(parts) >= 4:
            chat_id = int(parts[2])
            mode = "_".join(parts[3:])
            await self.set_welcome_mode(query, chat_id, mode)

    def build_node_keyboard(self, node: dict):
        """Construye teclado para un nodo"""
        rows = []
        buttons = self._buttons_to_list(node.get('buttons'))

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

    async def show_node_content(self, query, node: dict, book_mode: bool = True):
        """Muestra contenido de un nodo"""
        if not node:
            await query.answer("❌ Contenido no disponible", show_alert=True)
            return
            
        try:
            group_info = await self.db.get_group_info(node['chat_id'])
            group_name = group_info[1] if group_info else "el grupo"
            pmode = self._normalize_parse_mode(node.get('parse_mode') or "HTML")
            text = format_welcome_message(node['text'] or "", query.from_user, group_name, parse_mode=pmode)
            km = self.build_node_keyboard(node)

            message = query.message
            has_image = bool(node.get('image_url'))
            is_message_photo = bool(getattr(message, "photo", None))

            if has_image:
                if is_message_photo:
                    await self.safe_edit_message_caption(query, text, reply_markup=km, parse_mode=pmode)
                else:
                    current_chat_id = message.chat.id if message and message.chat else node['chat_id']
                    current_thread_id = getattr(message, "message_thread_id", None) if message else None
                    
                    await query.bot.send_photo(
                        chat_id=current_chat_id,
                        photo=node['image_url'],
                        caption=text,
                        reply_markup=km,
                        parse_mode=pmode,
                        message_thread_id=current_thread_id
                    )
            else:
                if is_message_photo:
                    current_chat_id = message.chat.id if message and message.chat else node['chat_id']
                    current_thread_id = getattr(message, "message_thread_id", None) if message else None
                    
                    await query.bot.send_message(
                        chat_id=current_chat_id,
                        text=text,
                        reply_markup=km,
                        parse_mode=pmode,
                        message_thread_id=current_thread_id
                    )
                else:
                    await self.safe_edit_message_text(query, text, reply_markup=km, parse_mode=pmode)

        except BadRequest as e:
            if "can't parse entities" in str(e).lower():
                # Reintento sin formato
                safe_text = format_welcome_message(node['text'] or "", query.from_user, group_name, parse_mode=None)
                try:
                    if has_image and not is_message_photo:
                        await query.bot.send_photo(
                            chat_id=current_chat_id,
                            photo=node['image_url'],
                            caption=safe_text,
                            reply_markup=km,
                            parse_mode=None,
                            message_thread_id=current_thread_id
                        )
                    else:
                        await self.safe_edit_message_text(query, safe_text, reply_markup=km, parse_mode=None)
                except Exception as e2:
                    logger.error(f"❌ Error mostrando contenido sin formato: {e2}")
            else:
                logger.error(f"❌ Error mostrando contenido: {e}")
        except Exception as e:
            logger.error(f"❌ Error inesperado mostrando contenido: {e}")
            try:
                await query.answer(f"❌ Error mostrando contenido", show_alert=True)
            except:
                pass

    async def test_welcome_message(self, query, chat_id: int):
        """CORREGIDO: Envía una vista previa funcional del mensaje de bienvenida"""
        logger.info(f"🧪 Iniciando prueba de bienvenida para grupo {chat_id}")
        
        try:
            # Asegurar que existe el nodo raíz
            await self.db.ensure_root_node(chat_id)
            root = await self.db.get_root_node(chat_id)
            if not root:
                await query.answer("❌ No hay configuración de bienvenida", show_alert=True)
                return

            # Obtener información del grupo
            group = await self.db.get_group_info(chat_id)
            group_name = group[1] if group else "el grupo de prueba"
            
            # Preparar datos del mensaje
            pmode = self._normalize_parse_mode(root.get("parse_mode") or "HTML")
            text = format_welcome_message(
                root.get("text") or "",
                query.from_user,
                group_name,
                parse_mode=pmode
            )
            keyboard = self.build_node_keyboard(root)
            admin_chat_id = query.from_user.id

            # Texto de vista previa
            preview_header = f"🧪 **Vista previa de bienvenida**\n📍 **Grupo:** {group_name}\n\n"
            
            logger.info(f"📤 Enviando vista previa a chat privado {admin_chat_id}")

            # Enviar la vista previa
            if root.get("image_url"):
                # Con imagen
                full_caption = preview_header + text
                await query.bot.send_photo(
                    chat_id=admin_chat_id,
                    photo=root["image_url"],
                    caption=full_caption,
                    reply_markup=keyboard,
                    parse_mode=pmode
                )
                logger.info("📷 Vista previa con imagen enviada")
            else:
                # Solo texto
                full_text = preview_header + text
                await query.bot.send_message(
                    chat_id=admin_chat_id,
                    text=full_text,
                    reply_markup=keyboard,
                    parse_mode=pmode
                )
                logger.info("📝 Vista previa de texto enviada")
            
            await query.answer("✅ Vista previa enviada a tu chat privado")
            logger.info("✅ Prueba de bienvenida completada exitosamente")

        except BadRequest as e:
            # Fallback si hay error de parseo
            if "can't parse entities" in str(e).lower():
                logger.warning(f"⚠️ Error de parseo, enviando sin formato: {e}")
                try:
                    safe_text = f"🧪 Vista previa de bienvenida\n📍 Grupo: {group_name}\n\n"
                    safe_text += format_welcome_message(
                        root.get("text") or "",
                        query.from_user,
                        group_name,
                        parse_mode=None
                    )
                    
                    if root.get("image_url"):
                        await query.bot.send_photo(
                            chat_id=admin_chat_id,
                            photo=root["image_url"],
                            caption=safe_text,
                            reply_markup=keyboard,
                            parse_mode=None
                        )
                    else:
                        await query.bot.send_message(
                            chat_id=admin_chat_id,
                            text=safe_text,
                            reply_markup=keyboard,
                            parse_mode=None
                        )
                    await query.answer("✅ Vista previa enviada (sin formato)")
                    logger.info("✅ Vista previa sin formato enviada")
                except Exception as e2:
                    logger.error(f"❌ Error enviando vista previa sin formato: {e2}")
                    await query.answer("❌ Error enviando vista previa", show_alert=True)
            else:
                logger.error(f"❌ Error BadRequest en vista previa: {e}")
                await query.answer("❌ Error enviando vista previa", show_alert=True)
        except Exception as e:
            logger.error(f"❌ Error inesperado en prueba de bienvenida: {e}")
            await query.answer("❌ Error inesperado. Revisa los logs.", show_alert=True)

    async def set_welcome_mode(self, query, chat_id: int, mode: str):
        """Establece el modo de bienvenida"""
        await self.db.set_welcome_mode(chat_id, mode)
        mode_text = "siempre" if mode == "always" else "solo nuevos usuarios"
        await query.answer(f"✅ Modo actualizado: {mode_text}")
        await self.show_welcome_config(query, chat_id)

    async def show_admin_panel(self, query):
        """Muestra el panel principal de administración"""
        keyboard = [
            [InlineKeyboardButton("📊 Ver Grupos", callback_data="view_groups")],
            [InlineKeyboardButton("🎉 Gestionar Bienvenidas", callback_data="manage_welcomes")],
            [InlineKeyboardButton("⚙️ Configuraciones Globales", callback_data="global_settings")],
            [InlineKeyboardButton("📈 Estadísticas Generales", callback_data="general_stats")],
            [InlineKeyboardButton("ℹ️ Información del Bot", callback_data="bot_info")]
        ]
        
        text = (
            "🏠 **Panel de Administración Principal**\n\n"
            "Bienvenido al sistema de control del bot administrador.\n\n"
            "**Funciones disponibles:**\n"
            "• Gestión completa de grupos\n"
            "• Sistema de bienvenidas avanzado\n"
            "• Configuración global del bot\n"
            "• Estadísticas detalladas\n"
            "• Monitoreo en tiempo real\n\n"
            "Selecciona una opción para continuar:"
        )
        
        await self.safe_edit_message_text(
            query,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    async def show_groups_list(self, query):
        """Muestra la lista de grupos registrados"""
        groups = await self.db.get_all_active_groups()
        if not groups:
            await self.safe_edit_message_text(
                query,
                "📭 **No hay grupos registrados**\n\n"
                "Añade el bot a un grupo para comenzar a administrarlo.\n\n"
                "**Instrucciones:**\n"
                "1. Añade el bot a tu grupo\n"
                "2. Dale permisos de administrador\n"
                "3. Usa `/admin` para configurar",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]]),
                parse_mode=ParseMode.MARKDOWN
            )
            return

        text = "📊 **Lista de Grupos Registrados**\n\n"
        keyboard = []
        
        for i, group in enumerate(groups, 1):
            text += f"**{i}. {group[1]}**\n"
            text += f"   🆔 ID: `{group[0]}`\n"
            text += f"   👥 Miembros: {group[6]}\n"
            text += f"   📅 Añadido: {format_date(group[7])}\n"
            text += f"   💬 Foro: {'✅' if group[9] else '❌'}\n\n"
            
            keyboard.append([InlineKeyboardButton(
                f"⚙️ {truncate_text(group[1], 25)}",
                callback_data=f"config_group_{group[0]}"
            )])

        keyboard.append([InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")])
        
        await self.safe_edit_message_text(
            query, 
            text, 
            reply_markup=InlineKeyboardMarkup(keyboard), 
            parse_mode=ParseMode.MARKDOWN
        )

    async def show_welcome_config(self, query, chat_id: int):
        """Muestra configuración de bienvenida de un grupo"""
        await self.db.ensure_root_node(chat_id)
        welcome_config = await self.db.get_welcome_settings(chat_id)
        group = await self.db.get_group_info(chat_id)
        
        if not group:
            await self.safe_edit_message_text(query, "❌ Grupo no encontrado.")
            return

        root_node = await self.db.get_root_node(chat_id)
        buttons = self._buttons_to_list(root_node.get('buttons') if root_node else [])
        buttons_count = sum(len(r) for r in buttons)
        welcome_mode = await self.db.get_welcome_mode(chat_id)

        status = "✅ Activado" if welcome_config and welcome_config[1] else "❌ Desactivado"
        message_preview = truncate_text(root_node['text'] or "", 120) if root_node else "Sin mensaje"
        mode_text = "Siempre" if welcome_mode == "always" else "Solo nuevos usuarios"

        text = (
            f"🎉 **Configuración de Bienvenida**\n\n"
            f"**Grupo:** {group[1]}\n"
            f"**Estado:** {status}\n"
            f"**Modo:** {mode_text}\n"
            f"**Botones:** {buttons_count} configurados\n"
            f"**Imagen:** {'✅ Sí' if root_node and root_node.get('image_url') else '❌ No'}\n\n"
            f"**Vista previa del mensaje:**\n"
            f"_{message_preview}_"
        )

        keyboard = [
            [InlineKeyboardButton("📝 Editar Mensaje", callback_data=f"edit_welcome_message_{chat_id}")],
            [InlineKeyboardButton("🔘 Gestionar Botones/Submenús", callback_data=f"edit_welcome_buttons_{chat_id}")],
            [InlineKeyboardButton("🖼️ Configurar Imagen", callback_data=f"edit_welcome_image_{chat_id}")],
            [
                InlineKeyboardButton("🔄 Siempre", callback_data=f"welcome_mode_{chat_id}_always"),
                InlineKeyboardButton("👤 Solo nuevos", callback_data=f"welcome_mode_{chat_id}_new_only")
            ],
            [InlineKeyboardButton("🔄 Cambiar Estado", callback_data=f"toggle_welcome_{chat_id}")],
            [InlineKeyboardButton("🧪 Probar Bienvenida", callback_data=f"test_welcome_{chat_id}")],
            [InlineKeyboardButton("🔙 Volver", callback_data="manage_welcomes")]
        ]
        
        await self.safe_edit_message_text(
            query, 
            text, 
            reply_markup=InlineKeyboardMarkup(keyboard), 
            parse_mode=ParseMode.MARKDOWN
        )

    async def show_manage_welcomes(self, query):
        """Muestra gestión de bienvenidas"""
        groups = await self.db.get_all_active_groups()
        if not groups:
            await self.safe_edit_message_text(
                query,
                "📭 **No hay grupos para gestionar**\n\n"
                "Añade el bot a grupos para poder configurar sus bienvenidas.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]])
            )
            return

        text = "🎉 **Gestión de Bienvenidas**\n\n"
        keyboard = []
        
        for group in groups:
            welcome_config = await self.db.get_welcome_settings(group[0])
            status = "✅" if welcome_config and welcome_config[1] else "❌"
            text += f"{status} **{group[1]}**\n"
            
            keyboard.append([InlineKeyboardButton(
                f"{status} {truncate_text(group[1], 25)}",
                callback_data=f"config_welcome_{group[0]}"
            )])
            
        keyboard.append([InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")])
        
        await self.safe_edit_message_text(
            query, 
            text, 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    async def show_node_manager(self, query, chat_id: int, node_id: int | None):
        """Muestra el gestor de nodos/botones"""
        await self.db.ensure_root_node(chat_id)
        node = await self.db.get_root_node(chat_id) if node_id is None else await self.db.get_node(node_id)
        
        if not node:
            await self.safe_edit_message_text(query, "❌ Nodo no encontrado.")
            return

        buttons = self._buttons_to_list(node.get('buttons'))
        btn_count = sum(len(r) for r in buttons)
        pmode = self._normalize_parse_mode(node.get('parse_mode') or "HTML")

        node_label = "Raíz (Principal)" if node['parent_id'] is None else f"Submenú ID {node['id']}"
        
        text = f"🔘 **Gestor de Botones y Submenús**\n\n"
        text += f"**Nodo:** {node_label}\n"
        text += f"**Botones configurados:** {btn_count}\n"
        text += f"**Parse mode:** {pmode}\n"
        text += f"**Imagen:** {'✅ Sí' if node.get('image_url') else '❌ No'}\n\n"

        if buttons:
            text += "**Botones actuales:**\n"
            for i, row in enumerate(buttons, 1):
                for j, b in enumerate(row, 1):
                    if b.get('type') == 'url':
                        text += f"• [{i}.{j}] 🔗 {b.get('text')} → `{b.get('url')}`\n"
                    elif b.get('type') == 'node':
                        text += f"• [{i}.{j}] 📁 {b.get('text')} → Submenú {b.get('node_id')}\n"
        else:
            text += "_No hay botones configurados en este nodo._\n"

        children = await self.db.get_child_nodes(node['chat_id'], node['id'])
        if children:
            text += f"\n**Submenús hijos:** {len(children)}\n"
            for ch in children[:3]:  # Mostrar solo los primeros 3
                preview = truncate_text(ch['text'] or '', 40)
                text += f"• Submenú {ch['id']}: _{preview}_\n"
            if len(children) > 3:
                text += f"• ... y {len(children) - 3} más\n"

        keyboard = [
            [
                InlineKeyboardButton("➕ Botón URL", callback_data=f"node_add_url_{node['id']}"),
                InlineKeyboardButton("➕ Submenú", callback_data=f"node_add_sub_{node['id']}")
            ],
            [
                InlineKeyboardButton("📝 Editar texto", callback_data=f"node_rename_{node['id']}"),
                InlineKeyboardButton("🖼️ Imagen", callback_data=f"node_set_image_{node['id']}")
            ],
            [InlineKeyboardButton(f"🛠 Parse: {pmode}", callback_data=f"node_parse_{node['id']}")],
            [InlineKeyboardButton("🧹 Limpiar botones", callback_data=f"node_clear_btns_{node['id']}")]
        ]
        
        if node['parent_id'] is not None:
            keyboard.append([InlineKeyboardButton("🗑️ Eliminar este submenú", callback_data=f"node_del_{node['id']}")])
            
        if children:
            keyboard.append([InlineKeyboardButton("📂 Ver submenús", callback_data=f"node_list_children_{node['chat_id']}_{node['id']}")])
            
        keyboard.append([InlineKeyboardButton("🔙 Volver", callback_data=f"config_welcome_{chat_id}")])

        await self.safe_edit_message_text(
            query, 
            text, 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    async def start_add_url_button(self, query, node_id: int):
        """Inicia proceso de añadir botón URL"""
        node = await self.db.get_node(node_id)
        self.message_handler.waiting_for_input[query.from_user.id] = {
            'action': 'button_text',
            'button_type': 'url',
            'node_id': node_id,
            'chat_id': node['chat_id']
        }
        
        await self.safe_edit_message_text(
            query,
            "🔘 **Añadir Botón URL**\n\n"
            "**Paso 1 de 2:** Envía el texto que tendrá el botón.\n\n"
            "Ejemplo: `Visitar sitio web`, `Más información`, etc.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancelar", callback_data=f"node_mgr_{node['chat_id']}_{node_id}")
            ]]),
            parse_mode=ParseMode.MARKDOWN
        )

    async def start_add_submenu_button(self, query, node_id: int):
        """Inicia proceso de añadir submenú"""
        node = await self.db.get_node(node_id)
        self.message_handler.waiting_for_input[query.from_user.id] = {
            'action': 'button_sub_text',
            'node_id': node_id,
            'chat_id': node['chat_id']
        }
        
        await self.safe_edit_message_text(
            query,
            "📁 **Añadir Submenú**\n\n"
            "**Paso 1 de 2:** Envía el texto del botón que abrirá el submenú.\n\n"
            "Ejemplo: `Ver más opciones`, `Información adicional`, etc.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancelar", callback_data=f"node_mgr_{node['chat_id']}_{node_id}")
            ]]),
            parse_mode=ParseMode.MARKDOWN
        )

    async def start_welcome_message_edit(self, query, chat_id: int):
        """Inicia edición del mensaje de bienvenida"""
        self.message_handler.waiting_for_input[query.from_user.id] = {
            'action': 'welcome_message',
            'chat_id': chat_id
        }
        
        text = (
            "📝 **Editar Mensaje de Bienvenida**\n\n"
            "Envía el nuevo mensaje que se mostrará cuando alguien se una al grupo.\n\n"
            "**Variables disponibles:**\n"
            "• `{mention}` — menciona al usuario\n"
            "• `{name}` — nombre del usuario\n"
            "• `{username}` — @usuario o nombre si no tiene\n"
            "• `{group_name}` — nombre del grupo\n\n"
            "**Formatos soportados:**\n"
            "• HTML: `<b>negrita</b>`, `<i>cursiva</i>`\n"
            "• MarkdownV2: `**negrita**`, `*cursiva*`\n\n"
            "**Ejemplo:**\n"
            "`¡Bienvenido/a {mention} a {group_name}! 🎉`"
        )
        
        await self.safe_edit_message_text(
            query,
            text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancelar", callback_data=f"config_welcome_{chat_id}")
            ]]),
            parse_mode=ParseMode.MARKDOWN
        )

    async def toggle_welcome_status(self, query, chat_id: int):
        """Cambia el estado de la bienvenida"""
        new_status = await self.db.toggle_welcome_status(chat_id)
        status_text = "activada" if new_status else "desactivada"
        await query.answer(f"✅ Bienvenida {status_text}")
        await self.show_welcome_config(query, chat_id)

    async def show_bot_info(self, query):
        """Muestra información del bot"""
        stats = await self.db.get_general_stats()
        
        text = (
            "ℹ️ **Información del Bot**\n\n"
            f"**Nombre:** Bot Administrador de Grupos\n"
            f"**Versión:** 2.0.0\n"
            f"**Estado:** ✅ Online\n\n"
            f"**Estadísticas:**\n"
            f"• Grupos activos: {stats['total_groups'][0]}\n"
            f"• Bienvenidas enviadas: {stats['total_welcomes'][0] or 0}\n"
            f"• Base de datos: MongoDB\n\n"
            f"**Funcionalidades:**\n"
            f"• Sistema de bienvenida avanzado\n"
            f"• Botones y submenús interactivos\n"
            f"• Soporte para imágenes y formatos\n"
            f"• Gestión completa de grupos\n"
            f"• Configuración de temas/hilos\n"
            f"• Modos de bienvenida personalizables\n"
            f"• Panel de administración completo\n"
            f"• Estadísticas en tiempo real"
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Volver al Panel", callback_data="admin_panel")]]
        
        await self.safe_edit_message_text(
            query, 
            text, 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    async def show_group_settings(self, query, chat_id: int):
        """Muestra configuraciones de un grupo específico"""
        # Actualizar información en vivo
        try:
            chat = await query.bot.get_chat(chat_id)
            member_count = await query.bot.get_chat_member_count(chat_id)
            is_forum_live = getattr(chat, "is_forum", False)
            await self.db.update_group_info(chat_id, chat.title, member_count, is_forum=is_forum_live)
        except Exception as e:
            logger.warning(f"⚠️ No se pudo actualizar info del grupo {chat_id}: {e}")

        group = await self.db.get_group_info(chat_id)
        if not group:
            await self.safe_edit_message_text(query, "❌ Grupo no encontrado.")
            return

        is_forum = bool(group[9])
        welcome_thread_id = group[10]

        text = (
            f"⚙️ **Configuraciones del Grupo**\n\n"
            f"**Información básica:**\n"
            f"• Nombre: {group[1]}\n"
            f"• ID: `{chat_id}`\n"
            f"• Tipo: {group[2]}\n"
            f"• Miembros: {group[6]}\n\n"
            f"**Configuración:**\n"
            f"• Temas habilitados: {'✅ Sí' if is_forum else '❌ No'}\n"
            f"• Tema de bienvenidas: {welcome_thread_id if welcome_thread_id is not None else 'No configurado'}\n\n"
            f"**Historial:**\n"
            f"• Añadido por: {group[5]}\n"
            f"• Fecha de adición: {format_date(group[7])}"
        )

        keyboard = [
            [InlineKeyboardButton("🎉 Configurar Bienvenida", callback_data=f"config_welcome_{chat_id}")],
            [InlineKeyboardButton("📊 Ver Estadísticas", callback_data=f"group_stats_{chat_id}")],
            [InlineKeyboardButton("🧵 Configurar tema", callback_data=f"set_welcome_topic_instr_{chat_id}")],
            [InlineKeyboardButton("🔄 Actualizar Info", callback_data=f"update_group_{chat_id}")],
            [InlineKeyboardButton("❌ Desactivar Grupo", callback_data=f"deactivate_group_{chat_id}")],
            [InlineKeyboardButton("🔙 Volver", callback_data="view_groups")]
        ]
        
        await self.safe_edit_message_text(
            query, 
            text, 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    async def show_group_config(self, query, chat_id: int):
        """Alias para show_group_settings"""
        await self.show_group_settings(query, chat_id)

    async def show_group_stats(self, query, chat_id: int):
        """Muestra estadísticas de un grupo"""
        group = await self.db.get_group_info(chat_id)
        stats = await self.db.get_group_stats(chat_id)
        
        if not group:
            await self.safe_edit_message_text(query, "❌ Grupo no encontrado.")
            return

        try:
            days_active = (datetime.utcnow() - datetime.fromisoformat(group[7])).days
        except:
            days_active = "N/D"

        welcomes_sent = stats[1] if stats else 0
        last_activity = format_date(stats[2]) if stats and stats[2] else "Nunca"

        text = (
            f"📈 **Estadísticas del Grupo**\n\n"
            f"**{group[1]}**\n\n"
            f"**Actividad:**\n"
            f"• Días activo: {days_active}\n"
            f"• Bienvenidas enviadas: {welcomes_sent}\n"
            f"• Última actividad: {last_activity}\n\n"
            f"**Información actual:**\n"
            f"• Miembros actuales: {group[6]}\n"
            f"• Estado: {'✅ Activo' if group[8] else '❌ Inactivo'}\n"
            f"• Tipo de chat: {group[2]}"
        )

        keyboard = [
            [InlineKeyboardButton("🔄 Actualizar", callback_data=f"refresh_stats_{chat_id}")],
            [InlineKeyboardButton("🔙 Volver", callback_data=f"group_settings_{chat_id}")]
        ]
        
        await self.safe_edit_message_text(
            query, 
            text, 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    async def show_general_stats(self, query):
        """Muestra estadísticas generales del bot"""
        stats = await self.db.get_general_stats()
        
        text = (
            "📈 **Estadísticas Generales del Bot**\n\n"
            f"**Resumen:**\n"
            f"• Grupos activos: {stats['total_groups'][0]}\n"
            f"• Grupos inactivos: {stats['inactive_groups'][0]}\n"
            f"• Total bienvenidas: {stats['total_welcomes'][0] or 0}\n"
            f"• Promedio de miembros: {int(stats['avg_members'][0]) if stats['avg_members'][0] else 0}\n\n"
            f"**🏆 Top 5 grupos (por bienvenidas):**\n"
        )
        
        for i, group in enumerate(stats['top_groups'], 1):
            text += f"{i}. {group[0]}: {group[1]} bienvenidas\n"
            
        if not stats['top_groups']:
            text += "_No hay datos de bienvenidas aún._\n"

        keyboard = [
            [InlineKeyboardButton("🔄 Actualizar", callback_data="general_stats")],
            [InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]
        ]
        
        await self.safe_edit_message_text(
            query, 
            text, 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    async def show_global_settings(self, query):
        """Muestra configuraciones globales"""
        settings = await self.db.get_all_settings()
        language = settings.get('language', 'es')
        datefmt = settings.get('date_format', '%d/%m/%Y %H:%M')
        parse_mode = settings.get('default_parse_mode', 'HTML')

        text = (
            "⚙️ **Configuraciones Globales**\n\n"
            f"**Configuración actual:**\n"
            f"• Idioma: {language.upper()}\n"
            f"• Formato de fecha: `{datefmt}`\n"
            f"• Parse Mode por defecto: {parse_mode}\n\n"
            "Selecciona una opción para modificar:"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("🌐 ES", callback_data="gs_lang_es"),
                InlineKeyboardButton("EN", callback_data="gs_lang_en"),
            ],
            [
                InlineKeyboardButton("📅 DD/MM/YYYY HH:mm", callback_data="gs_datefmt_1"),
                InlineKeyboardButton("YYYY-MM-DD HH:mm", callback_data="gs_datefmt_2"),
                InlineKeyboardButton("DD/MM/YYYY", callback_data="gs_datefmt_3"),
            ],
            [
                InlineKeyboardButton("📝 HTML", callback_data="gs_parse_HTML"),
                InlineKeyboardButton("MarkdownV2", callback_data="gs_parse_MarkdownV2"),
            ],
            [InlineKeyboardButton("🔙 Volver", callback_data="admin_panel")]
        ]
        
        await self.safe_edit_message_text(
            query, 
            text, 
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )

    async def handle_back_navigation(self, query, data: str):
        """Maneja navegación hacia atrás"""
        parts = data.split("_")
        destination = parts[1] if len(parts) > 1 else ""
        
        if destination == "admin":
            await self.show_admin_panel(query)
        elif destination == "groups":
            await self.show_groups_list(query)
        elif destination == "welcomes":
            await self.show_manage_welcomes(query)
        else:
            # Navegación por defecto
            await self.show_admin_panel(query)
