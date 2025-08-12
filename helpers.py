from telegram.constants import ChatMemberStatus
from config import ADMIN_ID
import html
import re

def check_admin_permissions(user_id: int, action: str = None) -> bool:
    """Verifica si un usuario tiene permisos de administrador"""
    return user_id == ADMIN_ID

async def is_group_admin(context, chat_id: int, user_id: int) -> bool:
    """Verifica si un usuario es administrador del grupo"""
    if user_id == ADMIN_ID:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    except Exception:
        return False

def _escape_md_v2(text: str) -> str:
    """Escapa caracteres especiales para MarkdownV2"""
    if not text:
        return ""
    special_chars = r'\_*[]()~`>#+-=|{}.!'
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text

def _escape_html(text: str) -> str:
    """Escapa caracteres HTML"""
    return html.escape(text or "", quote=False)

def format_welcome_message(template: str, user, group_name: str, parse_mode: str = "HTML") -> str:
    """Formatea el mensaje de bienvenida con las variables correspondientes"""
    if not template:
        template = "¡Bienvenido/a {mention} al grupo {group_name}! 🎉"
        
    # Valores seguros
    uid = getattr(user, "id", None)
    raw_name = getattr(user, "first_name", "") or "Usuario"
    raw_username = f"@{getattr(user, 'username', None)}" if getattr(user, "username", None) else raw_name
    raw_group = group_name or "el grupo"

    pm = (parse_mode or "HTML").strip()
    
    if pm.lower().startswith("markdown"):
        # MarkdownV2
        name = _escape_md_v2(raw_name)
        username = _escape_md_v2(raw_username)
        group_e = _escape_md_v2(raw_group)
        mention = f"[{name}](tg://user?id={uid})" if uid else name
    elif pm.upper() == "HTML":
        # HTML
        name = _escape_html(raw_name)
        username = _escape_html(raw_username)
        group_e = _escape_html(raw_group)
        mention = f"<a href='tg://user?id={uid}'>{name}</a>" if uid else name
    else:
        # Texto plano
        name = raw_name
        username = raw_username
        group_e = raw_group
        mention = raw_name

    result = template
    result = result.replace("{mention}", mention)
    result = result.replace("{name}", name)
    result = result.replace("{username}", username)
    result = result.replace("{group_name}", group_e)
    return result

def truncate_text(text: str, max_length: int = 50) -> str:
    """Trunca texto si excede la longitud máxima"""
    if not text:
        return ""
    return text[:max_length] + "..." if len(text) > max_length else text

def format_date(date_string: str) -> str:
    """Formatea una fecha ISO string a formato legible"""
    try:
        from datetime import datetime
        if date_string and date_string.endswith('Z'):
            date_string = date_string[:-1]
        date_obj = datetime.fromisoformat(date_string)
        return date_obj.strftime('%d/%m/%Y %H:%M')
    except Exception:
        return date_string[:10] if date_string else "Desconocido"

def validate_url(url: str) -> bool:
    """Valida si una URL es válida"""
    url_pattern = re.compile(
        r'^https?://'  # http:// o https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # dominio
        r'localhost|'  # localhost
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
        r'(?::\d+)?'  # puerto opcional
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    return url_pattern.match(url) is not None