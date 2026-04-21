import sqlite3
from datetime import datetime, timedelta
import pandas as pd

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)

import os
TOKEN = os.getenv("BOT_TOKEN")
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


# ===== DB =====
conn = sqlite3.connect("data.db", check_same_thread=False)
c = conn.cursor()

# users
c.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    group_name TEXT
)
""")

# stats（保留 group_name 歷史）
c.execute("""
CREATE TABLE IF NOT EXISTS stats (
    user_id INTEGER,
    date TEXT,
    group_name TEXT,
    打粉 INTEGER DEFAULT 0,
    回復 INTEGER DEFAULT 0,
    新增 INTEGER DEFAULT 0,
    回訪 INTEGER DEFAULT 0,
    熱聊 INTEGER DEFAULT 0
)
""")

conn.commit()

def today():
    return datetime.now().strftime("%Y-%m-%d")

# ===== 30天清理 =====
def clean_old_data():
    limit_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    c.execute("DELETE FROM stats WHERE date < ?", (limit_date,))
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
        ["❌ 移出分組", "👥 查看分組成員"],
        ["👤 我的分組"],   # ← 新增這行
        ["🔙 返回主選單"]
    ], resize_keyboard=True)

# ===== 分組成員 =====
async def view_group_members(update):
    c.execute("""
    SELECT IFNULL(group_name,'未分組'), name
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

    c.execute("SELECT group_name FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()

    if not result or not result[0]:
        msg = "❌ 你目前尚未加入任何分組"
    else:
        msg = f"👤 你目前所在分組：{result[0]}"

    await update.message.reply_text(msg, reply_markup=group_menu())

# ===== 分組總數 =====
async def group_total_stats(update):
    clean_old_data()

    c.execute("""
    SELECT 
        IFNULL(u.group_name,'未分組'),
        SUM(s.打粉),SUM(s.回復),SUM(s.新增),
        SUM(s.回訪),SUM(s.熱聊)
    FROM users u
    LEFT JOIN stats s 
        ON u.user_id = s.user_id 
        AND s.date = ?
    GROUP BY IFNULL(u.group_name,'未分組')
    """,(today(),))

    rows = c.fetchall()

    msg = "📊 分組總數（今日）\n\n"

    if not rows:
        msg += "沒有數據"
    else:
        for r in rows:
            msg += f"【{r[0]}】\n"
            msg += f"打粉:{r[1] or 0} 回復:{r[2] or 0} 新增:{r[3] or 0} 回訪:{r[4] or 0} 熱聊:{r[5] or 0}\n\n"

    await update.message.reply_text(msg, reply_markup=main_menu())

# ===== 導出 Excel（完整版本）=====
async def export_data(update, context):
    try:
        print("开始导出")

        clean_old_data()

        # 今日数据
        c.execute("""
        SELECT u.user_id, u.name, IFNULL(u.group_name,'未分組'),
        IFNULL(s.打粉,0), IFNULL(s.回復,0), IFNULL(s.新增,0),
        IFNULL(s.回訪,0), IFNULL(s.熱聊,0)
        FROM users u
        LEFT JOIN stats s
        ON u.user_id = s.user_id AND s.date=?
        """,(today(),))
        today_rows = c.fetchall()

        # 本月数据
        c.execute("""
        SELECT user_id,
        SUM(打粉), SUM(回復), SUM(新增),
        SUM(回訪), SUM(熱聊)
        FROM stats
        WHERE strftime('%Y-%m', date)=strftime('%Y-%m','now')
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
                group,
                name,
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
        df.to_excel(file_name, index=False, engine="openpyxl")

        await update.message.reply_document(document=open(file_name, "rb"))

    except Exception as e:
        print("导出错误：", e)
        await update.message.reply_text(f"❌ 导出失败：{e}")

# 👇👇👇 就貼在這裡 👇👇👇

# ===== 分組詳細（自己小組成員總數）=====
async def group_detail_stats(update, context):
    clean_old_data()

    user_id = update.effective_user.id

    # 查自己分組
    c.execute("SELECT group_name FROM users WHERE user_id=?", (user_id,))
    result = c.fetchone()

    if not result or not result[0]:
        return await update.message.reply_text("❌ 你沒有分組")

    group_name = result[0]

    # 查該組所有成員數據
    c.execute("""
    SELECT user_id,
    SUM(打粉),SUM(回復),SUM(新增),SUM(回訪),SUM(熱聊)
    FROM stats
    WHERE IFNULL(group_name,'未分組')=? AND date=?
    GROUP BY user_id
    """,(group_name, today()))

    rows = c.fetchall()

    msg = f"📊 分組詳細（{group_name}）\n\n"

    if not rows:
        msg += "目前沒有數據"
    else:
        for r in rows:
            uid = r[0]

            c.execute("SELECT name FROM users WHERE user_id=?", (uid,))
            name = c.fetchone()[0]

            msg += f"{name}\n"
            msg += f"打粉:{r[1] or 0} 回復:{r[2] or 0} 新增:{r[3] or 0} 回訪:{r[4] or 0} 熱聊:{r[5] or 0}\n\n"

    await update.message.reply_text(msg, reply_markup=main_menu())

# ===== 填報選單 =====
def report_menu():
    return ReplyKeyboardMarkup([
        ["今日打粉","今日回復"],
        ["今日新增","今日回訪"],
        ["今日熱聊","🔙 返回主選單"]
    ], resize_keyboard=True)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    c.execute("INSERT OR IGNORE INTO users VALUES (?,?,?)",
              (user.id, user.first_name, None))
    conn.commit()

    await update.message.reply_text(
        "📊 打粉統計機器人已啟動",
        reply_markup=main_menu()
    )

async def group_manage_menu(update):
    await update.message.reply_text(
        "👥 分組管理\n請選擇功能",
        reply_markup=group_menu()
    )

# ===============================
# ✅【修改】查看數據（只改這一個 function）
# ===============================
async def view_data(update, context):
    clean_old_data()

    user_id = update.effective_user.id
    admin = await is_admin(update, context)

    if admin:
        c.execute("""
        SELECT u.group_name, u.name,
        s.打粉,s.回復,s.新增,s.回訪,s.熱聊
        FROM users u
        LEFT JOIN stats s
        ON u.user_id=s.user_id AND s.date=?
        """,(today(),))
    else:
        c.execute("""
        SELECT u.group_name, u.name,
        s.打粉,s.回復,s.新增,s.回訪,s.熱聊
        FROM users u
        LEFT JOIN stats s
        ON u.user_id=s.user_id AND s.date=?
        WHERE u.user_id=?
        """,(today(), user_id))

    msg = "📊 今日數據\n\n"
    for r in c.fetchall():
        msg += f"【{r[0] or '未分組'}】{r[1]}\n"
        msg += f"打粉：{r[2] or 0} 回復：{r[3] or 0} 新增：{r[4] or 0} 回訪：{r[5] or 0} 熱聊：{r[6] or 0}\n\n"

    await update.message.reply_text(msg)

# ===== 排行榜 =====
async def ranking(update):
    clean_old_data()

    c.execute("""
    SELECT u.name, SUM(s.打粉)
    FROM users u
    JOIN stats s ON u.user_id=s.user_id
    WHERE s.date=?
    GROUP BY u.user_id
    ORDER BY SUM(s.打粉) DESC LIMIT 10
    """,(today(),))

    msg = "🏆 今日排行榜\n\n"
    for i,r in enumerate(c.fetchall(),1):
        msg += f"{i}. {r[0]} 打粉:{r[1] or 0}\n"

    await update.message.reply_text(msg)

# ===== 分組數據（所有小組總數）=====
async def group_rank(update):
    clean_old_data()

    c.execute("""
    SELECT 
        IFNULL(u.group_name,'未分組'),
        SUM(s.打粉),SUM(s.回復),SUM(s.新增),
        SUM(s.回訪),SUM(s.熱聊)
    FROM users u
    LEFT JOIN stats s 
        ON u.user_id = s.user_id 
        AND s.date = ?
    GROUP BY IFNULL(u.group_name,'未分組')
    """,(today(),))

    rows = c.fetchall()
    print("分组数据 rows:", rows)  # 🔥 关键调试

    msg = "📈 分組數據（今日總數）\n\n"

    if not rows:
        msg += "目前沒有數據"
    else:
        for r in rows:
            msg += f"【{r[0]}】\n"
            msg += f"打粉:{r[1] or 0} 回復:{r[2] or 0} 新增:{r[3] or 0} 回訪:{r[4] or 0} 熱聊:{r[5] or 0}\n\n"

    await update.message.reply_text(msg, reply_markup=main_menu())
    
# ===== 每月 =====
async def monthly(update):
    clean_old_data()

    c.execute("""
    SELECT u.name,
    SUM(s.打粉),SUM(s.回復),SUM(s.新增),SUM(s.回訪),SUM(s.熱聊)
    FROM users u
    LEFT JOIN stats s ON u.user_id=s.user_id
    WHERE strftime('%Y-%m', IFNULL(s.date,'')) = strftime('%Y-%m','now')
    GROUP BY u.user_id
    """)

    rows = c.fetchall()

    msg = "📅 本月報表\n\n"

    for r in rows:
        msg += f"{r[0]} 打粉:{r[1] or 0} 回復:{r[2] or 0} 新增:{r[3] or 0} 回訪:{r[4] or 0} 熱聊:{r[5] or 0}\n"

    await update.message.reply_text(msg, reply_markup=main_menu())

# ===== 填報 =====
async def handle_report(update, context):
    text = update.message.text
    user_id = update.effective_user.id

    mapping = {
        "今日打粉":"打粉",
        "今日回復":"回復",
        "今日新增":"新增",
        "今日回訪":"回訪",
        "今日熱聊":"熱聊"
    }

    if text in mapping:
        context.user_data["field"] = mapping[text]
        await update.message.reply_text(f"請輸入{text}數量")
        return True

    if "field" in context.user_data:
        try:
            value = int(text)
        except:
            await update.message.reply_text("請輸入數字")
            return True

        field = context.user_data["field"]

        c.execute("SELECT group_name FROM users WHERE user_id=?", (user_id,))
        group = c.fetchone()[0]

        c.execute("SELECT * FROM stats WHERE user_id=? AND date=?",
                  (user_id, today()))
        if not c.fetchone():
            c.execute("INSERT INTO stats (user_id,date,group_name) VALUES (?,?,?)",
                      (user_id, today(), group))

        c.execute(f"UPDATE stats SET {field}=? WHERE user_id=? AND date=?",
                  (value, user_id, today()))
        conn.commit()

        context.user_data.pop("field")

        await update.message.reply_text(
            f"✅ 已記錄{field}: {value}",
            reply_markup=report_menu()
        )
        return True

    return False

# ===== handle =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    # 返回主菜单
    if text in ["🔙 返回主選單", "返回主選單"]:
        context.user_data.clear()
        return await update.message.reply_text("返回主選單", reply_markup=main_menu())

    # ===== 基础功能 =====
    if text == "📊 分組總數":
        return await group_total_stats(update)

    if text == "📅 每月報表":
        return await monthly(update)

    if text == "📊 查看數據":
        return await view_data(update, context)

    if text == "🏆 排行榜":
        return await ranking(update)

    if "分组数据" in text or text in ["📈 分组数据", "📊 分組數據"]:
        return await group_rank(update)

    if text == "📊 分組詳細":
        return await group_detail_stats(update, context)

    if text == "📤 導出數據":
        if update.effective_user.id != ADMIN_ID:
            return await update.message.reply_text("❌ 只有群主可以導出數據")
        return await export_data(update, context)

    if text == "📝 填報數據":
        return await update.message.reply_text("選擇項目", reply_markup=report_menu())

    if "查看分組成員" in text:
        return await view_group_members(update)

    if text == "👤 我的分組":
        return await my_group(update)

    # ===== 分組管理入口 =====
    if text in ["👥 分组管理", "👥 分組管理"]:
        return await group_manage_menu(update)

    # ===== 建立分組 =====
    if text == "➕ 建立分組":
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ 只有管理員可以建立分組")
        context.user_data["mode"] = "create_group"
        return await update.message.reply_text("請輸入分組名稱")

    # ===== 加入分組 =====
    if text == "👤 加入分組":
        context.user_data["mode"] = "join_group"
        return await update.message.reply_text("請輸入分組名稱")

    # ===== 🔥 关键：输入分组名字 =====
    if context.user_data.get("mode") == "create_group":
        group_name = text

        c.execute("SELECT 1 FROM users WHERE group_name=?", (group_name,))
        if c.fetchone():
            context.user_data.clear()
            return await update.message.reply_text("❌ 分組已存在", reply_markup=group_menu())

        context.user_data.clear()
        return await update.message.reply_text(
            f"✅ 分組已建立：{group_name}\n👉 成員可自行加入",
            reply_markup=group_menu()
        )

    # ===== 加入分組處理 =====
    if context.user_data.get("mode") == "join_group":
        c.execute("UPDATE users SET group_name=? WHERE user_id=?", (text, update.effective_user.id))
        conn.commit()
        context.user_data.clear()
        return await update.message.reply_text(f"已加入：{text}", reply_markup=group_menu())

    # ===== 填報 =====
    handled = await handle_report(update, context)
    if handled:
        return

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
app.run_polling()
