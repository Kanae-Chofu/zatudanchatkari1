# app.py
import streamlit as st
import sqlite3
import datetime
import os
import re
import bcrypt

DB_FILE = "chat.db"
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

# -------------------------------
# ユーティリティ
# -------------------------------
def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def is_bcrypt_hash(value: str) -> bool:
    return isinstance(value, str) and value.startswith("$2")

def sanitize_message(text: str, max_len: int) -> str:
    # 改行/リンク/画像引用は初期は不要 → 改行はスペースに置換、URLはそのまま文字列として保存
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len]
    return text

# -------------------------------
# DB 接続ヘルパ
# -------------------------------
def get_conn():
    # 同時アクセス耐性を上げるため WAL を使う
    new_db = not os.path.exists(DB_FILE)
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    if new_db:
        conn.commit()
    return conn

# -------------------------------
# スキーマ初期化 / マイグレーション
# -------------------------------
def init_db():
    conn = get_conn()
    c = conn.cursor()

    # tables
    c.execute("""
        CREATE TABLE IF NOT EXISTS threads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            message TEXT,
            timestamp TEXT,
            thread_id INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT
        )
    """)

    # デフォルトスレ
    c.execute(
        "INSERT OR IGNORE INTO threads (id, title, created_at) VALUES (1, ?, ?)",
        ("雑談スレ", now_str())
    )

    # admin 登録（ハッシュで保持）
    c.execute("SELECT password FROM users WHERE username=?", (ADMIN_USER,))
    row = c.fetchone()
    if row is None:
        c.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (ADMIN_USER, hash_password(ADMIN_PASS))
        )
    else:
        # 既存が平文ならハッシュへ置き換え
        stored = row[0]
        if not is_bcrypt_hash(stored):
            if stored == ADMIN_PASS:
                c.execute(
                    "UPDATE users SET password=? WHERE username=?",
                    (hash_password(ADMIN_PASS), ADMIN_USER)
                )

    conn.commit()
    conn.close()

# -------------------------------
# ユーザー認証
# -------------------------------
def check_user(username: str, password: str) -> bool:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username=?", (username,))
    row = c.fetchone()
    if not row:
        conn.close()
        return False

    stored = row[0]
    ok = False
    if is_bcrypt_hash(stored):
        try:
            ok = bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))
        except Exception:
            ok = False
    else:
        # 平文時代の互換：一致したらハッシュに置換して以後はハッシュ運用
        ok = (stored == password)
        if ok:
            c.execute(
                "UPDATE users SET password=? WHERE username=?",
                (hash_password(password), username)
            )
            conn.commit()
    conn.close()
    return ok

def register_user(username: str, password: str) -> bool:
    if not username or not password:
        return False
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hash_password(password))
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        conn.close()
        return False

# -------------------------------
# メッセージ
# -------------------------------
def save_message(username: str, message: str, thread_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO messages (username, message, timestamp, thread_id) VALUES (?, ?, ?, ?)",
        (username, message, now_str(), thread_id)
    )
    conn.commit()
    conn.close()

