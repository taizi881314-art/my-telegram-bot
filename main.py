import psycopg2
from datetime import datetime, timedelta
import pandas as pd

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)

import os
TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")  # ✅ 新增

ADMIN_ID = 7784849131
GROUP_CHAT_ID = -5136356372

# ===============================
# ✅【新增】管理員判斷（只新增這段）
# ===============================
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id == ADMIN_ID:
        return True

    try:
        member = await context.bot.get_chat_member(GROUP_CHAT_ID, user_id)
        return member.status in ["administrator", "creator"]
    except:
        return False


# ===== PostgreSQL DB =====
conn = psycopg2.connect(
    DATABASE_URL,
    sslmode='require',
    connect_timeout=10
)
conn.autocommit = True
c = conn.cursor()
def get_cursor():
    global conn, c
    try:
        c.execute("SELECT 1")
    except:
        conn = psycopg2.connect(
            DATABASE_URL,
            sslmode='require',
            connect_timeout=10
        )
        conn.autocommit = True
        c = conn.cursor()
    return c
# users
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    name TEXT,
    group_name TEXT
)
""")

# stats（保留 group_name 歷史）
c.execute("""
CREATE TABLE IF NOT EXISTS stats (
    user_id BIGINT,
    date DATE,
    group_name TEXT,
    打粉 INTEGER DEFAULT 0,
    回復 INTEGER DEFAULT 0,
    新增 INTEGER DEFAULT 0,
    回訪 INTEGER DEFAULT 0,
    熱聊 INTEGER DEFAULT 0,
    UNIQUE(user_id, date)
)
""")

conn.commit()

def today():
    return datetime.now().date()  # 保持這個即可 ✅
# ===== 30天清理 =====
def clean_old_data():
    c = get_cursor()
    limit_date = datetime.now().date() - timedelta(days=30)
    c.execute("DELETE FROM stats WHERE date < %s", (limit_date,))
    conn.commit()

# ===== 主選單 =====
def main_menu():
    return ReplyKeyboardMarkup([
        ["📊 查看数据", "📝 填报数据"],
        ["👥 分组管理", "📈 分组数据"],  # ✅ 改这里
        ["🏆 排行榜", "📅 每月报表"],
        ["📊 分组详细","📤 导出数据"],
        ["📊 分组总数"]
    ], resize_keyboard=True)
def group_menu():
    return ReplyKeyboardMarkup([
        ["➕ 建立分組", "👤 加入分組"],
        ["👥 查看分組成員","👤 我的分組"],
        ["🔙 返回主選單"]
    ], resize_keyboard=True)

# ===== 分組成員 =====
async def view_group_members(update, context):
    c = get_cursor()   # ⭐加這行

    c.execute("""
    SELECT COALESCE(group_name,'未分組'), name
    FROM users
    ORDER BY group_name
    """)

    rows = c.fetchall()

    msg = "👥 分組成員\n\n"

    current_group = None

    for g, name in rows:
        if g != current_group:
            msg += f"\n【{g}】\n"
            current_group = g
        msg += f"- {name}\n"

    await update.message.reply_text(msg, reply_markup=group_menu())
    
# ===== 查看自己分組 =====
async def my_group(update):
    user_id = update.effective_user.id

    c = get_cursor()
    c.execute("SELECT group_name FROM users WHERE user_id=%s", (user_id,))
    result = c.fetchone()

    if not result or not result[0]:
        msg = "❌ 你目前尚未加入任何分組"
    else:
        msg = f"👤 你目前所在分組：{result[0]}"

    await update.message.reply_text(msg, reply_markup=group_menu())
    
# ===== 導出 Excel（完整版本）=====
async def export_data(update, context):
    try:
        c = get_cursor()
        clean_old_data()
        print("开始导出")

        # 今日数据
        c.execute("""
        SELECT u.user_id, u.name, COALESCE(u.group_name,'未分組'),
        COALESCE(s.打粉,0), COALESCE(s.回復,0), COALESCE(s.新增,0),
        COALESCE(s.回訪,0), COALESCE(s.熱聊,0)
        FROM users u
        LEFT JOIN stats s
        ON u.user_id = s.user_id AND s.date=%s
        """,(today(),))
        today_rows = c.fetchall()

        # 本月数据
        c.execute("""
        SELECT user_id,
        SUM(打粉), SUM(回復), SUM(新增),
        SUM(回訪), SUM(熱聊)
        FROM stats
        WHERE to_char(date::date, 'YYYY-MM') = to_char(NOW(), 'YYYY-MM')
        GROUP BY user_id
        """)
        month_data = {row[0]: row[1:] for row in c.fetchall()}

        data = []

        for r in today_rows:
            user_id = r[0]
            name = r[1]
            group = r[2]

            today_vals = r[3:8]
            month_vals = month_data.get(user_id, (0,0,0,0,0))

            data.append([
                group, name,
                today_vals[0], month_vals[0],
                today_vals[1], month_vals[1],
                today_vals[2], month_vals[2],
                today_vals[3], month_vals[3],
                today_vals[4], month_vals[4],
            ])

        if not data:
            return await update.message.reply_text("❌ 沒有數據可導出")

        df = pd.DataFrame(data, columns=[
            "分組","姓名",
            "今日打粉","本月打粉",
            "今日回復","本月回復",
            "今日新增","本月新增",
            "今日回訪","本月回訪",
            "今日熱聊","本月熱聊"
        ])

        file_name = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        df.to_excel(file_name, index=False)
        with open(file_name, "rb") as f:
            await update.message.reply_document(document=f)

    except Exception as e:
        print("导出错误：", e)
        await update.message.reply_text(f"❌ 导出失败：{e}")
# ===== 填報選單 =====
def report_menu():
    return ReplyKeyboardMarkup([
        ["今日打粉","今日回復"],
        ["今日新增","今日回訪"],
        ["今日熱聊","🔙 返回主選單"]
    ], resize_keyboard=True)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = get_cursor()   # ⭐加這行
    user = update.effective_user

    c.execute("""
