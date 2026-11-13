# Luni IDE для Linux (Debian / Ubuntu / AppImage)

Luni IDE — та же среда программирования ESP32 Dev Module (UniBase), что и
Windows-версия, но собранная под Linux. Внутри: редактор с подсветкой и
автодополнением, компиляция и прошивка через `arduino-cli`, serial-монитор,
менеджер библиотек и примеры. Проекты лежат обычными папками `.ino`, как в Arduino.

Готовые файлы (`.deb` и `.AppImage`) публикуются на странице релизов:

```
https://github.com/123asxcqasdc/Luni-ide/releases/latest
```

---

## 1. Установка из .deb (Debian 12+, Ubuntu 22.04+, Mint 21+)

```bash
sudo apt install ./luni-ide_1.4.0_amd64.deb
```

`apt` сам подтянет зависимости; `dpkg -i` тоже работает, но без автоустановки
зависимостей. После установки:

* меню приложений → **Luni IDE** (раздел «Разработка»);
* из терминала: `luni-ide` или `luni-ide ~/Мои/проекты/Blink/Blink.ino`;
* файлы `.ino` можно открывать двойным кликом (зарегистрирован MIME-тип).

Куда ставится: `/opt/luni-ide` (только чтение), ярлык — `/usr/bin/luni-ide`,
иконки — `/usr/share/icons/hicolor`, метаданные — `/usr/share/metainfo`.

Удаление: `sudo apt remove luni-ide` (пользовательские проекты и кэш не
удаляются).

## 2. AppImage (любой дистрибутив, без установки)

```bash
chmod +x Luni-IDE-1.4.0-x86_64.AppImage
./Luni-IDE-1.4.0-x86_64.AppImage
```

При первом запуске удобно интегрировать AppImage в меню (например,
[AppImageLauncher](https://github.com/TheAssassin/AppImageLauncher)) — тогда
появятся ярлык и иконка. Без FUSE в системе запускайте:

```bash
./Luni-IDE-1.4.0-x86_64.AppImage --appimage-extract-and-run
```

## 3. Права на serial-порт (важно!)

Чтобы прошивать плату и видеть порт, пользователь должен входить в группу
`dialout` (на некоторых дистрибутивах — `uucp`):

```bash
sudo usermod -aG dialout "$USER"
```

и **перелогиниться** (или перезагрузиться). После этого в списке портов
появятся `/dev/ttyUSB0`, `/dev/ttyACM0` и т. п. Драйвер CH340 в Linux уже
встроен в ядро — отдельно ставить ничего не нужно (в отличие от Windows).

## 4. Тулчейн: arduino-cli и ядро ESP32

Приложению нужен `arduino-cli` и установленное ядро `esp32:esp32`.
Есть три варианта, любой из них подходит:

**а) Автоматически (локальный тулчейн в домашнем каталоге, рекомендуется)**

```bash
python3 /opt/luni-ide/setup_toolchain_linux.py
```

Скрипт скачает `arduino-cli` под вашу архитектуру и поставит ядро ESP32 в
`~/.local/share/luni-ide/toolchain`. Luni IDE находит этот каталог сам, интернет
после этого не нужен. Для AppImage тот же скрипт:

```bash
./Luni-IDE-1.4.0-x86_64.AppImage --appimage-extract
python3 squashfs-root/usr/lib/luni-ide/setup_toolchain_linux.py
```

**б) Системный пакет**

```bash
sudo apt install arduino-cli           # если он есть в вашем дистрибутиве
arduino-cli core update-index
arduino-cli core install esp32:esp32
```

**в) Вшить в пакет при сборке** (офлайн-раздача, см. раздел 6):

```bash
python3 build_linux.py all --with-toolchain
```

Проверить, что IDE всё видит: меню **Файл → Проверка окружения** или
`curl http://127.0.0.1:5000/api/env` при запущенной IDE (поля `arduino_cli`,
`esp32_core`, `cli_path`).

