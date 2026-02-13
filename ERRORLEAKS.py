import sys
import subprocess
import os
import json
import asyncio
import logging
import time
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from enum import Enum


def install_packages():
    
    packages = [
        'python-telegram-bot==20.7',
        'telethon',
        'ollama',
        'colorama',
        'requests',
        'python-dotenv'
    ]

    print("🔧 Installing required Python packages...")
    for package in packages:
        try:
            __import__(package.split('==')[0].replace('-', '_'))
            print(f"✅ {package.split('==')[0]} already installed")
        except ImportError:
            print(f"📦 Installing {package}...")
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', package, "--break-system-packages"])
            print(f"✅ {package} installed successfully")


install_packages()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from telethon import TelegramClient, functions, errors
from telethon.tl.types import ReportResultChooseOption, ReportResultReported, ReportResultAddComment
import ollama
from colorama import Fore, Style, init as colorama_init
from dotenv import load_dotenv


load_dotenv()


colorama_init(autoreset=True)


OWNER_ID = 5318806760

BOT_TOKEN = os.environ.get('BOT_TOKEN')
API_ID = int(os.environ.get('API_ID', 0))
API_HASH = os.environ.get('API_HASH')

if not BOT_TOKEN or not API_ID or not API_HASH:
    print(f"{Fore.RED}❌ ERROR: Missing credentials in .env file!{Fore.RESET}")
    print(f"{Fore.YELLOW}Please ensure .env file contains:{Fore.RESET}")
    print("BOT_TOKEN=your_bot_token")
    print("API_ID=your_api_id")
    print("API_HASH=your_api_hash")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).parent.absolute()
SESSIONS_DIR = SCRIPT_DIR / "sessions"
DATA_DIR = SCRIPT_DIR / "channel_data"
REPORTS_DIR = SCRIPT_DIR / "reports"
LOGS_DIR = SCRIPT_DIR / "logs"
DB_DIR = SCRIPT_DIR / "database"


for directory in [SESSIONS_DIR, DATA_DIR, REPORTS_DIR, LOGS_DIR, DB_DIR]:
    directory.mkdir(exist_ok=True)


USERS_DB = DB_DIR / "users.json"
ADMINS_DB = DB_DIR / "admins.json"
ATTACKS_DB = DB_DIR / "global_attacks.json"


logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOGS_DIR / f'bot_{datetime.now().strftime("%Y%m%d")}.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)



class UserRole(Enum):
   
    OWNER = "owner"
    ADMIN = "admin"
    USER = "user"
    UNAPPROVED = "unapproved"



class DatabaseManager:
   
    
    @staticmethod
    def init_databases():

        if not USERS_DB.exists():
            with open(USERS_DB, 'w') as f:
                json.dump({}, f)
        
        if not ADMINS_DB.exists():
            with open(ADMINS_DB, 'w') as f:
                json.dump({}, f)
        
        if not ATTACKS_DB.exists():
            with open(ATTACKS_DB, 'w') as f:
                json.dump([], f)
    
    @staticmethod
    def load_users():

        try:
            with open(USERS_DB, 'r') as f:
                return json.load(f)
        except:
            return {}
    
    @staticmethod
    def save_users(users):

        with open(USERS_DB, 'w') as f:
            json.dump(users, f, indent=2)
    
    @staticmethod
    def load_admins():

        try:
            with open(ADMINS_DB, 'r') as f:
                return json.load(f)
        except:
            return {}
    
    @staticmethod
    def save_admins(admins):

        with open(ADMINS_DB, 'w') as f:
            json.dump(admins, f, indent=2)
    
    @staticmethod
    def load_attacks():
    
        try:
            with open(ATTACKS_DB, 'r') as f:
                return json.load(f)
        except:
            return []
    
    @staticmethod
    def save_attacks(attacks):

        with open(ATTACKS_DB, 'w') as f:
            json.dump(attacks, f, indent=2)
    
    @staticmethod
    def get_user_role(user_id: int) -> UserRole:

        if user_id == OWNER_ID:
            return UserRole.OWNER
        

        admins = DatabaseManager.load_admins()
        if str(user_id) in admins:
            admin_data = admins[str(user_id)]
            if admin_data.get('status') == 'active':

                if admin_data.get('banned_until'):
                    banned_until = datetime.fromisoformat(admin_data['banned_until'])
                    if datetime.now() > banned_until:

                        admin_data['banned_until'] = None
                        DatabaseManager.save_admins(admins)
                        return UserRole.ADMIN
                    else:
                        return UserRole.UNAPPROVED
                return UserRole.ADMIN
        

        users = DatabaseManager.load_users()
        if str(user_id) in users:
            user_data = users[str(user_id)]
            if user_data.get('status') == 'approved':
                
                expiry = datetime.fromisoformat(user_data['expiry_date'])
                if datetime.now() > expiry:
                   
                    return UserRole.UNAPPROVED
                
             
                if user_data.get('banned_until'):
                    banned_until = datetime.fromisoformat(user_data['banned_until'])
                    if datetime.now() > banned_until:
                     
                        user_data['banned_until'] = None
                        DatabaseManager.save_users(users)
                        return UserRole.USER
                    else:
                        return UserRole.UNAPPROVED
                
                return UserRole.USER
        
        return UserRole.UNAPPROVED
    
    @staticmethod
    def approve_user(user_id: int, days: int):
        
        users = DatabaseManager.load_users()
        expiry_date = datetime.now() + timedelta(days=days)
        
        users[str(user_id)] = {
            'user_id': user_id,
            'role': 'user',
            'status': 'approved',
            'expiry_date': expiry_date.isoformat(),
            'approved_at': datetime.now().isoformat(),
            'banned_until': None
        }
        
        DatabaseManager.save_users(users)
    
    @staticmethod
    def disapprove_user(user_id: int):
       
        users = DatabaseManager.load_users()
        if str(user_id) in users:
            del users[str(user_id)]
            DatabaseManager.save_users(users)
    
    @staticmethod
    def approve_admin(user_id: int, days: int):
        
        admins = DatabaseManager.load_admins()
        expiry_date = datetime.now() + timedelta(days=days)
        
        admins[str(user_id)] = {
            'user_id': user_id,
            'role': 'admin',
            'status': 'active',
            'expiry_date': expiry_date.isoformat(),
            'approved_at': datetime.now().isoformat(),
            'banned_until': None
        }
        
        DatabaseManager.save_admins(admins)
    
    @staticmethod
    def remove_admin(user_id: int):
       
        admins = DatabaseManager.load_admins()
        if str(user_id) in admins:
            del admins[str(user_id)]
            DatabaseManager.save_admins(admins)
    
    @staticmethod
    def ban_user(user_id: int, duration_hours: int):
       
        users = DatabaseManager.load_users()
        if str(user_id) in users:
            banned_until = datetime.now() + timedelta(hours=duration_hours)
            users[str(user_id)]['banned_until'] = banned_until.isoformat()
            DatabaseManager.save_users(users)
    
    @staticmethod
    def ban_admin(user_id: int, duration_hours: int):
      
        admins = DatabaseManager.load_admins()
        if str(user_id) in admins:
            banned_until = datetime.now() + timedelta(hours=duration_hours)
            admins[str(user_id)]['banned_until'] = banned_until.isoformat()
            DatabaseManager.save_admins(admins)
    
    @staticmethod
    def unban_user(user_id: int):
        """Unban a user"""
        users = DatabaseManager.load_users()
        if str(user_id) in users:
            users[str(user_id)]['banned_until'] = None
            DatabaseManager.save_users(users)
    
    @staticmethod
    def unban_admin(user_id: int):
       
        admins = DatabaseManager.load_admins()
        if str(user_id) in admins:
            admins[str(user_id)]['banned_until'] = None
            DatabaseManager.save_admins(admins)
    
    @staticmethod
    def log_attack(user_id: int, channel_url: str, target_count: int, status: str = "started"):
     
        attacks = DatabaseManager.load_attacks()
        
        attack_entry = {
            'user_id': user_id,
            'channel_url': channel_url,
            'target_count': target_count,
            'status': status,
            'timestamp': datetime.now().isoformat()
        }
        
        attacks.append(attack_entry)
        DatabaseManager.save_attacks(attacks)
    
    @staticmethod
    def update_attack_status(user_id: int, channel_url: str, status: str, stats: dict = None):
      
        attacks = DatabaseManager.load_attacks()
        
       
        for attack in reversed(attacks):
            if attack['user_id'] == user_id and attack['channel_url'] == channel_url:
                attack['status'] = status
                attack['updated_at'] = datetime.now().isoformat()
                if stats:
                    attack['stats'] = stats
                break
        
        DatabaseManager.save_attacks(attacks)


DatabaseManager.init_databases()



(WAITING_PHONE, WAITING_CODE, WAITING_PASSWORD, WAITING_2FA,
 WAITING_CHANNEL_URL, WAITING_REPORT_COUNT, SELECT_SESSION_DELETE,
 WAITING_ADMIN_ID, WAITING_ADMIN_DAYS, WAITING_USER_ID, WAITING_USER_DAYS,
 WAITING_BAN_ID, WAITING_BAN_DURATION) = range(13)


user_sessions = {} 


def generate_filename(channel_username: str, ai_category: str, status: str = "Analysis") -> str:

    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    clean_category = ai_category.replace(' ', '_').replace('/', '_').replace('-', '_')
    clean_username = channel_username.replace('@', '')
    return f"{timestamp}_{clean_username}_{clean_category}_{status}.json"

def escape_markdown(text: str) -> str:

    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text



