import os
import sys
import ssl
import json
import asyncio
import logging
import io
import time
import datetime
import qrcode
from PIL import Image
import certifi
import warnings
from dotenv import load_dotenv
from aiohttp import web

# Load .env file explicitly
load_dotenv()

# Set SSL Certificate for Windows/HTTPErrors
os.environ['SSL_CERT_FILE'] = certifi.where()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
from telegram.request import HTTPXRequest
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
from telegram.warnings import PTBUserWarning

# Suppress PTBUserWarning about per_message=False
warnings.filterwarnings("ignore", category=PTBUserWarning)

# Add src to path to import main
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from main import WDBot

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
# Suppress httpx logs (requests) to reduce noise
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Conversation States
LOGIN_USER, LOGIN_PASS = range(2)
DEPOSIT_NOMINAL = range(2, 3)
MANAGE_ACTION, MANAGE_USERNAME, MANAGE_PASSWORD, MANAGE_BOT_TOKEN, MANAGE_ADMIN_ID = range(3, 8)
SETTINGS_ACTION, SETTINGS_EDIT_WELCOME, SETTINGS_EDIT_TITLE, SETTINGS_EDIT_SUCCESS_MSG, SETTINGS_EDIT_SUCCESS_BTNS, SETTINGS_UPLOAD_LOGO = range(8, 14)

# Settings File
def get_settings_file(username=None):
    if username:
        return f'data/bot_settings_{username}.json'
    return 'data/bot_settings.json'

def load_bot_settings(username=None):
    filepath = get_settings_file(username)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except: pass
    return {
        "welcome_message": "Halo! Selamat datang.", 
        "guest_access": True,
        "dashboard_title": "ℹ️ Dashboard User",
        "payment_success_message": "✅ Pembayaran Berhasil! Terima kasih.",
        "payment_success_buttons": [],
        "use_qris_logo": False,
        "qris_logo_path": None
    }

def save_bot_settings(settings, username=None):
    filepath = get_settings_file(username)
    with open(filepath, 'w') as f:
        json.dump(settings, f, indent=4)

# NUCLEAR OPTION: Force disable SSL verification globally
def create_insecure_ssl_context(*args, **kwargs):
    context = ssl._create_unverified_context(*args, **kwargs)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context

try:
    ssl._create_default_https_context = create_insecure_ssl_context
    ssl.create_default_context = create_insecure_ssl_context
except AttributeError:
    pass

def is_admin_user(user_id, context) -> bool:
    admin_id = context.bot_data.get('admin_id')
    owner_id = os.getenv('OWNER_ID')
    return str(user_id) == str(admin_id) or str(user_id) == str(owner_id)

async def check_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    # Legacy check, now mostly used to protect Admin-only actions
    if not is_admin_user(update.effective_user.id, context):
        await update.message.reply_text("⛔ Anda tidak memiliki akses admin.")
        return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    wd_bot = context.bot_data['wd_bot']
    
    if is_admin_user(user.id, context):
        # ADMIN VIEW
        welcome_text = (
            f"👋 Halo Admin, {user.first_name}!\n"
            f"Selamat datang di **WDBot Dashboard**.\n"
            f"Bot ini terhubung dengan User: `{wd_bot.current_username}`\n\n"
            f"Status: `{wd_bot.current_username if wd_bot.current_username else 'Belum Login'}`"
        )
        is_owner = str(user.id) == os.getenv('OWNER_ID')
        is_admin = True
        await update.message.reply_text(
            text=welcome_text,
            reply_markup=main_menu_keyboard(is_owner, is_admin),
            parse_mode='Markdown'
        )
    else:
        # GUEST/REGULAR USER VIEW
        settings = load_bot_settings(wd_bot.current_username)
        if not settings.get('guest_access', True):
            await update.message.reply_text("⛔ Maaf, bot sedang dalam mode maintenance/private.")
            return

        welcome_msg = settings.get('welcome_message', "Halo! Selamat datang.")
        dashboard_title = settings.get('dashboard_title', "ℹ️ Dashboard User")
        
        text = (
            f"<b>{dashboard_title}</b>\n\n"
            f"{welcome_msg}\n\n"
            f"🟢 Status Bot: <b>Online</b>\n\n"
            f"Silakan pilih menu di bawah:"
        )
        
        keyboard = [
            [InlineKeyboardButton("💰 Pembayaran (QRIS)", callback_data='menu_deposit')],
            [InlineKeyboardButton("🔄 Refresh", callback_data='guest_dashboard')]
        ]
        
        await update.message.reply_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

def main_menu_keyboard(is_owner=False, is_admin=False):
    keyboard = [
        [InlineKeyboardButton("📊 Analisis / User Info", callback_data='menu_analysis')],
        [InlineKeyboardButton("💰 Pembayaran (QRIS)", callback_data='menu_deposit')],
    ]
    
    if is_owner:
        keyboard.append([InlineKeyboardButton("🌐 Browser Sniffing (Server Side)", callback_data='menu_sniffing')])
        keyboard.append([InlineKeyboardButton("👥 Kelola Users", callback_data='menu_manage_users')])
        
    if is_owner or is_admin:
        keyboard.append([InlineKeyboardButton("⚙️ Pengaturan Bot", callback_data='menu_settings')])
        
    keyboard.append([InlineKeyboardButton("🧾 Riwayat Transaksi", callback_data='menu_history')])
    keyboard.append([InlineKeyboardButton("♻️ Refresh Token", callback_data='action_refresh')])
    
    return InlineKeyboardMarkup(keyboard)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    is_admin = is_admin_user(user_id, context)
    data = query.data

    # PUBLIC/GUEST ACTIONS
    if data == 'menu_deposit':
        # Start deposit conversation explicitly or handle it via ConversationHandler entry point?
        # ConversationHandler captures it if it matches the pattern.
        # But here we are in button_handler which is a fallback or parallel?
        # The ConversationHandler has higher priority usually if added before.
        # Check main setup: application.add_handler(conv_deposit) is BEFORE button_handler.
        # So 'menu_deposit' should be caught by conv_deposit IF it matches.
        # However, button_handler is also a CallbackQueryHandler.
        # If conv_deposit is not active, it might fall through?
        # Actually, conv_deposit entry point IS a CallbackQueryHandler(pattern='^menu_deposit$').
        # So this line here is actually redundant if the ConversationHandler catches it.
        # BUT, if the user is NOT in conversation, the EntryPoint should catch it.
        # Let's leave it, but we need to ensure guests can use it.
        pass 
    elif data == 'guest_dashboard':
        await show_guest_dashboard(query, context)
        return
    elif data.startswith('cancel_deposit_'):
        # Allow guests to cancel their own deposits?
        # Current logic doesn't check ownership of order, but it's ephemeral.
        pass

    # PROTECTED ACTIONS (Admin Only)
    if not is_admin and data not in ['menu_deposit', 'guest_dashboard'] and not data.startswith('cancel_deposit_'):
        await query.message.reply_text("⛔ Akses ditolak.")
        return

    wd_bot = context.bot_data['wd_bot'] # Just to ensure it's available if needed

    if data == 'menu_main':
        if is_admin:
            await show_main_menu(query, context)
        else:
            # Show Guest Menu again
            await start(update, context)
    elif data == 'menu_analysis':
        await show_analysis(query, context)
    elif data == 'menu_history':
        await show_history(query, context)
    elif data == 'menu_sniffing':
        await perform_sniffing(query, context)
    elif data == 'action_refresh':
        await perform_refresh(query, context)
    elif data == 'menu_settings':
        await show_bot_settings(query, context)
    elif data == 'toggle_guest':
        await toggle_guest_access(query, context)
    elif data == 'toggle_logo':
        await toggle_qris_logo(query, context)
    elif data.startswith('cancel_deposit_'):
        order_id = data.replace('cancel_deposit_', '')
        active_deposits = context.bot_data.get('active_deposits', set())
        active_deposits.discard(order_id)
        # Update status to Cancelled in history
        update_transaction_status(wd_bot.current_username, order_id, "Cancelled")
        
        await show_guest_dashboard(query, context)

