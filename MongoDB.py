import pymongo as mongo
from binance import Client
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
from bson.objectid import ObjectId

SECURITY = 'pbkdf2:sha256'
FERNET_KEY = b'skxg1EVD3zKEnZGXh0okSujFfA7Hj_dVAYcUxtS-SwU='

class MongoDB:
    def __init__(self, connection_string: str):
        self.cluster = mongo.MongoClient(connection_string)
        self.db = self.cluster['bot_trading']
        self.users = self.db['users']
        self.editors = self.db['editors']
        self.trades_history = self.db['trades_history']

        self.crypter = Fernet(FERNET_KEY)

    def create_trades_history(self, uid):

        data = {
            'user': uid,
            'trades': []
        }

        u_ = self.trades_history.insert_one(data)

        return u_.inserted_id

    def validate_user(self, item: dict):
        keys_expect = ['name', 'profile_photo', 'email', 'password', 'user_key', 'secret_key', 'cantity', 'pairs', 'trades_history', 'active']

        keys = item.keys()

        bl = True

        if keys_expect[0] in keys and isinstance(item[keys_expect[0]], str) \
                and keys_expect[2] in keys and isinstance(item[keys_expect[2]], str) \
                and keys_expect[3] in keys and isinstance(item[keys_expect[3]], str):
            bl = True

        for i in keys:
            if not (i in keys_expect):
                bl = False
                break

        for i in keys_expect:
            if not (i in keys):
                if i == 'cantity':
                    item[i] = 0
                    continue
                elif i == 'trades_history':
                    item[i] = None
                    continue

                elif i == 'active':
                    item[i] = True

                item[i] = ''

        return bl, item

    def validate_user_keys(self, item: dict):

        keys_expect = ['name', 'profile_photo', 'email', 'password', 'user_key', 'secret_key']

        keys = item.keys()

        bl = False

        for i in keys:
            if not (i in keys_expect):
                bl = False
                break
            else:
                bl = True

        return bl

    def validate_exchange_keys(self, user_key: str, secret_key: str):
        try:
            cl = Client(user_key, secret_key)
            res = cl.futures_account_balance()
            return True
        except:
            return False

    def validate_user_exists(self, item: dict):
        item.pop('password', None)
        item.pop('profile_photo', None)
        item.pop('user_key', None)
        item.pop('secret_key', None)
        u_ = self.users.find_one(item)

        if u_ is None:
            return False
        return True

    def validate_user_exists_by_id(self, uid):

        u_ = self.users.find_one({'_id': ObjectId(uid)})

        if u_ is None:
            return False
        return True

    def password_hash(self, item: dict):
        encrypted_text = generate_password_hash(item['password'], SECURITY)
        item['password'] = encrypted_text
        return item

    def check_exists_any_data(self, item: dict):

        keys = item.keys()

        bl = False

        for i in keys:
            if i == 'password' or i == 'profile_photo' or i == 'user_key' or i == 'secret_key':
                continue

            data = {
                i: item[i]
            }
            u_ = self.users.find_one(data)
            if u_ is not None:
                bl = True
                break

        return bl

    def encrypt_api_keys(self, user_key, secret_key):

        uk = self.crypter.encrypt(bytes(user_key, 'utf8'))
        sk = self.crypter.encrypt(bytes(secret_key, 'utf8'))

        return str(uk, 'utf8'), str(sk, 'utf8')

    def decrypt_api_keys(self, user_key, secret_key):

        uk = self.crypter.decrypt(bytes(user_key, 'utf8'))
        sk = self.crypter.decrypt(bytes(secret_key, 'utf8'))

        return str(uk, 'utf8'), str(sk, 'utf8')

    def insert_user(self, item: dict):

        bl, item_ = self.validate_user(item)

        if not bl:
            return {
                'status': 400,
                'msg': f'Check json keys'
            }

        item_ = self.password_hash(item_)

        bl2 = self.check_exists_any_data(item_)

        if bl2:
            return {
                'status': 400,
                'msg': f'The data already exists'
            }

        if len(item_['user_key']) > 0 and len(item_['secret_key']) > 0:
            uk, sk = self.encrypt_api_keys(item_['user_key'], item_['secret_key'])
            item_['user_key'] = uk
            item_['secret_key'] = sk

        try:
            u_ = self.users.insert_one(item_)

            th_uid = self.create_trades_history(u_.inserted_id)

            user_ = self.users.find_one(u_.inserted_id)

            user_['trades_history'] = th_uid

            self.users.replace_one({'_id': user_['_id']}, user_)

            uid = str(u_.inserted_id)
            uid_encrypt = self.crypter.encrypt(bytes(uid, 'utf8'))
            return {
                'status': 200,
                'msg': f"Successfully added user: {item_['name']}",
                'user_id': str(uid_encrypt, 'utf8')
            }
        except NameError:
            print(NameError)
            return {
                'status': 500,
                'msg': f"Error adding user"
            }

    def insert_exchange_keys(self, item: dict, user_key: str, secret_key: str):

        bl2 = self.validate_contain_primary_user_keys(item, ['_id', 'password'])

        if not bl2:
            return {
                'status': 400,
                'msg': 'Check json keys'
            }

        is_keys = self.validate_exchange_keys(user_key, secret_key)

        if not is_keys:
            return {
                'status': 400,
                'msg': 'Check api keys'
            }

        password = item['password']
        item.pop('password', None)

        uid = self.crypter.decrypt(bytes(item['_id'], 'utf8'))
        uid = str(uid, 'utf8')
        bl3 = self.validate_user_exists_by_id(uid)

        if not bl3:
            return {
                'status': 400,
                'msg': 'The user do not exists'
            }

        item['_id'] = ObjectId(uid)

        u_ = self.users.find_one(item)

        if not self.check_password(password, u_['password']):
            return {
                'status': 400,
                'msg': 'Incorrect password'
            }

        uk, sk = self.encrypt_api_keys(user_key, secret_key)

        u_['user_key'] = uk
        u_['secret_key'] = sk
        self.users.replace_one(item, u_)

        return {
            'status': 200,
            'msg': 'Successfully added api keys'
        }

    def insert_profile_photo(self, item: dict, profile_photo: str):

        bl2 = self.validate_contain_primary_user_keys(item, ['_id', 'password'])

        if not bl2:
            return {
                'status': 400,
                'msg': 'Check json keys'
            }

        password = item['password']
        item.pop('password', None)

        uid = self.crypter.decrypt(bytes(item['_id'], 'utf8'))
        uid = str(uid, 'utf8')
        bl3 = self.validate_user_exists_by_id(uid)

        if not bl3:
            return {
                'status': 400,
                'msg': 'The user do not exists'
            }

        item['_id'] = ObjectId(uid)

        u_ = self.users.find_one(item)

        if not self.check_password(password, u_['password']):
            return {
                'status': 400,
                'msg': 'Incorrect password'
            }

        u_['profile_photo'] = profile_photo

        self.users.replace_one(item, u_)

        return {
            'status': 200,
            'msg': 'Successfully added profile photo'
        }

    def check_password(self, password_inserted: str, password_db: str):
        return check_password_hash(password_db, password_inserted)

    def validate_contain_primary_user_keys(self, item: dict, keys_expected=None):

        if keys_expected is None:
            keys_expected = ['name', 'password', 'email']
        keys = item.keys()

        bl = True

        for i in keys_expected:

            if not(i in keys):
                bl = False
                break

        return bl

    def get_user(self, item: dict):

        bl2 = self.validate_contain_primary_user_keys(item)

        if not bl2:
            return{
                'status': 400,
                'msg': 'Check json keys'
            }

        password = item['password']
        bl3 = self.validate_user_exists(item)

        if not bl3:
            return{
                'status': 400,
                'msg': 'The user do not exists'
            }

        u_ = self.users.find_one(item)

        if not self.check_password(password, u_['password']):
            return {
                'status': 400,
                'msg': 'Incorrect password'
            }

        u_.pop('password', None)
        uk_ = u_.pop('user_key', None)
        sk_ = u_.pop('secret_key', None)

        if len(uk_) > 0 or len(sk_) > 0:
            u_['api_key'] = True
        else:
            u_['api_key'] = False

        u_['_id'] = str(self.crypter.encrypt(bytes(str(u_['_id']), 'utf8')), 'utf8')
        u_['trades_history'] = str(u_['trades_history'])

        return {
            'status': 200,
            'user': u_
        }

    def get_user_by_id(self, id_: str):

        uid = self.crypter.decrypt(bytes(id_, 'utf8'))
        uid = str(uid, 'utf8')

        if not self.validate_user_exists_by_id(uid):
            return {
                'status': 400,
                'msg': 'User do not exists'
            }

        u_ = self.users.find_one({
            '_id': ObjectId(uid)
        })

        uid = str(u_['_id'])
        uid_encrypt = self.crypter.encrypt(bytes(uid, 'utf8'))

        u_['_id'] = str(uid_encrypt, 'utf8')
        u_['trades_history'] = str(u_['trades_history'])

        _uk = u_.pop('user_key', None)
        _sk = u_.pop('secret_key', None)
        u_.pop('password', None)

        if len(_uk) > 0 or len(_sk) > 0:
            u_['api_key'] = True
        else:
            u_['api_key'] = False

        return {
            'status': 200,
            'user': u_
        }

    def get_exchanges_key(self, item: dict):

        bl2 = self.validate_contain_primary_user_keys(item, ['_id', 'password'])

        if not bl2:
            return {
                'status': 400,
                'msg': 'Check json keys'
            }

        password = item['password']
        item.pop('password', None)

        uid = self.crypter.decrypt(bytes(item['_id'], 'utf8'))
        uid = str(uid, 'utf8')
        bl3 = self.validate_user_exists_by_id(uid)

        if not bl3:
            return {
                'status': 400,
                'msg': 'The user do not exists'
            }

        item['_id'] = ObjectId(uid)


        u_ = self.users.find_one(item)

        if not self.check_password(password, u_['password']):
            return {
                'status': 400,
                'msg': 'Incorrect password'
            }

        user_key = self.crypter.decrypt(bytes(u_['user_key'], 'utf8'))
        secret_key = self.crypter.decrypt(bytes(u_['secret_key'], 'utf8'))

        return {
            'status': 200,
            'user_key': str(user_key, 'utf8'),
            'secret_key': str(secret_key, 'utf8')
        }

    def add_editor(self, data):

        table_ = self.db['editors']

        data = self.password_hash(data)

        table_.insert_one(data)

    def validate_editor(self, item):

        bl = self.validate_contain_primary_user_keys(item, ['admin', 'admin_pass'])

        if not bl:
            return {
                'ok': False
            }

        pass_ = item.pop('admin_pass', None)

        u_ = self.editors.find_one({'name': item['admin']})

        if u_ is None:
            return {'ok': False}

        if not self.check_password(pass_, u_['password']):
            return {'ok': False}

        item.pop('admin', None)

        return {'ok': True}

    def get_trades_history(self, item):

        item['_id'] = ObjectId(item['_id'])

        th_ = self.trades_history.find_one(item)

        if th_ is None:
            return {
                'status': 400,
                'msg': 'ObjectId does not exists'
            }

        th_.pop('_id', None)
        th_.pop('user', None)

        return {'status': 200, 'trades_history': th_}

    def set_cantityparis(self, item):

        bl = self.validate_contain_primary_user_keys(item, ['_id', 'password', 'cantity', 'pairs'])

        if not bl:
            return {
                'status': 400,
                'msg': 'Check json keys'
            }

        if not((isinstance(item['cantity'], float) or isinstance(item['cantity'], int)) and isinstance(item['pairs'], str)):
            return {
                'status': 400,
                'msg': 'Check values'
            }

        item['cantity'] = float(item['cantity'])

        password = item.pop('password', None)

        uid = self.crypter.decrypt(bytes(item['_id'], 'utf8'))
        uid = str(uid, 'utf8')
        bl2 = self.validate_user_exists_by_id(uid)

        if not bl2:
            return {
                'status': 400,
                'msg': 'User do not exists, or uid is not valid'
            }

        item['_id'] = ObjectId(uid)
        cantity = item.pop('cantity', None)
        pairs = item.pop('pairs', None)

        u_ = self.users.find_one(item)

        if not self.check_password(password, u_['password']):
            return {
                'status': 400,
                'msg': 'Incorrect password'
            }

        u_['cantity'] = cantity
        u_['pairs'] = pairs

        self.users.replace_one(item, u_)

        return {
            'status': 200,
            'msg': 'Successfully added'
        }

    def add_trades(self, trades: dict):

        for i in trades:

            trade = trades[i]

            _data = {
                'entry': trade['entry'],
                'date': trade['date'],
                'tp': trade['tp_price'],
                'sl': trade['sl_price'],
                'finish_date': None,
                'order_id': trade['order']['clientOrderId'],
                'pnl': None,
                'positionSide': trade['positionSide']
            }

            _u = self.users.find_one({'_id': ObjectId(i)})

            _t = self.trades_history.find_one({'_id': _u['trades_history']})

            _t['trades'].insert(0, _data)

            self.trades_history.replace_one({'_id': _t['_id']}, _t)

    def put_trades(self, trades: dict):

        for i in trades:

            trade = trades[i]

            _data = {
                'entry': trade['entry'],
                'date': trade['date'],
                'tp': trade['tp_price'],
                'sl': trade['sl_price'],
                'finish_date': trade['finish_date'],
                'order_id': trade['order']['clientOrderId'],
                'pnl': trade['pnl'],
                'positionSide': trade['positionSide']
            }

            _u = self.users.find_one({'_id': ObjectId(i)})

            _t = self.trades_history.find_one({'_id': _u['trades_history']})

            for _i in _t['trades']:
                if _i['order_id'] == _data['order_id']:
                    _t['trades'][_t['trades'].index(_i)] = _data
                    break

            self.trades_history.replace_one({'_id': _t['_id']}, _t)

if __name__ == '__main__':
    mongo_db = MongoDB(
        'mongodb+srv://admin_1:aa74b6474add49868a695bcc3155e426@cluster0.umgwskd.mongodb.net/test?authSource=admin&replicaSet=atlas-qw1msu-shard-0&readPreference=primary&appname=MongoDB%20Compass&ssl=true')

    mongo_db.add_editor({
        'name': 'admin1',
        'password': 'ae8d4cca705f4806a73fbfa5eee0d7b4'
    })
