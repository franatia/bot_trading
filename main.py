import asyncio

from flask import Flask, jsonify, redirect, url_for, request
from decouple import config
from waitress import serve
import datetime
from binance import Client
from BotTrading import BotTrading
from MongoDB import MongoDB
from cryptography.fernet import Fernet
from controllers.users import validate_name, validate_email, validate_password, validate_keys, validate_profile_photo
from flask_cors import CORS, cross_origin
import os

app = Flask(__name__)
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'
PORT = os.environ['PORT']

date = datetime.datetime.now()
end_day = (date.timestamp() * 1000)
start_day = end_day - (86400000 * 30)

user_key = 'dIXuGb6b1CFjGb6nqn7Vyav7cKm0JwVSv3al62rBruM82Xmsjq4t4tMcNbFoYFsr'
secret_key = 'aNPDlOhEzk9WLKaLxnkFOTQT6BQ4p7ttXDzSlWK25drrMFY2pWHXszNLtQmwvHSq'

botTrading_btc = BotTrading('BTCUSDT', int(start_day), int(end_day), Client.KLINE_INTERVAL_5MINUTE, 1, 1000, 10, user_key,
                 secret_key, 99, 200)

MONGO_STRING = 'mongodb+srv://admin_1:aa74b6474add49868a695bcc3155e426@cluster0.umgwskd.mongodb.net/test?authSource=admin&replicaSet=atlas-qw1msu-shard-0&readPreference=primary&appname=MongoDB%20Compass&ssl=true'
mongo_db = MongoDB(MONGO_STRING)

FERNET_KEY = b'oHUYqtRfCEdDG7S5OSN-KWt32mj9WYtXtUadLGiKuPA='
_run_ws = False

def config_bot():
    global _run_ws
    _run_ws = True
    botTrading_btc.run_strategy()
    asyncio.run(botTrading_btc.config_BM())

def trade_test():
    botTrading_btc.ex_trade(16700, 16700, 16600, 'BUY', 'LONG', 0, botTrading_btc.klines[len(botTrading_btc.klines) - 1][6], 'ADX')

@cross_origin
@app.route('/', methods=['GET'])
def index():
    return jsonify({'Message': 'Welcome to API REST bot'})


@cross_origin
@app.route('/insert-user', methods=['POST'])
def insert_user():
    json = request.json

    bl = mongo_db.validate_contain_primary_user_keys(json, ['name', 'email', 'password', 'admin', 'admin_pass'])

    if not bl or not validate_email(json['email']) or not validate_name(json['name']) or not validate_password(
            json['password']):
        return jsonify({
            'status': 400,
            'msg': 'Check json keys'
        })

    item = mongo_db.validate_editor(json)

    if not item['ok']:
        return jsonify({
            'status': 400,
            'msg': 'Admin does not exists'
        })

    msg = mongo_db.insert_user(json)

    return jsonify(msg)


@cross_origin
@app.route('/log-in', methods=['POST'])
def log_in():
    json = request.json

    bl = mongo_db.validate_contain_primary_user_keys(json, ['name', 'email', 'password'])

    if not bl or not validate_email(json['email']) or not validate_name(json['name']) or not validate_password(
            json['password']):
        return jsonify({
            'status': 400,
            'msg': 'Check json keys'
        })

    msg = mongo_db.get_user(json)

    return jsonify(msg)


@cross_origin
@app.route('/insert-api-key', methods=['POST'])
def insert_api_key():
    json = request.json

    bl = mongo_db.validate_contain_primary_user_keys(json, ['_id', 'password', 'user_key', 'secret_key'])

    if not bl or not validate_password(json['password']) or not validate_keys(json['user_key'], json['secret_key']):
        return jsonify({
            'status': 400,
            'msg': 'Check json keys'
        })

    user_key = json.pop('user_key', None)
    secret_key = json.pop('secret_key', None)

    msg = mongo_db.insert_exchange_keys(json, user_key, secret_key)

    return jsonify(msg)


@cross_origin
@app.route('/insert-profile-photo', methods=['POST'])
def insert_profile_photo():
    json = request.json

    bl = mongo_db.validate_contain_primary_user_keys(json, ['_id', 'password', 'profile_photo'])

    if not bl or not validate_password(json['password']) or not validate_profile_photo(json['profile_photo']):
        return jsonify({
            'status': 400,
            'msg': 'Check json keys'
        })

    pp = json.pop('profile_photo', None)

    msg = mongo_db.insert_profile_photo(json, pp)

    return jsonify(msg)


@cross_origin
@app.route('/get-user', methods=['POST'])
def get_user():
    json = request.json

    bl = mongo_db.validate_contain_primary_user_keys(json, ['_id'])

    if not bl:
        return jsonify({
            'status': 400,
            'msg': 'Check json keys'
        })

    msg = mongo_db.get_user_by_id(json['_id'])

    return jsonify(msg)


@cross_origin
@app.route('/get-api-key', methods=['POST'])
def get_api_key():
    json = request.json

    bl = mongo_db.validate_contain_primary_user_keys(json, ['_id', 'password'])

    if not bl or not validate_password(json['password']):
        return jsonify({
            'status': 400,
            'msg': 'Check json keys'
        })

    msg = mongo_db.get_exchanges_key(json)

    return jsonify(msg)


@cross_origin
@app.route('/get-trades-history', methods=['POST'])
def get_trades_history():
    json = request.json
    bl = mongo_db.validate_contain_primary_user_keys(json, ['_id'])

    if not bl:
        return jsonify({
            'status': 400,
            'msg': 'Check json keys'
        })

    msg = mongo_db.get_trades_history(json)

    return jsonify(msg)


@cross_origin
@app.route('/set-cantitypairs', methods=['POST'])
def set_cantity_pairs():
    json = request.json
    bl = mongo_db.validate_contain_primary_user_keys(json, ['_id', 'password', 'cantity', 'pairs'])

    if not bl:
        return jsonify({
            'status': 400,
            'msg': 'Check json keys'
        })

    msg = mongo_db.set_cantityparis(json)

    return jsonify(msg)

@cross_origin
@app.route('/test-trade', methods=['POST'])
def run_test_trade():
    json = request.json
    bl = mongo_db.validate_contain_primary_user_keys(json, ['admin', 'admin_pass'])

    if not bl:
        return jsonify({
            'status': 400,
            'msg': 'Check json keys'
        })

    msg = mongo_db.validate_editor(json)

    if not msg['ok']:
        return jsonify({
            'status': 400,
            'msg': 'Check editor'
        })

    trade_test()

    return jsonify({'ok': True})

@cross_origin()
@app.route('/run_ws', methods=['GET'])
def run_ws():
    if _run_ws:
        return jsonify({'msg': 'Running'})
    config_bot()

if __name__ == '__main__':
    app.run()