# --- History Helper Functions ---
def get_history_file(username):
    return f'data/history_{username}.json'

def load_history(username):
    file_path = get_history_file(username)
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return []
    return []

def save_history(username, history):
    file_path = get_history_file(username)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=4)

def add_transaction(username, transaction):
    history = load_history(username)
    # Check if exists (idempotency)
    for item in history:
        if item.get('order_id') == transaction.get('order_id'):
            return
    history.insert(0, transaction) # Add to top
    save_history(username, history)

def update_transaction_status(username, order_id, status, payment_time=None):
    history = load_history(username)
    updated = False
    for item in history:
        if item.get('order_id') == order_id:
            item['status'] = status
            if payment_time:
                item['payment_time'] = payment_time
            updated = True
            break
    if updated:
        save_history(username, history)

async def show_main_menu(query, context):
    wd_bot = context.bot_data['wd_bot']
    
    # Fetch Wallet (Quick Check)
    wallet_info = None
    if wd_bot.token and not wd_bot.is_token_expired(wd_bot.token):
        # Only fetch if token seems valid to avoid delays/errors
        # We can run this in thread if it's slow, but it's just one GET
        try:
            wallet_info = await asyncio.to_thread(wd_bot.get_wallet_info)
        except: pass
        
    wallet_str = "Rp -"
    if wallet_info:
        wallet_str = f"Rp {wallet_info['total']:,.0f}"
    elif not wd_bot.token:
        wallet_str = "(Belum Login)"
    
    # Active Deposits
    active_deposits = context.bot_data.get('active_deposits', set())
    
    text = (
        f"🏠 **Dashboard Utama**\n\n"
        f"User Aktif: `{wd_bot.current_username}`\n"
        f"💰 Saldo: `{wallet_str}`\n"
        f"⏳ Deposit Pending: `{len(active_deposits)}`\n"
    )
    
    user_id = query.from_user.id
    is_owner = str(user_id) == os.getenv('OWNER_ID')
    is_admin = is_admin_user(user_id, context)
    
    await query.edit_message_text(text=text, reply_markup=main_menu_keyboard(is_owner, is_admin), parse_mode='Markdown')

async def show_analysis(query, context):
    wd_bot = context.bot_data['wd_bot']
    await query.edit_message_text("⏳ Sedang mengambil data...", parse_mode='Markdown')
    
    if not wd_bot.ensure_logged_in():
        await query.edit_message_text(
            "⚠️ **Gagal Login / Token Expired**.\nSilakan refresh token atau cek koneksi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data='menu_main')]]),
            parse_mode='Markdown'
        )
        return

    report = f"📊 **Laporan Analisis**\n"
    report += f"User: `{wd_bot.current_username}`\n\n"
    
    # --- 1. Fetch Live Base Info (Real Name & Bank) ---
    real_name = '-'
    bank_info_str = ""
    try:
        url_base = "https://wdbos.com/auth/commonpay/pay/common/getPlayerBaseInfo?l=id"
        resp_base = wd_bot.session.get(url_base, headers=wd_bot.api_headers)
        if resp_base.status_code == 200:
            data_base = resp_base.json()
            if data_base.get('success'):
                res_base = data_base.get('result', {})
                attach_list = res_base.get('attachInfoList', [])
                
                # Get Real Name
                if attach_list:
                    for item in attach_list:
                        if item.get('realName'):
                            real_name = item.get('realName')
                            break
                
                # Get Bank Info
                if attach_list:
                    bank_info_str += f"🏦 **Info Bank Penarikan**:\n"
                    for bank in attach_list:
                        bank_info_str += f"- Bank: {bank.get('bankName')}\n"
                        bank_info_str += f"- Code: `{bank.get('bankCode')}`\n\n"
                else:
                    bank_info_str += f"⚠️ Belum ada data bank tersimpan.\n\n"
    except Exception as e:
        bank_info_str += f"⚠️ Gagal fetch base info: {e}\n\n"

    # --- 2. Profile Info ---
    report += f"👤 **Info Profil User**:\n"
    
    # Prioritize user-specific profile file
    # Default path (should be avoided if possible in multi-user context)
    profile_path = 'data/current_profile.json'
    
    if wd_bot.current_username:
        user_profile = f'data/profile_{wd_bot.current_username}.json'
        if os.path.exists(user_profile):
            profile_path = user_profile
        else:
            # Auto-heal: Try to login silently to fetch profile if missing
            try:
                user_creds = wd_bot.get_user_by_username(wd_bot.current_username)
                if user_creds and user_creds.get('password'):
                    # Perform login to sync data
                    if wd_bot.login_api(wd_bot.current_username, user_creds.get('password')):
                        if os.path.exists(user_profile):
                            profile_path = user_profile
            except Exception as e:
                print(f"[!] Auto-heal profile failed: {e}")
            
            if not profile_path:
                profile_path = None

    if profile_path and os.path.exists(profile_path):
        try:
            with open(profile_path, 'r') as f:
                pInfo = json.load(f)
            
            # Double check (paranoia check) - though pInfo usually doesn't have username
            report += f"Nick     : `{pInfo.get('nickName')}`\n"
            report += f"Full Name: `{real_name}`\n"
            report += f"Email    : `{pInfo.get('mailAddress')}`\n"
            report += f"Mobile   : `{pInfo.get('mobile')}`\n"
            report += f"Currency : {pInfo.get('currencyCode')} ({pInfo.get('icon')})\n"
        except: 
            report += "⚠️ Gagal baca data profile lokal.\n"
    else:
        report += "⚠️ Data profile belum tersimpan (Coba Refresh Token/Login).\n"

    # Token Expiry
    if wd_bot.token:
        jwt_data = wd_bot.parse_jwt(wd_bot.token)
        if jwt_data and 'exp' in jwt_data:
            dt = datetime.datetime.fromtimestamp(jwt_data['exp'])
            report += f"Token Exp: {dt}\n"
    
    report += "\n"

    # --- 3. Wallet Info ---
    try:
        url = "https://wdbos.com/auth/playerInfo/getWalletInfo?l=id"
        resp = wd_bot.session.get(url, headers=wd_bot.api_headers)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                res = data.get('result', {})
                money = float(res.get('money', 0))
                reward = float(res.get('rewardMoney', 0))
                report += f"💰 **Wallet**:\n"
                report += f"- Saldo: `{money + reward:,.0f}`\n\n"
            else:
                report += f"⚠️ Gagal fetch wallet: {data.get('message')}\n\n"
    except Exception as e:
        report += f"⚠️ Error Wallet: {e}\n\n"

    # Append Bank Info
    report += bank_info_str

    await query.edit_message_text(
        text=report,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data='menu_main')]]),
        parse_mode='Markdown'
    )

