# Luni IDE — простая IDE для программирования UniBase (ESP32)

Редактор кода Arduino C++ с подсветкой, менеджером библиотек, компиляцией,
прошивкой и serial-монитором. Загрузка зашита **только** на плату
**UniBase (ESP32 Dev Module)** (`FQBN = esp32:esp32:esp32`).

Это локальное приложение: маленький Python-сервер оборачивает `arduino-cli`,
а фронтенд открывается в браузере (или в нативном окне, если установлен
`pywebview`). Браузер не умеет компилировать C++, поэтому компиляция и
прошивка идут через `arduino-cli`, который внутри сам вызывает `esptool`
(тот самый пайплайн `bootloader.bin / partitions.bin / firmware.bin`).

## ⬇️ Скачать

Готовые сборки — на странице релизов:

### [→ Скачать последнюю версию Luni IDE](https://github.com/123asxcqasdc/Luni-ide/releases/latest)

| Система | Файл | Как ставить |
| --- | --- | --- |
| Windows 10/11 | `Luni-IDE-Setup-<версия>.exe` | запустить; права администратора не нужны |
| Debian 12 / Ubuntu 22.04+ / Mint 21+ | `luni-ide_<версия>_amd64.deb` | `sudo apt install ./luni-ide_<версия>_amd64.deb` |
| любой Linux | `Luni-IDE-<версия>-x86_64.AppImage` | `chmod +x` и запустить |

Памятка ученику — [student-README.txt](student-README.txt).
Подробно про Linux (права на serial-порт, тулчейн, сборка, обновления) —
[README-LINUX.md](README-LINUX.md).

```
luni-ide/
├── server.py                  # backend (Flask + arduino-cli)
├── index.html                 # интерфейс (CodeMirror)
├── build.py                   # сборка exe + установщика (Windows)
├── build_linux.py             # сборка .deb + AppImage (Linux)
├── prepare_bundle.py          # офлайн-тулчейн ESP32 (Windows)
├── setup_toolchain_linux.py   # офлайн-тулчейн ESP32 (Linux)
├── packaging/                 # .desktop, AppStream, MIME, иконки (Linux)
├── installer/Luni-IDE.iss     # скрипт установщика (Inno Setup, Windows)
├── requirements.txt
└── Uni_Sketches/              # создаётся автоматически — проекты учеников
    └── uni_sketch1/uni_sketch1.ino
```

## 1. Установка arduino-cli

**Windows (PowerShell):**
```powershell
winget install ArduinoSA.CLI
```
или скачать с https://arduino.github.io/arduino-cli/latest/installation/ и
добавить в `PATH`.

**macOS:**
```bash
brew install arduino-cli
```

**Linux:** проще всего скриптом, который заодно поставит ядро ESP32:
```bash
python3 setup_toolchain_linux.py
```
(альтернативы — официальный `install.sh` или пакет `arduino-cli` из
дистрибутива, см. [README-LINUX.md](README-LINUX.md)).

Проверка: `arduino-cli version`

## 2. Установка ядра ESP32 (один раз)

```bash
arduino-cli config init
arduino-cli config add board_manager.additional_urls https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
arduino-cli core update-index
arduino-cli core install esp32:esp32
```

## 3. Зависимости Python

```bash
pip install -r requirements.txt
```

## 4. Запуск

```bash
python server.py
```
Откройте в браузере **http://127.0.0.1:5000** (или запустите `python server.py --browser`).

Полезные флаги: `--port 5001` (если 5000 занят), `--no-open` (только сервер),
`luni-ide path/to/Blink.ino` (сразу открыть проект).

В нижней строке статуса загорятся индикаторы `arduino-cli` и `esp32 core` —
если они красные, вернитесь к шагам 1–2.

## Как пользоваться

1. Подключите плату по USB → нажмите `↻`, выберите порт в выпадающем списке
   (`COM3` в Windows, `/dev/ttyUSB0` или `/dev/ttyACM0` в Linux).
