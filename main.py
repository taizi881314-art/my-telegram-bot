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
# ===============================
# ✅【新增】組長判斷（⭐就放這裡）
# ===============================
async def is_group_owner(update, group_name):
    owner = get_group_owner(group_name)
    return update.effective_user.id == owner

from contextlib import contextmanager

@contextmanager
def get_cursor():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cursor = conn.cursor()
    try:
        yield conn, cursor
    finally:
        cursor.close()
        conn.close()

# ===============================
# ✅⭐⭐⭐ 就插在这里（唯一正确位置）⭐⭐⭐
# ===============================
def init_db():
    with get_cursor() as (conn, c):

        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            name TEXT,
            group_name TEXT
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            name TEXT PRIMARY KEY,
            owner_id BIGINT,
            max_members INT DEFAULT 10
        )
        """)

        c.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            user_id BIGINT,
            date DATE,
            group_name TEXT,
            打粉 INT DEFAULT 0,
            回復 INT DEFAULT 0,
            新增 INT DEFAULT 0,
            回訪 INT DEFAULT 0,
            熱聊 INT DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )
        """)

        conn.commit()

# ===============================
# ✅ 2️⃣ 修正分組 + 同步 groups
# ===============================
def fix_group_case():
    with get_cursor() as (conn, c):

        # 統一大小寫
        c.execute("UPDATE users SET group_name = UPPER(group_name)")
        c.execute("UPDATE stats SET group_name = UPPER(group_name)")

        # 同步 groups 表
        c.execute("""
        INSERT INTO groups (name)
        SELECT DISTINCT UPPER(group_name)
        FROM users
        WHERE group_name IS NOT NULL
        ON CONFLICT DO NOTHING
        """)

        conn.commit()
        print("✅ 分組大小寫已統一 + groups 同步完成")

# ⭐ 正確順序

def get_all_groups():
    with get_cursor() as (conn, c):
        c.execute("SELECT name FROM groups ORDER BY name")
        return [row[0] for row in c.fetchall()]


def get_group_owner(group_name):
    with get_cursor() as (conn, c):
        c.execute("SELECT owner_id FROM groups WHERE name=%s", (group_name,))
        r = c.fetchone()
        return r[0] if r else None


def count_group_members(group_name):
    with get_cursor() as (conn, c):
        c.execute("SELECT COUNT(*) FROM users WHERE group_name=%s", (group_name,))
        return c.fetchone()[0]


def get_group_limit(group_name):
    

    with get_cursor() as (conn, c):
        c.execute("SELECT max_members FROM groups WHERE name=%s", (group_name,))
        r = c.fetchone()
        return r[0] if r else 10

def today():
    return datetime.now().date()  # 保持這個即可 ✅
# ===== 30天清理 =====
def clean_old_data():
    with get_cursor() as (conn, c):
        limit_date = datetime.now().date() - timedelta(days=30)
        c.execute("DELETE FROM stats WHERE date < %s", (limit_date,))
# ===== 自動備份（穩定版）=====
def backup_db():
    with get_cursor() as (conn, c):
        c.execute("SELECT * FROM users")
        users = c.fetchall()

        c.execute("SELECT * FROM stats")
        stats = c.fetchall()

        print("✅ 備份成功（記憶體版）")
        print("users:", users[:3])
        print("stats:", stats[:3])
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
    with get_cursor() as (conn, c):
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
async def my_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    with get_cursor() as (conn, c):

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
        with get_cursor() as (conn, c):
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
            os.remove(file_name)   # ⭐⭐⭐ 加這行

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
    with get_cursor() as (conn, c):
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
    admin = await is_admin(update, context)  # ✅ OK

    if admin:
        keyboard = [
            ["➕ 建立分組", "👤 加入分組"],
            ["👥 查看分組成員","👤 我的分組"],
            ["🔙 返回主選單"]
        ]
    else:
        keyboard = [
            ["👤 加入分組"],
            ["👤 我的分組"],
            ["🔙 返回主選單"]
        ]

    await update.message.reply_text(
        "👥 分組管理\n請選擇功能",
        reply_markup=ReplyKeyboardMarkup(
            keyboard,
            resize_keyboard=True,
            one_time_keyboard=True   # ⭐ 加這行
        )
    )

# ===============================
# ✅【修改】查看數據（只改這一個 function）
# ===============================
async def view_data(update, context):
    with get_cursor() as (conn, c):
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

# ===== 手動排行榜（⭐加在這裡）=====
async def ranking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_cursor() as (conn, c):
        clean_old_data()

        c.execute("""
        SELECT u.name,
               COALESCE(s.打粉,0)
        FROM users u
        LEFT JOIN stats s
            ON u.user_id = s.user_id AND s.date = %s
        ORDER BY COALESCE(s.打粉,0) DESC
        LIMIT 10
        """, (today(),))

        rows = c.fetchall()

        if not rows:
            return await update.message.reply_text("❌ 今日沒有數據")

        medals = ["🥇","🥈","🥉"]

        msg = "🏆 今日排行榜\n\n"

        for i, r in enumerate(rows, 1):
            medal = medals[i-1] if i <= 3 else f"{i}."
            msg += f"{medal} {r[0]} 打粉:{r[1]}\n"

        await update.message.reply_text(msg)
