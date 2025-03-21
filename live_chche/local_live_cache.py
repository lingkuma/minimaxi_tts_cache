# This Python file uses the following encoding: utf-8

import json
import os
import subprocess
import time
from typing import Iterator
from dotenv import load_dotenv
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import re
from pydub import AudioSegment
from pydub.silence import detect_leading_silence
import io

#https://www.minimax.io/platform/document/T2A%20V2
#http://localhost:3001/langid={lang}&txt={word}

# language_boost 
# Enhance the ability to recognize specified languages and dialects.
# Supported values include:
# 'Chinese', 'Chinese,Yue', 'English', 'Arabic', 'Russian', 'Spanish', 'French', 'Portuguese', 'German', 'Turkish', 'Dutch', 'Ukrainian', 'Vietnamese', 'Indonesian', 'Japanese', 'Italian', 'Korean', 'auto'

# 加载.env文件
load_dotenv()

group_id = os.getenv('group_id')
api_key = os.getenv('api_key')

# 确保环境变量已正确加载，否则提供错误信息
if group_id is None or api_key is None:
    raise ValueError("环境变量 'group_id' 或 'api_key' 未设置。请确保.env文件正确配置并已加载。")

file_format = 'mp3'  # support mp3/pcm/flac

url = "https://api.minimaxi.chat/v1/t2a_v2?GroupId=" + group_id
headers = {"Content-Type": "application/json", "Authorization": "Bearer " + api_key}


def build_tts_stream_headers() -> dict:
    headers = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/json',
        'authorization': "Bearer " + api_key,
    }
    return headers


def build_tts_stream_body(text: str, language: str = "German", voice_id: str = "violet_de") -> dict:
    # 在文本后添加句号以保持陈述语气
    if text and not text.endswith(('.', '!', '?', ';', '。', '！', '？')):
        text = text + "."
 
    # 可以根据需要添加更多语言的voice_id映射
    
    body = json.dumps({
        "model": "speech-01-turbo",
        "text": text,
        "stream": True,
        "language_boost": language,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
            "emotion": "happy" # range:["happy", "sad", "angry", "fearful", "disgusted", "surprised", "neutral"]
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1
        }
    })
    return body


mpv_command = ["mpv", "--no-cache", "--no-terminal", "--", "fd://0"]
mpv_process = subprocess.Popen(
    mpv_command,
    stdin=subprocess.PIPE,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)


def trim_leading_silence(audio_data: bytes, silence_threshold=-50, chunk_size=10) -> bytes:
    """
    删除音频开头的无声部分
    
    参数:
    - audio_data: 音频文件的二进制数据
    - silence_threshold: 静音阈值（dB），默认-50dB
    - chunk_size: 检测静音的时间片段大小（毫秒）
    
    返回:
    - 处理后的音频二进制数据
    """
    try:
        # 将二进制数据转换为AudioSegment对象
        sound = AudioSegment.from_file(io.BytesIO(audio_data), format="mp3")
        
        # 检测并删除开头的静音
        start_trim = detect_leading_silence(sound, silence_threshold=silence_threshold, chunk_size=chunk_size)
        
        # 如果检测到静音，则裁剪音频
        if start_trim > 0:
            trimmed_sound = sound[start_trim:]
            # 将处理后的音频转换回二进制数据
            buffer = io.BytesIO()
            trimmed_sound.export(buffer, format="mp3")
            return buffer.getvalue()
        
        # 如果没有检测到静音，则返回原始数据
        return audio_data
    except Exception as e:
        print(f"音频处理错误: {str(e)}")
        # 出错时返回原始音频数据
        return audio_data


def call_tts_stream(text: str, language: str = "German", stream: bool = True) -> Iterator[bytes] or bytes:
    """调用TTS API获取音频数据，支持流式和非流式响应"""
    tts_url = url
    tts_headers = build_tts_stream_headers()
    
    # 创建请求体副本以便修改stream参数
    body_dict = json.loads(build_tts_stream_body(text, language))
    body_dict["stream"] = stream
    tts_body = json.dumps(body_dict)

    response = requests.request("POST", tts_url, headers=tts_headers, data=tts_body)
    
    # 非流式响应处理
    if not stream:
        if not response.ok:
            raise Exception(f"API请求失败: {response.status_code} - {response.text}")
        
        data = response.json()
        if "data" in data and "audio" in data["data"]:
            audio_data = bytes.fromhex(data["data"]["audio"])
            # 处理音频，去除开头静音
            processed_audio = trim_leading_silence(audio_data)
            return processed_audio
        else:
            raise Exception("API返回数据格式不正确")
    
    # 流式响应处理
    response = requests.request("POST", tts_url, stream=True, headers=tts_headers, data=tts_body)
    for chunk in (response.raw):
        if chunk:
            if chunk[:5] == b'data:':
                data = json.loads(chunk[5:])
                if "data" in data and "extra_info" not in data:
                    if "audio" in data["data"]:
                        audio = data["data"]['audio']
                        yield audio


