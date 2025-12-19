import discord
import os
import google.generativeai as genai
from dotenv import load_dotenv
import PIL.Image
import io
import time
import random
from datetime import datetime, timezone, timedelta # 【新增】時間處理套件
from keep_alive import keep_alive

# ==========================================
# 1. 初始設定 & 金鑰讀取
# ==========================================
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# 【專屬設定】指定的主人 ID
YOUR_ADMIN_ID = 495464747848695808

# 【新增】營業時間設定 (24小時制)
OPEN_HOUR = 8   # 早上 8 點開始
CLOSE_HOUR = 24 # 晚上 11 點結束 (23:00)

if not DISCORD_TOKEN or not GEMINI_API_KEY:
    print("❌ 錯誤：請檢查 .env 檔案，Token 或 API Key 遺失！")

genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 2. 模型選擇
# ==========================================
try:
    model_name = 'gemini-2.5-flash-lite'
    model = genai.GenerativeModel(model_name)
    print(f"✅ 成功載入模型：{model_name}")
except Exception as e:
    print(f"⚠️ 1.5-flash 載入失敗，切換為 gemini-pro。原因：{e}")
    model = genai.GenerativeModel('gemini-2.5-flash')

# ==========================================
# 3. 機器人權限設定
# ==========================================
intents = discord.Intents.all()
client = discord.Client(intents=intents)

user_cooldowns = {}

@client.event
async def on_ready():
    print(f'------------------------------------------')
    print(f'🍯 蜂蜜水 上線！(營業時間: {OPEN_HOUR}:00 ~ {CLOSE_HOUR}:00)')
    print(f'👑 認證主人 ID: {YOUR_ADMIN_ID}')
    print(f'------------------------------------------')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # =================================================================
    # 【功能 A】管理員指令 !say (不受時間限制，隨時可用)
    # =================================================================
    if message.content.startswith('!say '):
        is_owner = (message.author.id == YOUR_ADMIN_ID)
        is_admin = message.author.guild_permissions.administrator
        
        if is_owner or is_admin:
            say_content = message.content[5:]
            if say_content:
                await message.channel.send(say_content)
            try:
                await message.delete()
            except Exception:
                pass
            return
        else:
            return

    # =================================================================
    # 【功能 B】營業時間檢查 (Time Check)
    # =================================================================
    # 1. 取得現在的台灣時間
    tz = timezone(timedelta(hours=8)) # UTC+8
    now = datetime.now(tz)
    current_hour = now.hour

    # 2. 檢查是否在營業時間內
    # 邏輯：如果 現在時間 小於 開門時間 或者 現在時間 大於等於 打烊時間 -> 睡覺
    if current_hour < OPEN_HOUR or current_hour >= CLOSE_HOUR:
        # 如果有人在非營業時間 Tag 機器人，偶爾回個睡覺訊息 (避免完全死機沒反應)
        # 但不要每次都回，設個 10% 機率回覆，才不會半夜被洗版
        if client.user in message.mentions and random.random() < 0.1:
            await message.channel.send("呼...呼...💤 (蜂蜜水睡著了，明天早上再來吧...)")
        
        # 這裡直接 return，不讓程式往下執行 AI 邏輯
        return 
    # =================================================================

    # =================================================================
    # 【功能 C】AI 聊天邏輯 (只有營業時間內會執行到這裡)
    # =================================================================
    is_mentioned = client.user in message.mentions
    is_reply_to_me = False
    
    if message.reference:
        try:
            ref_msg = message.reference.resolved
            if ref_msg is None:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
            if ref_msg.author == client.user:
                is_reply_to_me = True
        except Exception:
            pass

    if not is_mentioned and not is_reply_to_me:
        return

    # 冷卻檢查
    user_id = message.author.id
    current_time_stamp = time.time()
    if user_id in user_cooldowns and (current_time_stamp - user_cooldowns[user_id] < 3):
        try:
            await message.add_reaction('⏳') 
        except:
            pass
        return 
    user_cooldowns[user_id] = current_time_stamp

    try:
        async with message.channel.typing():
            image_input = None
            if message.attachments:
                for attachment in message.attachments:
                    if attachment.content_type and attachment.content_type.startswith('image/'):
                        try:
                            image_bytes = await attachment.read()
                            image_input = PIL.Image.open(io.BytesIO(image_bytes))
                            print(f"📥 收到圖片：{attachment.filename}")
                            break 
                        except Exception:
                            pass

            user_text = message.content.replace(f'<@{client.user.id}>', '').strip()
            if not user_text and image_input:
                user_text = "(這是一張圖片，請評論它)"
            elif not user_text:
                user_text = "(使用者戳了你一下)"

            chat_history = []
            try:
                async for msg in message.channel.history(limit=7):
                    if not msg.author.bot and len(msg.content) < 150:
                        chat_history.append(f"{msg.author.display_name}: {msg.content}")
                chat_history.reverse()
            except Exception:
                pass
            
            chat_history_str = "\n".join(chat_history)
            
            emoji_list_str = ""
            if message.guild and message.guild.emojis:
                emoji_list_str = " ".join([str(e) for e in message.guild.emojis[:20]])

            persona = f"""
            你現在的身分是「蜂蜜水」，Discord 群組的吉祥物。
            創造者是「[超時空蜜蜂] XiaoYuan(小俊ouo)」。
            
            【群組專屬表情符號】：
            {emoji_list_str}
            
            【對話規則】：
            1. **禁止亂 Tag 人**：專注回覆這則訊息，不要標記不在場的人。
            2. **表情符號**：放在句尾，每句最多 1~2 個。
            3. **排版**：長句請適當換行。
            4. **個性**：
               - 閒聊：活潑俏皮。
               - 知識/深奧：聰明溫柔。
            
            【最近聊天氣氛參考】：
            {chat_history_str}
            """

            full_prompt = f"{persona}\n\n使用者 ({message.author.display_name}) 說：「{user_text}」。請以「蜂蜜水」的身分回應："

            if image_input:
                response = model.generate_content([f"{persona}\n\n(使用者傳了圖片) 評論這張圖：", image_input])
            else:
                response = model.generate_content(full_prompt)
            
            await message.reply(response.text, mention_author=False)

    except Exception as e:
        error_msg = str(e)
        print(f"❌ 發生錯誤: {error_msg}")
        if "429" in error_msg or "quota" in error_msg.lower():
            await message.channel.send("哎唷～腦袋運轉過度（額度用完），讓我冷卻一下好不好？🥺💦")
        elif "safety" in error_msg.lower() or "blocked" in error_msg.lower():
            await message.channel.send("嗯...這個話題有點太刺激，我先跳過好了！🫣")
        elif "PrivilegedIntentsRequired" in error_msg:
             await message.channel.send("❌ 系統錯誤：請去 Discord Developer Portal 開啟所有 Intents 權限！")
        else:
            await message.channel.send(f"嗚嗚，線路怪怪的，快叫 [超時空蜜蜂] XiaoYuan(小俊ouo) 來修我～😭\n錯誤代碼：`{error_msg}`")

if __name__ == "__main__":
    keep_alive()
    client.run(DISCORD_TOKEN)

