"""
科大讯飞 webAPI语音合成
API文档: https://www.xfyun.cn/doc/tts/online_tts/API.html
"""


import base64
import json
import ssl
import os
# import sys
import time
import threading
import hmac
import hashlib
import wsgiref.handlers

from urllib.parse import urlencode
from datetime import datetime
from time import mktime

import websocket


STATUS_FIRST_FRAME = 0  # 第一帧的标识
STATUS_CONTINUE_FRAME = 1  # 中间帧标识
STATUS_LAST_FRAME = 2  # 最后一帧的标识


class TTS(object):

    APP_ID = ""
    API_KEY = ""
    API_SECRET = ""

    def __init__(self):

        # 公共参数(common)
        self.common_args = {"app_id": self.APP_ID}

        # 业务参数(business)
        self.business_args = {
            "aue": 'lame',                                  # 音频编码
            "sfl": 1,                                       # 需要配合aue=lame使用，开启流式返回
            "auf": "audio/L16;rate=16000",                  # 音频采样率，可选值:8000/16000
            "vcn": "aisjinger",                             # 发音人: aisjinger
            "speed": 50,                                    # 语速，可选值：[0-100]，默认为50
            "volume": 50,                                   # 音量，可选值：[0-100]，默认为50
            "pitch": 50,                                    # 音高，可选值：[0-100]，默认为50
            "bgs": 0,                                       # 合成音频的背景音 0:无背景音（默认值）/ 1:有背景音
            "tte": "utf8",                                  # 文本编码格式
            "reg": "2",                                     # 设置英文发音方式
            "rdn": "0",                                     # 合成音频数字发音方式
        }

    # 生成业务数据流参数(data)
    @staticmethod
    def gen_data(text):
        data = {
            "status": 2,  # 数据状态，固定为2 注：由于流式合成的文本只能一次性传输，不支持多次分段传输，此处status必须为2。
            "text": str(base64.b64encode(text.encode('utf-8')), "UTF8")
        }
        return data

    # 生成url
    def create_url(self):
        url = 'wss://tts-api.xfyun.cn/v2/tts'
        # 生成RFC1123格式的时间戳
        now = datetime.now()
        date = wsgiref.handlers.format_date_time(mktime(now.timetuple()))

        # 拼接字符串
        signature_origin = "host: ws-api.xfyun.cn\n" \
                           "date: {}\n" \
                           "GET /v2/tts HTTP/1.1".format(date)
        # 进行hmac - sha256进行加密
        signature_sha = hmac.new(self.API_SECRET.encode("utf-8"),
                                 signature_origin.encode("utf-8"),
                                 digestmod=hashlib.sha256).digest()
        signature_sha = base64.b64encode(signature_sha).decode(encoding='utf-8')

        authorization_origin = "api_key=\"%s\", algorithm=\"hmac-sha256\", " \
                               "headers=\"host date request-line\", signature=\"%s\"" % (self.API_KEY, signature_sha)
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode(encoding='utf-8')

        # 将请求的鉴权参数组合为字典
        v = {
            "authorization": authorization,
            "date": date,
            "host": "ws-api.xfyun.cn"
        }
        # 拼接鉴权参数，生成url
        url = url + '?' + urlencode(v)
        return url


class TTSWebSocket(object):

    def __init__(self, msg, tts_obj):
        self.msg = msg
        self.tts = tts_obj
        self.url = tts_obj.create_url()
        self.data = []
        self.flag = False
        self.audio_dir = "audio/"
        self.ws_listener = None

        websocket.enableTrace(False)
        self.ws = websocket.WebSocketApp(self.url, on_message=self.on_message,
                                         on_error=self.on_error, on_close=self.on_close)

    def on_message(self, ws, msg):
        try:
            message = json.loads(msg)
            print(message)
            code = message["code"]
            sid = message["sid"]
            audio = message["data"]["audio"]
            status = message["data"]["status"]

            if code == 0:
                self.data.append(audio)
            else:
                err_msg = message["message"]
                print("sid:%s call error:%s code is:%s" % (sid, err_msg, code))
            if status == 2:
                print("------>数据接受完毕")
                self.flag = True
                self.ws.close()
        except Exception as e:
            print("receive msg,but parse exception:", e)
            # print(sys.exc_info()[0])

    def on_error(self, ws, error):
        print("### error:", error)

    def on_close(self, ws):
        print("### closed ###")

    def on_open(self, ws):
        d = {"common": self.tts.common_args,
             "business": self.tts.business_args,
             "data": self.tts.gen_data(self.msg[1]),
             }
        d = json.dumps(d)
        print("------>开始发送文本数据: {}".format(self.msg))
        self.ws.send(d)

    def get_result(self, audio_filename):
        self.flag = False

        if self.data:
            audio_file = os.path.join(self.audio_dir, f"{audio_filename}.mp3")
            with open(audio_file, 'wb') as f:
                for _r in self.data:
                    f.write(base64.b64decode(_r))
            return audio_file
        return "error：未收到任何信息"

    def run(self):
        self.ws.on_open = self.on_open
        self.ws_listener = threading.Thread(target=self.ws.run_forever, kwargs={"sslopt": {"cert_reqs": ssl.CERT_NONE}})
        self.ws_listener.daemon = True
        self.ws_listener.start()

        timeout = 15
        end_time = time.time() + timeout
        while True:
            if time.time() > end_time:
                raise websocket.WebSocketTimeoutException
            if self.flag:
                result = self.get_result(str(self.msg[0]))
                return result


def main():
    text = (
        (0, "习近平：美丽中国不是涂脂抹粉 而是健康习近平勉励少先队员"),
        (1, "课本中的英烈 我们从未忘记清明策划 红色家书映照初心使命"),
        (2, "越南国会投票免去阮春福政府总理职务"),
        (3, "白皮书说，党的十八大以来，中国的核安全事业进入安全高效发展的新时期。"
            "在核安全观引领下，中国逐步构建起法律规范、行政监管、行业自律、技术保障、"
            "人才支撑、文化引领、社会参与、国际合作等为主体的核安全治理体系，核安全防线更加牢固。"),
        (4, "这个问题一般是使用了未授权的发音人，请到控制台检查是否所用发音人未添加，或授权已到期；"
            "另外，若总合成交互量超过上限也会报错11200。")
    )

    tts = TTS()
    sever = TTSWebSocket(tts_obj=tts, msg=text[4])
    result = sever.run()
    print(result)


if __name__ == '__main__':
    main()
