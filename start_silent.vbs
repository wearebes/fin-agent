Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d D:\科研小作坊\fin-agent & C:\ProgramData\Anaconda3\python.exe -m fin_agent.bootstrap.cli api > finagent.log 2>&1", 0, False
