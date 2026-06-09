# VS Translator Overlay

AI-assisted development

This project was created as a practical prototype with heavy assistance from AI tools, including ChatGPT and Codex.

I am not a professional programmer, so the code may not be perfect. The goal of this project is to provide a useful external translation overlay for Vintage Story players.

Code review, bug reports, pull requests, suggestions, and improvements are welcome.


## Windows SmartScreen warning

Windows Defender SmartScreen may show a warning when you run the app for the first time.

This happens because the executable is new and not code-signed yet. It does not automatically mean the app is malicious.

If you trust this project and downloaded it from the official GitHub Releases page, click:

More info → Run anyway

The source code is available in this repository, so you can inspect it or build the app yourself.


## VS Translator Overlay is a small external Windows overlay for Vintage Story.

It:

- reads `client-chat.log` and translates incoming chat;
- translates outgoing messages with preview/edit before paste;
- translates selected screen/sign text using Windows OCR;
- works outside the game and is not a Vintage Story mod.

## Features

- Incoming chat translation from the Vintage Story client chat log.
- Outgoing message translation with preview, editing, copy, and paste.
- Windows OCR for selected screen regions and quick center-screen OCR.
- Language dropdowns for chat, OCR, outgoing target language, and outgoing source language.
- Portable one-folder Windows build.
- Runtime settings, logs, and OCR debug images are stored in `%APPDATA%\VS Translator Overlay`.

## Requirements

- Windows 10 or Windows 11.
- Vintage Story.
- Internet connection for online translation.
- Windows OCR language packs for non-English OCR.

## Portable Release Usage

1. Download the release zip.
2. Extract the folder.
3. Run `VS Translator Overlay.exe`.
4. Press `Alt+P` to open settings.
5. Click `Auto-detect Vintage Story log`, or browse to `client-chat.log`.
6. Choose your languages.

The app reads chat from the local Vintage Story log file. It does not modify Vintage Story files.

## Hotkeys

- `Alt+T` - hide/show overlay
- `Alt+M` - move/resize/edit overlay
- `Alt+R` - translate outgoing message
- `Alt+Q` - quick center OCR
- `Alt+S` - select screen region OCR
- `Alt+Shift+Q` - repeat last OCR region
- `Alt+P` - settings
- `Alt+X` - quit

## Settings

- `Read chat/signs in` - language you want incoming chat and OCR translations translated into.
- `Read signs text as` - OCR source language for screen/sign text. Use Auto if unsure.
- `Send messages to` - target language for outgoing translated messages.
- `From language for outgoing messages` - source language for outgoing messages. Use Auto if unsure.

## Privacy Summary

The app is external. It does not inject into the game process and does not modify Vintage Story files.

It reads the local `client-chat.log` file and can capture a screen area selected by the user for OCR. Online translation is provided through the configured translator library, so translated text may be sent to third-party translation services.

Do not OCR or translate sensitive text if you do not want it sent to an online translator.

## Troubleshooting

- If OCR says the language is unavailable, install the matching Windows OCR language pack.
- Translation requires an internet connection.
- If the overlay is not visible, press `Alt+M` or open settings with `Alt+P` and reset overlay position.
- Logs are stored in `%APPDATA%\VS Translator Overlay`.

## Development Notes

The source version can be run with Python and the project dependencies installed.

The portable release is built with PyInstaller in one-folder mode.

---

# VS Translator Overlay

Разработка с помощью ИИ

Этот проект был создан как практический прототип при большой помощи ИИ-инструментов, включая ChatGPT и Codex.

Я не профессиональный программист, поэтому код может быть неидеальным. Цель проекта — сделать полезный внешний переводчик-оверлей для игроков Vintage Story.

Буду рад ревью кода, сообщениям об ошибках, pull request, предложениям и улучшениям.

## Предупреждение Windows SmartScreen

Windows Defender SmartScreen может показать предупреждение при первом запуске приложения.

Это происходит потому, что `.exe` новый и пока не подписан цифровой подписью. Это не означает автоматически, что приложение вредоносное.

Если вы доверяете проекту и скачали его с официальной страницы GitHub Releases, нажмите:

Подробнее → Выполнить в любом случае

Исходный код доступен в этом репозитории, поэтому его можно проверить или собрать приложение самостоятельно.

## VS Translator Overlay - это небольшое внешнее оверлей-приложение для Vintage Story под Windows.

Оно:

- читает `client-chat.log` и переводит входящий чат;
- переводит исходящие сообщения с предпросмотром и возможностью редактирования перед вставкой;
- переводит выбранный текст на экране/табличках через Windows OCR;
- работает снаружи игры и не является модом Vintage Story.

## Возможности

- Перевод входящего чата из клиентского лог-файла Vintage Story.
- Перевод исходящих сообщений с предпросмотром, редактированием, копированием и вставкой.
- Windows OCR для выбранной области экрана и быстрый OCR центра экрана.
- Выпадающие списки языков для чата, OCR, языка отправки и исходного языка сообщений.
- Портативная Windows-сборка одной папкой.
- Настройки, логи и отладочные изображения OCR хранятся в `%APPDATA%\VS Translator Overlay`.

## Требования

- Windows 10 или Windows 11.
- Vintage Story.
- Интернет-соединение для онлайн-перевода.
- Языковые пакеты Windows OCR для распознавания неанглийского текста.

## Как пользоваться портативной версией

1. Скачайте zip-архив релиза.
2. Распакуйте папку.
3. Запустите `VS Translator Overlay.exe`.
4. Нажмите `Alt+P`, чтобы открыть настройки.
5. Нажмите `Auto-detect Vintage Story log` или выберите `client-chat.log` вручную.
6. Выберите нужные языки.

Приложение читает чат из локального лог-файла Vintage Story. Оно не изменяет файлы Vintage Story.

## Горячие клавиши

- `Alt+T` - скрыть/показать оверлей
- `Alt+M` - переместить/изменить размер/редактировать оверлей
- `Alt+R` - перевести исходящее сообщение
- `Alt+Q` - быстрый OCR центра экрана
- `Alt+S` - выбрать область экрана для OCR
- `Alt+Shift+Q` - повторить OCR последней области
- `Alt+P` - настройки
- `Alt+X` - выход

## Настройки

- `Read chat/signs in` - язык, на который переводятся входящий чат и текст из OCR.
- `Read signs text as` - исходный язык OCR для текста на экране/табличках. Если не уверены, используйте Auto.
- `Send messages to` - язык, на который переводятся исходящие сообщения.
- `From language for outgoing messages` - исходный язык исходящих сообщений. Если не уверены, используйте Auto.

## Кратко о приватности

Приложение внешнее. Оно не внедряется в процесс игры и не изменяет файлы Vintage Story.

Оно читает локальный файл `client-chat.log` и может захватывать выбранную пользователем область экрана для OCR. Онлайн-перевод выполняется через настроенную библиотеку переводчика, поэтому переводимый текст может отправляться сторонним сервисам перевода.

Не распознавайте через OCR и не переводите чувствительный текст, если не хотите отправлять его онлайн-переводчику.

## Решение проблем

- Если OCR сообщает, что язык недоступен, установите соответствующий языковой пакет Windows OCR.
- Для перевода требуется интернет-соединение.
- Если оверлей не виден, нажмите `Alt+M` или откройте настройки через `Alt+P` и сбросьте позицию оверлея.
- Логи находятся в `%APPDATA%\VS Translator Overlay`.

## Заметки для разработки

Исходную версию можно запускать через Python с установленными зависимостями проекта.

Портативная версия собирается через PyInstaller в режиме one-folder.
