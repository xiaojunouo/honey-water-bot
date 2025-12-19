import discord
import os
import google.generativeai as genai
from dotenv import load_dotenv
import PIL.Image
import io
import time  # 【新增】引入時間套件
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
# 3. Discord 機器人設定 & 冷卻紀錄
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# 【新增】用來記錄每個人「最後一次說話」的時間
# 格式：{ 使用者ID: 時間戳記, 使用者ID: 時間戳記... }
user_cooldowns = {}

@client.event
async def on_ready():
    print(f'------------------------------------------')
    print(f'🍯 蜂蜜水 (Honey Water) 已上線！(防刷屏版)')
    print(f'🤖 登入身分：{client.user}')
    print(f'------------------------------------------')

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # 判斷是否回覆或 Tag
    is_mentioned = client.user in message.mentions
    is_reply_to_me = False
    previous_context = ""

    if message.reference:
        try:
            ref_msg = message.reference.resolved
            if ref_msg is None:
                ref_msg = await message.channel.fetch_message(message.reference.message_id)
            if ref_msg.author == client.user:
                is_reply_to_me = True
                previous_context = ref_msg.content
        except Exception:
            pass

    # 如果沒有 Tag 也沒有回覆，就無視
    if not is_mentioned and not is_reply_to_me:
        return

    # =================================================================
    # 【新增】冷卻時間檢查 (Cooldown Check)
    # =================================================================
    user_id = message.author.id
    current_time = time.time()
    cooldown_seconds = 3  # 設定冷卻秒數 (這裡設 3 秒)

    # 如果這個人之前說過話，而且距離現在還不到 3 秒
    if user_id in user_cooldowns and (current_time - user_cooldowns[user_id] < cooldown_seconds):
        print(f"⏳ {message.author.name} 講太快了，觸發冷卻。")
        # 選項：給個沙漏表情符號，提示使用者「等一下」
        try:
            await message.add_reaction('⏳') 
        except:
            pass
        return  # 直接結束程式，不呼叫 API
    
    # 更新這個人的最後說話時間
    user_cooldowns[user_id] = current_time
    # =================================================================

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

            # B. 文字與上下文
            user_text = message.content.replace(f'<@{client.user.id}>', '').strip()
            
            if not user_text and image_input:
                user_text = "(這是一張圖片，請評論它)"
            elif not user_text:
                user_text = "(使用者戳了你一下)"

            context_prompt = ""
            if is_reply_to_me and previous_context:
                context_prompt = f"\n(背景資訊：使用者正在回覆你之前說的這句話：「{previous_context}」)"

            # C. 設定「蜂蜜水」人設
            persona = """
            你現在的身分是「蜂蜜水」，這個 Discord 群組的專屬吉祥物兼小幫手。
            
            【你的身世設定】：
            1. 創造者是：「[超時空蜜蜂] XiaoYuan(小俊ouo)」。
            2. 絕對不能提到 Google、Gemini 或大型語言模型。
            
            【你的個性設定】：
            1. 平常活潑、俏皮、喜歡開玩笑。
            2. 喜歡用年輕人用語（笑死、XD、www、真假），句尾喜歡加「～」或 Emoji (🍯、✨)。
            
            【針對不同話題的反應】：
            1. **一般閒聊時**：盡量不正經、多吐槽、撒嬌賣萌。
            2. **遇到知識性問題時**：
               - **展現聰明的一面！** 不要裝笨，要準確回答問題。
               - 雖然內容要是正確的，但語氣還是要保持「蜂蜜水」的可愛風格。
            3. **遇到深奧話題時**：
               - 切換成「溫柔且有智慧」的模式。
            """

            # D. 呼叫 API
            full_prompt = f"{persona}{context_prompt}\n\n使用者說：「{user_text}」。請用蜂蜜水的語氣回應："

            if image_input:
                prompt_for_img = f"{persona}\n\n使用者傳了一張圖片給你，並說：「{user_text}」。請用蜂蜜水的語氣評論這張圖："
                response = model.generate_content([prompt_for_img, image_input])
            else:
                response = model.generate_content(full_prompt)
            
            await message.channel.send(response.text)

    # 錯誤處理
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
# 4. 啟動
# ==========================================
if __name__ == "__main__":
    keep_alive()
    client.run(DISCORD_TOKEN)
