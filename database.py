import aiosqlite
import asyncio
from typing import Optional
import json
from texts import DEFAULT_QUESTIONS

class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.connection: Optional[aiosqlite.Connection] = None
    
    async def connect(self):
        """Підключення до бази даних"""
        self.connection = await aiosqlite.connect(self.db_path)
        self.connection.row_factory = aiosqlite.Row
        await self.create_tables()
    
    async def close(self):
        """Закриття підключення"""
        if self.connection:
            await self.connection.close()
    
    async def create_tables(self):
        """Створення всіх таблиць"""
        cursor = await self.connection.cursor()
        
        # Таблиця заявок
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                discriminator TEXT,
                status TEXT DEFAULT 'на_розгляді',
                answers TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reviewed_by INTEGER,
                reviewed_by_username TEXT,
                decision_date TIMESTAMP,
                rejection_reason TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблиця налаштувань сервера
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS server_config (
                guild_id INTEGER PRIMARY KEY,
                application_channel_id INTEGER,
                application_message_id INTEGER,
                leader_role_id INTEGER,
                candidate_role_id INTEGER,
                member_role_id INTEGER,
                log_channel_id INTEGER,
                announcement_channel_id INTEGER,
                join_role_id INTEGER,
                questions_template TEXT NOT NULL,
                language TEXT DEFAULT 'uk',
                max_active_applications INTEGER DEFAULT 1,
                cooldown_days INTEGER DEFAULT 7
            )
        ''')
        
        # Таблиця логів аудиту
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                target_id INTEGER,
                target_username TEXT,
                details TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблиця активних заявок (для швидкої перевірки)
        await cursor.execute('''
            CREATE TABLE IF NOT EXISTS active_applications (
                user_id INTEGER PRIMARY KEY,
                application_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (application_id) REFERENCES applications(id) ON DELETE CASCADE
            )
        ''')
        
        await self.connection.commit()
        print("✅ База даних ініціалізована")
        
        # Додаємо відсутні колонки до існуючих таблиць
        try:
            await cursor.execute('ALTER TABLE server_config ADD COLUMN announcement_channel_id INTEGER')
        except:
            pass  # Колонка вже існує
        
        try:
            await cursor.execute('ALTER TABLE server_config ADD COLUMN join_role_id INTEGER')
        except:
            pass  # Колонка вже існує
    
    # === Application Methods ===
    
    async def create_application(self, user_id: int, username: str, discriminator: str, 
                                 answers: str, status: str = 'на_розгляді'):
        """Створення нової заявки"""
        cursor = await self.connection.cursor()
        await cursor.execute('''
            INSERT INTO applications (user_id, username, discriminator, answers, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, username, discriminator, answers, status))
        await self.connection.commit()
        return cursor.lastrowid
    
    async def get_application(self, app_id: int):
        """Отримання заявки по ID"""
        cursor = await self.connection.cursor()
        await cursor.execute('SELECT * FROM applications WHERE id = ?', (app_id,))
        return await cursor.fetchone()
    
    async def get_user_active_application(self, user_id: int):
        """Перевірка наявності активної заявки"""
        cursor = await self.connection.cursor()
        await cursor.execute('''
            SELECT a.* FROM applications a
            JOIN active_applications aa ON a.id = aa.application_id
            WHERE aa.user_id = ?
        ''', (user_id,))
        return await cursor.fetchone()
    
    async def get_applications_by_status(self, status: str, limit: int = 50):
        """Отримання заявок за статусом"""
        cursor = await self.connection.cursor()
        await cursor.execute('''
            SELECT * FROM applications 
            WHERE status = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (status, limit))
        return await cursor.fetchall()
    
    async def get_all_applications(self, limit: int = 100):
        """Отримання всіх заявок"""
        cursor = await self.connection.cursor()
        await cursor.execute('''
            SELECT * FROM applications 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        return await cursor.fetchall()
    
    async def update_application_status(self, app_id: int, status: str, 
                                        reviewed_by: int = None, 
                                        reviewed_by_username: str = None,
                                        rejection_reason: str = None):
        """Оновлення статусу заявки"""
        cursor = await self.connection.cursor()
        await cursor.execute('''
            UPDATE applications 
            SET status = ?, 
                reviewed_by = ?, 
                reviewed_by_username = ?,
                rejection_reason = ?,
                decision_date = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (status, reviewed_by, reviewed_by_username, rejection_reason, app_id))
        await self.connection.commit()
    
    async def add_to_active(self, user_id: int, application_id: int):
        """Додавання до активних заявок"""
        cursor = await self.connection.cursor()
        await cursor.execute('''
            INSERT OR REPLACE INTO active_applications (user_id, application_id)
            VALUES (?, ?)
        ''', (user_id, application_id))
        await self.connection.commit()
    
    async def remove_from_active(self, user_id: int):
        """Видалення з активних заявок"""
        cursor = await self.connection.cursor()
        await cursor.execute('''
            DELETE FROM active_applications WHERE user_id = ?
        ''', (user_id,))
        await self.connection.commit()
    
    # === Server Config Methods ===
    
    async def get_server_config(self, guild_id: int):
        """Отримання конфігурації сервера"""
        cursor = await self.connection.cursor()
        await cursor.execute('SELECT * FROM server_config WHERE guild_id = ?', (guild_id,))
        result = await cursor.fetchone()
        return dict(result) if result else None
    
    async def update_server_config(self, guild_id: int, **kwargs):
        """Оновлення конфігурації сервера"""
        cursor = await self.connection.cursor()
        
        # Отримуємо поточні значення
        current = await self.get_server_config(guild_id)
        
        # Додаємо defaults для нових записів
        kwargs_copy = kwargs.copy()
        if not current and 'questions_template' not in kwargs_copy:
            kwargs_copy['questions_template'] = json.dumps(DEFAULT_QUESTIONS, ensure_ascii=False)
        
        if not current:
            # Створюємо новий запис
            fields = 'guild_id, ' + ', '.join(kwargs_copy.keys())
            placeholders = '?,' + ','.join(['?' for _ in kwargs_copy])
            values = [guild_id] + list(kwargs_copy.values())
            await cursor.execute(f'''
                INSERT INTO server_config ({fields}) VALUES ({placeholders})
            ''', values)
        else:
            # Оновлюємо існуючий
            set_clause = ', '.join([f'{key} = ?' for key in kwargs_copy.keys()])
            values = list(kwargs_copy.values()) + [guild_id]
            await cursor.execute(f'''
                UPDATE server_config SET {set_clause} WHERE guild_id = ?
            ''', values)
        
        await self.connection.commit()
    
    # === Audit Log Methods ===
    
    async def log_action(self, guild_id: int, action: str, user_id: int, 
                        username: str, target_id: int = None, 
                        target_username: str = None, details: str = None):
        """Запис дії в лог аудиту"""
        cursor = await self.connection.cursor()
        await cursor.execute('''
            INSERT INTO audit_log (guild_id, action, user_id, username, 
                                  target_id, target_username, details)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (guild_id, action, user_id, username, target_id, target_username, details))
        await self.connection.commit()
    
    async def get_audit_logs(self, guild_id: int, limit: int = 50):
        """Отримання логів аудиту"""
        cursor = await self.connection.cursor()
        await cursor.execute('''
            SELECT * FROM audit_log 
            WHERE guild_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (guild_id, limit))
        return await cursor.fetchall()
    
    # === Statistics ===
    
    async def get_statistics(self, guild_id: int = None):
        """Отримання статистики по заявках"""
        cursor = await self.connection.cursor()
        
        stats = {}
        
        # Загальна кількість
        await cursor.execute('SELECT COUNT(*) as count FROM applications')
        stats['total'] = (await cursor.fetchone())['count']
        
        # По статусах
        for status in ['на_розгляді', 'схвалено', 'відхилено', 'очікує']:
            await cursor.execute('SELECT COUNT(*) as count FROM applications WHERE status = ?', (status,))
            stats[status] = (await cursor.fetchone())['count']
        
        # За сьогодні
        await cursor.execute('''
            SELECT COUNT(*) as count FROM applications 
            WHERE DATE(created_at) = DATE('now')
        ''')
        stats['today'] = (await cursor.fetchone())['count']
        
        return stats
