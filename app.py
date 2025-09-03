# app.py
import streamlit as st
import sqlite3
import datetime

DB_FILE = "chat.db"
ADMIN_USER = "admin"      # 管理者ユーザー名
ADMIN_PASS = "admin123"   # 管理者パスワード（簡易版）

# --- データベース初期化 ---
def init_db():
    conn = sqlite3.connect("chat.db", check_same_thread=False)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            message TEXT,
            timestamp TEXT,
            thread_id INTEGER
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT
        )
    ''')
    # 管理者アカウントを登録
    c.execute("INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)", (ADMIN_USER, ADMIN_PASS))

    # デフォルトスレ（雑談）を 1 個つくっておく
    c.execute("INSERT OR IGNORE INTO threads (id, title, created_at) VALUES (1, ?, ?)", 
              ("雑談スレ", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    try:
        c.execute("ALTER TABLE messages ADD COLUMN thread_id INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass  # すでにカラムがある場合は無視

    conn.commit()
    conn.close()


# --- ユーザー認証 ---
def check_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    result = c.fetchone()
    conn.close()
    return result is not None

# --- メッセージ保存 ---
def save_message(username, message, thread_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO messages (username, message, timestamp, thread_id) VALUES (?, ?, ?, ?)",
              (username, message, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), thread_id))
    conn.commit()
    conn.close()

# --- メッセージ取得 ---
def load_messages(thread_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, username, message, timestamp FROM messages WHERE thread_id=? ORDER BY id ASC", (thread_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# --- メッセージ削除（管理者のみ） ---
def delete_message(msg_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE id=?", (msg_id,))
    conn.commit()
    conn.close()

#スレッドよみこみ
def load_threads():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, title, created_at FROM threads ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

#スレッド作成
def create_thread(title):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO threads (title, created_at) VALUES (?, ?)",
              (title, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()


# --- Streamlit UI ---
def main():
    st.title("匿名チャット(デモ版)")

    if "user" not in st.session_state:
        st.session_state.user = None
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = None  # どのスレを見ているか

    # --- ログイン処理（省略：今のままでOK） ---

    if st.session_state.user is None:
        st.subheader("ログイン")
        login_user = st.text_input("ユーザー名", key="login_user")
        login_pass = st.text_input("パスワード", type="password", key="login_pass")
        if st.button("ログイン"):
            if check_user(login_user, login_pass):
                st.session_state.user = login_user
                st.success(f"{login_user}でログインしました")
                st.rerun()
            else:
                st.error("ユーザー名またはパスワードが違います")

        st.subheader("新規登録")
        new_user = st.text_input("新しいユーザー名", key="reg_user")
        new_pass = st.text_input("新しいパスワード", type="password", key="reg_pass")
        if st.button("登録"):
            if new_user and new_pass:
                conn = sqlite3.connect(DB_FILE)
                c = conn.cursor()
                try:
                    c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (new_user, new_pass))
                    conn.commit()
                    st.success(f"{new_user}を登録しました")
                except sqlite3.IntegrityError:
                    st.error("そのユーザー名はすでに使われています")
                conn.close()
            else:
                st.error("ユーザー名とパスワードを入力してください")
        return  
# ログインしていないのでここで終

    # --- ログアウト ---
    if st.button("ログアウト"):
        st.session_state.user = None
        st.rerun()

    st.write(f"ログイン中: {st.session_state.user}")

    # --- スレ選択してないとき：スレ一覧 ---
    if st.session_state.thread_id is None:
        st.subheader("📝 スレ一覧")
        threads = load_threads()
        for tid, title, created in threads:
            if st.button(f"{title} ({created})", key=f"thread_{tid}"):
                st.session_state.thread_id = tid
                st.rerun()

        st.subheader("新しいスレを作成")
        new_thread = st.text_input("スレッド名を入力")
        if st.button("作成"):
            if new_thread:
                create_thread(new_thread)
                st.success("スレを作成しました")
                st.rerun()
        return

    # --- スレ表示 ---
    st.subheader(f"📌 スレッド: {st.session_state.thread_id}")
    if st.button("← スレ一覧へ戻る"):
        st.session_state.thread_id = None
        st.rerun()

   # 管理者だけ履歴全削除
    if st.session_state.user == ADMIN_USER:
        if st.button("💥 全履歴を削除（管理者用）"):
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("DELETE FROM messages")
            conn.commit()
            conn.close()
            st.success("チャット履歴をすべて削除しました")

    # メッセージ入力
    message = st.text_input("メッセージを入力")
    if st.button("送信"):
        if message:
            save_message(st.session_state.user, message, st.session_state.thread_id)
            st.rerun()

    # 履歴表示
    messages = load_messages(st.session_state.thread_id)
    for msg_id, user, msg, ts in messages:
        st.write(f"[{ts}] {user}: {msg}")
        if st.session_state.user == ADMIN_USER:
            if st.button(f"削除 {msg_id}"):
                delete_message(msg_id)
                st.rerun()

if __name__ == "__main__":
    init_db()  # ← DB初期化
    main()     # ← アプリ実行
