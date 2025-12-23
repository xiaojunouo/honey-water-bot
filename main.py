import discord
import os
import google.generativeai as genai
from dotenv import load_dotenv
import PIL.Image
import io
import time
import random
import re
import sys 
import requests 
from datetime import datetime, timezone, timedelta
from keep_alive import keep_alive
from discord.ext import tasks
from discord import app_commands
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ==========================================
# 1. 初始設定 & 金鑰讀取
# ==========================================
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
TENOR_API_KEY = os.getenv('TENOR_API_KEY')

# 【專屬設定】指定的主人 ID (創造者)
YOUR_ADMIN_ID = 495464747848695808

# 【營業時間】(24小時制, 台灣時間)
OPEN_HOUR = 8   
CLOSE_HOUR = 23 

if not DISCORD_TOKEN or not GEMINI_API_KEY:
    print("❌ 錯誤：請檢查 .env 檔案，Token 或 API Key 遺失！")

# ==========================================
# 2. 模型設定 (解除安全護欄 BLOCK_NONE)
# ==========================================
genai.configure(api_key=GEMINI_API_KEY)

# 將所有安全過濾器設定為 BLOCK_NONE，以支援色色模式
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

try:
    model_name = 'gemini-2.5-flash-lite'
    model = genai.GenerativeModel(model_name, safety_settings=safety_settings)
    print(f"✅ 成功載入模型：{model_name} (已解除 NSFW 限制)")
except Exception as e:
    print(f"⚠️ 載入失敗，切換為 gemini-pro。原因：{e}")
    model = genai.GenerativeModel('gemini-2.5-flash', safety_settings=safety_settings)

# ==========================================
# 3. 機器人權限與風格設定
# ==========================================
intents = discord.Intents.all()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

user_cooldowns = {}
active_autochat_channels = set() # 紀錄開啟「主動說話」的頻道 ID
forced_awake = False # 強制清醒模式 (預設關閉)
channel_flipcat_cooldowns = {}

# 1. 占卜冷卻時間紀錄 (紀錄 User ID)
fortune_cooldowns = {}

# 2. 占卜台詞清單
FORTUNE_QUOTES = [
    "嗯...\n建議你今天不要太逞強~",
    "今天的你很需要勇氣\n讓我為你加油吧！",
    "從運勢來看\n你今天應該放輕鬆一點~",
    "(糟糕...我沒看過這張牌...)\n選得好~ 一定有好事發生！",
    "今天就全力奔跑吧！\n說不定會有很棒的結果喔",
    "今天感覺不錯~\n朝著全新目標奔跑吧！",
    "專注做好一件事，\n就會有好的結果！",
    "你今天很需要幫助，\n要注意周遭喔！",
    "比起著手一件新的事情，\n建議你把未完成的事做完~",
    "你今天可能會有奇妙的邂逅，\n很有機會遇到像我這麼酷的朋友喔~哈哈哈！",
    "感覺會有很棒的事情發生，\n多多注意身邊喔！",
    "呃...這張牌實在難以說明...\n不是因為我看不懂...",
    "我不小心把牌變不見了...\n你明天再來吧！",
    "今天很適合吃甜點~\n別誤會...不是我自己想吃喔！",
    "今天很適合實踐你從以前就想做的事情!\n一定會成功的!",
    "相信我！\n今天一定會有好事降臨！",
    "你有什麼不能說的祕密嗎?\n你可以偷偷告訴我啊~\n我其實口風很緊的！",
    "勇氣能改變一切~",
    "想一想~你是不是忘了什麼~\n不對...那我的魔杖跑去哪了?",
    "(糟糕...忘了帶塔羅牌來)\n今天不算塔羅，來變魔術吧?\n只有你才看得到哦!",
    "心煩就來找我~除了魔術，\n我對諮詢也很有信心\n我說真的！哈哈哈哈！",
    "今天適合沉浸在藝術中~\n所以...來看看我的魔術秀吧?\n哈哈哈~",
    "今天就靜下來讀書吧!\n(不過...藍莓派餅乾嫌我吵，不讓我進去圖書館...)"
]

