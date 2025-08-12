import asyncio
import aiohttp
import aiohttp.web
from datetime import datetime
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from config import BOT_TOKEN, logger, ADMIN_ID, KEEP_ALIVE_URL
from db_manager import DatabaseManager
from commands import CommandHandlers
from messages import MessageHandlers
from callbacks import CallbackHandlers

class KeepAliveService:
    """Servicio para mantener el bot activo en plataformas como Render"""
    
    def __init__(self, url: str = None, interval: int = 840):  # 14 minutos
        self.url = url or KEEP_ALIVE_URL
        self.interval = interval
        self.running = False
    
    async def ping_self(self):
        """Hace ping a sí mismo para mantener el servicio activo"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.url}/health", timeout=30) as response:
                    if response.status == 200:
                        logger.info(f"✅ Keep-alive ping exitoso - {datetime.now().strftime('%H:%M:%S')}")
                    else:
                        logger.warning(f"⚠️ Keep-alive ping falló: {response.status}")
        except Exception as e:
            logger.error(f"❌ Error en keep-alive ping: {e}")
    
    async def start(self):
        """Inicia el servicio de keep-alive"""
        self.running = True
        logger.info("🔄 Servicio Keep-Alive iniciado")
        
        while self.running:
            await asyncio.sleep(self.interval)
            if self.running:
                await self.ping_self()
    
    def stop(self):
        """Detiene el servicio"""
        self.running = False
        logger.info("⏹️ Servicio Keep-Alive detenido")

async def health_check(request):
    """Endpoint de health check"""
    return aiohttp.web.json_response({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "telegram-bot-admin",
        "version": "2.0.0"
    })

async def setup_health_server():
    """Configura servidor HTTP para health checks"""
    app = aiohttp.web.Application()
    app.router.add_get('/health', health_check)
    app.router.add_get('/', health_check)  # También responder en la raíz

    runner = aiohttp.web.AppRunner(app)
    await runner.setup()

    import os
    port = int(os.environ.get('PORT', 8080))

    site = aiohttp.web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"🌐 Servidor de salud iniciado en puerto {port}")

    return runner

class TelegramBot:
    """Clase principal del bot de Telegram"""
    
    def __init__(self):
        self.application = None
        self.db = DatabaseManager()
        self.keep_alive = KeepAliveService()
        self.health_server = None
        
        # Inicializar handlers
        self.command_handler = CommandHandlers(self.db)
        self.message_handler = MessageHandlers(self.db)
        self.callback_handler = CallbackHandlers(self.db, self.message_handler)

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Maneja errores del bot"""
        error_msg = str(context.error)
        logger.error(f"❌ Error en el bot: {error_msg}")
        
        # Notificar al administrador si es posible
        if update and hasattr(update, 'effective_user'):
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"❌ **Error en el bot:**\n\n```\n{error_msg[:1000]}\n```",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"❌ Error enviando notificación de error al admin: {e}")

    async def setup_handlers(self):
        """Configura todos los handlers del bot"""
        # Comandos
        self.application.add_handler(CommandHandler("start", self.command_handler.start))
        self.application.add_handler(CommandHandler("admin", self.command_handler.admin_command))
        self.application.add_handler(CommandHandler("setwelcometopic", self.command_handler.set_welcome_topic))
        self.application.add_handler(CommandHandler("clearwelcometopic", self.command_handler.clear_welcome_topic))

        # Mensajes
        self.application.add_handler(MessageHandler(
            filters.StatusUpdate.NEW_CHAT_MEMBERS, 
            self.message_handler.handle_new_chat_member
        ))
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, 
            self.message_handler.handle_text_input
        ))
        self.application.add_handler(MessageHandler(
            filters.PHOTO,
            self.message_handler.handle_photo_input
        ))
        
        # Callbacks
        self.application.add_handler(CallbackQueryHandler(self.callback_handler.handle_callback_query))

        # Manejador de errores
        self.application.add_error_handler(self.error_handler)
        
        logger.info("✅ Handlers configurados correctamente")

    async def send_startup_notification(self):
        """Envía notificación de inicio al administrador"""
        try:
            startup_message = (
                "🚀 **Bot Administrador Iniciado**\n\n"
                f"**Timestamp:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
                f"**Estado:** ✅ Online\n"
                f"**Versión:** 2.0.0\n\n"
                "El bot está listo para administrar grupos."
            )
            
            await self.application.bot.send_message(
                chat_id=ADMIN_ID,
                text=startup_message,
                parse_mode=ParseMode.MARKDOWN
            )
            logger.info("📬 Notificación de inicio enviada al administrador")
        except Exception as e:
            logger.error(f"❌ Error enviando notificación de inicio: {e}")

    async def run(self):
        """Ejecuta el bot"""
        try:
            # Inicializar base de datos
            logger.info("🔄 Inicializando base de datos...")
            await self.db.initialize_db()

            # Iniciar servidor de salud
            logger.info("🔄 Iniciando servidor de salud...")
            self.health_server = await setup_health_server()

            # Configurar aplicación de Telegram
            logger.info("🔄 Configurando aplicación de Telegram...")
            self.application = Application.builder().token(BOT_TOKEN).build()

            # Configurar handlers
            await self.setup_handlers()

            # Inicializar y arrancar bot
            logger.info("🔄 Iniciando bot de Telegram...")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()

            # Enviar notificación de inicio
            await self.send_startup_notification()

            # Iniciar keep-alive en segundo plano
            keep_alive_task = asyncio.create_task(self.keep_alive.start())
            
            logger.info("✅ Bot iniciado exitosamente")
            logger.info("🎯 El bot está listo para recibir comandos")
            logger.info("📱 Usa /start para acceder al panel de administración")

            try:
                # Mantener el bot corriendo
                await asyncio.Event().wait()
            except KeyboardInterrupt:
                logger.info("🛑 Interrupción por teclado recibida")
            finally:
                # Limpieza
                logger.info("🔄 Deteniendo servicios...")
                self.keep_alive.stop()
                
                if not keep_alive_task.done():
                    keep_alive_task.cancel()
                    try:
                        await keep_alive_task
                    except asyncio.CancelledError:
                        pass

                if self.health_server:
                    await self.health_server.cleanup()

                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                
                logger.info("✅ Bot detenido correctamente")

        except Exception as e:
            logger.error(f"❌ Error crítico en el bot: {e}")
            raise

async def main():
    """Función principal"""
    logger.info("🚀 Iniciando Bot Administrador de Grupos v2.0.0")
    logger.info("=" * 50)
    
    bot = TelegramBot()
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("🛑 Detenido por el usuario")
    except Exception as e:
        logger.error(f"❌ Error fatal: {e}")
        raise
    finally:
        logger.info("👋 ¡Hasta luego!")

if __name__ == "__main__":
    asyncio.run(main())
