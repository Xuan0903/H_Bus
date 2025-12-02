# -*- coding: utf-8 -*-
"""
每天 08:00 自動：
1) 查詢 reservation：今天、review_status='approved'
2) 連 users 表拿 email
3) 依使用者彙整並寄出確認信

依賴：
- 你的 MySQL_Run 函式 (from MySQL import MySQL_Run)
- Gmail 應用程式密碼 (建議放在 .env)
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from Backend.MySQL import MySQL_Doing 
# === 載入環境變數 ===
load_dotenv()

SENDER_EMAIL = os.getenv("Sender_email")
SENDER_PASS  = os.getenv("Password_email")
TZ = ZoneInfo("Asia/Taipei")
MySQL_Doing = MySQL_Doing()

# ========== 信件樣板 ==========
MAIL_SUBJECT = "【乘車提醒】您今日的預約資訊"
MAIL_TEXT_TEMPLATE = """親愛的乘客您好，

以下為您今日 ({today}) 的預約資訊：
{lines}

若資訊有誤或需更改，請盡速與我們聯繫。祝您旅途順利！

— 花蓮小巴預約系統
"""
# ========== 郵件發送 ==========
def send_email(receiver_email: str, subject: str, text: str):
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = SENDER_EMAIL
    message["To"] = receiver_email

    part1 = MIMEText(text, "plain", "utf-8")
    message.attach(part1)

    smtp_server = "smtp.gmail.com"
    port = 465  # SSL

    with smtplib.SMTP_SSL(smtp_server, port) as server:
        server.login(SENDER_EMAIL, SENDER_PASS)
        server.sendmail(SENDER_EMAIL, receiver_email, message.as_string())

# ========== 查詢今天預約 & 準備寄信名單 ==========
def fetch_today_reservations() -> pd.DataFrame:
    """
    回傳欄位：
      email, user_id, reservation_id, booking_time, booking_number,
      booking_start_station_name, booking_end_station_name, review_status, payment_status
    僅限今天 + approved
    """
    sql = """
    SELECT 
        u.email,
        r.user_id,
        r.reservation_id,
        r.booking_time,
        r.booking_number,
        r.booking_start_station_name,
        r.booking_end_station_name,
        r.review_status,
        r.payment_status
    FROM reservation r
    JOIN users u ON u.user_id = r.user_id
    WHERE r.review_status = 'approved'
      AND DATE(r.booking_time) = CURDATE()
      AND u.email IS NOT NULL
      AND u.email <> '';
    """
    rows = MySQL_Doing.run(sql)
    df = pd.DataFrame(rows)
    # 安全處理：若表空或欄位大小寫/命名不同，可在此做 rename
    return df

# ========== 組信內容（依 email 彙整多筆預約） ==========
def build_and_send_emails():
    now = datetime.now(TZ)
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 開始檢查今日預約…")

    try:
        df = fetch_today_reservations()
    except Exception as e:
        print(f"[{datetime.now(TZ):%Y-%m-%d %H:%M:%S}] 查詢 DB 失敗：{e}")
        return

    if df.empty:
        print(f"[{datetime.now(TZ):%Y-%m-%d %H:%M:%S}] 今日無符合條件的預約。")
        return

    required_cols = {
        "email", "reservation_id", "booking_time", "booking_number",
        "booking_start_station_name", "booking_end_station_name"
    }
    missing = required_cols - set(df.columns)
    if missing:
        print(f"[{datetime.now(TZ):%Y-%m-%d %H:%M:%S}] 结果少欄位: {missing}")
        return

    grouped = df.groupby("email", dropna=True)

    success, fail = 0, 0
    for email, g in grouped:
        lines = []
        for _, r in g.iterrows():
            bt = str(r["booking_time"])
            line = (
                f"- 預約編號: {r['reservation_id']}｜"
                f"時間: {bt}｜"
                f"人數: {r['booking_number']}｜"
                f"{r['booking_start_station_name']} → {r['booking_end_station_name']}"
            )
            lines.append(line)

        body = MAIL_TEXT_TEMPLATE.format(
            today=f"{now:%Y-%m-%d}",
            lines="\n".join(lines)
        )

        try:
            send_email(email, MAIL_SUBJECT, body)
            print(f"✔ 已寄出：{email}（{len(g)} 筆）")
            success += 1
        except Exception as e:
            print(f"✘ 寄送失敗：{email} → {e}")
            fail += 1

    print(f"[{datetime.now(TZ):%Y-%m-%d %H:%M:%S}] 寄送完成：成功 {success} 位、失敗 {fail} 位。")

# ========== 主程式：每天 08:00 自動執行 ==========
def main(hour=8, minute=0):
    scheduler = BlockingScheduler(timezone=TZ)
    scheduler.add_job(
        build_and_send_emails,
        CronTrigger(hour=hour, minute=minute),
        id="daily_0800_send"
    )

    print(f"排程已啟動（Asia/Taipei）。每天 {hour:02d}:{minute:02d} 寄送今日乘車提醒。")
    print("按 Ctrl+C 可停止。")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("排程停止。")

if __name__ == "__main__":
    main(hour=8, minute=00)