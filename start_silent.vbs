Option Explicit

Const SiteUrl = "http://127.0.0.1:8000"

Dim shell, projectRoot, mode, attempt
Set shell = CreateObject("WScript.Shell")
projectRoot = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
mode = ""
If WScript.Arguments.Count > 0 Then mode = LCase(WScript.Arguments(0))

Function IsReady()
    Dim request
    On Error Resume Next
    Set request = CreateObject("MSXML2.XMLHTTP.6.0")
    request.Open "GET", SiteUrl & "/healthz", False
    request.Send
    IsReady = (Err.Number = 0 And request.Status = 200)
    Err.Clear
    On Error GoTo 0
End Function

If mode = "check" Then
    If IsReady() Then WScript.Quit 0
    WScript.Quit 1
End If

If Not IsReady() Then
    shell.Run "cmd.exe /d /c """ & projectRoot & "\start_background.cmd""", 0, False
    For attempt = 1 To 40
        WScript.Sleep 500
        If IsReady() Then Exit For
    Next
End If

If Not IsReady() Then
    If mode = "open" Then
        MsgBox "FinAgent could not start. Check var\finagent.log.", 16, "FinAgent"
    End If
    WScript.Quit 1
End If

If mode = "open" Then shell.Run SiteUrl, 1, False
