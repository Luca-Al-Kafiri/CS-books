import os
import requests

from flask import Flask, session, render_template, redirect, request, jsonify, url_for
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

# Welcome page
@app.route("/")
def index():
    return render_template("welcome.html")

# Registration
@app.route("/register", methods=["GET", "POST"])
def register():
    """ Registration """
    if request.method == "POST":
        # Make sure name is provided
        if not request.form.get("username"):
            return render_template("apology.html",message="Must provide a name")
        # Make sure password is provided
        elif not request.form.get("password"):
            return render_template("apology.html",message="Must provide a password")
        # Make sure passwords are matching
        elif request.form.get("password") != request.form.get("confirm"):
            return render_template("apology.html",message="password does not match")
        # Get the username from the form
        username = request.form.get("username")
        # Check if the user already exist
        row = db.execute("SELECT * FROM users WHERE username = :username", {"username": username}).fetchone()
        if row != None:
            return render_template("apology.html",message="username already exists")
        # Password hash
        password = generate_password_hash(request.form.get("password"), method='pbkdf2:sha256', salt_length=8)
        # Add the user to database
        db.execute("INSERT INTO users (username, pass) VALUES (:username, :pass)", {"username": username, "pass": password}) 
        db.commit() 
        return redirect("/login")
    else:
        # User reached the page vis GET 
        return render_template("register.html")

# Login page
@app.route("/login", methods=["GET", "POST"])
def login():
    # Logout all users
    session.clear()
    if request.method == "POST":
        # Make sure name is provided
        if not request.form.get("username"):
            return render_template("apology.html",message="Please enter your name")
        # Make sure password is provided
        elif not request.form.get("password"):
            return render_template("apology.html",message="Please enter your password")
        # Get the user name from the form
        username = request.form.get("username")
        # Check if name and password are valid
        row = db.execute("SELECT * FROM users WHERE username = :username", {"username": username}).fetchall()
        if len(row) != 1 or not check_password_hash(row[0]["pass"], request.form.get("password")):
            return render_template("apology.html",message="invalid username or/and password")
        # Remember the user
        user = db.execute("SELECT * FROM users WHERE username = :username", {"username": username}).fetchone()
        session["user_id"] = user[0]
        return redirect("/search")
    else:
        # User reached via GET 
        return render_template("login.html")

# Logout
@app.route("/logout")
def logout():
    # Logout all users
    session.clear()
    return redirect("/login")

# Search page
@app.route("/search", methods=["GET", "POST"])
def search():
    """ Search and show results """
    if request.method == "POST":
        info = '%' + request.form.get("info") + '%'
        # Search for any possible matches in database
        books = db.execute("SELECT * FROM books WHERE isbn LIKE :info OR title LIKE :info OR author LIKE :info",{"info": info}).fetchall()
        # No matches
        if len(books) == 0:
            return render_template("apology.html", message="Sorry no matches")
        return render_template("search.html", books=books)
    else:
        # User reached via GET
        # Show first 10 books in database
        books = db.execute("SELECT * FROM books ORDER BY title DESC LIMIT 10").fetchall()
        return render_template("search.html", books=books)

        
@app.route("/book/<isbn>", methods=["GET", "POST"])
def book(isbn):
    """ Book details """
    # Query database using on isbn number
    book = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
    book_id = book[0]
    if request.method == "POST":
        # Get user review
        review = request.form.get("review")
        if request.form.get("rate") == None:
            return render_template("apology.html",message="Please select your rating")
        # Get user rate
        rate = int(request.form.get("rate"))
        # Make sure user did not write review before
        check = db.execute("SELECT * FROM reviews WHERE user_id = :user AND book_id = :book_id", {"user": session["user_id"], "book_id": book_id}).fetchall()
        if len(check) != 0:
            return render_template("apology.html",message="Sorry you can't post more than one review")
        # Add review to database
        db.execute("INSERT INTO reviews (review, book_id, user_id, rates) VALUES (:review, :book, :user, :rate)", {"review": review, "book": book_id, "user": session["user_id"], "rate": rate})
        db.commit()
        return redirect(url_for('book', isbn=isbn))
    else:
        # Query for all reviews for this book 
        reviews = db.execute("SELECT * FROM reviews WHERE book_id = :book_id", {"book_id": book_id}).fetchall()
        # Using Good reads API to get related info 
        res = requests.get("https://www.goodreads.com/book/review_counts.json", params={"key": "MYhzxMNiPKiK14VIFTMkbg", "isbns": isbn})
        data = res.json()
        # Average rating in Goodreads
        average = data['books'][0]['average_rating']
        # Total ratings in Goodreads
        rating = data['books'][0]['work_ratings_count']
        return render_template("book.html", book=book, average=average, rating=rating, isbn=isbn, reviews=reviews)

# Website API
@app.route("/api/<isbn>")
def book_api(isbn):
    """ API """
    # Query database using isbn
    book = db.execute("SELECT * FROM books WHERE isbn = :isbn", {"isbn": isbn}).fetchone()
    book_id = book[0]
    # Query database using book_id
    reviews = db.execute("SELECT COUNT(review), AVG(rates) FROM reviews WHERE book_id = :book_id", {"book_id": book_id}).fetchall()
    # Make sure isbn is valid
    if book is None:
        return jsonify({"error": "Invalid ISBN number"}), 404
    title = book[2]
    author = book[3]
    year = book[4]
    isbn = book[1]
    average_score = round(reviews[0][1], 1)
    if average_score is None:
        average_score = 0
    review_count = reviews[0][0]
    if review_count is None:
        review_count = 0
    # JSON response
    return jsonify({
        "title": title,
        "author": author,
        "year": year,
        "isbn": isbn,
        "average_score": float(average_score),
        "review_count": review_count
    })
