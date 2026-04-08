import sqlite3
import json

# Підключення до БД
conn = sqlite3.connect('sobranie_bot.db')
cursor = conn.cursor()

# Нові питання
new_questions = [
    {"id": 1, "text": "Який в тебе нік в грі?", "type": "short_text", "required": True},
    {"id": 2, "text": "🏓 Напиши свій ігровий ІД:", "type": "short_text", "required": True},
    {"id": 3, "text": "Був колись в клані ?❤️", "type": "short_text", "required": True},
    {"id": 4, "text": "Знаєш правила кланів? Так/ні ?️", "type": "short_text", "required": True},
    {"id": 5, "text": "Скільки часу будеш з нами проводити?", "type": "long_text", "required": True}
]

# Оновлюємо всі записи
cursor.execute('UPDATE server_config SET questions_template = ?', (json.dumps(new_questions, ensure_ascii=False),))
conn.commit()

print("✅ Питання оновлено в базі даних!")
print(f"Оновлено {cursor.rowcount} запис(ів)")

conn.close()
