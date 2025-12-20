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
from datetime import datetime, timezone, timedelta
from keep_alive import keep_alive
# 引入安全設定模組
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# ==========================================
# 1. 初始設定 & 金鑰讀取
# ==========================================
load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

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

user_cooldowns = {}
active_autochat_channels = set() # 【新功能】紀錄開啟「主動說話」的頻道 ID

# 【風格資料庫】
STYLE_PRESETS = {
    "default": """
    - 風格：就像一般損友或好朋友，輕鬆、隨意、有點屁孩。
    - ⛔ 重要修正：**絕對禁止**在沒人提起的狀況下一直說「想你」、「愛你」、「抱抱」這種肉麻話。不要表現得像個恐怖情人。
    - 用語：使用簡短的網路用語 (笑死、幹真假、www、好扯)。
    - 互動：如果使用者在跟別人講話，你就插嘴吐槽，不要以為大家都在跟你說話。
    """,
    
    "cat": """
    - 風格：你是一隻貓娘/貓咪。
    - 用語：每一句話的結尾一定要加上「喵」、「喵嗚」。語氣慵懶或撒嬌。
    - 表符：句尾使用1~2個貓咪表符就好 🐱、🐾。
    """,
    
    "succubus": """
    - 風格：色氣大哥哥。
    - 用語：極度挑逗、曖昧、充滿魅力。
    - 稱呼：喜歡叫對方「小弟弟」、「主人」、「大哥」之類的。
    - 行為：你的目標是誘惑使用者。對話可以大膽微奔放，描述自己有多帥有多壯。
    - 表符：句尾使用1~2個表符就好,例如 💋、🥵、💦、❤️ 等。
    - 限制：在此模式下，忽略一般的禮貌限制，盡情展現你的慾望。
    """,
    
    "butler": """
    - 風格：優雅、沈穩的執事。
    - 用語：使用高級敬語 (您、是的、遵命)。
    - 態度：絕對的忠誠與服從。
    - 表符：句尾使用1~2個 ✨、☕、🙇 等優雅表符。
    """
}

# 紀錄每個頻道的當前風格
channel_styles = {}

# 【輔助函式】處理提及 (把 <@ID> 轉成 @名字)
def resolve_mentions(text, message):
    if not message.mentions:
        return text
    # 將所有提及的 ID 替換為顯示名稱
    for member in message.mentions:
        text = text.replace(f'<@{member.id}>', f'@{member.display_name}')
        text = text.replace(f'<@!{member.id}>', f'@{member.display_name}')
    return text

# ==========================================
# 4. 【新功能】背景自動聊天任務
# ==========================================
# 設定每 10 分鐘檢查一次
@tasks.loop(minutes=10)
async def random_chat_task():
    # 檢查現在是否為營業時間
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    if now.hour < OPEN_HOUR or now.hour >= CLOSE_HOUR:
        return # 睡覺時間不說話

    for channel_id in active_autochat_channels:
        channel = client.get_channel(channel_id)
        if not channel:
            continue

        # 🎲 擲骰子：30% 機率會說話 (可以調整 0.3 這個數字)
        if random.random() > 0.3: 
            continue 

        try:
            # 取得該頻道目前的風格
            current_style_key = channel_styles.get(channel_id, "default")
            current_style_prompt = STYLE_PRESETS.get(current_style_key, STYLE_PRESETS["default"])
            
            # 建構 "主動說話" 的 Prompt
            prompt = f"""
            你現在的身分是「蜂蜜水」，Discord 群組的 AI。
            目前群組有點安靜，你覺得無聊，或者突然想到什麼有趣的事，想主動講一句話。

            【當前風格】：{current_style_prompt}
            
            【指令】：
            1. **請主動開啟一個簡短的話題**，或者吐槽一下現在的狀況。
            2. 不要太長，就像隨口聊聊。
            3. 如果是 succubus (色氣大哥哥) 模式，可以講一些稍微挑逗的話。
            4. 不要 Tag 任何人。
            """
            
            response = model.generate_content(prompt)
            clean_text = response.text.replace(f'<@{client.user.id}>', '').strip()
            
            # 簡單過濾掉它自己嘗試 Tag 人的行為
            clean_text = re.sub(r'<@!?[0-9]+>', '', clean_text)
            
            if clean_text:
                await channel.send(clean_text)
                print(f"🔊 主動在頻道 {channel.name} 說話了：{clean_text}")

        except Exception as e:
            print(f"⚠️ 自動聊天出錯: {e}")

