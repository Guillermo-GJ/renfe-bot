<div align="center">

# 🚆 renfe-bot

**Te avisa por Telegram en cuanto queda libre una plaza en el tren de Renfe que quieres.**

[![CI](https://github.com/Guillermo-GJ/renfe-bot/actions/workflows/ci.yml/badge.svg)](https://github.com/Guillermo-GJ/renfe-bot/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13%20%7C%203.14-blue)
![Plataformas](https://img.shields.io/badge/Linux%20%7C%20macOS%20%7C%20Windows-lightgrey)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-green)](LICENSE)

_[English summary below](#-english)_

</div>

---

¿El tren que necesitas sale como **"Completo"**? Cuando alguien cancela, la plaza vuelve a estar
a la venta… durante unos minutos. **renfe-bot** consulta Renfe cada minuto y te manda un aviso al
móvil en cuanto hay sitio, con un botón que te lleva directo a la compra.

```text
🚨 ¡Hay plaza! Madrid Pta. Atocha → Zaragoza-Delicias, 14/03/2027:

🚆 Tren AVE: 🕒 09:30 - 10:50 🕙 - 35.50 €

Pulsa el botón para abrirlo en Renfe (marca «Solo ida» y busca). ¡Corre, que vuela!
                    [ 🎟️ Abrir en Renfe ]
```

## ✨ Qué hace

- 🎯 **Vigila un tren concreto** (por ejemplo, solo el de las 09:30) o **cualquier tren desde una hora**.
- 📅 **Calendario** para elegir el día y **botones con las horas reales** de los trenes de ese día.
- 🔤 **Entiende lo que escribes**: `cordoba` → Córdoba, `delicias` → Zaragoza-Delicias,
  y si te equivocas te propone las estaciones más parecidas como botones.
- 🗓️ Fechas en lenguaje natural: `14/03 09:30`, `14 de marzo a las 09:30`…
- 🔁 **`/repetir`** tu última búsqueda, cambiando el día o la hora si quieres.
- 📊 **`/estado`**: comprueba en cualquier momento que tu búsqueda sigue activa y cómo va.
- 🧪 **`/prueba`**: te manda un aviso de ejemplo para comprobar que las notificaciones te llegan.
- 💾 **No pierde tus búsquedas**: si el bot se reinicia o se va la luz, las retoma solo y te avisa
  (⏸️ al pararse, ▶️ al volver).
- 🌐 **Aguanta los cortes**: si no hay internet o Renfe falla, reintenta cada minuto y te avisa si
  lleva 10 minutos sin poder consultar.
- 🔙 Ida y vuelta, filtros por precio máximo y duración máxima.

## 💬 Comandos

| Comando | Qué hace |
|---|---|
| `/buscar` | Empieza una búsqueda nueva |
| `/repetir` | Repite tu última búsqueda (igual, cambiando la hora o el día) |
| `/estado` | Te dice si tu búsqueda sigue activa, cuántas consultas lleva y el último resultado |
| `/cancelar` | Cancela la búsqueda en curso |
| `/prueba` | Aviso de ejemplo a los 15 s (`/prueba 60` para esperar 60 s) |
| `/ayuda` | Lista de comandos |

## 🚀 Cómo ponerlo en marcha

Necesitas **Python 3.12 o superior** y una cuenta de **Telegram**.

### 1. Crea tu bot de Telegram

1. Abre [@BotFather](https://t.me/botfather) en Telegram y escribe `/newbot`.
2. Elige un nombre y un usuario (tiene que acabar en `bot`).
3. Guarda el **token** que te da. Es la llave de tu bot: **no lo compartas**.

### 2. Instala y arranca

```bash
git clone https://github.com/Guillermo-GJ/renfe-bot.git
cd renfe-bot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=src .venv/bin/python src/bot.py
```

La primera vez te pedirá el token y lo guardará en `config.ini` (que no se sube a git).
Después, abre tu bot en Telegram y escribe `/buscar`.

<details>
<summary>🪟 En Windows</summary>

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
set PYTHONPATH=src
.venv\Scripts\python src\bot.py
```
</details>

<details>
<summary>🐳 Con Docker</summary>

```bash
docker build -t renfe-bot .
docker run -it -v $(pwd):/app renfe-bot
```

Si Docker no te deja escribir el token, créalo tú en `config.ini`:

```ini
[Telegram]
secret_token=123456789:ABCdefGhIjKlmNopQrsTuvWxYz
```
</details>

### 3. Déjalo siempre encendido (opcional, recomendado)

El bot solo vigila mientras está funcionando. Lo ideal es tenerlo en un equipo que esté siempre
encendido: un **portátil viejo con Linux**, una **Raspberry Pi** o un servidor. Consume muy poco
(un portátil antiguo en reposo gasta unos 15–20 W, ~2 € al mes).

En [`deploy/renfe-bot.service`](deploy/renfe-bot.service) tienes un servicio de **systemd** listo
para copiar: arranca el bot con el equipo, lo reinicia si falla y espera a tener internet tras un
corte de luz.

## ⌨️ Búsqueda rápida desde la terminal

También puedes consultar trenes sin Telegram:

```bash
PYTHONPATH=src python src/cli.py -o Madrid -d Barcelona --departure_date 21/06/2027
```

Muestra una tabla con los trenes con plazas (los completos no salen). Añade `--direct` para ver
solo trenes directos.

## 🛠️ Desarrollo

```bash
PYTHONPATH=src .venv/bin/python -m pytest tests --ignore=tests/integration
```

| Archivo | Qué hay |
|---|---|
| `src/bot.py` | Conversación de Telegram, búsquedas en segundo plano y guardado |
| `src/scraper.py` | Consulta de trenes a Renfe |
| `src/calendar_kb.py` | Calendario y botones de horas |
| `src/validators.py`, `src/storage.py` | Estaciones (con sugerencias) y fechas |
| `src/models.py` | Trenes y filtros (incluido el de hora exacta) |

¿Ideas o fallos? Abre una [issue](https://github.com/Guillermo-GJ/renfe-bot/issues) o manda un
pull request.

## ⚠️ Aviso

Proyecto personal, **sin relación con Renfe**. Usa la web pública de Renfe para consultar
disponibilidad y **no compra ni reserva nada**: solo te avisa. Consulta una vez por minuto por
búsqueda; úsalo con cabeza. Si Renfe cambia su web, el bot puede dejar de funcionar hasta que se
actualice.

## 🙏 Créditos

Basado en [**renfe-bot** de emartinez-dev](https://github.com/emartinez-dev/renfe-bot), que hizo
el trabajo duro de entender cómo consulta Renfe sus trenes. Este proyecto parte de su código y añade el calendario, la
vigilancia de un tren exacto, las sugerencias de estaciones, `/repetir`, `/estado`, `/prueba`, el
guardado de búsquedas y el despliegue en servidor.

Licencia [MIT](LICENSE).

---

## 🇬🇧 English

**renfe-bot** is a Telegram bot that watches sold-out trains of Renfe (Spain's railway operator)
and messages you as soon as a seat frees up, with a button that opens the booking page.

- Watch an **exact train** or any train from a given time; pick the day on a **calendar** and the
  time among the **real departures** of that day.
- Fuzzy station names with suggestions, natural-language dates (in Spanish or English).
- `/repetir` (repeat last search), `/estado` (status), `/prueba` (test alert), `/cancelar`.
- Searches **survive restarts and power cuts**, and network errors are retried.

Quick start: create a bot with [@BotFather](https://t.me/botfather), then

```bash
pip install -r requirements.txt
PYTHONPATH=src python src/bot.py   # asks for the token the first time
```

The bot's messages are in Spanish. Based on
[emartinez-dev/renfe-bot](https://github.com/emartinez-dev/renfe-bot) · MIT license.