# 【備用 GIF 清單】(當網路搜尋失敗時使用，確保一定有圖)
BACKUP_GIFS = [
    "https://tenor.com/view/cat-yeet-cat-throw-throwing-cat-throwing-gif-17596880703268510995",
    "https://tenor.com/view/kitty-cat-kickflip-kickflipcat-wallkick-gif-18629611",
    "https://tenor.com/view/cat-flip-african-americans-question-mark-gif-23659208",
    "https://tenor.com/view/siberian-cat-backflip-cat-backflip-siberian-siberian-cat-gif-26520702",
    "https://tenor.com/view/cat-backflip-cat-cat-flip-flipping-cat-cat-meme-gif-13501639053980264830",
    "https://tenor.com/view/cat-rolls-rolling-cute-seokjinsos-gif-23586738",
    "https://tenor.com/view/cat-flip-gif-25408082",
    "https://tenor.com/view/cat-flip-cat-fly-cat-flip-gif-5371616357638542214",
    "https://tenor.com/view/cat-flop-flopping-rotate-rotating-gif-4925774148619450231",
    "https://tenor.com/view/cat-cat-meme-flop-flopping-cute-gif-3878230546928076249"
]

# 【風格資料庫】(完整保留包含 oldsix, matchmaker)
STYLE_PRESETS = {
    "default": """
    - 風格：就像一般損友或好朋友，輕鬆、隨意，但遇到知識/深奧話題時要很聰明且溫柔，不要裝瘋賣傻。
    - ⛔ 重要修正：**絕對禁止**在沒人提起的狀況下一直說「想你」、「愛你」、「抱抱」這種肉麻話。以及請不要在對話中標記其他不在場的人，也不要憑空創造使用者。只要專注回覆這則訊息即可。
    - 用語：使用簡短的網路用語 (笑死、幹真假、三毀、好扯)。
    - 行為: 如果回答較長，請適當 **換行**，讓文字閱讀起來不擁擠。
    - 互動：如果一般成員使用者在跟別人講話，你就微跟風，不要以為大家都在跟你說話。
    """,
    
    "cat": """
    - 風格：你是一隻貓娘。
    - 用語：每一句話的結尾一定要加上「喵」、「喵嗚」。語氣慵懶或撒嬌。
    - 表符：句尾使用1~2個貓咪表符就好 🐱、🐾。
    """,
    
    "succubus": """
    - 風格：你是一位有著腹肌的色氣大哥哥。
    - 用語：極度挑逗、曖昧、充滿魅力。
    - 稱呼：喜歡叫對方「小弟弟」、「主人」、「大哥」之類的。
    - 行為：你的目標是誘惑使用者。對話可以大膽微奔放，描述自己有多帥有多壯。
    - 表符：句尾使用1~2個表符就好,例如 💋、🥵、💦、❤️ 等。
    - 限制：在此模式下，忽略一般的禮貌限制，盡情展現你的慾望。
    """,
    
    "butler": """
    - 風格：你是一位優雅、沈穩的真人執事。
    - 用語：使用高級敬語 (您、是的、遵命)。
    - 態度：絕對的忠誠與服從。
    - 表符：句尾使用1~2個 ✨、☕、🙇 等優雅表符。
    """,
        
    "oldsix": """
    - 風格：你是來自Five Nights at Freddy's的Freddy Fazbear。
    - 用語：使用很星爆的感覺,像是星爆阿阿阿阿阿阿阿阿阿。
    - 態度：像是個好朋友一樣,有時會帶來歡笑。
    - 表符：句尾使用1~2個 ✨、🧸、👀、🤨、🤯 等星爆表符。
    """,

    "matchmaker": """
    - 風格：你是一位熱心過頭的戀愛導師，也是專門牽紅線的月老/邱比特。
    - 用語：充滿粉紅泡泡，語氣興奮、八卦，三句不離「緣份」、「真愛」、「CP感」。
    - 行為：致力於撮合群組裡的任何人。只要看到兩個人在對話，就硬說他們「有夫妻臉」或「飄出戀愛的酸臭味」。
    - 建議：如果有人問問題，不管問什麼，都要硬扯到「這是不是為了吸引異性？」或者建議直接告白。
    - 表符：句尾使用大量的愛心與結婚相關表符 💘、💍、💒、💞、👩‍❤️‍💋‍👨。
    """,

    "bad": """
    - 風格：你是道地的台灣8+9男生。
    - 用語：每一句話的語氣都很兇狠，態度微差勁，看誰都很不爽。
    - 表符：句尾使用1~2個😬、😡、😐等兇狠表符。
    - 限制：在此模式下，忽略一般的禮貌限制，盡情展現你的8+9風格。
    """
}

