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
# 1. 初始設定 & 金鑰讀取
# ==========================================
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# 【重要】請將這裡換成你自己的 Discord User ID (數字)
# 這樣不管身分組設定如何，機器人一定聽你的話
YOUR_ADMIN_ID = 495464747848695808 

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
# 3. 機器人權限設定 (Intents)
# ==========================================
# 必須去 Developer Portal 開啟 Server Members & Message Content 權限
intents = discord.Intents.all()
client = discord.Client(intents=intents)

# 記錄冷卻時間
user_cooldowns = {}

@client.event
async def on_ready():
    print(f'------------------------------------------')
    print(f'🍯 蜂蜜水 (Honey Water) 全機能上線！')
    print(f'👑 指定主人 ID: {YOUR_ADMIN_ID}')
    print(f'------------------------------------------')

@client.event
async def on_message(message):
    # 1. 絕對不回覆機器人自己
    if message.author == client.user:
        return

    # =================================================================
    # 【功能 A】管理員指令 !say (優先處理)
    # =================================================================
    if message.content.startswith('!say '):
        # 權限檢查：是你本人 (ID符合) 或 擁有管理員權限
        is_owner = (message.author.id == 495464747848695808)
        is_admin = message.author.guild_permissions.administrator
        
        if is_owner or is_admin:
            say_content = message.content[5:] # 取得 !say 之後的字
            
            # 1. 先發話 (確保話有說出去)
            if say_content:
                await message.channel.send(say_content)
            
            # 2. 再刪除指令 (放在 try 避免權限不足報錯)
            try:
                await message.delete()
            except Exception:
                pass # 刪不掉就算了，不影響發話
            
            return # 指令執行完畢，結束程式
        else:
            # 如果不是管理員，無視
            return
    # =================================================================

    # 2. 判斷是否需要回應 (Tag 或 回覆機器人)
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

    # 3. 冷卻時間檢查 (3秒)
    user_id = message.author.id
    current_time = time.time()
    
    if user_id in user_cooldowns and (current_time - user_cooldowns[user_id] < 3):
        try:
            await message.add_reaction('⏳') 
        except:
            pass
        return 
    user_cooldowns[user_id] = current_time

    # 4. AI 處理邏輯
    try:
        async with message.channel.typing():
            # A. 圖片讀取
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

            # C. 讀取聊天紀錄 (讀空氣)
            chat_history = []
            try:
                async for msg in message.channel.history(limit=7):
                    if not msg.author.bot and len(msg.content) < 150:
                        chat_history.append(f"{msg.author.display_name}: {msg.content}")
                chat_history.reverse()
            except Exception:
                pass # 讀不到就算了
            
            chat_history_str = "\n".join(chat_history)
            
            # D. 群組表符抓取
            emoji_list_str = ""
            if message.guild and message.guild.emojis:
                emoji_list_str = " ".join([str(e) for e in message.guild.emojis[:30]])

            # E. 設定人設 Prompt
            persona = f"""
            你現在的身分是「蜂蜜水」，這個 Discord 群組的專屬吉祥物兼小幫手。
            
            【你的身世】：
            創造者是「[超時空蜜蜂] XiaoYuan(小俊ouo)」。(如果有問到，一定要回答這個)
            
            【群組專屬表情符號】：
            {emoji_list_str}
            (請在回應中大量且自然地使用這些表符，讓對話更有趣)
            
            【擬真對話指南】：
            1. **讀空氣**：參考下方的「最近聊天紀錄」，模仿群組氣氛。如果大家在嘴砲，你也可以嘴砲。
            2. **Tag 人**：目前的對話者 ID 是 `{message.author.id}`。如果你想特別點名他，請在回應中加上 `<@{message.author.id}>`。
            
            【個性切換開關】：
            1. **一般閒聊**：不正經、愛吐槽、愛撒嬌、用網路流行語 (笑死、XD、www)。
            2. **知識問答**：(如科學、數學) 展現聰明的一面，準確回答，不要裝笨。
            3. **深奧話題**：(如人生、哲學) 變得溫柔且有智慧。
            
            【最近聊天紀錄 (參考用)】：
            {chat_history_str}
            """

            # F. 呼叫 Gemini
            full_prompt = f"{persona}\n\n(輪到你了)\n使用者 ({message.author.display_name}) 說：「{user_text}」。請以「蜂蜜水」的身分回應："

            if image_input:
                # 圖片模式 Prompt
                prompt_for_img = f"{persona}\n\n使用者傳了一張圖片給你，並說：「{user_text}」。請用蜂蜜水的語氣評論這張圖："
                response = model.generate_content([prompt_for_img, image_input])
            else:
                # 文字模式 Prompt
                response = model.generate_content(full_prompt)
            
            # G. 回覆 (使用 reply，但不強制 Tag 作者，讓 AI 決定內容)
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
             await message.channel.send("❌ 系統錯誤：請去 Discord Developer Portal 開啟所有權限 (Intents)！")
        else:
            await message.channel.send(f"嗚嗚，線路怪怪的，快叫 [超時空蜜蜂] XiaoYuan(小俊ouo) 來修我～😭")

# ==========================================
# 6. 啟動
# ==========================================
if __name__ == "__main__":
    keep_alive()
    client.run(DISCORD_TOKEN)
