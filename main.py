import discord
import os
import google.generativeai as genai
from dotenv import load_dotenv
import PIL.Image
import io
import time
import random
from keep_alive import keep_alive

# ==========================================
# 1. 初始設定 & 金鑰讀取
# ==========================================
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# 【專屬設定】指定的主人 ID (請確認已填入正確 ID)
YOUR_ADMIN_ID = 495464747848695808

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
    print(f'🍯 蜂蜜水 (Honey Water) 優化版上線！')
    print(f'👑 認證主人 ID: {YOUR_ADMIN_ID}')
    print(f'------------------------------------------')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # =================================================================
    # 【功能 A】管理員指令 !say
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
    # 【功能 B】一般對話處理
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
    current_time = time.time()
    if user_id in user_cooldowns and (current_time - user_cooldowns[user_id] < 3):
        try:
            await message.add_reaction('⏳') 
        except:
            pass
        return 
    user_cooldowns[user_id] = current_time

    try:
        async with message.channel.typing():
            # A. 圖片處理
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

            # B. 文字處理
            user_text = message.content.replace(f'<@{client.user.id}>', '').strip()
            if not user_text and image_input:
                user_text = "(這是一張圖片，請評論它)"
            elif not user_text:
                user_text = "(使用者戳了你一下)"

            # C. 讀取歷史訊息
            chat_history = []
            try:
                async for msg in message.channel.history(limit=7):
                    if not msg.author.bot and len(msg.content) < 150:
                        chat_history.append(f"{msg.author.display_name}: {msg.content}")
                chat_history.reverse()
            except Exception:
                pass
            
            chat_history_str = "\n".join(chat_history)
            
            # D. 表符處理 (限制數量以免 Prompt 過長)
            emoji_list_str = ""
            if message.guild and message.guild.emojis:
                # 這裡會抓取正確的 Discord 格式 <a:name:id>
                emoji_list_str = " ".join([str(e) for e in message.guild.emojis[:20]])

            # E. 設定人設 Prompt (大幅修正)
            persona = f"""
            你現在的身分是「蜂蜜水」，Discord 群組的吉祥物。
            
            【群組專屬表情符號】：
            {emoji_list_str}
            
            【對話規則 - 請嚴格遵守】：
            1. **禁止亂 Tag 人**：請不要在對話中標記其他不在場的人，也不要憑空創造使用者。只要專注回覆這則訊息即可。
            2. **表情符號控制**：
               - 請 **適量使用** (每則訊息最多 1~2 個)。
               - 請將表符放在 **句子的末尾**，不要插在句子中間。
               - 只能使用上面列表提供的表符，或是通用的 Emoji (如 🍯、✨)。
            3. **排版**：如果回答較長，請適當 **換行**，讓文字閱讀起來不擁擠。
            4. **個性**：
               - 一般閒聊：活潑、俏皮 (笑死、XD)。
               - 知識/深奧話題：聰明且溫柔。
            
            【最近聊天氣氛參考】：
            {chat_history_str}
            """

            # F. 呼叫 API
            full_prompt = f"{persona}\n\n使用者 ({message.author.display_name}) 說：「{user_text}」。請以「蜂蜜水」的身分回應："

            if image_input:
                response = model.generate_content([f"{persona}\n\n(使用者傳了圖片) 評論這張圖：", image_input])
            else:
                response = model.generate_content(full_prompt)
            
            # G. 回覆 (使用 reply，但關閉 mention，避免一直 Tag 很吵)
            await message.reply(response.text, mention_author=False)

    except Exception as e:
        print(f"❌ 錯誤: {e}")
        # 不再回傳錯誤訊息到頻道，避免干擾體驗

if __name__ == "__main__":
    keep_alive()
    client.run(DISCORD_TOKEN)
