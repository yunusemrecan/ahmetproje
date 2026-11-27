"""{{name}}: {{t:web_doc}}"""

from flask import Flask, redirect, render_template, request, url_for

app = Flask(__name__)

# {{t:web_memory_comment}}
notes: list[str] = []


@app.get("/")
def index():
    return render_template("index.html", notes=notes, title="{{name}}")


@app.post("/add")
def add():
    text = request.form.get("note", "").strip()
    if text:
        notes.append(text)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)
