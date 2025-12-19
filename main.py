import discord
import os
import google.generativeai as genai
from dotenv import load_dotenv
import PIL.Image
import io
import time
import random
import re
import sys  # 【新增】用來強制結束程式
from datetime import datetime, timezone, timedelta
from keep_alive import keep_alive

# ==========================================
# 1. 初始設定 & 金鑰讀取
# ==========================================
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# 【專屬設定】指定的主人 ID
YOUR_ADMIN_ID = 495464747848695808

# 【營業時間】(24小時制, 台灣時間)
OPEN_HOUR = 8
CLOSE_HOUR = 23

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
    print(f'🍯 蜂蜜水 上線中！(含關機指令 + 完整報錯)')
    print(f'👑 認證主人 ID: {YOUR_ADMIN_ID}')
    print(f'------------------------------------------')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # 檢查權限 (主人或管理員)
    is_owner = (message.author.id == YOUR_ADMIN_ID)
    is_admin = message.author.guild_permissions.administrator
    has_permission = is_owner or is_admin

    # =================================================================
    # 【功能 A】管理員指令區 (!say / !shutdown)
    # =================================================================
    
    # 1. 遠端關機指令
    if message.content == '!shutdown':
        if has_permission:
            print("🛑 收到關機指令，準備下線...")
            await message.channel.send("蜂蜜水要下班去睡覺囉... 大家晚安！💤 (系統關機中)")
            await client.close() # 關閉 Discord 連線
            sys.exit(0) # 強制終止 Python 程式
        else:
            await message.channel.send("❌ 你沒有權限叫我去睡覺！")
            return

    # 2. 代說指令
    if message.content.startswith('!say '):
        if has_permission:
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
    # 【功能 B】營業時間檢查
    # =================================================================
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    current_hour = now.hour

    if current_hour < OPEN_HOUR or current_hour >= CLOSE_HOUR:
        # 非營業時間，10% 機率回覆睡著
        if client.user in message.mentions and random.random() < 0.1:
            await message.channel.send("呼...呼...💤 (蜂蜜水睡著了...)")
        return 

    # =================================================================
    # 【功能 C】AI 聊天邏輯
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
            # A. 圖片
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

            # B. 文字
            user_text = message.content.replace(f'<@{client.user.id}>', '').strip()
            if not user_text and image_input:
                user_text = "(這是一張圖片，請評論它)"
            elif not user_text:
                user_text = "(使用者戳了你一下)"

            # C. 讀空氣
            chat_history = []
            try:
                async for msg in message.channel.history(limit=7):
                    if not msg.author.bot and len(msg.content) < 150:
                        chat_history.append(f"{msg.author.display_name}: {msg.content}")
                chat_history.reverse()
            except Exception:
                pass
            
            chat_history_str = "\n".join(chat_history)
            
            # D. 表符
            emoji_list_str = ""
            if message.guild and message.guild.emojis:
                emoji_list_str = " ".join([str(e) for e in message.guild.emojis[:20]])

            # E. Prompt
            persona = f"""
            你現在的身分是「蜂蜜水」，Discord 群組的吉祥物。
            
            【群組專屬表情符號】：
            {emoji_list_str}
            
            【絕對指令】：
            1. **禁止 Tag 任何人**：絕對不要在回應中輸出 `<@ID>` 格式。叫名字就好。
            2. **表情符號**：每句話結尾最多放 1~2 個表符。
            3. **排版**：長句請換行。
            4. **個性**：活潑、俏皮、聰明。
            
            【最近聊天氣氛參考】：
            {chat_history_str}
            """

            full_prompt = f"{persona}\n\n使用者 ({message.author.display_name}) 說：「{user_text}」。請以「蜂蜜水」的身分回應："

            if image_input:
                response = model.generate_content([f"{persona}\n\n(使用者傳了圖片) 評論這張圖：", image_input])
            else:
                response = model.generate_content(full_prompt)
            
            # =================================================================
            # 【物理防禦】過濾 Tag
            # =================================================================
            clean_text = response.text
            clean_text = re.sub(r'<@!?[0-9]+>', '', clean_text)
            if not clean_text.strip():
                clean_text = "🍯✨"

            await message.reply(clean_text, mention_author=False)

    # =================================================================
    # 【錯誤處理】完整回報版
    # =================================================================
    except Exception as e:
        error_msg = str(e)
        print(f"❌ 發生錯誤: {error_msg}")

        # 針對常見錯誤給予友善回應
        if "429" in error_msg or "quota" in error_msg.lower():
            await message.channel.send("哎唷～腦袋運轉過度（額度用完），讓我冷卻一下好不好？🥺💦")
        elif "safety" in error_msg.lower() or "blocked" in error_msg.lower():
            await message.channel.send("嗯...這個話題有點太刺激，我先跳過好了！🫣")
        elif "PrivilegedIntentsRequired" in error_msg:
             await message.channel.send("❌ 系統錯誤：請去 Discord Developer Portal 開啟所有 Intents 權限！")
        else:
            # 【這裡已恢復顯示完整錯誤】
            await message.channel.send(f"嗚嗚，程式出錯了，快叫 [超時空蜜蜂] XiaoYuan(小俊ouo) 來修我～😭\n錯誤訊息：`{error_msg}`")

if __name__ == "__main__":
    keep_alive()
    client.run(DISCORD_TOKEN)