async def perform_sniffing(query, context):
    wd_bot = context.bot_data['wd_bot']
    await query.edit_message_text("🌐 Membuka browser di server... Cek terminal/layar server.")
    
    if wd_bot.start_browser():
        await query.message.reply_text("✅ Browser terbuka. Lakukan login manual di browser server, lalu klik Refresh Token di sini.")
    else:
        await query.message.reply_text("❌ Gagal membuka browser.")
            
    await show_main_menu(query, context)

async def show_history(query, context):
    wd_bot = context.bot_data['wd_bot']
    await query.edit_message_text("⏳ Mengambil riwayat transaksi...", parse_mode='Markdown')
    
    if not wd_bot.ensure_logged_in():
        await query.edit_message_text(
            "⚠️ **Gagal Login / Token Expired**.\nSilakan refresh token.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data='menu_main')]]),
            parse_mode='Markdown'
        )
        return

    history_text = "🧾 **Riwayat Transaksi (Lokal)**\n\n"
    
    try:
        # Load from Local File
        orders = load_history(wd_bot.current_username)

        if orders:
            # Show max 10 latest
            for order in orders[:10]:
                status_raw = order.get('status', 'Unknown')
                
                status_icon = "❓"
                if status_raw == "Success": status_icon = "✅"
                elif status_raw == "Pending": status_icon = "⏳"
                elif status_raw == "Failed" or status_raw == "Cancelled" or status_raw == "Expired": status_icon = "❌"
                
                amount = float(order.get('amount', 0))
                order_id = order.get('order_id')
                time_str = order.get('create_time', '-')
                payment_time = order.get('payment_time', '-')
                
                history_text += f"🆔 `{order_id}`\n"
                history_text += f"💰 Rp {amount:,.0f}\n"
                history_text += f"📅 {time_str}\n"
                history_text += f"Stat: {status_icon} {status_raw}\n"
                if payment_time and payment_time != "-":
                    history_text += f"Paid: {payment_time}\n"
                history_text += "-------------------\n"
        else:
            history_text += "⚠️ Tidak ada data transaksi tersimpan.\n"
             
    except Exception as e:
        history_text += f"⚠️ Error: {str(e)}\n"

    await query.edit_message_text(
        text=history_text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data='menu_main')]]),
        parse_mode='Markdown'
    )

async def perform_refresh(query, context):
    wd_bot = context.bot_data['wd_bot']
    await query.edit_message_text("🔄 Mencoba refresh session/token...")
    
    if wd_bot.is_browser_alive():
        wd_bot.sync_cookies()
        await query.edit_message_text(
            "✅ Cookies disinkronisasi. Coba cek Info User.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data='menu_main')]])
        )
    else:
        if wd_bot.ensure_logged_in():
            await query.edit_message_text(
                "✅ Token valid/refreshed via API.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data='menu_main')]])
            )
        else:
            await query.edit_message_text(
                "❌ Gagal refresh. Browser tertutup dan auto-login gagal.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu Utama", callback_data='menu_main')]])
            )

# --- Settings & Guest Handlers ---

async def show_guest_dashboard(query, context):
    wd_bot = context.bot_data['wd_bot']
    settings = load_bot_settings(wd_bot.current_username)
    welcome_msg = settings.get('welcome_message', "Halo! Selamat datang.")
    dashboard_title = settings.get('dashboard_title', "ℹ️ Dashboard User")
    
    text = (
        f"<b>{dashboard_title}</b>\n\n"
        f"{welcome_msg}\n\n"
        f"🟢 Status Bot: <b>Online</b>\n\n"
        f"Silakan pilih menu di bawah:"
    )
    
    keyboard = [
        [InlineKeyboardButton("💰 Pembayaran (QRIS)", callback_data='menu_deposit')],
        [InlineKeyboardButton("🔄 Refresh", callback_data='guest_dashboard')]
    ]
    
    if query.message.photo:
        try:
            await query.message.delete()
        except: pass
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    else:
        try:
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        except BadRequest as e:
            if "Message is not modified" in str(e):
                pass
            else:
                raise e

async def show_bot_settings(query, context):
    wd_bot = context.bot_data['wd_bot']
    settings = load_bot_settings(wd_bot.current_username)
    guest_access = settings.get('guest_access', True)
    welcome_msg = settings.get('welcome_message', '-')
    dashboard_title = settings.get('dashboard_title', 'ℹ️ Dashboard User')
    
    dashboard_title = settings.get('dashboard_title', 'ℹ️ Dashboard User')
    use_logo = settings.get('use_qris_logo', False)
    logo_status = "✅" if use_logo else "❌"
    
    status_icon = "✅" if guest_access else "❌"
    
    text = (
        f"⚙️ **Pengaturan Bot**\n"
        f"User: `{wd_bot.current_username}`\n\n"
        f"Status Publik: {status_icon} {'Aktif' if guest_access else 'Non-Aktif'}\n"
        f"Logo QRIS: {logo_status} {'Aktif' if use_logo else 'Non-Aktif'}\n"
        f"Judul Dashboard:\n`{dashboard_title}`\n"
        f"Pesan Sambutan:\n`{welcome_msg}`\n"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"{'🔴 Matikan' if guest_access else '🟢 Hidupkan'} Akses Publik", callback_data='toggle_guest')],
        [InlineKeyboardButton(f"{'🔴 Matikan' if use_logo else '🟢 Hidupkan'} Logo QRIS", callback_data='toggle_logo')],
        [InlineKeyboardButton("🖼️ Upload Logo QRIS", callback_data='upload_logo')],
        [InlineKeyboardButton("✏️ Ubah Judul Dashboard", callback_data='edit_title')],
        [InlineKeyboardButton("✏️ Ubah Pesan Sambutan", callback_data='edit_welcome')],
        [InlineKeyboardButton("✏️ Ubah Pesan Sukses Bayar", callback_data='edit_success_msg')],
        [InlineKeyboardButton("🔘 Ubah Tombol Sukses Bayar", callback_data='edit_success_btns')],
        [InlineKeyboardButton("🔙 Kembali", callback_data='menu_main')]
    ]
    
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def toggle_guest_access(query, context):
    wd_bot = context.bot_data['wd_bot']
    settings = load_bot_settings(wd_bot.current_username)
    settings['guest_access'] = not settings.get('guest_access', True)
    save_bot_settings(settings, wd_bot.current_username)
    
    await show_bot_settings(query, context)

async def toggle_qris_logo(query, context):
    wd_bot = context.bot_data['wd_bot']
    settings = load_bot_settings(wd_bot.current_username)
    settings['use_qris_logo'] = not settings.get('use_qris_logo', False)
    save_bot_settings(settings, wd_bot.current_username)
    
    await show_bot_settings(query, context)

