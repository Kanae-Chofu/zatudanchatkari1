# app.py
import streamlit as st
import sqlite3
import datetime

DB_FILE = "chat.db"
ADMIN_USER = "admin"      # 管理者ユーザー名
ADMIN_PASS = "admin123"   # 管理者パスワード（簡易版）

# --- データベース初期化 ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            message TEXT,
            timestamp TEXT
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
def save_message(username, message):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO messages (username, message, timestamp) VALUES (?, ?, ?)",
              (username, message, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

# --- メッセージ取得 ---
def load_messages():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, username, message, timestamp FROM messages ORDER BY id ASC")
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

# --- Streamlit UI ---
def main():
    st.title("匿名チャット（デモ版）💬")

    # セッションステート初期化
    if "user" not in st.session_state:
        st.session_state.user = None

    # --- ログイン / 新規登録画面 ---
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

        return  # ログインしていないのでここで終了

    # --- ログアウトボタン ---
    if st.button("ログアウト"):
        st.session_state.user = None
        st.rerun()

    st.write(f"ログイン中: {st.session_state.user}")

    # --- メッセージ入力 ---
    message = st.text_input("メッセージを入力")
    send = st.button("送信")

    if send and message:
        save_message(st.session_state.user, message)
        st.rerun()

    # --- チャット履歴表示 ---
    st.subheader("📜 チャット履歴")

    # 管理者だけ履歴全削除
    if st.session_state.user == ADMIN_USER:
        if st.button("💥 全履歴を削除（管理者用）"):
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("DELETE FROM messages")
            conn.commit()
            conn.close()
            st.success("チャット履歴をすべて削除しました")
            st.rerun()

    messages = load_messages()
    for msg_id, user, msg, ts in messages:
        st.write(f"[{ts}] {user}: {msg}")
        # 管理者のみ削除ボタン
        if st.session_state.user == ADMIN_USER:
            if st.button(f"削除 {msg_id}"):
                delete_message(msg_id)
                st.rerun()

if __name__ == "__main__":
    init_db()
    main()
