import asyncio
import logging
from typing import Dict, List
from datetime import datetime
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, 
    filters, ContextTypes, CallbackQueryHandler
)
from telegram.error import TelegramError

from config import config
from snapchat_downloader import SnapchatDownloader

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class RateLimiter:
    """Simple rate limiter for users."""
    def __init__(self):
        self.user_requests = {}
    
    def is_allowed(self, user_id: int) -> bool:
        """Check if user can make a request."""
        current_time = datetime.now().timestamp()
        
        if user_id not in self.user_requests:
            self.user_requests[user_id] = []
        
        # Clean old requests (older than 1 minute)
        self.user_requests[user_id] = [
            t for t in self.user_requests[user_id] 
            if current_time - t < 60
        ]
        
        # Check limit
        if len(self.user_requests[user_id]) >= config.REQUESTS_PER_MINUTE:
            return False
        
        self.user_requests[user_id].append(current_time)
        return True
    
    def get_wait_time(self, user_id: int) -> float:
        """Get remaining wait time for user."""
        if user_id not in self.user_requests:
            return 0
        
        current_time = datetime.now().timestamp()
        valid_requests = [
            t for t in self.user_requests[user_id] 
            if current_time - t < 60
        ]
        
        if not valid_requests:
            return 0
        
        oldest_request = min(valid_requests)
        return max(0, 60 - (current_time - oldest_request))

