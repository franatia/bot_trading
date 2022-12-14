from flask import Flask, jsonify

app = Flask(__name__)
PORT = 5000


@app.route('/', methods=['GET'])
def index():
    return jsonify({'Message': 'Welcome to API REST tutorial'})


if __name__ == '__main__':
    app.run(port=PORT, debug=False)
