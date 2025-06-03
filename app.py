from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import time
from threading import Thread
import os  # NEW: For using secret file path

app = Flask(__name__)

# === Google Sheet Setup ===
SERVICE_ACCOUNT_FILE = "/etc/secrets/credentials.json"  # 🔐 Use Render's secret file path
scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
client = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)  # ✅ Secure way on Render
sheet = client.open("StudyPlusData").sheet1



# === Rank System ===
def get_rank(xp):
    xp = int(xp)
    if xp >= 500:
        return "📘 Scholar"
    elif xp >= 300:
        return "📗 Master"
    elif xp >= 150:
        return "📙 Intermediate"
    elif xp >= 50:
        return "📕 Beginner"
    else:
        return "🍼 Newbie"


# === Badge System ===
def get_badges(total_minutes):
    badges = []
    if total_minutes >= 50:
        badges.append("🥉 Bronze Mind")
    if total_minutes >= 110:
        badges.append("🥈 Silver Brain")
    if total_minutes >= 150:
        badges.append("🥇 Golden Genius")
    if total_minutes >= 240:
        badges.append("🔷 Diamond Crown")
    return badges


# === Daily Streak ===
def calculate_streak(userid):
    records = sheet.get_all_records()
    dates = set()
    for row in records:
        if str(row['UserID']) == str(userid) and row['Action'] == 'Attendance':
            try:
                date = datetime.strptime(str(row['Timestamp']),
                                         "%Y-%m-%d %H:%M:%S").date()
                dates.add(date)
            except ValueError:
                pass

    if not dates:
        return 0

    streak = 0
    today = datetime.now().date()

    for i in range(0, 365):
        day = today - timedelta(days=i)
        if day in dates:
            streak += 1
        else:
            break
    return streak


# === ROUTES ===


# ✅ !attend
@app.route("/attend")
def attend():
    username = request.args.get('user') or ""
    userid = request.args.get('id') or ""
    now = datetime.now()
    today_date = now.date()  # only the date part, not time

    # Check if this user already gave attendance today
    records = sheet.get_all_records()
    for row in records[::-1]:  # check from latest to oldest
        if str(row['UserID']) == str(userid) and row['Action'] == 'Attendance':
            try:
                row_date = datetime.strptime(str(row['Timestamp']),
                                             "%Y-%m-%d %H:%M:%S").date()
                if row_date == today_date:
                    return f"⚠️ {username}, your attendance for today is already recorded! ✅"
            except ValueError:
                continue

    # Log new attendance
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row(
        [username, userid, timestamp, "Attendance", "10", "", "", ""])
    streak = calculate_streak(userid)

    return f"✅ {username}, your attendance is logged and you earned 10 XP! 🔥 Daily Streak: {streak} days."


# ✅ !start
@app.route("/start")
def start():
    username = request.args.get('user')
    userid = request.args.get('id')
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Check if a session is already running (no stop yet)
    records = sheet.get_all_records()
    for row in reversed(records):
        if str(row['UserID']) == str(userid) and row['Action'] == 'Session Start':
            return f"⚠️ {username} , you already started a session. Use `!stop` before starting a new one."

    # Log a new session start
    sheet.append_row([username, userid, now, "Session Start", "0", "", "", ""])
    return f"⏱️ {username} , your study session has started! Use `!stop` to end it. Happy studying 📚"



# ✅ !stop
@app.route("/stop")
def stop():
    username = request.args.get('user')
    userid = request.args.get('id')
    now = datetime.now()

    records = sheet.get_all_records()

    # Find latest session start
    session_start = None
    row_index = None
    for i in range(len(records) - 1, -1, -1):
        row = records[i]
        if str(row['UserID']) == str(userid) and row['Action'] == 'Session Start':
            try:
                session_start = datetime.strptime(row['Timestamp'], "%Y-%m-%d %H:%M:%S")
                row_index = i + 2  # for updating that row if needed
                break
            except ValueError:
                continue

    if not session_start:
        return f"⚠️ {username} , you didn't start any session. Use `!start` to begin."

    # Calculate duration
    duration_minutes = int((now - session_start).total_seconds() / 60)
    xp_earned = duration_minutes * 2

    # Add final study session row
    sheet.append_row([
        username, userid,
        now.strftime("%Y-%m-%d %H:%M:%S"),
        "Study Session", str(xp_earned),
        session_start.strftime("%Y-%m-%d %H:%M:%S"),
        now.strftime("%Y-%m-%d %H:%M:%S"),
        f"{duration_minutes} min"
    ])

    # Optionally: remove the "Session Start" row or mark it
    sheet.update_cell(row_index, 4, "Session Start ✅")

    # Check badge
    badges = get_badges(duration_minutes)
    badge_message = f" 🎖 {username} , you unlocked a badge: {badges[-1]}! keep it up" if badges else ""

    return f"👩🏻‍💻📓✍🏻 {username} , you studied for {duration_minutes} minutes and earned {xp_earned} XP.{badge_message}"



