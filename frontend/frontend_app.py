"""Frontend app: serves the MasterBlog UI (index.html and static assets)."""
from flask import Flask, render_template

app = Flask(__name__)


@app.route('/', methods=['GET'])
def home():
    """Serve the main blog UI page."""
    return render_template("index.html")


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5001, debug=True)
