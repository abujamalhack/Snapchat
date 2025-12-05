from flask import Flask
from threading import Thread
import time
import logging

app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# Ping function to prevent sleep
def ping_server():
    import requests
    while True:
        try:
            requests.get('https://your-repl-name.your-username.repl.co')
        except:
            pass
        time.sleep(300)  # Ping every 5 minutes