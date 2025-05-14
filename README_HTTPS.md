# TTS缓存服务器 HTTPS 支持

本文档说明如何启用TTS缓存服务器的HTTPS支持。

## 安装依赖

要使用HTTPS功能，需要安装额外的依赖：

```bash
pip install pyOpenSSL
```

## 启动HTTPS服务器

### 使用自动生成的自签名证书

最简单的方式是让服务器自动生成自签名证书：

```bash
python live_chche/local_live_cache_cn.py --https
```

这将在当前目录下生成`server.crt`和`server.key`文件，并启动HTTPS服务器。

### 使用自定义证书

如果您有自己的SSL证书，可以通过以下方式指定：

```bash
python live_chche/local_live_cache_cn.py --https --cert your_cert.crt --key your_key.key
```

### 指定端口

默认情况下，服务器使用3001端口。您可以通过`--port`参数指定不同的端口：

```bash
python live_chche/local_live_cache_cn.py --https --port 3443
```

## 测试HTTPS服务器

可以使用提供的测试脚本测试HTTPS服务器：

```bash
python test_https_server.py --url https://localhost:3001 --text "测试" --lang zh
```

注意：由于使用的是自签名证书，测试脚本默认会忽略SSL证书验证。如果您想验证证书，可以添加`--verify`参数。

## 客户端使用

当使用HTTPS服务器时，客户端需要将URL从`http://`更改为`https://`。例如：

```
https://localhost:3001/langid=zh&txt=测试
```

## 注意事项

1. 自签名证书会导致浏览器显示安全警告，这是正常的。在生产环境中，建议使用由受信任的证书颁发机构签发的证书。

2. 如果您在局域网中使用，请确保在证书的Common Name (CN)中使用服务器的IP地址或主机名，而不是`localhost`。

3. 自签名证书的默认有效期为10年。