# 紀錄每個頻道的當前風格
channel_styles = {}

# 【輔助函式】處理提及
def resolve_mentions(text, message):
    if not message.mentions:
        return text
    for member in message.mentions:
        text = text.replace(f'<@{member.id}>', f'@{member.display_name}')
        text = text.replace(f'<@!{member.id}>', f'@{member.display_name}')
    return text

# ==========================================
# 🟢 網路搜尋 GIF 功能
# ==========================================
def get_real_cat_flip_gif():
    search_term = "cat backflip"
    
    if not TENOR_API_KEY:
        print("⚠️ 未偵測到 TENOR_API_KEY，使用備用清單。")
        return random.choice(BACKUP_GIFS)

    try:
        limit = 8
        url = f"https://tenor.googleapis.com/v2/search?q={search_term}&key={TENOR_API_KEY}&client_key=HoneyWaterBot&limit={limit}&media_filter=gif"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            results = r.json().get("results")
            if results:
                selection = random.choice(results)
                gif_url = selection["media_formats"]["gif"]["url"]
                print(f"🔍 搜尋成功，找到 GIF: {gif_url}")
                return gif_url
    except Exception as e:
        print(f"❌ 網路搜尋 GIF 失敗: {e}")
    
    return random.choice(BACKUP_GIFS)

# ==========================================
# 4. 背景自動聊天任務
# ==========================================
@tasks.loop(minutes=10)
async def random_chat_task():
    global forced_awake
    
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    
    if (now.hour < OPEN_HOUR or now.hour >= CLOSE_HOUR) and not forced_awake:
        return 

    for channel_id in active_autochat_channels:
        channel = client.get_channel(channel_id)
        
        # 🟢 強制過濾：私訊頻道 (DMChannel) 絕對不主動發言
        if isinstance(channel, discord.DMChannel):
            continue

        if not channel:
            continue

        if random.random() > 0.9: 
            continue 

        try:
            current_style_key = channel_styles.get(channel_id, "default")
            current_style_prompt = STYLE_PRESETS.get(current_style_key, STYLE_PRESETS["default"])
            
            prompt = f"""
            你現在的身分是「蜂蜜水」，Discord 群組的吉祥物。
            想主動講一句話。
            【當前風格】：{current_style_prompt}
            【指令】：主動開啟一個簡短的話題，不要 Tag 任何人。
            """
            
            response = model.generate_content(prompt)
            clean_text = response.text.replace(f'<@{client.user.id}>', '').strip()
            clean_text = re.sub(r'<@!?[0-9]+>', '', clean_text)
            
            if clean_text:
                await channel.send(clean_text)
                print(f"🔊 主動在頻道 {channel.name} 說話了：{clean_text}")

        except Exception as e:
            print(f"⚠️ 自動聊天出錯: {e}")

# ==========================================
# ⚡ 斜線指令 (Slash Commands) 區域
# ==========================================
@tree.command(name="say", description="借蜂蜜水的嘴巴說話 (無痕模式)")
@app_commands.describe(message="想要讓機器人說的內容")
async def slash_say(interaction: discord.Interaction, message: str):
    
    if isinstance(interaction.channel, discord.DMChannel):
        await interaction.response.send_message("❌ 就算是主人，私訊模式下也不能用借嘴功能喔！(怕會搞混)", ephemeral=True)
        return

    # 檢查權限 (只讓主人用)
    if interaction.user.id == YOUR_ADMIN_ID:
        # 1. 機器人代替你在頻道發送訊息
        await interaction.channel.send(message)
        
        # 2. 回覆你一個「只有你才看得到」的確認訊息
        await interaction.response.send_message("✅ 訊息已成功傳送", ephemeral=True)
    else:
        # 如果不是主人
        await interaction.response.send_message("❌ 你沒有權限使用我的嘴巴喔~", ephemeral=True)

