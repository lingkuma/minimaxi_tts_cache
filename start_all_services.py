#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
启动所有服务的脚本
同时启动TTS缓存服务器和代理服务器
"""

import os
import sys
import argparse
import subprocess
import time
import threading

def run_tts_cache_server(port=3001, use_https=True, cert_file=None, key_file=None):
    """运行TTS缓存服务器"""
    cmd = [sys.executable, "live_chche/local_live_cache_cn.py", "--port", str(port)]
    
    if use_https:
        cmd.append("--https")
        
        if cert_file:
            cmd.extend(["--cert", cert_file])
        
        if key_file:
            cmd.extend(["--key", key_file])
    
    print(f"启动TTS缓存服务器: {' '.join(cmd)}")
    
    # 使用subprocess启动进程
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    
    # 实时输出日志
    prefix = "[TTS缓存] "
    for line in process.stdout:
        print(f"{prefix}{line.rstrip()}")
    
    # 等待进程结束
    process.wait()
    print(f"{prefix}服务已停止，返回码: {process.returncode}")


def run_proxy_server(port=3003, use_https=True, cert_file=None, key_file=None):
    """运行代理服务器"""
    cmd = [sys.executable, "https_proxy_server.py", "--port", str(port)]
    
    if not use_https:
        cmd.append("--http")
        
    if cert_file:
        cmd.extend(["--cert", cert_file])
    
    if key_file:
        cmd.extend(["--key", key_file])
    
    print(f"启动代理服务器: {' '.join(cmd)}")
    
    # 使用subprocess启动进程
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1
    )
    
    # 实时输出日志
    prefix = "[代理服务] "
    for line in process.stdout:
        print(f"{prefix}{line.rstrip()}")
    
    # 等待进程结束
    process.wait()
    print(f"{prefix}服务已停止，返回码: {process.returncode}")


if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="启动所有服务")
    parser.add_argument("--tts-port", type=int, default=3001, help="TTS缓存服务器端口，默认3001")
    parser.add_argument("--proxy-port", type=int, default=3003, help="代理服务器端口，默认3003")
    parser.add_argument("--http", action="store_true", help="使用HTTP而非HTTPS")
    parser.add_argument("--cert", type=str, help="SSL证书文件路径")
    parser.add_argument("--key", type=str, help="SSL私钥文件路径")
    
    args = parser.parse_args()
    
    # 创建线程启动服务
    tts_thread = threading.Thread(
        target=run_tts_cache_server,
        args=(args.tts_port, not args.http, args.cert, args.key),
        daemon=True
    )
    
    proxy_thread = threading.Thread(
        target=run_proxy_server,
        args=(args.proxy_port, not args.http, args.cert, args.key),
        daemon=True
    )
    
    # 启动线程
    tts_thread.start()
    time.sleep(2)  # 等待TTS服务器启动
    proxy_thread.start()
    
    # 等待线程结束（实际上不会结束，除非按Ctrl+C）
    try:
        while tts_thread.is_alive() and proxy_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n收到中断信号，正在退出...")
        sys.exit(0)