## 5. Где Luni IDE хранит данные на Linux

| Что | Путь |
| --- | --- |
| Проекты по умолчанию | `~/.local/share/luni-ide/Uni_Sketches` |
| Список последних проектов | `~/.local/share/luni-ide/luni-ide-recent.json` |
| Кэш сборки (общий для проектов) | `~/.local/share/luni-ide/build-cache` |
| Каталог сборки | `~/.local/share/luni-ide/build-tmp` |
| Локальный тулчейн | `~/.local/share/luni-ide/toolchain` |
| Журнал запуска (собранная версия) | `~/.local/share/luni-ide/luni-ide-log.txt` |

Путь `XDG_DATA_HOME` учитывается. Код приложения (в `.deb` — `/opt/luni-ide`,
в AppImage — точка монтирования) не изменяется, поэтому обновление пакета не
затрагивает проекты. Windows-версия по-прежнему хранит данные рядом с `.exe`
и в `%LOCALAPPDATA%\Luni-IDE`.

Интерфейс открывается в системном браузере (порт 5000). Если установлен
`pywebview` с GTK/WebKit и приложение запущено из исходников, откроется
нативное окно. Порт можно поменять: `luni-ide --port 5001`.

## 6. Сборка из исходников

Зависимости сборки:

```bash
sudo apt install python3 python3-pip dpkg tar            # dpkg-deb нужен для .deb
sudo apt install libpython3.11                           # общая библиотека для PyInstaller
python3 -m pip install --upgrade pyinstaller flask pyserial
```

`libpython3.X` нужен только PyInstaller (замороженный бандл со своим
интерпретатором). Если его нет, `build_linux.py` сам переключится в режим
`--no-frozen`: в пакет пойдут исходники, `flask` и `pyserial` будут положены
в `lib/` рядом с приложением, а запуск пойдёт системным `python3` — то есть
на машине пользователя достаточно `python3`, без `python3-flask`.

Сборка:

```bash
python3 build_linux.py appdir        # дерево приложения (build/linux/appimage/Luni-IDE.AppDir)
python3 build_linux.py deb           # dist/luni-ide_<версия>_amd64.deb
python3 build_linux.py appimage      # dist/Luni-IDE-<версия>-x86_64.AppImage
python3 build_linux.py all           # и пакет, и AppImage
```

Полезные флаги:

| Флаг | Что делает |
| --- | --- |
| `--with-toolchain` | вшивает `arduino-cli` + ядро ESP32 (пакет становится на сотни МБ) |
| `--no-frozen` | без PyInstaller: в пакет кладутся исходники, `flask`/`pyserial` вендорятся в `lib/`, запуск системным `python3` |
| `--strict` | считать отсутствие `appimagetool` ошибкой (для CI) |
| `--out DIR` | куда складывать артефакты (по умолчанию `dist/`) |

Рядом с каждым артефактом пишется `.sha256`.

Воспроизводимая сборка (одинаковые таймстампы в `.deb` и архиве AppDir):

```bash
SOURCE_DATE_EPOCH=1700000000 python3 build_linux.py all
```

То же самое автоматически собирает GitHub Actions —
`.github/workflows/build-linux.yml` (тесты → `.deb` → `.AppImage` → артефакты
запуска).

### appimagetool

Для `.AppImage` нужен `appimagetool` — он не входит в дистрибутивы:

```bash
mkdir -p ~/.local/bin
wget -O ~/.local/bin/appimagetool \
  https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x ~/.local/bin/appimagetool
```

Если `appimagetool` нет, `build_linux.py` не падает: он оставляет готовый
AppDir и собирает `dist/Luni-IDE-<версия>-<arch>.AppDir.tar.gz`, который
запускается через `./Luni-IDE.AppDir/AppRun`. В контейнерах без FUSE помогает
`APPIMAGE_EXTRACT_AND_RUN=1`.

