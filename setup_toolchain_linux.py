#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_toolchain_linux.py — офлайн-тулчейн для Luni IDE на Linux.

Linux-аналог prepare_bundle.py: один раз скачивает arduino-cli и ядро ESP32,
после чего IDE компилирует и прошивает платы БЕЗ интернета.

Что делает:
  1) скачивает arduino-cli для своей архитектуры (x86_64 / aarch64 / armv7);
  2) обновляет индексы плат и библиотек;
  3) ставит ядро ESP32 (esp32:esp32) в переносимую папку;
  4) (необязательно) ставит библиотеки занятий.

Куда ставит:
  * по умолчанию — ~/.local/share/luni-ide/toolchain (XDG_DATA_HOME учитывается).
    IDE сама находит этот каталог, отдельная настройка не нужна;
  * с --dest DIR — в указанный каталог. Так тулчейн можно зашить внутрь
    AppImage или .deb:  python3 build_linux.py appimage --with-toolchain

Примеры:
    python3 setup_toolchain_linux.py
    python3 setup_toolchain_linux.py --dest ~/luni-toolchain
    python3 setup_toolchain_linux.py --no-core          # только arduino-cli
    python3 setup_toolchain_linux.py --lib Servo --lib "Adafruit NeoPixel"

Нужен интернет только на время работы скрипта (сотни МБ).
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request

ESP32_INDEX = ("https://raw.githubusercontent.com/espressif/arduino-esp32/"
               "gh-pages/package_esp32_index.json")

# Имена архивов arduino-cli для разных архитектур (официальные сборки Arduino).
CLI_URLS = {
    "x86_64":  "arduino-cli_latest_Linux_64bit.tar.gz",
    "amd64":   "arduino-cli_latest_Linux_64bit.tar.gz",
    "aarch64": "arduino-cli_latest_Linux_ARM64.tar.gz",
    "arm64":   "arduino-cli_latest_Linux_ARM64.tar.gz",
    "armv7l":  "arduino-cli_latest_Linux_ARMv7.tar.gz",
    "armv6l":  "arduino-cli_latest_Linux_ARMv6.tar.gz",
    "i686":    "arduino-cli_latest_Linux_32bit.tar.gz",
    "i386":    "arduino-cli_latest_Linux_32bit.tar.gz",
}
CLI_BASE = "https://downloads.arduino.cc/arduino-cli/"


def log(msg):
    print("[toolchain] " + msg, flush=True)


def default_dest():
    """Тот же путь, который ищет server.py: <XDG_DATA_HOME>/luni-ide/toolchain."""
    root = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"),
                                                           ".local", "share")
    return os.path.join(root, "luni-ide", "toolchain")


def cli_url(machine=None):
    machine = (machine or platform.machine()).lower()
    name = CLI_URLS.get(machine)
    if not name:
        return None
    return CLI_BASE + name


def download(url, dst, tries=4):
    """Скачивание с повтором: обрывы сети на школьном интернете — норма."""
    for attempt in range(1, tries + 1):
        try:
            log("скачиваю " + url)
            req = urllib.request.Request(url, headers={"User-Agent": "luni-ide-toolchain"})
            with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
                shutil.copyfileobj(r, f, length=256 * 1024)
            return
        except Exception as e:  # noqa: BLE001
            if attempt == tries:
                raise
            log(f"не удалось ({e}); повтор {attempt}/{tries - 1} через 5 с")
            time.sleep(5)


def install_cli(dest, force=False):
    """Распаковывает arduino-cli в dest/arduino-cli (chmod +x)."""
    target = os.path.join(dest, "arduino-cli")
    if os.path.exists(target) and not force:
        log("arduino-cli уже есть: " + target)
        return target

    url = cli_url()
    if not url:
        log("Неизвестная архитектура: " + platform.machine())
        log("Скачайте arduino-cli вручную: https://arduino.github.io/arduino-cli/latest/installation/")
        sys.exit(1)

    with tempfile.TemporaryDirectory(prefix="luni-cli-") as tmp:
        arch = os.path.join(tmp, "cli.tar.gz")
        download(url, arch)
        with tarfile.open(arch) as tar:
            member = None
            for m in tar.getmembers():
                if os.path.basename(m.name) == "arduino-cli" and m.isfile():
                    member = m
                    break
            if member is None:
                log("В архиве нет файла arduino-cli — скачайте вручную.")
                sys.exit(1)
            with tar.extractfile(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    os.chmod(target, 0o755)
    log("arduino-cli готов: " + target)
    return target


def cli_env(dest):
    return {
        **os.environ,
        "ARDUINO_DIRECTORIES_DATA": os.path.join(dest, "arduino-data"),
        "ARDUINO_DIRECTORIES_USER": os.path.join(dest, "arduino-user"),
        "ARDUINO_DIRECTORIES_DOWNLOADS": os.path.join(dest, "arduino-downloads"),
        "ARDUINO_BOARD_MANAGER_ADDITIONAL_URLS": ESP32_INDEX,
    }


def run_cli(cli, args, env, tries=6, delay=10):
    """Вызов arduino-cli с повторами (докачка идёт из кэша загрузок)."""
    for attempt in range(1, tries + 1):
        log("> arduino-cli " + " ".join(args))
        try:
            subprocess.run([cli] + args, env=env, check=True)
            return
        except subprocess.CalledProcessError as e:
            if attempt == tries:
                raise
            log(f"сбой ({e}); повтор {attempt}/{tries - 1} через {delay} с")
            time.sleep(delay)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Скачать arduino-cli и ядро ESP32 для Luni IDE (Linux)")
    ap.add_argument("--dest", default=None,
                    help="куда ставить тулчейн (по умолчанию ~/.local/share/luni-ide/toolchain)")
    ap.add_argument("--no-core", action="store_true",
                    help="не устанавливать ядро ESP32 (только arduino-cli)")
    ap.add_argument("--force", action="store_true",
                    help="перекачать arduino-cli, даже если он уже есть")
    ap.add_argument("--lib", action="append", default=[],
                    help="дополнительная библиотека (можно указать несколько раз)")
    args = ap.parse_args(argv)

    if sys.platform != "linux":
        log("Скрипт предназначен для Linux. Для Windows используйте prepare_bundle.py.")
        return 2

    dest = os.path.abspath(os.path.expanduser(args.dest or default_dest()))
    for sub in ("arduino-data", "arduino-user", "arduino-downloads"):
        os.makedirs(os.path.join(dest, sub), exist_ok=True)
    log("каталог тулчейна: " + dest)

    cli = install_cli(dest, force=args.force)
    env = cli_env(dest)

    if args.no_core:
        log("ядро ESP32 пропущено (--no-core).")
        log("готово.")
        return 0

    run_cli(cli, ["core", "update-index"], env)
    run_cli(cli, ["lib", "update-index"], env)
    log("устанавливаю ядро ESP32 (сотни МБ, это надолго)")
    run_cli(cli, ["core", "install", "esp32:esp32"], env)

    for lib in args.lib:
        log("библиотека: " + lib)
        run_cli(cli, ["lib", "install", lib], env, tries=3)

    log("готово. Теперь Luni IDE найдёт тулчейн автоматически.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
