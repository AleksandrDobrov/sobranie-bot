import discord
from discord import app_commands
from discord.ext import commands
import json
import asyncio
from texts import *

class LeaderPanelCog(commands.Cog):
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db
        self.manage_group = app_commands.Group(name='manage', description='👑 Панель лідера для управління заявками')
    
    async def is_leader(self, interaction: discord.Interaction) -> bool:
        """Перевірка чи користувач є лідером"""
        config = await self.db.get_server_config(interaction.guild_id)
        if not config or not config.get('leader_role_id'):
            return False
        
        leader_role = interaction.guild.get_role(config['leader_role_id'])
        return leader_role and leader_role in interaction.user.roles
    
    @app_commands.check(is_leader)
    async def error_handler(self, interaction: discord.Interaction, error):
        """Обробник помилок доступу"""
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ Недостатньо прав!",
                description=ERROR_NO_PERMISSIONS,
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name='panel', description='👑 Відкрити панель лідера')
    async def panel(self, interaction: discord.Interaction):
        """Відкрити панель лідера"""
        try:
            # Отримуємо статистику
            stats = await self.db.get_statistics()
            
            embed = discord.Embed(
                title=ADMIN_PANEL_TITLE,
                description=ADMIN_PANEL_DESCRIPTION.format(
                    new_count=stats.get('на_розгляді', 0),
                    review_count=stats.get('на_розгляді', 0),
                    approved_today=stats.get('схвалено', 0),
                    rejected_today=stats.get('відхилено', 0)
                ),
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="📊 Загальна статистика",
                value=f"Всього заявок: **{stats.get('total', 0)}**\nСьогодні: **{stats.get('today', 0)}**",
                inline=False
            )
            
            view = discord.ui.View()
            
            # Кнопки фільтрів
            for filter_key, filter_label in ADMIN_FILTER_OPTIONS.items():
                btn = discord.ui.Button(
                    label=filter_label,
                    style=discord.ButtonStyle.secondary
                )
                
                async def filter_callback(interaction: discord.Interaction, f_type=filter_key):
                    await self.show_filtered_applications(interaction, f_type)
                
                btn.callback = lambda i, ft=filter_key: filter_callback(i, ft)
                view.add_item(btn)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Сталася помилка: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def show_filtered_applications(self, interaction: discord.Interaction, filter_type: str):
        """Показати відфільтровані заявки"""
        try:
            if filter_type == 'all':
                apps = await self.db.get_all_applications(limit=25)
                title = "📋 Всі заявки"
            elif filter_type == 'pending':
                apps = await self.db.get_applications_by_status('на_розгляді', limit=25)
                title = "⏳ На розгляді"
            elif filter_type == 'approved':
                apps = await self.db.get_applications_by_status('схвалено', limit=25)
                title = "✅ Схвалені"
            elif filter_type == 'rejected':
                apps = await self.db.get_applications_by_status('відхилено', limit=25)
                title = "❌ Відхилені"
            elif filter_type == 'today':
                cursor = await self.db.connection.cursor()
                await cursor.execute('''
                    SELECT * FROM applications 
                    WHERE DATE(created_at) = DATE('now')
                    ORDER BY created_at DESC
                    LIMIT 25
                ''')
                apps = await cursor.fetchall()
                title = "📅 За сьогодні"
            else:
                apps = []
            
            if not apps:
                embed = discord.Embed(
                    title=title,
                    description="Заявок не знайдено",
                    color=discord.Color.greyple()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Форматуємо список
            applications_text = ""
            for app in apps[:10]:  # Показуємо максимум 10
                status_emoji = {
                    'на_розгляді': '⏳',
                    'схвалено': '✅',
                    'відхилено': '❌',
                    'очікує': '⏸️'
                }.get(app['status'], '⏳')
                
                applications_text += f"{status_emoji} **#{app['id']}** - {app['username']}\n"
                applications_text += f"   Статус: `{app['status']}` | Дата: {app['created_at']}\n\n"
            
            if len(apps) > 10:
                applications_text += f"... і ще {len(apps) - 10} заявок"
            
            embed = discord.Embed(
                title=title,
                description=applications_text,
                color=discord.Color.blue()
            )
            
            view = discord.ui.View()
            
            # Кнопки для кожної заявки (перші 5)
            for app in apps[:5]:
                btn = discord.ui.Button(
                    label=f"#{app['id']} - {app['username'][:20]}",
                    style=discord.ButtonStyle.primary
                )
                
                async def app_callback(interaction: discord.Interaction, app_data=app):
                    await self.show_application_details(interaction, app_data)
                
                btn.callback = lambda i, ad=app: app_callback(i, ad)
                view.add_item(btn)
            
            # Кнопка назад
            back_btn = discord.ui.Button(
                label="🔙 Назад до панелі",
                style=discord.ButtonStyle.secondary
            )
            
            async def back_callback(interaction: discord.Interaction):
                await self.panel(interaction)
            
            back_btn.callback = back_callback
            view.add_item(back_btn)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Сталася помилка: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def show_application_details(self, interaction: discord.Interaction, app: dict):
        """Показати деталі заявки"""
        try:
            answers = json.loads(app['answers'])
            
            status_map = {
                'на_розгляді': (STATUS_UNDER_REVIEW, discord.Color.orange()),
                'схвалено': (STATUS_APPROVED, discord.Color.green()),
                'відхилено': (STATUS_REJECTED, discord.Color.red()),
                'очікує': (STATUS_PENDING, discord.Color.greyple())
            }
            
            status_text, color = status_map.get(app['status'], ('⏳ Невідомо', discord.Color.greyple()))
            
            embed = discord.Embed(
                title=f"📝 Заявка #{app['id']}",
                description=f"**Користувач:** {app['username']}\n**Статус:** {status_text}",
                color=color
            )
            
            # Додаємо відповіді
            for question, answer in answers.items():
                embed.add_field(
                    name=question[:256],
                    value=f"```\n{answer[:1024]}\n```",
                    inline=False
                )
            
            # Додаємо інформацію про рішення
            if app.get('reviewed_by_username'):
                embed.add_field(
                    name="👑 Розглянув",
                    value=f"{app['reviewed_by_username']}\n{app.get('decision_date', '')}",
                    inline=False
                )
            
            if app['status'] == 'відхилено' and app.get('rejection_reason'):
                embed.add_field(
                    name="❌ Причина відхилення",
                    value=f"```\n{app['rejection_reason']}\n```",
                    inline=False
                )
            
            view = discord.ui.View()
            
            # Кнопки дій (тільки якщо на розгляді)
            if app['status'] == 'на_розгляді':
                approve_btn = discord.ui.Button(
                    label="✅ Схвалити",
                    style=discord.ButtonStyle.success,
                    emoji="✅"
                )
                reject_btn = discord.ui.Button(
                    label="❌ Відхилити",
                    style=discord.ButtonStyle.danger,
                    emoji="❌"
                )
                pending_btn = discord.ui.Button(
                    label="⏳ На розгляді",
                    style=discord.ButtonStyle.secondary,
                    emoji="⏳"
                )
                
                async def approve_callback(interaction: discord.Interaction):
                    await self.approve_application(interaction, app['id'])
                
                async def reject_callback(interaction: discord.Interaction):
                    await self.reject_application(interaction, app['id'])
                
                async def pending_callback(interaction: discord.Interaction):
                    await self.set_pending_application(interaction, app['id'])
                
                approve_btn.callback = approve_callback
                reject_btn.callback = reject_callback
                pending_btn.callback = pending_callback
                
                view.add_item(approve_btn)
                view.add_item(reject_btn)
                view.add_item(pending_btn)
            
            # Кнопка назад
            back_btn = discord.ui.Button(
                label="🔙 Назад",
                style=discord.ButtonStyle.secondary
            )
            
            async def back_callback(interaction: discord.Interaction):
                await self.show_filtered_applications(interaction, 'pending')
            
            back_btn.callback = back_callback
            view.add_item(back_btn)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Сталася помилка: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def approve_application(self, interaction: discord.Interaction, app_id: int):
        """Схвалення заявки"""
        try:
            app = await self.db.get_application(app_id)
            
            if not app:
                await interaction.response.send_message(
                    "❌ Заявку не знайдено!",
                    ephemeral=True
                )
                return
            
            if app['status'] != 'на_розгляді':
                await interaction.response.send_message(
                    "❌ Заявка вже оброблена!",
                    ephemeral=True
                )
                return
            
            # Оновлюємо статус
            await self.db.update_application_status(
                app_id,
                'схвалено',
                reviewed_by=interaction.user.id,
                reviewed_by_username=str(interaction.user)
            )
            
            # Видаляємо з активних
            await self.db.remove_from_active(app['user_id'])
            
            # Видаємо роль
            config = await self.db.get_server_config(interaction.guild_id)
            if config and config.get('member_role_id'):
                member_role = interaction.guild.get_role(config['member_role_id'])
                user = interaction.guild.get_member(app['user_id'])
                
                if user and member_role:
                    await user.add_roles(member_role)
                    
                    # Логуємо
                    await self.db.log_action(
                        interaction.guild_id,
                        "role_given",
                        interaction.user.id,
                        str(interaction.user),
                        target_id=app['user_id'],
                        target_username=str(user),
                        details=f"Видано роль {member_role.name}"
                    )
            
            # Логуємо схвалення
            await self.db.log_action(
                interaction.guild_id,
                "application_approved",
                interaction.user.id,
                str(interaction.user),
                target_id=app_id,
                target_username=app['username'],
                details="Заявку схвалено"
            )
            
            # Надсилаємо повідомлення користувачеві
            user = interaction.guild.get_member(app['user_id'])
            if user:
                try:
                    embed = discord.Embed(
                        title="🎉 ВІТАЄМО У SOBRANIE!",
                        description=APPROVAL_MESSAGE.format(
                            role_name=config.get('member_role_id', 'Учасник'),
                            curator_mention=interaction.user.mention
                        ),
                        color=discord.Color.green()
                    )
                    await user.send(embed=embed)
                except:
                    pass  # Не вдалося надіслати DM
            
            # Надсилаємо оголошення в канал оголошень
            if config and config.get('announcement_channel_id'):
                announcement_channel = interaction.guild.get_channel(config['announcement_channel_id'])
                if announcement_channel:
                    embed = discord.Embed(
                        title="🎉 НОВИЙ УЧАСНИК КЛАНУ!",
                        description=f"**{app['username']}** успішно пройшов перевірку та приєднався до **SOBRANIE CLAN**!",
                        color=discord.Color.green()
                    )
                    embed.add_field(
                        name="👑 Лідер, що прийняв",
                        value=interaction.user.mention,
                        inline=True
                    )
                    embed.add_field(
                        name="📅 Дата прийому",
                        value=discord.utils.format_dt(discord.utils.utcnow(), style='D'),
                        inline=True
                    )
                    embed.set_footer(text="SOBRANIE CLAN | Слава Україні!")
                    await announcement_channel.send(embed=embed)
            
            embed = discord.Embed(
                title="✅ Заявку схвалено!",
                description=f"Заявка #{app_id} користувача {app['username']} схвалена!\n\nЙому видано роль учасника.",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Сталася помилка: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def reject_application(self, interaction: discord.Interaction, app_id: int):
        """Відхилення заявки"""
        try:
            # Запитуємо причину
            modal = RejectReasonModal(self.db, app_id)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Сталася помилка: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def set_pending_application(self, interaction: discord.Interaction, app_id: int):
        """Встановити статус 'На розгляді'"""
        try:
            await self.db.update_application_status(
                app_id,
                'на_розгляді',
                reviewed_by=interaction.user.id,
                reviewed_by_username=str(interaction.user)
            )
            
            # Логуємо
            await self.db.log_action(
                interaction.guild_id,
                "application_updated",
                interaction.user.id,
                str(interaction.user),
                target_id=app_id,
                details="Статус змінено на 'На розгляді'"
            )
            
            embed = discord.Embed(
                title="✅ Статус оновлено!",
                description=f"Заявка #{app_id} тепер на розгляді",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Сталася помилка: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='remind', description='🔔 Нагадати про не розглянуті заявки')
    async def remind(self, interaction: discord.Interaction):
        """Нагадати лідерам про не розглянуті заявки"""
        try:
            # Отримуємо не розглянуті заявки
            pending_apps = await self.db.get_applications_by_status('на_розгляді', limit=10)
            
            if not pending_apps:
                embed = discord.Embed(
                    title="ℹ️ Немає не розглянутих заявок",
                    description="Всі заявки оброблені!",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Надсилаємо нагадування в канал логів
            config = await self.db.get_server_config(interaction.guild_id)
            if config and config.get('log_channel_id'):
                log_channel = interaction.guild.get_channel(config['log_channel_id'])
                if log_channel:
                    embed = discord.Embed(
                        title="🔔 Нагадування про не розглянуті заявки",
                        description=f"Лідер {interaction.user.mention} нагадав про {len(pending_apps)} не розглянутих заявок!",
                        color=discord.Color.orange()
                    )
                    
                    apps_list = ""
                    for app in pending_apps[:5]:
                        apps_list += f"• #{app['id']} - {app['username']} ({app['created_at']})\n"
                    
                    if len(pending_apps) > 5:
                        apps_list += f"... і ще {len(pending_apps) - 5}"
                    
                    embed.add_field(
                        name="Не розглянуті заявки",
                        value=apps_list,
                        inline=False
                    )
                    
                    await log_channel.send(embed=embed)
            
            embed = discord.Embed(
                title="✅ Нагадування відправлено!",
                description=f"Надіслано нагадування про {len(pending_apps)} не розглянутих заявок",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Сталася помилка: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


class RejectReasonModal(discord.ui.Modal):
    def __init__(self, db, app_id: int):
        super().__init__(title="❌ Вкажіть причину відхилення")
        self.db = db
        self.app_id = app_id
        
        self.reason_input = discord.ui.TextInput(
            label="Причина відхилення",
            style=discord.TextStyle.long,
            placeholder="Детально опишіть причину відхилення заявки...",
            required=True,
            max_length=500
        )
        self.add_item(self.reason_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Обробка відправленої причини"""
        try:
            app = await self.db.get_application(self.app_id)
            
            if not app:
                await interaction.response.send_message(
                    "❌ Заявку не знайдено!",
                    ephemeral=True
                )
                return
            
            if app['status'] != 'на_розгляді':
                await interaction.response.send_message(
                    "❌ Заявка вже оброблена!",
                    ephemeral=True
                )
                return
            
            # Оновлюємо заявку
            await self.db.update_application_status(
                self.app_id,
                'відхилено',
                reviewed_by=interaction.user.id,
                reviewed_by_username=str(interaction.user),
                rejection_reason=self.reason_input.value
            )
            
            # Видаляємо з активних
            await self.db.remove_from_active(app['user_id'])
            
            # Логуємо
            await self.db.log_action(
                interaction.guild_id,
                "application_rejected",
                interaction.user.id,
                str(interaction.user),
                target_id=self.app_id,
                target_username=app['username'],
                details=f"Відхилено: {self.reason_input.value[:100]}"
            )
            
            # Надсилаємо повідомлення користувачеві
            guild = interaction.guild
            user = guild.get_member(app['user_id'])
            
            if user:
                try:
                    embed = discord.Embed(
                        title="❌ Рішення по твоїй заявці",
                        description=REJECTION_MESSAGE.format(
                            reason=self.reason_input.value
                        ),
                        color=discord.Color.red()
                    )
                    await user.send(embed=embed)
                except:
                    pass  # Не вдалося надіслати DM
            
            # Надсилаємо оголошення в канал оголошень
            config = await self.db.get_server_config(guild.id)
            if config and config.get('announcement_channel_id'):
                announcement_channel = guild.get_channel(config['announcement_channel_id'])
                if announcement_channel:
                    embed = discord.Embed(
                        title="❌ ЗАЯВКА ВІДХИЛЕНА",
                        description=f"Заявка **{app['username']}** була відхилена лідером {interaction.user.mention}.",
                        color=discord.Color.red()
                    )
                    embed.add_field(
                        name="📝 Причина",
                        value=self.reason_input.value[:1024],
                        inline=False
                    )
                    embed.set_footer(text="SOBRANIE CLAN")
                    await announcement_channel.send(embed=embed)
            
            embed = discord.Embed(
                title="❌ Заявку відхилено",
                description=f"Заявка #{self.app_id} відхилена.\n\nКористувач отримав повідомлення з причиною.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Сталася помилка: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
