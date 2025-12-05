#!/usr/bin/env python3
"""
Snapchat Downloader Bot for Replit
Main entry point with web server for uptime
"""

import asyncio
import signal
import sys
import logging
from threading import Thread

# Import bot modules
from keep_alive import keep_alive, ping_server
from telegram_bot import SnapchatTelegramBot
from config import config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class ReplitBotRunner:
    def __init__(self):
        self.bot = SnapchatTelegramBot()
        self.shutdown_event = asyncio.Event()
        self.ping_thread = None
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def run_bot(self):
        """Run the Telegram bot."""
        try:
            await self.bot.initialize()
            await self.bot.application.run_polling()
        except Exception as e:
            logger.error(f"Bot error: {e}")
            raise
    
    async def cleanup(self):
        """Cleanup resources."""
        logger.info("Cleaning up resources...")
        
        if hasattr(self.bot, 'cleanup'):
            await self.bot.cleanup()
        
        # Close any open files/sessions
        import gc
        gc.collect()
    
    def start_ping_thread(self):
        """Start thread to ping server for uptime."""
        self.ping_thread = Thread(target=ping_server, daemon=True)
        self.ping_thread.start()
        logger.info("Ping thread started")
    
    async def main(self):
        """Main async entry point."""
        logger.info("=== Starting Snapchat Bot on Replit ===")
        
        # Validate config
        if not config.validate():
            logger.error("Configuration failed. Please check:")
            logger.error("1. BOT_TOKEN in Replit Secrets")
            logger.error("2. ADMIN_IDS in Replit Secrets (optional)")
            return
        
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Start keep-alive server (for Replit web view)
        keep_alive()
        logger.info("Keep-alive server started on port 8080")
        
        # Start ping thread
        self.start_ping_thread()
        
        # Run bot
        bot_task = asyncio.create_task(self.run_bot())
        
        # Wait for shutdown signal
        try:
            await self.shutdown_event.wait()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        finally:
            # Cancel bot task
            bot_task.cancel()
            try:
                await bot_task
            except asyncio.CancelledError:
                pass
            
            # Cleanup
            await self.cleanup()
            logger.info("Bot shutdown complete")

def run_sync():
    """Run the bot synchronously (for Replit)."""
    runner = ReplitBotRunner()
    
    # Get or create event loop
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    # Run main coroutine
    try:
        loop.run_until_complete(runner.main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup loop
        if not loop.is_closed():
            loop.close()

if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════╗
    ║   Snapchat Downloader Bot - Replit   ║
    ║        Starting up...                ║
    ╚══════════════════════════════════════╝
    """)
    
    # Check Python version
    import platform
    print(f"Python: {platform.python_version()}")
    
    # Run the bot
    run_sync()