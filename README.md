
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
- 提供本地HTTP服务用于音频访问

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
   python local_live_cache.py
   ```

5. 访问音频
   ```
   http://localhost:3001/langid=de&txt=你的单词
   ```

## 注意事项

- 确保网络连接稳定
- 建议使用3-5个线程进行下载
- 音频文件默认保存在 cache 目录
- 支持的语言参考 Minimaxi API 文档