def load_messages(thread_id: int):
    conn = get_conn()
    c = conn.cursor()
    # Twitter型（新しい順）：id DESC
    c.execute(
        "SELECT id, username, message, timestamp FROM messages WHERE thread_id=? ORDER BY id DESC",
        (thread_id,)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def delete_message(msg_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE id=?", (msg_id,))
    conn.commit()
    conn.close()

def delete_all_messages():
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM messages")
    conn.commit()
    conn.close()

# -------------------------------
# スレッド
# -------------------------------
def load_threads(keyword: str = ""):
    conn = get_conn()
    c = conn.cursor()
    if keyword:
        like = f"%{keyword}%"
        c.execute(
            "SELECT id, title, created_at FROM threads WHERE title LIKE ? ORDER BY id DESC",
            (like,)
        )
    else:
        c.execute("SELECT id, title, created_at FROM threads ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    return rows

def create_thread(title: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO threads (title, created_at) VALUES (?, ?)",
        (title, now_str())
    )
    conn.commit()
    conn.close()

# -------------------------------
# UI
# -------------------------------
def rules_box():
    with st.expander("掲示板ルール", expanded=True):
        st.markdown(
            """
- 誹謗中傷・個人情報の投稿は禁止
- スレッド名は **64文字まで**／メッセージは **150文字まで**
- 画像・リンク貼付・改行はサポート外（テキストのみ）
- 管理者が不適切な投稿を削除する場合があります
            """
        )

def main():
    st.set_page_config(page_title="匿名チャット（デモ）", page_icon="💬", layout="centered")
    st.title("匿名チャット（デモ版）")
    rules_box()

    # セッション初期化
    if "user" not in st.session_state:
        st.session_state.user = None
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = None

    # ---------------- ログイン/登録 ----------------
    if st.session_state.user is None:
        st.subheader("ログイン")
        login_user = st.text_input("ユーザー名", key="login_user")
        login_pass = st.text_input("パスワード", type="password", key="login_pass")
        if st.button("ログイン"):
            if check_user(login_user, login_pass):
                st.session_state.user = login_user
                st.success(f"{login_user} でログインしました")
                st.rerun()
            else:
                st.error("ユーザー名またはパスワードが違います")

        st.subheader("新規登録")
        new_user = st.text_input("新しいユーザー名", key="reg_user")
        new_pass = st.text_input("新しいパスワード", type="password", key="reg_pass")
        if st.button("登録"):
            if register_user(new_user, new_pass):
                st.success(f"{new_user} を登録しました。ログインしてください。")
            else:
                st.error("登録に失敗しました（既に存在 or 未入力）")
        return

    # ---------------- ログアウト ----------------
    cols = st.columns([1,1,4])
    with cols[0]:
        if st.button("ログアウト"):
            st.session_state.user = None
            st.session_state.thread_id = None
            st.rerun()
    with cols[1]:
        st.write(f"**ログイン中:** {st.session_state.user}")

    # ---------------- スレ一覧（未選択時） ----------------
    if st.session_state.thread_id is None:
        st.subheader("スレ一覧")

        # 検索
        keyword = st.text_input("スレッド検索（部分一致）", key="thread_search")
        threads = load_threads(keyword.strip())

        # 新規作成（64文字制限）
        st.markdown("#### 新しいスレを作成")
        new_thread = st.text_input("スレッド名（64文字まで）", key="thread_title_input", max_chars=64)
        create_col1, create_col2 = st.columns([3,1])
        with create_col2:
            if st.button("作成"):
                title = sanitize_message(new_thread, 64)
                if not title:
                    st.warning("スレッド名を入力してください。")
                else:
                    create_thread(title)
                    st.success("スレを作成しました")
                    st.rerun()

        st.markdown("---")
        if not threads:
            st.info("スレッドがありません。新しく作成してください。")
        else:
            for tid, title, created in threads:
                if st.button(f"{title}（{created}）", key=f"thread_{tid}"):
                    st.session_state.thread_id = tid
                    st.rerun()
        return

    # ---------------- スレ表示（選択後） ----------------
    st.subheader(f"スレッドID: {st.session_state.thread_id}")
    if st.button("← スレ一覧へ戻る"):
        st.session_state.thread_id = None
        st.rerun()

    # 管理者だけ全削除
    if st.session_state.user == ADMIN_USER:
        if st.button("このアプリの全メッセージを削除（管理者）"):
            delete_all_messages()
            st.success("チャット履歴をすべて削除しました")
            st.experimental_rerun()

    # 送信ハンドラ（Enter とボタンの両方から呼ぶ）
    def handle_send():
        raw = st.session_state.input_message
        msg = sanitize_message(raw, 150)
        if not msg:
            st.warning("メッセージを入力してください（150文字まで）。")
            return
        save_message(st.session_state.user, msg, st.session_state.thread_id)
        st.session_state.input_message = ""  # 入力欄クリア

    # 入力（Enterで送信可 / ボタンでも送信可）
    st.text_input(
        "メッセージ（150文字まで）",
        key="input_message",
        max_chars=150,
        on_change=handle_send
    )
    if st.button("送信"):
        handle_send()

    # 履歴表示（新しい順）
    st.markdown("---")
    messages = load_messages(st.session_state.thread_id)
    if not messages:
        st.info("まだ投稿がありません。最初のメッセージをどうぞ！")
    else:
        for msg_id, user, msg, ts in messages:
            st.write(f"[{ts}] **{user}**: {msg}")
            if st.session_state.user == ADMIN_USER:
                if st.button(f"削除 {msg_id}", key=f"del_{msg_id}"):
                    delete_message(msg_id)
                    st.experimental_rerun()

# -------------------------------
if __name__ == "__main__":
    init_db()
    main()
