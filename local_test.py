# This Python file uses the following encoding: utf-8

import json
import os
import subprocess
import time
from typing import Iterator
from dotenv import load_dotenv

import requests


#https://www.minimax.io/platform/document/T2A%20V2

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


def build_tts_stream_body(text: str) -> dict:
    body = json.dumps({
        "model": "speech-01-turbo",
        "text": "wie.",
        "stream": True,
        "language_boost": "German",
        "voice_setting": {
            "voice_id": "violet_de",
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


def call_tts_stream(text: str) -> Iterator[bytes]:
    tts_url = url
    tts_headers = build_tts_stream_headers()
    tts_body = build_tts_stream_body(text)

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


audio_chunk_iterator = call_tts_stream('')
audio = audio_play(audio_chunk_iterator)

# save results to file
timestamp = int(time.time())
file_name = f'output_total_{timestamp}.{file_format}'
with open(file_name, 'wb') as file:
    file.write(audio)