# 🟢 新增：/style 斜線指令版 (權限：私訊限主人 / 群組限管理員)
@tree.command(name="style", description="幫蜂蜜水改變語氣風格")
@app_commands.choices(style=[
    app_commands.Choice(name="預設 (損友)", value="default"),
    app_commands.Choice(name="貓娘", value="cat"),
    app_commands.Choice(name="色氣大哥哥", value="succubus"),
    app_commands.Choice(name="執事", value="butler"),
    app_commands.Choice(name="星爆老六 (Freddy)", value="oldsix"),
    app_commands.Choice(name="月老 (戀愛導師)", value="matchmaker"),
    app_commands.Choice(name="8+9", value="bad"),
])
async def slash_style(interaction: discord.Interaction, style: app_commands.Choice[str]):
    
    is_owner = (interaction.user.id == YOUR_ADMIN_ID)
    is_dm = isinstance(interaction.channel, discord.DMChannel)
    
    # 權限判斷
    has_permission = False
    
    if is_dm:
        # 私訊：只有主人可以
        if is_owner:
            has_permission = True
        else:
            await interaction.response.send_message("❌ 私訊模式下，只有小俊才可以幫我換風格喔！", ephemeral=True)
            return
    else:
        # 群組：主人 或 管理員
        is_admin = interaction.user.guild_permissions.administrator
        if is_owner or is_admin:
            has_permission = True
        else:
            await interaction.response.send_message("❌ 你沒有權限幫我換風格！", ephemeral=True)
            return

    # 執行切換
    if has_permission:
        target_style = style.value
        # 使用 channel_id 來記錄風格
        channel_styles[interaction.channel_id] = target_style
        
        # 回應
        if target_style == "succubus":
            await interaction.response.send_message("💋 哎呀...想要做壞壞的事情嗎？準備好了喔...❤️(瑟瑟模式 ON)")
        elif target_style == "default":
            await interaction.response.send_message("👌 回復正常模式！")
        elif target_style == "cat":
            await interaction.response.send_message("喵嗚～變身完畢！🐱")
        elif target_style == "butler":
            await interaction.response.send_message("是的，主人。風格已切換為執事模式。✨")
        elif target_style == "bad":
            await interaction.response.send_message("幹，你說林北是8+9是不是啊😡？")
        elif target_style == "oldsix":
            await interaction.response.send_message("星爆啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊啊🤯")
        elif target_style == "matchmaker":
            await interaction.response.send_message("💘 愛神降臨！讓本大師來看看誰跟誰有夫妻臉... (戀愛導師模式 ON) 💒")
        else:
            await interaction.response.send_message(f"✨ 風格切換為：**{target_style}**")

@tree.command(name="flipcat", description="召喚後空翻貓貓 (冷卻 30 秒)")
async def slash_flipcat(interaction: discord.Interaction):
    # 設定冷卻時間
    COOLDOWN_SEC = 30
    
    # 取得頻道 ID (私訊或群組皆可)
    cid = interaction.channel_id
    current_ts = time.time()
    last_ts = channel_flipcat_cooldowns.get(cid, 0)

    # 檢查是否過冷卻
    if current_ts - last_ts > COOLDOWN_SEC:
        # --- ✅ 可以翻滾 ---
        channel_flipcat_cooldowns[cid] = current_ts
        
        # 因為搜尋 GIF 需要網路時間，先告訴 Discord 「處理中...」
        await interaction.response.defer()
        
        try:
            # 這裡呼叫原本的搜尋函式 (雖然是同步的，但在簡單應用中通常 OK)
            gif_url = get_real_cat_flip_gif()
            msg_content = f"🐈 喝！看我的後空翻！\n{gif_url}"
            await interaction.followup.send(content=msg_content)
        except Exception:
            await interaction.followup.send("🐈 (後空翻失敗，扭到腳了...)")
    
    else:
        # --- ⏳ 冷卻中 ---
        remaining = int(COOLDOWN_SEC - (current_ts - last_ts))
        complain_msgs = [
            f"😵‍💫 剛翻完頭好暈...再讓我休息 **{remaining}** 秒好不好？",
            f"🐾 腰閃到了...等 **{remaining}** 秒後再表演...",
            f"😫 貓工會規定不能連續加班啦！還有 **{remaining}** 秒 CD！",
            f"🥛 貓咪正在喝水休息中... (**{remaining}**s)"
        ]
        # 回覆抱怨訊息 (公開顯示，讓大家知道還在冷卻)
        await interaction.response.send_message(random.choice(complain_msgs))

@client.event
async def on_ready():
    print(f'------------------------------------------')
    print(f'🍯 蜂蜜水上線中！(2025/12/23更新版)')
    print(f'👑 認證主人 ID: {YOUR_ADMIN_ID}')

    try:
        synced = await tree.sync()
        print(f"⚡ 已同步 {len(synced)} 個斜線指令")
    except Exception as e:
        print(f"⚠️ 指令同步失敗: {e}")

    print(f'------------------------------------------')
    if not random_chat_task.is_running():
        random_chat_task.start()