class SnapchatTelegramBot:
    def __init__(self):
        self.application = None
        self.session = None
        self.downloader = None
        self.rate_limiter = RateLimiter()
        self.user_sessions = {}
    
    async def initialize(self):
        """Initialize bot components."""
        import aiohttp
        
        # Create aiohttp session
        self.session = aiohttp.ClientSession()
        self.downloader = SnapchatDownloader(self.session)
        
        # Initialize Telegram bot
        self.application = Application.builder().token(config.BOT_TOKEN).build()
        
        # Add handlers
        self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup all Telegram bot handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("stats", self.stats_command))
        self.application.add_handler(CommandHandler("clean", self.clean_command))
        
        # Message handler
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Callback query handler for buttons
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        user = update.effective_user
        
        # Check if user is authorized
        if config.ADMIN_IDS and user.id not in config.ADMIN_IDS:
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
        
        welcome_text = f"""
👋 *Welcome to Snapchat Downloader Bot* 👋

*Hello {user.first_name}!* I can help you download public Snapchat stories.

*How to use:*
1. Send a Snapchat username (e.g., `username`)
2. Send a profile URL (e.g., `snapchat.com/add/username`)
3. I'll fetch and send you the public content

*Commands:*
/start - Show this message
/help - Detailed instructions
/stats - Your usage statistics
/clean - Clean temporary files

*Rate Limit:* {config.REQUESTS_PER_MINUTE} requests per minute
*Max File Size:* {config.MAX_FILE_SIZE // 1024 // 1024}MB

⚠️ *Note:* Only works with public content.
        """
        
        keyboard = [
            [InlineKeyboardButton("📖 How to Use", callback_data="help")],
            [InlineKeyboardButton("🔧 Bot Status", callback_data="status")],
            [InlineKeyboardButton("🚀 Quick Start", callback_data="quickstart")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            welcome_text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        help_text = """
*📚 Detailed Help Guide*

*Supported Input Formats:*
1. *Username:* `username` or `@username`
2. *Profile URL:* `https://snapchat.com/add/username`
3. *Story URL:* `https://story.snapchat.com/s/username`

*How it works:*
1. I fetch public Snapchat stories
2. Download media files
3. Send them to you via Telegram
4. Automatically clean up temporary files

*Limitations:*
• Only public content (no private accounts)
• Max 15 items per request
• {max_size}MB file size limit
• {rate_limit} requests per minute

*Troubleshooting:*
• If bot doesn't respond: Send /start again
• If download fails: Content might be private or removed
• If rate limited: Wait 1 minute

*Privacy:*
• I don't store your data permanently
• Temporary files are deleted after sending
• No logs are kept
        """.format(
            max_size=config.MAX_FILE_SIZE // 1024 // 1024,
            rate_limit=config.REQUESTS_PER_MINUTE
        )
        
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command."""
        user_id = update.effective_user.id
        
        stats = self.rate_limiter.get_wait_time(user_id)
        
        stats_text = f"""
*📊 Your Statistics*

*Rate Limit Status:*
• Wait time: {stats:.1f} seconds
• Limit: {config.REQUESTS_PER_MINUTE} requests/minute
• Burst: {config.BURST_SIZE} concurrent

*Bot Status:*
• Active: ✅
• Temp files: {len(list(Path(config.TEMP_DIR).glob('*')))} files
• Memory: {self._get_memory_usage()} MB

*Note:* Statistics reset every minute.
        """
        
        await update.message.reply_text(stats_text, parse_mode='Markdown')
    
    async def clean_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /clean command to clean temporary files."""
        import shutil
        
        try:
            temp_dir = Path(config.TEMP_DIR)
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                temp_dir.mkdir(exist_ok=True)
            
            await update.message.reply_text("✅ Temporary files cleaned successfully!")
        except Exception as e:
            await update.message.reply_text(f"❌ Error cleaning files: {e}")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming text messages."""
        user_id = update.effective_user.id
        
        # Check authorization
        if config.ADMIN_IDS and user_id not in config.ADMIN_IDS:
            await update.message.reply_text("❌ You are not authorized to use this bot.")
            return
        
        # Check rate limit
        if not self.rate_limiter.is_allowed(user_id):
            wait_time = self.rate_limiter.get_wait_time(user_id)
            await update.message.reply_text(
                f"⏳ Rate limit exceeded. Please wait {wait_time:.0f} seconds."
            )
            return
        
        text = update.message.text.strip()
        
        # Show typing indicator
        await update.message.chat.send_action(action="typing")
        
        try:
            # Extract username
            username = self.downloader.extract_username_from_url(text)
            
            if not username:
                await update.message.reply_text(
                    "❌ Invalid input. Please send a valid username or URL.\n"
                    "Examples:\n"
                    "• `username`\n"
                    "• `@username`\n"
                    "• `snapchat.com/add/username`"
                )
                return
            
            # Inform user
            status_msg = await update.message.reply_text(
                f"🔍 Searching for @{username}..."
            )
            
            # Fetch content
            media_items = await self.downloader.fetch_public_content(username)
            
            if not media_items:
                await status_msg.edit_text(
                    f"❌ No public content found for @{username}.\n"
                    "Possible reasons:\n"
                    "• Account is private\n"
                    "• No public stories\n"
                    "• Account doesn't exist"
                )
                return
            
            await status_msg.edit_text(
                f"✅ Found {len(media_items)} items. Downloading..."
            )
            
            # Download and send each item
            success_count = 0
            for idx, item in enumerate(media_items[:10]):  # Limit to 10 items
                try:
                    # Generate filename
                    filename = f"{user_id}_{int(datetime.now().timestamp())}_{idx}"
                    
                    # Download file
                    filepath = await self.downloader.download_media(item['url'], filename)
                    
                    if not filepath or not filepath.exists():
                        continue
                    
                    # Send file based on type
                    if item['type'] == 'video':
                        await update.message.reply_video(
                            video=open(filepath, 'rb'),
                            caption=f"🎥 @{username} | Via SnapBot",
                            supports_streaming=True
                        )
                    else:
                        await update.message.reply_photo(
                            photo=open(filepath, 'rb'),
                            caption=f"📸 @{username} | Via SnapBot"
                        )
                    
                    success_count += 1
                    
                    # Clean up file
                    try:
                        filepath.unlink()
                    except:
                        pass
                    
                    # Small delay between sends
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error processing item {idx}: {e}")
                    continue
            
            # Update status
            result_text = f"""
✅ *Download Complete*

*Results for @{username}:*
• Found: {len(media_items)} items
• Successfully downloaded: {success_count} items
• Failed: {len(media_items) - success_count} items

*Note:* Temporary files have been cleaned.
            """
            
            await status_msg.edit_text(result_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error in handle_message: {e}")
            await update.message.reply_text(
                f"❌ An error occurred:\n`{str(e)[:200]}`",
                parse_mode='Markdown'
            )
    
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks."""
        query = update.callback_query
        await query.answer()
        
        if query.data == "help":
            await self.help_command(update, context)
        elif query.data == "status":
            await query.edit_message_text("✅ Bot is running normally on Replit!")
        elif query.data == "quickstart":
            await query.edit_message_text(
                "🚀 *Quick Start:*\nJust send me a Snapchat username!",
                parse_mode='Markdown'
            )
    
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors gracefully."""
        logger.error(f"Update {update} caused error {context.error}")
        
        try:
            # Try to notify user
            if update and update.effective_message:
                error_msg = str(context.error)[:200]
                await update.effective_message.reply_text(
                    f"⚠️ Bot error: `{error_msg}`\n\nPlease try again or contact admin.",
                    parse_mode='Markdown'
                )
        except:
            pass
    
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        import psutil
        process = psutil.Process()
        return process.memory_info().rss / 1024 / 1024
    
    async def run(self):
        """Run the bot."""
        if not config.validate():
            logger.error("Invalid configuration. Please check Replit Secrets.")
            return
        
        await self.initialize()
        
        logger.info("Starting bot on Replit...")
        
        # Start polling
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        # Keep running
        await asyncio.Event().wait()
    
    async def cleanup(self):
        """Cleanup resources."""
        if self.session:
            await self.session.close()
        if self.application:
            await self.application.stop()