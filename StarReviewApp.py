from flask import Flask, request, render_template_string, redirect, url_for
from transformers import pipeline
import sqlite3

app = Flask(__name__)

# ---------- MODEL ----------
classifier = pipeline(
    "sentiment-analysis",
    model="nlptown/bert-base-multilingual-uncased-sentiment"
)

# ---------- DATABASE ----------
def get_db_connection():
    conn = sqlite3.connect('stars_reviews.db')
    conn.row_factory = sqlite3.Row
    return conn

# ---------- DATABASE INIT ----------
with get_db_connection() as conn:
    conn.execute('''
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT,
        review TEXT,
        emoji TEXT
    )
    ''')
    conn.commit()

# ---------- HTML UI ----------
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title> Rating System</title>

    <style>
        body {
            font-family: 'Segoe UI', Arial;
            background: #f0f2f5;
            margin: 0;
            padding: 0;
        }

        .container {
            max-width: 700px;
            margin: 40px auto;
            background: white;
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
        }

        h2 {
            text-align: center;
            margin-bottom: 25px;
            color: #333;
        }

        input, textarea {
            width: 100%;
            padding: 12px;
            margin-top: 8px;
            margin-bottom: 18px;
            border-radius: 6px;
            border: 1px solid #ddd;
            font-size: 14px;
            box-sizing: border-box;
        }

        button {
            width: 100%;
            padding: 12px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border: none;
            border-radius: 6px;
            font-size: 16px;
            cursor: pointer;
        }

        .reviews {
            margin-top: 30px;
        }

        .review-card {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 15px;
        }

        .email {
            font-weight: bold;
        }

        .emoji {
            font-size: 32px;
        }
    </style>
</head>

<body>

    <div class="container">

        <h2>AI Rating System</h2>

        <form method="POST">
            <label>Email Address</label>
            <input type="email" name="email" required>

            <label>Your Review</label>
            <textarea name="review" rows="4" required></textarea>

            <button type="submit">Analyze & Save</button>
        </form>

        <div class="reviews">
            <h3>Review History</h3>

            {% for r in reviews %}
                <div class="review-card">
                    <div class="email">{{ r.email }}</div>
                    <div>{{ r.review }}</div>
                    <div class="emoji">{{ r.emoji }}</div>
                </div>
            {% endfor %}
        </div>

    </div>

</body>
</html>
"""

# ---------- ROUTE ----------
@app.route('/', methods=['GET', 'POST'])
def index():

    if request.method == 'POST':
        email = request.form['email']
        review = request.form['review']

        print("\n================ NEW REVIEW =================")
        print("User Email:", email)
        print("User Review:", review)

        result = classifier(review)[0]

        print("Raw Model Output:", result)

        stars_count = int(result['label'][0])
        confidence = round(result['score'] * 100, 2)

        print("Predicted Stars:", stars_count)
        print("Confidence Score:", confidence, "%")

        # ---------- STAR → EMOJI ----------
        if stars_count == 5:
            emoji = "😍"
        elif stars_count == 4:
            emoji = "😄"
        elif stars_count == 3:
            emoji = "😶"
        elif stars_count == 2:
            emoji = "😕"
        else:
            emoji = "😡"

        print("Emoji from Stars:", emoji)

        # ---------- CONFIDENCE LOGIC ----------
        if confidence < 50:
            print("Low Confidence Detected , Showing Uncertainty")
            emoji = "❓"

        print("Final Emoji Displayed:", emoji)
        

        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO reviews (email, review, emoji) VALUES (?, ?, ?)",
                (email, review, emoji)
            )
            conn.commit()

        return redirect(url_for('index'))

    with get_db_connection() as conn:
        reviews = conn.execute("SELECT * FROM reviews ORDER BY id DESC").fetchall()

    return render_template_string(HTML_PAGE, reviews=reviews)


# ---------- RUN ----------
if __name__ == '__main__':
    app.run(debug=True)