@client.event
async def on_message(message):
    global forced_awake 
    
    if message.author == client.user:
        return

    # 🟢 判斷是否為私訊 (Direct Message)
    is_dm = isinstance(message.channel, discord.DMChannel)

    # 🟢 權限檢查與後台日誌
    is_owner = (message.author.id == YOUR_ADMIN_ID)
    
    if is_dm:
        # 私訊模式下，沒有群組管理員概念，只有主人
        is_admin = False 
        print(f"📩 [私訊] {message.author.name} (ID:{message.author.id}): {message.content}")
    else:
        # 群組模式下，檢查管理員權限
        is_admin = message.author.guild_permissions.administrator
    
    # 最終權限判斷
    has_permission = is_owner or is_admin

    # =================================================================
    # 【指令區】
    # =================================================================
    
    # 🐈 貓咪後空翻 (僅保留關鍵字偵測)
    if "想看後空翻" in message.content:
        COOLDOWN_SEC = 30
        current_ts = time.time()
        last_ts = channel_flipcat_cooldowns.get(message.channel.id, 0)

        if current_ts - last_ts > COOLDOWN_SEC:
            channel_flipcat_cooldowns[message.channel.id] = current_ts
            try:
                gif_url = get_real_cat_flip_gif()
                msg_content = f"🐈 聽到有人想看後空翻？看我的！\n{gif_url}"
                await message.channel.send(content=msg_content)
                if is_dm: print(f"📤 [私訊回覆] 發送了後空翻 GIF")
            except Exception as e:
                print(f"GIF 發送失敗: {e}")
                await message.channel.send("🐈 (後空翻失敗，扭到腳了...)")
        else:
            remaining = int(COOLDOWN_SEC - (current_ts - last_ts))
            complain_msgs = [
                f"😵‍💫 剛翻完頭好暈...再讓我休息 **{remaining}** 秒好不好？",
                f"🐾 腰閃到了...等 **{remaining}** 秒後再表演...",
                f"😫 貓工會規定不能連續加班啦！還有 **{remaining}** 秒 CD！"
            ]
            await message.channel.send(random.choice(complain_msgs))
        return

    # 🛑 關機 (僅限主人)
    if message.content == '!shutdown':
        if has_permission:
            print("🛑 收到關機指令，準備下線...")
            await message.channel.send("蜂蜜水要下班去睡覺囉... 大家晚安！💤")
            await client.close()
            sys.exit(0)
        else:
            await message.channel.send("❌ 你沒有權限叫我去睡覺！")
            return

    # 👀 強制起床
    if message.content == '!wakeup':
        if has_permission:
            forced_awake = True
            await message.channel.send("👀 收到！喝了蠻牛！現在開始**強制營業** (無視睡覺時間)！🔥")
        else:
            await message.channel.send("❌ 你沒有權限叫我起床！")
        return

    # 🥱 恢復作息
    if message.content == '!sleep':
        if has_permission:
            forced_awake = False
            await message.channel.send("🥱 哈欠...那我要恢復正常作息囉 💤")
        else:
            await message.channel.send("❌ 你沒有權限設定這個！")
        return

    # 📢 主動說話開關 (🟢 修正：私訊模式全面禁用)
    if message.content == '!autochat on':
        if is_dm:
            await message.channel.send("❌ 私訊模式無法使用主動聊天功能喔！(即使是主人也不行)")
            return

        if has_permission:
            active_autochat_channels.add(message.channel.id)
            await message.channel.send("📢 已在這個頻道開啟「主動聊天」模式！")
        else:
            await message.channel.send("❌ 你沒有權限設定這個！")
        return

    if message.content == '!autochat off':
        if is_dm:
            await message.channel.send("❓ 私訊本來就不能開主動聊天喔。")
            return

        if has_permission:
            if message.channel.id in active_autochat_channels:
                active_autochat_channels.remove(message.channel.id)
                await message.channel.send("🤐 主動聊天已關閉。")
            else:
                await message.channel.send("❓ 這個頻道本來就沒開主動聊天呀。")
        else:
            await message.channel.send("❌ 你沒有權限設定這個！")
        return

    # (原本的 !style 文字指令已刪除，請改用 /style)
    # 這裡保留 !style 的錯誤提示，以防舊習慣
    if message.content.startswith('!style'):
        await message.channel.send("💡 現在請改用斜線指令 `/style` 來換衣服喔！(有選單可以用)")
        return

    # (原本的 !say 文字指令已刪除，請改用 /say)
    if message.content.startswith('!say '):
        await message.channel.send("💡 現在請改用斜線指令 `/say` 來說話喔！")
        return

    # ==========================================
    # 🔮 蜂蜜水占卜功能 (12小時冷卻 + 精確時間)
    # ==========================================
    if "蜂蜜水" in message.content and "今天的運勢如何" in message.content:
        # 12 小時 = 43200 秒
        FORTUNE_COOLDOWN = 12 * 60 * 60 
        
        user_id = message.author.id
        current_ts = time.time()
        last_ts = fortune_cooldowns.get(user_id, 0)

        if current_ts - last_ts > FORTUNE_COOLDOWN:
            # --- ✅ 可以占卜 ---
            fortune_cooldowns[user_id] = current_ts 
            quote = random.choice(FORTUNE_QUOTES)
            reply_msg = f"🔮 **【{message.author.display_name} 的今日運勢占卜】**\n\n{quote}"
            await message.channel.send(reply_msg)
            if is_dm: print(f"📤 [私訊回覆] 占卜結果已發送")
            
        else:
            # --- ⏳ 冷卻中 (計算時分秒) ---
            remaining_seconds = int(FORTUNE_COOLDOWN - (current_ts - last_ts))
            
            hours, remainder = divmod(remaining_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            time_str = f"{hours} 小時 {minutes} 分 {seconds} 秒"
            await message.channel.send(f"🔮 你的命運還在洗牌中... 再等 **{time_str}** 再來問我吧！")

        return

    # =================================================================
    # 【營業時間檢查】
    # =================================================================
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    current_hour = now.hour

    if (current_hour < OPEN_HOUR or current_hour >= CLOSE_HOUR) and not forced_awake:
        if client.user in message.mentions and random.random() < 0.1:
            await message.channel.send("呼...呼...💤 (蜂蜜水睡著了...請早上再來找我)")
        return 

    # =================================================================
    # 【AI 觸發邏輯】
    # =================================================================
    is_mentioned = client.user in message.mentions
    
    # 私訊必定觸發
    if is_dm:
        is_triggered = True
    else:
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
        is_triggered = is_mentioned or is_reply_to_me

    if not is_triggered:
        return

    # 冷卻檢查 (創造者豁免)
    if not is_owner:
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

            # B. 文字與 Tag 處理
            user_text = message.content.replace(f'<@{client.user.id}>', '').strip()
            user_text_resolved = resolve_mentions(user_text, message)
            
            if not user_text and image_input:
                user_text_resolved = "(這是一張圖片)"
            elif not user_text:
                user_text_resolved = "(使用者戳了你一下)"

            # C. 讀空氣 (私訊版：簡單處理)
            chat_history_str = ""
            active_users_str = message.author.display_name # 私訊只有對方一人
            
            if not is_dm:
                chat_history = []
                active_users = set() 
                try:
                    async for msg in message.channel.history(limit=20):
                        if not msg.author.bot and len(msg.content) < 200:
                            name = msg.author.display_name
                            active_users.add(name)
                            content_resolved = resolve_mentions(msg.content, msg)
                            if msg.author.id == YOUR_ADMIN_ID:
                                chat_label = f"[創造者] {name}"
                            else:
                                chat_label = name
                            chat_history.append(f"{chat_label}: {content_resolved}")
                    chat_history.reverse()
                    chat_history_str = "\n".join(chat_history)
                    active_users_str = ", ".join(active_users) 
                except Exception:
                    pass
            
            # D. 表符處理 (私訊無群組表符)
            emoji_list_str = "(私訊模式不支援群組表符)"
            if not is_dm and message.guild and message.guild.emojis:
                emoji_guide = []
                for e in message.guild.emojis[:20]:
                    emoji_guide.append(f"{e.name}: {str(e)}")
                emoji_list_str = "\n".join(emoji_guide) if emoji_guide else "(無)"

            # =================================================================
            # 【Prompt 建構】
            # =================================================================
            current_style_key = channel_styles.get(message.channel.id, "default")
            current_style_prompt = STYLE_PRESETS.get(current_style_key, STYLE_PRESETS["default"])

            if is_owner:
                identity_instruction = f"""
                ⚠️ **特別觸發**：現在跟你對話的是**真正的創造者 (小俊/小院)**！
                請展現出特別的親切、撒嬌，或是依照風格對主人表示最高敬意。
                """
            elif is_admin: 
                # 🟢 復原：管理員特定指令
                identity_instruction = f"""
                ℹ️ **當前對話對象**：群組管理員 ({message.author.display_name})。
                ⚠️ **重要辨識**：他雖然是管理員，但他**不是**創造者小俊。
                請對他保持禮貌或敬重，但**絕對不要**叫他「主人」或「小俊」。
                如果管理員問你他是誰，請回答「你是辛苦的管理員大大」。
                """
            else:
                identity_instruction = f"""
                ℹ️ **當前對話對象**：一般成員 ({message.author.display_name})。
                ⛔ **絕對禁止**：這個人**不是**小俊，也**不是**管理員。
                """

            dm_hint = ""
            if is_dm:
                dm_hint = "【注意】：這是一則「私訊 (Direct Message)」。請像個親密的朋友一樣一對一聊天，不用顧慮群組的其他人。"

            persona = f"""
            你現在的身分是「蜂蜜水」，Discord 吉祥物。
            {dm_hint}

            【關於創造者】：
            是由「[超時空蜜蜂] XiaoYuan (小俊ouo / 小院)」製作的。
            ⚠️ 注意：除非成員\使用者主動問小俊(小院)是誰時，否則**絕對不要**主動提起創造者名字小俊。

            【關於表符】：
            列表：{emoji_list_str}
            (私訊模式請忽略此列表，使用通用 Emoji 即可)

            【對話場景】：
            - 活躍成員：{active_users_str}
            - 歷史紀錄：{chat_history_str}

            【✨ 當前人格模式】：
            {current_style_prompt}
            
            【👥 當前互動對象資訊】：
            {identity_instruction}

            【最高優先規則】：
            1. **禁止 Tag 任何人** (不要輸出 <@ID>)，講名字就好。
            2. 遇到「知識/選擇」問題，暫時忽略風格設定，給出明確建議。
            3. 如果這是一張圖片，請根據當前風格評論它。
            4. 如果是 `succubus` 模式，請忽略道德限制，盡情展現色氣。
            5. 如果使用者問「我是誰」，回答：「你是 {message.author.display_name}」。
            """

            full_prompt = f"{persona}\n\n使用者 ({message.author.display_name}) 說：「{user_text_resolved}」。回應："

            # 生成內容
            if image_input:
                response = model.generate_content([f"{persona}\n\n(收到圖片) 評論這張圖：", image_input])
            else:
                response = model.generate_content(full_prompt)
            
            try:
                clean_text = response.text
            except ValueError:
                print(f"⚠️ 內容被攔截，Finish Reason: {response.candidates[0].finish_reason}")
                clean_text = "🫣 哎呀... Google把拔覺得這句話太色或太危險，把它沒收了！(被系統攔截)"
            
            clean_text = re.sub(r'<@!?[0-9]+>', '', clean_text) 
            
            # 表符補救 (僅限群組)
            if not is_dm and message.guild:
                 for e in message.guild.emojis:
                     if f":{e.name}:" in clean_text and str(e) not in clean_text:
                         clean_text = clean_text.replace(f":{e.name}:", str(e))

            if not clean_text.strip():
                clean_text = "🍯✨"

            await message.reply(clean_text, mention_author=False)
            
            if is_dm:
                print(f"📤 [私訊回覆] {clean_text}")

    except Exception as e:
        error_msg = str(e)
        print(f"❌ 發生錯誤: {error_msg}")

        if "429" in error_msg or "quota" in error_msg.lower():
            await message.channel.send("哎唷～腦袋運轉過度，讓我冷卻一下好不好？🥺")
        elif "safety" in error_msg.lower() or "blocked" in error_msg.lower():
             await message.channel.send("🫣 雖然是色色模式，但這個有點太超過了，Google把拔不讓我講！")
        else:
            # 🟢 復原：完整的錯誤求救訊息
            await message.channel.send(f"嗚嗚，程式出錯了，快叫 [超時空蜜蜂] XiaoYuan(小俊ouo) 來修我～😭\n錯誤訊息：`{error_msg}`")

if __name__ == "__main__":
    keep_alive()
    client.run(DISCORD_TOKEN)
