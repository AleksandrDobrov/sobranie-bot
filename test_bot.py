#!/usr/bin/env python3
"""
Тестовый запуск бота для отладки
"""

import os
from dotenv import load_dotenv
import discord

# Завантажуємо змінні середовища
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = int(os.getenv('GUILD_ID', 0))

print("🏆 SOBRANIE Bot - Тестовый запуск")
print(f"🔍 Токен: {DISCORD_TOKEN[:20]}..." if DISCORD_TOKEN else "❌ Токен не найден!")
print(f"📝 Guild ID: {GUILD_ID}")

if not DISCORD_TOKEN or DISCORD_TOKEN == 'your_bot_token_here':
    print("❌ ПОМИЛКА: Токен не указан!")
    exit(1)

# Тест подключения к Discord
try:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    
    bot = discord.Client(intents=intents)
    
    @bot.event
    async def on_ready():
        print(f'✅ Бот подключен как: {bot.user}')
        print(f'📊 Серверов: {len(bot.guilds)}')
        await bot.close()
    
    print("🔄 Подключение к Discord...")
    bot.run(DISCORD_TOKEN)
    
except discord.LoginFailure:
    print("❌ ОШИБКА: Токен неверный или просрочен!")
    print("📝 Проверьте токен в Discord Developer Portal")
except Exception as e:
    print(f"❌ Ошибка подключения: {e}")

print("✅ Тест завершен")
