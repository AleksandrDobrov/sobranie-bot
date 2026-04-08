# Vercel Serverless Discord Bot
import json
import os
from discord.ext import commands
import discord

# Глобальные переменные для бота
bot_instance = None

async def handler(request):
    """Vercel serverless handler"""
    global bot_instance
    
    try:
        # Инициализация бота при первом запросе
        if not bot_instance:
            intents = discord.Intents.default()
            intents.message_content = True
            intents.members = True
            
            bot_instance = commands.Bot(
                command_prefix='!',
                intents=intents,
                description='SOBRANIE CLAN Bot'
            )
            
            # Загрузка когов
            await bot_instance.setup_hook()
        
        # Обработка запроса
        if request.method == 'POST':
            data = await request.json()
            
            # Верификация Discord
            signature = request.headers.get('X-Signature-Ed25519')
            timestamp = request.headers.get('X-Signature-Timestamp')
            
            if not signature or not timestamp:
                return {'status': 'missing_headers'}, 400
            
            # Обработка взаимодействия Discord
            if data.get('type') == 1:  # PING
                return {'type': 1}
            
            # Обработка slash команд
            if data.get('type') == 2:  # APPLICATION_COMMAND
                await handle_interaction(data)
                return {'type': 5}  # DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
        
        return {'status': 'ok'}
        
    except Exception as e:
        return {'error': str(e)}, 500

async def handle_interaction(data):
    """Обработка Discord взаимодействий"""
    # Здесь логика обработки команд
    pass

# Vercel entry point
def vercel_handler(request):
    import asyncio
    return asyncio.run(handler(request))
