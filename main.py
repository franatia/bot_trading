from flask import Flask, jsonify
from decouple import config

app = Flask(__name__)
PORT = config('PORT')


@app.route('/', methods=['GET'])
def index():
    return jsonify({'Message': 'Welcome to API REST tutorial'})


if __name__ == '__main__':
    app.run(port=PORT, debug=False)
