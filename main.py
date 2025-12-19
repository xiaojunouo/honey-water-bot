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
# 3. Discord 機器人設定
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

user_cooldowns = {}

@client.event
async def on_ready():
    print(f'------------------------------------------')
    print(f'🍯 蜂蜜水 已上線！(防雙重回應 + 引用回覆版)')
    print(f'🤖 登入身分：{client.user}')
    print(f'------------------------------------------')

@client.event
async def on_message(message):
    # 1. 絕對不回覆機器人自己 (防止無限迴圈)
    if message.author == client.user:
        return

    # 2. 判斷是否需要回應 (Tag 或 回覆機器人)
    is_mentioned = client.user in message.mentions
    is_reply_to_me = False
    previous_context = ""

    # 檢查是否為「回覆」訊息
    if message.reference:
        try:
            ref_msg = message.reference.resolved
            if ref_msg is None:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
            # 如果是回覆給機器人本人
            if ref_msg.author == client.user:
                is_reply_to_me = True
                previous_context = ref_msg.content # 抓取上下文記憶
        except Exception:
            pass

    # 如果既沒 Tag 也沒回覆機器人，直接結束，不做任何事
    if not is_mentioned and not is_reply_to_me:
        return

    # 3. 冷卻時間檢查 (防止刷屏)
    user_id = message.author.id
    current_time = time.time()
    cooldown_seconds = 3
    
    if user_id in user_cooldowns and (current_time - user_cooldowns[user_id] < cooldown_seconds):
        # 選項：給個表情但不回話，節省資源
        try:
            await message.add_reaction('⏳') 
        except:
            pass
        return 
    
    user_cooldowns[user_id] = current_time

    # 4. 生成回應
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

            # C. 上下文記憶 (如果有的話)
            context_prompt = ""
            if is_reply_to_me and previous_context:
                context_prompt = f"\n(背景資訊：使用者正在回覆你之前說的這句話：「{previous_context}」)"

            # D. 自動抓取群組表符
            emoji_list_str = ""
            if message.guild:
                emojis = message.guild.emojis[:30]
                if emojis:
                    emoji_list_str = " ".join([str(e) for e in emojis])

            # E. 設定人設
            persona = f"""
            你現在的身分是「蜂蜜水」，這個 Discord 群組的專屬吉祥物兼小幫手。
            
            【你的身世設定】：
            1. 創造者是：「[超時空蜜蜂] XiaoYuan(小俊ouo)」。
            
            【你的個性設定】：
            1. 平常活潑、俏皮、喜歡開玩笑。
            2. 喜歡用年輕人用語（笑死、XD、www、真假）。
            
            【表情符號使用】：
            可以使用這些群組專屬表符：{emoji_list_str}
            
            【針對不同話題的反應】：
            1. **一般閒聊時**：不正經、多吐槽、撒嬌。
            2. **遇到知識性問題時**：展現聰明的一面，不要裝笨。
            3. **遇到深奧話題時**：切換成溫柔且有智慧的模式。
            """

            # F. 呼叫 API
            full_prompt = f"{persona}{context_prompt}\n\n使用者說：「{user_text}」。請用蜂蜜水的語氣回應："

            if image_input:
                prompt_for_img = f"{persona}\n\n使用者傳了一張圖片給你，並說：「{user_text}」。請用蜂蜜水的語氣評論這張圖："
                response = model.generate_content([prompt_for_img, image_input])
            else:
                response = model.generate_content(full_prompt)
            
            # 【升級】使用 reply() 進行引用回覆
            # mention_author=False 代表回覆時不會特別 Tag 對方 (避免太吵)，如果你想 Tag 可以改成 True
            await message.reply(response.text, mention_author=False)

    # 5. 錯誤處理
    except Exception as e:
        error_msg = str(e)
        print(f"❌ 發生錯誤: {error_msg}")

        if "429" in error_msg or "quota" in error_msg.lower():
            await message.channel.send("哎唷～腦袋運轉過度（額度用完），讓我冷卻一下好不好？🥺💦")
        elif "safety" in error_msg.lower() or "blocked" in error_msg.lower():
            await message.channel.send("嗯...這個話題有點太刺激，我先跳過好了！🫣")
        else:
            await message.channel.send(f"嗚嗚，線路怪怪的，快叫 [超時空蜜蜂] XiaoYuan(小俊ouo) 來修我～😭\n`{error_msg}`")

# ==========================================
# 6. 啟動
# ==========================================
if __name__ == "__main__":
    keep_alive()
    client.run(DISCORD_TOKEN)
