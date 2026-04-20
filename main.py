import sqlite3
from datetime import datetime
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

# ===== DB =====
conn = sqlite3.connect("data.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    group_name TEXT
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS stats (
    user_id INTEGER,
    date TEXT,
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

# ===== 主選單 =====
def main_menu():
    return ReplyKeyboardMarkup([
        ["📊 查看數據", "📝 填報數據"],
        ["👥 分組管理", "📈 分組數據"],
        ["🏆 排行榜", "📅 每月報表"],
        ["📊 分組詳細","📤 導出數據"],
    ], resize_keyboard=True)

# ===== 分組選單 =====
def group_menu():
    return ReplyKeyboardMarkup([
        ["➕ 建立分組"],
        ["👤 加入分組"],
        ["❌ 移出分組"],
        ["👥 查看分組成員"],
        ["🔙 返回主選單"]
    ], resize_keyboard=True)

# ===== 查看分組成員 =====
async def view_group_members(update):
    c.execute("SELECT group_name, name FROM users")

    groups = {}
    for g, name in c.fetchall():
        g = g or "未分組"
        groups.setdefault(g, []).append(name)

    msg = "👥 分組成員列表\n\n"

    for g, members in groups.items():
        msg += f"【{g}】\n"
        for m in members:
            msg += f" - {m}\n"
        msg += "\n"

    # ✅ 保證返回鍵存在
    await update.message.reply_text(msg, reply_markup=group_menu())

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

# ===== 分組入口 =====
async def group_manage_menu(update):
    await update.message.reply_text(
        "👥 分組管理\n請選擇功能",
        reply_markup=group_menu()
    )

# ===== 查看數據 =====
async def view_data(update):
    c.execute("""
    SELECT u.group_name, u.name,
    s.打粉,s.回復,s.新增,s.回訪,s.熱聊
    FROM users u
    LEFT JOIN stats s
    ON u.user_id=s.user_id AND s.date=?
    """,(today(),))

    msg = "📊 今日數據\n\n"

    for r in c.fetchall():
        msg += f"【{r[0] or '未分組'}】{r[1]}\n"
        msg += f"打粉：{r[2] or 0} 回復：{r[3] or 0} 新增：{r[4] or 0} 回訪：{r[5] or 0} 熱聊：{r[6] or 0}\n\n"

    await update.message.reply_text(msg)

# ===== 排行榜 =====
async def ranking(update):
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

# ===== 分組數據（修復）=====
async def group_rank(update):
    c.execute("SELECT DISTINCT group_name FROM users WHERE group_name IS NOT NULL")
    groups = c.fetchall()

    msg = "📈 分組數據\n\n"

    if not groups:
        msg += "目前沒有任何分組"
    else:
        for g in groups:
            msg += f"【{g[0]}】\n"

            c.execute("""
            SELECT u.name, SUM(s.打粉)
            FROM users u
            JOIN stats s ON u.user_id=s.user_id
            WHERE u.group_name=? AND s.date=?
            GROUP BY u.user_id
            """,(g[0],today()))

            rows = c.fetchall()

            if not rows:
                msg += "無數據\n"
            else:
                for r in rows:
                    msg += f"{r[0]}：{r[1] or 0}\n"

            msg += "\n"

    # ✅ 防止看起來沒反應
    await update.message.reply_text(msg, reply_markup=main_menu())

# ===== 每月報表（修復）=====
async def monthly(update):
    c.execute("""
    SELECT u.name,
    SUM(s.打粉),SUM(s.回復),SUM(s.新增),SUM(s.回訪),SUM(s.熱聊)
    FROM users u
    JOIN stats s ON u.user_id=s.user_id
    WHERE strftime('%Y-%m', s.date)=strftime('%Y-%m','now')
    GROUP BY u.user_id
    """)

    rows = c.fetchall()

    msg = "📅 本月報表\n\n"

    if not rows:
        msg += "目前沒有數據"
    else:
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
        value = int(text)

        field = context.user_data["field"]

        c.execute("SELECT * FROM stats WHERE user_id=? AND date=?",
                  (user_id, today()))
        if not c.fetchone():
            c.execute("INSERT INTO stats (user_id,date) VALUES (?,?)",
                      (user_id, today()))

        c.execute(f"UPDATE stats SET {field}=? WHERE user_id=? AND date=?",
                  (value, user_id, today()))
        conn.commit()

        context.user_data.pop("field")

        await update.message.reply_text(
            f"✅ 已記錄{field}: {value}",
            reply_markup=main_menu()
        )
        return True

    return False

# ===== 主處理 =====
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text in ["🔙 返回主選單", "返回主選單"]:
        context.user_data.clear()
        return await update.message.reply_text("返回主選單", reply_markup=main_menu())

    if text == "📝 填報數據":
        return await update.message.reply_text("選擇項目", reply_markup=report_menu())

    handled = await handle_report(update, context)
    if handled:
        return

    if text == "👥 分組管理":
        return await group_manage_menu(update)

    if "查看分組成員" in text:
        return await view_group_members(update)

    if text == "➕ 建立分組":
        context.user_data["mode"] = "create_group"
        return await update.message.reply_text("請輸入分組名稱")

    if text == "👤 加入分組":
        context.user_data["mode"] = "join_group"
        return await update.message.reply_text("請輸入分組名稱")

    if text == "❌ 移出分組":
        c.execute("UPDATE users SET group_name=NULL WHERE user_id=?", (update.effective_user.id,))
        conn.commit()
        return await update.message.reply_text("已移出分組", reply_markup=group_menu())

    if context.user_data.get("mode") == "create_group":
        context.user_data.clear()
        return await update.message.reply_text(f"已建立：{text}", reply_markup=group_menu())

    if context.user_data.get("mode") == "join_group":
        c.execute("UPDATE users SET group_name=? WHERE user_id=?", (text, update.effective_user.id))
        conn.commit()
        context.user_data.clear()
        return await update.message.reply_text(f"已加入：{text}", reply_markup=group_menu())

    if text == "📊 查看數據":
        return await view_data(update)

    if text == "🏆 排行榜":
        return await ranking(update)

    if text == "📈 分組數據":
        return await group_rank(update)

    if text == "📅 每月報表":
        return await monthly(update)

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
app.run_polling()
