import threading
import time
import requests
import sys
from flask import Flask, jsonify

# Flask app for health check
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({"status": "ok", "bot": "clan-bot"})

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": time.time()})

def run_web_server():
    app.run(host='0.0.0.0', port=10000, threaded=True)

# Import and run bot
def run_bot():
    try:
        print("Starting clan bot...")
        
        # Add requests to globals before importing bot
        globals()['requests'] = requests
        
        # Read and modify bot.py content to include requests import
        with open('bot.py', 'r', encoding='utf-8') as f:
            bot_content = f.read()
        
        # Add requests import if not present
        if 'import requests' not in bot_content:
            bot_content = 'import requests\n' + bot_content
        
        # Execute modified bot code
        exec(bot_content, globals())
        
    except Exception as e:
        print(f"Bot error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    # Start web server in background
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    
    # Run bot
    run_bot()