async def settings_welcome_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    helper_text = (
        "ℹ️ **Panduan Format HTML:**\n"
        "• <b>Bold</b>: `<b>text</b>`\n"
        "• <i>Italic</i>: `<i>text</i>`\n"
        "• <u>Underline</u>: `<u>text</u>`\n"
        "• <s>Strike</s>: `<s>text</s>`\n"
        "• Link: `<a href='url'>text</a>`\n"
        "• Code: `<code>text</code>`\n"
        "• Quote: `<blockquote>text</blockquote>`"
    )
    
    keyboard = [[InlineKeyboardButton("❌ Batalkan", callback_data='cancel_settings')]]
    
    await query.edit_message_text(
        f"📝 **Ubah Pesan Sambutan**\n\nSilakan kirim pesan baru (Support HTML).\n\n{helper_text}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SETTINGS_EDIT_WELCOME

async def settings_welcome_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    wd_bot = context.bot_data['wd_bot']
    
    settings = load_bot_settings(wd_bot.current_username)
    settings['welcome_message'] = text
    save_bot_settings(settings, wd_bot.current_username)
    
    await update.message.reply_text("✅ Pesan sambutan berhasil disimpan!")
    
    # Return to settings menu
    keyboard = [[InlineKeyboardButton("🔙 Kembali ke Pengaturan", callback_data='menu_settings')]]
    await update.message.reply_text("Klik tombol di bawah untuk kembali.", reply_markup=InlineKeyboardMarkup(keyboard))
    
    return ConversationHandler.END

async def settings_title_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    helper_text = (
        "ℹ️ **Panduan Format HTML:**\n"
        "• <b>Bold</b>: `<b>text</b>`\n"
        "• <i>Italic</i>: `<i>text</i>`\n"
        "• <u>Underline</u>: `<u>text</u>`\n"
        "• <s>Strike</s>: `<s>text</s>`\n"
        "• Code: `<code>text</code>`"
    )
    
    keyboard = [[InlineKeyboardButton("❌ Batalkan", callback_data='cancel_settings')]]
    
    await query.edit_message_text(
        f"📝 **Ubah Judul Dashboard**\n\nSilakan kirim judul baru (Support HTML).\n\n{helper_text}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SETTINGS_EDIT_TITLE

async def settings_title_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    wd_bot = context.bot_data['wd_bot']
    
    settings = load_bot_settings(wd_bot.current_username)
    settings['dashboard_title'] = text
    save_bot_settings(settings, wd_bot.current_username)
    
    await update.message.reply_text("✅ Judul Dashboard berhasil disimpan!")
    
    # Return to settings menu
    keyboard = [[InlineKeyboardButton("🔙 Kembali ke Pengaturan", callback_data='menu_settings')]]
    await update.message.reply_text("Klik tombol di bawah untuk kembali.", reply_markup=InlineKeyboardMarkup(keyboard))
    
    return ConversationHandler.END

async def settings_success_msg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    helper_text = (
        "ℹ️ **Panduan Format HTML:**\n"
        "• <b>Bold</b>: `<b>text</b>`\n"
        "• <i>Italic</i>: `<i>text</i>`\n"
        "• Code: `<code>text</code>`"
    )
    
    keyboard = [[InlineKeyboardButton("❌ Batalkan", callback_data='cancel_settings')]]
    
    await query.edit_message_text(
        f"📝 **Ubah Pesan Sukses Pembayaran**\n\nSilakan kirim pesan baru (Support HTML).\n\n{helper_text}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SETTINGS_EDIT_SUCCESS_MSG

async def settings_success_msg_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    wd_bot = context.bot_data['wd_bot']
    
    settings = load_bot_settings(wd_bot.current_username)
    settings['payment_success_message'] = text
    save_bot_settings(settings, wd_bot.current_username)
    
    await update.message.reply_text("✅ Pesan sukses pembayaran berhasil disimpan!")
    
    keyboard = [[InlineKeyboardButton("🔙 Kembali ke Pengaturan", callback_data='menu_settings')]]
    await update.message.reply_text("Klik tombol di bawah untuk kembali.", reply_markup=InlineKeyboardMarkup(keyboard))
    
    return ConversationHandler.END

async def settings_success_btns_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("❌ Batalkan", callback_data='cancel_settings')]]
    
    await query.edit_message_text(
        "🔘 **Ubah Tombol Sukses Pembayaran**\n\n"
        "Silakan kirim daftar tombol dengan format:\n"
        "`Label Tombol | URL`\n\n"
        "Contoh untuk 2 tombol:\n"
        "`Website Utama | https://example.com`\n"
        "`Hubungi Admin | https://t.me/admin`\n\n"
        "Ketik `RESET` untuk menghapus semua tombol tambahan.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SETTINGS_EDIT_SUCCESS_BTNS

async def settings_success_btns_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    wd_bot = context.bot_data['wd_bot']
    
    buttons = []
    if text.strip().upper() != 'RESET':
        lines = text.split('\n')
        for line in lines:
            parts = line.split('|')
            if len(parts) >= 2:
                label = parts[0].strip()
                url = parts[1].strip()
                if label and url:
                    buttons.append({"label": label, "url": url})
    
    settings = load_bot_settings(wd_bot.current_username)
    settings['payment_success_buttons'] = buttons
    save_bot_settings(settings, wd_bot.current_username)
    
    count = len(buttons)
    await update.message.reply_text(f"✅ Berhasil menyimpan {count} tombol tambahan!")
    
    keyboard = [[InlineKeyboardButton("🔙 Kembali ke Pengaturan", callback_data='menu_settings')]]
    await update.message.reply_text("Klik tombol di bawah untuk kembali.", reply_markup=InlineKeyboardMarkup(keyboard))
    
    return ConversationHandler.END

async def settings_upload_logo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [[InlineKeyboardButton("❌ Batalkan", callback_data='cancel_upload')]]
    
    await query.edit_message_text(
        "🖼️ **Upload Logo QRIS**\n\nSilakan kirim file gambar (PNG/JPG) yang akan digunakan sebagai logo QRIS.\nPastikan gambar berbentuk persegi agar hasil maksimal.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return SETTINGS_UPLOAD_LOGO

async def settings_generic_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_bot_settings(query, context)
    return ConversationHandler.END

async def settings_upload_logo_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    wd_bot = context.bot_data['wd_bot']
    file_obj = None
    
    # Handle Photo (Compressed) or Document (File)
    if update.message.photo:
        file_obj = update.message.photo[-1] # Largest size
    elif update.message.document:
        file_obj = update.message.document
        # Double check mime type
        if not (file_obj.mime_type and file_obj.mime_type.startswith('image/')):
             await update.message.reply_text("⚠️ File harus berupa gambar (PNG/JPG).")
             return SETTINGS_UPLOAD_LOGO

    if not file_obj:
        await update.message.reply_text("⚠️ Gagal mendeteksi gambar. Silakan coba lagi.")
        return SETTINGS_UPLOAD_LOGO
    
    try:
        new_file = await context.bot.get_file(file_obj.file_id)
        
        # Setup path: assets/{username}/logo.png
        assets_dir = f"assets/{wd_bot.current_username}"
        if not os.path.exists(assets_dir):
            os.makedirs(assets_dir, exist_ok=True)
        
        logo_path = f"{assets_dir}/logo.png"
        await new_file.download_to_drive(logo_path)
        
        # Update settings
        settings = load_bot_settings(wd_bot.current_username)
        settings['qris_logo_path'] = logo_path
        settings['use_qris_logo'] = True # Auto-enable on upload
        save_bot_settings(settings, wd_bot.current_username)
        
        await update.message.reply_text("✅ Logo QRIS berhasil diupload dan diaktifkan!")
        
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke Pengaturan", callback_data='menu_settings')]]
        await update.message.reply_text("Klik tombol di bawah untuk kembali.", reply_markup=InlineKeyboardMarkup(keyboard))
        
        return ConversationHandler.END
        
    except Exception as e:
        print(f"[!] Upload Error: {e}")
        await update.message.reply_text(f"❌ Terjadi kesalahan saat upload: {str(e)}")
        
        keyboard = [[InlineKeyboardButton("🔙 Kembali ke Pengaturan", callback_data='menu_settings')]]
        await update.message.reply_text("Silakan coba lagi atau kembali.", reply_markup=InlineKeyboardMarkup(keyboard))
        return ConversationHandler.END

# --- Deposit Conversation ---
async def deposit_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await show_guest_dashboard(query, context)
    return ConversationHandler.END

async def deposit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    wd_bot = context.bot_data['wd_bot']
    if not wd_bot.ensure_logged_in():
        await query.edit_message_text(
            "⚠️ **Layanan Sedang Offline**.\nAdmin belum mengaktifkan sesi pembayaran.\nSilakan hubungi admin.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data='menu_main')]]),
            parse_mode='Markdown'
        )
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton("❌ Batalkan", callback_data='cancel_deposit_input')]]
    msg_prompt = await query.edit_message_text(
        "💰 **Menu Pembayaran**\nMasukkan jumlah pembayaran (Min. 10.000).\nContoh: `50000`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    context.user_data['deposit_prompt_msg_id'] = msg_prompt.message_id
    return DEPOSIT_NOMINAL

async def deposit_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    try:
        nominal = int(text)
        if nominal < 10000:
            await update.message.reply_text("⚠️ Minimal pembayaran adalah Rp 10.000. Silakan input ulang.")
            return DEPOSIT_NOMINAL
    except ValueError:
        await update.message.reply_text("⚠️ Nominal harus angka. Silakan input ulang.")
        return DEPOSIT_NOMINAL

    # Cleanup: Delete user input and prompt message
    try:
        await update.message.delete()
    except: pass

    if 'deposit_prompt_msg_id' in context.user_data:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id, 
                message_id=context.user_data['deposit_prompt_msg_id']
            )
        except: pass
        del context.user_data['deposit_prompt_msg_id']

    msg = await update.message.reply_text("⏳ Memproses permintaan pembayaran...")
    wd_bot = context.bot_data['wd_bot']

    # 1. Check QRIS Type (Simplified)
    qris_type = "P2M"
    try:
        url_active = "https://wdbos.com/auth/commonpay/ida/common/getQrisActive?l=id"
        resp = wd_bot.session.get(url_active, headers=wd_bot.api_headers)
        if resp.status_code == 200:
            d = resp.json()
            if d.get('success') and d.get('result'):
                qris_type = d.get('result')
    except: pass

    # 2. Request Deposit
    url_deposit = "https://wdbos.com/auth/commonpay/ida/common/getYukkQris?l=id"
    payload = {"nominal": nominal, "qrisType": qris_type}
    
    try:
        resp = wd_bot.session.post(url_deposit, json=payload, headers=wd_bot.api_headers)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                res = data.get('result', {}).get('result', {})
                qris_string = res.get('qris_string')
                order_id = res.get('order_id')
                
                if not qris_string:
                    await msg.edit_text("❌ Gagal mendapatkan QRIS String.")
                    return ConversationHandler.END

                # Generate QR Image
                qr = qrcode.QRCode(box_size=10, border=4, error_correction=qrcode.constants.ERROR_CORRECT_H)
                qr.add_data(qris_string)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
                
                # Check for Logo
                settings = load_bot_settings(wd_bot.current_username)
                if settings.get('use_qris_logo') and settings.get('qris_logo_path'):
                    logo_path = settings.get('qris_logo_path')
                    if os.path.exists(logo_path):
                        try:
                            logo = Image.open(logo_path)
                            
                            # Calculate dimensions
                            width, height = img.size
                            logo_size = int(width / 4) # Logo is 25% of QR size
                            
                            # Resize logo
                            logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)
                            
                            # Calculate position
                            pos = ((width - logo_size) // 2, (height - logo_size) // 2)
                            
                            # Paste logo
                            img.paste(logo, pos)
                        except Exception as e:
                            print(f"[!] Failed to embed logo: {e}")

                bio = io.BytesIO()
                img.save(bio, 'PNG')
                bio.seek(0)
                
                await msg.delete()
                
                # Add to active deposits
                if 'active_deposits' not in context.bot_data:
                    context.bot_data['active_deposits'] = set()
                context.bot_data['active_deposits'].add(order_id)
                
                # Save to Local History
                now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                transaction = {
                    "order_id": order_id,
                    "amount": nominal,
                    "status": "Pending",
                    "create_time": now_str,
                    "payment_time": "-"
                }
                add_transaction(wd_bot.current_username, transaction)
                
                cancel_kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("❌ Batalkan Pembayaran", callback_data=f"cancel_deposit_{order_id}")]
                ])

                qris_msg = await update.message.reply_photo(
                    photo=bio,
                    caption=(
                        f"✅ **Pembayaran Dibuat!**\n"
                        f"Nominal: `Rp {nominal:,}`\n"
                        f"Order ID: `{order_id}`\n\n"
                        f"⏳ Menunggu pembayaran... (Bot akan cek otomatis selama 300s)"
                    ),
                    reply_markup=cancel_kb,
                    parse_mode='Markdown'
                )
                
                # Start Polling Task
                context.application.create_task(
                    poll_deposit_status(update.effective_chat.id, order_id, context, qris_msg.message_id, nominal)
                )
                
                return ConversationHandler.END
            else:
                await msg.edit_text(f"❌ API Error: {data.get('message')}")
        else:
            await msg.edit_text(f"❌ HTTP Error: {resp.status_code}")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")

    return ConversationHandler.END