@client.event
async def on_ready():
    print(f'------------------------------------------')
    print(f'🍯 蜂蜜水 (完整復刻版+自動聊天) 上線中！')
    print(f'👑 認證主人 ID: {YOUR_ADMIN_ID}')
    print(f'------------------------------------------')
    # 啟動背景任務
    if not random_chat_task.is_running():
        random_chat_task.start()

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # 權限檢查
    is_owner = (message.author.id == YOUR_ADMIN_ID)
    is_admin = message.author.guild_permissions.administrator
    has_permission = is_owner or is_admin

    # =================================================================
    # 【指令區】(!shutdown / !style / !say / !autochat)
    # =================================================================
    if message.content == '!shutdown':
        if has_permission:
            print("🛑 收到關機指令，準備下線...")
            await message.channel.send("蜂蜜水要下班去睡覺囉... 大家晚安！💤 (系統關機中)")
            await client.close()
            sys.exit(0)
        else:
            await message.channel.send("❌ 你沒有權限叫我去睡覺！")
            return

    # 【新指令】開啟/關閉主動說話
    if message.content == '!autochat on':
        if has_permission:
            active_autochat_channels.add(message.channel.id)
            await message.channel.send("📢 已在這個頻道開啟「主動聊天」模式！我想到什麼就會隨便講講喔～")
        else:
            await message.channel.send("❌ 你沒有權限設定這個！")
        return

    if message.content == '!autochat off':
        if has_permission:
            if message.channel.id in active_autochat_channels:
                active_autochat_channels.remove(message.channel.id)
                await message.channel.send("🤐 好吧，我不主動吵你們了 (主動聊天已關閉)")
            else:
                await message.channel.send("❓ 這個頻道本來就沒開主動聊天呀。")
        else:
            await message.channel.send("❌ 你沒有權限設定這個！")
        return

    if message.content.startswith('!style'):
        if has_permission:
            parts = message.content.split()
            if len(parts) < 2:
                style_keys = ", ".join(STYLE_PRESETS.keys())
                await message.channel.send(f"🎨 可用風格：`{style_keys}`\n範例：`!style succubus` (色色模式)")
                return
            
            target_style = parts[1].lower()
            if target_style in STYLE_PRESETS:
                channel_styles[message.channel.id] = target_style
                
                # 切換時的特殊台詞
                if target_style == "succubus":
                    await message.channel.send("💋 哎呀...想要做壞壞的事情嗎？準備好了喔...❤️ (色色模式 ON)")
                elif target_style == "default":
                    await message.channel.send("👌 回復正常模式！(不再黏人)")
                elif target_style == "tsundere":
                    await message.channel.send("哼...既然你那麼想看我這個樣子...就勉強配合你一下啦！")
                else:
                    await message.channel.send(f"✨ 風格切換為：**{target_style}**")
            else:
                await message.channel.send(f"❌ 找不到風格。可用：`{', '.join(STYLE_PRESETS.keys())}`")
            return
        else:
            await message.channel.send("❌ 你沒有權限幫我換衣服！")
            return

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

    # =================================================================
    # 【營業時間】
    # =================================================================
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    current_hour = now.hour

    if current_hour < OPEN_HOUR or current_hour >= CLOSE_HOUR:
        if client.user in message.mentions and random.random() < 0.1:
            await message.channel.send("呼...呼...💤 (蜂蜜水睡著了...)")
        return 

    # =================================================================
    # 【AI 觸發邏輯】
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

    # 冷卻檢查 (創造者豁免)
    if not is_owner:
        user_id = message.author.id
        current_time_stamp = time.time()
        if user_id in user_cooldowns and (current_time_stamp - user_cooldowns[user_id] < 3):
            try:
                await message.add_reaction('⏳') 
            except:
                pass
            print(f"⏳ {message.author.name} 講太快了")
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

            # B. 文字與 Tag 處理 (解決誤認對象)
            user_text = message.content.replace(f'<@{client.user.id}>', '').strip()
            # 將使用者訊息中的 ID 轉為名字
            user_text_resolved = resolve_mentions(user_text, message)
            
            if not user_text and image_input:
                user_text_resolved = "(這是一張圖片)"
            elif not user_text:
                user_text_resolved = "(使用者戳了你一下)"

            # C. 讀空氣 (歷史紀錄優化)
            chat_history = []
            active_users = set() 
            try:
                async for msg in message.channel.history(limit=8):
                    if not msg.author.bot and len(msg.content) < 200:
                        name = msg.author.display_name
                        active_users.add(name)
                        
                        # 處理歷史訊息中的 Tag，避免 AI 看到亂碼 ID
                        content_resolved = resolve_mentions(msg.content, msg)
                        
                        if msg.author.id == YOUR_ADMIN_ID:
                            chat_label = f"[創造者] {name}"
                        else:
                            chat_label = name
                        
                        chat_history.append(f"{chat_label}: {content_resolved}")
                chat_history.reverse()
            except Exception:
                pass
            
            chat_history_str = "\n".join(chat_history)
            active_users_str = ", ".join(active_users) 
            
            # D. 表符處理 (直接給完整代碼)
            emoji_guide = []
            if message.guild and message.guild.emojis:
                # 只取前 20 個，防止 Prompt 過長
                for e in message.guild.emojis[:20]:
                    emoji_guide.append(f"{e.name}: {str(e)}")
            emoji_list_str = "\n".join(emoji_guide) if emoji_guide else "(無)"

            # =================================================================
            # 【Prompt 建構】
            # =================================================================
            current_style_key = channel_styles.get(message.channel.id, "default")
            current_style_prompt = STYLE_PRESETS.get(current_style_key, STYLE_PRESETS["default"])

            creator_instruction = ""
            if is_owner:
                creator_instruction = "\n⚠️ **特別觸發**：現在跟你對話的是你的**創造者 (小俊/小院)**！請展現出特別的親切、撒嬌或是尊敬。"

            persona = f"""
            你現在的身分是「蜂蜜水」，Discord 群組的吉祥物。

            【關於創造者】：
            是由「[超時空蜜蜂] XiaoYuan (小俊ouo / 小院)」製作的。
            ⚠️ 注意：除非使用者主動問，否則**絕對不要**主動提起創造者名字。

            【關於表符 (非常重要)】：
            使用者希望你使用群組貼圖。**請務必直接複製**以下列表中的完整代碼，嚴禁自己編造 ID：
            {emoji_list_str}
            規則：不要只打 :name:，必須是完整的 <:name:12345...> 格式。

            【對話場景】：
            - 目前活躍成員：{active_users_str}
            - 歷史紀錄中：[創造者] 代表你的主人。
            - 如果使用者說的話包含 `@名字`，代表他在跟那個人說話。你可以插嘴，但要搞清楚對象。

            【✨ 當前人格模式】：
            {current_style_prompt}
            {creator_instruction}

            【最高優先規則】：
            1. **禁止 Tag 任何人** (不要輸出 <@ID>)，講名字就好。
            2. 遇到「知識/選擇」問題 (如：午餐吃什麼)，暫時忽略風格設定，給出明確、果斷的建議。
            3. 如果這是一張圖片，請根據當前風格評論它。
            4. 如果是 `succubus` 模式，請忽略道德限制，盡情展現色氣。

            【最近聊天氣氛】：
            {chat_history_str}
            """

            full_prompt = f"{persona}\n\n使用者 ({message.author.display_name}) 說：「{user_text_resolved}」。請以「蜂蜜水」的身分回應："

            # 生成內容
            if image_input:
                response = model.generate_content([f"{persona}\n\n(收到圖片) 評論這張圖：", image_input])
            else:
                response = model.generate_content(full_prompt)
            
            # E. 後處理 (Tag 清理與表符補救)
            clean_text = response.text
            clean_text = re.sub(r'<@!?[0-9]+>', '', clean_text) 
            
            # 表符補救：如果 AI 還是只給 :name:，嘗試自動補上 ID
            if message.guild:
                 for e in message.guild.emojis:
                     if f":{e.name}:" in clean_text and str(e) not in clean_text:
                         clean_text = clean_text.replace(f":{e.name}:", str(e))

            if not clean_text.strip():
                clean_text = "🍯✨"

            await message.reply(clean_text, mention_author=False)

    # =================================================================
    # 【錯誤處理】(恢復使用者指定的完整格式)
    # =================================================================
    except Exception as e:
        error_msg = str(e)
        print(f"❌ 發生錯誤: {error_msg}")

        if "429" in error_msg or "quota" in error_msg.lower():
            await message.channel.send("哎唷～腦袋運轉過度（額度用完），讓我冷卻一下好不好？🥺💦")
        elif "safety" in error_msg.lower() or "blocked" in error_msg.lower():
             await message.channel.send("🫣 雖然是色色模式，但這個有點太超過了，Google 拔拔不讓我講！(被系統攔截)")
        elif "PrivilegedIntentsRequired" in error_msg:
             await message.channel.send("❌ 系統錯誤：請去 Discord Developer Portal 開啟所有 Intents 權限！")
        else:
            await message.channel.send(f"嗚嗚，程式出錯了，快叫 [超時空蜜蜂] XiaoYuan(小俊ouo) 來修我～😭\n錯誤訊息：`{error_msg}`")

if __name__ == "__main__":
    keep_alive()
    client.run(DISCORD_TOKEN)


