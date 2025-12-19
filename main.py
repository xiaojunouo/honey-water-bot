import discord
import os
import google.generativeai as genai
from dotenv import load_dotenv
import PIL.Image
import io
import time
import random
from keep_alive import keep_alive  # 確保你有建立 keep_alive.py

# ==========================================
# 1. 初始設定
# ==========================================
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

if not DISCORD_TOKEN or not GEMINI_API_KEY:
    print("❌ 錯誤：請檢查 .env 檔案，Token 或 API Key 遺失！")

genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 2. 模型選擇 (自動避開額度限制)
# ==========================================
try:
    model_name = 'gemini-2.5-flash-lite'
    model = genai.GenerativeModel(model_name)
    print(f"✅ 成功載入模型：{model_name}")
except Exception as e:
    print(f"⚠️ 1.5-flash 載入失敗，切換為 gemini-pro。原因：{e}")
    model = genai.GenerativeModel('gemini-2.5-flash')

# ==========================================
# 3. Discord 機器人權限設定 (重要！)
# ==========================================
# 改用 all() 以支援讀取成員名單與歷史訊息
# 請務必去 Developer Portal 開啟 Server Members Intent
intents = discord.Intents.all()
client = discord.Client(intents=intents)

# 用來記錄每個人最後發言時間的字典
user_cooldowns = {}

@client.event
async def on_ready():
    print(f'------------------------------------------')
    print(f'🍯 蜂蜜水 (Honey Water) 已上線！(終極擬真版)')
    print(f'🤖 登入身分：{client.user}')
    print(f'------------------------------------------')

@client.event
async def on_message(message):
    # 1. 絕對不回覆機器人自己
    if message.author == client.user:
        return

    # 2. 判斷是否需要回應
    # 規則：被 Tag (@蜂蜜水) 或者 是回覆(Reply)給機器人的訊息
    is_mentioned = client.user in message.mentions
    is_reply_to_me = False
    
    # 檢查引用回覆
    if message.reference:
        try:
            ref_msg = message.reference.resolved
            if ref_msg is None:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
            if ref_msg.author == client.user:
                is_reply_to_me = True
        except Exception:
            pass # 抓不到就算了

    if not is_mentioned and not is_reply_to_me:
        return

    # 3. 冷卻時間檢查 (3秒)
    user_id = message.author.id
    current_time = time.time()
    cooldown_seconds = 3
    
    if user_id in user_cooldowns and (current_time - user_cooldowns[user_id] < cooldown_seconds):
        try:
            await message.add_reaction('⏳') # 給個漏斗提示
        except:
            pass
        return 
    
    user_cooldowns[user_id] = current_time

    # 4. 開始處理訊息
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

            # B. 文字處理 (移除 Tag)
            user_text = message.content.replace(f'<@{client.user.id}>', '').strip()
            if not user_text and image_input:
                user_text = "(這是一張圖片，請評論它)"
            elif not user_text:
                user_text = "(使用者戳了你一下)"

            # =================================================================
            # 【核心功能】C. 讀取最近聊天紀錄 (讀空氣)
            # =================================================================
            chat_history = []
            try:
                # 抓取最近 7 則訊息 (包含別人的發言)，讓 AI 知道現在的氣氛
                async for msg in message.channel.history(limit=7):
                    if not msg.author.bot and len(msg.content) < 150:
                        author_name = msg.author.display_name
                        chat_history.append(f"{author_name}: {msg.content}")
                chat_history.reverse() # 轉成正確的時間順序
            except Exception as e:
                print(f"無法讀取歷史紀錄 (可能是權限不足): {e}")
            
            chat_history_str = "\n".join(chat_history)
            
            # =================================================================
            # D. 自動抓取群組表符
            # =================================================================
            emoji_list_str = ""
            if message.guild:
                emojis = message.guild.emojis[:30] # 限制前30個以免 Prompt 太長
                if emojis:
                    emoji_list_str = " ".join([str(e) for e in emojis])

            # =================================================================
            # E. 設定人設 (加入模仿、Tag 指令、作者資訊)
            # =================================================================
            persona = f"""
            你現在的身分是「蜂蜜水」，這個 Discord 群組的專屬吉祥物兼小幫手。
            
            【你的身世】：
            創造者是「[超時空蜜蜂] XiaoYuan(小俊ouo)」。
            (如果有人問是誰做的，一定要回答這個名字)
            
            【表情符號資料庫】：
            {emoji_list_str}
            (請在回應中大量且自然地使用這些表符，如果沒有適合的就用一般 emoji)
            
            【擬真對話指南 - 重要！】：
            1. **讀空氣**：請參考下方的「最近聊天紀錄」。如果大家都在用簡短的網路用語（如：笑死、真假、好扯），你也要跟著用。如果氣氛很嗨，你就很嗨。
            2. **學說話**：觀察使用者的語氣，試著模仿群組的說話風格。
            3. **Tag 人**：目前的對話者 ID 是 `{message.author.id}`。如果你想要特別 Tag 他，請在句子裡加上 `<@{message.author.id}>`。
            4. **個性切換**：
               - 一般閒聊：不正經、愛吐槽、愛撒嬌 (🍯、✨)。
               - 知識問答：展現聰明的一面，不要裝笨。
               - 深奧話題：變成溫柔有智慧的模式。
            
            【最近聊天紀錄 (參考用)】：
            {chat_history_str}
            """

            # F. 組合 Prompt 並呼叫 API
            full_prompt = f"{persona}\n\n(輪到你了)\n使用者 ({message.author.display_name}) 說：「{user_text}」。請以「蜂蜜水」的身分回應："

            if image_input:
                prompt_for_img = f"{persona}\n\n使用者傳了一張圖片給你，並說：「{user_text}」。請用蜂蜜水的語氣評論這張圖："
                response = model.generate_content([prompt_for_img, image_input])
            else:
                response = model.generate_content(full_prompt)
            
            # 傳送訊息 (使用 reply 功能，mention_author=False 代表不強制 Tag，讓 AI 自己決定內容要不要 Tag)
            await message.reply(response.text, mention_author=False)

    # 5. 錯誤處理
    except Exception as e:
        error_msg = str(e)
        print(f"❌ 發生錯誤: {error_msg}")

        if "429" in error_msg or "quota" in error_msg.lower():
            await message.channel.send("哎唷～腦袋運轉過度（額度用完），讓我冷卻一下好不好？🥺💦")
        elif "safety" in error_msg.lower() or "blocked" in error_msg.lower():
            await message.channel.send("嗯...這個話題有點太刺激，我先跳過好了！🫣")
        elif "PrivilegedIntentsRequired" in error_msg:
             await message.channel.send("❌ 錯誤：請去 Discord Developer Portal 開啟 `Server Members Intent` 和 `Message Content Intent` 權限！")
        else:
            await message.channel.send(f"嗚嗚，線路怪怪的，快叫 [超時空蜜蜂] XiaoYuan(小俊ouo) 來修我～😭\n`{error_msg}`")

# ==========================================
# 6. 啟動伺服器與機器人
# ==========================================
if __name__ == "__main__":
    keep_alive()
    client.run(DISCORD_TOKEN)