async def poll_deposit_status(chat_id, order_id, context, message_id, nominal=0):
    timeout = 300
    start_time = time.time()
    wd_bot = context.bot_data['wd_bot']
    active_deposits = context.bot_data.get('active_deposits', set())
    
    while (time.time() - start_time) < timeout:
        if order_id not in active_deposits:
            return

        try:
            url = f"https://wdbos.com/auth/commonpay/ida/common/queryOrderIsPayment?l=id&orderId={order_id}"
            resp = await asyncio.to_thread(wd_bot.session.get, url, headers=wd_bot.api_headers)
            
            # Check for Session Expiry / Auth Failure
            if resp.status_code == 401 or (resp.status_code == 200 and not resp.json().get('success') and 'login' in str(resp.json().get('message', '')).lower()):
                print(f"[!] Polling: Session expired for {order_id}. Re-logging...")
                
                # Force re-login attempt
                creds = wd_bot.get_user_by_username(wd_bot.current_username)
                if creds:
                    await asyncio.to_thread(wd_bot.login_api, creds['username'], creds['password'])
                    # Retry request
                    resp = await asyncio.to_thread(wd_bot.session.get, url, headers=wd_bot.api_headers)

            if resp.status_code == 200:
                d = resp.json()
                res = d.get('result', {})
                if res.get('orderStatus') != 0: # 0 is pending
                    active_deposits.discard(order_id)
                    try:
                        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                    except: pass
                    
                    status_text = "SUKSES" if res.get('orderStatus') == 1 else "GAGAL"
                    
                    # Update Local History
                    payment_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Default to now if not provided
                    if res.get('paymentTime'):
                         # Try to format paymentTime if needed, assuming it comes as a string or timestamp
                         payment_time_str = str(res.get('paymentTime'))
                    
                    update_transaction_status(wd_bot.current_username, order_id, "Success" if res.get('orderStatus') == 1 else "Failed", payment_time_str)
                    
                    if res.get('orderStatus') == 1:
                        # Success Logic with Custom Message and Buttons
                        settings = load_bot_settings(wd_bot.current_username)
                        success_msg_template = settings.get('payment_success_message', "✅ Pembayaran Berhasil! Terima kasih.")
                        success_buttons = settings.get('payment_success_buttons', [])
                        
                        # Prepare buttons
                        kb_list = []
                        if success_buttons:
                            for btn in success_buttons:
                                kb_list.append([InlineKeyboardButton(btn['label'], url=btn['url'])])
                        
                        # Fallback or default buttons if needed, or just allow empty
                        # Always adding a 'Close' or 'Menu' button might be good practice, but user wants custom.
                        # We'll add a 'Menu Utama' button at the bottom just in case.
                        kb_list.append([InlineKeyboardButton("🏠 Menu Utama", callback_data='menu_main')])
                        
                        # Format message (simple replacement if user wants dynamic vars later, for now just append info)
                        # We can allow {nominal}, {order_id}, {time} placeholders in future.
                        # For now, let's just append the details below the custom message.
                        
                        final_text = (
                            f"{success_msg_template}\n\n"
                            f"💰 Nominal: `Rp {nominal:,}`\n"
                            f"📅 Waktu: `{payment_time_str}`\n"
                            f"🆔 Order ID: `{order_id}`"
                        )

                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=final_text,
                            reply_markup=InlineKeyboardMarkup(kb_list),
                            parse_mode='HTML' # Switch to HTML to support custom tags in success message
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"❌ **Pembayaran Gagal/Kadaluarsa**\nOrder `{order_id}` status: {status_text}",
                            parse_mode='Markdown'
                        )
                    return
            await asyncio.sleep(5)
        except:
            await asyncio.sleep(5)
            
    # Timeout Handler
    if order_id in active_deposits:
        active_deposits.discard(order_id)
        update_transaction_status(wd_bot.current_username, order_id, "Expired")
        
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except: pass
        
        # Show Dashboard (Manual construction since no query)
        settings = load_bot_settings(wd_bot.current_username)
        welcome_msg = settings.get('welcome_message', "Halo! Selamat datang.")
        dashboard_title = settings.get('dashboard_title', "ℹ️ Dashboard User")
        
        text = (
            f"⚠️ **Waktu Pembayaran Habis**\n"
            f"Order `{order_id}` dibatalkan otomatis.\n\n"
            f"<b>{dashboard_title}</b>\n\n"
            f"{welcome_msg}\n\n"
            f"🟢 Status Bot: <b>Online</b>\n\n"
            f"Silakan pilih menu di bawah:"
        )
        
        keyboard = [
            [InlineKeyboardButton("💰 Pembayaran (QRIS)", callback_data='menu_deposit')],
            [InlineKeyboardButton("🔄 Refresh", callback_data='guest_dashboard')]
        ]
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operasi dibatalkan.")
    return ConversationHandler.END