INSERT INTO users (user_id, name, group_name)
VALUES (%s,%s,%s)
ON CONFLICT (user_id) DO NOTHING
""", (user.id, user.first_name, None))
    conn.commit()

    await update.message.reply_text(
        "📊 打粉統計機器人已啟動",
        reply_markup=main_menu()
    )

async def group_manage_menu(update, context):
    await update.message.reply_text(
        "👥 分組管理\n請選擇功能",
        reply_markup=group_menu()
    )

# ===============================
# ✅【修改】查看數據（只改這一個 function）
# ===============================
async def view_data(update, context):
    c = get_cursor()   # ⭐⭐⭐ 就是你在找的這行
    clean_old_data()

    user_id = update.effective_user.id
    admin = await is_admin(update, context)

    # 👉 先取得自己的分組
    c.execute("SELECT group_name FROM users WHERE user_id=%s", (user_id,))
    result = c.fetchone()
    group_name = result[0] if result else None

    if admin:
        # ✅ 管理員看全部
        c.execute("""
        SELECT u.group_name, u.name,
        s.打粉,s.回復,s.新增,s.回訪,s.熱聊
        FROM users u
        LEFT JOIN stats s
        ON u.user_id=s.user_id AND s.date=%s
        """,(today(),))
    else:
        # ✅ 成員：看自己 + 同分組
        c.execute("""
        SELECT u.group_name, u.name,
        s.打粉,s.回復,s.新增,s.回訪,s.熱聊
        FROM users u
        LEFT JOIN stats s
        ON u.user_id=s.user_id AND s.date=%s
        WHERE u.user_id=%s 
           OR COALESCE(u.group_name,'')=COALESCE(%s, '')
        """,(today(), user_id, group_name))

    rows = c.fetchall()

    if not rows:
        return await update.message.reply_text("❌ 沒有數據")

    msg = "📊 今日數據\n\n"

    for r in rows:
        msg += f"【{r[0] or '未分組'}】{r[1]}\n"
        msg += f"打粉：{r[2] or 0} 回復：{r[3] or 0} 新增：{r[4] or 0} 回訪：{r[5] or 0} 熱聊：{r[6] or 0}\n\n"

    await update.message.reply_text(msg)

# ===== 排行榜 =====
async def ranking(update):
    c = get_cursor()
    clean_old_data()

    c.execute("""
    SELECT u.name, SUM(s.打粉)
    FROM users u
    JOIN stats s 
        ON u.user_id = s.user_id 
        AND s.date = %s
    GROUP BY u.user_id
    ORDER BY SUM(s.打粉) DESC 
    LIMIT 10
    """, (today(),))

    msg = "🏆 今日排行榜\n\n"
    for i, r in enumerate(c.fetchall(), 1):
        msg += f"{i}. {r[0]} 打粉:{r[1] or 0}\n"

    await update.message.reply_text(msg)
# ===== 分組數據（所有小組總數）=====
async def group_total_stats(update):
    c = get_cursor()   # ⭐加這行
    clean_old_data()

    c.execute("""
    SELECT 
        COALESCE(u.group_name,'未分組'),
        SUM(s.打粉),SUM(s.回復),SUM(s.新增),
        SUM(s.回訪),SUM(s.熱聊)
    FROM users u
    LEFT JOIN stats s 
        ON u.user_id = s.user_id 
        AND s.date = %s
    GROUP BY COALESCE(u.group_name,'未分組')
    """,(today(),))

    rows = c.fetchall()

    msg = "📊 分組總數（今日）\n\n"
    has_data = False

    for r in rows:
        total = sum([x or 0 for x in r[1:]])
        if total > 0:
            has_data = True

        msg += f"【{r[0]}】\n"
        msg += f"打粉:{r[1] or 0} 回復:{r[2] or 0} 新增:{r[3] or 0} 回訪:{r[4] or 0} 熱聊:{r[5] or 0}\n\n"

    if not has_data:
        msg = "❌ 今日還沒有任何數據"

    await update.message.reply_text(msg, reply_markup=main_menu())
    
# ===== 每月 =====
async def monthly(update):
    c = get_cursor()   # ⭐加這行
    clean_old_data()

    c.execute("""
    SELECT u.name,
    SUM(s.打粉),SUM(s.回復),SUM(s.新增),SUM(s.回訪),SUM(s.熱聊)
    FROM users u
    LEFT JOIN stats s ON u.user_id=s.user_id
    WHERE to_char(s.date, 'YYYY-MM') = to_char(NOW(), 'YYYY-MM')
    GROUP BY u.user_id
    """)

    rows = c.fetchall()

    msg = "📅 本月報表\n\n"

    for r in rows:
        msg += f"{r[0]} 打粉:{r[1] or 0} 回復:{r[2] or 0} 新增:{r[3] or 0} 回訪:{r[4] or 0} 熱聊:{r[5] or 0}\n"

    await update.message.reply_text(msg, reply_markup=main_menu())

# ===== 填報 =====
async def handle_report(update, context):
    c = get_cursor()   # ⭐加這行
    text = update.message.text.strip()
    user_id = update.effective_user.id

    mapping = {
        "今日打粉":"打粉",
        "今日回復":"回復",
        "今日新增":"新增",
        "今日回訪":"回訪",
        "今日熱聊":"熱聊"
    }

    # 👉 点击按钮
    if text in mapping:
        context.user_data["field"] = mapping[text]
        await update.message.reply_text(
            f"📌 請輸入【{text}】數量（輸入數字）"
        )
        return True

    # 👉 没在填报状态
    if "field" not in context.user_data:
        return False

    # 👉 输入数值
    try:
        value = int(text)
    except:
        await update.message.reply_text("❌ 請輸入數字")
        return True

    field = context.user_data["field"]

    # 👉 获取分组
    c.execute("SELECT group_name FROM users WHERE user_id=%s", (user_id,))
    result = c.fetchone()
    group = result[0] if result else None
    
    # 👉 初始化（关键）
    c.execute("""
