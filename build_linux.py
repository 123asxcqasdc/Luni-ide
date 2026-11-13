#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_linux.py — сборка Luni IDE под Linux: Debian-пакет (.deb) и AppImage.

Linux-аналог build.py (тот собирает Windows-версию через PyInstaller + Inno Setup).
Здесь то же приложение упаковывается в:

  * AppDir  — FHS-дерево, из которого appimagetool делает один файл .AppImage;
  * .deb    — пакет для Debian/Ubuntu/Mint: /opt/luni-ide + ярлык, иконки, metainfo;
  * AppImage — переносимый файл, запускается двойным кликом без установки.

Настольные файлы, иконки и AppStream-метаданные берутся из packaging/.

БЫСТРЫЙ СТАРТ
    python3 build_linux.py appdir          # только дерево приложения
    python3 build_linux.py deb             # dist/luni-ide_<версия>_amd64.deb
    python3 build_linux.py appimage        # dist/Luni-IDE-<версия>-x86_64.AppImage
    python3 build_linux.py all             # и .deb, и AppImage

ПОЛЕЗНЫЕ ФЛАГИ
    --with-toolchain   вшить arduino-cli + ядро ESP32 (офлайн «из коробки»,
                       пакет становится на сотни МБ больше)
    --no-frozen        не использовать PyInstaller: положить в пакет исходники
                       и запускать системным python3 (нужны python3-flask,
                       python3-serial)
    --strict           считать отсутствие appimagetool ошибкой (для CI)