# --- User Management Conversation ---

async def manage_users_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    wd_bot = context.bot_data['wd_bot']
    users = wd_bot.load_all_credentials()
    
    keyboard = []
    for u in users:
        u_name = u.get('username', 'Unknown')
        # Changed to user_options to show submenu
        keyboard.append([InlineKeyboardButton(f"👤 {u_name}", callback_data=f"user_options_{u_name}")])
        
    keyboard.append([InlineKeyboardButton("➕ Tambah User Baru", callback_data="add_new_user")])
    keyboard.append([InlineKeyboardButton("🔙 Kembali", callback_data="menu_main")])
    
    await query.edit_message_text(
        "👥 **Manajemen User**\nPilih user untuk Aksi (Switch/Edit) atau tambah baru.",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    return MANAGE_ACTION

async def manage_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == 'menu_main':
        await show_main_menu(query, context)
        return ConversationHandler.END
        
    # Initialize context data
    if 'manage_data' not in context.user_data:
        context.user_data['manage_data'] = {}
        
    if data == 'add_new_user':
        await query.edit_message_text("📝 **Tambah User Baru**\n\nMasukkan Username:")
        return MANAGE_USERNAME
    
    # Show Submenu for User
    if data.startswith('user_options_'):
        username = data.replace('user_options_', '')
        keyboard = [
            [InlineKeyboardButton("🚀 Login / Switch to User", callback_data=f"switch_user_{username}")],
            [InlineKeyboardButton("✏️ Edit Credentials", callback_data=f"edit_user_{username}")],
            [InlineKeyboardButton("🔙 Kembali", callback_data="back_to_list")]
        ]
        await query.edit_message_text(
            f"👤 **Opsi User:** `{username}`\nPilih aksi:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return MANAGE_ACTION # Stay in action handler
        
    if data == 'back_to_list':
        # Re-call manage_users_start logic but we need to fake it or just call it?
        # Since we are in ConversationHandler state, we can just call the function logic
        wd_bot = context.bot_data['wd_bot']
        users = wd_bot.load_all_credentials()
        keyboard = []
        for u in users:
            u_name = u.get('username', 'Unknown')
            keyboard.append([InlineKeyboardButton(f"👤 {u_name}", callback_data=f"user_options_{u_name}")])
        keyboard.append([InlineKeyboardButton("➕ Tambah User Baru", callback_data="add_new_user")])
        keyboard.append([InlineKeyboardButton("🔙 Kembali", callback_data="menu_main")])
        
        await query.edit_message_text(
            "👥 **Manajemen User**\nPilih user untuk Aksi (Switch/Edit) atau tambah baru.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        return MANAGE_ACTION

    # SWITCH USER IMPLEMENTATION
    if data.startswith('switch_user_'):
        username = data.replace('switch_user_', '')
        await query.edit_message_text(f"🔄 **Switching to {username}...**\nMohon tunggu sebentar.", parse_mode='Markdown')
        
        # 1. Load Credentials for this user
        wd_bot = context.bot_data['wd_bot'] # Current instance to access loader
        users = wd_bot.load_all_credentials()
        target_user_config = next((u for u in users if u.get('username') == username), None)
        
        if not target_user_config:
            await query.edit_message_text("❌ User tidak ditemukan di konfigurasi.")
            return ConversationHandler.END
            
        # 2. Initialize new WDBot instance
        new_bot = WDBot(username=username)
        
        # 3. Login
        # Try login using saved password if token invalid?
        # Or just use ensure_logged_in() logic which tries token then password.
        # But we need to set the password into the bot instance first for it to work.
        # WDBot doesn't store password in self, it reads from config/credentials inside methods? 
        # Actually main.py: WDBot.login() takes password as arg. WDBot.login_api() takes password.
        # ensure_logged_in calls login_api without args? No, let's check main.py.
        # It seems ensure_logged_in calls self.login_api(password) but where does it get password?
        # It reads from credentials.json inside login_api if not provided?
        # Let's check main.py briefly? 
        # Assumption: WDBot methods handle reading credentials if needed or we pass it.
        
        password = target_user_config.get('password', '')
        
        success = False
        try:
            if new_bot.load_token():
                if new_bot.check_token_valid():
                    success = True
            
            if not success and password:
                if new_bot.login_api(username, password):
                    success = True
                    
        except Exception as e:
            await query.edit_message_text(f"❌ Error saat login: {e}")
            return ConversationHandler.END
            
        if success:
            # 4. Update Context
            context.bot_data['wd_bot'] = new_bot
            context.bot_data['active_deposits'] = set() # Reset deposits cache for new user
            
            # 5. Success Message & Redirect to Main Menu
            await query.edit_message_text(
                f"✅ **Berhasil Switch ke {username}!**\nDashboard sekarang mengontrol akun ini.",
                parse_mode='Markdown'
            )
            await asyncio.sleep(1) # Brief pause
            await show_main_menu(query, context)
            return ConversationHandler.END
        else:
            await query.edit_message_text(
                f"❌ **Gagal Login ke {username}**.\nPastikan password benar atau coba login manual via browser.",
                parse_mode='Markdown'
            )
            return ConversationHandler.END

    if data.startswith('edit_user_'):
        username = data.replace('edit_user_', '')
        context.user_data['manage_data']['username'] = username
        context.user_data['manage_data']['is_edit'] = True
        
        await query.edit_message_text(
            f"📝 **Edit User:** `{username}`\n\nMasukkan Password baru (atau ketik 'skip' untuk tidak mengubah):",
            parse_mode='Markdown'
        )
        return MANAGE_PASSWORD

async def manage_username_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("Username tidak boleh kosong. Silakan input lagi:")
        return MANAGE_USERNAME
        
    context.user_data['manage_data']['username'] = text
    await update.message.reply_text("📝 Masukkan **Password**:")
    return MANAGE_PASSWORD

async def manage_password_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    # If editing, allow skip
    if context.user_data['manage_data'].get('is_edit') and text.lower() == 'skip':
        pass # Keep old password
    else:
        context.user_data['manage_data']['password'] = text
        
    await update.message.reply_text(
        "🤖 Masukkan **Bot Token** (atau ketik 'skip' jika tidak ada perubahan/kosong):",
        parse_mode='Markdown'
    )
    return MANAGE_BOT_TOKEN

async def manage_token_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() != 'skip':
        context.user_data['manage_data']['bot_token'] = text
        
    await update.message.reply_text(
        "🆔 Masukkan **Admin ID** (angka, atau 'skip'):\n_Admin ID diperlukan agar bot hanya bisa diakses oleh Anda._",
        parse_mode='Markdown'
    )
    return MANAGE_ADMIN_ID

# Global registry for running bots
RUNNING_APPS = {}

async def restart_user_bot(username, update_msg_func=None):
    """
    Restarts or starts a bot for a specific user dynamically.
    """
    # 1. Load fresh config
    temp_bot = WDBot() # Temporary instance just to load creds
    user_config = temp_bot.get_user_by_username(username)
    
    if not user_config:
        if update_msg_func: await update_msg_func(f"❌ User {username} tidak ditemukan di config.")
        return

    token = user_config.get('telegram_bot_token')
    
    # 2. Check if running
    if username in RUNNING_APPS:
        old_app = RUNNING_APPS[username]
        # Stop existing
        if update_msg_func: await update_msg_func(f"🔄 Menghentikan bot lama untuk {username}...")
        try:
            await old_app.updater.stop()
            await old_app.stop()
            await old_app.shutdown()
        except Exception as e:
            print(f"Error stopping bot {username}: {e}")
        
        del RUNNING_APPS[username]
        
    if not token:
        if update_msg_func: await update_msg_func(f"⚠️ User {username} tidak memiliki Bot Token. Bot tidak dijalankan.")
        return

    # 3. Start new
    if update_msg_func: await update_msg_func(f"🚀 Memulai bot baru untuk {username}...")
    try:
        app = await run_bot_for_user(user_config)
        if app:
            RUNNING_APPS[username] = app
            if update_msg_func: await update_msg_func(f"✅ Bot untuk {username} BERHASIL dijalankan!")
        else:
            if update_msg_func: await update_msg_func(f"❌ Gagal menjalankan bot untuk {username}. Cek log console.")
    except Exception as e:
        if update_msg_func: await update_msg_func(f"❌ Error starting bot: {e}")


async def manage_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.lower() != 'skip':
        context.user_data['manage_data']['admin_id'] = text
        
    # Save Process
    data = context.user_data['manage_data']
    username = data.get('username')
    password = data.get('password') # Might be None if skipped
    bot_token = data.get('bot_token')
    admin_id = data.get('admin_id')
    
    wd_bot = context.bot_data['wd_bot']
    
    # Helper logic to handle partial updates
    if data.get('is_edit'):
        existing = wd_bot.get_user_by_username(username)
        if existing:
            if not password: password = existing.get('password')
            if not bot_token: bot_token = existing.get('telegram_bot_token')
            if not admin_id: admin_id = existing.get('telegram_admin_id')
            
    # Update/Save
    wd_bot.update_user_credential(username, password, bot_token=bot_token, admin_id=admin_id)
    
    await update.message.reply_text(
        f"✅ **Data User Berhasil Disimpan!**\n\n"
        f"User: `{username}`\n"
        f"Bot Token: `{'Updated' if bot_token else 'No Change/Empty'}`\n"
        f"Admin ID: `{admin_id if admin_id else 'No Change/Empty'}`\n\n"
        "🔄 **Mencoba menjalankan/reload bot...**",
        parse_mode='Markdown'
    )
    
    # Trigger Hot Reload
    async def send_update(msg):
        await update.message.reply_text(msg)
        
    await restart_user_bot(username, update_msg_func=send_update)
    
    # Show main menu again via text message
    user_id = update.effective_user.id
    is_owner = str(user_id) == os.getenv('OWNER_ID')
    
    await update.message.reply_text(
        "Kembali ke menu utama:",
        reply_markup=main_menu_keyboard(is_owner)
    )
    
    return ConversationHandler.END

async def cancel_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Manajemen user dibatalkan.")
    return ConversationHandler.END

# --- Application Factory ---

async def auto_login_loop(wd_bot):
    """
    Background task to ensure the bot stays logged in.
    Runs every 5 minutes.
    """
    while True:
        try:
            # Run blocking ensure_logged_in in a thread to avoid freezing the bot
            # ensure_logged_in handles token expiry check and auto-relogin
            is_valid = await asyncio.to_thread(wd_bot.ensure_logged_in)
            if is_valid:
                # Optional: You could also verify if the token works against the API here
                # but ensure_logged_in is usually enough for expiry.
                pass
            else:
                print(f"[!] Auto-login check failed for {wd_bot.current_username}")
                
        except Exception as e:
            print(f"[!] Auto-login loop error for {wd_bot.current_username}: {e}")
        
        await asyncio.sleep(300) # Check every 5 minutes

async def run_bot_for_user(user_config):
    username = user_config['username']
    token = user_config.get('telegram_bot_token')
    admin_id = user_config.get('telegram_admin_id')
    
    if not token or not admin_id:
        print(f"[!] User {username} tidak memiliki konfigurasi Telegram Bot (token/admin_id). Skipping.")
        return None

    print(f"[*] Starting Bot for User: {username} (Admin ID: {admin_id})")
    
    # Initialize WDBot for this user
    wd_bot = WDBot(username=username)
    # Try to ensure login/session is active
    wd_bot.ensure_logged_in()
    
    # Configure connection timeouts
    request = HTTPXRequest(connect_timeout=60.0, read_timeout=60.0, write_timeout=60.0)

    # Build Application
    application = Application.builder().token(token).request(request).build()
    
    # Inject data
    application.bot_data['wd_bot'] = wd_bot
    application.bot_data['admin_id'] = admin_id
    application.bot_data['active_deposits'] = set()

    # Start Auto-Login Background Task
    application.create_task(auto_login_loop(wd_bot))

    # Handlers
    conv_deposit = ConversationHandler(
        entry_points=[CallbackQueryHandler(deposit_start, pattern='^menu_deposit$')],
        states={
            DEPOSIT_NOMINAL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, deposit_process),
                CallbackQueryHandler(deposit_cancel_callback, pattern='^cancel_deposit_input$')
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    conv_manage = ConversationHandler(
        entry_points=[CallbackQueryHandler(manage_users_start, pattern='^menu_manage_users$')],
        states={
            MANAGE_ACTION: [CallbackQueryHandler(manage_action_handler)],
            MANAGE_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_username_input)],
            MANAGE_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_password_input)],
            MANAGE_BOT_TOKEN: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_token_input)],
            MANAGE_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_admin_input)],
        },
        fallbacks=[CommandHandler('cancel', cancel_manage)]
    )
    
    conv_settings = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(settings_welcome_start, pattern='^edit_welcome$'),
            CallbackQueryHandler(settings_title_start, pattern='^edit_title$'),
            CallbackQueryHandler(settings_success_msg_start, pattern='^edit_success_msg$'),
            CallbackQueryHandler(settings_success_btns_start, pattern='^edit_success_btns$'),
            CallbackQueryHandler(settings_upload_logo_start, pattern='^upload_logo$')
        ],
        states={
            SETTINGS_EDIT_WELCOME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, settings_welcome_input),
                CallbackQueryHandler(settings_generic_cancel, pattern='^cancel_settings$')
            ],
            SETTINGS_EDIT_TITLE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, settings_title_input),
                CallbackQueryHandler(settings_generic_cancel, pattern='^cancel_settings$')
            ],
            SETTINGS_EDIT_SUCCESS_MSG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, settings_success_msg_input),
                CallbackQueryHandler(settings_generic_cancel, pattern='^cancel_settings$')
            ],
            SETTINGS_EDIT_SUCCESS_BTNS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, settings_success_btns_input),
                CallbackQueryHandler(settings_generic_cancel, pattern='^cancel_settings$')
            ],
            SETTINGS_UPLOAD_LOGO: [
                MessageHandler(filters.PHOTO | filters.Document.IMAGE, settings_upload_logo_input),
                CallbackQueryHandler(settings_generic_cancel, pattern='^cancel_upload$')
            ]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_deposit)
    application.add_handler(conv_manage)
    application.add_handler(conv_settings)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Initialize and Start
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    return application

