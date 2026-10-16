import os
import threading
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo
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

TARGET_CHANNEL_ID = int(os.environ.get("TARGET_CHANNEL_ID", "0"))
JST = ZoneInfo("Asia/Tokyo")


# --- 各種情報取得の補助関数（安定版） ---

async def get_weather():
    # 東京のcityコード（130010）を指定して日本の天気APIから取得
    url = "https://weather.tsukumijima.net/api/forecast/city/130010"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    forecasts = data.get("forecasts", [])
                    if forecasts:
                        today = forecasts[0]
                        telop = today.get("telop", "不明")
                        
                        # 気温情報（最高/最低）を取得
                        temp_data = today.get("temperature", {})
                        max_temp = temp_data.get("max", {}).get("celsius", "-")
                        min_temp = temp_data.get("min", {}).get("celsius", "-")
                        
                        return f"📍 **東京の天気:** {telop} / 気温: 最低 {min_temp}℃ / 最高 {max_temp}℃"
                else:
                    print(f"⚠️ 天気APIステータスコード: {resp.status}")
    except Exception as e:
        print(f"❌ 天気取得エラー詳細: {e}")
    return "📍 天気情報の取得に失敗しました。"

async def get_news():
    news_list = []
    url = "https://www.nhk.or.jp/rss/news/cat0.xml"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    root = ET.fromstring(text)
                    items = root.findall(".//item")[:5]
                    for item in items:
                        title = item.find("title").text
                        link = item.find("link").text
                        news_list.append(f"• [{title}]({link})")
    except Exception as e:
        print(f"❌ ニュース取得エラー: {e}")
    
    if not news_list:
        return "ニュースの取得に失敗しました。"
    return "\n".join(news_list)

async def get_earthquake_info():
    url = "https://api.p2pquake.net/v2/history?codes=551&limit=1"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        latest = data[0]
                        earthquake = latest.get("earthquake", {})
                        time = earthquake.get("time", "不明")
                        hypo = earthquake.get("hypocenter", {}).get("name", "不明")
                        mag = earthquake.get("hypocenter", {}).get("magnitude", "不明")
                        return f"⚠️ **直近の地震情報:**\n発生時刻: {time}\n震源地: {hypo} (M{mag})"
    except Exception as e:
        print(f"❌ 地震情報取得エラー: {e}")
    return "直近の地震情報の取得に失敗しました。"


# --- 定期実行するタスク ---

async def get_target_channel():
    try:
        channel = bot.get_channel(TARGET_CHANNEL_ID)
        if not channel:
            channel = await bot.fetch_channel(TARGET_CHANNEL_ID)
        return channel
    except Exception as e:
        print(f"❌ チャンネルの取得に失敗しました: {e}")
        return None

async def job_morning():
    print(f"⏰ [JST {datetime.now(JST)}] job_morning が実行されました！")
    channel = await get_target_channel()
    if not channel:
        print("❌ 通知先チャンネルが見つかりませんでした。")
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
    print(f"⏰ [JST {datetime.now(JST)}] job_evening が実行されました！")
    channel = await get_target_channel()
    if not channel:
        return
    await channel.send("夕方ですね、皆さんも、外出などの際は気を付けてくださいね。")

async def job_night():
    print(f"⏰ [JST {datetime.now(JST)}] job_night が実行されました！")
    channel = await get_target_channel()
    if not channel:
        return
    await channel.send("夜ですね。ちゃんと皆さんは寝ましょう")


# --- ボット起動イベント ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    now_jst = datetime.now(JST)
    print(f"🌍 現在の日本時間(JST): {now_jst.strftime('%Y-%m-%d %H:%M:%S')}")

    scheduler = AsyncIOScheduler(timezone=JST)
    scheduler.add_job(job_morning, CronTrigger(hour=0, minute=13, timezone=JST))
    scheduler.add_job(job_evening, CronTrigger(hour=16, minute=30, timezone=JST))
    scheduler.add_job(job_night, CronTrigger(hour=22, minute=0, timezone=JST))

    scheduler.start()
    print("⏰ スケジューラーがJST基準で起動しました（8:00 / 16:30 / 22:00）")

if __name__ == "__main__":
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("❌ エラー: DISCORD_TOKEN が設定されていません。")
    else:
        bot.run(token)
