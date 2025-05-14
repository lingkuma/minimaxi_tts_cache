#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
不能用了
"""

import json
import time
import uuid
import threading
import websocket
import argparse
from flask import Flask, request, Response, jsonify
from flask_cors import CORS
import os
import io
import binascii
import hashlib
from urllib.parse import urlencode
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()




class HailuoWSTest:
    """Hailuo AI WebSocket测试类"""

    def __init__(self, token, device_id=None):
        """初始化测试类"""
        self.token = token
        self.device_id = device_id or "335735017107767300"
        self.uuid = str(uuid.uuid4())
        self.connected = False
        self.connection_event = threading.Event()
        self.message_received = threading.Event() # 用于初始连接确认
        self.last_message = None
        self.ws = None  # WebSocketApp instance
        self.heartbeat_thread = None
        self.stop_threads = threading.Event() # Event to signal threads to stop
        self.audio_buffer = io.BytesIO() # 用于存储接收到的音频块
        self.is_processing_tts = False # 标记是否正在进行TTS处理 (替代 tts_active)
        self.current_tts_msg_id = None # 当前正在处理的TTS请求的msg_id
        self.audio_hex_buffer = [] # 用于存储接收到的十六进制音频数据字符串片段

    def generate_yy_value(self, timestamp, token):
        """生成yy参数值

        注意：这里我们尝试使用与curl命令中相同的yy值
        实际应用中，应该根据服务器的算法生成
        """
        # 从您的curl命令中提取的yy值
        if timestamp > 1746638000000 and timestamp < 1746639000000:
            return "d94d5add90c15ef1fb9af1b0d20a2d87"

        # 备用算法
        data = f"{timestamp}{token[:10]}"
        return hashlib.md5(data.encode()).hexdigest()

    def build_ws_url(self):
        """构建WebSocket URL"""
        base_url = "wss://minimaxi.com/v1/audio/ws"

        # 使用固定的时间戳和uuid，与curl命令保持一致
        timestamp = 1746638222913  # 从curl命令中提取的时间戳
        uuid_value = "e3031f83-b1d6-4dd4-a701-7bebfe8f5090"  # 从curl命令中提取的uuid

        # 使用固定的yy值
        yy_value = "d94d5add90c15ef1fb9af1b0d20a2d87"  # 从curl命令中提取的yy值

        params = {
            "device_platform": "web",
            "app_id": "3001",
            "version_code": "22201",
            "biz_id": "1",
            "uuid": uuid_value,
            "lang": "zh-Hans",
            "device_id": self.device_id,
            "os_name": "Windows",
            "browser_name": "chrome",
            "device_memory": "8",
            "cpu_core_num": "12",
            "browser_language": "de-DE",
            "browser_platform": "Win32",
            "screen_width": "1920",
            "screen_height": "1080",
            "unix": str(timestamp),
            "yy": yy_value,
            "token": self.token
        }

        return f"{base_url}?{urlencode(params)}"

    def on_open(self, ws):
        """WebSocket连接打开时的回调"""
        print("WebSocket连接已建立")
        self.connected = True
        self.connection_event.set()
        self.ws = ws # Store the WebSocketApp instance

        # 启动心跳发送线程
        # 确保之前的停止事件被清除，以便新连接可以开始新的心跳
        self.stop_threads.clear()
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_sender)
        self.heartbeat_thread.daemon = True # 设置为守护线程，以便主程序退出时它也会退出
        self.heartbeat_thread.start()
        print("心跳发送线程已启动")

    def _heartbeat_sender(self):
        """周期性发送心跳消息"""
        heartbeat_interval = 15  # 心跳间隔（秒），根据需要调整
        print(f"心跳线程：将每 {heartbeat_interval} 秒发送一次心跳。")
        while not self.stop_threads.wait(heartbeat_interval):
            if self.ws and self.connected:
                try:
                    heartbeat_msg = {
                        "method": "Heartbeat",
                        "msg_id": str(uuid.uuid4()),
                        "timestamp": int(time.time() * 1000)
                    }
                    self.ws.send(json.dumps(heartbeat_msg))
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] (周期性)已发送心跳消息: {json.dumps(heartbeat_msg)}")
                except websocket.WebSocketConnectionClosedException:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 心跳发送失败：WebSocket连接已关闭。")
                    self.stop_threads.set() # 确保其他地方知道连接已断开
                    break
                except Exception as e:
                    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 发送心跳时发生错误: {e}")
                    self.stop_threads.set()
                    break
            else:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 心跳线程：WebSocket未连接或实例不存在，停止心跳。")
                self.stop_threads.set() # 确保设置停止事件
                break
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 心跳发送线程已停止。")


    def on_message(self, ws, message):
        """接收WebSocket消息的回调"""
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')
        if isinstance(message, str):
            # 检查消息是否包含音频数据，如果包含则不显示完整消息
            if '"audio":' in message:
                print(f"[{current_time}] 收到包含音频数据的文本消息")
            else:
                print(f"[{current_time}] 收到文本消息: {message[:500]}{'...' if len(message) > 500 else ''}")

            # 尝试直接从消息中提取音频数据
            try:
                msg_data = json.loads(message)
                # 检查是否包含音频数据
                if "data" in msg_data and "audio" in msg_data["data"] and self.is_processing_tts:
                    hex_chunk = msg_data["data"]["audio"]
                    status = msg_data["data"].get("status", 1)  # 默认为中间块

                    if hex_chunk and isinstance(hex_chunk, str):
                        # 验证数据有效性
                        try:
                            audio_bytes = bytes.fromhex(hex_chunk)
                            print(f"[{current_time}] 直接从消息中提取到音频数据 (字节数: {len(audio_bytes)}, 状态: {status})")

                            # 将数据添加到缓冲区（不检查重复，保持顺序）
                            self.audio_hex_buffer.append(hex_chunk)
                            print(f"[{current_time}] 已添加到缓冲区，当前缓冲区大小: {len(self.audio_hex_buffer)}")

                            # 如果是结束块，设置处理状态为完成
                            if status == 2:
                                print(f"[{current_time}] 检测到结束块 (status=2)，标记TTS处理完成")
                                self.is_processing_tts = False
                        except ValueError as e:
                            print(f"[{current_time}] 解码音频数据失败: {e}")
            except Exception as e:
                print(f"[{current_time}] 尝试提取音频数据时出错: {e}")
                # 继续正常处理

        elif isinstance(message, bytes):
            # 根据新的需求，我们不再期望直接收到二进制音频流，而是内嵌在JSON中的hex字符串
            print(f"[{current_time}] 收到二进制消息 (长度: {len(message)} bytes)")
            # 如果服务器确实发送了纯二进制消息，这里可以添加特定处理逻辑
            # 但根据任务描述，音频数据在JSON文本消息中
            self.last_message = message
            return # 假设纯二进制消息不是我们要处理的TTS响应格式
        else:
            print(f"[{current_time}] 收到未知类型的消息: {type(message)}")
            self.last_message = message
            return

        try:
            msg_data = json.loads(message)
            method = msg_data.get("method")
            msg_id_from_server = msg_data.get("msg_id") # 有些响应可能直接有msg_id
            extra_info = msg_data.get("extra_info", {})
            msg_id_in_extra = extra_info.get("msg_id") # TTS的msg_id在extra_info中

            if method == "HeartbeatResp":
                print(f"[{current_time}] 收到心跳响应: {message}")
                if not self.message_received.is_set():
                    self.message_received.set()
            elif method == "AudioPlay":
                if not self.is_processing_tts:
                    print(f"[{current_time}] 警告: 收到 AudioPlay 消息，但当前没有活动的TTS请求 (is_processing_tts=False)。忽略此消息。 (服务器Msg ID: {msg_id_from_server}, Extra Msg ID: {msg_id_in_extra})")
                    return
                # 任务要求：删除之前从 extra_info 提取并比较 msg_id 的逻辑。
                # 现在仅依赖 self.is_processing_tts 来决定是否处理 AudioPlay 消息。
                # self.current_tts_msg_id 将用于文件名生成和日志记录。
                print(f"[{current_time}] AudioPlay: is_processing_tts is True. 关联的TTS请求 msg_id: '{self.current_tts_msg_id}'. 收到的消息 Extra Msg ID: '{msg_id_in_extra}'.")

                audio_payload = msg_data.get("data", {}) # 确保 audio_payload 是一个字典
                base_response = msg_data.get("base_resp", {}) # 提取顶层 base_resp

                # 也检查 data 字段中是否有 base_resp
                data_base_resp = audio_payload.get("base_resp", {})

                # 合并两个 base_resp，优先使用 data 中的
                if data_base_resp:
                    base_response = data_base_resp

                hex_chunk = audio_payload.get("audio")
                status = audio_payload.get("status")
                base_status_code = base_response.get("status_code")
                base_status_msg = base_response.get("status_msg", "")

                print(f"[{current_time}] 处理 AudioPlay 消息: Extra Msg ID: {msg_id_in_extra}, Status: {status}, BaseStatusCode: {base_status_code}, BaseStatusMsg: '{base_status_msg}', Audio Chunk Present: {bool(hex_chunk)}")

                # 记录收到的音频块信息
                if hex_chunk and isinstance(hex_chunk, str):
                    print(f"[{current_time}] 收到音频块 (Status: {status}, BaseStatusCode: {base_status_code}, BaseStatusMsg: '{base_status_msg}', Msg ID: {msg_id_in_extra})。")

                    # 验证数据有效性
                    try:
                        audio_bytes = bytes.fromhex(hex_chunk)
                        # 将收到的音频块添加到缓冲区（不检查重复，保持顺序）
                        self.audio_hex_buffer.append(hex_chunk)
                        chunk_index = len(self.audio_hex_buffer)
                        print(f"[{current_time}] 音频块 {chunk_index} 已成功解码并添加到缓冲区 (字节数: {len(audio_bytes)})")
                    except ValueError as e:
                        print(f"[{current_time}] 错误: 解码音频块的十六进制数据失败: {e}")
                    except Exception as e:
                        print(f"[{current_time}] 处理音频块时发生错误: {e}")

                elif status != 2: # 如果不是结束块，但hex_chunk为空或无效，记录一下
                    print(f"[{current_time}] AudioPlay 消息 (Status: {status}) 未包含有效的音频数据块 (hex_chunk is None or not a string)。 (Msg ID: {msg_id_in_extra})")

                # 检查是否有 "base_resp":{"status_code":0,"status_msg":"success"} 这个结束标签
                base_status_msg = base_response.get("status_msg", "")

                # 明确的结束条件：
                # 1. 检查 base_resp 中的 status_msg 是否为 "success"
                # 2. 或者 status == 2 且 base_status_code == 0 (兼容旧逻辑)
                if base_status_msg == "success" or (status == 2 and base_status_code == 0):
                    print(f"[{current_time}] 收到明确的TTS结束信号 (Status: {status}, BaseStatusCode: {base_status_code}, BaseStatusMsg: {base_status_msg})。 (关联的TTS Msg ID: {self.current_tts_msg_id}, 收到的 Extra Msg ID: {msg_id_in_extra})")
                    try:
                        # 验证音频数据完整性，但不保存文件
                        if not self.audio_hex_buffer:
                            print(f"[{current_time}] 结束信号已收到，但没有收集到任何有效的音频数据。 (TTS Msg ID: {self.current_tts_msg_id})")
                        else:
                            print(f"[{current_time}] 收到结束信号，音频数据接收完成。 (TTS Msg ID: {self.current_tts_msg_id})")
                            try:
                                # 仅验证数据有效性，不保存文件
                                total_size = 0
                                for hex_data in self.audio_hex_buffer:
                                    total_size += len(bytes.fromhex(hex_data))

                                print(f"[{current_time}] 完整的音频数据接收完成 (总字节数: {total_size}, 块数: {len(self.audio_hex_buffer)}, TTS Msg ID: {self.current_tts_msg_id})")
                            except ValueError as e:
                                print(f"[{current_time}] 错误: 解码合并的音频数据失败: {e} (TTS Msg ID: {self.current_tts_msg_id})")
                            except Exception as e:
                                print(f"[{current_time}] 处理音频数据时发生未知错误: {e} (TTS Msg ID: {self.current_tts_msg_id})")
                    except Exception as e: # 捕获其他在音频处理过程中可能发生的错误
                        print(f"[{current_time}] 处理音频数据时发生未知错误: {e} (TTS Msg ID: {self.current_tts_msg_id})")
                    finally:
                        # 关键：无论 try 块中发生什么，都必须执行状态重置
                        print(f"[{current_time}] 正在重置TTS状态 (在明确结束信号的finally块中)... (TTS Msg ID: {self.current_tts_msg_id})")
                        # 不清空audio_hex_buffer，因为hailuo_ws_server.py需要使用它
                        # self.audio_hex_buffer = []
                        self.is_processing_tts = False
                        self.current_tts_msg_id = None

                elif status == 1 or status == 0: # 中间块
                    print(f"[{current_time}] 收到音频数据中间块 (Status: {status}, BaseStatusCode: {base_status_code}, BaseStatusMsg: '{base_status_msg}', Msg ID: {msg_id_in_extra})。等待后续数据块。")
                    # 不重置TTS状态或清空缓冲区

                # 处理 status == 2 但 base_status_code != 0 (错误结束) 或其他意外 status
                elif (status == 2 and base_status_code != 0) or status not in [0, 1, 2]: # 处理错误结束或意外status
                    warning_message = f"[{current_time}] 警告: AudioPlay 消息收到意外的结束状态或错误响应。"
                    if status == 2 and base_status_code != 0: # status 为2，但 base_resp.status_code 非0，表示服务端处理该请求时可能出错
                        warning_message += f" Status: 2 (结束信号), 但 BaseStatusCode: {base_status_code} (非0表示错误)."
                    else: # status 不是 0, 1, 或 2
                        warning_message += f" 未知的 Status 值: {status}, BaseStatusCode: {base_status_code}."
                    warning_message += f" (关联的TTS Msg ID: {self.current_tts_msg_id}, 收到的 Extra Msg ID: {msg_id_in_extra})"
                    print(warning_message)

                    # 关键：立即重置TTS状态和清空缓冲区以防止阻塞后续请求
                    print(f"[{current_time}] 由于意外的结束状态或错误响应，正在重置TTS状态... (TTS Msg ID: {self.current_tts_msg_id})")
                    self.audio_hex_buffer = []
                    self.is_processing_tts = False
                    self.current_tts_msg_id = None
                # else: # 理论上所有 status 和 base_status_code 的组合都应该被覆盖了
                #    print(f"[{current_time}] 未处理的 AudioPlay 状态组合: Status: {status}, BaseStatusCode: {base_status_code}. (Msg ID: {msg_id_in_extra})")


            # 原有的TTS音频数据响应逻辑 (data.audio, data.status)
            # 根据新的 AudioPlay 格式，这部分可能不再需要，或者需要调整
            # 为避免冲突，暂时注释掉或仔细检查其触发条件
            # elif "data" in msg_data and "audio" in msg_data["data"] and "status" in msg_data:
            #     # ... (旧的音频处理逻辑) ...
            #     pass # 这部分逻辑已被上面的 AudioPlay 处理取代或需要整合

            else:
                # 检查消息是否包含音频数据，如果包含则不显示完整消息
                if '"audio":' in message:
                    print(f"[{current_time}] 收到包含音频数据的其他类型JSON消息")
                else:
                    print(f"[{current_time}] 收到其他类型的JSON消息: {message}")

                # 检查是否包含 base_resp 和 audio 数据，即使不是 AudioPlay 类型
                if "data" in msg_data and "audio" in msg_data["data"] and "base_resp" in msg_data and self.is_processing_tts:
                    base_resp = msg_data.get("base_resp", {})
                    base_status_code = base_resp.get("status_code")
                    base_status_msg = base_resp.get("status_msg", "")

                    print(f"[{current_time}] 在非AudioPlay消息中检测到音频数据和base_resp: status_code={base_status_code}, status_msg='{base_status_msg}'")

                    # 检查是否是结束标志
                    if base_status_msg == "success" or base_status_code == 0:
                        print(f"[{current_time}] 在非AudioPlay消息中检测到TTS结束标志，尝试处理音频数据...")

                        # 获取音频数据
                        audio_data = msg_data.get("data", {})
                        hex_chunk = audio_data.get("audio")
                        status = audio_data.get("status")

                        # 如果是结束消息，处理当前消息中的音频数据但不保存文件
                        if base_status_msg == "success" or (status == 2 and base_status_code == 0):
                            try:
                                # 验证最后一个流中的音频数据
                                if not hex_chunk or not isinstance(hex_chunk, str):
                                    print(f"[{current_time}] 结束信号已收到，但最后一个消息中没有有效的音频数据。 (TTS Msg ID: {self.current_tts_msg_id})")
                                else:
                                    print(f"[{current_time}] 收到结束信号，验证最后一个流中的音频数据... (TTS Msg ID: {self.current_tts_msg_id})")
                                    try:
                                        # 验证数据有效性
                                        audio_bytes = bytes.fromhex(hex_chunk)
                                        print(f"[{current_time}] 最后一个流的音频数据有效 (总字节数: {len(audio_bytes)}, TTS Msg ID: {self.current_tts_msg_id})")

                                        # 将数据添加到缓冲区（不检查重复，保持顺序）
                                        self.audio_hex_buffer.append(hex_chunk)
                                        print(f"[{current_time}] 最后一个音频块已添加到缓冲区，当前缓冲区大小: {len(self.audio_hex_buffer)}")
                                    except ValueError as e:
                                        print(f"[{current_time}] 错误: 解码最后一个流的十六进制音频数据失败: {e} (TTS Msg ID: {self.current_tts_msg_id})")
                            except Exception as e:
                                print(f"[{current_time}] 处理音频数据时发生未知错误: {e} (TTS Msg ID: {self.current_tts_msg_id})")
                            finally:
                                print(f"[{current_time}] 正在重置TTS状态... (TTS Msg ID: {self.current_tts_msg_id})")
                                # 不清空audio_hex_buffer，因为hailuo_ws_server.py需要使用它
                                # self.audio_hex_buffer = []
                                self.is_processing_tts = False
                                self.current_tts_msg_id = None

                if not self.message_received.is_set():
                    self.message_received.set()

        except json.JSONDecodeError:
            print(f"[{current_time}] 收到非JSON格式文本消息")
            if not self.message_received.is_set(): # 确保任何消息都能确认初始连接
                self.message_received.set()
        except Exception as e:
            print(f"[{current_time}] 处理消息时发生未知错误: {e}")
            print(f"    处理消息时发生错误")
            # 发生未知错误时，也应该尝试重置TTS状态，防止阻塞
            if self.is_processing_tts:
                print(f"[{current_time}] 因处理消息错误，重置TTS状态。")
                self.is_processing_tts = False
                self.current_tts_msg_id = None
            if not self.message_received.is_set():
                self.message_received.set()

        self.last_message = message

    def on_error(self, ws, error):
        """WebSocket错误的回调"""
        print(f"WebSocket错误: {error}")
        # 确保在出错时也能触发连接事件，避免主线程卡死
        if not self.connection_event.is_set():
            self.connection_event.set()
        self.connected = False # 标记连接断开
        self.stop_threads.set() # 停止心跳

    def on_close(self, ws, close_status_code, close_msg):
        """WebSocket关闭的回调"""
        print(f"WebSocket连接已关闭: {close_status_code} - {close_msg}")
        self.connected = False
        self.stop_threads.set() # 通知心跳线程停止
        # 确保在关闭时也能触发连接事件，避免主线程卡死
        if not self.connection_event.is_set():
            self.connection_event.set()

    def test_connection(self):
        """测试WebSocket连接"""
        url = self.build_ws_url()

        # 构建完整的Cookie字符串
        cookie_str = f"sensorsdata2015jssdkchannel=%7B%22prop%22%3A%7B%22_sa_channel_landing_url%22%3A%22%22%7D%7D; _tt_enable_cookie=1; _ttp=my4b2j_PuYsMlqsi0hENTd_N1ew.tt.1; sensorsdata2015jssdkcross=%7B%22distinct_id%22%3A%22gKGmANgLn3d5%22%2C%22first_id%22%3A%2219467674a99581-057ec55af3b58d8-26011851-2073600-19467674a9a878%22%2C%22props%22%3A%7B%22%24latest_traffic_source_type%22%3A%22%E7%9B%B4%E6%8E%A5%E6%B5%81%E9%87%8F%22%2C%22%24latest_search_keyword%22%3A%22%E6%9C%AA%E5%8F%96%E5%88%B0%E5%80%BC_%E7%9B%B4%E6%8E%A5%E6%89%93%E5%BC%80%22%2C%22%24latest_referrer%22%3A%22%22%7D%2C%22identities%22%3A%22eyIkaWRlbnRpdHlfY29va2llX2lkIjoiMTk0Njc2NzRhOTk1ODEtMDU3ZWM1NWFmM2I1OGQ4LTI2MDExODUxLTIwNzM2MDAtMTk0Njc2NzRhOWE4NzgiLCIkaWRlbnRpdHlfbG9naW5faWQiOiJnS0dtQU5nTG4zZDUifQ%3D%3D%22%2C%22history_login_id%22%3A%7B%22name%22%3A%22%24identity_login_id%22%2C%22value%22%3A%22gKGmANgLn3d5%22%7D%2C%22%24device_id%22%3A%2219467674a99581-057ec55af3b58d8-26011851-2073600-19467674a9a878%22%7D; _token={self.token}"

        # WebSocket连接头 - 避免重复的头信息
        headers = {
            # 不设置Upgrade和Connection，让websocket-client库自己处理
            "Origin": "https://minimaxi.com",
            "Cache-Control": "no-cache",
            "Accept-Language": "de-DE,de;q=0.9,zh-CN;q=0.8,zh;q=0.7,en-US;q=0.6,en;q=0.5,zh-TW;q=0.4,fr;q=0.3",
            "Pragma": "no-cache",
            "Cookie": cookie_str,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
            # 不设置Sec-WebSocket-*头，让websocket-client库自己处理
        }

        print(f"正在连接到: {url}")
        print(f"使用头信息: {headers}")

        # 创建WebSocket连接
        ws = websocket.WebSocketApp(
            url,
            header=headers,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )

        # 启动WebSocket连接
        ws_thread = threading.Thread(target=ws.run_forever)
        ws_thread.daemon = True
        ws_thread.start()

        # 等待连接建立 (on_open 会设置 connection_event)
        if not self.connection_event.wait(timeout=10):
            print("连接超时")
            self.stop_threads.set() # 确保在超时时也尝试停止任何可能已启动的线程
            # 尝试关闭可能已部分启动的ws
            if ws:
                try: ws.close()
                except: pass
            return False

        # 如果连接成功，再等待第一条消息 (on_message 会设置 message_received)
        if self.connected:
            if not self.message_received.wait(timeout=10):
                print("初始连接后10秒内未收到任何消息 (这可能是正常的，将依赖心跳机制)")
        else:
             # 如果 connection_event 被设置但 self.connected 仍然是 False (可能由 on_error 或 on_close 设置)
             print("连接事件已触发，但连接状态为失败。")
             return False

        # 连接已建立，心跳线程已启动（在on_open中）
        # 此方法不再负责关闭连接，而是返回连接状态
        # 连接的保持由 ws_thread (运行 run_forever) 和 _heartbeat_sender 线程负责
        return self.connected

    def stop_connection(self):
        """优雅地停止WebSocket连接和相关线程"""
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 正在请求停止连接...")
        self.stop_threads.set() # 信号给所有线程停止

        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 等待心跳线程停止...")
            self.heartbeat_thread.join(timeout=2) # 缩短等待时间
            if self.heartbeat_thread.is_alive():
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 心跳线程未在2秒内停止。")
            else:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 心跳线程已成功停止。")

        if self.ws:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 正在关闭WebSocket连接...")
            try:
                # 关闭 run_forever 循环需要一些技巧，直接 close 可能不够
                # 移除 skip_utf8_validation=True 参数
                self.ws.close() # 或者 self.ws.close(status=1000)
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] WebSocket close() 方法已调用。")
                # run_forever 线程应该会在 close 后退出，不需要显式 join ws_thread
            except Exception as e:
                print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 关闭WebSocket时发生错误: {e}")

        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 连接停止流程完成。")


    def send_tts_request(self, text, voice_id="266629239353481", speed=1.0, vol=1.0, pitch=0.0, model="speech-01-hd", emotion=None, language_boost="Auto"):
        """发送TTS请求到WebSocket"""
        if not self.ws or not self.connected:
            print("错误：WebSocket未连接，无法发送TTS请求。")
            return
        if self.is_processing_tts: # 使用 is_processing_tts
            print(f"警告：上一个TTS请求 (Msg ID: {self.current_tts_msg_id}) 仍在处理中，请稍候...")
            return

        msg_id = str(uuid.uuid4())

        # 构建voice_setting字典
        voice_setting = {
            "speed": int(speed) if isinstance(speed, float) and speed.is_integer() else speed,
            "vol": int(vol) if isinstance(vol, float) and vol.is_integer() else vol,
            "pitch": int(pitch) if isinstance(pitch, float) and pitch.is_integer() else pitch,
            "voice_id": voice_id
        }

        # 如果提供了emotion参数，添加到voice_setting中
        if emotion:
            voice_setting["emotion"] = emotion

        # 打印language_boost参数，便于调试
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 使用language_boost: {language_boost}")

        payload = {
            "payload": {
                "model": model,
                "text": text,
                "voice_setting": voice_setting,
                "audio_setting": {}, # 保持为空，使用默认值
                "effects": { # 保持默认值
                    "deepen_lighten": 0,
                    "stronger_softer": 0,
                    "nasal_crisp": 0,
                    "spacious_echo": False,
                    "lofi_telephone": False,
                    "robotic": False,
                    "auditorium_echo": False
                },
                "er_weights": [],
                "language_boost": language_boost, # 使用传入的language_boost参数
                "stream": True # 确保是流式传输
            },
            "msg_id": msg_id
        }

        try:
            request_json = json.dumps(payload)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 准备发送TTS请求 (Msg ID: {msg_id})")
            self.ws.send(request_json)
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 已发送TTS请求 (Msg ID: {msg_id}): {text}")

            # 重置所有相关状态
            self.audio_hex_buffer = [] # 清空音频数据缓冲区
            self.audio_buffer = io.BytesIO() # 重置二进制缓冲区
            self.is_processing_tts = True # 标记开始TTS处理
            self.current_tts_msg_id = msg_id # 存储当前TTS请求的msg_id

            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] TTS状态已重置，等待响应... (Msg ID: {msg_id})")
        except websocket.WebSocketConnectionClosedException:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 发送TTS请求失败：WebSocket连接已关闭。")
            self.connected = False
            self.stop_threads.set()
        except Exception as e:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 发送TTS请求时发生错误: {e}")
            self.is_processing_tts = False # 发送失败，重置状态
            self.current_tts_msg_id = None

    # _play_audio 函数已移除，因为音频现在保存到文件。







# 创建Flask应用
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True, allow_headers=["Content-Type", "Authorization", "Accept"], methods=["GET", "POST", "OPTIONS"])  # 启用跨域支持，允许所有来源和必要的头信息

# 添加一个处理OPTIONS请求的路由，用于跨域预检请求
@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    """处理OPTIONS请求，用于跨域预检请求"""
    response = jsonify({})
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,Accept')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
    return response

# 添加一个简单的测试路由，确保Flask应用能够正确处理POST请求
@app.route('/test', methods=['GET', 'POST'])
def test_endpoint():
    """测试路由，确保Flask应用能够正确处理POST请求"""
    if request.method == 'POST':
        return jsonify({"message": "POST请求成功", "data": request.json}), 200
    else:
        return jsonify({"message": "GET请求成功"}), 200

# 全局变量，存储WebSocket客户端实例
ws_client = None

# 从环境变量中获取token
token = os.getenv('token')  # 存储token，用于初始化WebSocket客户端

def initialize_ws_client(token_value):
    """初始化WebSocket客户端"""
    global ws_client, token
    token = token_value

    # 检查token是否有效
    if not token:
        print("错误：未提供有效的token，无法初始化WebSocket客户端")
        return False

    if ws_client is None or not ws_client.connected:
        print(f"初始化WebSocket客户端，使用token: {token[:10]}...")  # 只显示token的前10个字符，保护隐私
        ws_client = HailuoWSTest(token=token)
        success = ws_client.test_connection()
        if success:
            print("WebSocket客户端连接成功")
            return True
        else:
            print("WebSocket客户端连接失败")
            ws_client = None
            return False
    return True

@app.route('/v1/t2a_v2', methods=['GET', 'POST', 'OPTIONS'])
def tts_endpoint():
    """处理TTS请求的HTTP端点，适配官方API格式"""
    global ws_client

    # 检查WebSocket客户端是否已初始化
    if ws_client is None or not ws_client.connected:
        if not initialize_ws_client(token):
            return jsonify({"error": "WebSocket客户端未连接"}), 500

    # 处理OPTIONS请求
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,Accept')
        response.headers.add('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        return response

    # 获取请求数据
    try:
        # 获取URL参数中的GroupId，但不实际使用它
        group_id = request.args.get('GroupId', '')

        # 获取请求头中的Authorization，但不实际使用它
        auth_header = request.headers.get('Authorization', '')

        # 检查请求方法并获取数据
        if request.method == 'POST':
            if request.is_json:
                data = request.json
            else:
                # 如果不是JSON格式，尝试从表单数据获取
                data = request.form.to_dict()
                # 如果表单数据为空，尝试从请求体获取并解析为JSON
                if not data and request.data:
                    try:
                        data = json.loads(request.data.decode('utf-8'))
                    except:
                        data = {}
        else:  # GET请求
            # 从URL参数获取数据
            data = request.args.to_dict()

        # 如果data为None，初始化为空字典
        if data is None:
            data = {}

        # 打印接收到的数据，帮助调试
        print(f"接收到的请求数据: {data}")

        text = data.get('text', '')
        voice_setting = data.get('voice_setting', {})
        if isinstance(voice_setting, str):
            try:
                voice_setting = json.loads(voice_setting)
            except:
                voice_setting = {}

        voice_id = voice_setting.get('voice_id', '226869409853570') if isinstance(voice_setting, dict) else '226869409853570'
        speed = voice_setting.get('speed', 1.0) if isinstance(voice_setting, dict) else 1.0
        vol = voice_setting.get('vol', 1.0) if isinstance(voice_setting, dict) else 1.0
        pitch = voice_setting.get('pitch', 0.0) if isinstance(voice_setting, dict) else 0.0

        # 检查是否有emotion或emotio字段（处理可能的拼写错误）
        emotion = None
        if isinstance(voice_setting, dict):
            emotion = voice_setting.get('emotion')
            if emotion is None:
                emotion = voice_setting.get('emotio')  # 处理可能的拼写错误
        model = data.get('model', 'speech-01-hd')
        stream = data.get('stream', True)

        # 提取language_boost参数
        language_boost = data.get('language_boost', 'Auto')

        # 尝试将stream转换为布尔值
        if isinstance(stream, str):
            stream = stream.lower() == 'true'

        # 打印请求信息，包括language_boost参数
        print(f"收到TTS请求: GroupId={group_id}, Auth={auth_header[:10] if auth_header else 'None'}..., 文本={text[:50]}... (流式: {stream}, language_boost: {language_boost})")

        if not stream:
            # 非流式请求处理
            # 清空之前的缓冲区
            ws_client.audio_hex_buffer = []

            # 发送请求到WebSocket
            ws_client.send_tts_request(text, voice_id, speed, vol, pitch, model, emotion=emotion, language_boost=language_boost)

            # 等待处理完成
            max_wait = 30  # 最多等待30秒
            start_time = time.time()
            while ws_client.is_processing_tts and time.time() - start_time < max_wait:
                time.sleep(0.1)

            # 检查是否收集到了音频数据
            if ws_client.audio_hex_buffer:
                try:
                    # 合并所有音频块
                    all_audio_hex = ""
                    for hex_chunk in ws_client.audio_hex_buffer:
                        all_audio_hex += hex_chunk

                    # 构造响应，适配官方API格式
                    response = {
                        "data": {
                            "audio": all_audio_hex,  # 这里包含音频数据，但日志中不会显示
                            "status": 2  # 非流式请求，状态为2表示完成
                        },
                        "base_resp": {
                            "status_code": 0,
                            "status_msg": "success"
                        }
                    }

                    # 清空缓冲区
                    audio_buffer = ws_client.audio_hex_buffer.copy()
                    ws_client.audio_hex_buffer = []
                    print(f"非流式请求完成，共合并 {len(audio_buffer)} 个音频块")

                    return jsonify(response)
                except Exception as e:
                    print(f"处理非流式响应时出错: {e}")

            # 如果没有有效响应，返回错误
            return jsonify({"error": "无法获取TTS响应"}), 500

        # 流式请求处理 - 实时转发每个音频块
        def generate():
            # 清空之前的缓冲区
            ws_client.audio_hex_buffer = []

            # 记录已发送的块数量
            sent_chunks_count = 0

            # 发送请求到WebSocket
            print(f"发送TTS请求到WebSocket服务...")
            ws_client.send_tts_request(text, voice_id, speed, vol, pitch, model, emotion=emotion, language_boost=language_boost)

            # 等待处理开始
            wait_start = time.time()
            while not ws_client.is_processing_tts:
                time.sleep(0.05)  # 减少等待时间，更快响应
                # 如果等待超过5秒，可能出现问题
                if time.time() - wait_start > 5:
                    print(f"警告: 等待TTS处理开始超时")
                    break

            print(f"TTS处理已开始，开始实时转发音频块...")

            # 最多等待60秒
            max_wait_time = 60
            start_wait_time = time.time()
            last_activity_time = start_wait_time

            # 持续监听并实时转发音频块
            while time.time() - start_wait_time < max_wait_time:
                current_buffer_size = len(ws_client.audio_hex_buffer)

                # 如果有新的音频块，立即转发
                if current_buffer_size > sent_chunks_count:
                    # 发送所有新的音频块
                    for i in range(sent_chunks_count, current_buffer_size):
                        hex_chunk = ws_client.audio_hex_buffer[i]

                        # 判断是否是最后一块（仅当处理已结束且是当前最后一块时）
                        is_last_chunk = (not ws_client.is_processing_tts and i == current_buffer_size - 1)

                        # 构造与官方API相同格式的响应
                        response = {
                            "data": {
                                "audio": hex_chunk,  # 这里包含音频数据，但日志中不会显示
                                "status": 2 if is_last_chunk else 1  # 最后一块状态为2
                            },
                            "base_resp": {
                                "status_code": 0,
                                "status_msg": "success" if is_last_chunk else ""
                            }
                        }

                        print(f"实时发送音频块 {i+1}/{current_buffer_size} (最后一块: {is_last_chunk})")
                        # 直接发送JSON字符串，不添加data:前缀
                        # 不在日志中显示响应内容，因为它包含音频数据
                        yield f"{json.dumps(response)}\n\n"

                        # 更新已发送的块数量
                        sent_chunks_count = i + 1
                        last_activity_time = time.time()

                # 检查是否应该结束循环
                if not ws_client.is_processing_tts:
                    # 如果处理已结束且所有块都已发送，等待一小段时间确保没有新块，然后退出
                    if sent_chunks_count >= len(ws_client.audio_hex_buffer):
                        if time.time() - last_activity_time > 0.5:  # 等待0.5秒确保没有新块
                            print(f"TTS处理已完成，所有音频块已发送")
                            break

                # 短暂休眠，减少CPU使用但保持响应性
                time.sleep(0.02)

            # 检查是否有未发送的块（以防万一）
            final_buffer_size = len(ws_client.audio_hex_buffer)
            if sent_chunks_count < final_buffer_size:
                print(f"发现 {final_buffer_size - sent_chunks_count} 个未发送的音频块，立即发送")

                # 发送剩余的块
                for i in range(sent_chunks_count, final_buffer_size):
                    hex_chunk = ws_client.audio_hex_buffer[i]
                    is_last_chunk = (i == final_buffer_size - 1)

                    response = {
                        "data": {
                            "audio": hex_chunk,  # 这里包含音频数据，但日志中不会显示
                            "status": 2 if is_last_chunk else 1
                        },
                        "base_resp": {
                            "status_code": 0,
                            "status_msg": "success" if is_last_chunk else ""
                        }
                    }

                    print(f"发送剩余音频块 {i+1}/{final_buffer_size} (最后一块: {is_last_chunk})")
                    # 直接发送JSON字符串，不添加data:前缀
                    # 不在日志中显示响应内容，因为它包含音频数据
                    yield f"{json.dumps(response)}\n\n"

            # 请求完成后清空缓冲区
            total_sent = max(sent_chunks_count, final_buffer_size)
            ws_client.audio_hex_buffer = []
            print(f"流式请求完成，共发送 {total_sent} 个音频块")

        return Response(generate(), mimetype='text/event-stream')

    except Exception as e:
        print(f"处理TTS请求时出错: {e}")
        return jsonify({"error": str(e)}), 500

def run_server(port=3002, token_value=None):
    """运行HTTP服务器，默认端口3002与官方API保持一致"""
    global token
    token = token_value

    # 如果提供了token，尝试初始化WebSocket客户端
    if token:
        initialize_ws_client(token)

    print(f"启动HTTP服务器，监听端口 {port}...")
    print(f"服务器已适配官方API格式，可通过 http://localhost:{port}/v1/t2a_v2 访问")
    print(f"可以通过 http://localhost:{port}/test 测试POST请求")

    # 设置Flask应用的配置
    app.config['JSON_AS_ASCII'] = False  # 确保JSON响应中的中文字符不会被转义
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False  # 禁用JSON响应的美化输出

    # 不再需要使用add_url_rule添加路由，因为我们已经使用装饰器添加了路由

    # 启动Flask应用
    app.run(host='0.0.0.0', port=port, debug=True, threaded=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Hailuo AI TTS WebSocket服务器 (适配官方API格式)")
    parser.add_argument("--token", required=False, help="Hailuo AI的认证Token，如不提供则从.env文件中读取")
    parser.add_argument("--port", type=int, default=3002, help="HTTP服务器端口，默认3002与官方API保持一致")

    args = parser.parse_args()

    # 优先使用命令行参数中的token，如果没有则使用环境变量中的token
    cmd_token = args.token
    env_token = token

    if cmd_token:
        # 使用命令行参数中的token
        print("使用命令行参数中的token")
        final_token = cmd_token
    elif env_token:
        # 使用环境变量中的token
        print("使用.env文件中的token")
        final_token = env_token
    else:
        # 没有提供token
        print("错误：未提供token，请在命令行参数中使用--token指定，或在.env文件中设置token")
        exit(1)

    run_server(port=args.port, token_value=final_token)