INSERT INTO stats 
(user_id, date, group_name, 打粉, 回復, 新增, 回訪, 熱聊)
VALUES (%s,%s,%s,0,0,0,0,0)
ON CONFLICT (user_id, date) DO NOTHING
""", (user_id, today(), group))

    # 👉 更新分组（关键）
    c.execute("""
UPDATE stats SET group_name=%s
WHERE user_id=%s AND date=%s
""", (group, user_id, today()))

      # 👉 更新数据
    c.execute(
    f'UPDATE stats SET "{field}" = COALESCE("{field}",0) + %s WHERE user_id=%s AND date=%s',
    (value, user_id, today())
)
    conn.commit()

    context.user_data.clear()

    await update.message.reply_text(f"✅ 已記錄 {field}: {value}")

    return True
    
# ===== handle =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    c = get_cursor()   # ⭐一定要加
    text = update.message.text.strip()
    
    # ===== 覆蓋確認（⭐一定要放最前面）=====
    if context.user_data.get("confirm_override"):
        if text == "確認":
            group_name = context.user_data.get("pending_group")

            c.execute("UPDATE users SET group_name=%s WHERE user_id=%s",
                      (group_name, update.effective_user.id))
            conn.commit()

            context.user_data.clear()
            return await update.message.reply_text(
                f"✅ 已覆蓋並建立新分組：{group_name}",
                reply_markup=group_menu()
            )
        elif text == "取消":
            context.user_data.clear()
            return await update.message.reply_text(
                "❌ 已取消操作",
                reply_markup=group_menu()
            )
        else:
            return await update.message.reply_text("請輸入【確認】或【取消】")

    # ===== 返回主选单 =====
    if text in ["🔙 返回主選單", "返回主選單"]:
        context.user_data.clear()
        return await update.message.reply_text("返回主選單", reply_markup=main_menu())

    # ===== 填報流程（最高優先）=====
    handled = await handle_report(update, context)
    if handled:
        return

    # ===== 填報入口 =====
    if text in ["📝 填报数据", "📝 填報數據"]:
        return await update.message.reply_text("選擇項目", reply_markup=report_menu())

    # ===== 查看數據 =====
    if text in ["📊 查看数据", "📊 查看數據"]:
        return await view_data(update, context)

    # ===== 排行榜 =====
    if text in ["🏆 排行榜"]:
        return await ranking(update)

    # ===== 分組總數 =====
    if text in ["📊 分组总数", "📊 分組總數"]:
        return await group_total_stats(update)

    # ===== 每月報表 =====
    if text in ["📅 每月报表", "📅 每月報表"]:
        return await monthly(update)

    # ===== 分組數據 =====
    if text in ["📈 分组数据", "📈 分組數據"]:
        c = get_cursor()
        clean_old_data()
        c.execute("""
        SELECT 
            COALESCE(u.group_name,'未分組'),
            SUM(s.打粉),SUM(s.回復),SUM(s.新增),
            SUM(s.回訪),SUM(s.熱聊)
        FROM users u
        LEFT JOIN stats s 
            ON u.user_id = s.user_id 
            AND s.date = %s
        GROUP BY COALESCE(u.group_name,'未分組')
        """,(today(),))

        rows = c.fetchall()

        if not rows:
            return await update.message.reply_text("❌ 沒有分組數據", reply_markup=main_menu())

        msg = "📈 分組數據（今日總數）\n\n"
        has_data = False

        for r in rows:
            total = sum([x or 0 for x in r[1:]])
            if total > 0:
                has_data = True

            msg += f"【{r[0]}】\n"
            msg += f"打粉:{r[1] or 0} 回復:{r[2] or 0} 新增:{r[3] or 0} 回訪:{r[4] or 0} 熱聊:{r[5] or 0}\n\n"

        if not has_data:
            return await update.message.reply_text("❌ 今日還沒有任何數據", reply_markup=main_menu())

        return await update.message.reply_text(msg, reply_markup=main_menu())

    # ===== 分組詳細 =====
    if text in ["📊 分组详细", "📊 分組詳細"]:
        c = get_cursor()
        clean_old_data()

        user_id = update.effective_user.id
        c.execute("SELECT group_name FROM users WHERE user_id=%s", (user_id,))
        result = c.fetchone()

        if not result or not result[0]:
            return await update.message.reply_text("❌ 你沒有分組", reply_markup=main_menu())

        group_name = result[0]

        c.execute("""
        SELECT u.name,
               COALESCE(s.打粉,0),
               COALESCE(s.回復,0),
               COALESCE(s.新增,0),
               COALESCE(s.回訪,0),
               COALESCE(s.熱聊,0)
        FROM users u
        LEFT JOIN stats s
            ON u.user_id = s.user_id AND s.date=%s
        WHERE COALESCE(u.group_name,'未分組')=%s
        """,(today(), group_name))

        rows = c.fetchall()

        if not rows:
            return await update.message.reply_text("❌ 此分組今日沒有數據", reply_markup=main_menu())

        msg = f"📊 分組詳細（{group_name}）\n\n"

        for r in rows:
            msg += f"{r[0]}\n"
            msg += f"打粉:{r[1]} 回復:{r[2]} 新增:{r[3]} 回訪:{r[4]} 熱聊:{r[5]}\n\n"

        return await update.message.reply_text(msg, reply_markup=main_menu())
           
    # ===== 導出數據 =====
    if text in ["📤 导出数据", "📤 導出數據"]:
        if update.effective_user.id != ADMIN_ID:
            return await update.message.reply_text("❌ 只有群主可以導出數據")
        return await export_data(update, context)

    # ===== 分組管理 =====
    if text in ["👥 分组管理", "👥 分組管理"]:
        return await group_manage_menu(update, context)

    if text in ["👥 查看分組成員", "查看分組成員"]:
        return await view_group_members(update, context)

    if text in ["👤 我的分組"]:
        return await my_group(update)

    # ===== 建立分組 =====
    if text in ["➕ 建立分組"]:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ 只有管理員可以建立分組")
        context.user_data["mode"] = "create_group"
        return await update.message.reply_text("請輸入分組名稱")

    # ===== 加入分組 =====
    if text in ["👤 加入分組"]:
        context.user_data["mode"] = "join_group"
        return await update.message.reply_text("請輸入分組名稱")

    # ===== 建立分組流程 =====
    if context.user_data.get("mode") == "create_group":
        group_name = text

        # 1️⃣ 檢查分組是否已存在
        c.execute("SELECT 1 FROM users WHERE group_name=%s", (group_name,))
        if c.fetchone():
            context.user_data.clear()
            return await update.message.reply_text("❌ 分組已存在", reply_markup=group_menu())

        # 2️⃣ 👉 放這裡（檢查自己是否已有分組）
        c.execute("SELECT group_name FROM users WHERE user_id=%s",
                  (update.effective_user.id,))
        old_group = c.fetchone()

        if old_group and old_group[0]:
            context.user_data["pending_group"] = group_name
            context.user_data["confirm_override"] = True
            return await update.message.reply_text(
                f"⚠️ 你目前已在【{old_group[0]}】\n是否要建立新分組並覆蓋？（輸入：確認）"
            )

        # 3️⃣ 再執行建立（更新）
        c.execute("UPDATE users SET group_name=%s WHERE user_id=%s",
                  (group_name, update.effective_user.id))
        conn.commit()

        context.user_data.clear()
        return await update.message.reply_text(
            f"✅ 分組已建立：{group_name}",
            reply_markup=group_menu()
        )
    
    # ===== 加入分組流程 =====
    if context.user_data.get("mode") == "join_group":
        c.execute("UPDATE users SET group_name=%s WHERE user_id=%s", (text, update.effective_user.id))
        conn.commit()
        context.user_data.clear()
        return await update.message.reply_text(f"✅ 已加入：{text}", reply_markup=group_menu())

# ===== RUN =====
def main():
    import asyncio
    asyncio.get_event_loop().set_debug(False)

    app = ApplicationBuilder().token(TOKEN).build()

    await app.bot.delete_webhook(drop_pending_updates=True)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    print("Bot started...")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
