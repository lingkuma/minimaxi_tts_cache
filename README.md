
德语单词音频缓存，目前有23,000个单词的音频缓存,会逐渐随着我的阅读增加。
目前使用的是minimaxi的API，需要注册账号，然后获取api key。后续可能考虑openai等其他api。

german word audio cache, currently has 23,000 word audio cache, will gradually increase with my reading.


一些Minimaxi德语音频Bug
- im 请换成Im
- ni请换成nI BildungsnIveaus
- Gy请换成GY GYmnasium


---

## 功能说明
- 支持多语言TTS缓存
- 使用Minimaxi API进行TTS转换
- 本地缓存音频文件，避免重复请求
- 支持多线程并发下载
- 提供本地HTTP/HTTPS服务用于音频访问
- 支持SSL加密连接

## 使用方法

1. 配置环境变量
   - 创建 `.env` 文件
   - 设置 `group_id` 和 `api_key`

2. 准备单词列表
   - 创建 `listtest.txt` 文件
   - 每行一个单词

3. 运行缓存程序
   ```bash
   python local_file_to_cache.py
   ```

4. 启动本地服务
   ```bash
   # HTTP服务
   python live_chche/local_live_cache_cn.py

   # 或启动HTTPS服务
   python live_chche/local_live_cache_cn.py --https
   ```

5. 访问音频
   ```
   # HTTP访问
   http://localhost:3001/langid=de&txt=你的单词

   # HTTPS访问
   https://localhost:3001/langid=de&txt=你的单词
   ```

## 注意事项

- 确保网络连接稳定
- 建议使用3-5个线程进行下载
- 音频文件默认保存在 cache 目录
- 支持的语言参考 Minimaxi API 文档

## HTTPS支持

使用HTTPS需要安装额外的依赖：

```bash
pip install pyOpenSSL
```

详细的HTTPS配置说明请参考 [README_HTTPS.md](README_HTTPS.md)

### 生成自定义证书

可以使用提供的脚本生成自定义证书：

```bash
python generate_ssl_cert.py --cn your-ip-or-domain
```

### 测试HTTPS服务器

```bash
python test_https_server.py --url https://localhost:3001 --text "测试" --lang zh
```

## HTTPS代理服务器

系统还提供了一个HTTPS代理服务器，可以将HTTPS请求转发到HTTP服务。

### 启动代理服务器

```bash
python https_proxy_server.py
```

默认情况下，代理服务器在端口3003上运行，将请求从：
```
https://192.168.0.253:3003/api/tts?text=你的文本
```
转发到：
```
http://192.168.0.253:2333/api/tts?text=你的文本
```

### 测试代理服务器

```bash
python test_proxy_server.py --url https://localhost:3003 --text "测试"
```

### 同时启动所有服务

可以使用提供的脚本同时启动TTS缓存服务器和代理服务器：

```bash
python start_all_services.py
```