class OllamaManager:


    @staticmethod
    def check_ollama_installed():

        try:
            result = subprocess.run(['ollama', '--version'],
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except:
            return False

    @staticmethod
    def install_ollama():

        print(f"{Fore.YELLOW}🔧 Installing Ollama...{Fore.RESET}")
        try:
            install_cmd = "curl -fsSL https://ollama.com/install.sh | sh"
            subprocess.run(install_cmd, shell=True, check=True)
            print(f"{Fore.GREEN}✅ Ollama installed successfully{Fore.RESET}")

            subprocess.Popen(['ollama', 'serve'],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)
            time.sleep(5)
            return True
        except Exception as e:
            print(f"{Fore.RED}❌ Failed to install Ollama: {e}{Fore.RESET}")
            return False

    @staticmethod
    def check_model_exists(model_name="deepseek-r1:1.5b"):

        try:
            models = ollama.list()
            return any(model_name in model['name'] for model in models.get('models', []))
        except:
            return False

    @staticmethod
    def download_model(model_name="deepseek-r1:1.5b"):

        print(f"{Fore.YELLOW}📥 Downloading {model_name} model (this may take a few minutes)...{Fore.RESET}")
        try:
            ollama.pull(model_name)
            print(f"{Fore.GREEN}✅ Model downloaded successfully{Fore.RESET}")
            return True
        except Exception as e:
            print(f"{Fore.RED}❌ Failed to download model: {e}{Fore.RESET}")
            return False

    @staticmethod
    def setup():

        if not OllamaManager.check_ollama_installed():
            print(f"{Fore.YELLOW}⚠️ Ollama not found. Installing...{Fore.RESET}")
            if not OllamaManager.install_ollama():
                return False
        else:
            print(f"{Fore.GREEN}✅ Ollama already installed{Fore.RESET}")
            try:
                subprocess.Popen(['ollama', 'serve'],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
                time.sleep(2)
            except:
                pass

        if not OllamaManager.check_model_exists():
            print(f"{Fore.YELLOW}⚠️ DeepSeek model not found. Downloading...{Fore.RESET}")
            if not OllamaManager.download_model():
                return False
        else:
            print(f"{Fore.GREEN}✅ DeepSeek model already downloaded{Fore.RESET}")

        return True



class AIAnalyzer:


    def __init__(self, model="deepseek-r1:1.5b"):
        self.model = model

    def analyze_posts(self, posts: List[Dict], channel_name: str) -> Dict:


        total_posts = len(posts)
        print(f"{Fore.CYAN}📊 Preparing to analyze ALL {total_posts} posts...{Fore.RESET}")
        
        posts_text = "\n".join([
            f"Post {i+1} (ID: {post['id']}, Link: https://t.me/{channel_name}/{post['id']}): {post['text'][:200]}..."
            if len(post['text']) > 200 else f"Post {i+1} (ID: {post['id']}, Link: https://t.me/{channel_name}/{post['id']}): {post['text']}"
            for i, post in enumerate(posts)
        ])

        categories = """
1. I don't like it - General dislike without specific violation
2. Child abuse - Content involving minors inappropriately
3. Violence - Violent threats, gore, or harmful content
4. Illegal goods and services - Drugs, weapons, stolen goods, etc.
5. Illegal adult content - Non-consensual or illegal pornography
6. Personal data - Doxxing, sharing private information
7. Scam or fraud - Phishing, fake schemes, financial fraud
8. Copyright - Pirated content, unauthorized distribution
9. Spam - Unsolicited bulk messages, repetitive content
10. Other - Violations not covered by other categories
11. It's not illegal, but must be taken down - Terms of service violations
"""

        prompt = f"""You are a Telegram content moderation expert analyzing posts for policy violations.

Channel: {channel_name}
Total Posts to Analyze: {total_posts} (ANALYZING ALL POSTS TOGETHER)

Posts Content (ALL {total_posts} POSTS):
{posts_text}

Telegram Report Categories:
{categories}

Your Task:
1. Carefully analyze ALL {total_posts} posts for violations of Telegram's Terms of Service
2. Consider patterns across ALL posts, not just individual messages
3. Identify the PRIMARY violation category (1-11) that best describes the issue
4. Focus on genuine policy violations, not subjective opinions
5. Generate 15 COMPLETELY DIFFERENT, compelling report comments that:
   - Each must use DIFFERENT wording and structure
   - Vary the tone (formal, direct, detailed, concise)
   - Reference different aspects of violations
   - Use diverse vocabulary and phrasing
   - Some short (1-2 sentences), some longer (3-4 sentences)
   - Mention specific patterns, behaviors, or content types
   - Each comment must be UNIQUE with NO repetitive phrases

You MUST respond with ONLY valid JSON in this EXACT format (no markdown, no extra text):
{{
    "violates_policy": true,
    "primary_category": 9,
    "category_name": "Spam",
    "reason": "Brief explanation of why this violates policy",
    "confidence": "high",
    "specific_violations": ["violation 1", "violation 2"],
    "targeted_posts": [list of post IDs that violate policy],
    "report_comments": [
        "Comment 1 with unique wording",
        "Comment 2 completely different from 1",
        "Comment 3 with different angle",
        "Comment 4 short and direct",
        "Comment 5 longer with details",
        "Comment 6 pattern-focused",
        "Comment 7 behavior-focused",
        "Comment 8 impact-focused",
        "Comment 9 policy-focused",
        "Comment 10 evidence-focused",
        "Comment 11 with different tone",
        "Comment 12 formal language",
        "Comment 13 direct approach",
        "Comment 14 detailed explanation",
        "Comment 15 strong conclusion"
    ]
}}

CRITICAL: The "report_comments" field is MANDATORY and must contain exactly 15 different comments. Do not skip this field!"""

        try:
            print(f"{Fore.YELLOW}🤖 AI is analyzing ALL {total_posts} posts together...{Fore.RESET}")
            response = ollama.chat(
                model=self.model,
                messages=[{'role': 'user', 'content': prompt}],
                options={'temperature': 0.7, 'num_predict': 2000}
            )

            response_text = response['message']['content']
            
            print(f"\n{Fore.MAGENTA}{'='*100}")
            print(f"🤖 RAW AI RESPONSE:")
            print(f"{'='*100}{Fore.RESET}")
            print(f"{Fore.CYAN}{response_text}{Fore.RESET}")
            print(f"{Fore.MAGENTA}{'='*100}\n{Fore.RESET}")
            
            response_text = response_text.strip()
            
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].split('```')[0].strip()
            
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_text = response_text[json_start:json_end]
                
                print(f"{Fore.YELLOW}🔍 Extracted JSON (attempting to parse):{Fore.RESET}")
                print(f"{Fore.CYAN}{json_text[:500]}...{Fore.RESET}\n")
                
                result = json.loads(json_text)
                
                print(f"{Fore.GREEN}✅ JSON PARSED SUCCESSFULLY!{Fore.RESET}")
                print(f"{Fore.CYAN}Parsed result: {json.dumps(result, indent=2)[:500]}...{Fore.RESET}\n")
                
                required_fields = ['violates_policy', 'primary_category', 'category_name', 'reason', 'report_comments']
                missing_fields = [field for field in required_fields if field not in result]
                
                if missing_fields:
                    print(f"{Fore.RED}❌ Missing required fields: {missing_fields}{Fore.RESET}")
                    raise ValueError(f"Missing fields: {missing_fields}")
                
                if not result.get('report_comments') or len(result['report_comments']) == 0:
                    print(f"{Fore.RED}❌ report_comments is empty!{Fore.RESET}")
                    raise ValueError("report_comments is empty")
                
                print(f"{Fore.GREEN}✅ AI analysis complete - Category: {result.get('category_name')}{Fore.RESET}")
                print(f"{Fore.CYAN}📊 Confidence: {result.get('confidence', 'medium')}{Fore.RESET}")
                print(f"{Fore.CYAN}🎯 Violations: {', '.join(result.get('specific_violations', ['General']))}{Fore.RESET}")
                print(f"{Fore.CYAN}💬 Generated {len(result.get('report_comments', []))} report comments{Fore.RESET}\n")
                return result
            
            print(f"{Fore.RED}❌ Could not find JSON in AI response{Fore.RESET}")
            raise ValueError("Invalid JSON structure from AI")

        except json.JSONDecodeError as e:
            logger.error(f"AI JSON parsing error: {e}")
            print(f"{Fore.RED}❌ JSON parsing failed: {e}{Fore.RESET}")
            print(f"{Fore.YELLOW}⚠️ Using fallback analysis{Fore.RESET}\n")
        except Exception as e:
            logger.error(f"AI analysis error: {e}")
            print(f"{Fore.RED}❌ AI analysis error: {e}{Fore.RESET}")
            print(f"{Fore.YELLOW}⚠️ Using fallback analysis{Fore.RESET}\n")
        
        print(f"{Fore.CYAN}📋 Generating fallback analysis...{Fore.RESET}")
        fallback = {
            "violates_policy": True,
            "primary_category": 9,
            "category_name": "Spam",
            "reason": f"Content appears to violate platform guidelines based on pattern analysis of all {total_posts} posts",
            "confidence": "medium",
            "specific_violations": ["Potential spam patterns detected across multiple posts", "Suspicious activity patterns"],
            "targeted_posts": [post['id'] for post in posts[:10]],
            "report_comments": [
                f"This channel violates Telegram's Terms of Service with {total_posts} posts showing prohibited patterns.",
                f"Systematic policy violations detected across the entire channel content.",
                f"Reporting for non-compliance with community guidelines. Multiple infractions identified.",
                f"Channel content breaches platform rules. Immediate review required.",
                f"Prohibited activity patterns found in analyzed messages.",
                f"Terms of service violations evident throughout channel history.",
                f"Content policy infractions require moderation action.",
                f"Platform guidelines violated repeatedly across posts.",
                f"Unacceptable content patterns detected requiring intervention.",
                f"Channel demonstrates clear disregard for community standards.",
                f"Multiple posts contain policy-violating material.",
                f"Reporting systematic abuse of platform terms.",
                f"Content review needed for Terms of Service violations.",
                f"Channel activity conflicts with acceptable use policies.",
                f"Repeated guideline breaches warrant moderation review."
            ]
        }
        print(f"{Fore.GREEN}✅ Fallback analysis generated with {len(fallback['report_comments'])} comments{Fore.RESET}\n")
        return fallback


class SessionManager:


    @staticmethod
    def get_user_session_dir(user_id: int) -> Path:

        user_dir = SESSIONS_DIR / f"user_{user_id}"
        user_dir.mkdir(exist_ok=True)
        return user_dir

    @staticmethod
    def get_all_sessions(user_id: int):

        user_dir = SessionManager.get_user_session_dir(user_id)
        return list(user_dir.glob("*.session"))

    @staticmethod
    def get_session_info(session_path: Path):

        return {
            'name': session_path.stem,
            'path': str(session_path),
            'size': session_path.stat().st_size,
            'modified': datetime.fromtimestamp(session_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
        }

    @staticmethod
    def delete_session(user_id: int, session_name: str):

        user_dir = SessionManager.get_user_session_dir(user_id)
        session_path = user_dir / f"{session_name}.session"
        deleted_files = []
        
        if session_path.exists():
            try:
                session_path.unlink()
                deleted_files.append(str(session_path))
            except Exception as e:
                logger.error(f"Error deleting session file: {e}")
                
        for pattern in [f"{session_name}.session-journal*", f"{session_name}.session-shm", f"{session_name}.session-wal"]:
            for journal_file in user_dir.glob(pattern):
                try:
                    journal_file.unlink()
                    deleted_files.append(str(journal_file))
                except Exception as e:
                    logger.error(f"Error deleting journal file: {e}")
        
        return len(deleted_files) > 0

    @staticmethod
    async def create_client(user_id: int, phone: str, max_retries=3):

        user_dir = SessionManager.get_user_session_dir(user_id)
        session_name = f"session_{phone.replace('+', '')}"
        session_path = user_dir / session_name

        for attempt in range(max_retries):
            try:
                client = TelegramClient(
                    str(session_path), 
                    API_ID, 
                    API_HASH,
                    timeout=30,
                    connection_retries=5,
                    retry_delay=2,
                    sequential_updates=True
                )
                
                await client.connect()
                
                try:
                    import sqlite3
                    conn = sqlite3.connect(str(session_path) + '.session', timeout=30.0)
                    conn.execute('PRAGMA journal_mode=WAL')
                    conn.execute('PRAGMA busy_timeout=30000')
                    conn.close()
                except:
                    pass
                
                return client, session_name
                
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(3)
                    for pattern in [f"{session_name}.session-journal*", f"{session_name}.session-shm", f"{session_name}.session-wal"]:
                        for lock_file in user_dir.glob(pattern):
                            try:
                                lock_file.unlink()
                            except:
                                pass
                else:
                    raise


class ChannelScraper:


    @staticmethod
    async def scrape_channel(client, channel_url: str, max_retries=3):

        channel_name = channel_url.strip().lower().replace("https://t.me/", "").replace("@", "")

        for attempt in range(max_retries):
            try:
                print(f"{Fore.CYAN}🔍 Attempt {attempt + 1}/{max_retries}: Connecting to channel...{Fore.RESET}")
                
                await client(functions.channels.JoinChannelRequest(channel=channel_name))
                print(f"{Fore.GREEN}✅ Joined channel successfully{Fore.RESET}")

                entity = await client.get_entity(channel_name)
                
                actual_channel_username = None
                if hasattr(entity, 'username') and entity.username:
                    actual_channel_username = entity.username
                else:
                    actual_channel_username = channel_name
                
                print(f"{Fore.CYAN}📊 Channel: {entity.title if hasattr(entity, 'title') else channel_name}{Fore.RESET}")
                print(f"{Fore.CYAN}📱 Username: @{actual_channel_username}{Fore.RESET}")

                messages = []
                message_count = 0
                
                print(f"{Fore.YELLOW}📥 Scraping ALL posts from channel...{Fore.RESET}")
                async for message in client.iter_messages(entity, limit=None):
                    message_count += 1
                    if message_count % 50 == 0:
                        print(f"{Fore.CYAN}   Scraped {message_count} posts...{Fore.RESET}")
                    
                    text = ""
                    if message.text:
                        try:
                            text = message.text
                        except Exception as parse_error:
                            try:
                                text = message.raw_text if hasattr(message, 'raw_text') else str(message.message)
                                logger.warning(f"Entity parsing failed for message {message.id}, using raw text")
                            except:
                                text = "[Unable to parse message text]"
                                logger.error(f"Complete parsing failure for message {message.id}")
                    
                    if text:
                        messages.append({
                            'id': message.id,
                            'text': text,
                            'link': f"https://t.me/{actual_channel_username}/{message.id}",
                            'date': message.date.isoformat() if message.date else None,
                            'views': message.views or 0
                        })

                print(f"{Fore.GREEN}✅ Successfully scraped ALL {len(messages)} posts{Fore.RESET}")

                data_file = DATA_DIR / generate_filename(actual_channel_username, "ChannelData", "Scraped")
                with open(data_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'channel': actual_channel_username,
                        'channel_title': entity.title if hasattr(entity, 'title') else actual_channel_username,
                        'scraped_at': datetime.now().isoformat(),
                        'total_posts': len(messages),
                        'posts': messages
                    }, f, indent=2, ensure_ascii=False)

                return {
                    'channel_name': actual_channel_username,
                    'total_posts': len(messages),
                    'messages': messages,
                    'data_file': str(data_file)
                }

            except errors.FloodWaitError as e:
                wait_time = e.seconds
                print(f"{Fore.YELLOW}⚠️ Flood wait: Need to wait {wait_time} seconds{Fore.RESET}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    raise
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Channel scraping error (attempt {attempt + 1}): {error_msg}")
                print(f"{Fore.RED}❌ Error: {error_msg}{Fore.RESET}")
                
                if "database is locked" in error_msg.lower():
                    print(f"{Fore.YELLOW}⚠️ Database locked, waiting 5 seconds before retry...{Fore.RESET}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5)
                        continue
                
                if attempt >= max_retries - 1:
                    raise
                    
                await asyncio.sleep(3)

class ReportStats:

    
    def __init__(self):
        self.successful = 0
        self.failed = 0
        self.lock = asyncio.Lock()
        self.report_logs = []
        self.last_update_time = time.time()
        self.telegram_responses = []
        
    async def add_success(self, category: str, comment: str, account_num: int, post_link: str = "", telegram_response: str = ""):
        async with self.lock:
            self.successful += 1
            timestamp = datetime.now().strftime('%H:%M:%S')
            
            log_entry = {
                'type': 'success',
                'category': category,
                'comment': comment[:50] + '...' if len(comment) > 50 else comment,
                'account': account_num,
                'post_link': post_link,
                'timestamp': timestamp,
                'telegram_response': telegram_response
            }
            self.report_logs.append(log_entry)
            
            print(f"\n{Fore.GREEN}{'='*100}")
            print(f"✅ REPORT SUCCESS #{self.successful}")
            print(f"{'='*100}{Fore.RESET}")
            print(f"{Fore.CYAN}⏰ Time: {timestamp}")
            print(f"👤 Account: #{account_num}")
            print(f"📋 Category: {category}")
            print(f"💬 Comment: {comment}")
            if post_link:
                print(f"🔗 Post: {post_link}")
            if telegram_response:
                print(f"{Fore.YELLOW}📱 Telegram Response: {telegram_response}{Fore.RESET}")
            print(f"{Fore.GREEN}{'='*100}\n{Fore.RESET}")
            
    async def add_failure(self, category: str, reason: str, account_num: int, post_link: str = "", telegram_error: str = ""):
        async with self.lock:
            self.failed += 1
            timestamp = datetime.now().strftime('%H:%M:%S')
            
            log_entry = {
                'type': 'failed',
                'category': category,
                'reason': reason,
                'account': account_num,
                'post_link': post_link,
                'timestamp': timestamp,
                'telegram_error': telegram_error
            }
            self.report_logs.append(log_entry)
            
            print(f"\n{Fore.RED}{'='*100}")
            print(f"❌ REPORT FAILED #{self.failed}")
            print(f"{'='*100}{Fore.RESET}")
            print(f"{Fore.CYAN}⏰ Time: {timestamp}")
            print(f"👤 Account: #{account_num}")
            print(f"📋 Category: {category}")
            print(f"⚠️ Error: {reason}")
            if post_link:
                print(f"🔗 Post: {post_link}")
            if telegram_error:
                print(f"{Fore.YELLOW}📱 Telegram Error Details: {telegram_error}{Fore.RESET}")
            print(f"{Fore.RED}{'='*100}\n{Fore.RESET}")
    
    async def get_stats(self):
        async with self.lock:
            return {
                'successful': self.successful,
                'failed': self.failed,
                'total': self.successful + self.failed,
                'recent_logs': self.report_logs[-10:]
            }



class MassReporter:


    @staticmethod
    async def get_category_by_name(options, target_name: str):

        for option in options:
            if target_name.lower() in option.text.lower():
                return option
        return options[0]

    @staticmethod
    async def report_single(client, channel_name: str, message_ids: List[int],
                          category_option, category_name: str, comment: str,
                          account_num: int, stats: ReportStats, post_link: str):

        try:
            print(f"{Fore.CYAN}🚀 Sending report from Account #{account_num}...{Fore.RESET}")
            
            response = await client(functions.messages.ReportRequest(
                peer=channel_name,
                id=message_ids,
                option=category_option,
                message=comment
            ))
            
            response_type = type(response).__name__
            print(f"{Fore.YELLOW}📱 Telegram returned: {response_type}{Fore.RESET}")
            
            if isinstance(response, ReportResultReported):
                telegram_response = f"ReportResultReported - Report accepted by Telegram"
                await stats.add_success(category_name, comment, account_num, post_link, telegram_response)
                return True
                
            elif isinstance(response, ReportResultChooseOption):
                print(f"{Fore.YELLOW}📋 Sub-categories available: {len(response.options)}{Fore.RESET}")
                if response.options:
                    sub_option = random.choice(response.options)
                    sub_category_name = f"{category_name} → {sub_option.text}"
                    
                    print(f"{Fore.CYAN}🎯 Selected sub-category: {sub_option.text}{Fore.RESET}")
                    
                    sub_response = await client(functions.messages.ReportRequest(
                        peer=channel_name,
                        id=message_ids,
                        option=sub_option.option,
                        message=comment
                    ))
                    
                    sub_response_type = type(sub_response).__name__
                    telegram_response = f"{response_type} → {sub_response_type} - Sub-category '{sub_option.text}' selected and report accepted"
                    
                    await stats.add_success(sub_category_name, comment, account_num, post_link, telegram_response)
                    return True
                    
            elif isinstance(response, ReportResultAddComment):
                print(f"{Fore.YELLOW}💬 Telegram requested additional comment{Fore.RESET}")
                final_response = await client(functions.messages.ReportRequest(
                    peer=channel_name,
                    id=message_ids,
                    option=category_option,
                    message=comment
                ))
                
                final_response_type = type(final_response).__name__
                telegram_response = f"{response_type} → {final_response_type} - Comment added and report accepted"
                
                await stats.add_success(category_name, comment, account_num, post_link, telegram_response)
                return True
            else:
                telegram_response = f"{response_type} - Report processed (unknown response type)"
                await stats.add_success(category_name, comment, account_num, post_link, telegram_response)
                return True
                
        except errors.FloodWaitError as e:
            telegram_error = f"FloodWaitError: Must wait {e.seconds} seconds before next report"
            await stats.add_failure(category_name, f"FloodWait: {e.seconds}s", account_num, post_link, telegram_error)
            print(f"{Fore.RED}⏳ Account #{account_num} hit flood limit: {e.seconds}s wait required{Fore.RESET}")
            await asyncio.sleep(e.seconds)
            return False
            
        except Exception as e:
            error_msg = str(e)
            telegram_error = f"Exception: {error_msg}"
            await stats.add_failure(category_name, error_msg[:50], account_num, post_link, telegram_error)
            print(f"{Fore.RED}❌ Report failed: {error_msg}{Fore.RESET}")
            return False

    @staticmethod
    async def report_with_account(client, channel_name: str, message_ids: List[int],
                                  ai_result: Dict, account_num: int, 
                                  stats: ReportStats, target_count: int, accounts_count: int,
                                  post_links: List[str]):
       
        try:
            print(f"\n{Fore.MAGENTA}{'='*80}")
            print(f"🎮 ACCOUNT #{account_num} STARTING")
            print(f"{'='*80}{Fore.RESET}\n")
            
            choose_options = await client(functions.messages.ReportRequest(
                peer=channel_name,
                id=message_ids,
                option=b'',
                message=""
            ))

            if not hasattr(choose_options, 'options'):
                await stats.add_failure("Setup", "No report options available", account_num, "", "No options returned by Telegram API")
                return

            category = await MassReporter.get_category_by_name(
                choose_options.options, 
                ai_result['category_name']
            )
            
            print(f"{Fore.CYAN}📋 Available categories: {[opt.text for opt in choose_options.options]}{Fore.RESET}")
            print(f"{Fore.GREEN}✅ Selected category: {category.text}{Fore.RESET}")
            
            report_comments = ai_result.get('report_comments', [])
            if not report_comments or len(report_comments) == 0:
                print(f"{Fore.RED}❌ No report comments available in AI result!{Fore.RESET}")
                print(f"{Fore.YELLOW}🔧 Generating fallback comments...{Fore.RESET}")
                report_comments = [
                    f"This channel violates Telegram's Terms of Service. Multiple policy infractions detected.",
                    f"Content posted breaches community guidelines. Review required.",
                    f"Reporting for systematic platform rule violations.",
                    f"Channel demonstrates prohibited activity patterns.",
                    f"Posts contain content explicitly against terms of service.",
                    f"Unacceptable content requiring moderation action.",
                    f"Platform policy violations evident across channel.",
                    f"Terms of service breached repeatedly.",
                    f"Content conflicts with acceptable use policies.",
                    f"Guideline violations warrant immediate review.",
                    f"Channel activity violates community standards.",
                    f"Prohibited content patterns detected throughout.",
                    f"Systematic abuse of platform terms identified.",
                    f"Multiple infractions of content policies found.",
                    f"Channel requires moderation for policy violations."
                ]
            
            print(f"{Fore.CYAN}💬 Using {len(report_comments)} unique report comments{Fore.RESET}")

            reports_per_account = target_count // accounts_count
            extra_reports = target_count % accounts_count
            
            my_reports = reports_per_account
            if account_num < extra_reports:
                my_reports += 1

            print(f"{Fore.YELLOW}🎯 Account #{account_num} will send {my_reports} reports{Fore.RESET}")

            last_comment = None
            used_comments = []
            
            for i in range(my_reports):
                current_stats = await stats.get_stats()
                if current_stats['successful'] >= target_count:
                    print(f"{Fore.GREEN}✅ Target reached! Account #{account_num} stopping.{Fore.RESET}")
                    break
                
                available_comments = [c for c in report_comments if c != last_comment]
                if not available_comments:
                    available_comments = report_comments
                    
                comment = random.choice(available_comments)
                last_comment = comment
                used_comments.append(comment)
                
                post_link = post_links[i % len(post_links)]
                
                print(f"\n{Fore.CYAN}📤 Account #{account_num} - Report {i+1}/{my_reports}{Fore.RESET}")
                print(f"{Fore.YELLOW}💬 Using comment variant #{(i % len(report_comments)) + 1}{Fore.RESET}")
                
                await MassReporter.report_single(
                    client, channel_name, message_ids,
                    category.option, category.text, comment,
                    account_num, stats, post_link
                )
                
                delay = random.uniform(0.2, 0.5)
                await asyncio.sleep(delay)
            
            print(f"\n{Fore.CYAN}📊 Comment Usage Stats:{Fore.RESET}")
            print(f"{Fore.CYAN}   Total unique comments used: {len(set(used_comments))}/{len(report_comments)}{Fore.RESET}")
            
            print(f"\n{Fore.MAGENTA}{'='*80}")
            print(f"🏁 ACCOUNT #{account_num} FINISHED")
            print(f"{'='*80}{Fore.RESET}\n")

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Account {account_num} reporting error: {error_msg}")
            await stats.add_failure("Account Error", error_msg[:50], account_num, "", f"Account-level exception: {error_msg}")

    @staticmethod
    async def live_progress_updater(stats: ReportStats, update: Update, target_count: int, 
                                   channel_name: str, start_time: float):
      
        message = None
        last_successful = 0
        last_failed = 0
        
        try:
            while True:
                await asyncio.sleep(2)
                
                current_stats = await stats.get_stats()
                elapsed = time.time() - start_time
                
                if current_stats['successful'] >= target_count:
                    break
                
                if current_stats['successful'] != last_successful or current_stats['failed'] != last_failed:
                    last_successful = current_stats['successful']
                    last_failed = current_stats['failed']
                    
                    speed = current_stats['successful'] / elapsed if elapsed > 0 else 0
                    success_rate = (current_stats['successful'] / max(1, current_stats['total'])) * 100
                    remaining = target_count - current_stats['successful']
                    eta = remaining / speed if speed > 0 else 0
                    
                    progress_percentage = (current_stats['successful'] / target_count) * 100
                    filled = int(progress_percentage / 5)
                    bar = '█' * filled + '░' * (20 - filled)
                    
                    progress_text = f"""
⚡ <b>LIVE ATTACK PROGRESS</b> ⚡

🎯 Target: <code>{channel_name}</code>
📊 Progress: [{bar}] {progress_percentage:.1f}%
📈 {current_stats['successful']}/{target_count} reports sent

✅ <b>Successful:</b> {current_stats['successful']}
❌ <b>Failed:</b> {current_stats['failed']}
📊 <b>Success Rate:</b> {success_rate:.1f}%
⚡ <b>Speed:</b> {speed:.2f} reports/sec
⏱️ <b>Elapsed:</b> {int(elapsed)}s
🎯 <b>ETA:</b> {int(eta)}s

<b>📋 Recent Activity:</b>
"""
                    for log in current_stats['recent_logs'][-5:]:
                        if log['type'] == 'success':
                            progress_text += f"✅ <code>{log['timestamp']}</code> | Acc#{log['account']} | {log['category']}\n"
                        else:
                            progress_text += f"❌ <code>{log['timestamp']}</code> | Acc#{log['account']} | {log['reason']}\n"
                    
                    try:
                        if message is None:
                            message = await update.message.reply_text(progress_text, parse_mode='HTML')
                        else:
                            await message.edit_text(progress_text, parse_mode='HTML')
                    except Exception as e:
                        pass
                        
        except asyncio.CancelledError:
            pass

    @staticmethod
    async def mass_report(sessions: List[str], channel_name: str,
                         ai_result: Dict, target_count: int, update: Update):
       
        stats = ReportStats()
        start_time = time.time()
        
        print(f"\n{Fore.CYAN}{'='*100}")
        print(f"{Fore.YELLOW}🚀 STARTING MASS REPORT ATTACK{Fore.RESET}")
        print(f"{Fore.CYAN}{'='*100}")
        print(f"{Fore.YELLOW}🎯 Target: {channel_name}")
        print(f"📊 Reports: {target_count}")
        print(f"👥 Accounts: {len(sessions)}")
        print(f"📋 Category: {ai_result['category_name']}")
        print(f"💡 Reason: {ai_result.get('reason', 'N/A')}")
        print(f"🎲 Confidence: {ai_result.get('confidence', 'medium')}")
        print(f"{Fore.CYAN}{'='*100}\n{Fore.RESET}")

        clients = []
        for i, session_path in enumerate(sessions):
            try:
                print(f"{Fore.CYAN}🔌 Connecting Account #{i+1}...{Fore.RESET}")
                
                if i > 0:
                    await asyncio.sleep(0.5)
                
                client = TelegramClient(
                    str(session_path), 
                    API_ID, 
                    API_HASH, 
                    timeout=30,
                    sequential_updates=True
                )
                await client.connect()
                
                if await client.is_user_authorized():
                    clients.append((client, i+1))
                    print(f"{Fore.GREEN}✅ Account #{i+1} connected and authorized{Fore.RESET}")
                else:
                    print(f"{Fore.RED}❌ Account #{i+1} not authorized{Fore.RESET}")
            except Exception as e:
                logger.error(f"Failed to connect session {session_path}: {e}")
                print(f"{Fore.RED}❌ Account #{i+1} failed: {e}{Fore.RESET}")

        if not clients:
            print(f"{Fore.RED}❌ No clients available for attack!{Fore.RESET}")
            return await stats.get_stats()

        try:
            print(f"\n{Fore.YELLOW}🔍 Getting target messages...{Fore.RESET}")
            messages = await clients[0][0].get_messages(channel_name, limit=10) 
            message_ids = [msg.id for msg in messages]
            post_links = [f"https://t.me/{channel_name}/{msg.id}" for msg in messages]
            
            if not message_ids:
                print(f"{Fore.RED}❌ No messages found in the target channel to report!{Fore.RESET}")
                for client, _ in clients:
                    try:
                        await client.disconnect()
                    except:
                        pass
                return await stats.get_stats()

            print(f"{Fore.GREEN}✅ Got {len(message_ids)} target messages{Fore.RESET}")
            print(f"{Fore.CYAN}🔗 Target posts:{Fore.RESET}")
            for link in post_links[:5]:
                print(f"   {link}")
            if len(post_links) > 5:
                print(f"   ... and {len(post_links) - 5} more")
            print()
            
        except Exception as e:
            print(f"{Fore.RED}❌ Failed to get messages: {e}{Fore.RESET}")
            for client, _ in clients:
                try:
                    await client.disconnect()
                except:
                    pass
            return await stats.get_stats()

        progress_task = asyncio.create_task(
            MassReporter.live_progress_updater(stats, update, target_count, channel_name, start_time)
        )

        print(f"\n{Fore.GREEN}{'='*100}")
        print(f"🚀 LAUNCHING ALL ACCOUNTS")
        print(f"{'='*100}{Fore.RESET}\n")
        
        tasks = []
        for client, account_num in clients:
            task = asyncio.create_task(
                MassReporter.report_with_account(
                    client, channel_name, message_ids,
                    ai_result, account_num, stats, target_count, len(clients),
                    post_links
                )
            )
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)
        
        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass

        for i, (client, _) in enumerate(clients):
            try:
                if i > 0:
                    await asyncio.sleep(0.3)
                await client.disconnect()
            except:
                pass

        final_stats = await stats.get_stats()
        final_stats['elapsed'] = time.time() - start_time
        
        print(f"\n{Fore.CYAN}{'='*100}")
        print(f"{Fore.GREEN}✅ ATTACK COMPLETED!")
        print(f"{Fore.CYAN}{'='*100}{Fore.RESET}\n")
        
        return final_stats


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id
    role = DatabaseManager.get_user_role(user_id)

    if user_id not in user_sessions:
        user_sessions[user_id] = {'clients': [], 'data': {}}


    if role == UserRole.OWNER:
        welcome_text = """
👑 <b>ERRORLEAKS x SOULCRACK v1.0 - OWNER PANEL</b>

Welcome back, Master! You have full control over the system.

<b>✨ Your Privileges:</b>
✅ Manage Admins & Users
✅ View Global Attack List
✅ Launch Unlimited Attacks
✅ Access All System Features

<b>🎮 Owner Controls:</b>
"""
        keyboard = [
            [InlineKeyboardButton("🛡️ Manage Admins", callback_data='manage_admins')],
            [InlineKeyboardButton("👥 Manage Users", callback_data='manage_users')],
            [InlineKeyboardButton("🌐 Global Attack List", callback_data='global_attacks')],
            [InlineKeyboardButton("⚔️ Launch Attack", callback_data='attack')],
            [InlineKeyboardButton("📋 My Sessions", callback_data='view_sessions')],
            [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
        ]

    elif role == UserRole.ADMIN:
        welcome_text = """
🛡️ <b>ERRORLEAKS x SOULCRACK v1.0 - ADMIN PANEL</b>

Welcome back, Administrator! You have elevated privileges.

<b>✨ Your Privileges:</b>
✅ Manage Users
✅ Launch Attacks
✅ View Active Sessions

<b>🎮 Admin Controls:</b>
"""
        keyboard = [
            [InlineKeyboardButton("👥 Manage Users", callback_data='manage_users')],
            [InlineKeyboardButton("⚔️ Launch Attack", callback_data='attack')],
            [InlineKeyboardButton("📋 My Sessions", callback_data='view_sessions')],
            [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
        ]

    elif role == UserRole.USER:
      
        users = DatabaseManager.load_users()
        user_data = users.get(str(user_id), {})
        expiry = datetime.fromisoformat(user_data.get('expiry_date', datetime.now().isoformat()))
        days_left = (expiry - datetime.now()).days

        welcome_text = f"""
⚔️ <b>ERRORLEAKS x SOULCRACK v1.0 - USER PANEL</b>

Welcome back, Warrior! Ready to launch attacks.

<b>✨ Your Status:</b>
✅ Access Approved
⏰ Days Remaining: <b>{days_left}</b>
📅 Expiry: {expiry.strftime('%Y-%m-%d')}

<b>🎮 Your Controls:</b>
"""
        keyboard = [
            [InlineKeyboardButton("⚔️ Launch Attack", callback_data='attack')],
            [InlineKeyboardButton("📊 My Stats", callback_data='my_stats')],
            [InlineKeyboardButton("📋 My Sessions", callback_data='view_sessions')],
            [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
        ]

    else: 
        welcome_text = """
❌ <b>ACCESS DENIED</b>

You are not approved to use this bot.

Please contact the owner for access approval.
"""
        keyboard = [
            [InlineKeyboardButton("📱 Contact Owner", url='https://t.me/soulcracks_owner')]
        ]

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='HTML')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
   
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    role = DatabaseManager.get_user_role(user_id)

  
    owner_only_actions = ['manage_admins', 'global_attacks']
    admin_actions = ['manage_users']
    
    if query.data in owner_only_actions and role != UserRole.OWNER:
        await query.edit_message_text("❌ <b>Access Denied</b>\n\nThis action is only available to the Owner.", parse_mode='HTML')
        return ConversationHandler.END
    
    if query.data in admin_actions and role not in [UserRole.OWNER, UserRole.ADMIN]:
        await query.edit_message_text("❌ <b>Access Denied</b>\n\nThis action is only available to Admins and Owner.", parse_mode='HTML')
        return ConversationHandler.END

 
    if query.data == 'manage_admins':
        text = """
👑 <b>ADMIN MANAGEMENT PANEL</b>

Select an action:
"""
        keyboard = [
            [InlineKeyboardButton("➕ Approve Admin", callback_data='approve_admin')],
            [InlineKeyboardButton("➖ Remove Admin", callback_data='remove_admin')],
            [InlineKeyboardButton("🚫 Ban Admin", callback_data='ban_admin')],
            [InlineKeyboardButton("✅ Unban Admin", callback_data='unban_admin')],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif query.data == 'approve_admin':
        await query.edit_message_text(
            "👑 <b>Approve New Admin</b>\n\n"
            "Please forward a message from the user you want to make admin, "
            "OR send their Telegram User ID.\n\n"
            "Type /cancel to abort.",
            parse_mode='HTML'
        )
        return WAITING_ADMIN_ID

    elif query.data == 'remove_admin':
        admins = DatabaseManager.load_admins()
        if not admins:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='manage_admins')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("No admins to remove.", reply_markup=reply_markup)
        else:
            text = "🛡️ <b>Remove Admin</b>\n\nSelect admin to remove:\n\n"
            keyboard = []
            for admin_id, admin_data in admins.items():
                keyboard.append([InlineKeyboardButton(
                    f"❌ Admin ID: {admin_id}",
                    callback_data=f"remove_admin_{admin_id}"
                )])
            keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data='manage_admins')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif query.data.startswith('remove_admin_'):
        admin_id = int(query.data.replace('remove_admin_', ''))
        DatabaseManager.remove_admin(admin_id)
        keyboard = [[InlineKeyboardButton("🔙 Back to Admin Management", callback_data='manage_admins')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"✅ Admin <code>{admin_id}</code> has been removed successfully!",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    elif query.data == 'global_attacks':
        attacks = DatabaseManager.load_attacks()
        if not attacks:
            text = "🌐 <b>Global Attack List</b>\n\nNo attacks recorded yet."
        else:
            text = f"🌐 <b>Global Attack List</b>\n\nTotal Attacks: {len(attacks)}\n\n"
            for i, attack in enumerate(attacks[-20:], 1):  # Show last 20
                text += f"{i}. User: <code>{attack['user_id']}</code>\n"
                text += f"   Channel: <code>{attack['channel_url']}</code>\n"
                text += f"   Status: {attack['status']}\n"
                text += f"   Time: {attack['timestamp'][:19]}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

   
    elif query.data == 'manage_users':
        text = """
👥 <b>USER MANAGEMENT PANEL</b>

Select an action:
"""
        keyboard = [
            [InlineKeyboardButton("➕ Approve User", callback_data='approve_user')],
            [InlineKeyboardButton("➖ Disapprove User", callback_data='disapprove_user')],
            [InlineKeyboardButton("🚫 Ban User", callback_data='ban_user')],
            [InlineKeyboardButton("✅ Unban User", callback_data='unban_user')],
            [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif query.data == 'approve_user':
        await query.edit_message_text(
            "👥 <b>Approve New User</b>\n\n"
            "Please forward a message from the user you want to approve, "
            "OR send their Telegram User ID.\n\n"
            "Type /cancel to abort.",
            parse_mode='HTML'
        )
        return WAITING_USER_ID

    elif query.data == 'disapprove_user':
        users = DatabaseManager.load_users()
        if not users:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='manage_users')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("No users to disapprove.", reply_markup=reply_markup)
        else:
            text = "⚔️ <b>Disapprove User</b>\n\nSelect user to disapprove:\n\n"
            keyboard = []
            for user_id_str, user_data in users.items():
                keyboard.append([InlineKeyboardButton(
                    f"❌ User ID: {user_id_str}",
                    callback_data=f"disapprove_user_{user_id_str}"
                )])
            keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data='manage_users')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif query.data.startswith('disapprove_user_'):
        user_id_to_remove = int(query.data.replace('disapprove_user_', ''))
        DatabaseManager.disapprove_user(user_id_to_remove)
        keyboard = [[InlineKeyboardButton("🔙 Back to User Management", callback_data='manage_users')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"✅ User <code>{user_id_to_remove}</code> has been disapproved!",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    elif query.data in ['ban_user', 'ban_admin']:
        context.user_data['ban_type'] = 'user' if query.data == 'ban_user' else 'admin'
        await query.edit_message_text(
            f"🚫 <b>Ban {'User' if query.data == 'ban_user' else 'Admin'}</b>\n\n"
            "Send the User ID to ban.\n\n"
            "Type /cancel to abort.",
            parse_mode='HTML'
        )
        return WAITING_BAN_ID

    elif query.data in ['unban_user', 'unban_admin']:
        db_func = DatabaseManager.load_users if query.data == 'unban_user' else DatabaseManager.load_admins
        users_or_admins = db_func()
        
        banned = {uid: data for uid, data in users_or_admins.items() if data.get('banned_until')}
        
        if not banned:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='manage_users' if query.data == 'unban_user' else 'manage_admins')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("No banned users/admins found.", reply_markup=reply_markup)
        else:
            text = f"✅ <b>Unban {'User' if query.data == 'unban_user' else 'Admin'}</b>\n\nSelect to unban:\n\n"
            keyboard = []
            for uid, data in banned.items():
                ban_until = data.get('banned_until', 'Unknown')
                keyboard.append([InlineKeyboardButton(
                    f"✅ ID: {uid} (until {ban_until[:19]})",
                    callback_data=f"unban_{'user' if query.data == 'unban_user' else 'admin'}_{uid}"
                )])
            keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data='manage_users' if query.data == 'unban_user' else 'manage_admins')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif query.data.startswith('unban_user_'):
        user_id_to_unban = int(query.data.replace('unban_user_', ''))
        DatabaseManager.unban_user(user_id_to_unban)
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='manage_users')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"✅ User <code>{user_id_to_unban}</code> has been unbanned!",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    elif query.data.startswith('unban_admin_'):
        admin_id_to_unban = int(query.data.replace('unban_admin_', ''))
        DatabaseManager.unban_admin(admin_id_to_unban)
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='manage_admins')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"✅ Admin <code>{admin_id_to_unban}</code> has been unbanned!",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

  
    elif query.data == 'my_stats':
        users = DatabaseManager.load_users()
        user_data = users.get(str(user_id), {})
        expiry = datetime.fromisoformat(user_data.get('expiry_date', datetime.now().isoformat()))
        days_left = (expiry - datetime.now()).days
        approved_at = user_data.get('approved_at', 'Unknown')
        
      
        attacks = DatabaseManager.load_attacks()
        user_attacks = [a for a in attacks if a['user_id'] == user_id]
        
        sessions = SessionManager.get_all_sessions(user_id)
        
        text = f"""
📊 <b>Your Statistics</b>

<b>Account Info:</b>
👤 User ID: <code>{user_id}</code>
✅ Status: Approved
📅 Approved On: {approved_at[:19]}
⏰ Days Left: <b>{days_left}</b>
📅 Expires: {expiry.strftime('%Y-%m-%d')}

<b>Attack Statistics:</b>
⚔️ Total Attacks: {len(user_attacks)}
📋 Active Sessions: {len(sessions)}

<b>Recent Attacks:</b>
"""
        for i, attack in enumerate(user_attacks[-5:], 1):
            text += f"{i}. {attack['channel_url']} - {attack['status']}\n"
        
        if not user_attacks:
            text += "No attacks yet.\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    # COMMON ACTIONS (based on role)
    elif query.data == 'view_sessions':
        if role == UserRole.UNAPPROVED:
            await query.edit_message_text("❌ Access Denied")
            return ConversationHandler.END
        
        sessions = SessionManager.get_all_sessions(user_id)

        if not sessions:
            await query.edit_message_text("❌ No sessions found.\n\nUse 'Add Session' to add accounts.")
        else:
            text = f"📋 <b>Your Active Sessions ({len(sessions)})</b>\n\n"
            for i, session in enumerate(sessions, 1):
                info = SessionManager.get_session_info(session)
                text += f"{i}. <code>{info['name']}</code>\n   📅 Modified: {info['modified']}\n   📦 Size: {info['size']} bytes\n\n"

            keyboard = [
                [InlineKeyboardButton("➕ Add Session", callback_data='add_session')],
                [InlineKeyboardButton("🗑️ Remove Session", callback_data='remove_session')],
                [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')

    elif query.data == 'add_session':
        if role == UserRole.UNAPPROVED:
            await query.edit_message_text("❌ Access Denied")
            return ConversationHandler.END
        
        await query.edit_message_text(
            "📱 <b>Add New Session</b>\n\n"
            "Please send your phone number with country code.\n"
            "Example: +1234567890\n\n"
            "💡 Tip: Make sure you have access to this phone number to receive OTP.\n\n"
            "Type /cancel to abort."
        , parse_mode='HTML')
        return WAITING_PHONE

    elif query.data == 'remove_session':
        if role == UserRole.UNAPPROVED:
            await query.edit_message_text("❌ Access Denied")
            return ConversationHandler.END
        
        sessions = SessionManager.get_all_sessions(user_id)

        if not sessions:
            keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text("❌ No sessions to remove.", reply_markup=reply_markup)
        else:
            keyboard = []
            for session in sessions:
                info = SessionManager.get_session_info(session)
                keyboard.append([InlineKeyboardButton(
                    f"🗑️ {info['name']}",
                    callback_data=f"delete_{info['name']}"
                )])
            keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data='back_to_menu')])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "🗑️ <b>Remove Session</b>\n\nSelect session to delete:",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

    elif query.data.startswith('delete_'):
        session_name = query.data.replace('delete_', '')
        if SessionManager.delete_session(user_id, session_name):
            keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"✅ Session <code>{session_name}</code> deleted successfully!\n\nAll associated files have been removed.",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text(f"❌ Failed to delete session.")

    elif query.data == 'attack':
        if role == UserRole.UNAPPROVED:
            await query.edit_message_text("❌ Access Denied")
            return ConversationHandler.END
        
        sessions = SessionManager.get_all_sessions(user_id)

        if not sessions:
            keyboard = [[InlineKeyboardButton("➕ Add Session Now", callback_data='add_session')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "❌ <b>No Sessions Available</b>\n\n"
                "Please add at least one session before attacking.\n"
                "Click the button below to add a session.",
                reply_markup=reply_markup,
                parse_mode='HTML'
            )
        else:
            await query.edit_message_text(
                f"⚔️ <b>ATTACK MODE ACTIVATED</b>\n\n"
                f"✅ Your sessions available: {len(sessions)}\n\n"
                f"🎯 Send the target channel URL or username:\n"
                f"   • @channelname\n"
                f"   • https://t.me/channelname\n\n"
                f"💡 Tip: Make sure the channel is public and accessible.\n\n"
                f"Type /cancel to abort.",
                parse_mode='HTML'
            )
            return WAITING_CHANNEL_URL

    elif query.data == 'help':
        help_text = """
📖 <b>ERRORLEAKS x SOULCRACK v1.0 - Help & Instructions</b>

<b>🚀 Quick Start Guide:</b>

<b>1️⃣ Add Sessions</b>
   • Click 'Add Session' button
   • Enter phone number with country code
   • Enter OTP code received via SMS
   • Enter 2FA password if enabled
   • Repeat for multiple accounts

<b>2️⃣ Launch Attack</b>
   • Click 'ATTACK' button
   • Send target channel URL
   • Bot scrapes ALL posts from channel
   • AI analyzes ALL content for violations
   • Review AI findings and post links
   • Enter number of reports to send
   • Watch live progress updates!

<b>3️⃣ Manage Sessions</b>
   • View all your connected accounts
   • Remove sessions you don't need
   • Keep your account list clean

<b>🎯 New in v1.0:</b>
👑 Owner Panel - Full system control
🛡️ Admin Panel - User management
⚔️ User Panel - Personal sessions
🔒 Tiered Permission System
📊 Personal Statistics
🌐 Global Attack Tracking

Type /start to return to main menu.
"""
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='HTML')

    elif query.data == 'back_to_menu':
     
        if role == UserRole.OWNER:
            keyboard = [
                [InlineKeyboardButton("🛡️ Manage Admins", callback_data='manage_admins')],
                [InlineKeyboardButton("👥 Manage Users", callback_data='manage_users')],
                [InlineKeyboardButton("🌐 Global Attack List", callback_data='global_attacks')],
                [InlineKeyboardButton("⚔️ Launch Attack", callback_data='attack')],
                [InlineKeyboardButton("📋 My Sessions", callback_data='view_sessions')],
                [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
            ]
        elif role == UserRole.ADMIN:
            keyboard = [
                [InlineKeyboardButton("👥 Manage Users", callback_data='manage_users')],
                [InlineKeyboardButton("⚔️ Launch Attack", callback_data='attack')],
                [InlineKeyboardButton("📋 My Sessions", callback_data='view_sessions')],
                [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
            ]
        elif role == UserRole.USER:
            keyboard = [
                [InlineKeyboardButton("⚔️ Launch Attack", callback_data='attack')],
                [InlineKeyboardButton("📊 My Stats", callback_data='my_stats')],
                [InlineKeyboardButton("📋 My Sessions", callback_data='view_sessions')],
                [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("📱 Contact Owner", url='https://t.me/soulcracks_owner')]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🤖 <b>Main Menu</b>\n\nSelect an option to continue:",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

    return ConversationHandler.END


async def receive_admin_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
   
    user_id = update.effective_user.id
    role = DatabaseManager.get_user_role(user_id)
    
    if role != UserRole.OWNER:
        await update.message.reply_text("❌ Access Denied")
        return ConversationHandler.END
    
  
    if update.message.forward_from:
        target_id = update.message.forward_from.id
    else:
        try:
            target_id = int(update.message.text.strip())
        except:
            await update.message.reply_text("❌ Invalid User ID. Please send a valid number or forward a message from the user.")
            return WAITING_ADMIN_ID
    
    context.user_data['target_admin_id'] = target_id
    
    await update.message.reply_text(
        f"👤 Target Admin ID: <code>{target_id}</code>\n\n"
        f"How many days should this admin have access?\n\n"
        f"Send number of days (e.g., 30, 90, 365)\n\n"
        f"Type /cancel to abort.",
        parse_mode='HTML'
    )
    return WAITING_ADMIN_DAYS

async def receive_admin_days(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:
        days = int(update.message.text.strip())
        if days <= 0:
            raise ValueError()
    except:
        await update.message.reply_text("❌ Invalid number. Please send a positive number of days.")
        return WAITING_ADMIN_DAYS
    
    target_id = context.user_data['target_admin_id']
    DatabaseManager.approve_admin(target_id, days)
    
    await update.message.reply_text(
        f"✅ <b>Admin Approved!</b>\n\n"
        f"Admin ID: <code>{target_id}</code>\n"
        f"Duration: {days} days\n"
        f"Expires: {(datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')}\n\n"
        f"Type /start to return to menu.",
        parse_mode='HTML'
    )
    
    return ConversationHandler.END


async def receive_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
   
    user_id = update.effective_user.id
    role = DatabaseManager.get_user_role(user_id)
    
    if role not in [UserRole.OWNER, UserRole.ADMIN]:
        await update.message.reply_text("❌ Access Denied")
        return ConversationHandler.END
    
    if update.message.forward_from:
        target_id = update.message.forward_from.id
    else:
        try:
            target_id = int(update.message.text.strip())
        except:
            await update.message.reply_text("❌ Invalid User ID. Please send a valid number or forward a message from the user.")
            return WAITING_USER_ID
    
    context.user_data['target_user_id'] = target_id
    
    await update.message.reply_text(
        f"👤 Target User ID: <code>{target_id}</code>\n\n"
        f"How many days should this user have access?\n\n"
        f"Send number of days (e.g., 7, 30, 90)\n\n"
        f"Type /cancel to abort.",
        parse_mode='HTML'
    )
    return WAITING_USER_DAYS

async def receive_user_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
  
    try:
        days = int(update.message.text.strip())
        if days <= 0:
            raise ValueError()
    except:
        await update.message.reply_text("❌ Invalid number. Please send a positive number of days.")
        return WAITING_USER_DAYS
    
    target_id = context.user_data['target_user_id']
    DatabaseManager.approve_user(target_id, days)
    
    await update.message.reply_text(
        f"✅ <b>User Approved!</b>\n\n"
        f"User ID: <code>{target_id}</code>\n"
        f"Duration: {days} days\n"
        f"Expires: {(datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')}\n\n"
        f"Type /start to return to menu.",
        parse_mode='HTML'
    )
    
    return ConversationHandler.END


async def receive_ban_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
   
    try:
        target_id = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ Invalid User ID. Please send a valid number.")
        return WAITING_BAN_ID
    
    context.user_data['target_ban_id'] = target_id
    
    await update.message.reply_text(
        f"👤 Target ID: <code>{target_id}</code>\n\n"
        f"How long should they be banned?\n\n"
        f"Send duration in hours (e.g., 1, 24, 168 for 1 week)\n\n"
        f"Type /cancel to abort.",
        parse_mode='HTML'
    )
    return WAITING_BAN_DURATION

async def receive_ban_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
   
    try:
        hours = int(update.message.text.strip())
        if hours <= 0:
            raise ValueError()
    except:
        await update.message.reply_text("❌ Invalid number. Please send a positive number of hours.")
        return WAITING_BAN_DURATION
    
    target_id = context.user_data['target_ban_id']
    ban_type = context.user_data.get('ban_type', 'user')
    
    if ban_type == 'admin':
        DatabaseManager.ban_admin(target_id, hours)
    else:
        DatabaseManager.ban_user(target_id, hours)
    
    banned_until = datetime.now() + timedelta(hours=hours)
    
    await update.message.reply_text(
        f"✅ <b>{'Admin' if ban_type == 'admin' else 'User'} Banned!</b>\n\n"
        f"ID: <code>{target_id}</code>\n"
        f"Duration: {hours} hours\n"
        f"Banned Until: {banned_until.strftime('%Y-%m-%d %H:%M')}\n\n"
        f"Type /start to return to menu.",
        parse_mode='HTML'
    )
    
    return ConversationHandler.END


async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    phone = update.message.text.strip()
    user_id = update.effective_user.id

    status_msg = await update.message.reply_text(f"📱 Connecting to Telegram with {phone}...\n⏳ Please wait...")

    try:
        client, session_name = await SessionManager.create_client(user_id, phone)

        await client.send_code_request(phone)

        if user_id not in user_sessions:
            user_sessions[user_id] = {'clients': [], 'data': {}}
        user_sessions[user_id]['temp_client'] = client
        user_sessions[user_id]['temp_phone'] = phone
        user_sessions[user_id]['temp_session'] = session_name

        await status_msg.edit_text(
            "✅ <b>OTP Sent!</b>\n\n"
            "📱 Please check your Telegram app or SMS for the verification code.\n\n"
            "💬 Send the code here (Example: 12345)\n\n"
            "Type /cancel to abort.",
            parse_mode='HTML'
        )
        return WAITING_CODE

    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Error:</b> {str(e)}\n\nPlease try again with /start", parse_mode='HTML')
        return ConversationHandler.END

async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    code = update.message.text.strip()
    user_id = update.effective_user.id

    status_msg = await update.message.reply_text("🔐 Verifying code...\n⏳ Please wait...")

    client = user_sessions[user_id]['temp_client']
    phone = user_sessions[user_id]['temp_phone']

    try:
        await client.sign_in(phone, code)

        if await client.is_user_authorized():
            me = await client.get_me()
            await status_msg.edit_text(
                f"✅ <b>Session Added Successfully!</b>\n\n"
                f"👤 Account: {me.first_name or 'User'}\n"
                f"📱 Phone: {phone}\n\n"
                f"You can now use this account for reporting.\n\n"
                f"Type /start to return to menu.",
                parse_mode='HTML'
            )

            await client.disconnect()
            del user_sessions[user_id]['temp_client']
            del user_sessions[user_id]['temp_phone']
            del user_sessions[user_id]['temp_session']

            return ConversationHandler.END
        else:
            await status_msg.edit_text(
                "🔐 <b>2FA Enabled</b>\n\n"
                "Your account has Two-Factor Authentication enabled.\n\n"
                "💬 Please enter your 2FA password:\n\n"
                "Type /cancel to abort.",
                parse_mode='HTML'
            )
            return WAITING_2FA

    except errors.SessionPasswordNeededError:
        await status_msg.edit_text(
            "🔐 <b>2FA Enabled</b>\n\n"
            "Your account has Two-Factor Authentication enabled.\n\n"
            "💬 Please enter your 2FA password:\n\n"
            "Type /cancel to abort.",
            parse_mode='HTML'
        )
        return WAITING_2FA
    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Error:</b> {str(e)}\n\nPlease try again with /start", parse_mode='HTML')
        return ConversationHandler.END

async def receive_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
   
    password = update.message.text.strip()
    user_id = update.effective_user.id

    status_msg = await update.message.reply_text("🔐 Verifying 2FA password...\n⏳ Please wait...")

    client = user_sessions[user_id]['temp_client']

    try:
        await client.sign_in(password=password)

        if await client.is_user_authorized():
            me = await client.get_me()
            await status_msg.edit_text(
                f"✅ <b>Session Added Successfully!</b>\n\n"
                f"👤 Account: {me.first_name or 'User'}\n"
                f"📱 Phone: {user_sessions[user_id]['temp_phone']}\n"
                f"🔐 2FA: Enabled\n\n"
                f"You can now use this account for reporting.\n\n"
                f"Type /start to return to menu.",
                parse_mode='HTML'
            )

            await client.disconnect()
            del user_sessions[user_id]['temp_client']
            del user_sessions[user_id]['temp_phone']
            del user_sessions[user_id]['temp_session']

            return ConversationHandler.END
        else:
            await status_msg.edit_text("❌ Authentication failed. Please try again with /start")
            return ConversationHandler.END

    except Exception as e:
        await status_msg.edit_text(f"❌ <b>Error:</b> {str(e)}\n\nPlease try again with /start", parse_mode='HTML')
        return ConversationHandler.END


async def receive_channel_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    
    url = update.message.text.strip()
    user_id = update.effective_user.id
    role = DatabaseManager.get_user_role(user_id)
    
   
    if role == UserRole.UNAPPROVED:
        await update.message.reply_text("❌ Access Denied. You are not approved.")
        return ConversationHandler.END

    status_msg = await update.message.reply_text(
        "🔍 <b>Analyzing target channel...</b>\n\n"
        "⏳ Step 1/3: Connecting to Telegram...\n"
        "This may take a moment...",
        parse_mode='HTML'
    )

    try:
        sessions = SessionManager.get_all_sessions(user_id)
        if not sessions:
            await status_msg.edit_text("❌ No active sessions found. Please add a session first.")
            return ConversationHandler.END
            
        client = TelegramClient(str(sessions[0]), API_ID, API_HASH, timeout=30, sequential_updates=True)
        await client.connect()

        if not await client.is_user_authorized():
            await status_msg.edit_text("❌ Session expired or not authorized. Please add a new session with /start")
            await client.disconnect()
            return ConversationHandler.END

        await status_msg.edit_text(
            "📥 <b>Step 2/3: Scraping ALL channel posts...</b>\n\n"
            "⏳ This may take a few minutes for large channels...\n"
            "Getting all posts from the channel...",
            parse_mode='HTML'
        )
        
        channel_data = await ChannelScraper.scrape_channel(client, url)

        await status_msg.edit_text(
            f"🤖 <b>Step 3/3: AI Analysis</b>\n\n"
            f"📊 Analyzing ALL {channel_data['total_posts']} posts together...\n"
            f"⏳ This may take 1-2 minutes for comprehensive analysis...\n\n"
            f"🧠  AI is reviewing ALL content...",
            parse_mode='HTML'
        )

        analyzer = AIAnalyzer()
        ai_result = analyzer.analyze_posts(channel_data['messages'], channel_data['channel_name'])

        report_file = REPORTS_DIR / generate_filename(
            channel_data['channel_name'], 
            ai_result.get('category_name', 'Unknown'), 
            "Analysis"
        )
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump({
                'channel': channel_data['channel_name'],
                'analyzed_at': datetime.now().isoformat(),
                'ai_result': ai_result,
                'channel_data': channel_data
            }, f, indent=2, ensure_ascii=False)

        user_sessions[user_id]['attack_data'] = {
            'channel_name': channel_data['channel_name'],
            'ai_result': ai_result,
            'report_file': str(report_file)
        }

        result_text = f"""
✅ <b>Analysis Complete!</b>

<b>🎯 Target:</b> {channel_data['channel_name']}
<b>📊 Total Posts Scraped:</b> {channel_data['total_posts']}
<b>📝 Posts Analyzed by AI:</b> {channel_data['total_posts']} (ALL POSTS)
<b>🗂️ Data File:</b> {Path(channel_data['data_file']).name}

<b>🤖 AI Analysis Results:</b>
{'🚨' if ai_result.get('violates_policy') else '✅'} <b>Violates Policy:</b> {'Yes' if ai_result.get('violates_policy') else 'No'}
<b>📋 Category:</b> {ai_result.get('category_name', 'N/A')}
<b>🎯 Confidence:</b> {ai_result.get('confidence', 'medium').upper()}
<b>💡 Reason:</b> {ai_result.get('reason', 'N/A')}

<b>🔍 Specific Violations Found:</b>
"""
        for violation in ai_result.get('specific_violations', ['General policy violation']):
            result_text += f"   • {violation}\n"

        result_text += f"""
<b>🔗 Targeted Posts (will be reported):</b>
"""
        targeted_posts_ids = ai_result.get('targeted_posts', [msg['id'] for msg in channel_data['messages'][:5]])
        for post_id in targeted_posts_ids[:5]:
            result_text += f"   • https://t.me/{channel_data['channel_name']}/{post_id}\n"
        if len(targeted_posts_ids) > 5:
            result_text += f"   • ... and {len(targeted_posts_ids) - 5} more posts\n"

        result_text += f"""
<b>💬 AI Generated Report Comments ({len(ai_result.get('report_comments', []))} total):</b>
"""
        comments_to_show = ai_result.get('report_comments', [])
        if comments_to_show:
            for i, comment in enumerate(comments_to_show[:5], 1):
                result_text += f"{i}. {comment[:80]}...\n"
            if len(comments_to_show) > 5:
                result_text += f"   ...and {len(comments_to_show) - 5} more unique comments\n"
        else:
            result_text += "   ⚠️ No comments generated (will use fallback)\n"


        result_text += f"""
<b>👥 Available Accounts:</b> {len(sessions)}

<b>⚔️ Ready to launch attack!</b>
📝 Send the number of reports you want to send.

Example: 100 or 500 or 1000

Type /cancel to abort.
"""

        await status_msg.edit_text(result_text, parse_mode='HTML')
        await client.disconnect()

        return WAITING_REPORT_COUNT

    except Exception as e:
        logger.error(f"Channel analysis error: {e}")
        error_msg = str(e)
        
        if "database is locked" in error_msg.lower():
            await status_msg.edit_text(
                f"❌ <b>Database Lock Error</b>\n\n"
                f"The session database is currently locked.\n\n"
                f"<b>Solutions:</b>\n"
                f"1. Wait a few seconds and try again\n"
                f"2. Remove and re-add the session\n"
                f"3. Restart the bot\n\n"
                f"Type /start to return to menu.",
                parse_mode='HTML'
            )
        elif "can't parse entities" in error_msg.lower() or "entity" in error_msg.lower():
            await status_msg.edit_text(
                f"❌ <b>Message Parsing Error</b>\n\n"
                f"Failed to parse message entities in the channel.\n\n"
                f"This usually means the channel has malformed messages.\n"
                f"The bot has attempted to handle this but the channel may be inaccessible.\n\n"
                f"Type /start to try another channel.",
                parse_mode='HTML'
            )
        else:
            await status_msg.edit_text(
                f"❌ <b>Error analyzing channel</b>\n\n"
                f"Error: {error_msg}\n\n"
                f"Type /start to return to menu.",
                parse_mode='HTML'
            )
        
        return ConversationHandler.END

async def receive_report_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
   
    try:
        count = int(update.message.text.strip())
        if count <= 0:
            raise ValueError("Count must be positive")
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid number.\n\n"
            "Please send a valid positive number.\n"
            "Example: 100"
        )
        return WAITING_REPORT_COUNT

    user_id = update.effective_user.id
    attack_data = user_sessions[user_id]['attack_data']

    sessions = SessionManager.get_all_sessions(user_id)
    
  
    DatabaseManager.log_attack(user_id, attack_data['channel_name'], count, "started")

    await update.message.reply_text(
        f"⚔️ <b>ATTACK INITIATED</b>\n\n"
        f"🎯 Target: <code>{attack_data['channel_name']}</code>\n"
        f"📊 Reports: {count}\n"
        f"👥 Accounts: {len(sessions)}\n"
        f"📋 Category: {attack_data['ai_result']['category_name']}\n"
        f"🎯 Confidence: {attack_data['ai_result'].get('confidence', 'medium').upper()}\n\n"
        f"🚀 Starting mass reporting...\n"
        f"⚡ Live updates will appear below!\n\n"
        f"💡 Check your terminal for detailed Telegram API responses!",
        parse_mode='HTML'
    )

    start_time = time.time()
    stats = await MassReporter.mass_report(
        sessions,
        attack_data['channel_name'],
        attack_data['ai_result'],
        count,
        update
    )

  
    DatabaseManager.update_attack_status(user_id, attack_data['channel_name'], "completed", stats)

    elapsed = time.time() - start_time
    success_rate = (stats['successful'] / max(1, stats['successful'] + stats['failed'])) * 100
    
    progress_percentage = (stats['successful'] / count) * 100
    filled = int(progress_percentage / 5)
    bar = '█' * filled + '░' * (20 - filled)

    result_text = f"""
✅ <b>ATTACK COMPLETED!</b>

<b>📊 Final Results:</b>

[{bar}] {progress_percentage:.1f}%

✅ <b>Successful:</b> {stats['successful']}
❌ <b>Failed:</b> {stats['failed']}
📊 <b>Success Rate:</b> {success_rate:.1f}%
⏱️ <b>Total Time:</b> {elapsed:.1f}s
⚡ <b>Average Speed:</b> {stats['successful']/elapsed:.2f} reports/sec

<b>🎯 Target Details:</b>
• Channel: <code>{attack_data['channel_name']}</code>
• Category: {attack_data['ai_result']['category_name']}
• Confidence: {attack_data['ai_result'].get('confidence', 'medium').upper()}

<b>📁 Reports saved to:</b>
<code>{attack_data['report_file']}</code>

<b>💡 Tip:</b> Check your terminal for detailed Telegram API responses and logging.

Type /start to return to main menu.
"""

    await update.message.reply_text(result_text, parse_mode='HTML')

    final_report_file = REPORTS_DIR / generate_filename(
        attack_data['channel_name'],
        attack_data['ai_result']['category_name'],
        "Complete"
    )
    with open(final_report_file, 'w', encoding='utf-8') as f:
        json.dump({
            'user_id': user_id,
            'channel': attack_data['channel_name'],
            'attack_completed_at': datetime.now().isoformat(),
            'target_count': count,
            'stats': stats,
            'elapsed_time': elapsed,
            'success_rate': success_rate,
            'ai_analysis': attack_data['ai_result']
        }, f, indent=2)
    
    print(f"\n{Fore.GREEN}📁 Final report saved: {final_report_file}{Fore.RESET}\n")

    del user_sessions[user_id]['attack_data']

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
   
    user_id = update.effective_user.id
    
    if user_id in user_sessions:
        if 'temp_client' in user_sessions[user_id]:
            try:
                await user_sessions[user_id]['temp_client'].disconnect()
            except:
                pass
            user_sessions[user_id].pop('temp_client', None)
            user_sessions[user_id].pop('temp_phone', None)
            user_sessions[user_id].pop('temp_session', None)
    
    await update.message.reply_text(
        "❌ <b>Operation cancelled.</b>\n\n"
        "All temporary data has been cleared.\n\n"
        "Type /start to return to main menu.",
        parse_mode='HTML'
    )
    return ConversationHandler.END


def main():
    
    print(f"{Fore.CYAN}{'='*100}")
    print(f"{Fore.YELLOW}🤖 ERRORLEAKS x SOULCRACK v1.0 - AI Mass Reporting Bot + Tiered Permissions")
    print(f"{Fore.CYAN}{'='*100}{Fore.RESET}\n")

    print(f"{Fore.YELLOW}🔧 Setting up AI components...{Fore.RESET}")
    if not OllamaManager.setup():
        print(f"{Fore.RED}❌ Failed to setup AI. Please install Ollama manually.{Fore.RESET}")
        print(f"{Fore.YELLOW}Run: curl -fsSL https://ollama.com/install.sh | sh{Fore.RESET}")
        return

    print(f"\n{Fore.GREEN}✅ All systems ready!{Fore.RESET}")
    print(f"{Fore.CYAN}📁 Data directory: {SCRIPT_DIR}{Fore.RESET}")
    print(f"{Fore.CYAN}👑 Owner ID: {OWNER_ID}{Fore.RESET}")
    print(f"{Fore.CYAN}📊 Logs directory: {LOGS_DIR}{Fore.RESET}")
    print(f"{Fore.CYAN}📋 Reports directory: {REPORTS_DIR}{Fore.RESET}\n")

    application = Application.builder().token(BOT_TOKEN).build()


    admin_approval_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^approve_admin$')],
        states={
            WAITING_ADMIN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_admin_id)],
            WAITING_ADMIN_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_admin_days)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )

   
    user_approval_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^approve_user$')],
        states={
            WAITING_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_id)],
            WAITING_USER_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_user_days)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )

   
    ban_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^ban_(user|admin)$')],
        states={
            WAITING_BAN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_id)],
            WAITING_BAN_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ban_duration)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )
    
   
    add_session_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^add_session$')],
        states={
            WAITING_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            WAITING_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_code)],
            WAITING_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_2fa)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )

 
    attack_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern='^attack$')],
        states={
            WAITING_CHANNEL_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_channel_url)],
            WAITING_REPORT_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_report_count)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )

 
    application.add_handler(CommandHandler('start', start))
    application.add_handler(admin_approval_handler)
    application.add_handler(user_approval_handler)
    application.add_handler(ban_handler)
    application.add_handler(add_session_handler)
    application.add_handler(attack_handler)
    application.add_handler(CallbackQueryHandler(button_handler))

    print(f"{Fore.GREEN}{'='*100}")
    print(f"🚀 Bot is starting...")
    print(f"👑 Owner Mode: Enabled for ID {OWNER_ID}")
    print(f"📱 Telegram responses will be logged here in the terminal")
    print(f"⏹️  Press Ctrl+C to stop")
    print(f"{'='*100}\n{Fore.RESET}")

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}{'='*100}")
        print(f"👋 Bot stopped by user")
        print(f"{'='*100}{Fore.RESET}\n")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        print(f"{Fore.RED}{'='*100}")
        print(f"❌ Fatal error: {e}")
        print(f"{'='*100}{Fore.RESET}\n")
