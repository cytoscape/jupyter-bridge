from flask import Flask
import time
from flask import request
import json

app = Flask(__name__)

msg_map = dict()

@app.route('/server_send_to_js', methods=['PUT'])
def server_send_to_js():
    return 'server_send_to_js is not implemented: ' + str(request.args)

@app.route('/js_receive_from_server', methods=['GET'])
def js_receive_from_server():
    return 'js_receive_from_server is not implemented ' + str(request.args)

@app.route('/js_send_to_server', methods=['PUT'])
def js_send_to_server():
    if 'msg_id' in request.args:
        if request.content_type.startswith('application/json'):
            data = request.get_data()
            json_data = json.loads(data.decode('utf-8'))
            print(str(data))
            print(str(json_data))
            msg_map[request.args['msg_id']] = {'status': 'idle', 'submit_time': time.asctime(), 'job': json_data}
            print(str(msg_map))
        else:
            print('invalid content type: ' + request.content_type)
    else:
        print('missing msg_id')
    return 'js_send_to_server is not implemented ' + str(request.args)

@app.route('/server_receive_from_js', methods=['GET'])
def server_receive_from_js():
    return 'server_receive_from_js is not implemented ' + str(request.args)



if __name__=='__main__':
    app.run(debug=True, host='69.163.152.126', port=9529)