def audio_play(audio_stream: Iterator[bytes]) -> bytes:
    audio = b""
    for chunk in audio_stream:
        if chunk is not None and chunk != '\n':
            decoded_hex = bytes.fromhex(chunk)
            mpv_process.stdin.write(decoded_hex)  # type: ignore
            mpv_process.stdin.flush()
            audio += decoded_hex

    return audio


# 语言代码到MiniMax语言的映射
def map_lang_code_to_minimax(lang_code: str) -> str:
    lang_map = {
        "de": "German",
        "en": "English",
        "zh": "Chinese",
        "fr": "French",
        "es": "Spanish",
        # 可以根据需要添加更多映射
    }
    return lang_map.get(lang_code, "auto")


def play_local_file(file_path: str) -> bool:
    """播放本地音频文件"""
    if not os.path.exists(file_path):
        return False
    
    try:
        play_command = ["mpv", "--no-terminal", file_path]
        subprocess.run(play_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        print(f"播放本地文件出错: {str(e)}")
        return False


class TTSRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 解析请求路径
        try:
            # 使用正则表达式提取langid和txt参数
            match = re.match(r'/langid=([^&]+)&txt=(.+)', self.path)
            if match:
                lang_code = match.group(1)
                text = match.group(2)
                
                # URL解码文本内容
                text = urllib.parse.unquote(text)
                
                # 将语言代码映射到MiniMax支持的语言
                language = map_lang_code_to_minimax(lang_code)
                
                # 根据语言选择合适的voice_id和emotion
                voice_id = "violet_de"  # 默认值
                emotion = "happy"      # 默认值
                
                # 获取脚本所在目录
                script_dir = os.path.dirname(os.path.abspath(__file__))
                
                # 构建相对于脚本的缓存路径
                cache_dir = os.path.join(script_dir, "speech-01-turbo", voice_id, emotion, lang_code)
                
                # 确保目录存在
                if not os.path.exists(cache_dir):
                    os.makedirs(cache_dir)
                
                # 文件路径
                file_path = os.path.join(cache_dir, f"{text}.mp3")
                
                # 音频数据变量
                audio_data = None
                
                # 检查缓存文件是否已存在
                if os.path.exists(file_path):
                    # 从缓存文件读取音频数据
                    with open(file_path, 'rb') as file:
                        audio_data = file.read()
                else:
                    # 生成TTS - 使用流式API
                    try:
                        # 修改调用方式，不再播放而是直接获取音频数据
                        audio_chunk_iterator = call_tts_stream(text, language, stream=True)
                        audio_data = b""
                        for chunk in audio_chunk_iterator:
                            if chunk is not None and chunk != '\n':
                                decoded_hex = bytes.fromhex(chunk)
                                audio_data += decoded_hex
                    except Exception as e:
                        print(f"流式API调用失败，尝试非流式API: {str(e)}")
                        # 如果流式调用失败，尝试非流式调用
                        audio_data = call_tts_stream(text, language, stream=False)
                    
                    # 处理音频（移除开头静音）
                    audio_data = trim_leading_silence(audio_data)
                    
                    # 保存文件
                    with open(file_path, 'wb') as file:
                        file.write(audio_data)
                
                # 直接返回音频数据
                self.send_response(200)
                self.send_header("Content-type", "audio/mpeg")
                self.send_header("Content-length", str(len(audio_data)))
                # self.send_header("Content-Disposition", f'attachment; filename="{text}.mp3"')
                self.end_headers()
                self.wfile.write(audio_data)
            else:
                self.send_response(400)
                self.send_header("Content-type", "text/plain")
                self.end_headers()
                self.wfile.write("请求格式错误，正确格式: /langid=语言代码&txt=文本".encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(f"服务器错误: {str(e)}".encode("utf-8"))


def run_server(port=3001):
    server_address = ('', port)
    httpd = HTTPServer(server_address, TTSRequestHandler)
    print(f"启动TTS缓存服务器，监听端口 {port}...")
    httpd.serve_forever()


# 启动服务器（替换原来的直接TTS调用）
if __name__ == "__main__":
    run_server()