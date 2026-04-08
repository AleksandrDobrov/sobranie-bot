import discord
from discord import app_commands
from typing import Optional
import json
import asyncio
from texts import *


class ApplicationModal(discord.ui.Modal):
    def __init__(self, db, questions: list = None):
        super().__init__(title=MODAL_TITLE)
        self.db = db
        self.questions = questions or DEFAULT_QUESTIONS
        
        # Додаємо поля форми
        for q in self.questions:
            field = discord.ui.TextInput(
                label=q['text'],
                style=discord.TextStyle.long if q['type'] == 'long_text' else discord.TextStyle.short,
                placeholder="Введіть вашу відповідь...",
                required=q['required'],
                max_length=1000 if q['type'] == 'long_text' else 100
            )
            setattr(self, f'field_{q["id"]}', field)
            self.add_item(field)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Обробка відправленої форми"""
        try:
            # Перевіряємо чи користувач вже подавав заявку
            cursor = await self.db.connection.cursor()
            await cursor.execute('''
                SELECT * FROM applications 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT 1
            ''', (interaction.user.id,))
            
            existing_app = await cursor.fetchone()
            
            if existing_app:
                # Користувач вже подавав заявку
                embed = discord.Embed(
                    title="❌ У тебе вже є заявка!",
                    description=f"**Ти вже подавав заявку!**\\n\\n**Статус:** {existing_app['status']}\\n**Дата подання:** {existing_app['created_at']}\\n\\nТи не можеш подати нову заявку, поки попередня не буде розглянута.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Збираємо відповіді
            answers = {}
            for q in self.questions:
                field = getattr(self, f'field_{q["id"]}')
                if field.value:
                    answers[q['text']] = field.value
            
            # Всі питання заповнені - створюємо заявку
            app_id = await self.db.create_application(
                user_id=interaction.user.id,
                username=str(interaction.user),
                discriminator=interaction.user.discriminator,
                answers=json.dumps(answers, ensure_ascii=False)
            )
            
            # Додаємо до активних
            await self.db.add_to_active(interaction.user.id, app_id)
            
            # Логуємо
            await self.db.log_action(
                interaction.guild_id,
                "application_created",
                interaction.user.id,
                str(interaction.user),
                target_id=app_id,
                details=f"Створено заявку #{app_id}"
            )
            
            # Відправляємо повідомлення лідерам
            config = await self.db.get_server_config(interaction.guild_id)
            if config and config.get('log_channel_id'):
                log_channel = interaction.guild.get_channel(config['log_channel_id'])
                if log_channel:
                    embed = discord.Embed(
                        title="📝 НОВА ЗАЯВКА!",
                        description=f"**{interaction.user.mention}** подав заявку на вступ!",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="ID заявки", value=str(app_id), inline=True)
                    embed.add_field(name="Користувач", value=str(interaction.user), inline=True)
                    embed.add_field(name="Дата", value=discord.utils.format_dt(discord.utils.utcnow(), style='D'), inline=True)
                    
                    # Додаємо короткі відповіді
                    for i, (question, answer) in enumerate(answers.items(), 1):
                        if i <= 5:  # Перші 5 питань
                            embed.add_field(
                                name=question[:256],
                                value=f"```\n{answer[:1024]}\n```",
                                inline=False
                            )
                    
                    view = discord.ui.View()
                    approve_btn = discord.ui.Button(
                        label="✅ Схвалити",
                        style=discord.ButtonStyle.success,
                        custom_id=f"approve_{app_id}"
                    )
                    reject_btn = discord.ui.Button(
                        label="❌ Відхилити",
                        style=discord.ButtonStyle.danger,
                        custom_id=f"reject_{app_id}"
                    )
                    pending_btn = discord.ui.Button(
                        label="⏳ На розгляді",
                        style=discord.ButtonStyle.secondary,
                        custom_id=f"pending_{app_id}"
                    )
                    
                    view.add_item(approve_btn)
                    view.add_item(reject_btn)
                    view.add_item(pending_btn)
                    
                    await log_channel.send(embed=embed, view=view)
            
            # Показуємо успішне повідомлення користувачеві
            embed = discord.Embed(
                title="✅ Заявку подано!",
                description=APPLICATION_SUBMITTED_SUCCESS,
                color=discord.Color.green()
            )
            embed.set_footer(text=f"ID заявки: #{app_id}")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Сталася помилка при створенні заявки: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """Обробка помилок"""
        embed = discord.Embed(
            title="❌ Помилка",
            description=f"Сталася помилка: {str(error)}",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ApplicationCog(app_commands.Group):
    def __init__(self, bot, db):
        super().__init__(name='apply', description='📝 Подати заявку в SOBRANIE')
        self.bot = bot
        self.db = db
    
    @app_commands.command(name='form', description='📝 Заповнити форму заявки')
    async def form(self, interaction: discord.Interaction):
        """Команда для подання заявки"""
        try:
            # Перевіряємо активну заявку
            active_app = await self.db.get_user_active_application(interaction.user.id)
            
            if active_app:
                status_map = {
                    'на_розгляді': STATUS_UNDER_REVIEW,
                    'схвалено': STATUS_APPROVED,
                    'відхилено': STATUS_REJECTED,
                    'очікує': STATUS_PENDING
                }
                
                status_emoji = status_map.get(active_app['status'], '⏳')
                
                embed = discord.Embed(
                    title="❌ У тебе вже є активна заявка!",
                    description=APPLICATION_ALREADY_EXISTS.format(
                        status=f"{status_emoji} {active_app['status']}",
                        created_at=active_app['created_at']
                    ),
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Перевіряємо роль приєднання якщо встановлена
            config = await self.db.get_server_config(interaction.guild_id)
            if config and config.get('join_role_id'):
                join_role = interaction.guild.get_role(config['join_role_id'])
                if join_role and join_role not in interaction.user.roles:
                    embed = discord.Embed(
                        title="❌ Немає доступу",
                        description=f"Для подання заявки потрібна роль {join_role.mention}",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
            
            # Отримуємо налаштування питань
            if config and config.get('questions_template'):
                questions = json.loads(config['questions_template'])
            else:
                questions = DEFAULT_QUESTIONS
            
            # Відкриваємо модальну форму
            modal = ApplicationModal(self.db, questions)
            await interaction.response.send_modal(modal)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Не вдалося відкрити форму: {str(e)}",
                color=discord.Color.red()
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name='status', description='📊 Перевірити статус заявки')
    async def status(self, interaction: discord.Interaction):
        """Перевірка статусу заявки"""
        try:
            # Шукаємо останню заявку користувача
            cursor = await self.db.connection.cursor()
            await cursor.execute('''
                SELECT * FROM applications 
                WHERE user_id = ? 
                ORDER BY created_at DESC 
                LIMIT 1
            ''', (interaction.user.id,))
            
            app = await cursor.fetchone()
            
            if not app:
                embed = discord.Embed(
                    title="ℹ️ У тебе немає заявок",
                    description="Ти ще не подавав заявку в SOBRANIE.\n\nВикористовуй /apply form щоб подати!",
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            status_map = {
                'на_розгляді': (STATUS_UNDER_REVIEW, discord.Color.orange()),
                'схвалено': (STATUS_APPROVED, discord.Color.green()),
                'відхилено': (STATUS_REJECTED, discord.Color.red()),
                'очікує': (STATUS_PENDING, discord.Color.greyple())
            }
            
            status_text, color = status_map.get(app['status'], ('⏳ Невідомо', discord.Color.greyple()))
            
            embed = discord.Embed(
                title=APPLICATION_STATUS_TITLE,
                description=f"**Статус:** {status_text}\n\n**ID заявки:** #{app['id']}\n**Дата подання:** {app['created_at']}",
                color=color
            )
            
            # Додаємо інформацію про рішення
            if app['status'] == 'схвалено':
                embed.add_field(
                    name="✅ Схвалено",
                    value=f"Лідером: {app.get('reviewed_by_username', 'Невідомо')}\nДата: {app.get('decision_date', 'Невідомо')}",
                    inline=False
                )
            elif app['status'] == 'відхилено':
                reason = app.get('rejection_reason', 'Причина не вказана')
                embed.add_field(
                    name="❌ Відхилено",
                    value=f"**Причина:**\n```\n{reason}\n```",
                    inline=False
                )
            
            embed.set_footer(text="SOBRANIE CLAN")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Не вдалося перевірити статус: {str(e)}",
                color=discord.Color.red()
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name='cancel', description='❌ Скасувати активну заявку')
    async def cancel(self, interaction: discord.Interaction):
        """Скасувати активну заявку"""
        try:
            # Отримуємо активну заявку користувача
            active_app = await self.db.get_user_active_application(interaction.user.id)
            
            if not active_app:
                embed = discord.Embed(
                    title="ℹ️ Немає активної заявки",
                    description="У тебе немає активної заявки для скасування.",
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Перевіряємо статус - можна скасувати тільки якщо очікує або на розгляді
            if active_app['status'] not in ['очікує', 'на_розгляді']:
                status_text = {
                    'схвалено': '✅ Схвалено',
                    'відхилено': '❌ Відхилено'
                }.get(active_app['status'], 'Невідомо')
                
                embed = discord.Embed(
                    title="❌ Не можна скасувати",
                    description=f"Заявку зі статусом **{status_text}** не можна скасувати.\n\nВикористовуй /apply status для перевірки статусу.",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Скасовуємо заявку
            await self.db.update_application_status(
                active_app['id'],
                'скасовано',
                reviewed_by=interaction.user.id,
                reviewed_by_username=str(interaction.user)
            )
            
            # Видаляємо з активних
            await self.db.remove_from_active(interaction.user.id, active_app['id'])
            
            # Логуємо
            await self.db.log_action(
                interaction.guild_id,
                "application_cancelled",
                interaction.user.id,
                str(interaction.user),
                target_id=active_app['id'],
                details=f"Користувач скасував заявку #{active_app['id']}"
            )
            
            embed = discord.Embed(
                title="✅ Заявку скасовано!",
                description=f"Заявка #{active_app['id']} була успішно скасована.\n\nТепер ти можеш подати нову заявку.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Не вдалося скасувати заявку: {str(e)}",
                color=discord.Color.red()
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)


class ApplicationButtonView(discord.ui.View):
    """View з кнопкою для подання заявки"""
    def __init__(self, db):
        super().__init__(timeout=None)
        self.db = db
        
        apply_button = discord.ui.Button(
            label="📝 Подати заявку",
            style=discord.ButtonStyle.primary,
            custom_id="sobranie_apply",
            emoji="📝"
        )
        
        async def apply_callback(interaction: discord.Interaction):
            # Перевіряємо активну заявку
            active_app = await self.db.get_user_active_application(interaction.user.id)
            
            if active_app:
                embed = discord.Embed(
                    title="❌ У тебе вже є активна заявка!",
                    description=APPLICATION_ALREADY_EXISTS.format(
                        status=active_app['status'],
                        created_at=active_app['created_at']
                    ),
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Перевіряємо роль приєднання якщо встановлена
            config = await self.db.get_server_config(interaction.guild_id)
            if config and config.get('join_role_id'):
                join_role = interaction.guild.get_role(config['join_role_id'])
                if join_role and join_role not in interaction.user.roles:
                    embed = discord.Embed(
                        title="❌ Немає доступу",
                        description=f"Для подання заявки потрібна роль {join_role.mention}",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
            
            # Отримуємо питання
            if config and config.get('questions_template'):
                questions = json.loads(config['questions_template'])
            else:
                questions = DEFAULT_QUESTIONS
            
            # Відкриваємо форму
            modal = ApplicationModal(self.db, questions)
            await interaction.response.send_modal(modal)
        
        apply_button.callback = apply_callback
        self.add_item(apply_button)


class PersistentApplicationView(discord.ui.View):
    """Постійне повідомлення з формою заявки"""
    def __init__(self, db, bot):
        super().__init__(timeout=None)
        self.db = db
        self.bot = bot
        
        apply_button = discord.ui.Button(
            label="📝 Подати заявку",
            style=discord.ButtonStyle.primary,
            custom_id="sobranie_apply",
            emoji="📝"
        )
        
        async def apply_callback(interaction: discord.Interaction):
            # Перевіряємо активну заявку
            active_app = await self.db.get_user_active_application(interaction.user.id)
            
            if active_app:
                embed = discord.Embed(
                    title="❌ У тебе вже є активна заявка!",
                    description=APPLICATION_ALREADY_EXISTS.format(
                        status=active_app['status'],
                        created_at=active_app['created_at']
                    ),
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Перевіряємо роль приєднання якщо встановлена
            config = await self.db.get_server_config(interaction.guild_id)
            if config and config.get('join_role_id'):
                join_role = interaction.guild.get_role(config['join_role_id'])
                if join_role and join_role not in interaction.user.roles:
                    embed = discord.Embed(
                        title="❌ Немає доступу",
                        description=f"Для подання заявки потрібна роль {join_role.mention}",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
            
            # Отримуємо питання
            if config and config.get('questions_template'):
                questions = json.loads(config['questions_template'])
            else:
                questions = DEFAULT_QUESTIONS
            
            # Відкриваємо форму
            modal = ApplicationModal(self.db, questions)
            await interaction.response.send_modal(modal)
        
        apply_button.callback = apply_callback
        self.add_item(apply_button)
