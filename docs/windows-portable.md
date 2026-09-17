# Windows 免安装版

面向 Windows 10/11 x64。包内包含 Python 3.13.15、运行依赖、项目代码和构建后的网页。用户解压后运行 Start FinAgent.cmd，Stop FinAgent.cmd 用于关闭服务。它仍通过本机浏览器使用，行情和模型请求需要联网。

## 构建

在 Windows 上使用 64 位 Python 3.13 和 Node.js。先在 frontend 目录运行 npm install，再回到项目根目录执行：

```powershell
python scripts/build_portable.py
python scripts/check_portable.py
```

若 Node 不在 PATH 中，构建命令可增加 --node 参数指定 node.exe。构建脚本拒绝覆盖已有的 dist/FinAgent-Windows-x64.zip；重新打包前请将旧包移到别处。

脚本从 Python 官方下载嵌入式运行环境并校验 SHA-256，按 scripts/requirements-windows.txt 安装固定版本的依赖，完成前端检查和构建。jsonpath 只有源码发行包，由构建机生成纯 Python wheel，用户端无需编译。输出 ZIP、SHA256SUMS.txt 和供检查的解压目录。不要手动压缩整个开发目录。

## 运行与数据

- 运行环境只读取包内路径，不加载电脑上已有的 Python 包或 PYTHONPATH。
- 首次启动生成独立的账户签名密钥，存放在 var/auth-secret.txt。备份或升级时应复制整个 var 文件夹。
- 监听地址固定为 127.0.0.1，优先使用 8765 端口。端口被占用时自动选择空闲端口，浏览器由启动器打开。
- 重复启动同一个目录时复用已有服务；不同解压目录分别保存数据。
- 关闭入口使用本次运行的随机口令请求退出，不按端口或进程名称强制结束其他程序。
- 使用账户下的个人模型连接；旧版写入 .env 的系统密钥设置在此模式下禁用。停止服务会中断未完成的研究任务。
- 包中没有开发者的 .env、账户、报告、日志、模型密钥或本机 Codex 配置；第三方包的许可证和 Python 许可证随包保留。

## 验证与发布

check_portable.py 会从最终 ZIP 解压到带中文和空格的独立目录，清除 PATH 中的开发环境入口，检查包内导入、原生依赖、页面文件、账户注册与登录、重启、重复启动、端口占用和关闭鉴权。测试数据留在 tmp/portable-smoke-* 中供检查，不进入发布 ZIP。

发布前还应运行后端测试。隔离路径测试不等同于在所有 Windows 电脑上验收；Windows 安全策略、浏览器设置和外部数据源仍可能影响使用。

通过检查后，将 ZIP 和 SHA256SUMS.txt 上传为 GitHub Release 附件。README 的下载入口指向最新正式 Release 的 FinAgent-Windows-x64.zip，不能以 GitHub 自动生成的 Source code (zip) 代替。

运行环境来源：[Python 3.13.15](https://www.python.org/downloads/release/python-31315/)；分发方式参考：[Python 嵌入式包说明](https://docs.python.org/3.13/using/windows.html#the-embeddable-package)。