# ✅ !rank
@app.route("/rank")
def rank():
    username = request.args.get('user')
    userid = request.args.get('id')

    records = sheet.get_all_records()
    total_xp = 0

    for row in records:
        if str(row['UserID']) == str(userid):
            try:
                total_xp += int(row['XP'])
            except ValueError:
                pass

    user_rank = get_rank(total_xp)
    return f"🏅 {username} , you have {total_xp} XP. Your rank is: {user_rank}"


# ✅ !top
@app.route("/top")
def leaderboard():
    records = sheet.get_all_records()
    xp_map = {}

    for row in records:
        name = row['Username']
        try:
            xp = int(row['XP'])
        except ValueError:
            continue

        if name in xp_map:
            xp_map[name] += xp
        else:
            xp_map[name] = xp

    sorted_users = sorted(xp_map.items(), key=lambda x: x[1], reverse=True)[:5]
    message = "🏆 Top 5 Learners:\n"
    for i, (user, xp) in enumerate(sorted_users, 1):
        message += f"{i}. {user} - {xp} XP\n"

    return message.strip()


# ✅ !task
@app.route("/task")
def add_task():
    username = request.args.get('user')
    userid = request.args.get('id')
    msg = request.args.get('msg')

    if not msg or len(msg.strip().split()) < 2:
        return f"⚠️ {username} , please provide a task like: !task Physics Chapter 1 or !task Studying Math."

    records = sheet.get_all_records()
    for row in records[::-1]:
        if str(row['UserID']) == str(userid) and str(
                row['Action']).startswith("Task:") and "✅ Done" not in str(
                    row['Action']):
            return f"⚠️ {username} , please complete your previous task first. Use `!done` to mark it as completed."

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    task_name = msg.strip()
    sheet.append_row([
        username or "", userid or "", now, f"Task: {task_name}", "0", "", "",
        ""
    ])
    return f"✏️ {username} , your task '{task_name}' has been added. Study well! Use `!done` to mark it as completed. Use `!remove` to remove it."


# ✅ !done
@app.route("/done")
def mark_done():
    username = request.args.get('user')
    userid = request.args.get('id')

    records = sheet.get_all_records()

    # Calculate total minutes BEFORE this task
    previous_total_minutes = 0
    for row in records:
        if str(row['UserID']) == str(
                userid) and row['Action'] == "Study Session":
            try:
                minutes = int(str(row['Duration']).replace("min", "").strip())
                previous_total_minutes += minutes
            except (ValueError, KeyError):
                pass

    for i in range(len(records) - 1, -1, -1):
        row = records[i]
        if str(row['UserID']) == str(userid) and str(
                row['Action']).startswith("Task:") and "✅ Done" not in str(
                    row['Action']):
            row_index = i + 2
            task_name = str(row['Action'])[6:]

            # Mark task as done
            sheet.update_cell(row_index, 4, f"Task: {task_name} ✅ Done")

            # Add XP row for completing task
            xp_earned = 15
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sheet.append_row([
                str(username),
                str(userid), now, "Task Completed",
                str(xp_earned), "", "", ""
            ])

            # Recalculate total minutes AFTER this task (no change since task isn't time-based)
            # But still check for badge in case user had already passed a threshold in a previous !stop

            new_total_minutes = previous_total_minutes  # no increase from task
            old_badges = get_badges(previous_total_minutes)
            new_badges = get_badges(new_total_minutes)

            badge_message = ""
            if len(new_badges) > len(old_badges):
                badge_message = f" 🎖 {username} , you unlocked a badge: {new_badges[-1]}! keep it up"

            return f"✅ {username} , you completed your task '{task_name}' and earned {xp_earned} XP! Great job! 💪{badge_message}"

    return f"⚠️ {username} , you don't have any active task. Use `!task Your Task` to add one."


# ✅ !remove
@app.route("/remove")
def remove_task():
    username = request.args.get('user')
    userid = request.args.get('id')

    records = sheet.get_all_records()
    for i in range(len(records) - 1, -1, -1):
        row = records[i]
        if str(row['UserID']) == str(userid) and str(
                row['Action']).startswith("Task:") and "✅ Done" not in str(
                    row['Action']):
            row_index = i + 2
            task_name = str(row['Action'])[6:]
            sheet.delete_rows(row_index)
            return f"🗑️ {username} , your task '{task_name}' has been removed. Use `!task Your Task` to add a new one."

    return f"⚠️ {username} , you have no active task to remove. Use `!task Your Task` to add one."