# --- Keep Alive Server for Render ---
from aiohttp import web, ClientSession

async def health_check(request):
    return web.Response(text="Bot is running!")

async def self_ping_loop(app_url):
    """
    Melakukan ping ke diri sendiri setiap 10 menit untuk mencegah tidur.
    """
    print(f"[*] Starting Self-Ping to: {app_url}")
    # Tunggu sebentar agar server up dulu
    await asyncio.sleep(10)
    
    while True:
        try:
            async with ClientSession() as session:
                async with session.get(app_url) as resp:
                    if resp.status == 200:
                        # Log success (optional, maybe too verbose)
                        pass
                    else:
                        print(f"[Ping] Warning: Ping returned status {resp.status}")
        except Exception as e:
            print(f"[Ping] Error pinging {app_url}: {e}")
        
        await asyncio.sleep(600) # 10 menit

async def start_keep_alive_server():
    app = web.Application()
    app.add_routes([web.get('/', health_check), web.get('/health', health_check)])
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    # Render provides PORT via environment variable
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    try:
        await site.start()
        print(f"[*] Keep-alive web server running on port {port}")
        
        # Check APP_URL from Env for Self-Ping
        app_url = os.environ.get("APP_URL")
        if app_url:
            asyncio.create_task(self_ping_loop(app_url))
            
    except Exception as e:
        print(f"[!] Failed to start web server: {e}")

