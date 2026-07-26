' 双击静默启动桌面待办插件（无黑框）
Set ws = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
ws.CurrentDirectory = dir

' 优先使用 pythonw 绝对路径，避免 vbs 环境 PATH 找不到 python 的情况
pyw = ws.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python314\pythonw.exe"
If Not fso.FileExists(pyw) Then
    ' 找不到绝对路径时回退到 PATH 中的 pythonw
    pyw = "pythonw"
End If

' 用 pythonw 无控制台窗口运行 PySide6 版本
ws.Run """" & pyw & """ """ & dir & "\todo_qt.py""", 0, False