from flask import Flask, jsonify, request
from enum import Enum

app = Flask(__name__)


@app.route('/', methods=['GET'])
def index():
    return jsonify({'Message': 'Welcome to API REST tutorial'})
