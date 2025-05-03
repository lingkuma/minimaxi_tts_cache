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

#
url = "https://api.minimax.chat/v1/t2a_v2?GroupId=" + group_id
headers = {"Content-Type": "application/json", "Authorization": "Bearer " + api_key}

# 构建TTS请求头
def build_tts_stream_headers() -> dict:
    headers = {
        'accept': 'application/json, text/plain, */*',
        'content-type': 'application/json',
        'authorization': "Bearer " + api_key,
    }
    return headers


def build_tts_stream_body(text: str, language: str = "German", voice_id: str = "violet_de", lang: str = None) -> dict:
    # 在文本后添加句号以保持陈述语气
    if text and not text.endswith(('.', '!', '?', ';', '。', '！', '？')):
        text = text + "."

    # 将单词里的小写i全部换成大写I
    text = text.replace("ni", "nI")
    text = text.replace("Gy", "GY")

    # 根据lang参数选择language_boost
    if lang:
        language_boost = 'auto'
        lang_map = {
            'zh': 'Chinese',
            'en': 'English',
            'ar': 'Arabic',
            'ru': 'Russian',
            'es': 'Spanish',
            'fr': 'French',
            'pt': 'Portuguese',
            'de': 'German',
            'tr': 'Turkish',
            'nl': 'Dutch',
            'uk': 'Ukrainian',
            'vi': 'Vietnamese',
            'id': 'Indonesian',
            'ja': 'Japanese',
            'it': 'Italian',
            'ko': 'Korean'
        }
        language_boost = lang_map.get(lang, 'auto')
        # 使用映射后的language_boost替代传入的language参数
        language = language_boost
        print(f'language_boost: {language_boost}')

    #打印text
    print(text)

    body = json.dumps({
        "model": "speech-02-turbo",
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


# 全局mpv进程，延迟启动并保持常开

mpv_process = None

def ensure_mpv_process():
    """确保MPV进程已启动"""
    global mpv_process
    if mpv_process is None or mpv_process.poll() is not None:
        mpv_command = ["mpv", "--no-cache", "--no-terminal", "--", "fd://0"]
        try:
            mpv_process = subprocess.Popen(
                mpv_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print("MPV播放器已启动")
        except Exception as e:
            print(f"MPV播放器启动失败: {e}")
            mpv_process = None
    return mpv_process is not None


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


def call_tts_stream(text: str, language: str = "German", stream: bool = True, lang: str = None) -> Iterator[bytes] | bytes:
    """调用TTS API获取音频数据，支持流式和非流式响应"""
    tts_url = url
    tts_headers = build_tts_stream_headers()

    # 创建请求体副本以便修改stream参数
    body_dict = json.loads(build_tts_stream_body(text, language, lang=lang))
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


def audio_play(audio_stream: Iterator[str]) -> bytes:
    """将16进制字符串流转换为二进制并播放"""
    print("开始流式播放...")
    audio = b""
    buffer = b""  # 预缓冲区
    buffer_size = 8192  # 预缓冲大小，可调整
    is_playing = False

    # 确保MPV进程已经启动
    ensure_mpv_process()

    for chunk in audio_stream:
        if chunk is not None and chunk != '\n':
            try:
                decoded_hex = bytes.fromhex(chunk)

                # 预缓冲积累足够数据
                # if not is_playing:
                #     buffer += decoded_hex
                #     if len(buffer) >= buffer_size:
                #         if mpv_process and mpv_process.poll() is None:
                #             mpv_process.stdin.write(buffer)
                #             mpv_process.stdin.flush()
                #             is_playing = True
                #         buffer = b""
                # # 已经开始播放，直接写入
                # elif mpv_process and mpv_process.poll() is None:
                #     mpv_process.stdin.write(decoded_hex)
                #     mpv_process.stdin.flush()

                print(".", end="", flush=True)
                audio += decoded_hex
            except Exception as e:
                print(f"\n处理音频块时出错: {e}")

    # 确保缓冲区中剩余数据被播放
    if buffer and mpv_process and mpv_process.poll() is None:
        mpv_process.stdin.write(buffer)
        mpv_process.stdin.flush()

    print("\n流式播放完成")
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
        print(f"文件不存在: {file_path}")
        return False

    try:
        # 使用单独的进程播放文件，不依赖全局mpv进程
        play_command = ["mpv", "--no-terminal", file_path]
        result = subprocess.run(play_command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"播放本地文件完成: {file_path}, 返回码: {result.returncode}")
        return result.returncode == 0
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
                print(f"处理请求：语言={lang_code}, 文本={text}")

                # 将语言代码映射到MiniMax支持的语言
                language = map_lang_code_to_minimax(lang_code)

                # 根据语言选择合适的voice_id和emotion
                voice_id = "violet_de"  # 默认值
                emotion = "happy"      # 默认值

                # 保存原始语言代码，用于传递给TTS API
                original_lang_code = lang_code

                # 获取脚本所在目录
                script_dir = os.path.dirname(os.path.abspath(__file__))

                # 构建相对于脚本的缓存路径
                cache_dir = os.path.join(script_dir, "speech-01-turbo", voice_id, emotion, lang_code)

                # 确保目录存在
                if not os.path.exists(cache_dir):
                    os.makedirs(cache_dir)

                # 文件路径
                file_path = os.path.join(cache_dir, f"{text}.mp3")

                # 检查缓存文件是否已存在
                if os.path.exists(file_path):
                    print(f"找到缓存文件: {file_path}")
                    # 从缓存文件读取音频数据
                    with open(file_path, 'rb') as file:
                        audio_data = file.read()

                    # 在响应前播放本地文件
                    # success = play_local_file(file_path)
                    # print(f"播放缓存文件结果: {success}")

                    # 直接返回音频数据
                    self.send_response(200)
                    self.send_header("Content-type", "audio/mpeg")
                    self.send_header("Content-length", str(len(audio_data)))
                    self.end_headers()
                    self.wfile.write(audio_data)
                else:
                    print(f"未找到缓存文件，开始生成: {file_path}")
                    # 如果没有缓存，返回500错误
                    self.send_response(500)
                    self.send_header("Content-type", "text/plain")
                    self.end_headers()
                    self.wfile.write(f"没有找到缓存文件: {text}".encode("utf-8"))

                    # 在后台异步生成缓存文件(不阻塞响应)
                    import threading
                    threading.Thread(target=self.generate_and_cache_audio,
                                     args=(text, language, file_path, original_lang_code)).start()
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

    def generate_and_cache_audio(self, text, language, file_path, lang_code=None):
        """后台生成并缓存音频文件"""
        try:
            print(f"开始后台生成音频: {text}")
            # 生成TTS - 使用流式API
            try:
                # 获取流式音频数据
                audio_chunk_iterator = call_tts_stream(text, language, stream=True, lang=lang_code)

                # 使用audio_play函数处理流式播放
                audio_data = audio_play(audio_chunk_iterator)

            except Exception as e:
                print(f"流式API调用失败，尝试非流式API: {str(e)}")
                # 如果流式调用失败，尝试非流式调用
                audio_data = call_tts_stream(text, language, stream=False, lang=lang_code)

                # 非流式方式下也使用mpv播放
                if mpv_process and mpv_process.poll() is None:
                    mpv_process.stdin.write(audio_data)
                    mpv_process.stdin.flush()
                    print("非流式播放完成")

            # 处理音频（移除开头静音）
            audio_data = trim_leading_silence(audio_data)

            # 保存文件
            with open(file_path, 'wb') as file:
                file.write(audio_data)

            print(f"已生成并缓存音频: {file_path}")
        except Exception as e:
            print(f"生成缓存音频时出错: {str(e)}")


def run_server(port=3001):
    server_address = ('', port)
    httpd = HTTPServer(server_address, TTSRequestHandler)
    print(f"启动TTS缓存服务器，监听端口 {port}...")
    httpd.serve_forever()


# 启动服务器（替换原来的直接TTS调用）
if __name__ == "__main__":
    run_server()