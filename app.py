import os


import datetime
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
import sqlite3


from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem on server side (instead of signed cookies on client side)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Login_required decorator redirect to "/login" if the user is not logged on.
@app.route("/")
@login_required
def index():
    with sqlite3.connect("finance.db") as conn:
        cur = conn.cursor()
        cur.execute("SELECT symbol, stocks FROM portfolio WHERE user_id = ?", [str(session["user_id"])])
        stocks = cur.fetchall()
        cur.execute("SELECT cash FROM users WHERE id = ?", [str(session["user_id"])])
        cash = cur.fetchall()
    portfolio = []
    total_stock_option = cash[0][0]
    for row in stocks:
        portfolio.append({"symbol": row[0], "unit_price": lookup(row[0])["price"], "shares": row[1], "total": (row[1] * lookup(row[0])["price"])})
        total_stock_option += row[1] * lookup(row[0])["price"]
    return render_template("index.html", portfolio=portfolio, cash=cash[0][0],  total=total_stock_option)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        # fetch form information
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        # Managing user's inputs
        if not symbol or not shares:
            flash("Please enter a symbol and the numbers of share you want to buy.")
            return redirect("/buy")
        try:
            shares = int(shares)
        except ValueError:
            flash("Please enter a valid ammount.")
            return redirect("/buy")
        if shares < 1:
            flash("Please enter a valid ammount.")
            return redirect("/buy")

        # request API for share' price
        share_info = lookup(symbol)
        if not share_info:
            flash("The symbol you've entered cannot be found")
            return redirect("/buy")
        price = share_info["price"]

        # request db for user'cash
        with sqlite3.connect("finance.db") as conn:
            cur = conn.cursor()
            cur.execute("SELECT cash FROM users WHERE id=?", [session["user_id"]])
            row = cur.fetchall()
        cash = row[0][0]
        total = float(price) * float(shares)

        # Check if user has enough money
        if float(cash) < total:
            flash("You do not have enough fund to complete the transaction")
            return redirect("/buy")

        # Proceed the transaction, update portfolio, draw money from account and redirect to index page
        with sqlite3.connect("finance.db") as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO transactions (date, user_id, type, symbol, unit_price, shares, total) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session["user_id"], "buy", symbol, price, shares, total)) 
            
            # update portfolio table
            cur.execute("SELECT * FROM portfolio WHERE user_id = ? AND symbol = ?", (session["user_id"], symbol))
            portfolio_symbol = cur.fetchall()
            if portfolio_symbol == []:
                cur.execute("INSERT INTO portfolio (user_id, symbol, stocks) VALUES (?, ?, ?)", (session["user_id"], symbol, shares))
            else:
                cur.execute("UPDATE portfolio SET stocks = stocks + ? WHERE user_id = ? and symbol = ?", (shares, session["user_id"], symbol))
                
            # update cash users table
            cur.execute("UPDATE users SET cash = cash - ? WHERE id = ?", (total, session["user_id"]))
        flash("Transaction successful")
        return redirect("/")

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    with sqlite3.connect("finance.db") as conn:
        cur = conn.cursor()
        cur.execute("SELECT *  FROM transactions WHERE user_id = ? ORDER  BY date DESC", [str(session["user_id"])])
        history = cur.fetchall()
        cur.execute("SELECT cash FROM users WHERE id = ?", [session["user_id"]])
        cash = cur.fetchall()
    return render_template("/history.html", history=history, cash=cash[0][0])


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # # Forget any user_id optional?? conflict with flash message when registering
    # session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        with sqlite3.connect("finance.db") as conn:
            cur = conn.cursor()
            username = request.form.get("username")
            cur.execute("SELECT * FROM users WHERE username = ?", ([username]))
            rows = cur.fetchall()

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0][2], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0][0]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if "symbol" not in session:
        session["symbol"] = []

    if request.method == "POST" and request.form.get("reset"):
        session["symbol"] = []
        flash("No corresponding symbol found")
        return redirect("/quote")
    elif request.method == "POST":
        if not request.form.get("symbol"):
            flash("Please enter a symbol to quote")
        else:
            symbol = request.form.get("symbol")
            if lookup(symbol) == None:
                    flash("No corresponding symbol found")
                    return redirect("/quote")
            session["symbol"].append(lookup(symbol))
            return redirect("/quote")

    return render_template("/quote.html", symbols=session["symbol"])


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # check problems
        if not request.form.get("username"):
            flash("Username missing")
            # return apology("Username missing")
        elif not request.form.get("password") or not request.form.get("confirmation"):
            # return apology("Password missing")
            flash("Missing password or confirmation")
        elif request.form.get("password") != request.form.get("confirmation"):
            # return apology("Confirmation not identical")
            flash("Confirmation and password not identical!")
            
        # update database
        else:
            try:
                with sqlite3.connect("finance.db") as conn:
                    cur = conn.cursor()
                    cur.execute("INSERT INTO users (username, hash) VALUES (?, ?)", (request.form.get("username"), generate_password_hash(request.form.get("password"))))
                flash("Successfully registered")
                return redirect("/")
            # If duplicate in the database: IntegrityError because username tagged as UNIQUE INDEX.
            except sqlite3.IntegrityError:
                # return apology("Username already taken!")
                flash("Username already taken!")

    return render_template("/register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        # fetch form information
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        # Managing user's inputs
        if not symbol or not shares:
            flash("Please enter a symbol and the numbers of share you want to buy.")
            return redirect("/sell")
        try:
            shares = int(shares)
        except ValueError:
            flash("Please enter a valid ammount.")
            return redirect("/sell")
        if shares < 1:
            flash("Please enter a valid ammount.")
            return redirect("/sell")

        # fetching user datas
        with sqlite3.connect("finance.db") as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM portfolio WHERE user_id = ? and symbol = ?", (session["user_id"], symbol))
            symbol_owned = cur.fetchall()

        # checking selling possibilities
        if len(symbol_owned) == 0:
            flash("You do not own this stock option")
            return redirect("/sell")
        elif symbol_owned[0][2] < shares:
            flash("You do not own enough share!")
            return redirect("/sell")

        # Proceeding transaction
        price = lookup(symbol)["price"]
        total = price * shares
        
        with sqlite3.connect("finance.db") as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO transactions (date, user_id, type, symbol, unit_price, shares, total) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), session["user_id"], "sell", symbol, price, shares, total))
            cur.execute("UPDATE portfolio SET stocks = stocks - ? WHERE user_id = ? and symbol = ?", (shares, session["user_id"], symbol))
            cur.execute("DELETE FROM portfolio WHERE stocks = 0")
            cur.execute("UPDATE users SET cash = cash + ? WHERE id = ?", (total, session["user_id"]))

        flash("Transaction successful")
        return redirect("/")

    return render_template("/sell.html")