### Режим разработки (без сборки)

```bash
sudo apt install python3-flask python3-serial     # или: python3 -m pip install -r requirements.txt
python3 server.py
```

Откроется браузер с интерфейсом на `http://127.0.0.1:5000`.

## 7. Структура Linux-сборки в репозитории

```
build_linux.py                     сборка .deb и AppImage
setup_toolchain_linux.py           arduino-cli + ядро ESP32 (офлайн-тулчейн)
packaging/
├── luni-ide.desktop.in            ярлык (шаблон: подставляется @EXEC@)
├── luni-ide.metainfo.xml.in       AppStream-метаданные
├── luni-ide-mime.xml              MIME-тип text/x-arduino для .ino
└── icons/luni-ide-{32..256}.png   иконки hicolor
build.py                           Windows-сборка (exe + Inno Setup)
installer/Luni-IDE.iss             Windows-установщик
```

Артефакты сборки (`build/`, `dist/`) в репозиторий не попадают.

## 8. Обновления

В Linux у приложения нет самоподмены файлов (AppImage смонтирован только для
чтения, а `/opt` принадлежит пакетному менеджеру). IDE проверяет последний
релиз и показывает в статус-баре ссылку на страницу загрузки:

* `.deb` — `sudo apt install ./luni-ide_<новая>_amd64.deb`
  (или `sudo apt update && sudo apt upgrade`, если подключён репозиторий);
* `.AppImage` — заменить файл новым.

Репозиторий обновлений можно переопределить переменной окружения
`LUNI_UPDATE_REPO="owner/repo"`.

## 9. Частые проблемы

| Симптом | Решение |
| --- | --- |
| В списке портов пусто | нет прав: `sudo usermod -aG dialout "$USER"` и перелогин; кабель должен быть с данными |
| «arduino-cli не найден» | раздел 4: `setup_toolchain_linux.py` или `sudo apt install arduino-cli` |
| «ядро esp32 не установлено» | `arduino-cli core install esp32:esp32` (или скрипт выше) |
| AppImage не запускается | `chmod +x`, проверить FUSE, попробовать `--appimage-extract-and-run` |
| Окно не открылось | интерфейс доступен в браузере: `http://127.0.0.1:5000`; порт занят — `--port 5001` |
| Первая компиляция долгая | нормально: один раз собирается кэш ядра ESP32 |
| Кириллица в путях проектов | работает: пути передаются как UTF-8, `arduino-cli` получает их через build-path |

## 10. Отличия от Windows-версии

* нет установщика с драйвером CH340 — драйвер в Linux встроен в ядро;
* нет самоподмены файлов (payload-обновления): вместо этого `.deb`/AppImage;
* `--no-frozen` даёт маленький пакет, использующий системный Python;
* данные лежат в `~/.local/share/luni-ide`, а не рядом с бинарником.

## 11. Выпуск релиза (для мейнтейнера)

Релиз собирается и публикуется автоматически — `.github/workflows/build-linux.yml`:

1. Поднимите `VERSION` в `server.py` и влейте изменения в `main`
   (CI прогонит тесты и проверит сборку).
2. Поставьте тег на `main` и запушьте его:
   ```bash
   git tag -a v1.4.0 -m "Luni IDE 1.4.0"
   git push origin v1.4.0
   ```
3. Воркфлоу проверит, что тег совпадает с `VERSION`, соберёт `.deb` и `.AppImage`
   и прикрепит к релизу файлы `luni-ide_<версия>_amd64.deb`,
   `Luni-IDE-<версия>-x86_64.AppImage` и их `.sha256`.

Тег обязан иметь вид `vX.Y.Z` — по нему автообновление в `server.py` определяет
последнюю версию (`/releases/latest`). Windows-артефакты (`Luni-IDE-Setup-*.exe`)
собираются отдельно на Windows: `python prepare_bundle.py` → `python build.py`.
