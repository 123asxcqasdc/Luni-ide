ДРАЙВЕР USB-UART ДЛЯ ПЛАТЫ ESP32 (папка drivers) — ТОЛЬКО WINDOWS

На платах ESP32 Dev Module для связи по USB стоит чип CH340/CH341.

drivers/CH341SER/   — INF-пакет драйвера (Win10/11). Установщик Luni IDE
                      ставит его ТИХО через командную строку:
                        pnputil /add-driver CH341SER.INF /install
                      (галочка на последнем шаге установки; появится
                      только окно UAC — подтвердить права администратора).

drivers/CH341SER.EXE — запасной вариант: официальный GUI-инсталлятор WCH,
                      если по какой-то причине pnputil недоступен.
                      Источник: https://www.wch-ic.com/downloads/CH341SER_EXE.html

Если на вашей плате другой чип (CP2102 / CP210x, Silicon Labs):
  скачайте «CP210x Universal Windows Driver» и поставьте отдельно —
  https://www.silabs.com/developer-tools/usb-to-uart-bridge-vcp-drivers

Драйвер ставится с правами администратора и только один раз на каждом ПК.

--------------------------------------------------
LINUX
--------------------------------------------------
Драйверы CH340/CH341 и CP210x уже входят в ядро Linux — эта папка для Linux
не нужна. Вместо драйвера нужны права на serial-порт: пользователь должен
входить в группу dialout (на некоторых дистрибутивах — uucp):

    sudo usermod -aG dialout "$USER"

После этого нужно перелогиниться. Порт платы появится как /dev/ttyUSB0
или /dev/ttyACM0. Подробности — README-LINUX.md.
