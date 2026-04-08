import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv
import json

# Імпорт модулів
from database import Database
from config_cog import ConfigCog, DEFAULT_QUESTIONS
from application_cog import ApplicationCog, PersistentApplicationView
from leader_cog import LeaderPanelCog, RejectReasonModal
from texts import *

# Завантажуємо змінні середовища
load_dotenv()

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = int(os.getenv('GUILD_ID', 0))
DATABASE_URL = os.getenv('DATABASE_URL', './sobranie_bot.db')

# Перевірка токену
if not DISCORD_TOKEN or DISCORD_TOKEN == 'your_bot_token_here':
    print("❌ ПОМИЛКА: Вкажіть DISCORD_TOKEN у файлі .env")
    print("📝 Створіть файл .env за прикладом .env.example")
    exit(1)

# Ініціалізація бота
class SobranieBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            description='SOBRANIE CLAN - Бот для управління заявками'
        )
        
        self.db = None
    
    async def setup_hook(self):
        """Початкове налаштування бота"""
        print("🔄 Підключення бази даних...")
        # Підключаємо базу даних
        self.db = Database(DATABASE_URL)
        await self.db.connect()
        print("✅ База даних підключена")
        
        print("🔄 Завантаження когів...")
        # Реєструємо коги
        self.tree.add_command(ConfigCog(self, self.db))
        self.tree.add_command(ApplicationCog(self, self.db))
        await self.add_cog(LeaderPanelCog(self, self.db))
        print("✅ Коги завантажені")
        
        print(f"🔄 Синхронізація команд для гільдії {GUILD_ID}...")
        # Синхронізуємо команди
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            print(f"✅ Синхронізовано {len(synced)} команд для гільдії {GUILD_ID}")
        else:
            synced = await self.tree.sync()
            print(f"✅ Синхронізовано {len(synced)} глобальних команд")
    
    async def on_ready(self):
        """Бот готовий до роботи"""
        print(f'\n{"="*50}')
        print(f'✅ SOBRANIE Bot увійшов як: {self.user}')
        print(f'ID: {self.user.id}')
        print(f'Кількість серверів: {len(self.guilds)}')
        print(f'Кількість учасників: {sum(g.member_count for g in self.guilds)}')
        print(f'{"="*50}\n')
        
        # Змінюємо статус бота
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name="SOBRANIE CLAN | /help"
        )
        await self.change_presence(activity=activity)
        
        # Створюємо повідомлення з формою
        await create_application_message(self)
    
    async def on_member_join(self, member: discord.Member):
        """Автоматичне призначення ролі кандидата новим учасникам"""
        try:
            # Отримуємо налаштування сервера
            config = await self.db.get_server_config(member.guild.id)
            
            if config and config.get('candidate_role_id'):
                candidate_role = member.guild.get_role(config['candidate_role_id'])
                if candidate_role:
                    await member.add_roles(candidate_role)
                    
                    # Логуємо
                    await self.db.log_action(
                        member.guild.id,
                        "role_given",
                        self.user.id,  # бот
                        str(self.user),
                        target_id=member.id,
                        target_username=str(member),
                        details=f"Автоматично видано роль кандидата: {candidate_role.name}"
                    )
                    
                    print(f"✅ Автоматично видано роль кандидата {candidate_role.name} учаснику {member}")
                    
                    # Надсилаємо приветственне повідомлення
                    try:
                        app_channel_id = config.get('application_channel_id')
                        if app_channel_id:
                            embed = discord.Embed(
                                title="👋 Ласкаво просимо до SOBRANIE!",
                                description="Привіт, " + member.mention + "!\\n\\nМи раді бачити тебе на сервері!\\n\\n**📝 Хочеш вступити до клану?**\\nТобі вже видано роль кандидата!\\nНатисни кнопку \"Подати заявку\" у каналі <#" + str(app_channel_id) + ">",
                                color=discord.Color.blue()
                            )
                            await member.send(embed=embed)
                    except Exception as dm_error:
                        print(f"⚠️ Не вдалося надіслати DM: {dm_error}")
        except Exception as e:
            print(f"❌ Помилка при призначенні ролі кандидата: {e}")

    async def on_interaction(self, interaction: discord.Interaction):
        """Обробка інтеракцій (кнопки, меню)"""
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get('custom_id', '')
            
            # Обробка кнопки подання заявки (доступна ВСІМ)
            if custom_id == 'sobranie_apply':
                from application_cog import PersistentApplicationView
                view = PersistentApplicationView(self.db, self)
                await view.apply_button.callback(interaction, None)
                return
            
            # Перевірка прав лідера для інших дій
            config = await self.db.get_server_config(interaction.guild_id)
            is_leader = False
            if config and config.get('leader_role_id'):
                leader_role = interaction.guild.get_role(config['leader_role_id'])
                is_leader = leader_role and leader_role in interaction.user.roles
            
            # Кнопки лідерів (approve/reject/pending)
            if custom_id.startswith('approve_') or custom_id.startswith('reject_') or custom_id.startswith('pending_'):
                if not is_leader:
                    await interaction.response.send_message("❌ Недостатньо прав! Ця дія доступна тільки лідерам.", ephemeral=True)
                    return
                
                if custom_id.startswith('approve_'):
                    app_id = int(custom_id.split('_')[1])
                    leader_cog = self.get_cog('LeaderPanelCog')
                    if leader_cog:
                        await leader_cog.approve_application(interaction, app_id)
                    else:
                        # Якщо cog не знайдено, імпортуємо напряму
                        from leader_cog import LeaderPanelCog
                        leader_panel = LeaderPanelCog(self, self.db)
                        await leader_panel.approve_application(interaction, app_id)
                elif custom_id.startswith('reject_'):
                    app_id = int(custom_id.split('_')[1])
                    modal = RejectReasonModal(self.db, app_id)
                    await interaction.response.send_modal(modal)
                elif custom_id.startswith('pending_'):
                    app_id = int(custom_id.split('_')[1])
                    leader_cog = self.get_cog('LeaderPanelCog')
                    if leader_cog:
                        await leader_cog.set_pending_application(interaction, app_id)
                    else:
                        from leader_cog import LeaderPanelCog
                        leader_panel = LeaderPanelCog(self, self.db)
                        await leader_panel.set_pending_application(interaction, app_id)


