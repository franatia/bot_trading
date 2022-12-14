from flask import Flask, jsonify
from decouple import config
from waitress import serve

app = Flask(__name__)
PORT = config('PORT')


@app.route('/hi', methods=['GET'])
def index():
    return jsonify({'Message': 'Welcome to API REST tutorial'})


if __name__ == '__main__':
    serve(app, host='0.0.0.0', port=PORT, threads=2, url_prefix='/my-app')
