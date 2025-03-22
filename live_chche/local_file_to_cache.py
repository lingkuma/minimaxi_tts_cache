# This Python file uses the following encoding: utf-8

import json
import os
import time
import threading
from queue import Queue
from typing import Iterator
from dotenv import load_dotenv
import requests
import re
from pydub import AudioSegment
from pydub.silence import detect_leading_silence
import io

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


def build_tts_stream_body(text: str, language: str = "German", voice_id: str = "violet_de") -> dict:
    # 在文本后添加句号以保持陈述语气
    if text and not text.endswith(('.', '!', '?', ';', '。', '！', '？')):
        text = text + "."
    text = text.replace("ni", "nI")
    text = text.replace("Gy", "GY")
    body = json.dumps({
        "model": "speech-01-turbo",
        "text": text,
        "stream": False,
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


def call_tts_stream(text: str, language: str = "German") -> bytes:
    """调用TTS API获取音频数据，并直接返回二进制数据"""
    tts_url = url
    tts_headers = build_tts_stream_headers()
    tts_body = build_tts_stream_body(text, language)

    response = requests.request("POST", tts_url, headers=tts_headers, data=tts_body)
    
    # 非流式返回时，直接获取JSON响应
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


def read_word_list(file_path: str) -> list:
    """读取单词表文件，返回单词列表"""
    words = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            word = line.strip()
            if word and not word.startswith('...'): # 跳过省略行
                # 检查是否有分隔符，如果有则尝试提取，否则直接使用整行
                if '|' in word:
                    parts = word.split('|', 1)
                    if len(parts) > 1:
                        word = parts[1].strip()
                # 确保单词不为空
                if word:
                    words.append(word)
    return words


def get_existing_cached_files(cache_dir: str) -> set:
    """获取已经缓存的文件列表"""
    cached_files = set()
    if os.path.exists(cache_dir):
        for filename in os.listdir(cache_dir):
            if filename.endswith('.mp3'):
                # 从文件名中提取单词
                word = filename[:-4]  # 移除 .mp3 后缀
                cached_files.add(word)
    return cached_files


# 用于多线程的工作函数，处理单个单词
def process_single_word(word: str, cache_dir: str, language: str, processed_count: list, lock: threading.Lock):
    try:
        # 构建保存路径
        file_path = os.path.join(cache_dir, f"{word}.mp3")
        
        # 如果文件已存在，跳过
        if os.path.exists(file_path):
            with lock:
                processed_count[0] += 1
                print(f"文件已存在: {file_path}，跳过 [进度: {processed_count[0]}/{processed_count[1]}]")
            return
        
        # 获取TTS音频
        audio_data = call_tts_stream(word, language)
        
        # 保存文件
        with open(file_path, 'wb') as file:
            file.write(audio_data)
        
        with lock:
            processed_count[0] += 1
            print(f"保存到: {file_path} [进度: {processed_count[0]}/{processed_count[1]}]")
        
    except Exception as e:
        with lock:
            processed_count[0] += 1
            print(f"处理单词 '{word}' 时出错: {str(e)} [进度: {processed_count[0]}/{processed_count[1]}]")


# 线程工作函数，处理一组单词
def worker_thread(word_queue: Queue, cache_dir: str, language: str, processed_count: list, lock: threading.Lock):
    while not word_queue.empty():
        try:
            word = word_queue.get(block=False)
            process_single_word(word, cache_dir, language, processed_count, lock)
            # 添加小延迟以避免API速率限制
            time.sleep(0.2)
        except Exception as e:
            print(f"线程处理出错: {str(e)}")
        finally:
            word_queue.task_done()


def process_word_list(word_list_path: str, lang_code: str = "de", thread_count: int = 3):
    """处理单词列表，检查缓存并下载未缓存的单词，使用多线程加速处理"""
    # 获取脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 构建相对于脚本的缓存路径
    voice_id = "violet_de"  # 默认值
    emotion = "happy"      # 默认值
    cache_dir = os.path.join(script_dir, "speech-01-turbo", voice_id, emotion, lang_code)
    
    # 确保目录存在
    if not os.path.exists(cache_dir):
        os.makedirs(cache_dir)
    
    # 读取单词列表
    words = read_word_list(word_list_path)
    print(f"从 {word_list_path} 读取了 {len(words)} 个单词")
    
    # 获取已缓存的文件
    cached_files = get_existing_cached_files(cache_dir)
    print(f"找到 {len(cached_files)} 个已缓存的单词")
    
    # 计算需要下载的单词
    words_to_download = [word for word in words if word not in cached_files]
    print(f"需要下载 {len(words_to_download)} 个单词")
    
    if not words_to_download:
        print("所有单词都已缓存，无需下载！")
        return
    
    # 创建工作队列
    word_queue = Queue()
    for word in words_to_download:
        word_queue.put(word)
    
    # 创建线程锁和进度计数器 [当前处理数, 总数]
    lock = threading.Lock()
    processed_count = [0, len(words_to_download)]
    
    # 调整线程数量，避免创建过多线程
    thread_count = min(thread_count, len(words_to_download))
    print(f"使用 {thread_count} 个线程进行处理...")
    
    # 创建并启动线程
    language = map_lang_code_to_minimax(lang_code)
    threads = []
    for _ in range(thread_count):
        thread = threading.Thread(
            target=worker_thread,
            args=(word_queue, cache_dir, language, processed_count, lock)
        )
        thread.daemon = True
        thread.start()
        threads.append(thread)
    
    # 等待所有任务完成
    word_queue.join()
    
    print("所有单词处理完成！")


# 主函数入口
if __name__ == "__main__":
    # 获取脚本目录下的listtest.txt文件路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    word_list_path = os.path.join(script_dir, "./wort_list/de/die_wand/list.txt")
    
    # 设置线程数 - 可以根据需要调整
    thread_count = 3  # 默认使用3个线程，可以手动修改这个值
    
    if os.path.exists(word_list_path):
        process_word_list(word_list_path, "de", thread_count)
    else:
        print(f"错误: 找不到单词表文件 {word_list_path}")