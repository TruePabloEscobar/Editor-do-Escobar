"""Native installer contract with a stub Python executable; no pip/network side effects."""

import json
import os
import shutil
import subprocess
from pathlib import Path


def test_separate_install_root_uses_its_python_and_editable_source(tmp_path):
    root = Path(__file__).resolve().parents[2]
    source = tmp_path / "Source With Spaces"
    shutil.copytree(root / "launcher", source / "launcher")
    shutil.copytree(root / "config", source / "config")
    shutil.copytree(
        root / "scripts", source / "scripts", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copyfile(root / "pyproject.toml", source / "pyproject.toml")
    fake = tmp_path / "python-stub.exe"
    log = tmp_path / "python-arguments.txt"
    code = r"""
using System;
using System.IO;
using System.Diagnostics;
public class StubPython {
 public static int Main(string[] args) {
  string log = Environment.GetEnvironmentVariable("EDE_STUB_LOG");
  File.AppendAllText(log, string.Join("|",args)+"\n");
  if(args.Length>1 && args[0]=="-c") {
   Console.WriteLine(args[1].Contains("struct") ? "3.11|64" : "3.11"); return 0;
  }
  if(args.Length>2 && args[0]=="-m" && args[1]=="venv") {
   string folder=Path.Combine(args[2],"Scripts"); Directory.CreateDirectory(folder);
   File.Copy(Process.GetCurrentProcess().MainModule.FileName,Path.Combine(folder,"python.exe"));
  }
  return 0;
 }
}
"""
    cs = tmp_path / "stub.cs"
    cs.write_text(code, encoding="utf-8")
    compile_script = tmp_path / "compile.ps1"
    compile_script.write_text(
        "param($Source,$Destination)\n"
        "Add-Type -TypeDefinition ([IO.File]::ReadAllText($Source)) "
        "-OutputAssembly $Destination -OutputType ConsoleApplication\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-File", str(compile_script), str(cs), str(fake)],
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    appdata = tmp_path / "appdata"
    install = tmp_path / "Installed Outside Source"
    installer = os.environ.get("EDE_INSTALL_SCRIPT_TEST", str(root / "scripts/install_windows.ps1"))
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            installer,
            "-SourceRoot",
            str(source),
            "-PythonPath",
            str(fake),
            "-InstallRoot",
            str(install),
            "-LauncherDestination",
            str(tmp_path / "Resolve Utility"),
            "-SkipEnvironmentPersistence",
        ],
        env={**os.environ, "APPDATA": str(appdata), "EDE_STUB_LOG": str(log)},
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    configuration = json.loads((appdata / "O Editor/launcher.json").read_text(encoding="utf-8"))
    assert (
        str(install / ".venv/Scripts/python.exe").lower()
        in json.dumps(configuration).replace("\\\\", "\\").lower()
    )
    assert "|-e|" in log.read_text(encoding="utf-8")
