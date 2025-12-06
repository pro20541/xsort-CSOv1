from flask import Flask, request, redirect, url_for, render_template, flash, session
import mysql.connector
from mysql.connector import Error

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# MySQL connection
def get_db_connection():
    try:
        connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password='',
            database='xsort_db'
        )
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

# ----------------------
# Home Page
# ----------------------
@app.route('/')
def index():
    return render_template('index.html')

# ----------------------
# CSO Login / Logout
# ----------------------
@app.route('/cso/problems', endpoint='cso_problems')
def cso_problems():
    logged_in = session.get('cso_logged_in', False)
    username = session.get('username')
    points = session.get('points', 0)
    solved_problems = session.get('solved_problems', [])
    # Get problems from DB
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM problems")
    problems = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template(
        'cso.html',
        logged_in=logged_in,
        username=username,
        points=points,
        solved_problems=solved_problems,
        problems=problems
    )

@app.route('/cso/login', methods=['GET', 'POST'])
def cso_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        conn = get_db_connection()
        if not conn:
            flash("Database connection failed.", "error")
            return redirect(url_for('cso_login'))

        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM accounts WHERE username=%s AND password=%s", (username, password))
            account = cursor.fetchone()
            if account:
                session['cso_logged_in'] = True
                session['username'] = account['username']
                session['points'] = account['points']

                # Fetch solved problems
                cursor.execute("SELECT problem_id FROM user_solved_problems WHERE username=%s", (username,))
                solved = cursor.fetchall()
                session['solved_problems'] = [s['problem_id'] for s in solved]
                flash(f"Welcome, {username}!", "success")
                return redirect(url_for('cso'))
            else:
                flash("Invalid username or password.", "error")
        finally:
            cursor.close()
            conn.close()
    return render_template('cso_login.html')

@app.route('/cso/logout', methods=['POST'])
def cso_logout():
    session.pop('cso_logged_in', None)
    session.pop('username', None)
    session.pop('points', None)
    session.pop('solved_problems', None)
    flash("Logged out successfully.", "success")
    return redirect(url_for('cso'))

# ----------------------
# CSO Main / Problems / Leaderboard
# ----------------------
@app.route('/cso')
def cso():
    return redirect(url_for('cso_problems'))
# --- Add Problem (Admin) ---
@app.route("/admin/add_problem", methods=["POST"])
def add_problem():
    if not True:  # Replace with admin auth check
        flash("You must be an admin to perform this action.", "error")
        return redirect(url_for("admin_dashboard"))

    title = request.form.get("title")
    description = request.form.get("description")
    points = request.form.get("points", type=int)
    difficulty = request.form.get("difficulty")
    flag = request.form.get("flag")

    if not title or not description or points is None or not difficulty or not flag:
        flash("All fields are required!", "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO problems (title, description, points, difficulty, flag)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (title, description, points, difficulty, flag))
        conn.commit()
        flash("Problem added successfully!", "success")
    except Exception as e:
        flash(f"Error adding problem: {e}", "error")
    finally:
        conn.close()

    return redirect(url_for("admin_dashboard"))
import time
from flask import jsonify

# Keep a simple cooldown dict per user (in-memory)
user_cooldowns = {}

@app.route('/cso/solve/<int:problem_id>', methods=['POST'])
def solve_problem(problem_id):
    if not session.get('cso_logged_in'):
        return jsonify({"status": "error", "message": "Unauthorized"}), 401

    username = session.get('username')
    now = time.time()

    # Check cooldown
    last_time = user_cooldowns.get(username, 0)
    if now - last_time < 2:  # 2 seconds cooldown
        return jsonify({"status": "error", "message": "Please wait before submitting again."})

    flag = request.form.get('flag', '').strip()
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Get correct flag for the problem
        cursor.execute("SELECT flag, points FROM problems WHERE id=%s", (problem_id,))
        problem = cursor.fetchone()
        if not problem:
            return jsonify({"status": "error", "message": "Problem not found."})

        # Check if already solved
        cursor.execute("SELECT * FROM user_solved_problems WHERE username=%s AND problem_id=%s",
                       (username, problem_id))
        if cursor.fetchone():
            return jsonify({"status": "info", "message": "Problem already solved."})

        if flag == problem['flag']:
            # Add to solved
            cursor.execute("INSERT INTO user_solved_problems (username, problem_id) VALUES (%s,%s)",
                           (username, problem_id))

            # Update points
            new_points = session.get('points', 0) + problem['points']
            cursor.execute("UPDATE accounts SET points=%s WHERE username=%s", (new_points, username))
            conn.commit()

            # Update session
            session['points'] = new_points
            session['solved_problems'].append(problem_id)

            user_cooldowns[username] = now
            return jsonify({"status": "success", "message": f"Correct! You earned {problem['points']} points.", "points": new_points})
        else:
            user_cooldowns[username] = now
            return jsonify({"status": "error", "message": "Incorrect flag."})
    finally:
        cursor.close()
        conn.close()


@app.route('/cso/leaderboard')
def cso_leaderboard():
    conn = get_db_connection()
    leaderboard = []
    if conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT username, points FROM accounts ORDER BY points DESC")
        leaderboard = cursor.fetchall()
        cursor.close()
        conn.close()
    return render_template('cso_leaderboard.html', leaderboard=leaderboard)

# ----------------------
# Admin
# ----------------------
ADMIN_USER = "admin"
ADMIN_PASS = "root"


@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    # Assume you handle login state here
    logged_in = True  # Replace with real check
    flash_message = None


    conn = get_db_connection()
    with conn.cursor(dictionary=True) as cursor:
        cursor.execute("SELECT * FROM mailing_list ORDER BY created_at DESC")
        mailing_list = cursor.fetchall()

        cursor.execute("SELECT * FROM accounts ORDER BY id")
        users = cursor.fetchall()

        cursor.execute("SELECT * FROM problems ORDER BY id")
        problems = cursor.fetchall()
    conn.close()

    return render_template(
        "admin.html",
        logged_in=logged_in,
        mailing_list=mailing_list,
        users=users,
        problems=problems,
        flash_message=flash_message
    )


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login_page():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USER and password == ADMIN_PASS:
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin.html', logged_in=False, flash_message="Invalid credentials!")
    return render_template('admin.html', logged_in=False)

@app.route('/admin/add_user', methods=['POST'])
def add_user():
    if not session.get('logged_in'):
        return "Unauthorized", 401
    username = request.form.get('username')
    password = request.form.get('password')
    points = request.form.get('points', 0)
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO accounts (username, password, points) VALUES (%s,%s,%s)",
                       (username, password, points))
        conn.commit()
        flash("User added successfully!", "success")
    except mysql.connector.IntegrityError:
        flash("This username already exists!", "error")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for('admin_dashboard'))



if __name__ == '__main__':
    app.run(debug=True)