2. Пишите код в редакторе (он сохраняется автоматически).
3. **✓ Проверить** — только компиляция (`Ctrl/Cmd + R`).
4. **▶ Загрузить** — компиляция и прошивка на выбранный порт (`Ctrl/Cmd + Enter`).
5. Вкладка **Serial** (справа) — serial-монитор: кнопка «Подключить»,
   выбор скорости, отправка строк в порт.
6. Вкладка **Библиотеки** — поиск и установка по имени (`arduino-cli lib`).

## Где хранятся данные

| Система | Проекты и настройки |
| --- | --- |
| Windows (портативный бандл) | рядом с `Luni-IDE.exe` |
| Windows (установка) | `%LOCALAPPDATA%\Luni-IDE` |
| Linux (.deb, AppImage) | `~/.local/share/luni-ide` (`XDG_DATA_HOME`) |

Кэш сборки (`build-cache`) общий для всех проектов, каталог `build-tmp` —
отдельный на каждый проект. Код приложения в Linux-пакетах только для чтения,
поэтому обновление пакета не затрагивает проекты учеников.

## Автообновление

**Windows.** Установленная IDE обновляется сама: exe — тонкий «загрузчик»
(`bootstrap.py`), а логика (`server.py`, `index.html`, `vendor/`) — обычные файлы
рядом. Фоновый поток раз в несколько часов проверяет последний релиз на GitHub
(по редиректу `releases/latest`, без API-лимитов), скачивает лёгкий
`payload-<версия>.zip` (~0.5 МБ), сверяет sha256 и складывает в
`updates/pending`. Загрузчик применяет его при следующем запуске — с бэкапом и
автооткатом, если новая версия не стартовала. В статус-баре появляется тихая
подсказка «обновление готово — перезапустите». Офлайн-машины просто ничего не
замечают.

**Linux.** Самоподмена файлов невозможна (AppImage смонтирован только для
чтения, `/opt` принадлежит пакетному менеджеру), поэтому режим `manual`: IDE
проверяет версию и показывает ссылку на страницу релизов с `.deb` и `.AppImage`.
Репозиторий обновлений переопределяется переменной `LUNI_UPDATE_REPO="owner/repo"`.

Правила выпуска (Windows):
- `python build.py` кладёт в `installer-out/` **три** артефакта:
  `Luni-IDE-Setup-<v>.exe`, `payload-<v>.zip`, `payload-<v>.zip.sha256`.
  В релиз GitHub загружаются все три (payload обязателен — иначе установленные
  копии предложат ученикам скачивать полный установщик).
- Если менялись `bootstrap.py` или python-зависимости (flask/pyserial/pywebview) —
  поднимите `PAYLOAD_MIN_BASE` в `build.py` до новой версии: старые установки
  увидят плашку «нужен полный установщик» вместо кривого payload-обновления.
- Новый import в `server.py` должен быть в списке предзагрузки `bootstrap.py`
  (иначе замороженный python его не найдёт) — это тоже повод поднять
  `PAYLOAD_MIN_BASE`.

Правила выпуска (Linux):
- `python3 build_linux.py all` → `dist/luni-ide_<v>_amd64.deb` и
  `dist/Luni-IDE-<v>-x86_64.AppImage` (+ `.sha256` рядом).
- Для офлайн-раздачи: `python3 build_linux.py all --with-toolchain`
  (внутрь пакета вшивается `arduino-cli` и ядро ESP32).

## Сборка Linux-пакетов

```bash
sudo apt install python3 python3-pip dpkg tar
python3 -m pip install --upgrade pyinstaller flask pyserial

python3 build_linux.py deb           # Debian-пакет
python3 build_linux.py appimage      # AppImage
python3 build_linux.py all           # оба
```

