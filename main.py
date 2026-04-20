import sqlite3
from datetime import datetime
import pandas as pd

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)

from docx import Document

# ===== 基本設定 =====
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

# ===== 分組管理選單 =====
def group_menu():
    return ReplyKeyboardMarkup([
        ["➕ 建立分組"],
        ["👤 加入分組"],
        ["❌ 移出分組"],
        ["🔙 返回主選單"]
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

# ===== 分組管理入口 =====
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

# ===== 分組數據 =====
async def group_rank(update):
    c.execute("SELECT DISTINCT group_name FROM users WHERE group_name IS NOT NULL")
    groups = c.fetchall()

    msg = "📈 分組數據\n\n"

    for g in groups:
        msg += f"【{g[0]}】\n"

        c.execute("""
        SELECT u.name, SUM(s.打粉)
        FROM users u
        JOIN stats s ON u.user_id=s.user_id
        WHERE u.group_name=? AND s.date=?
        GROUP BY u.user_id
        """,(g[0],today()))

        for r in c.fetchall():
            msg += f"{r[0]}：{r[1] or 0}\n"

        msg += "\n"

    await update.message.reply_text(msg)

# ===== 每月報表 =====
async def monthly(update):
    c.execute("""
    SELECT u.name,
    SUM(s.打粉),SUM(s.回復),SUM(s.新增),SUM(s.回訪),SUM(s.熱聊)
    FROM users u
    JOIN stats s ON u.user_id=s.user_id
    WHERE strftime('%Y-%m', s.date)=strftime('%Y-%m','now')
    GROUP BY u.user_id
    """)

    msg = "📅 本月報表\n\n"
    for r in c.fetchall():
        msg += f"{r[0]} 打粉:{r[1] or 0} 回復:{r[2] or 0} 新增:{r[3] or 0} 回訪:{r[4] or 0} 熱聊:{r[5] or 0}\n"

    await update.message.reply_text(msg)

# ===== 分組詳細 =====
async def group_detail(update):
    c.execute("""
    SELECT u.group_name, u.name,
    SUM(s.打粉), SUM(s.回復), SUM(s.新增),
    SUM(s.回訪), SUM(s.熱聊)
    FROM users u
    LEFT JOIN stats s ON u.user_id=s.user_id
    GROUP BY u.user_id
    """)

    rows = c.fetchall()
    groups = {}

    for r in rows:
        g = r[0] or "未分組"
        groups.setdefault(g, []).append(r)

    msg = "📊 分組詳細\n\n"

    for g, members in groups.items():
        msg += f"【{g}】\n"
        for m in members:
            msg += f"{m[1]} 打粉:{m[2] or 0} 回復:{m[3] or 0} 新增:{m[4] or 0} 回訪:{m[5] or 0} 熱聊:{m[6] or 0}\n"
        msg += "\n"

    await update.message.reply_text(msg)

# ===== 導出 =====
async def export_doc(update):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("❌ 只有群主可以導出")

    doc = Document()
    doc.add_heading('打粉統計報表', 0)

    c.execute("""
    SELECT u.group_name, u.name,
    SUM(s.打粉), SUM(s.回復), SUM(s.新增),
    SUM(s.回訪), SUM(s.熱聊)
    FROM users u
    LEFT JOIN stats s ON u.user_id=s.user_id
    GROUP BY u.user_id
    """)

    rows = c.fetchall()
    groups = {}

    for r in rows:
        g = r[0] or "未分組"
        groups.setdefault(g, []).append(r)

    for g, members in groups.items():
        doc.add_heading(g, level=1)
        for m in members:
            doc.add_paragraph(
                f"{m[1]} | 打粉:{m[2] or 0} 回復:{m[3] or 0} 新增:{m[4] or 0} 回訪:{m[5] or 0} 熱聊:{m[6] or 0}"
            )

    file = "報表.docx"
    doc.save(file)

    await update.message.reply_document(open(file, "rb"))

# ===== 主處理 =====
async def handle(update: Update, context):
    text = update.message.text

    # ===== 分組管理入口 =====
    if text == "👥 分組管理":
        return await group_manage_menu(update)

    if text == "🔙 返回主選單":
        return await update.message.reply_text("返回主選單", reply_markup=main_menu())

    # ===== 分組操作 =====
    if text == "➕ 建立分組":
        context.user_data["mode"] = "create_group"
        return await update.message.reply_text("請輸入分組名稱")

    if text == "👤 加入分組":
        context.user_data["mode"] = "join_group"
        return await update.message.reply_text("請輸入分組名稱")

    if text == "❌ 移出分組":
        c.execute("UPDATE users SET group_name=NULL WHERE user_id=?",
                  (update.effective_user.id,))
        conn.commit()
        return await update.message.reply_text("✅ 已移出分組")

    mode = context.user_data.get("mode")

    if mode == "create_group":
        context.user_data["mode"] = None
        return await update.message.reply_text(f"✅ 分組已建立：{text}")

    if mode == "join_group":
        c.execute("UPDATE users SET group_name=? WHERE user_id=?",
                  (text, update.effective_user.id))
        conn.commit()
        context.user_data["mode"] = None
        return await update.message.reply_text(f"✅ 已加入分組：{text}")

    # ===== 原功能 =====
    if text == "📊 查看數據":
        return await view_data(update)

    if text == "🏆 排行榜":
        return await ranking(update)

    if text == "📈 分組數據":
        return await group_rank(update)

    if text == "📅 每月報表":
        return await monthly(update)

    if text == "📊 分組詳細":
        return await group_detail(update)

    if text == "📤 導出數據":
        return await export_doc(update)

# ===== RUN =====
app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

if __name__ == "__main__":
    app.run_polling()