# ===== ⭐⭐⭐ 就放在這裡 ⭐⭐⭐ =====
async def auto_send_ranking(context: ContextTypes.DEFAULT_TYPE):
    with get_cursor() as (conn, c):
        clean_old_data()

        c.execute("""
        SELECT u.name,
               COALESCE(s.打粉,0)
        FROM users u
        LEFT JOIN stats s
            ON u.user_id = s.user_id AND s.date = %s
        ORDER BY COALESCE(s.打粉,0) DESC
        LIMIT 10
        """, (today(),))

        rows = c.fetchall()

        if not rows:
            return

        medals = ["🥇","🥈","🥉"]
        msg = "🏆 今日排行榜（自動）\n\n"

        for i, r in enumerate(rows, 1):
            medal = medals[i-1] if i <= 3 else f"{i}."
            msg += f"{medal} {r[0]} 打粉:{r[1]}\n"

        await context.bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=msg
        )


# ===== 分組數據（所有小組總數）=====
async def group_total_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_cursor() as (conn, c):
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
        """, (today(),))

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

# ===== 分組詳細 =====
async def group_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_cursor() as (conn, c):
        c.execute("""
        SELECT 
            u.group_name,
            u.name,
            COALESCE(s."打粉",0),
            COALESCE(s."回復",0),
            COALESCE(s."新增",0),
            COALESCE(s."回訪",0),
            COALESCE(s."熱聊",0)
        FROM users u
        LEFT JOIN stats s
        ON u.user_id = s.user_id AND s.date=%s
        ORDER BY u.group_name
        """, (today(),))

        rows = c.fetchall()

        if not rows:
            return await update.message.reply_text("❌ 沒有數據")

        msg = "📊 分組詳細（今日）\n\n"

        current_group = None

        for r in rows:
            group = r[0] or "未分組"

            if group != current_group:
                msg += f"\n【{group}】\n"
                current_group = group

            msg += f"{r[1]} 👉 打粉:{r[2]} 回復:{r[3]} 新增:{r[4]} 回訪:{r[5]} 熱聊:{r[6]}\n"

        await update.message.reply_text(msg)


# ===== 每月 =====
async def monthly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with get_cursor() as (conn, c):
        clean_old_data()

        c.execute("""
            SELECT u.name,
            SUM(s.打粉),SUM(s.回復),SUM(s.新增),SUM(s.回訪),SUM(s.熱聊)
            FROM users u
            LEFT JOIN stats s ON u.user_id=s.user_id
            WHERE DATE_TRUNC('month', s.date) = DATE_TRUNC('month', %s)
            GROUP BY u.user_id
        """, (today(),))

        rows = c.fetchall()

        msg = "📅 本月報表\n\n"

        for r in rows:
            msg += f"{r[0]} 打粉:{r[1] or 0} 回復:{r[2] or 0} 新增:{r[3] or 0} 回訪:{r[4] or 0} 熱聊:{r[5] or 0}\n"

        await update.message.reply_text(msg, reply_markup=main_menu())


# ===== 填報 =====
async def handle_report(update, context):
    with get_cursor() as (conn, c):
        text = update.message.text.strip()
        user_id = update.effective_user.id

        c.execute("SELECT group_name FROM users WHERE user_id=%s", (user_id,))
        result = c.fetchone()

        if not result or not result[0]:
            await update.message.reply_text(
                "❌ 你還沒加入分組\n👉 請先到「分組管理」加入分組"
            )
            return True

        mapping = {
            "今日打粉":"打粉",
            "今日回復":"回復",
            "今日新增":"新增",
            "今日回訪":"回訪",
            "今日熱聊":"熱聊"
        }

        if text in mapping:
            context.user_data["field"] = mapping[text]
            await update.message.reply_text(f"📌 請輸入【{text}】數量（輸入數字）")
            return True

        if "field" not in context.user_data:
            return False

        try:
            value = int(text)
        except:
            await update.message.reply_text("❌ 請輸入數字")
            return True

        field = context.user_data["field"]
        group = result[0]

        c.execute("""
        INSERT INTO stats 
        (user_id, date, group_name, 打粉, 回復, 新增, 回訪, 熱聊)
        VALUES (%s,%s,%s,0,0,0,0,0)
        ON CONFLICT (user_id, date) DO NOTHING
        """, (user_id, today(), group))

        c.execute("""
        UPDATE stats SET group_name=%s
        WHERE user_id=%s AND date=%s
        """, (group, user_id, today()))

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

    user_id = update.effective_user.id
    text = update.message.text.strip()
    name = update.effective_user.first_name

    # ⭐⭐⭐ 1️⃣ 先处理流程状态（最重要）⭐⭐⭐
    if context.user_data.get("mode") == "create_group":
        with get_cursor() as (conn, c):

            group_name = text.strip().upper()

            if any(group_name.startswith(x) for x in ["📊","👥","🏆","📈","📤","👤","📝"]):
                return await update.message.reply_text("❌ 請輸入分組名稱")

            c.execute("SELECT 1 FROM groups WHERE name=%s", (group_name,))
            if c.fetchone():
                context.user_data.clear()
                return await update.message.reply_text(f"❌ 分組已存在：{group_name}")

            c.execute(
                "INSERT INTO groups (name, owner_id) VALUES (%s,%s)",
                (group_name, user_id)
            )

            c.execute(
                "UPDATE users SET group_name=%s WHERE user_id=%s",
                (group_name, user_id)
            )

            conn.commit()
            context.user_data.clear()

        return await update.message.reply_text(
            f"✅ 分組已建立：{group_name}",
            reply_markup=group_menu()
        )

    if context.user_data.get("mode") == "join_group":
        group_name = text.strip().upper()

        groups = get_all_groups()

        # 🔥 关键：统一大写比较
        groups_upper = [g.upper() for g in groups]

        if group_name not in groups_upper:
            return await update.message.reply_text("❌ 請點按按鈕選擇分組")
        limit = get_group_limit(group_name)
        count = count_group_members(group_name)

        if count >= limit:
            return await update.message.reply_text(f"❌ 此分組已滿（{limit}人）")

        with get_cursor() as (conn, c):
            c.execute(
                "UPDATE users SET group_name=%s WHERE user_id=%s",
                (group_name, user_id)
            )
            conn.commit()

        context.user_data.clear()
        return await update.message.reply_text(
            f"✅ 成功加入分組：{group_name}",
            reply_markup=main_menu()
        )

    # ⭐⭐⭐ 2️⃣ 再处理数据库注册 ⭐⭐⭐
    with get_cursor() as (conn, c):
        c.execute("""
        INSERT INTO users (user_id, name, group_name)
        VALUES (%s,%s,%s)
        ON CONFLICT (user_id) DO NOTHING
        """, (user_id, name, None))
        conn.commit()
    # ⭐⭐⭐ 3️⃣ 填报流程 ⭐⭐⭐
    handled = await handle_report(update, context)
    if handled:
        return

    # ⭐⭐⭐ 4️⃣ 菜单功能 ⭐⭐⭐
    if text in ["🔙 返回主選單", "返回主選單"]:
        context.user_data.clear()
        return await update.message.reply_text("返回主選單", reply_markup=main_menu())

    if text in ["📝 填报数据", "📝 填報數據"]:
        return await update.message.reply_text("選擇項目", reply_markup=report_menu())

    if text in ["📊 查看数据", "📊 查看數據"]:
        return await view_data(update, context)

    if text in ["🏆 排行榜"]:
        return await ranking(update, context)

    if text in ["📤 导出数据"]:
        return await export_data(update, context)

    if text in ["📊 分组总数", "📊 分組總數"]:
        return await group_total_stats(update, context)

    if text in ["📈 分组数据"]:
        return await group_total_stats(update, context)

    if text in ["📊 分组详细"]:
        return await group_detail(update, context)
    
    if text in ["📅 每月报表", "📅 每月報表"]:
        return await monthly(update, context)

    if text in ["👥 分组管理", "👥 分組管理"]:
        return await group_manage_menu(update, context)

    if text in ["👥 查看分組成員"]:
        return await view_group_members(update, context)

    if text in ["👤 我的分組"]:
        return await my_group(update, context)

    if text in ["➕ 建立分組"]:
        if not await is_admin(update, context):
            return await update.message.reply_text("❌ 只有管理員可以建立分組")

        context.user_data["mode"] = "create_group"
        return await update.message.reply_text("請輸入分組名稱")

    if text in ["👤 加入分組"]:
        groups = get_all_groups()

        if not groups:
            return await update.message.reply_text("❌ 目前沒有任何分組")

        keyboard = [[g] for g in groups]
        keyboard.append(["🔙 返回主選單"])

        context.user_data["mode"] = "join_group"

        return await update.message.reply_text(
            "📌 請選擇要加入的分組",
            reply_markup=ReplyKeyboardMarkup(
                keyboard,
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
   
# ===== RUN =====
def main():
    init_db()   # ⭐ 就加这一行
    print("DATABASE_URL =", DATABASE_URL)  # ⭐加這行（就這裡）
    
    fix_group_case()  # 👍 原本就有

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

    # ✅ ⭐ 加在這裡（這段是關鍵）
    from datetime import time
    import pytz
    
    job_queue = app.job_queue  # ⭐⭐⭐ 這行一定要加

    job_queue.run_daily(
        auto_send_ranking,
        time=time(hour=23, minute=0, second=0, tzinfo=pytz.timezone("Asia/Taipei"))
    )

    print("Bot started...")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
