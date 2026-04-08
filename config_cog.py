import discord
from discord import app_commands
from typing import Optional
import json

from texts import APPLICATION_FORM_TITLE, APPLICATION_MESSAGE, DEFAULT_QUESTIONS

from application_cog import PersistentApplicationView

class LeaderSelect(discord.ui.Select):
    def __init__(self, roles):
        options = [discord.SelectOption(label=role.name, value=str(role.id)) for role in roles if not role.is_default()]
        super().__init__(placeholder="Выбери роль лидера", options=options[:25], min_values=1, max_values=1)  # Discord limit 25 options

    async def callback(self, interaction: discord.Interaction):
        self.view.leader_role = int(self.values[0])
        await interaction.response.defer()

class CandidateSelect(discord.ui.Select):
    def __init__(self, roles):
        options = [discord.SelectOption(label=role.name, value=str(role.id)) for role in roles if not role.is_default()]
        super().__init__(placeholder="Выбери роль кандидата", options=options[:25], min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        self.view.candidate_role = int(self.values[0])
        await interaction.response.defer()

class MemberSelect(discord.ui.Select):
    def __init__(self, roles):
        options = [discord.SelectOption(label=role.name, value=str(role.id)) for role in roles if not role.is_default()]
        super().__init__(placeholder="Выбери роль участника", options=options[:25], min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        self.view.member_role = int(self.values[0])
        await interaction.response.defer()

class SubmitRolesButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Сохранить роли", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        if not self.view.leader_role or not self.view.candidate_role or not self.view.member_role:
            await interaction.response.send_message("Выбери все роли перед сохранением!", ephemeral=True)
            return

        try:
            await self.view.db.update_server_config(
                interaction.guild_id,
                leader_role_id=self.view.leader_role,
                candidate_role_id=self.view.candidate_role,
                member_role_id=self.view.member_role
            )

            embed = discord.Embed(
                title="✅ Ролі налаштовано!",
                description="Роли сохранены через настройку.",
                color=discord.Color.green()
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

            # Логуємо
            await self.view.db.log_action(
                interaction.guild_id,
                "config_changed",
                interaction.user.id,
                str(interaction.user),
                details=f"Ролі через setup: leader={self.view.leader_role}, candidate={self.view.candidate_role}, member={self.view.member_role}"
            )
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Не вдалося зберегти ролі: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

class RoleSetupView(discord.ui.View):
    def __init__(self, db, roles):
        super().__init__()
        self.db = db
        self.leader_role = None
        self.candidate_role = None
        self.member_role = None

        self.add_item(LeaderSelect(roles))
        self.add_item(CandidateSelect(roles))
        self.add_item(MemberSelect(roles))
        self.add_item(SubmitRolesButton())


class ConfigCog(app_commands.Group):
    def __init__(self, bot, db):
        super().__init__(name='config', description='⚙️ Налаштування бота SOBRANIE')
        self.bot = bot
        self.db = db
    
    async def is_leader(self, interaction: discord.Interaction) -> bool:
        """Перевірка чи користувач є лідером"""
        config = await self.db.get_server_config(interaction.guild_id)
        if not config or not config['leader_role_id']:
            return False
        
        leader_role = interaction.guild.get_role(config['leader_role_id'])
        return leader_role in interaction.user.roles
    
    @app_commands.check(is_leader)
    @app_commands.default_permissions(administrator=True)
    async def error_handler(self, interaction: discord.Interaction, error):
        """Обробник помилок доступу"""
        if isinstance(error, app_commands.CheckFailure):
            embed = discord.Embed(
                title="❌ Недостатньо прав!",
                description="Ця команда доступна тільки для лідерів клану.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name='setup', description='🔧 Початкове налаштування бота')
    async def setup(self, interaction: discord.Interaction):
        """Початкове налаштування"""
        embed = discord.Embed(
            title="⚙️ Налаштування SOBRANIE Bot",
            description="""
**Ласкаво просимо до системи налаштувань!**

Для повної роботи бота потрібно налаштувати:

**📁 Канали:**
• Канал для заявок - де буде форма з кнопкою

**🎭 Ролі:**
• Роль лідера - хто може розглядати заявки
• Роль кандидата - видається при поданні заявки
• Роль учасника - видається після схвалення

**🇺🇦 Мова:**
• Українська (за замовчуванням)

**Обери що налаштувати першим:**
            """,
            color=discord.Color.blue()
        )
        
        view = discord.ui.View()
        
        # Кнопки для вибору що налаштовувати
        channels_btn = discord.ui.Button(
            label="📁 Канали",
            style=discord.ButtonStyle.primary,
            emoji="📁"
        )
        roles_btn = discord.ui.Button(
            label="🎭 Ролі",
            style=discord.ButtonStyle.primary,
            emoji="🎭"
        )
        questions_btn = discord.ui.Button(
            label="📝 Питання",
            style=discord.ButtonStyle.primary,
            emoji="📝"
        )
        
        async def channels_callback(interaction: discord.Interaction):
            await interaction.response.send_message(
                "📁 **Налаштування каналів**\n\nНапишіть ID каналу або згадайте його (#канал)",
                ephemeral=True
            )
            
            def check(m):
                return m.author == interaction.user and m.channel == interaction.channel
            
            try:
                msg = await self.bot.wait_for('message', timeout=60.0, check=check)
                
                # Парсимо згадку каналу або ID
                channel_id = None
                if msg.channel_mentions:
                    channel_id = msg.channel_mentions[0].id
                elif msg.content.isdigit():
                    channel_id = int(msg.content)
                
                if channel_id:
                    await self.db.update_server_config(
                        interaction.guild_id,
                        application_channel_id=channel_id
                    )
                    
                    await msg.reply(f"✅ Канал для заявок налаштовано: <#{channel_id}>")
                    
                    # Логуємо дію
                    await self.db.log_action(
                        interaction.guild_id,
                        "config_changed",
                        interaction.user.id,
                        str(interaction.user),
                        details=f"Налаштовано канал заявок: {channel_id}"
                    )
                else:
                    await msg.reply("❌ Не вдалося розпізнати канал. Спробуйте ще раз.")
                    
            except asyncio.TimeoutError:
                await interaction.followup.send("⏰ Час очікування минув.", ephemeral=True)
        
        async def roles_callback(interaction: discord.Interaction):
            embed = discord.Embed(
                title="🎭 Налаштування ролей",
                description="Выбери роли из списков ниже и нажми 'Сохранить роли'",
                color=discord.Color.blue()
            )
            view = RoleSetupView(self.db, interaction.guild.roles)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        async def questions_callback(interaction: discord.Interaction):
            await interaction.response.send_message(
                "📝 **Налаштування питань**\n\nСтандартні питання вже налаштовані.\n\nХочете додати свої? Напишіть `так` або `ні`",
                ephemeral=True
            )
        
        channels_btn.callback = channels_callback
        roles_btn.callback = roles_callback
        questions_btn.callback = questions_callback
        
        view.add_item(channels_btn)
        view.add_item(roles_btn)
        view.add_item(questions_btn)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @app_commands.command(name='channels', description='📁 Налаштувати канали')
    async def channels(self, interaction: discord.Interaction, 
                      application_channel: discord.TextChannel = None):
        """Налаштування каналів"""
        try:
            if not application_channel:
                embed = discord.Embed(
                    title="❌ Помилка",
                    description="Вкажіть канал: `/config channels #каналь`",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            await self.db.update_server_config(
                interaction.guild_id,
                application_channel_id=application_channel.id
            )
            
            embed = discord.Embed(
                title="✅ Канал налаштовано!",
                description=f"Канал для заявок: {application_channel.mention}",
                color=discord.Color.green()
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=False)
            
            # Логуємо
            await self.db.log_action(
                interaction.guild_id,
                "config_changed",
                interaction.user.id,
                str(interaction.user),
                details=f"Канал заявок: {application_channel.id}"
            )
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Не вдалося налаштувати канал: {str(e)}",
                color=discord.Color.red()
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name='roles', description='🎭 Налаштувати ролі')
    async def roles(self, interaction: discord.Interaction,
                   leader_role: discord.Role = None,
                   candidate_role: discord.Role = None,
                   member_role: discord.Role = None):
        """Налаштування ролей"""
        try:
            updates = {}
            
            if leader_role:
                updates['leader_role_id'] = leader_role.id
            if candidate_role:
                updates['candidate_role_id'] = candidate_role.id
            if member_role:
                updates['member_role_id'] = member_role.id
            
            if not updates:
                embed = discord.Embed(
                    title="❌ Помилка",
                    description="Вкажіть хоча б одну роль:\n`/config roles @лідер @кандидат @учасник`",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            await self.db.update_server_config(interaction.guild_id, **updates)
            
            embed = discord.Embed(
                title="✅ Ролі налаштовано!",
                description="Оновлено:",
                color=discord.Color.green()
            )
            
            for role_name, role_id in updates.items():
                role = interaction.guild.get_role(role_id)
                if role:
                    embed.add_field(
                        name=f"{'👑' if 'leader' in role_name else '🎯' if 'candidate' else '⭐'} {role.name}",
                        value=f"ID: `{role_id}`",
                        inline=False
                    )
            
            await interaction.response.send_message(embed=embed, ephemeral=False)
            
            # Логуємо
            await self.db.log_action(
                interaction.guild_id,
                "config_changed",
                interaction.user.id,
                str(interaction.user),
                details=f"Ролі: {updates}"
            )
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Не вдалося налаштувати ролі: {str(e)}",
                color=discord.Color.red()
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name='questions', description='📝 Керування питаннями')
    async def questions(self, interaction: discord.Interaction):
        """Керування питаннями у формі"""
        try:
            config = await self.db.get_server_config(interaction.guild_id)
            
            # Отримуємо поточні питання
            if config and config['questions_template']:
                current_questions = json.loads(config['questions_template'])
            else:
                current_questions = DEFAULT_QUESTIONS.copy()
            
            # Форматуємо список питань
            questions_text = "\n".join([
                f"**{q['id']}.** {q['text']} {'(обов.)' if q['required'] else '(необов.)'}"
                for q in current_questions
            ])
            
            embed = discord.Embed(
                title="📝 Керування питаннями",
                description=f"**Поточні питання:**\n\n{questions_text}\n\n**Оберіть дію:**",
                color=discord.Color.blue()
            )
            
            from question_editor import QuestionEditView
            view = QuestionEditView(self.db, interaction.guild_id, current_questions)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Не вдалося завантажити питання: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name='show', description='📊 Показати поточні налаштування')
    async def show(self, interaction: discord.Interaction):
        """Показати поточні налаштування"""
        try:
            config = await self.db.get_server_config(interaction.guild_id)
            
            if not config:
                embed = discord.Embed(
                    title="⚠️ Бот не налаштований",
                    description="Використовуйте `/config setup` для початкового налаштування",
                    color=discord.Color.orange()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Форматуємо налаштування
            app_channel = interaction.guild.get_channel(config.get('application_channel_id'))
            log_channel = interaction.guild.get_channel(config.get('log_channel_id'))
            announcement_channel = interaction.guild.get_channel(config.get('announcement_channel_id'))
            leader_role = interaction.guild.get_role(config.get('leader_role_id'))
            candidate_role = interaction.guild.get_role(config.get('candidate_role_id'))
            member_role = interaction.guild.get_role(config.get('member_role_id'))
            join_role = interaction.guild.get_role(config.get('join_role_id'))
            
            embed = discord.Embed(
                title="⚙️ Поточні налаштування SOBRANIE",
                description=f"Сервер: **{interaction.guild.name}**",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="📁 Канали",
                value=f"""
Заявки: {app_channel.mention if app_channel else '❌ Не налаштовано'}
Лог: {log_channel.mention if log_channel else '❌ Не налаштовано'}
Оголошення: {announcement_channel.mention if announcement_channel else '❌ Не налаштовано'}
                """,
                inline=False
            )
            
            embed.add_field(
                name="🎭 Ролі",
                value=f"""
Лідер: {leader_role.mention if leader_role else '❌'}
Кандидат: {candidate_role.mention if candidate_role else '❌'}
Учасник: {member_role.mention if member_role else '❌'}
Приєднання: {join_role.mention if join_role else '❌'}
                """,
                inline=False
            )
            
            embed.add_field(
                name="⚙️ Інше",
                value=f"""
Мова: 🇺🇦 Українська
Активних заявок: {config.get('max_active_applications', 1)}
Кулдаун: {config.get('cooldown_days', 7)} днів
                """,
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Не вдалося показати налаштування: {str(e)}",
                color=discord.Color.red()
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name='join_role', description='🎭 Налаштувати роль приєднання')
    async def join_role(self, interaction: discord.Interaction, 
                        role: discord.Role = None):
        """Налаштування ролі, що видається автоматично при приєднанні"""
        try:
            if role is None:
                # Очищуємо роль приєднання
                await self.db.update_server_config(
                    interaction.guild_id,
                    join_role_id=None
                )
                
                embed = discord.Embed(
                    title="✅ Роль приєднання очищено!",
                    description="Тепер всі можуть подавати заявки без ролі.",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed, ephemeral=False)
                return
            
            await self.db.update_server_config(
                interaction.guild_id,
                join_role_id=role.id
            )
            
            embed = discord.Embed(
                title="✅ Роль приєднання налаштовано!",
                description=f"Нова роль приєднання: {role.mention}",
                color=discord.Color.green()
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=False)
            
            # Логуємо
            await self.db.log_action(
                interaction.guild_id,
                "config_changed",
                interaction.user.id,
                str(interaction.user),
                details=f"Роль приєднання: {role.id}"
            )
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Не вдалося налаштувати роль: {str(e)}",
                color=discord.Color.red()
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name='log_channel', description='📋 Налаштувати канал логів')
    async def log_channel(self, interaction: discord.Interaction, 
                         channel: discord.TextChannel = None):
        """Налаштування каналу для логів та повідомлень лідерам"""
        try:
            if not channel:
                embed = discord.Embed(
                    title="❌ Помилка",
                    description="Вкажіть канал: `/config log_channel #канал`",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            await self.db.update_server_config(
                interaction.guild_id,
                log_channel_id=channel.id
            )
            
            embed = discord.Embed(
                title="✅ Канал логів налаштовано!",
                description=f"Канал для логів та повідомлень лідерам: {channel.mention}",
                color=discord.Color.green()
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=False)
            
            # Логуємо
            await self.db.log_action(
                interaction.guild_id,
                "config_changed",
                interaction.user.id,
                str(interaction.user),
                details=f"Канал логів: {channel.id}"
            )
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Не вдалося налаштувати канал: {str(e)}",
                color=discord.Color.red()
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name='announcement_channel', description='📢 Налаштувати канал оголошень')
    async def announcement_channel(self, interaction: discord.Interaction, 
                                  channel: discord.TextChannel = None):
        """Налаштування каналу для оголошень"""
        try:
            if not channel:
                embed = discord.Embed(
                    title="❌ Помилка",
                    description="Вкажіть канал: `/config announcement_channel #канал`",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            await self.db.update_server_config(
                interaction.guild_id,
                announcement_channel_id=channel.id
            )
            
            embed = discord.Embed(
                title="✅ Канал оголошень налаштовано!",
                description=f"Канал для оголошень: {channel.mention}",
                color=discord.Color.green()
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=False)
            
            # Логуємо
            await self.db.log_action(
                interaction.guild_id,
                "config_changed",
                interaction.user.id,
                str(interaction.user),
                details=f"Канал оголошень: {channel.id}"
            )
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Не вдалося налаштувати канал: {str(e)}",
                color=discord.Color.red()
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
    
    @app_commands.command(name='create_message', description='📢 Створити повідомлення з формою заявки')
    async def create_message(self, interaction: discord.Interaction):
        """Створити повідомлення з формою заявки"""
        try:
            config = await self.db.get_server_config(interaction.guild_id)
            
            if not config or not config.get('application_channel_id'):
                embed = discord.Embed(
                    title="❌ Канал не налаштовано",
                    description="Спочатку налаштуйте канал командою `/config channels #канал`",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            guild = interaction.guild
            channel = guild.get_channel(config['application_channel_id'])
            if not channel:
                embed = discord.Embed(
                    title="❌ Канал не знайдено",
                    description="Перевірте налаштування каналу",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
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
                    
                    view = PersistentApplicationView(self.db, self.bot)
                    await old_message.edit(embed=embed, view=view)
                    embed = discord.Embed(
                        title="✅ Повідомлення оновлено",
                        description=f"Повідомлення в {channel.mention} оновлено",
                        color=discord.Color.green()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
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
            
            view = PersistentApplicationView(self.db, self.bot)
            message = await channel.send(embed=embed, view=view)
            
            # Закріплюємо повідомлення
            await message.pin()
            
            # Зберігаємо ID в БД
            await self.db.update_server_config(
                guild.id,
                application_message_id=message.id
            )
            
            embed = discord.Embed(
                title="✅ Повідомлення створено",
                description=f"Повідомлення в {channel.mention} створено та закріплено",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Не вдалося створити повідомлення: {str(e)}",
                color=discord.Color.red()
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