async def create_application_message(bot: SobranieBot):
    """Створення постійного повідомлення з формою заявки"""
    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            print("⚠️ Гільдію не знайдено")
            return
        
        config = await bot.db.get_server_config(guild.id)
        if not config or not config.get('application_channel_id'):
            print("⚠️ Канал заявок не налаштовано")
            return
        
        channel = guild.get_channel(config['application_channel_id'])
        if not channel:
            print("⚠️ Канал не знайдено")
            return
        
        # Перевіряємо чи вже є повідомлення
        if config.get('application_message_id'):
            try:
                old_message = await channel.fetch_message(config['application_message_id'])
                # Оновлюємо повідомлення
                embed = discord.Embed(
                    title=APPLICATION_FORM_TITLE,
                    description=APPLICATION_MESSAGE,
                    color=discord.Color.blue()
                )
                embed.set_footer(text="SOBRANIE CLAN | Слава Україні!")
                
                view = PersistentApplicationView(bot.db, bot)
                await old_message.edit(embed=embed, view=view)
                print("✅ Оновлено повідомлення з формою")
                return
            except:
                pass  # Повідомлення видалено, створюємо нове
        
        # Створюємо Embed
        embed = discord.Embed(
            title=APPLICATION_FORM_TITLE,
            description=APPLICATION_MESSAGE,
            color=discord.Color.blue()
        )
        embed.set_footer(text="SOBRANIE CLAN | Слава Україні!")
        
        # Створюємо View з кнопкою
        view = PersistentApplicationView(bot.db, bot)
        
        # Надсилаємо повідомлення
        message = await channel.send(embed=embed, view=view)
        
        # Закріплюємо повідомлення
        await message.pin()
        
        # Зберігаємо ID в БД
        await bot.db.update_server_config(
            guild.id,
            application_message_id=message.id
        )
        
        print(f"✅ Створено повідомлення з формою в каналі #{channel.name}")
        
    except Exception as e:
        print(f"❌ Помилка створення повідомлення: {e}")


async def main():
    """Головна функція"""
    try:
        bot = SobranieBot()
        await bot.start(DISCORD_TOKEN)
    except discord.LoginFailure as e:
        print("\n❌ ПОМИЛКА АВТОРИЗАЦІЇ!")
        print(f"Токен невірний або прострочений")
        print(f"Перевірь токен у файлі .env")
        import sys
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Критична помилка: {e}")
        import traceback
        traceback.print_exc()
        import sys
        sys.exit(1)


if __name__ == '__main__':
    print("\n🏆 SOBRANIE CLAN BOT\n")
    print("🔄 Запуск...")
    
    try:
        # Перевірка змінних середовища
        print(f"🔍 Перевірка токену...")
        if not DISCORD_TOKEN or DISCORD_TOKEN == 'your_bot_token_here':
            print("❌ ПОМИЛКА: Токен не вказано або невірний!")
            print(f"   Поточне значення: {DISCORD_TOKEN[:20]}...")
            exit(1)
        print(f"✅ Токен знайдено (довжина: {len(DISCORD_TOKEN)})")
        print(f"📝 Guild ID: {GUILD_ID}")
        
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Бота зупинено користувачем")
    except Exception as e:
        print(f"\n❌ Критична помилка: {e}")
        import traceback
        traceback.print_exc()
