#!/usr/bin/env python3
"""
SOBRANIE Bot - PythonAnywhere Web App Version
Запускает бота как веб-приложение с автоматическим перезапуском
"""

from flask import Flask, request, jsonify
import threading
import asyncio
import os
import signal
import sys
from dotenv import load_dotenv
import discord
from bot import SobranieBot, DISCORD_TOKEN, GUILD_ID

# Завантажуємо змінні середовища
load_dotenv()

app = Flask(__name__)

# Глобальні змінні для бота
bot_instance = None
bot_thread = None
bot_running = False

def run_bot():
    """Запускає бота в окремому потоці"""
    global bot_instance, bot_running
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        bot_instance = SobranieBot()
        bot_running = True
        
        # Запускаємо бота
        loop.run_until_complete(bot_instance.start(DISCORD_TOKEN))
        
    except Exception as e:
        print(f"❌ Помилка бота: {e}")
        bot_running = False
    finally:
        bot_running = False

def stop_bot():
    """Зупиняє бота"""
    global bot_instance, bot_running
    
    if bot_instance and bot_running:
        try:
            asyncio.create_task(bot_instance.close())
            bot_running = False
            print("✅ Бот зупинено")
        except Exception as e:
            print(f"❌ Помилка зупинки бота: {e}")

@app.route('/')
def index():
    """Головна сторінка - статус бота"""
    global bot_instance, bot_running
    
    status = "🟢 Онлайн" if bot_running and bot_instance and bot_instance.is_ready() else "🔴 Офлайн"
    
    return f"""
    <html>
        <head>
            <title>SOBRANIE Bot Status</title>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                .status {{ font-size: 24px; margin: 20px; }}
                .info {{ margin: 10px; color: #666; }}
            </style>
        </head>
        <body>
            <h1>🏆 SOBRANIE CLAN Bot</h1>
            <div class="status">Статус: {status}</div>
            <div class="info">Guild ID: {GUILD_ID}</div>
            <div class="info">PythonAnywhere Web App</div>
        </body>
    </html>
    """

@app.route('/restart')
def restart_bot():
    """Перезапускає бота"""
    global bot_thread, bot_running
    
    stop_bot()
    
    if bot_thread and bot_thread.is_alive():
        bot_thread.join(timeout=5)
    
    # Запускаємо новий потік
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    return jsonify({"status": "restarting"})

@app.route('/stop')
def stop():
    """Зупиняє бота"""
    stop_bot()
    return jsonify({"status": "stopped"})

@app.route('/start')
def start():
    """Запускає бота"""
    global bot_thread, bot_running
    
    if not bot_running:
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
    
    return jsonify({"status": "starting"})

@app.route('/status')
def status():
    """API для перевірки статусу"""
    global bot_instance, bot_running
    
    bot_status = {
        "running": bot_running,
        "ready": bot_instance.is_ready() if bot_instance else False,
        "guilds": len(bot_instance.guilds) if bot_instance else 0,
        "ping": round(bot_instance.latency * 1000) if bot_instance else 0
    }
    
    return jsonify(bot_status)

# Обробник сигналу для коректного завершення
def signal_handler(sig, frame):
    print("🛑 Отримано сигнал завершення...")
    stop_bot()
    sys.exit(0)

if __name__ == '__main__':
    # Реєструємо обробники сигналів
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("🏆 SOBRANIE Bot - PythonAnywhere Version")
    print("🔄 Запуск веб-сервера...")
    
    # Запускаємо бота в окремому потоці
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаємо Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