# ✅ !weeklytop
@app.route("/weeklytop")
def weekly_top():
    records = sheet.get_all_records()
    xp_map = {}
    one_week_ago = datetime.now() - timedelta(days=7)

    for row in records:
        try:
            xp = int(row['XP'])
            timestamp = datetime.strptime(str(row['Timestamp']),
                                          "%Y-%m-%d %H:%M:%S")
            if timestamp >= one_week_ago:
                user = row['Username']
                xp_map[user] = xp_map.get(user, 0) + xp
        except (ValueError, KeyError):
            continue

    sorted_users = sorted(xp_map.items(), key=lambda x: x[1], reverse=True)[:5]
    message = "📆 Weekly Top 5 Learners:\n"
    for i, (user, xp) in enumerate(sorted_users, 1):
        message += f"{i}. {user} - {xp} XP\n"

    return message.strip()


# ✅ !goal
@app.route("/goal")
def goal():
    username = request.args.get('user')
    userid = request.args.get('id')
    msg = request.args.get('msg') or ""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    records = sheet.get_all_records()
    user_row_index = None

    # Find the last goal row or existing goal row for the user
    for i in range(len(records) - 1, -1, -1):
        row = records[i]
        if str(row['UserID']) == str(userid) and row['Goal']:
            user_row_index = i + 2
            break

    if msg.strip():
        # Set or update goal
        if user_row_index:
            sheet.update_cell(user_row_index, 9,
                              msg.strip())  # Update Goal column
        else:
            sheet.append_row([
                username or "", userid or "", now, "Set Goal", "0", "", "", "",
                msg.strip()
            ])
        return f"🎯 {username} , your goal has been set to: {msg.strip()} Use `!complete` to mark it as achieved. Use `!goal` to view your current goal."
    else:
        # Show existing goal
        for row in records[::-1]:
            if str(row['UserID']) == str(userid) and row['Goal']:
                return f"🎯 {username} , your current goal is: {row['Goal']} Use `!complete` to mark it as achieved."
        return f"⚠️ {username} , you haven't set any goal. Use `!goal Your Goal` to set one."


# ✅ !complete
@app.route("/complete")
def complete_goal():
    username = request.args.get('user')
    userid = request.args.get('id')

    records = sheet.get_all_records()

    for i in range(len(records) - 1, -1, -1):
        row = records[i]
        if str(row['UserID']) == str(userid) and row.get('Goal'):
            row_index = i + 2
            sheet.update_cell(row_index, 9, "")  # Clear the goal
            return f"🎉 {username} , you achieved your goal! Congratulations!"

    return f"⚠️ {username} , you don’t have any goal set. Use `!goal Your Goal` to set one."


# ✅ !summary
@app.route("/summary")
def summary():
    username = request.args.get('user')
    userid = request.args.get('id')

    records = sheet.get_all_records()

    total_minutes = 0
    total_xp = 0
    completed_tasks = 0
    pending_tasks = 0

    for row in records:
        if str(row['UserID']) == str(userid):
            # Total XP
            try:
                total_xp += int(row['XP'])
            except ValueError:
                pass

            # Study time
            if row['Action'] == "Study Session":
                duration_str = str(row.get('Duration',
                                           '0')).replace(" min", "")
                try:
                    total_minutes += int(duration_str)
                except ValueError:
                    pass

            # Tasks
            if str(row['Action']).startswith("Task:"):
                if "✅ Done" in str(row['Action']):
                    completed_tasks += 1
                else:
                    pending_tasks += 1

    hours = total_minutes // 60
    minutes = total_minutes % 60
    return (f"📊 {username} 's Summary:\n"
            f"⏱️ Total Study Time: {hours}h {minutes}m\n"
            f"⚜️ Total XP: {total_xp}\n"
            f"✅ Completed Tasks: {completed_tasks}\n"
            f"🕒 Pending Tasks: {pending_tasks}")


# ✅ !pending
@app.route("/pending")
def pending_task():
    username = request.args.get('user')
    userid = request.args.get('id')

    records = sheet.get_all_records()

    for row in reversed(records):
        if str(row['UserID']) == str(userid) and str(
                row['Action']).startswith("Task:") and "✅ Done" not in str(
                    row['Action']):
            task_name = str(row['Action'])[6:]  # Remove "Task: " prefix
            return f"🕒 {username} , your current pending task is: '{task_name}' — Keep going. Use `!done` to mark it as completed. Use `!remove` to remove it."

    return f"✅ {username} , you have no pending tasks! Use `!task Your Task` to add one."

@app.route("/ping")
def home():
    return "✅ Sunnie-BOT is alive!"

@app.route("/ping")
def ping():
    return "🟢 Ping OK"



# === Run Server ===
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
