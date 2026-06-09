import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


APP_NAME = "VS Translator Overlay"
ROOT = Path(__file__).resolve().parent
MAIN_PY = ROOT / "main.py"
ICON_PATH = ROOT / "app_icon.ico"
SHORTCUT_NAME = f"{APP_NAME}.lnk"


def find_pythonw():
    exe = Path(sys.executable).resolve()
    if exe.name.lower() == "python.exe":
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            return pythonw
    sibling = exe.with_name("pythonw.exe")
    return sibling if sibling.exists() else exe


def create_icon():
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Pixel/blocky original icon: dark chat panel, wooden sign, VS letters.
    draw.rounded_rectangle((22, 34, 226, 174), radius=12, fill=(18, 24, 31, 218), outline=(142, 162, 182, 160), width=4)
    draw.polygon([(72, 174), (106, 174), (78, 210)], fill=(18, 24, 31, 218), outline=(142, 162, 182, 160))
    draw.rectangle((46, 70, 202, 122), fill=(106, 68, 36, 255), outline=(58, 37, 22, 255), width=4)
    draw.rectangle((58, 82, 190, 110), fill=(145, 92, 45, 255))
    for x in (70, 118, 166):
        draw.line((x, 72, x + 12, 120), fill=(91, 55, 28, 180), width=3)

    try:
        font_big = ImageFont.truetype("segouib.ttf", 58)
        font_small = ImageFont.truetype("segouib.ttf", 28)
    except Exception:
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()

    draw.text((74, 132), "VS", font=font_big, fill=(254, 197, 0, 255), stroke_width=2, stroke_fill=(36, 26, 10, 255))
    draw.text((86, 52), "RU", font=font_small, fill=(214, 214, 214, 255))
    draw.text((138, 52), "EN", font=font_small, fill=(214, 214, 214, 255))
    draw.line((126, 65, 134, 65), fill=(254, 197, 0, 255), width=4)
    draw.polygon([(134, 65), (126, 59), (126, 71)], fill=(254, 197, 0, 255))

    img.save(ICON_PATH, sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])


def desktop_path():
    script = "[Environment]::GetFolderPath('Desktop')"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return Path(result.stdout.strip())


def ps_quote(value):
    return str(value).replace("'", "''")


def create_shortcut():
    pythonw = find_pythonw()
    desktop = desktop_path()
    shortcut = desktop / SHORTCUT_NAME

    ps = f"""
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut('{ps_quote(shortcut)}')
    $shortcut.TargetPath = '{ps_quote(pythonw)}'
    $shortcut.Arguments = '"{ps_quote(MAIN_PY)}"'
    $shortcut.WorkingDirectory = '{ps_quote(ROOT)}'
    $shortcut.IconLocation = '{ps_quote(ICON_PATH)},0'
    $shortcut.WindowStyle = 1
    $shortcut.Save()
    """
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    return shortcut, pythonw


def main():
    if not MAIN_PY.exists():
        raise SystemExit(f"Missing {MAIN_PY}")
    create_icon()
    shortcut, pythonw = create_shortcut()
    print(f"Shortcut: {shortcut}")
    print(f"Target: {pythonw}")
    print(f"Arguments: \"{MAIN_PY}\"")
    print(f"WorkingDirectory: {ROOT}")
    print(f"Icon: {ICON_PATH},0")


if __name__ == "__main__":
    main()