ЗАВИСИМОСТИ СБОРКИ
    * Python 3.9+ и pip-пакеты: pyinstaller, flask, pyserial
        python3 -m pip install --upgrade pyinstaller flask pyserial
    * dpkg-deb (пакет dpkg) — для .deb;
    * appimagetool — для .AppImage (см. README-LINUX.md). Без него сборка
      всё равно оставит готовый AppDir и архив dist/*.AppDir.tar.gz.

ЗАМЕЧАНИЕ ПРО pywebview
    На Linux pywebview требует PyGObject + WebKitGTK, которые проблематично
    вшивать в переносимый бандл. Поэтому Linux-сборки открывают интерфейс в
    системном браузере (как и режим разработки). Если pywebview установлен в
    системе и запускается из исходников, IDE сама откроет нативное окно.
"""

import argparse
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import sysconfig

HERE = os.path.dirname(os.path.abspath(__file__))

APP_ID     = "luni-ide"                      # имя пакета, .desktop, иконок
APP_TITLE  = "Luni IDE"                      # человекочитаемое имя
APP_BIN    = "Luni-IDE"                      # исполняемый файл в бандле
PROJECT    = "https://github.com/123asxcqasdc/Luni-ide"
MAINTAINER = os.environ.get("LUNI_MAINTAINER", "Luni IDE <noreply@localhost>")

BUILD_DIR    = os.path.join(HERE, "build", "linux")     # рабочие деревья
DIST_DIR     = os.path.join(HERE, "dist")               # готовые артефакты
PACKAGING    = os.path.join(HERE, "packaging")
VENDOR_DIR   = os.path.join(PACKAGING, "vendor")        # загруженный appimagetool

# Что кладём рядом с приложением (server.py сам раздаёт эти файлы).
RES_FILES = ["index.html", "icon.png", "icon.ico", "student-README.txt",
             "README-LINUX.md", "setup_toolchain_linux.py"]
RES_DIRS  = ["vendor", "sim", "image"]

ICON_SIZES = [32, 48, 64, 128, 256]


# --------------------------------------------------------------------------- #
# Утилиты
# --------------------------------------------------------------------------- #
def log(msg):
    print("[build-linux] " + msg, flush=True)


def run(cmd, cwd=None, env=None, check=True):
    log("> " + " ".join(str(c) for c in cmd))
    subprocess.run(cmd, cwd=cwd, env=env, check=check)


def read_version():
    """Единый источник версии — VERSION в server.py."""
    with open(os.path.join(HERE, "server.py"), encoding="utf-8") as f:
        m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', f.read(), re.M)
    return m.group(1) if m else "0.0.0"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(256 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_checksum(path):
    """Рядом с артефактом кладём .sha256 — как для payload в build.py."""
    digest = sha256_file(path)
    with open(path + ".sha256", "w", encoding="utf-8") as f:
        f.write(digest + "  " + os.path.basename(path) + "\n")
    log("sha256 " + os.path.basename(path) + ": " + digest)
    return digest


def dpkg_arch():
    """Архитектура Debian (amd64/arm64/armhf/i386)."""
    if shutil.which("dpkg"):
        out = subprocess.run(["dpkg", "--print-architecture"],
                             capture_output=True, text=True, check=False)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    machine = platform.machine().lower()
    return {
        "x86_64": "amd64", "amd64": "amd64",
        "aarch64": "arm64", "arm64": "arm64",
        "armv7l": "armhf", "armv6l": "armhf",
        "i686": "i386", "i386": "i386",
    }.get(machine, machine)


def appimage_arch():
    """Архитектура в терминах AppImage (ARCH=...)."""
    machine = platform.machine().lower()
    return {
        "x86_64": "x86_64", "amd64": "x86_64",
        "aarch64": "aarch64", "arm64": "aarch64",
        "armv7l": "armhf", "armv6l": "armhf",
    }.get(machine, machine)


def have_module(name):
    r = subprocess.run([sys.executable, "-c", "import " + name],
                       capture_output=True, text=True, check=False)
    return r.returncode == 0


def pyinstaller_problem():
    """Почему нельзя собрать замороженный бандл (или None, если можно).

    PyInstaller на Linux требует общую библиотеку libpython: в Debian/Ubuntu
    она ставится отдельным пакетом (libpython3.11), которого может не быть.
    """
    if not have_module("PyInstaller"):
        return "PyInstaller не установлен (pip install pyinstaller)"
    lib = sysconfig.get_config_var("LDLIBRARY")
    libdir = sysconfig.get_config_var("LIBDIR") or ""
    if lib and not os.path.exists(os.path.join(libdir, lib)):
        pkg = "libpython%d.%d" % sys.version_info[:2]
        return ("не найдена общая библиотека Python (" + str(lib) + "): "
                "sudo apt install " + pkg)
    return None


def desktop_text(exec_name, try_exec=None):
    """Текст .desktop из шаблона; TryExec= нужен только для системной установки
    (.deb). В AppImage этого файла нет в PATH, поэтому строку убираем."""
    text = render(os.path.join(PACKAGING, "luni-ide.desktop.in"),
                  {"EXEC": exec_name, "TRY_EXEC": try_exec or exec_name})
    if not try_exec:
        text = "\n".join(line for line in text.splitlines()
                         if not line.startswith("TryExec="))
    if not text.endswith("\n"):
        text += "\n"
    return text


def render(template_path, values):
    with open(template_path, encoding="utf-8") as f:
        text = f.read()
    for key, val in values.items():
        text = text.replace("@" + key + "@", val)
    return text


def write_file(path, text, mode=0o644):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(path, mode)


def copy_tree_contents(src, dst):
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        s = os.path.join(src, name)
        d = os.path.join(dst, name)
        if os.path.isdir(s) and not os.path.islink(s):
            shutil.copytree(s, d, symlinks=True, dirs_exist_ok=True)
        else:
            if os.path.lexists(d):
                os.remove(d)
            shutil.copy2(s, d, follow_symlinks=False)


def copy_resources(dst):
    """index.html, иконки, vendor/ и т.д. — рядом с исполняемым файлом."""
    for name in RES_FILES:
        src = os.path.join(HERE, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dst, name))
        else:
            log("  (пропуск, нет файла) " + name)
    for name in RES_DIRS:
        src = os.path.join(HERE, name)
        if os.path.isdir(src):
            target = os.path.join(dst, name)
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(src, target, symlinks=True)
        else:
            log("  (пропуск, нет папки) " + name)
    # портативный режим: если рядом есть updates/, bootstrap.py (Windows)
    # или base-version.txt, Linux-версии это не мешает.
    with open(os.path.join(dst, "base-version.txt"), "w", encoding="utf-8") as f:
        f.write(read_version())


def icons():
    """Список (размер, путь) готовых PNG-иконок из packaging/icons."""
    found = []
    for size in ICON_SIZES:
        p = os.path.join(PACKAGING, "icons", f"{APP_ID}-{size}.png")
        if os.path.exists(p):
            found.append((size, p))
    if not found:
        fallback = os.path.join(HERE, "icon.png")
        if os.path.exists(fallback):
            log("  (иконки не найдены в packaging/icons — беру icon.png 256×256)")
            found.append((256, fallback))
    return found


# --------------------------------------------------------------------------- #
# 1. Бандл приложения
# --------------------------------------------------------------------------- #
def build_bundle(frozen=True):
    """Собирает каталог приложения в build/linux/bundle/Luni-IDE."""
    bundle_root = os.path.join(BUILD_DIR, "bundle")
    target = os.path.join(bundle_root, APP_BIN)
    shutil.rmtree(bundle_root, ignore_errors=True)
    os.makedirs(bundle_root, exist_ok=True)

    problem = pyinstaller_problem() if frozen else None
    if frozen and problem:
        log("PyInstaller недоступен: " + problem)
        log("собираю без него (--no-frozen): в пакет пойдут исходники,")
        log("а запуск будет через системный python3 (python3-flask, python3-serial).")
        frozen = False

    if not frozen:
        log("режим без PyInstaller: в пакет пойдут исходники")
        for name in ("server.py", "icon.png", "icon.ico",
                     "student-README.txt", "README-LINUX.md", "requirements.txt",
                     "setup_toolchain_linux.py"):
            src = os.path.join(HERE, name)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(bundle_root, name))
        copy_resources(bundle_root)
        vendored = vendor_python_deps(bundle_root)
        write_file(
            os.path.join(bundle_root, APP_BIN),
            "#!/bin/sh\n"
            "# Luni IDE (запуск из исходников системным python3)\n"
            'HERE=$(dirname "$(readlink -f "$0")")\n'
            'export LUNI_BASE="$HERE"\n'
            'if [ -d "$HERE/lib" ]; then\n'
            '    export PYTHONPATH="$HERE/lib${PYTHONPATH:+:$PYTHONPATH}"\n'
            'fi\n'
            'exec python3 "$HERE/server.py" "$@"\n',
            0o755,
        )
        return bundle_root, False, vendored

    work = os.path.join(BUILD_DIR, "pyinstaller")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)

    pyi_major = 0
    try:
        import PyInstaller  # noqa: F401
        pyi_major = int(PyInstaller.__version__.split(".")[0])
    except Exception:
        pass

    cmd = [sys.executable, "-m", "PyInstaller",
           "--noconfirm", "--clean", "--onedir",
           "--name", APP_BIN,
           "--distpath", bundle_root,
           "--workpath", work,
           "--specpath", work,
           "--hidden-import", "serial.tools.list_ports",
           "--hidden-import", "flask",
           "--hidden-import", "werkzeug",
           "--hidden-import", "jinja2",
           "--exclude-module", "tkinter",
           "--exclude-module", "PyQt5",
           "--exclude-module", "PySide6"]
    if pyi_major >= 6:
        # всё содержимое рядом с бинарником: server.py ищет ресурсы в BASE
        cmd += ["--contents-directory", "."]
    if have_module("webview"):
        log("pywebview найден — включаю нативное окно в бандл")
        cmd += ["--collect-all", "webview"]
    cmd.append(os.path.join(HERE, "server.py"))
    run(cmd)

    if not os.path.isdir(target):
        log("ОШИБКА: PyInstaller не создал " + target)
        sys.exit(1)

    log("копирую ресурсы приложения в бандл")
    copy_resources(target)
    binary = os.path.join(target, APP_BIN)
    if os.path.exists(binary):
        os.chmod(binary, 0o755)
    return bundle_root, True, False


def vendor_python_deps(bundle_root):
    """Кладёт flask и pyserial в bundle/lib (режим без PyInstaller).

    Тогда пакету нужен только системный python3, а не python3-flask.
    Если pip/интернета нет — возвращает False, и .deb объявит зависимости
    python3-flask/python3-serial.
    """
    target = os.path.join(bundle_root, "lib")
    log("складываю python-зависимости в lib/ (flask, pyserial)")
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--no-compile",
           "--target", target, "flask>=3.0", "pyserial>=3.5"]
    try:
        run(cmd, check=True)
    except Exception as e:  # noqa: BLE001
        log("не удалось скачать зависимости (" + str(e) + ");")
        log("пакет будет использовать системные python3-flask / python3-serial")
        shutil.rmtree(target, ignore_errors=True)
        return False
    return os.path.isdir(os.path.join(target, "flask"))


def maybe_add_toolchain(bundle_root, enabled):
    """--with-toolchain: arduino-cli + ядро ESP32 внутрь бандла (офлайн)."""
    if not enabled:
        return
    log("вшиваю офлайн-тулчейн (arduino-cli + ядро ESP32) — это надолго")
    run([sys.executable, os.path.join(HERE, "setup_toolchain_linux.py"),
         "--dest", bundle_root])


# --------------------------------------------------------------------------- #
# 2. AppDir
# --------------------------------------------------------------------------- #
def make_appdir(bundle_root):
    """Собирает FHS-дерево AppDir из готового бандла."""
    root = os.path.join(BUILD_DIR, "appimage", APP_BIN + ".AppDir")
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root, exist_ok=True)

    # приложение -> usr/lib/luni-ide
    app_lib = os.path.join(root, "usr", "lib", APP_ID)
    copy_tree_contents(bundle_root, app_lib)
    for name in os.listdir(app_lib):
        p = os.path.join(app_lib, name)
        if os.path.isfile(p) and (name == APP_BIN or name.startswith("arduino-cli")):
            os.chmod(p, 0o755)

    # обёртка: usr/bin/Luni-IDE
    write_file(
        os.path.join(root, "usr", "bin", APP_BIN),
        "#!/bin/sh\n"
        "# Luni IDE — запуск приложения из AppImage/AppDir\n"
        'SELF=$(readlink -f "$0")\n'
        'HERE=$(dirname "$SELF")\n'
        'exec "$HERE/../lib/' + APP_ID + '/' + APP_BIN + '" "$@"\n',
        0o755,
    )

    # AppRun — точка входа AppImage (APPDIR задаёт сам runtime)
    write_file(
        os.path.join(root, "AppRun"),
        "#!/bin/sh\n"
        "# Точка входа AppImage: Luni IDE\n"
        'if [ -z "$APPDIR" ]; then APPDIR=$(dirname "$(readlink -f "$0")"); fi\n'
        'exec "$APPDIR/usr/bin/' + APP_BIN + '" "$@"\n',
        0o755,
    )

    # метаданные рабочего стола
    desktop = desktop_text(APP_BIN)
    write_file(os.path.join(root, APP_ID + ".desktop"), desktop)
    write_file(os.path.join(root, "usr", "share", "applications", APP_ID + ".desktop"),
               desktop)

    metainfo = render(os.path.join(PACKAGING, "luni-ide.metainfo.xml.in"),
                      {"VERSION": read_version()})
    write_file(os.path.join(root, "usr", "share", "metainfo", APP_ID + ".metainfo.xml"),
               metainfo)

    for size, src in icons():
        dst = os.path.join(root, "usr", "share", "icons", "hicolor",
                           f"{size}x{size}", "apps", APP_ID + ".png")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

    # иконка верхнего уровня + .DirIcon (требования AppImage)
    top_icon = os.path.join(root, APP_ID + ".png")
    src_icon = dict(icons()).get(256) or (icons()[0][1] if icons() else None)
    if src_icon:
        shutil.copy2(src_icon, top_icon)
        diricon = os.path.join(root, ".DirIcon")
        if os.path.lexists(diricon):
            os.remove(diricon)
        os.symlink(APP_ID + ".png", diricon)
    else:
        log("ВНИМАНИЕ: нет ни одной иконки (icon.png отсутствует)")

    log("AppDir готов: " + root)
    return root


def tree_size(path):
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            p = os.path.join(root, name)
            if not os.path.islink(p):
                total += os.path.getsize(p)
    return total


# --------------------------------------------------------------------------- #
# 3. Debian-пакет
# --------------------------------------------------------------------------- #
CONTROL_TEMPLATE = """\
Package: {package}
Version: {version}
Section: devel
Priority: optional
Architecture: {arch}
Maintainer: {maintainer}
Installed-Size: {size_kb}
Depends: {depends}
Recommends: {recommends}
Homepage: {homepage}
Description: {title} — среда программирования ESP32 Dev Module
 Luni IDE — простая локальная IDE для учебных плат на ESP32 Dev Module.
 Внутри редактор кода с подсветкой и автодополнением, компиляция и прошивка
 через arduino-cli, serial-монитор, менеджер библиотек и примеры.
 .
 Работает офлайн, если установлен локальный тулчейн:
   python3 /opt/luni-ide/setup_toolchain_linux.py
"""

POSTINST = """\
#!/bin/sh
set -e
# Обновляем кэши рабочего стола/иконок и MIME, если инструменты есть.
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
fi
if command -v update-mime-database >/dev/null 2>&1; then
    update-mime-database /usr/share/mime || true
fi
exit 0
"""

PRERM = """\
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
"""

COPYRIGHT = """\
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: Luni IDE
Source: {homepage}

Files: *
Copyright: Luni IDE contributors
License: no license file in the upstream repository yet
 В исходном репозитории нет файла лицензии. Пока лицензия не добавлена,
 распространять пакет можно только с разрешения правообладателя.
"""


def make_deb(bundle_root, frozen=True, vendored=False, out_dir=DIST_DIR):
    """Собирает Debian-пакет с приложением в /opt/luni-ide."""
    version = read_version()
    arch = dpkg_arch()
    root = os.path.join(BUILD_DIR, "deb", APP_ID)
    shutil.rmtree(root, ignore_errors=True)

    opt = os.path.join(root, "opt", APP_ID)
    copy_tree_contents(bundle_root, opt)

    # исполняемый файл в /usr/bin
    write_file(
        os.path.join(root, "usr", "bin", APP_ID),
        "#!/bin/sh\n"
        "# Luni IDE — launcher Debian-пакета\n"
        'APP_DIR="/opt/' + APP_ID + '"\n'
        'if [ ! -x "$APP_DIR/' + APP_BIN + '" ]; then\n'
        '    echo "Luni IDE: не найден $APP_DIR/' + APP_BIN + '" >&2\n'
        '    exit 1\n'
        'fi\n'
        'exec "$APP_DIR/' + APP_BIN + '" "$@"\n',
        0o755,
    )

    desktop = desktop_text(APP_ID, try_exec=APP_ID)
    write_file(os.path.join(root, "usr", "share", "applications", APP_ID + ".desktop"),
               desktop)

    metainfo = render(os.path.join(PACKAGING, "luni-ide.metainfo.xml.in"),
                      {"VERSION": version})
    write_file(os.path.join(root, "usr", "share", "metainfo", APP_ID + ".metainfo.xml"),
               metainfo)

    for size, src in icons():
        dst = os.path.join(root, "usr", "share", "icons", "hicolor",
                           f"{size}x{size}", "apps", APP_ID + ".png")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)

    mime_src = os.path.join(PACKAGING, "luni-ide-mime.xml")
    if os.path.exists(mime_src):
        write_file(os.path.join(root, "usr", "share", "mime", "packages",
                                APP_ID + ".xml"),
                   open(mime_src, encoding="utf-8").read())

    doc = os.path.join(root, "usr", "share", "doc", APP_ID)
    os.makedirs(doc, exist_ok=True)
    if os.path.exists(os.path.join(HERE, "README-LINUX.md")):
        shutil.copy2(os.path.join(HERE, "README-LINUX.md"),
                     os.path.join(doc, "README-LINUX.md"))
    write_file(os.path.join(doc, "copyright"), COPYRIGHT.format(homepage=PROJECT))

    if frozen:
        depends = "libc6 (>= 2.34), libstdc++6, libgcc-s1"
        recommends = "arduino-cli, xdg-utils, python3"
    elif vendored:
        # flask и pyserial уже лежат в /opt/luni-ide/lib
        depends = "python3 (>= 3.9), xdg-utils"
        recommends = "arduino-cli"
    else:
        depends = "python3 (>= 3.9), python3-flask, python3-serial, xdg-utils"
        recommends = "arduino-cli"

    size_kb = max(1, tree_size(root) // 1024)
    control = CONTROL_TEMPLATE.format(
        package=APP_ID, version=version, arch=arch, maintainer=MAINTAINER,
        size_kb=size_kb, depends=depends, recommends=recommends,
        homepage=PROJECT, title=APP_TITLE,
    )
    write_file(os.path.join(root, "DEBIAN", "control"), control)
    write_file(os.path.join(root, "DEBIAN", "postinst"), POSTINST, 0o755)
    write_file(os.path.join(root, "DEBIAN", "prerm"), PRERM, 0o755)

    if not shutil.which("dpkg-deb"):
        log("ОШИБКА: нет dpkg-deb (пакет dpkg). Установите: sudo apt install dpkg")
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{APP_ID}_{version}_{arch}.deb")
    run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", root, out])
    write_checksum(out)
    log("ГОТОВО. Пакет: " + out)
    log("установить:  sudo apt install " + out)
    log("удалить:     sudo apt remove " + APP_ID)
    return out


# --------------------------------------------------------------------------- #
# 4. AppImage
# --------------------------------------------------------------------------- #
APPIMAGETOOL_HINT = """\
appimagetool не найден — .AppImage не собран.
Варианты:
  1) Поставить appimagetool (рекомендуется):
       wget -O ~/.local/bin/appimagetool \\
         https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
       chmod +x ~/.local/bin/appimagetool
     (нужен FUSE; в контейнере помогает APPIMAGE_EXTRACT_AND_RUN=1)
  2) Указать путь вручную:
       APPIMAGETOOL=/путь/к/appimagetool python3 build_linux.py appimage
  3) Собрать из AppDir пакетом appimage-builder или squashfs-tools:
       mksquashfs build/linux/appimage/Luni-IDE.AppDir out.squashfs ...
Готовый AppDir уже лежит в build/linux/appimage/Luni-IDE.AppDir
"""


def find_appimagetool():
    env = os.environ.get("APPIMAGETOOL", "").strip()
    if env and os.path.exists(env):
        return env
    for name in ("appimagetool", "appimagetool-x86_64.AppImage",
                 "appimagetool-aarch64.AppImage"):
        path = shutil.which(name)
        if path:
            return path
    if os.path.isdir(VENDOR_DIR):
        for name in sorted(os.listdir(VENDOR_DIR)):
            if name.startswith("appimagetool"):
                return os.path.join(VENDOR_DIR, name)
    return None


def make_appimage(appdir, strict=False, out_dir=DIST_DIR):
    """Упаковывает AppDir в .AppImage; без appimagetool — в tar.gz."""
    version = read_version()
    arch = appimage_arch()
    os.makedirs(out_dir, exist_ok=True)
    tool = find_appimagetool()

    if tool:
        try:
            os.chmod(tool, 0o755)
        except OSError:
            pass
        out = os.path.join(out_dir, f"{APP_BIN}-{version}-{arch}.AppImage")
        env = dict(os.environ)
        env["ARCH"] = arch
        # appimagetool сам является AppImage: без FUSE запускаем через извлечение
        env.setdefault("APPIMAGE_EXTRACT_AND_RUN", "1")
        cmd = [tool, "--no-appstream", appdir, out]
        run(cmd, env=env, check=False)
        if not os.path.exists(out):
            log("appimagetool завершился без результата.")
            if strict:
                sys.exit(1)
        else:
            os.chmod(out, 0o755)
            write_checksum(out)
            log("ГОТОВО. AppImage: " + out)
            return out
    else:
        log(APPIMAGETOOL_HINT)
        if strict:
            sys.exit(1)

    # Fallback: архив готового AppDir — его можно распаковать и запустить
    # через ./AppRun (полезно, когда FUSE/appimagetool недоступны).
    fallback = os.path.join(out_dir, f"{APP_BIN}-{version}-{arch}.AppDir.tar.gz")
    cmd = ["tar", "--sort=name", "--owner=0", "--group=0", "--numeric-owner"]
    epoch = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    if epoch.isdigit():
        # воспроизводимая сборка: фиксируем mtime у всех файлов архива
        cmd.append("--mtime=@" + epoch)
    cmd += ["-czf", fallback, "-C", os.path.dirname(appdir), os.path.basename(appdir)]
    run(cmd)
    write_checksum(fallback)
    log("Вместо .AppImage собран архив AppDir: " + fallback)
    log("распаковать: tar -xzf " + os.path.basename(fallback) + " && ./Luni-IDE.AppDir/AppRun")
    return fallback


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv=None):
    if sys.platform != "linux":
        log("Этот скрипт собирает только Linux-версию.")
        log("Для Windows используйте:  python build.py")
        return 2

    ap = argparse.ArgumentParser(
        description="Сборка Luni IDE под Linux (.deb и AppImage)")
    ap.add_argument("target", nargs="?", default="all",
                    choices=["all", "bundle", "appdir", "deb", "appimage"],
                    help="что собрать (по умолчанию all)")
    ap.add_argument("--no-frozen", action="store_true",
                    help="не использовать PyInstaller (запуск системным python3)")
    ap.add_argument("--with-toolchain", action="store_true",
                    help="вшить arduino-cli и ядро ESP32 (офлайн-пакет)")
    ap.add_argument("--strict", action="store_true",
                    help="ошибка, если appimagetool недоступен")
    ap.add_argument("--out", default=DIST_DIR, help="каталог для артефактов")
    args = ap.parse_args(argv)

    version = read_version()
    frozen = not args.no_frozen
    log(f"{APP_TITLE} {version}: цель={args.target}, "
        f"режим={'PyInstaller' if frozen else 'python3 из системы'}, "
        f"архитектура={dpkg_arch()}")

    bundle_root, frozen, vendored = build_bundle(frozen=frozen)
    maybe_add_toolchain(bundle_root, args.with_toolchain)

    if args.target == "bundle":
        log("Бандл готов: " + bundle_root)
        return 0

    appdir = make_appdir(bundle_root)

    if args.target == "appdir":
        log("AppDir готов: " + appdir)
        return 0

    artifacts = []
    if args.target in ("all", "deb"):
        artifacts.append(make_deb(bundle_root, frozen=frozen, vendored=vendored,
                                  out_dir=args.out))
    if args.target in ("all", "appimage"):
        artifacts.append(make_appimage(appdir, strict=args.strict, out_dir=args.out))

    log("=== ИТОГ ===")
    for path in artifacts:
        size = os.path.getsize(path) / (1024 * 1024)
        log(f"  {path}  ({size:.1f} МБ)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
