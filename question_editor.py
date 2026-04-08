import discord
from typing import List
import json

class QuestionEditView(discord.ui.View):
    """Інтерактивне редагування питань"""
    def __init__(self, db, guild_id: int, questions: list):
        super().__init__(timeout=None)
        self.db = db
        self.guild_id = guild_id
        self.questions = questions
        
        # Кнопки
        add_btn = discord.ui.Button(
            label="➕ Додати питання",
            style=discord.ButtonStyle.success,
            emoji="➕"
        )
        remove_btn = discord.ui.Button(
            label="➖ Видалити питання",
            style=discord.ButtonStyle.danger,
            emoji="➖"
        )
        reset_btn = discord.ui.Button(
            label="🔄 Скинути до стандартних",
            style=discord.ButtonStyle.secondary,
            emoji="🔄"
        )
        close_btn = discord.ui.Button(
            label="❌ Закрити",
            style=discord.ButtonStyle.secondary,
            emoji="❌"
        )
        
        async def add_callback(interaction: discord.Interaction):
            try:
                modal = AddQuestionModal(self.db, self.guild_id, self.questions)
                await interaction.response.send_modal(modal)
            except Exception as e:
                embed = discord.Embed(
                    title="❌ Помилка",
                    description=f"Не вдалося відкрити форму: {str(e)}",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

        async def remove_callback(interaction: discord.Interaction):
            if not self.questions:
                await interaction.response.send_message("❌ Немає питань для видалення!", ephemeral=True)
                return
            
            view = RemoveQuestionView(self.db, self.guild_id, self.questions)
            embed = discord.Embed(
                title="➖ Видалення питання",
                description="Оберіть питання для видалення:",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        async def reset_callback(interaction: discord.Interaction):
            from config_cog import DEFAULT_QUESTIONS
            await self.db.update_server_config(
                self.guild_id,
                questions_template=json.dumps(DEFAULT_QUESTIONS, ensure_ascii=False)
            )
            
            embed = discord.Embed(
                title="✅ Питання скинуто!",
                description="Встановлено стандартні питання",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        async def close_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=None)
        
        add_btn.callback = add_callback
        remove_btn.callback = remove_callback
        reset_btn.callback = reset_callback
        close_btn.callback = close_callback
        
        self.add_item(add_btn)
        self.add_item(remove_btn)
        self.add_item(reset_btn)
        self.add_item(close_btn)


class AddQuestionModal(discord.ui.Modal):
    def __init__(self, db, guild_id: int, questions: list):
        super().__init__(title="➕ Додати питання")
        self.db = db
        self.guild_id = guild_id
        self.questions = questions
        
        self.question_input = discord.ui.TextInput(
            label="Текст питання",
            style=discord.TextStyle.short,
            placeholder="Наприклад: Чи є у тебе мікрофон?",
            required=True,
            max_length=100
        )
        self.add_item(self.question_input)
        
        # Вибір обов'язковості
        self.required_select = discord.ui.StringSelect(
            placeholder="Обов'язкове?",
            options=[
                discord.SelectOption(label="Так", value="true", description="Питання обов'язкове"),
                discord.SelectOption(label="Ні", value="false", description="Питання не обов'язкове")
            ]
        )
        self.add_item(self.required_select)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Отримуємо поточні питання
            config = await self.db.get_server_config(self.guild_id)
            if config and config['questions_template']:
                current_questions = json.loads(config['questions_template'])
            else:
                from config_cog import DEFAULT_QUESTIONS
                current_questions = DEFAULT_QUESTIONS.copy()
            
            # Додаємо нове питання
            new_id = max(q['id'] for q in current_questions) + 1
            is_required = self.required_select.values[0] == 'true'
            
            current_questions.append({
                'id': new_id,
                'text': self.question_input.value,
                'type': 'long_text',
                'required': is_required
            })
            
            # Зберігаємо
            await self.db.update_server_config(
                self.guild_id,
                questions_template=json.dumps(current_questions, ensure_ascii=False)
            )
            
            embed = discord.Embed(
                title="✅ Питання додано!",
                description=f"**#{new_id}.** {self.question_input.value} {'(обов.)' if is_required else '(необов.)'}",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = discord.Embed(
                title="❌ Помилка",
                description=f"Не вдалося додати питання: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)


class RemoveQuestionView(discord.ui.View):
    def __init__(self, db, guild_id: int, questions: list):
        super().__init__(timeout=None)
        self.db = db
        self.guild_id = guild_id
        self.questions = questions
        
        # Додаємо кнопки для кожного питання (максимум 5)
        for q in questions[:5]:
            btn = discord.ui.Button(
                label=f"#{q['id']} - {q['text'][:30]}...",
                style=discord.ButtonStyle.danger
            )
            
            async def btn_callback(interaction: discord.Interaction, question=q):
                try:
                    # Отримуємо поточні питання
                    config = await self.db.get_server_config(self.guild_id)
                    if config and config['questions_template']:
                        current_questions = json.loads(config['questions_template'])
                    else:
                        return
                    
                    # Видаляємо питання
                    current_questions = [qst for qst in current_questions if qst['id'] != question['id']]
                    
                    # Зберігаємо
                    await self.db.update_server_config(
                        self.guild_id,
                        questions_template=json.dumps(current_questions, ensure_ascii=False)
                    )
                    
                    embed = discord.Embed(
                        title="✅ Питання видалено!",
                        description=f"Питання #{question['id']} видалено",
                        color=discord.Color.green()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    
                except Exception as e:
                    embed = discord.Embed(
                        title="❌ Помилка",
                        description=f"Не вдалося видалити питання: {str(e)}",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            
            btn.callback = lambda i, q=question: btn_callback(i, q)
            self.add_item(btn)
