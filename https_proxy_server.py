#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
HTTPS代理服务器，将HTTPS请求转发到HTTP服务
支持使用与TTS缓存服务器相同的SSL证书
"""

import os
import sys
import json
import argparse
import ssl
import socket
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import re

# 导入证书生成函数
try:
    from live_chche.local_live_cache_cn import generate_self_signed_cert, HTTPSServer
except ImportError:
    # 如果无法导入，定义自己的函数
    def generate_self_signed_cert(cert_file="server.crt", key_file="server.key", force_new=False):
        """生成自签名SSL证书"""
        from OpenSSL import crypto
        import socket
        
        # 检查证书文件是否已存在
        if os.path.exists(cert_file) and os.path.exists(key_file) and not force_new:
            print(f"证书文件已存在: {cert_file}, {key_file}")
            print("如需重新生成证书，请删除现有证书文件或使用--force-new-cert参数")
            return cert_file, key_file
        
        print("生成自签名SSL证书...")
        
        # 获取本机IP地址
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        
        # 创建密钥对
        k = crypto.PKey()
        k.generate_key(crypto.TYPE_RSA, 2048)
        
        # 创建自签名证书
        cert = crypto.X509()
        cert.get_subject().C = "CN"
        cert.get_subject().ST = "State"
        cert.get_subject().L = "City"
        cert.get_subject().O = "Organization"
        cert.get_subject().OU = "Organizational Unit"
        
        # 使用IP地址作为Common Name
        cert.get_subject().CN = local_ip
        print(f"使用IP地址作为证书CN: {local_ip}")
        
        cert.set_serial_number(1000)
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(10*365*24*60*60)  # 10年有效期
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(k)
        
        # 添加subjectAltName扩展，包含localhost和IP地址
        alt_names = [
            f"DNS:localhost",
            f"DNS:{hostname}",
            f"IP:127.0.0.1",
            f"IP:{local_ip}"
        ]
        
        # 尝试添加192.168.0.253
        if local_ip != "192.168.0.253":
            alt_names.append("IP:192.168.0.253")
        
        san_extension = crypto.X509Extension(
            b"subjectAltName",
            False,
            ", ".join(alt_names).encode()
        )
        cert.add_extensions([san_extension])
        
        cert.sign(k, 'sha256')
        
        # 保存证书和私钥
        with open(cert_file, "wb") as f:
            f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
        
        with open(key_file, "wb") as f:
            f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, k))
        
        print(f"已生成自签名SSL证书: {cert_file}")
        print(f"已添加以下备用名称: {', '.join(alt_names)}")
        return cert_file, key_file

    class HTTPSServer(HTTPServer):
        """支持HTTPS的HTTP服务器"""
        def __init__(self, server_address, RequestHandlerClass, certfile, keyfile, ssl_version=ssl.PROTOCOL_TLS_SERVER):
            HTTPServer.__init__(self, server_address, RequestHandlerClass)
            
            # 创建SSL上下文
            self.ssl_context = ssl.SSLContext(ssl_version)
            self.ssl_context.load_cert_chain(certfile=certfile, keyfile=keyfile)
            
            # 包装socket
            self.socket = self.ssl_context.wrap_socket(self.socket, server_side=True)


class ProxyRequestHandler(BaseHTTPRequestHandler):
    """代理请求处理器，将HTTPS请求转发到HTTP服务"""
    
    def do_GET(self):
        """处理GET请求"""
        try:
            # 解析请求路径
            if self.path.startswith('/api/tts'):
                # 提取查询参数
                parsed_url = urllib.parse.urlparse(self.path)
                query_params = urllib.parse.parse_qs(parsed_url.query)
                
                # 获取text参数
                if 'text' in query_params:
                    text = query_params['text'][0]
                    print(f"收到TTS请求: text={text}")
                    
                    # 构建目标URL
                    target_url = f"http://192.168.0.253:2333/api/tts?text={urllib.parse.quote(text)}"
                    print(f"转发到: {target_url}")
                    
                    # 发送请求到目标服务器
                    response = requests.get(target_url)
                    
                    # 返回响应
                    self.send_response(response.status_code)
                    
                    # 复制所有响应头
                    for header, value in response.headers.items():
                        if header.lower() not in ['transfer-encoding', 'connection']:
                            self.send_header(header, value)
                    
                    # 设置CORS头
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
                    self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                    
                    self.end_headers()
                    
                    # 写入响应内容
                    self.wfile.write(response.content)
                else:
                    # 缺少text参数
                    self.send_response(400)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b"Missing 'text' parameter")
            else:
                # 不支持的路径
                self.send_response(404)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Not Found")
        except Exception as e:
            # 处理异常
            print(f"处理请求时出错: {str(e)}")
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(f"Server Error: {str(e)}".encode('utf-8'))
    
    def do_OPTIONS(self):
        """处理OPTIONS请求，用于CORS预检"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Max-Age', '86400')  # 24小时
        self.end_headers()


def run_server(port=3003, use_https=True, cert_file=None, key_file=None, force_new_cert=False):
    """运行代理服务器"""
    server_address = ('', port)
    
    if use_https:
        # 如果没有提供证书文件，使用默认证书
        if not cert_file or not key_file:
            cert_file, key_file = generate_self_signed_cert(force_new=force_new_cert)
        
        # 创建HTTPS服务器
        httpd = HTTPSServer(server_address, ProxyRequestHandler, cert_file, key_file)
        protocol = "HTTPS"
        
        # 打印访问信息
        import socket
        hostname = socket.gethostname()
        local_ip = socket.gethostbyname(hostname)
        print(f"HTTPS代理服务器已启动，可通过以下地址访问:")
        print(f"https://localhost:{port}/api/tts?text=test")
        print(f"https://127.0.0.1:{port}/api/tts?text=test")
        print(f"https://{hostname}:{port}/api/tts?text=test")
        print(f"https://{local_ip}:{port}/api/tts?text=test")
        if local_ip != "192.168.0.253":
            print(f"https://192.168.0.253:{port}/api/tts?text=test (如果此IP可用)")
    else:
        # 创建普通HTTP服务器
        httpd = HTTPServer(server_address, ProxyRequestHandler)
        protocol = "HTTP"
        print(f"HTTP代理服务器已启动，可通过 http://localhost:{port}/api/tts?text=test 访问")
    
    print(f"启动代理服务器 ({protocol})，监听端口 {port}...")
    print(f"将请求转发到: http://192.168.0.253:2333/api/tts")
    httpd.serve_forever()


if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="HTTPS代理服务器")
    parser.add_argument("--port", type=int, default=3003, help="服务器端口，默认3003")
    parser.add_argument("--http", action="store_true", help="使用HTTP而非HTTPS")
    parser.add_argument("--cert", type=str, help="SSL证书文件路径")
    parser.add_argument("--key", type=str, help="SSL私钥文件路径")
    parser.add_argument("--force-new-cert", action="store_true", help="强制重新生成SSL证书")
    
    args = parser.parse_args()
    
    # 启动服务器
    run_server(
        port=args.port,
        use_https=not args.http,
        cert_file=args.cert,
        key_file=args.key,
        force_new_cert=args.force_new_cert
    )