async def main_async():
    # Load users
    creds_path = 'config/credentials.json'
    users = []
    
    if os.path.exists(creds_path):
        try:
            with open(creds_path, 'r') as f:
                data = json.load(f)
            users = data.get('users', [])
        except Exception as e:
            print(f"[!] Warning: Gagal membaca credentials.json: {e}")
    else:
        print("[!] Warning: config/credentials.json tidak ditemukan. Menggunakan environment variables saja.")
    
    # --- AUTO-INJECT FROM .ENV (For Owner) ---
    # If there are users but they don't have bot tokens, let's assume the first user 
    # or the one matching OWNER's expectation should use the env var.
    # OR better: Add a "master" bot if credentials.json is empty or not configured.
    
    env_token = os.getenv('TELEGRAM_BOT_TOKEN')
    env_owner = os.getenv('OWNER_ID')
    
    apps = []
    
    # 1. Try to run bots defined in credentials.json
    for user in users:
        # Check if has config
        if user.get('telegram_bot_token') and user.get('telegram_admin_id'):
            app = await run_bot_for_user(user)
            if app:
                apps.append(app)
                RUNNING_APPS[user['username']] = app
    
    # 2. Fallback / Owner Injection from .env
    # If a user is not running yet (no config in json), try to use .env credentials
    if env_token and env_owner:
        target_user = None
        
        # Priority 1: Look for 'bimanata' if not running
        for u in users:
            if u['username'] == 'bimanata' and u['username'] not in RUNNING_APPS:
                target_user = u
                break
        
        # Priority 2: Look for ANY user not running
        if not target_user:
            for u in users:
                if u['username'] not in RUNNING_APPS:
                    target_user = u
                    break
        
        # If we found a target user that needs a bot
        if target_user:
            print(f"[i] Menggunakan Token & Admin ID dari .env untuk user: {target_user['username']}")
            
            user_config = target_user.copy()
            user_config['telegram_bot_token'] = env_token
            user_config['telegram_admin_id'] = env_owner
            
            app = await run_bot_for_user(user_config)
            if app:
                apps.append(app)
                RUNNING_APPS[target_user['username']] = app

    if not apps:
        print("[!] Warning: Tidak ada bot yang berhasil dijalankan.")
        print("[i] Pastikan telegram_bot_token diisi di config/credentials.json atau .env")
        # Do not return, keep running for web server

    print(f"[*] {len(apps)} Bot Telegram berjalan...")
    print("[i] Menunggu request di background. Tekan CTRL+C untuk stop.")
    
    # Start Keep-Alive Server
    await start_keep_alive_server()
    
    # Keep alive
    stop_event = asyncio.Event()
    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        print("Stopping bots...")
        for app in list(RUNNING_APPS.values()):
            await app.updater.stop()
            await app.stop()
            await app.shutdown()

def main():
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    main()
