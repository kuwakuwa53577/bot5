import os
import threading
import aiohttp
import xml.etree.ElementTree as ET
import discord
from discord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask

# --- Flask（簡易Webサーバー：Renderのポート対策） ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# --- Discord Bot の設定 ---
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# 送信先のチャンネルID（環境変数、または直接記述）
TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", "0"))
WEATHER_CITY = "Tokyo"


# --- 各種情報取得の補助関数 ---

async def get_weather():
    url = f"https://wttr.in/{WEATHER_CITY}?format=j1&lang=ja"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    current = data["current_condition"][0]
                    desc = current["lang_ja"][0]["value"]
                    temp = current["temp_C"]
                    return f"📍 **{WEATHER_CITY}の天気:** {desc} / 気温: {temp}℃"
    except Exception:
        pass
    return "📍 天気情報の取得に失敗しました。"

async def get_news():
    news_list = []
    url = "https://www.nhk.or.jp/rss/news/cat0.xml"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    root = ET.fromstring(text)
                    items = root.findall(".//item")[:5]
                    for item in items:
                        title = item.find("title").text
                        link = item.find("link").text
                        news_list.append(f"• [{title}]({link})")
    except Exception:
        pass
    
    if not news_list:
        return "ニュースの取得に失敗しました。"
    return "\n".join(news_list)

async def get_earthquake_info():
    url = "https://www.jma.go.jp/bosai/quake/data/list.json"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        latest = data[0]
                        time = latest.get("at", "不明").replace("T", " ").replace("Z", "")
                        hypo = latest.get("hypo", {}).get("name", "不明")
                        mag = latest.get("mag", "不明")
                        return f"⚠️ **直近の地震情報:**\n発生時刻: {time}\n震源地: {hypo} (M{mag})"
    except Exception:
        pass
    return "地震情報の取得に失敗しました。"


# --- 定期実行するタスク ---

async def job_morning():
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not channel:
        return

    weather = await get_weather()
    news = await get_news()
    quake = await get_earthquake_info()

    embed = discord.Embed(title="🌅 おはようございます！本日の朝刊情報", color=discord.Color.gold())
    embed.add_field(name="天気予報", value=weather, inline=False)
    embed.add_field(name="📰 最新ニュース (上位5件)", value=news, inline=False)
    embed.add_field(name="揺れ情報 (地震)", value=quake, inline=False)
    
    await channel.send("おはようございます！今日も一日頑張りましょう！", embed=embed)

async def job_evening():
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not channel:
        return
    await channel.send("夕方ですね、皆さんも、外出などの際は気を付けてくださいね。")

async def job_night():
    channel = bot.get_channel(TARGET_CHANNEL_ID)
    if not channel:
        return
    await channel.send("夜ですね。ちゃんと皆さんは寝ましょう")


# --- ボット起動イベント ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    # APSchedulerによる日本時間スケジューラー
    scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")
    scheduler.add_job(job_morning, CronTrigger(hour=23, minute=46))
    scheduler.add_job(job_evening, CronTrigger(hour=16, minute=30))
    scheduler.add_job(job_night, CronTrigger(hour=22, minute=0))

    scheduler.start()
    print("⏰ スケジューラーが起動しました（8:00 / 16:30 / 22:00 JST）")

if __name__ == "__main__":
    # Flaskを別スレッドで起動
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("❌ エラー: DISCORD_TOKEN が設定されていません。")
    else:
        bot.run(token)