`appimagetool` нужен только для шага AppImage; если его нет,
`build_linux.py` оставит готовый AppDir и соберёт
`dist/Luni-IDE-<v>-<arch>.AppDir.tar.gz`. Подробности и флаги —
[README-LINUX.md](README-LINUX.md).

## Тесты

Базовые функции серверного API (проекты, сохранение, недавние, примеры,
прогрев среды, опрос портов) и автообновление покрыты тестами — без реального
arduino-cli и без сети, выполняются пару секунд:

```bash
python -m unittest discover -s tests -v
```

Запускайте перед сборкой релиза.

## Частые проблемы

- **Порт не появляется** — нет драйвера USB-UART (CP2102 / CH340) или плохой кабель.
  В Linux драйвер CH340 уже в ядре, но нужна группа `dialout`
  (см. [README-LINUX.md](README-LINUX.md)).
- **`Failed uploading` / `Connecting...`** — на части плат нужно удерживать кнопку
  **BOOT** в момент начала прошивки.
- **Долгая первая компиляция** — это нормально, ESP32-ядро прогревает кэш.
- **arduino-cli не в PATH** — задайте путь явно:
  `ARDUINO_CLI=/полный/путь/arduino-cli python server.py`

---

# Офлайн-бандл для учеников (Windows, без интернета)

Сценарий: каждый ученик на своём ноутбуке с Windows, интернета на занятии нет,
нужен строго Arduino C++. Тогда весь тулчейн зашивается в один кликабельный
бандл. Готовите его **вы один раз с интернетом**, дальше раздаёте ученикам
флешкой/файлом — они просто запускают `Luni-IDE.exe`.

Для Linux тот же сценарий решается флагом `--with-toolchain`
(см. [README-LINUX.md](README-LINUX.md), раздел 4в).

### Что делаете вы (один раз, с интернетом)

1. Запекаете тулчейн в переносимую папку:
   ```
   python prepare_bundle.py
   ```
   Скачает `arduino-cli.exe` и установит ядро `esp32:esp32` в `./arduino-data`
   (несколько сотен МБ — это нормально, ужать нельзя). Нужные библиотеки можно
   добавить в список `LIBS` внутри скрипта.
2. Ставите **Inno Setup 6** (один раз на машине сборки):
   https://jrsoftware.org/isdl.php  или  `winget install JRSoftware.InnoSetup`
3. Собираете установщик одной командой:
   ```
   python build.py
   ```
   `build.py` соберёт `Luni-IDE.exe` (PyInstaller), положит рядом тулчейн и
   ресурсы и упакует всё в установщик:
   ```
   installer-out\Luni-IDE-Setup-1.0.0.exe
   ```
   Нужен только бандл без установщика — `python build.py --no-installer`
   (результат в папке `dist\Luni-IDE`).
4. Раздаёте ученикам **один файл** `Luni-IDE-Setup-x.x.x.exe`.

### Что делает ученик

Запускает `Luni-IDE-Setup-x.x.x.exe` — установка идёт **без прав
администратора** (программа ставится в папку пользователя). На последнем шаге
галочкой можно установить драйвер CH340. Дальше запускает **Luni IDE** ярлыком
с рабочего стола или из меню «Пуск» — откроется окно среды. Интернет не нужен.
Памятка для ученика — `student-README.txt`.

### Честные ограничения этого пути

- **Размер.** Ядро ESP32 + компилятор ≈ 0.5–1 ГБ. Это разовая раздача.
- **Драйвер CH340.** На «чистом» ноутбуке Windows его может не быть, и плата
  не появится в списке портов. Установщик предлагает поставить его галочкой
  (права администратора нужны только на сам драйвер). В Linux драйвер встроен
  в ядро.
- **Сборка под конкретную ОС.** Windows-установщик собирается на Windows,
  Linux-пакеты — на Linux.

> Windows: `python prepare_bundle.py` → `python build.py`.
> Linux: `python3 setup_toolchain_linux.py` → `python3 build_linux.py all`.
