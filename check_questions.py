import sqlite3
import json

conn = sqlite3.connect('sobranie_bot.db')
cursor = conn.cursor()

cursor.execute('SELECT questions_template FROM server_config')
result = cursor.fetchone()
questions = json.loads(result[0])

print(f"✅ Всего вопросов: {len(questions)}\n")
for q in questions:
    required = "(обов.)" if q['required'] else "(необов.)"
    print(f"{q['id']}. {q['text']} {required}")

conn.close()
