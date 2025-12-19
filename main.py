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
# 1. 初始設定
# ==========================================
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

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
# 3. Discord 機器人權限設定
# ==========================================
intents = discord.Intents.all()
client = discord.Client(intents=intents)

user_cooldowns = {}

@client.event
async def on_ready():
    print(f'------------------------------------------')
    print(f'🍯 蜂蜜水 已上線！(含 !say 管理員指令)')
    print(f'🤖 登入身分：{client.user}')
    print(f'------------------------------------------')

@client.event
async def on_message(message):
    # 1. 絕對不回覆機器人自己
    if message.author == client.user:
        return

    # =================================================================
    # 【新增功能】管理員專屬指令: !say
    # =================================================================
    if message.content.startswith('!say '):
        # 權限檢查：確認發話者有管理員權限
        if message.author.guild_permissions.administrator:
            # 取得 !say 之後的所有文字
            say_content = message.content[5:] 
            
            # A. 刪除使用者的指令 (毀屍滅跡)
            try:
                await message.delete()
            except Exception as e:
                print(f"❌ 無法刪除指令 (請給機器人「管理訊息」權限): {e}")

            # B. 機器人代說 (如果內容不為空)
            if say_content:
                await message.channel.send(say_content)
            
            return # 結束程式，不要觸發後面的 AI 回覆
        else:
            # 如果不是管理員，無視或告訴他沒權限
            print(f"⚠️ {message.author} 嘗試使用 !say 但沒有權限")
            return
    # =================================================================

    # 2. 一般 AI 聊天判斷 (Tag 或 回覆)
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

    # 3. 冷卻時間檢查
    user_id = message.author.id
    current_time = time.time()
    cooldown_seconds = 3
    
    if user_id in user_cooldowns and (current_time - user_cooldowns[user_id] < cooldown_seconds):
        try:
            await message.add_reaction('⏳') 
        except:
            pass
        return 
    
    user_cooldowns[user_id] = current_time

    # 4. AI 處理邏輯
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

            # C. 讀取最近聊天紀錄
            chat_history = []
            try:
                async for msg in message.channel.history(limit=7):
                    if not msg.author.bot and len(msg.content) < 150:
                        author_name = msg.author.display_name
                        chat_history.append(f"{author_name}: {msg.content}")
                chat_history.reverse()
            except Exception:
                pass
            
            chat_history_str = "\n".join(chat_history)
            
            # D. 群組表符
            emoji_list_str = ""
            if message.guild:
                emojis = message.guild.emojis[:30]
                if emojis:
                    emoji_list_str = " ".join([str(e) for e in emojis])

            # E. 設定人設
            persona = f"""
            你現在的身分是「蜂蜜水」，這個 Discord 群組的專屬吉祥物兼小幫手。
            創造者是「[超時空蜜蜂] XiaoYuan(小俊ouo)」。
            
            【表情符號資料庫】：
            {emoji_list_str}
            
            【擬真對話指南】：
            1. 讀空氣：參考下方的「最近聊天紀錄」，模仿群組氣氛和用語。
            2. Tag人：目前的對話者 ID 是 `{message.author.id}`，想 Tag 他就用 `<@{message.author.id}>`。
            
            【最近聊天紀錄】：
            {chat_history_str}
            """

            # F. 呼叫 API
            full_prompt = f"{persona}\n\n(輪到你了)\n使用者 ({message.author.display_name}) 說：「{user_text}」。請以「蜂蜜水」的身分回應："

            if image_input:
                prompt_for_img = f"{persona}\n\n使用者傳了一張圖片給你，並說：「{user_text}」。請用蜂蜜水的語氣評論這張圖："
                response = model.generate_content([prompt_for_img, image_input])
            else:
                response = model.generate_content(full_prompt)
            
            await message.reply(response.text, mention_author=False)

    except Exception as e:
        error_msg = str(e)
        print(f"❌ 發生錯誤: {error_msg}")
        if "429" in error_msg or "quota" in error_msg.lower():
            await message.channel.send("哎唷～腦袋運轉過度（額度用完），讓我冷卻一下好不好？🥺💦")
        elif "PrivilegedIntentsRequired" in error_msg:
             await message.channel.send("❌ 錯誤：請去 Discord Developer Portal 開啟權限！")
        else:
            # 只有在非 !say 指令出錯時才回報
            pass

if __name__ == "__main__":
    keep_alive()
    client.run(DISCORD_TOKEN)
